"""Research protocol guardrails for reproducible offline strategy search."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STRATEGY_FAMILIES = [
    "momentum_trend_filter",
    "breakout_volatility_filter",
    "mean_reversion_regime_filter",
    "pullback_in_trend",
    "session_filter",
    "cooldown_fee_aware",
]


def build_research_protocol(
    *,
    raw_root: str | Path,
    git_commit: str,
    run_id: str | None = None,
    data_window: dict[str, object] | None = None,
    parameter_space: dict[str, object] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return {
        "schema_version": 1,
        "run_id": run_id or f"research_{now}",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_commit": git_commit,
        "raw_root": str(Path(raw_root)),
        "data_window": data_window or {},
        "selection_data": ["subtrain", "validation"],
        "blindtest_usage": "final_evaluation_only",
        "strategy_families": list(STRATEGY_FAMILIES),
        "parameter_space": parameter_space or {},
        "ranking_rules": [
            "validation_net_usdc_per_day_desc",
            "validation_profit_factor_desc",
            "validation_max_drawdown_asc",
            "trade_count_sufficient_not_overtrading",
            "fees_slippage_load_penalty",
            "training_validation_stability",
        ],
        "required_outputs": [
            "run_id",
            "git_commit",
            "raw_root",
            "windows",
            "parameters",
            "training_results",
            "validation_results",
            "blindtest_result_after_selection",
            "safety_status",
        ],
        "safety": safety_status(),
    }


def validate_research_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if "blindtest" in protocol.get("selection_data", []):
        errors.append("blindtest must not be used for selection")
    if protocol.get("blindtest_usage") != "final_evaluation_only":
        errors.append("blindtest must be final_evaluation_only")
    if protocol.get("safety", {}).get("orders") != "not_created":
        errors.append("orders must remain not_created")
    return {"valid": not errors, "errors": errors}


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
