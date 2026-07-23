"""Real training-only quality evidence for Protocol-v3 cycle finalists."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Final

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles
from ethusdc_bot.backtest.equity import (
    chain_equity_curves,
    max_drawdown_usdc,
    max_underwater_calendar_days,
)
from ethusdc_bot.backtest.metrics import compute_metrics
from ethusdc_bot.backtest.quality_gates import (
    QUALITY_GATE_V1,
    evaluate_quality_gates,
)
from ethusdc_bot.backtest.selection_evidence import (
    generate_parameter_neighbors,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.backtest.walk_forward import summarize_walk_forward
from ethusdc_bot.backtest.walk_forward_evidence import (
    FoldSelectionObservation,
    build_walk_forward_selection_evidence,
    build_walk_forward_stress_evidence,
)

from .inner_folds import InnerFoldPlan, validate_inner_fold_plan
from .intrabar_execution import (
    BASELINE_COST_PROFILE,
    JOINT_STRESS_COST_PROFILE,
    SLIPPAGE_STRESS_COST_PROFILE,
    ExecutionCostProfile,
    simulate_protocol_v3_intrabar_strategy,
)
from .production_fold_evaluator import _slice_fold_context
from .run_identity import FrozenExchangeInfoSnapshot
from .runtime_state import HorizonPolicy

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_production_finalist_quality_contract.json"
)
CONTRACT_SCHEMA_VERSION: Final = (
    "protocol_v3_production_finalist_quality_contract_v1"
)
CONTRACT_VERSION: Final = "protocol_v3_real_finalist_quality_evidence_v1"
MAX_NUMERIC_PARAMETERS: Final = 18
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "input_policy": {
        "selection_window_days": 730,
        "validation_union_days": 360,
        "fold_count": 6,
        "fold_days": 60,
        "finalists_per_cycle": 2,
        "training_only": True,
        "audit_or_holdout_forbidden": True,
    },
    "evaluation_policy": {
        "simulator": "protocol_v3_intrabar_execution",
        "baseline_fee_bps_per_side": 10,
        "baseline_slippage_bps_per_side": 5,
        "joint_fee_bps_per_side": 15,
        "joint_slippage_bps_per_side": 10,
        "slippage_fee_bps_per_side": 10,
        "slippage_stress_bps_per_side": 15,
        "flat_start_per_wfv_fold": True,
        "full_training_replay_required": True,
        "continuous_validation_replay_required": True,
        "all_numeric_parameter_neighbors_required": True,
        "parameter_neighbor_limit": MAX_NUMERIC_PARAMETERS,
        "rolling_temporal_regime_from_baseline_wfv": True,
    },
    "output_policy": {
        "quality_gate_version": QUALITY_GATE_V1.version,
        "missing_or_invalid_gate_evidence_forbidden": True,
        "candidate_evidence_hash_binding_required": True,
        "outer_results_forbidden": True,
        "target_usdc_per_day_used": False,
    },
    "safety": _SAFETY,
}


class ProductionFinalistQualityError(ValueError):
    """Raised when real finalist evidence is incomplete or non-causal."""


def load_production_finalist_quality_contract(
    repo_root: str | Path,
) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProductionFinalistQualityError(
            "production finalist-quality contract is missing or invalid"
        ) from exc
    if value != _CANONICAL_CONTRACT:
        raise ProductionFinalistQualityError(
            "production finalist-quality contract is not canonical"
        )
    return value


def build_production_finalist_quality_evidence(
    *,
    repo_root: str | Path,
    context: AlignedMarketCandles,
    candidate: StrategyCandidate,
    fold_plan: InnerFoldPlan | Mapping[str, Any],
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    horizon_policy: HorizonPolicy,
) -> dict[str, Any]:
    """Evaluate one finalist only on its 730-day development window."""

    load_production_finalist_quality_contract(repo_root)
    if not isinstance(context, AlignedMarketCandles):
        raise ProductionFinalistQualityError(
            "aligned real three-market context is required"
        )
    if not isinstance(candidate, StrategyCandidate):
        raise ProductionFinalistQualityError("StrategyCandidate is required")
    plan = validate_inner_fold_plan(fold_plan)
    baseline = _profile_summary(
        context=context,
        candidate=candidate,
        plan=plan,
        exchange_info_snapshot=exchange_info_snapshot,
        horizon_policy=horizon_policy,
        cost_profile=BASELINE_COST_PROFILE,
        include_selection_evidence=True,
    )
    joint = _profile_summary(
        context=context,
        candidate=candidate,
        plan=plan,
        exchange_info_snapshot=exchange_info_snapshot,
        horizon_policy=horizon_policy,
        cost_profile=JOINT_STRESS_COST_PROFILE,
        include_selection_evidence=False,
    )
    slippage = _profile_summary(
        context=context,
        candidate=candidate,
        plan=plan,
        exchange_info_snapshot=exchange_info_snapshot,
        horizon_policy=horizon_policy,
        cost_profile=SLIPPAGE_STRESS_COST_PROFILE,
        include_selection_evidence=False,
    )
    training_context = _slice_fold_context(
        context,
        start_ms=_timestamp_ms(plan.training_start_inclusive_utc),
        end_ms=_timestamp_ms(plan.training_end_exclusive_utc),
    )
    validation_context = _slice_fold_context(
        context,
        start_ms=plan.folds[0].validation_start_ms,
        end_ms=plan.folds[-1].validation_end_ms,
    )
    full_training = _simulate(
        training_context,
        candidate,
        days=730,
        exchange_info_snapshot=exchange_info_snapshot,
        horizon_policy=horizon_policy,
        cost_profile=BASELINE_COST_PROFILE,
    )
    validation = _simulate(
        validation_context,
        candidate,
        days=360,
        exchange_info_snapshot=exchange_info_snapshot,
        horizon_policy=horizon_policy,
        cost_profile=BASELINE_COST_PROFILE,
    )
    baseline_selection = baseline["selection_evidence"]
    aggregate = dict(baseline["aggregate_metrics"])
    aggregate.update(
        {
            "positive_fold_count": baseline["positive_fold_count"],
            "folds_pf_at_least_1_05": baseline[
                "folds_pf_at_least_1_05"
            ],
            "worst_fold_profit_factor": baseline[
                "worst_fold_profit_factor"
            ],
            "median_fold_net_usdc_per_day": baseline[
                "median_fold_net_usdc_per_day"
            ],
            "worst_fold_net_usdc_per_day": baseline[
                "worst_fold_net_usdc_per_day"
            ],
            "fold_net_coefficient_of_variation": baseline[
                "fold_net_coefficient_of_variation"
            ],
            "full_training_net_usdc_per_day": (
                full_training.metrics.net_usdc_per_day
            ),
        }
    )
    evidence = {
        "protocol": {
            "gate_version": QUALITY_GATE_V1.version,
            "gate_frozen_before_evaluation": True,
            "selection_uses_audit": False,
            "producer": CONTRACT_VERSION,
            "target_usdc_per_day_used": False,
        },
        "validation": _validation_metrics(validation),
        "wfv": {
            "fold_count": baseline["fold_count"],
            "folds": baseline["folds"],
            "aggregate": aggregate,
        },
        "rolling": baseline_selection["rolling"],
        "stress": build_walk_forward_stress_evidence(
            baseline,
            joint,
            slippage,
            baseline_fee_bps=float(
                BASELINE_COST_PROFILE.fee_bps_per_side
            ),
            baseline_slippage_bps=float(
                BASELINE_COST_PROFILE.slippage_bps_per_side
            ),
            joint_fee_bps=float(
                JOINT_STRESS_COST_PROFILE.fee_bps_per_side
            ),
            joint_slippage_bps=float(
                JOINT_STRESS_COST_PROFILE.slippage_bps_per_side
            ),
            slippage_fee_bps=float(
                SLIPPAGE_STRESS_COST_PROFILE.fee_bps_per_side
            ),
            slippage_stress_bps=float(
                SLIPPAGE_STRESS_COST_PROFILE.slippage_bps_per_side
            ),
        ),
        "parameter_stability": _parameter_stability(
            context=validation_context,
            candidate=candidate,
            baseline=validation,
            exchange_info_snapshot=exchange_info_snapshot,
            horizon_policy=horizon_policy,
        ),
        "temporal": baseline_selection["temporal"],
        "regime": baseline_selection["regime"],
        "selection_evidence_provenance": {
            "selection_data_only": True,
            "uses_audit_or_holdout": False,
            "fold_plan_sha256": plan.plan_sha256,
            "rolling_temporal_regime_source": (
                "protocol_v3_exact_6x60_validation_folds"
            ),
            "parameter_source": "continuous_360_day_validation_union",
            "stress_source": "same_exact_6x60_folds_fixed_cost_profiles",
            "full_training_source": "exact_730_day_development_window",
        },
        "safety": dict(_SAFETY),
    }
    return validate_production_finalist_quality_evidence(evidence)


def validate_production_finalist_quality_evidence(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionFinalistQualityError(
            "finalist quality evidence must be an object"
        )
    root = json.loads(
        json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )
    expected = {
        "protocol",
        "validation",
        "wfv",
        "rolling",
        "stress",
        "parameter_stability",
        "temporal",
        "regime",
        "selection_evidence_provenance",
        "safety",
    }
    protocol = root.get("protocol")
    provenance = root.get("selection_evidence_provenance")
    if (
        set(root) != expected
        or not isinstance(protocol, dict)
        or protocol.get("gate_version") != QUALITY_GATE_V1.version
        or protocol.get("gate_frozen_before_evaluation") is not True
        or protocol.get("selection_uses_audit") is not False
        or protocol.get("producer") != CONTRACT_VERSION
        or protocol.get("target_usdc_per_day_used") is not False
        or root.get("safety") != _SAFETY
        or not isinstance(provenance, dict)
        or provenance.get("selection_data_only") is not True
        or provenance.get("uses_audit_or_holdout") is not False
    ):
        raise ProductionFinalistQualityError(
            "finalist quality evidence provenance is invalid"
        )
    wfv = root.get("wfv")
    if (
        not isinstance(wfv, dict)
        or wfv.get("fold_count") != 6
        or not isinstance(wfv.get("folds"), list)
        or len(wfv["folds"]) != 6
        or any(row.get("days") != 60 for row in wfv["folds"])
    ):
        raise ProductionFinalistQualityError(
            "finalist quality evidence lacks exact 6x60 WFV"
        )
    gate = evaluate_quality_gates(root, stage="selection").to_dict()
    if gate["status"] not in {"pass", "fail_gate"}:
        raise ProductionFinalistQualityError(
            "finalist quality evidence is missing or invalid"
        )
    return root


def _profile_summary(
    *,
    context: AlignedMarketCandles,
    candidate: StrategyCandidate,
    plan: InnerFoldPlan,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    horizon_policy: HorizonPolicy,
    cost_profile: ExecutionCostProfile,
    include_selection_evidence: bool,
) -> dict[str, Any]:
    fold_rows = []
    observations = []
    trades = []
    curves = []
    for fold in plan.folds:
        validation_context = _slice_fold_context(
            context,
            start_ms=fold.validation_start_ms,
            end_ms=fold.validation_end_ms,
        )
        training_context = _slice_fold_context(
            context,
            start_ms=fold.fit_start_ms,
            end_ms=fold.fit_end_ms,
        )
        result = _simulate(
            validation_context,
            candidate,
            days=60,
            exchange_info_snapshot=exchange_info_snapshot,
            horizon_policy=horizon_policy,
            cost_profile=cost_profile,
        )
        metrics = result.metrics.to_dict()
        metrics.update(
            {
                "gross_profit_usdc": math.fsum(
                    max(0.0, float(row.net_profit_usdc))
                    for row in result.trades
                ),
                "gross_loss_usdc": abs(
                    math.fsum(
                        min(0.0, float(row.net_profit_usdc))
                        for row in result.trades
                    )
                ),
                "drawdown_method": result.drawdown_method,
            }
        )
        fold_rows.append(
            {
                "fold_id": fold.fold_index,
                "days": 60,
                "metrics": metrics,
                "equity_curve_usdc": result.equity_curve_usdc,
                "equity_curve_timestamps_ms": (
                    result.equity_curve_timestamps_ms
                ),
            }
        )
        observations.append(
            FoldSelectionObservation(
                fold_id=fold.fold_index,
                training_candles=tuple(training_context.ethusdc),
                validation_candles=tuple(validation_context.ethusdc),
                result=result,
            )
        )
        trades.extend(result.trades)
        curves.append(result.equity_curve)
    chained = chain_equity_curves(curves)
    aggregate = compute_metrics(
        trades,
        days=360,
        training_days=730,
        blindtest_days=0,
    )
    aggregate = type(aggregate)(
        **{
            **aggregate.to_dict(),
            "max_drawdown_usdc": max_drawdown_usdc(chained),
        }
    )
    summary = summarize_walk_forward(
        fold_rows,
        aggregate_metrics=aggregate,
        aggregate_max_underwater_days=max_underwater_calendar_days(chained),
    )
    if include_selection_evidence:
        summary["selection_evidence"] = (
            build_walk_forward_selection_evidence(
                observations,
                chained_equity=chained,
            )
        )
    else:
        summary["selection_evidence"] = {
            "not_computed_reason": (
                "stress_profile_reuses_baseline_selection_evidence"
            ),
            "uses_audit_or_holdout": False,
        }
    return summary


def _parameter_stability(
    *,
    context: AlignedMarketCandles,
    candidate: StrategyCandidate,
    baseline: Any,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    horizon_policy: HorizonPolicy,
) -> dict[str, Any]:
    specs, numeric_count = generate_parameter_neighbors(
        candidate,
        perturbation_fraction=QUALITY_GATE_V1.parameter_perturbation_fraction,
        session_hour_step=QUALITY_GATE_V1.parameter_session_hour_step,
    )
    if numeric_count > MAX_NUMERIC_PARAMETERS:
        raise ProductionFinalistQualityError(
            "candidate exceeds frozen parameter-neighbor budget"
        )
    rows = []
    for parameter, direction, value, neighbor in specs:
        result = _simulate(
            context,
            neighbor,
            days=360,
            exchange_info_snapshot=exchange_info_snapshot,
            horizon_policy=horizon_policy,
            cost_profile=BASELINE_COST_PROFILE,
        )
        rows.append(
            {
                "parameter": parameter,
                "direction": direction,
                "value": value,
                "net_usdc_per_day": result.metrics.net_usdc_per_day,
                "profit_factor": result.metrics.profit_factor,
                "max_drawdown_usdc": result.metrics.max_drawdown_usdc,
                "trade_count": result.metrics.trade_count,
            }
        )
    passing = [
        row
        for row in rows
        if row["net_usdc_per_day"] > 0
        and row["profit_factor"] >= QUALITY_GATE_V1.min_validation_profit_factor
        and row["max_drawdown_usdc"]
        <= QUALITY_GATE_V1.max_validation_drawdown_usdc
    ]
    baseline_net = float(baseline.metrics.net_usdc_per_day)
    neighbor_nets = [float(row["net_usdc_per_day"]) for row in rows]
    retention = (
        [value / baseline_net for value in neighbor_nets]
        if baseline_net > 0
        else []
    )
    return {
        "all_numeric_parameters_perturbed": len(rows) >= numeric_count * 2,
        "numeric_parameter_count": numeric_count,
        "neighbor_count": len(rows),
        "perturbation_fraction": (
            QUALITY_GATE_V1.parameter_perturbation_fraction
        ),
        "session_hour_step": QUALITY_GATE_V1.parameter_session_hour_step,
        "passing_neighbor_fraction": (
            round(len(passing) / len(rows), 10) if rows else 0.0
        ),
        "median_net_retention": (
            round(median(retention), 10) if retention else 0.0
        ),
        "worst_neighbor_net_usdc_per_day": (
            round(min(neighbor_nets), 10) if neighbor_nets else 0.0
        ),
        "baseline_net_usdc_per_day": baseline_net,
        "neighbors": rows,
        "uses_audit_or_holdout": False,
    }


def _validation_metrics(result: Any) -> dict[str, Any]:
    payload = result.metrics.to_dict()
    payload["drawdown_method"] = result.drawdown_method
    payload["max_underwater_days"] = result.max_underwater_days
    return payload


def _simulate(
    context: AlignedMarketCandles,
    candidate: StrategyCandidate,
    *,
    days: int,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    horizon_policy: HorizonPolicy,
    cost_profile: ExecutionCostProfile,
) -> Any:
    return simulate_protocol_v3_intrabar_strategy(
        list(context.ethusdc),
        candidate,
        days=days,
        exchange_info_snapshot=exchange_info_snapshot,
        horizon_policy=horizon_policy,
        cost_profile=cost_profile,
        training_days=730,
        blindtest_days=0,
        market_context=context,
    )


def _timestamp_ms(value: Any) -> int:
    return int(value.timestamp() * 1000)


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "MAX_NUMERIC_PARAMETERS",
    "ProductionFinalistQualityError",
    "build_production_finalist_quality_evidence",
    "load_production_finalist_quality_contract",
    "validate_production_finalist_quality_evidence",
]
