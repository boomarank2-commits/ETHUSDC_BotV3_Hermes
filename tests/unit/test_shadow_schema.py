"""Strict safety-contract tests for Shadow deployment and state schemas."""

from __future__ import annotations

from copy import deepcopy

import pytest

from ethusdc_bot.portfolio import PortfolioPolicy, canonical_portfolio_signature
from ethusdc_bot.shadow.schema import (
    ShadowSchemaError,
    canonical_signature_payload,
    shadow_safety_status,
    validate_shadow_deployment,
    validate_shadow_state,
)


def _deployment() -> dict[str, object]:
    params = {"symbol": "ETHUSDC", "lookback": 60, "side": "LONG"}
    policy = PortfolioPolicy(deployment_budget_usdc=500)
    return {
        "schema_version": 1,
        "deployment_id": "shadow_final_001_abcd1234",
        "created_at_utc": "2026-07-11T08:00:00Z",
        "mode": "public_data_shadow",
        "status": "adopted",
        "source_report": {
            "path": "C:/external/final_001.json",
            "sha256": "a" * 64,
            "final_evaluation_id": "final_001",
            "source_research_run_id": "research_loop_001",
            "git_commit": "c2b65c8",
        },
        "candidate": {
            "candidate_id": "candidate_001",
            "family": "momentum",
            "params": params,
            "candidate_signature": canonical_signature_payload("momentum", params),
        },
        "portfolio_policy": {
            "policy": policy.to_dict(),
            "canonical_signature": canonical_portfolio_signature(policy),
        },
        "cost_model": {
            "fee_rate_per_side": 0.001,
            "fee_bps_per_side": 10.0,
            "slippage_bps_per_side": 5.0,
        },
        "assessment": {
            "color": "green",
            "color_scope": "canonical_100_usdc_final_evaluation",
            "shadow_eligible": True,
            "target_reached": True,
            "target_evidence_budget_usdc": 100,
            "deployment_budget_usdc": 500,
            "deployment_target_usdc_per_day": 15.0,
            "deployment_target_status": "unverified_scaling",
            "deployment_target_reached": False,
            "live_eligible": False,
            "reason_codes": [
                "all_quality_gates_passed",
                "deployment_budget_scaling_unverified",
            ],
        },
        "safety": shadow_safety_status(),
    }


def _state() -> dict[str, object]:
    return {
        "schema_version": 1,
        "deployment_id": "shadow_final_001_abcd1234",
        "phase": "adopted_stopped",
        "created_at_utc": "2026-07-11T08:00:00Z",
        "updated_at_utc": "2026-07-11T08:00:00Z",
        "deployment_budget_usdc": 500,
        "lot_notional_usdc": 100.0,
        "max_open_lots": 5,
        "last_processed_candle_open_time_ms": None,
        "open_lots": [],
        "realized_net_usdc": 0.0,
        "unrealized_net_usdc": 0.0,
        "event_count": 1,
        "last_event_hash": "b" * 64,
        "error": None,
        "safety": shadow_safety_status(),
    }


def test_valid_shadow_deployment_and_state_pass_strict_validation():
    validate_shadow_deployment(_deployment())
    validate_shadow_state(_state())


@pytest.mark.parametrize(
    ("path", "bad_value"),
    [
        (("cost_model", "fee_bps_per_side"), 9.0),
        (("cost_model", "slippage_bps_per_side"), 0.0),
        (("safety", "orders_enabled"), True),
        (("safety", "trading_api_enabled"), True),
        (("safety", "api_keys_used"), True),
        (("assessment", "live_eligible"), True),
    ],
)
def test_deployment_rejects_unsafe_or_noncanonical_values(path, bad_value):
    deployment = deepcopy(_deployment())
    deployment[path[0]][path[1]] = bad_value  # type: ignore[index]

    with pytest.raises(ShadowSchemaError):
        validate_shadow_deployment(deployment)


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("lot_notional_usdc", 99.0),
        ("deployment_budget_usdc", 300),
        ("max_concurrent_lots", 6),
        ("compounding_enabled", True),
    ],
)
def test_deployment_rejects_noncanonical_portfolio_policy(key, bad_value):
    deployment = _deployment()
    deployment["portfolio_policy"]["policy"][key] = bad_value  # type: ignore[index]

    with pytest.raises(ShadowSchemaError):
        validate_shadow_deployment(deployment)


def test_deployment_rejects_unknown_fields_and_forged_signature():
    unknown = _deployment()
    unknown["live_enabled"] = True
    with pytest.raises(ShadowSchemaError, match="unknown keys"):
        validate_shadow_deployment(unknown)

    forged = _deployment()
    forged["candidate"]["candidate_signature"]["params"][0][1] = "BTCUSDC"  # type: ignore[index]
    with pytest.raises(ShadowSchemaError, match="not canonical"):
        validate_shadow_deployment(forged)


def test_state_rejects_more_open_lots_than_budget_and_non_100_lot():
    state = _state()
    lot = {
        "lot_id": "lot_1",
        "signal_time_ms": 1,
        "entry_time_ms": 2,
        "entry_mid_price": 2000.0,
        "entry_price": 2001.0,
        "quantity": 0.049975,
        "notional_usdc": 100.0,
        "best_close": 2001.0,
    }
    state["open_lots"] = [{**lot, "lot_id": f"lot_{index}"} for index in range(6)]
    with pytest.raises(ShadowSchemaError, match="exceeds"):
        validate_shadow_state(state)

    state = _state()
    state["open_lots"] = [{**lot, "notional_usdc": 99.0}]
    with pytest.raises(ShadowSchemaError, match="must be 100"):
        validate_shadow_state(state)


def test_state_can_never_enable_order_or_live_capability():
    for key, value in [
        ("orders_enabled", True),
        ("trading_api_enabled", True),
        ("api_keys_used", True),
        ("live", "unlocked"),
    ]:
        state = _state()
        state["safety"][key] = value  # type: ignore[index]
        with pytest.raises(ShadowSchemaError):
            validate_shadow_state(state)
