"""Research protocol guardrails for reproducible offline strategy search."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

STRATEGY_FAMILIES = (
    "momentum_trend_filter",
    "breakout_volatility_filter",
    "mean_reversion_regime_filter",
    "pullback_in_trend",
    "session_filter",
    "cooldown_fee_aware",
)

SELECTION_DATA = ("subtrain", "validation", "walk_forward")
RANKING_RULES = (
    "validation_only_pre_rank_without_holdout",
    "wfv_day_weighted_net_usdc_per_day_desc",
    "wfv_aggregate_profit_factor_desc",
    "wfv_aggregate_max_drawdown_asc",
    "wfv_fold_stability_tiebreakers",
    "quality_gate_v1_before_freeze",
)
REQUIRED_REPORT_PATHS = (
    "loop_run_id",
    "window_plan",
    "research_protocol.parameter_space",
    "cycles[].generated_candidate_inventory",
    "cycles[].candidate_leaderboard_summary",
    "cycles[].walk_forward_summaries",
    "cycles[].finalist_summaries",
    "candidate_stage_totals",
    "audit_policy",
    "safety_status",
)

# Historical ledger only. These fixed dates never drive dynamic window
# selection; they prevent a previously viewed window from becoming eligible
# for optimization again.
CONSUMED_AUDIT_WINDOWS = (
    MappingProxyType({
        "start": "2025-07-08",
        "end": "2026-07-07",
        "reason": "repeatedly viewed during pre-Protocol-v2 research",
    }),
)

CANDIDATE_STAGE_BUDGETS = MappingProxyType({
    "generated_candidates": 40,
    "tested_candidates": 12,
    "walk_forward_candidates": 3,
    "finalists": 2,
})

DYNAMIC_WINDOW_POLICY: Mapping[str, object] = MappingProxyType({
    "timezone": "UTC",
    "end_anchor": "latest_complete_utc_day",
    "training_days": 730,
    "holdout_days": 365,
    "minimum_complete_days": 1095,
    "rolling_origin_when_extra_history": True,
    "fixed_calendar_years": False,
})

CONSUMED_AUDIT_POLICY: Mapping[str, object] = MappingProxyType({
    "consumed": True,
    "evaluate_during_research": False,
    "use_for_selection": False,
    "use_for_ranking": False,
    "use_for_parameter_changes": False,
    "allowed_uses": ("historical_reference", "defect_analysis"),
    "windows": CONSUMED_AUDIT_WINDOWS,
})


def build_research_protocol(
    *,
    raw_root: str | Path,
    git_commit: str,
    run_id: str | None = None,
    data_window: dict[str, object] | None = None,
    parameter_space: dict[str, object] | None = None,
    candidate_stage_budgets: dict[str, int] | None = None,
    dynamic_window_policy: dict[str, object] | None = None,
    consumed_audit_policy: dict[str, object] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return {
        "schema_version": 2,
        "run_id": run_id or f"research_{now}",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_commit": git_commit,
        "raw_root": str(Path(raw_root)),
        "data_window": data_window or {},
        "dynamic_window_policy": dict(
            DYNAMIC_WINDOW_POLICY if dynamic_window_policy is None else dynamic_window_policy
        ),
        "candidate_stage_budgets": dict(
            CANDIDATE_STAGE_BUDGETS if candidate_stage_budgets is None else candidate_stage_budgets
        ),
        "selection_data": list(SELECTION_DATA),
        "consumed_audit_policy": _copy_consumed_audit_policy(
            CONSUMED_AUDIT_POLICY if consumed_audit_policy is None else consumed_audit_policy
        ),
        "strategy_families": list(STRATEGY_FAMILIES),
        "parameter_space": parameter_space or {},
        "ranking_rules": list(RANKING_RULES),
        "required_report_paths": list(REQUIRED_REPORT_PATHS),
        "safety": safety_status(),
    }


def validate_research_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if protocol.get("schema_version") != 2:
        errors.append("schema_version must be 2")

    selection_data = protocol.get("selection_data")
    if selection_data != list(SELECTION_DATA):
        errors.append("selection_data must be exactly subtrain, validation, and walk_forward in that order")
    if protocol.get("ranking_rules") != list(RANKING_RULES):
        errors.append("ranking_rules must match the canonical Protocol-v2 ranking order")
    if protocol.get("required_report_paths") != list(REQUIRED_REPORT_PATHS):
        errors.append("required_report_paths must match the canonical Protocol-v2 report schema")
    if protocol.get("strategy_families") != list(STRATEGY_FAMILIES):
        errors.append("strategy_families must match the canonical non-context research families")
    if not isinstance(protocol.get("parameter_space"), dict):
        errors.append("parameter_space must be an object")

    errors.extend(_validate_candidate_stage_budgets(protocol.get("candidate_stage_budgets")))
    errors.extend(_validate_dynamic_window_policy(protocol.get("dynamic_window_policy")))
    errors.extend(_validate_consumed_audit_policy(protocol.get("consumed_audit_policy")))

    safety = protocol.get("safety", {})
    if not isinstance(safety, dict):
        errors.append("safety must be an object")
    else:
        for key, expected in safety_status().items():
            if safety.get(key) != expected:
                errors.append(f"safety.{key} must remain {expected!r}")
    return {"valid": not errors, "errors": errors}


def _copy_consumed_audit_policy(policy: Mapping[str, object]) -> dict[str, object]:
    copied = dict(policy)
    allowed_uses = copied.get("allowed_uses")
    if isinstance(allowed_uses, Sequence) and not isinstance(allowed_uses, (str, bytes)):
        copied["allowed_uses"] = list(allowed_uses)
    windows = copied.get("windows")
    if isinstance(windows, Sequence) and not isinstance(windows, (str, bytes)):
        copied["windows"] = [dict(window) if isinstance(window, Mapping) else window for window in windows]
    return copied


def _validate_candidate_stage_budgets(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["candidate_stage_budgets must be an object"]

    expected_keys = tuple(CANDIDATE_STAGE_BUDGETS)
    errors: list[str] = []
    if set(value) != set(expected_keys):
        errors.append(
            "candidate_stage_budgets must define generated_candidates, tested_candidates, "
            "walk_forward_candidates, and finalists"
        )
        return errors

    for key in expected_keys:
        cap = value[key]
        if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
            errors.append(f"candidate_stage_budgets.{key} must be a positive integer cap")
        elif cap > CANDIDATE_STAGE_BUDGETS[key]:
            errors.append(
                f"candidate_stage_budgets.{key} must not exceed the safety cap {CANDIDATE_STAGE_BUDGETS[key]}"
            )
    if errors:
        return errors

    generated = value["generated_candidates"]
    tested = value["tested_candidates"]
    walk_forward = value["walk_forward_candidates"]
    finalists = value["finalists"]
    if not (finalists <= walk_forward <= tested <= generated):
        errors.append(
            "candidate_stage_budgets caps must satisfy finalists <= walk_forward_candidates "
            "<= tested_candidates <= generated_candidates"
        )
    return errors


def _validate_dynamic_window_policy(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["dynamic_window_policy must be an object"]
    errors: list[str] = []
    for key, expected in DYNAMIC_WINDOW_POLICY.items():
        if value.get(key) != expected:
            errors.append(f"dynamic_window_policy.{key} must be {expected!r}")
    return errors


def _validate_consumed_audit_policy(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["consumed audit policy must be an object"]
    errors: list[str] = []
    if value.get("consumed") is not True:
        errors.append("consumed audit must remain marked consumed")
    for key in ["evaluate_during_research", "use_for_selection", "use_for_ranking", "use_for_parameter_changes"]:
        if value.get(key) is not False:
            errors.append(f"consumed audit {key} must remain False")
    if value.get("allowed_uses") != ["historical_reference", "defect_analysis"]:
        errors.append("consumed audit allowed_uses must remain historical_reference and defect_analysis only")
    if value.get("windows") != [dict(window) for window in CONSUMED_AUDIT_WINDOWS]:
        errors.append("consumed audit window ledger must not be removed or changed")
    return errors


def safety_status() -> dict[str, str | bool]:
    return {
        "live": "locked",
        "paper": "locked",
        "testtrade": "locked",
        "orders": "not_created",
        "binance_trading_api": "not_used",
        "api_keys": "not_used",
        "short_margin_futures_leverage": "forbidden",
        "candidate_adoptable": False,
    }
