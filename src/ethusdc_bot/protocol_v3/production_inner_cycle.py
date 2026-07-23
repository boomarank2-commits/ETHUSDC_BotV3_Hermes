"""Real-data Protocol-v3 inner-cycle execution for Tasks 14 and 16-18."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Final

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles
from ethusdc_bot.backtest.search_space import (
    SearchSpaceState,
    generate_search_space,
    select_candidates_for_testing,
)

from .candidate_matrix import build_candidate_daily_matrix
from .dsr import calculate_dsr
from .inner_folds import InnerFoldPlan, validate_inner_fold_plan
from .inner_selection import (
    build_candidate_selection_evidence,
    build_dsr_development_support,
    build_selection_training_window,
)
from .intrabar_execution import BASELINE_COST_PROFILE
from .pbo import calculate_pbo
from .pipeline import build_pipeline_generation
from .production_fold_evaluator import evaluate_candidate_on_inner_folds
from .run_identity import FrozenExchangeInfoSnapshot
from .runtime_state import HorizonPolicy
from .trial_ledger import (
    append_trial,
    build_trial_record,
    read_trial_ledger,
    record_cache_reuse,
)

PROTOCOL_VERSION: Final = "3.0.0"
RESULT_SCHEMA_VERSION: Final = "protocol_v3_production_inner_cycle_result_v1"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class ProductionInnerCycleError(ValueError):
    """Raised when a real inner cycle is incomplete or not replayable."""


@dataclass(frozen=True)
class ProductionInnerCycleResult:
    canonical_json: str
    result_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["result_sha256"] = self.result_sha256
        return value


def execute_production_inner_cycle(
    *,
    repo_root: str | Path,
    context: AlignedMarketCandles,
    fold_plan: InnerFoldPlan | Mapping[str, Any],
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    horizon_policy: HorizonPolicy,
    trial_ledger_root: str | Path,
    origin_index: int,
    cycle_index: int,
    code_commit: str,
) -> ProductionInnerCycleResult:
    """Evaluate exactly 12 deterministic candidates and append immutable trials."""

    repo = Path(repo_root).resolve(strict=True)
    if not isinstance(context, AlignedMarketCandles):
        raise ProductionInnerCycleError(
            "aligned real three-market context is required"
        )
    plan = validate_inner_fold_plan(fold_plan)
    origin = _positive(origin_index, "origin_index")
    cycle = _positive(cycle_index, "cycle_index")
    commit = str(code_commit).strip().lower()
    if not _COMMIT.fullmatch(commit):
        raise ProductionInnerCycleError(
            "code_commit must be a full lowercase git SHA"
        )
    pipeline = build_pipeline_generation(repo)
    window = build_selection_training_window(plan)
    generated = generate_search_space(
        SearchSpaceState(cycle_index=cycle),
        max_candidates=40,
        context_enabled=False,
    )
    tested = select_candidates_for_testing(
        generated,
        12,
        round_offset=max(0, cycle - 1),
    )
    if len(generated) != 40 or len(tested) != 12:
        raise ProductionInnerCycleError(
            "production candidate budget must remain exactly 40/12"
        )
    ledger_root = Path(trial_ledger_root).resolve(strict=True)
    ledger = read_trial_ledger(ledger_root)
    profiles = []
    summaries = []
    for candidate in tested:
        candidate_id = build_candidate_selection_evidence(
            candidate, {}, window
        ).canonical_candidate_id
        versions = {
            "pipeline_generation": pipeline.generation_id,
            "ranking_version": "protocol_v3_inner_selection_and_pbo_dsr_v1",
            "gate_version": "quality_gate_v1",
            "simulator_version": (
                "next_tradable_price_pessimistic_intrabar_v1"
            ),
            "cost_model_version": "baseline_10bps_fee_5bps_slippage_v1",
            "boundary_version": plan.plan_id,
        }
        scope = {"origin_index": origin, "cycle_index": cycle}
        seed = int(hashlib.sha256(
            f"{origin}:{cycle}:{candidate_id}".encode()
        ).hexdigest()[:16], 16)
        identity_probe = build_trial_record(
            source_kind="native_evaluation",
            candidate_id=candidate_id,
            family=candidate.family,
            parameters=candidate.params,
            feature_variant="protocol_v3_three_market_context_available_v1",
            seed=seed,
            versions=versions,
            code_commit=commit,
            evaluation_scope=scope,
            daily_net_mtm_usdc=[
                {"day": "2000-01-01", "net_usdc": 0.0}
            ],
            result_summary={},
        )
        existing = ledger.trials.get(identity_probe.trial_id)
        reusable = (
            None
            if existing is not None
            else _reusable_trial(
                ledger,
                candidate_id=candidate_id,
                versions=versions,
                code_commit=commit,
            )
        )
        if existing is None and reusable is None:
            evaluation = evaluate_candidate_on_inner_folds(
                context=context,
                candidate=candidate,
                fold_plan=plan,
                exchange_info_snapshot=exchange_info_snapshot,
                horizon_policy=horizon_policy,
                cost_profile=BASELINE_COST_PROFILE,
            )
            evaluated = evaluation.to_dict()
            folds = evaluation.candidate_matrix_folds
            daily = [
                row
                for fold in folds
                for row in fold["daily_net_mtm_usdc"]
            ]
            aggregate = evaluated["aggregate"]
            record = build_trial_record(
                source_kind="native_evaluation",
                candidate_id=candidate_id,
                family=candidate.family,
                parameters=candidate.params,
                feature_variant=(
                    "protocol_v3_three_market_context_available_v1"
                ),
                seed=seed,
                versions=versions,
                code_commit=commit,
                evaluation_scope=scope,
                daily_net_mtm_usdc=daily,
                result_summary={
                    **aggregate,
                    "evaluation_sha256": evaluation.evaluation_sha256,
                },
            )
            ledger = append_trial(ledger_root, record)
            trial_id = record.trial_id
            resumed = False
            cache_reuse = False
            evaluation_sha256 = evaluation.evaluation_sha256
        else:
            source = existing if existing is not None else reusable
            if source is None:
                raise AssertionError("existing or reusable trial required")
            daily = source["daily_net_mtm_usdc"]
            if not isinstance(daily, list) or len(daily) != 360:
                raise ProductionInnerCycleError(
                    "existing production trial lacks complete daily evidence"
                )
            folds = _matrix_folds(plan, daily)
            aggregate = dict(source["result_summary"])
            trial_id = str(source["trial_id"])
            resumed = existing is not None
            cache_reuse = reusable is not None
            if cache_reuse:
                ledger = record_cache_reuse(
                    ledger_root,
                    trial_id=trial_id,
                    reuse_scope=scope,
                )
            evaluation_sha256 = aggregate.get("evaluation_sha256")
        profiles.append(
            {
                "candidate_id": candidate_id,
                "trial_id": trial_id,
                "cache_reuse": cache_reuse,
                "folds": folds,
            }
        )
        summaries.append(
            {
                "candidate_id": candidate_id,
                "trial_id": trial_id,
                "family": candidate.family,
                "parameters": dict(candidate.params),
                "net_profit_usdc": float(aggregate["net_profit_usdc"]),
                "net_usdc_per_day": float(
                    aggregate["net_usdc_per_day"]
                ),
                "trade_count": int(aggregate["trade_count"]),
                "evaluation_sha256": evaluation_sha256,
                "resumed_from_permanent_trial": resumed,
                "cache_reuse": cache_reuse,
            }
        )
    ledger = read_trial_ledger(ledger_root)
    ranked = sorted(
        summaries,
        key=lambda row: (
            -row["net_usdc_per_day"],
            row["candidate_id"],
        ),
    )
    tested_ids = sorted(row["candidate_id"] for row in summaries)
    promoted_ids = sorted(row["candidate_id"] for row in ranked[:3])
    finalist_ids = sorted(row["candidate_id"] for row in ranked[:2])
    matrix = build_candidate_daily_matrix(
        fold_plan=plan,
        origin_index=origin,
        cycles=[
            {
                "cycle_index": cycle,
                "tested_candidate_ids": tested_ids,
                "promoted_candidate_ids": promoted_ids,
                "finalist_candidate_ids": finalist_ids,
                "profiles": profiles,
            }
        ],
        trial_ledger=ledger,
    )
    pbo = calculate_pbo(matrix)
    matrix_cycle = matrix.to_dict()["cycles"][0]
    dsr_by_candidate = {
        profile["candidate_id"]: calculate_dsr(
            pbo_evidence=pbo,
            selected_profile_id=profile["profile_id"],
            trial_ledger=ledger,
        )
        for profile in matrix_cycle["profiles"]
    }
    support = build_dsr_development_support(
        dsr_by_candidate,
        cycle_index=cycle,
        trial_ledger=ledger,
    )
    basis = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "code_commit": commit,
        "pipeline_generation_id": pipeline.generation_id,
        "origin_index": origin,
        "cycle_index": cycle,
        "fold_plan_sha256": plan.plan_sha256,
        "generated_candidate_count": len(generated),
        "tested_candidate_count": len(tested),
        "candidate_summaries": sorted(
            summaries, key=lambda row: row["candidate_id"]
        ),
        "promoted_candidate_ids": promoted_ids,
        "finalist_candidate_ids": finalist_ids,
        "matrix": matrix.to_dict(),
        "pbo": pbo.to_dict(),
        "dsr_by_candidate": {
            key: value.to_dict()
            for key, value in sorted(dsr_by_candidate.items())
        },
        "development_support": support.to_dict(),
        "trial_ledger_head_sha256": ledger.status.head_sha256,
        "safety": dict(_SAFETY),
    }
    return validate_production_inner_cycle_result(
        ProductionInnerCycleResult(_canonical(basis), _digest(basis))
    )


def validate_production_inner_cycle_result(
    value: ProductionInnerCycleResult | Mapping[str, Any],
) -> ProductionInnerCycleResult:
    root = (
        value.to_dict()
        if isinstance(value, ProductionInnerCycleResult)
        else dict(_mapping(value, "production_inner_cycle_result"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "code_commit",
        "pipeline_generation_id",
        "origin_index",
        "cycle_index",
        "fold_plan_sha256",
        "generated_candidate_count",
        "tested_candidate_count",
        "candidate_summaries",
        "promoted_candidate_ids",
        "finalist_candidate_ids",
        "matrix",
        "pbo",
        "dsr_by_candidate",
        "development_support",
        "trial_ledger_head_sha256",
        "safety",
        "result_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != RESULT_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["safety"] != _SAFETY
        or not _COMMIT.fullmatch(str(root["code_commit"]))
        or root["generated_candidate_count"] != 40
        or root["tested_candidate_count"] != 12
        or not isinstance(root["candidate_summaries"], list)
        or not isinstance(root["promoted_candidate_ids"], list)
        or not isinstance(root["finalist_candidate_ids"], list)
        or len(root["candidate_summaries"]) != 12
        or len(root["promoted_candidate_ids"]) != 3
        or len(root["finalist_candidate_ids"]) != 2
    ):
        raise ProductionInnerCycleError(
            "production inner-cycle fields or budgets are invalid"
        )
    matrix = _mapping(root["matrix"], "matrix")
    pbo = _mapping(root["pbo"], "pbo")
    support = _mapping(root["development_support"], "development_support")
    if (
        matrix.get("matrix_sha256")
        != pbo.get("matrix_identity", {}).get("matrix_sha256")
        or support.get("matrix", {}).get("evidence_sha256")
        != matrix.get("matrix_sha256")
        or support.get("pbo", {}).get("evidence_sha256")
        != pbo.get("evidence_sha256")
        or matrix.get("trial_ledger_head_sha256")
        != root["trial_ledger_head_sha256"]
    ):
        raise ProductionInnerCycleError(
            "production inner-cycle evidence chain is inconsistent"
        )
    observed = root.pop("result_sha256")
    if observed != _digest(root):
        raise ProductionInnerCycleError(
            "production inner-cycle result digest mismatch"
        )
    return ProductionInnerCycleResult(_canonical(root), observed)


def write_production_inner_cycle_result(
    value: ProductionInnerCycleResult | Mapping[str, Any],
    path: str | Path,
) -> Path:
    result = validate_production_inner_cycle_result(value)
    target = Path(path)
    if not target.is_absolute():
        raise ProductionInnerCycleError("cycle result path must be absolute")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical(result.to_dict()) + "\n")
    except FileExistsError as exc:
        raise ProductionInnerCycleError(
            "production inner-cycle result is create-only"
        ) from exc
    return target


def _matrix_folds(
    plan: InnerFoldPlan, daily: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if len(daily) != 360:
        raise ProductionInnerCycleError(
            "production trial must contain exactly 360 daily rows"
        )
    return [
        {
            "fold_index": fold.fold_index,
            "fold_id": fold.fold_id,
            "daily_net_mtm_usdc": daily[index * 60 : (index + 1) * 60],
        }
        for index, fold in enumerate(plan.folds)
    ]


def _reusable_trial(
    ledger,
    *,
    candidate_id: str,
    versions: Mapping[str, str],
    code_commit: str,
) -> dict[str, Any] | None:
    matches = []
    for trial in ledger.trials.values():
        identity = trial.get("identity_basis", {})
        candidate = identity.get("candidate", {})
        if (
            candidate.get("candidate_id") == candidate_id
            and identity.get("versions") == dict(versions)
            and identity.get("code_commit") == code_commit
            and identity.get("feature_variant")
            == "protocol_v3_three_market_context_available_v1"
        ):
            matches.append(trial)
    if len(matches) > 1:
        raise ProductionInnerCycleError(
            "multiple independent trials exist for one reusable candidate/window"
        )
    return matches[0] if matches else None


def _positive(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProductionInnerCycleError(f"{path} must be positive")
    return value


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionInnerCycleError(f"{path} must be an object")
    return dict(value)


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
    "ProductionInnerCycleError",
    "ProductionInnerCycleResult",
    "RESULT_SCHEMA_VERSION",
    "execute_production_inner_cycle",
    "validate_production_inner_cycle_result",
    "write_production_inner_cycle_result",
]
