"""Exact real-data Task-14 fold evaluation through the Task-8 simulator."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import math
from typing import Any, Final

from ethusdc_bot.backtest.data_loader import (
    AlignedMarketCandles,
    EXPECTED_STEP_MS,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate

from .inner_folds import InnerFoldPlan, validate_inner_fold_plan
from .intrabar_execution import (
    BASELINE_COST_PROFILE,
    ExecutionCostProfile,
    simulate_protocol_v3_intrabar_strategy,
)
from .run_identity import FrozenExchangeInfoSnapshot
from .runtime_state import HorizonPolicy

PROTOCOL_VERSION: Final = "3.0.0"
EVALUATION_SCHEMA_VERSION: Final = (
    "protocol_v3_production_inner_fold_evaluation_v1"
)
MINUTES_PER_DAY: Final = 1440
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class ProductionFoldEvaluationError(ValueError):
    """Raised when a real inner-fold evaluation is incomplete or inconsistent."""


@dataclass(frozen=True)
class ProductionFoldEvaluation:
    canonical_json: str
    evaluation_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["evaluation_sha256"] = self.evaluation_sha256
        return value

    @property
    def candidate_matrix_folds(self) -> list[dict[str, Any]]:
        return [
            {
                "fold_index": row["fold_index"],
                "fold_id": row["fold_id"],
                "daily_net_mtm_usdc": row["daily_net_mtm_usdc"],
            }
            for row in self.to_dict()["folds"]
        ]


def evaluate_candidate_on_inner_folds(
    *,
    context: AlignedMarketCandles,
    candidate: StrategyCandidate,
    fold_plan: InnerFoldPlan | Mapping[str, Any],
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    horizon_policy: HorizonPolicy,
    cost_profile: ExecutionCostProfile = BASELINE_COST_PROFILE,
) -> ProductionFoldEvaluation:
    """Evaluate six flat-start 60-day folds with explicit daily MTM deltas."""

    if not isinstance(context, AlignedMarketCandles):
        raise ProductionFoldEvaluationError(
            "aligned real three-market context is required"
        )
    if not isinstance(candidate, StrategyCandidate):
        raise ProductionFoldEvaluationError("StrategyCandidate is required")
    plan = validate_inner_fold_plan(fold_plan)
    rows = []
    for fold in plan.folds:
        fold_context = _slice_fold_context(
            context,
            start_ms=fold.validation_start_ms,
            end_ms=fold.validation_end_ms,
        )
        result = simulate_protocol_v3_intrabar_strategy(
            list(fold_context.ethusdc),
            candidate,
            days=fold.validation_days,
            exchange_info_snapshot=exchange_info_snapshot,
            horizon_policy=horizon_policy,
            cost_profile=cost_profile,
            training_days=730,
            blindtest_days=0,
            market_context=fold_context,
        )
        daily = _daily_mtm(
            result.equity_curve,
            start=fold.validation_start_inclusive_utc,
            days=fold.validation_days,
        )
        total = math.fsum(item["net_usdc"] for item in daily)
        if not math.isclose(
            total,
            float(result.metrics.net_profit_usdc),
            rel_tol=0.0,
            abs_tol=1e-8,
        ):
            raise ProductionFoldEvaluationError(
                "daily MTM total differs from simulator net profit"
            )
        gross_profit = math.fsum(
            max(0.0, float(trade.net_profit_usdc))
            for trade in result.trades
        )
        gross_loss = abs(
            math.fsum(
                min(0.0, float(trade.net_profit_usdc))
                for trade in result.trades
            )
        )
        basis = {
            "fold_index": fold.fold_index,
            "fold_id": fold.fold_id,
            "validation_start_inclusive_utc": _utc_text(
                fold.validation_start_inclusive_utc
            ),
            "validation_end_exclusive_utc": _utc_text(
                fold.validation_end_exclusive_utc
            ),
            "daily_net_mtm_usdc": daily,
            "metrics": {
                "trade_count": result.metrics.trade_count,
                "net_profit_usdc": result.metrics.net_profit_usdc,
                "net_usdc_per_day": result.metrics.net_usdc_per_day,
                "gross_profit_usdc": gross_profit,
                "gross_loss_usdc": gross_loss,
                "fees_usdc": result.metrics.fees_usdc,
                "slippage_usdc": result.metrics.slippage_usdc,
                "max_drawdown_usdc": result.metrics.max_drawdown_usdc,
                "profit_factor": result.metrics.profit_factor,
            },
            "signal_funnel": dict(sorted(result.signal_funnel.items())),
            "rejection_reasons": dict(sorted(result.rejection_reasons.items())),
        }
        rows.append({**basis, "fold_sha256": _digest(basis)})
    candidate_payload = {
        "family": candidate.family,
        "params": dict(candidate.params),
    }
    aggregate = {
        "validation_days": sum(
            len(row["daily_net_mtm_usdc"]) for row in rows
        ),
        "trade_count": sum(row["metrics"]["trade_count"] for row in rows),
        "net_profit_usdc": math.fsum(
            row["metrics"]["net_profit_usdc"] for row in rows
        ),
        "fees_usdc": math.fsum(row["metrics"]["fees_usdc"] for row in rows),
        "slippage_usdc": math.fsum(
            row["metrics"]["slippage_usdc"] for row in rows
        ),
        "positive_fold_count": sum(
            row["metrics"]["net_profit_usdc"] > 0 for row in rows
        ),
    }
    aggregate["net_usdc_per_day"] = (
        aggregate["net_profit_usdc"] / aggregate["validation_days"]
    )
    basis = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "candidate": candidate_payload,
        "candidate_sha256": _digest(candidate_payload),
        "fold_plan_sha256": plan.plan_sha256,
        "cost_profile": {
            "name": cost_profile.name,
            "fee_bps_per_side": str(cost_profile.fee_bps_per_side),
            "slippage_bps_per_side": str(cost_profile.slippage_bps_per_side),
        },
        "folds": rows,
        "aggregate": aggregate,
        "safety": dict(_SAFETY),
    }
    return validate_production_fold_evaluation(
        ProductionFoldEvaluation(_canonical(basis), _digest(basis)),
        fold_plan=plan,
    )


def validate_production_fold_evaluation(
    value: ProductionFoldEvaluation | Mapping[str, Any],
    *,
    fold_plan: InnerFoldPlan | Mapping[str, Any],
) -> ProductionFoldEvaluation:
    root = (
        value.to_dict()
        if isinstance(value, ProductionFoldEvaluation)
        else dict(_mapping(value, "production_fold_evaluation"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "candidate",
        "candidate_sha256",
        "fold_plan_sha256",
        "cost_profile",
        "folds",
        "aggregate",
        "safety",
        "evaluation_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != EVALUATION_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["safety"] != _SAFETY
    ):
        raise ProductionFoldEvaluationError(
            "production fold-evaluation fields are invalid"
        )
    plan = validate_inner_fold_plan(fold_plan)
    if root["fold_plan_sha256"] != plan.plan_sha256:
        raise ProductionFoldEvaluationError(
            "production fold evaluation belongs to another fold plan"
        )
    candidate = _mapping(root["candidate"], "candidate")
    if (
        set(candidate) != {"family", "params"}
        or not isinstance(candidate["family"], str)
        or not candidate["family"]
        or not isinstance(candidate["params"], Mapping)
        or root["candidate_sha256"] != _digest(candidate)
    ):
        raise ProductionFoldEvaluationError(
            "production fold candidate identity is invalid"
        )
    folds = root["folds"]
    if not isinstance(folds, list) or len(folds) != 6:
        raise ProductionFoldEvaluationError(
            "production evaluation requires exactly six folds"
        )
    for row, boundary in zip(folds, plan.folds, strict=True):
        item = _mapping(row, "fold")
        daily_rows = item.get("daily_net_mtm_usdc")
        if (
            item.get("fold_index") != boundary.fold_index
            or item.get("fold_id") != boundary.fold_id
            or not isinstance(daily_rows, list)
            or len(daily_rows) != 60
            or any(
                not isinstance(daily, Mapping)
                or set(daily) != {"day", "net_usdc"}
                or isinstance(daily["net_usdc"], bool)
                or not isinstance(daily["net_usdc"], (int, float))
                or not math.isfinite(float(daily["net_usdc"]))
                for daily in daily_rows
            )
        ):
            raise ProductionFoldEvaluationError(
                "production fold provenance or day count is invalid"
            )
        expected_days = [
            (
                boundary.validation_start_inclusive_utc.date()
                + timedelta(days=index)
            ).isoformat()
            for index in range(60)
        ]
        if [
            daily.get("day")
            for daily in daily_rows
        ] != expected_days:
            raise ProductionFoldEvaluationError(
                "production fold daily MTM grid is invalid"
            )
        observed = item.get("fold_sha256")
        fold_basis = dict(item)
        fold_basis.pop("fold_sha256", None)
        if observed != _digest(fold_basis):
            raise ProductionFoldEvaluationError(
                "production fold digest mismatch"
            )
    aggregate = _mapping(root["aggregate"], "aggregate")
    if (
        aggregate.get("validation_days") != 360
        or aggregate.get("trade_count")
        != sum(row["metrics"]["trade_count"] for row in folds)
        or not math.isclose(
            float(aggregate.get("net_profit_usdc", math.nan)),
            math.fsum(
                daily["net_usdc"]
                for row in folds
                for daily in row["daily_net_mtm_usdc"]
            ),
            rel_tol=0.0,
            abs_tol=1e-8,
        )
    ):
        raise ProductionFoldEvaluationError(
            "production fold aggregate is invalid"
        )
    observed = root.pop("evaluation_sha256")
    if observed != _digest(root):
        raise ProductionFoldEvaluationError(
            "production fold evaluation digest mismatch"
        )
    return ProductionFoldEvaluation(_canonical(root), observed)


def _slice_fold_context(
    context: AlignedMarketCandles,
    *,
    start_ms: int,
    end_ms: int,
) -> AlignedMarketCandles:
    indexes = [
        index
        for index, candle in enumerate(context.ethusdc)
        if start_ms <= candle.open_time < end_ms
    ]
    expected = (end_ms - start_ms) // EXPECTED_STEP_MS
    if (
        not indexes
        or len(indexes) != expected
        or indexes != list(range(indexes[0], indexes[-1] + 1))
    ):
        raise ProductionFoldEvaluationError(
            "aligned context does not cover the complete fold minute grid"
        )
    start = indexes[0]
    stop = indexes[-1] + 1
    return AlignedMarketCandles(
        ethusdc=context.ethusdc[start:stop],
        btcusdc=context.btcusdc[start:stop],
        ethbtc=context.ethbtc[start:stop],
    )


def _daily_mtm(
    points,
    *,
    start: datetime,
    days: int,
) -> list[dict[str, Any]]:
    if not points:
        raise ProductionFoldEvaluationError("simulator equity curve is empty")
    rows = []
    prior = 0.0
    for index in range(days):
        day = start + timedelta(days=index)
        cutoff = int((day + timedelta(days=1)).timestamp() * 1000)
        eligible = [point for point in points if point.timestamp_ms < cutoff]
        if not eligible:
            raise ProductionFoldEvaluationError(
                "simulator equity curve misses a validation day"
            )
        closing = float(eligible[-1].equity_usdc)
        rows.append(
            {
                "day": day.date().isoformat(),
                "net_usdc": round(closing - prior, 10),
            }
        )
        prior = closing
    return rows


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionFoldEvaluationError(f"{path} must be an object")
    return dict(value)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


__all__ = [
    "EVALUATION_SCHEMA_VERSION",
    "ProductionFoldEvaluation",
    "ProductionFoldEvaluationError",
    "evaluate_candidate_on_inner_folds",
    "validate_production_fold_evaluation",
]
