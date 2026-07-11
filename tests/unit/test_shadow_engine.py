"""Order-free closed-candle Shadow reducer tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.portfolio_simulator import simulate_portfolio_strategy
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.portfolio import PortfolioPolicy, canonical_portfolio_signature
from ethusdc_bot.shadow.engine import (
    ShadowReplayError,
    replay_closed_candles,
    start_shadow_replay,
    stop_shadow_replay,
)
from ethusdc_bot.shadow.schema import (
    canonical_signature_payload,
    shadow_safety_status,
)


def _candles(closes: list[float], *, start_minute: int = 0) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=start_minute)
    return [
        Candle(
            open_time=int((start + timedelta(minutes=index)).timestamp() * 1000),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1.0,
        )
        for index, close in enumerate(closes)
    ]


def _deployment(
    params: dict[str, float | int | str], *, family: str = "momentum", budget: int = 500
) -> dict[str, object]:
    normalized = {"symbol": "ETHUSDC", "side": "LONG", **params}
    policy = PortfolioPolicy(budget)
    return {
        "schema_version": 1,
        "deployment_id": "shadow_final_001_replay",
        "created_at_utc": "2026-01-01T00:00:00Z",
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
            "family": family,
            "params": normalized,
            "candidate_signature": canonical_signature_payload(family, normalized),
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
            "deployment_budget_usdc": budget,
            "deployment_target_usdc_per_day": (
                policy.target_guidance.desired_net_usdc_per_day
            ),
            "deployment_target_status": (
                "verified" if budget == 100 else "unverified_scaling"
            ),
            "deployment_target_reached": budget == 100,
            "live_eligible": False,
            "reason_codes": (
                ["all_quality_gates_passed"]
                if budget == 100
                else [
                    "all_quality_gates_passed",
                    "deployment_budget_scaling_unverified",
                ]
            ),
        },
        "safety": shadow_safety_status(),
    }


def _state(*, budget: int = 500) -> dict[str, object]:
    policy = PortfolioPolicy(budget)
    return {
        "schema_version": 1,
        "deployment_id": "shadow_final_001_replay",
        "phase": "adopted_stopped",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "updated_at_utc": "2026-01-01T00:00:00Z",
        "deployment_budget_usdc": budget,
        "lot_notional_usdc": 100.0,
        "max_open_lots": policy.max_concurrent_lots,
        "last_processed_candle_open_time_ms": None,
        "open_lots": [],
        "realized_net_usdc": 0.0,
        "unrealized_net_usdc": 0.0,
        "event_count": 1,
        "last_event_hash": "b" * 64,
        "error": None,
        "safety": shadow_safety_status(),
    }


def test_shadow_replay_has_exact_backtest_entry_exit_cost_and_pnl_parity():
    params = {
        "lookback": 1,
        "threshold_bps": 1,
        "max_hold_minutes": 1,
        "take_profit_bps": 10_000,
        "stop_loss_bps": 10_000,
    }
    deployment = _deployment(params)
    candles = _candles([100, 110, 90, 90, 90])
    backtest = simulate_portfolio_strategy(
        candles,
        StrategyCandidate("momentum", dict(deployment["candidate"]["params"])),  # type: ignore[index]
        days=1,
        policy=PortfolioPolicy(500),
    )
    running = start_shadow_replay(deployment, _state())

    replay = replay_closed_candles(deployment, running, candles)

    assert replay.state.trades == tuple(backtest.trades)
    assert len(replay.state.trades) == 1
    assert replay.state.open_lots == ()
    assert all(event.hypothetical for event in replay.events)
    assert all(not event.orders_enabled for event in replay.events)
    assert all(not event.trading_api_enabled for event in replay.events)


def test_exact_previously_processed_candles_are_idempotently_ignored():
    deployment = _deployment({"max_hold_minutes": 99}, family="always_long")
    candles = _candles([100, 101, 102])
    first = replay_closed_candles(
        deployment, start_shadow_replay(deployment, _state()), candles
    )

    repeated = replay_closed_candles(deployment, first.state, [*candles, candles[-1]])

    assert repeated.state == first.state
    assert repeated.events == ()
    assert repeated.processed_candles == 0
    assert repeated.ignored_idempotent_candles == len(candles) + 1


def test_duplicate_in_one_batch_and_one_minute_gap_pause_fail_closed():
    deployment = _deployment({"max_hold_minutes": 99}, family="always_long")
    first = _candles([100])[0]
    running = start_shadow_replay(deployment, _state())

    duplicate = replay_closed_candles(deployment, running, [first, first])
    assert duplicate.state.phase == "paused"
    assert duplicate.state.paused_reason == "duplicate_candle_in_batch"
    assert duplicate.events[-1].event_type == "replay_paused"

    two = replay_closed_candles(
        deployment, start_shadow_replay(deployment, _state()), _candles([100, 101])
    )
    gap_candle = _candles([103], start_minute=3)[0]
    gap = replay_closed_candles(deployment, two.state, [gap_candle])
    assert gap.state.phase == "paused"
    assert gap.state.paused_reason == "one_minute_gap"
    assert gap.processed_candles == 0


def test_off_grid_shadow_timestamp_pauses_before_processing():
    deployment = _deployment({"max_hold_minutes": 99}, family="always_long")
    candle = _candles([100])[0]
    off_grid = replace(candle, open_time=candle.open_time + 1)

    result = replay_closed_candles(
        deployment, start_shadow_replay(deployment, _state()), [off_grid]
    )

    assert result.state.phase == "paused"
    assert result.state.paused_reason == "invalid_candle:open_time_grid"
    assert result.processed_candles == 0


@pytest.mark.parametrize(
    ("start_minute", "reason"),
    [(-1, "pre_adoption_candle"), (1, "initial_candle_gap")],
)
def test_first_shadow_candle_must_match_forward_adoption_cursor(
    start_minute, reason
):
    deployment = _deployment({"max_hold_minutes": 99}, family="always_long")

    result = replay_closed_candles(
        deployment,
        start_shadow_replay(deployment, _state()),
        _candles([100], start_minute=start_minute),
    )

    assert result.state.phase == "paused"
    assert result.state.paused_reason == reason
    assert result.processed_candles == 0
    assert result.events[-1].event_type == "replay_paused"


def test_stop_never_artificially_closes_an_open_hypothetical_lot():
    deployment = _deployment({"max_hold_minutes": 99}, family="always_long")
    replay = replay_closed_candles(
        deployment,
        start_shadow_replay(deployment, _state()),
        _candles([100, 100]),
    )
    assert len(replay.state.open_lots) == 1
    assert replay.state.trades == ()

    stopped = stop_shadow_replay(replay.state)
    ignored = replay_closed_candles(deployment, stopped, _candles([100], start_minute=2))

    assert stopped.phase == "stopped"
    assert stopped.open_lots == replay.state.open_lots
    assert stopped.trades == replay.state.trades
    assert ignored.processed_candles == 0
    assert ignored.events == ()
    assert ignored.state.open_lots == replay.state.open_lots


def test_unsafe_deployment_or_partially_processed_persisted_state_is_rejected():
    deployment = _deployment({"max_hold_minutes": 99}, family="always_long")
    unsafe = deepcopy(deployment)
    unsafe["safety"]["orders_enabled"] = True  # type: ignore[index]
    with pytest.raises(ShadowReplayError):
        start_shadow_replay(unsafe, _state())

    partial = _state()
    partial["last_processed_candle_open_time_ms"] = 1_000
    with pytest.raises(ShadowReplayError, match="partially processed"):
        start_shadow_replay(deployment, partial)
