"""Bounded Shadow retention remains exactly reducer-equivalent to full replay."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import random

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.portfolio_simulator import (
    BOUNDED_SHADOW_RETENTION_PROFILE,
    FULL_RETENTION_PROFILE,
    MAX_BOUNDED_HISTORY_CANDLES,
)
from ethusdc_bot.portfolio import PortfolioPolicy, canonical_portfolio_signature
from ethusdc_bot.shadow.engine import (
    ShadowReplayState,
    bounded_shadow_retention_profile,
    replay_closed_candles,
    select_bounded_shadow_retention,
    start_shadow_replay,
)
from ethusdc_bot.shadow.schema import (
    canonical_signature_payload,
    shadow_safety_status,
)


def _deployment(
    params: dict[str, float | int | str],
    *,
    family: str,
    budget: int,
) -> dict[str, object]:
    normalized = {"symbol": "ETHUSDC", "side": "LONG", **params}
    policy = PortfolioPolicy(budget)
    return {
        "schema_version": 1,
        "deployment_id": "shadow_bounded_retention_001",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "mode": "public_data_shadow",
        "status": "adopted",
        "source_report": {
            "path": "C:/external/final_001.json",
            "sha256": "a" * 64,
            "final_evaluation_id": "final_001",
            "source_research_run_id": "research_loop_001",
            "git_commit": "bafbc18",
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
            "shadow_eligible": True,
            "target_reached": True,
            "live_eligible": False,
            "reason_codes": ["all_quality_gates_passed"],
        },
        "safety": shadow_safety_status(),
    }


def _state(*, budget: int) -> dict[str, object]:
    policy = PortfolioPolicy(budget)
    return {
        "schema_version": 1,
        "deployment_id": "shadow_bounded_retention_001",
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


def _seeded_candles(count: int, *, seed: int = 8712) -> list[Candle]:
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    previous = 100.0
    candles: list[Candle] = []
    for index in range(count):
        opening = previous
        closing = max(1.0, opening * (1.0 + rng.uniform(-0.0035, 0.0035)))
        high = max(opening, closing) * (1.0 + rng.uniform(0.0001, 0.0010))
        low = min(opening, closing) * (1.0 - rng.uniform(0.0001, 0.0010))
        candles.append(
            Candle(
                open_time=int(
                    (start + timedelta(minutes=index)).timestamp() * 1000
                ),
                open=opening,
                high=high,
                low=low,
                close=closing,
                volume=1.0 + rng.random(),
            )
        )
        previous = closing
    return candles


def _pattern_candles(count: int) -> list[Candle]:
    pattern = (100.0, 100.0, 102.0, 101.0, 100.0, 100.0)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(
            open_time=int((start + timedelta(minutes=index)).timestamp() * 1000),
            open=pattern[index % len(pattern)],
            high=pattern[index % len(pattern)] + 0.5,
            low=pattern[index % len(pattern)] - 0.5,
            close=pattern[index % len(pattern)],
            volume=1.0,
        )
        for index in range(count)
    ]


def _started_pair(
    deployment: dict[str, object], *, budget: int
) -> tuple[ShadowReplayState, ShadowReplayState]:
    full = start_shadow_replay(deployment, _state(budget=budget))
    return full, select_bounded_shadow_retention(full)


def _assert_forward_state_parity(
    full: ShadowReplayState, bounded: ShadowReplayState
) -> None:
    left = full.engine_state
    right = bounded.engine_state
    assert right.open_lots == left.open_lots
    assert right.pending_entry == left.pending_entry
    assert right.cooldown_until_index == left.cooldown_until_index
    assert right.realized_net_usdc == left.realized_net_usdc
    assert right.next_lot_sequence == left.next_lot_sequence
    assert right.max_concurrent_lots == left.max_concurrent_lots
    assert right.max_open_entry_exposure_usdc == left.max_open_entry_exposure_usdc
    assert right.max_reserved_notional_usdc == left.max_reserved_notional_usdc
    assert right.total_processed_candles == left.total_processed_candles
    assert right.equity_curve[-1] == left.equity_curve[-1]
    assert bounded.next_event_sequence == full.next_event_sequence


def test_full_retention_remains_the_legacy_default_and_is_not_compacted():
    deployment = _deployment(
        {"max_hold_minutes": 3}, family="always_long", budget=100
    )
    full = start_shadow_replay(deployment, _state(budget=100))
    assert full.engine_state.retention_profile == FULL_RETENTION_PROFILE
    assert full.engine_state.retained_history_limit is None

    result = replay_closed_candles(deployment, full, _seeded_candles(80))

    assert len(result.state.engine_state.candles) == 80
    assert len(result.state.engine_state.equity_curve) == 81
    assert result.state.engine_state.trades
    assert result.state.engine_state.total_processed_candles == 80


def test_profile_is_deterministic_and_hard_fails_above_10081_candles():
    allowed = _deployment(
        {
            "lookback": 20,
            "trend_lookback": 30,
            "volatility_lookback": 40,
            "max_hold_minutes": 10_080,
        },
        family="momentum",
        budget=100,
    )
    full = start_shadow_replay(allowed, _state(budget=100))

    profile = bounded_shadow_retention_profile(full)

    assert profile == {
        "profile": BOUNDED_SHADOW_RETENTION_PROFILE,
        "retained_history_candles": MAX_BOUNDED_HISTORY_CANDLES,
        "max_equity_points": 1,
        "retain_cumulative_trades": False,
        "retain_cumulative_capacity_rejections": False,
    }
    assert (
        select_bounded_shadow_retention(full).engine_state.retained_history_limit
        == MAX_BOUNDED_HISTORY_CANDLES
    )

    excessive = _deployment(
        {"max_hold_minutes": 10_081}, family="always_long", budget=100
    )
    excessive_state = start_shadow_replay(excessive, _state(budget=100))
    with pytest.raises(ValueError, match="10081-candle"):
        select_bounded_shadow_retention(excessive_state)


@pytest.mark.parametrize("budget", [100, 500, 1000])
def test_seeded_momentum_full_and_bounded_reducers_have_exact_event_trade_and_state_parity(
    budget: int,
):
    params = {
        "lookback": 7,
        "trend_lookback": 11,
        "volatility_lookback": 17,
        "threshold_bps": 3,
        "trend_min_bps": -10,
        "max_hold_minutes": 13,
        "take_profit_bps": 25,
        "stop_loss_bps": 20,
        "break_even_after_bps": 10,
        "trailing_stop_bps": 12,
        "cooldown_minutes": 2,
    }
    deployment = _deployment(
        params, family="momentum_trend_filter", budget=budget
    )
    candles = _seeded_candles(720)
    full, bounded = _started_pair(deployment, budget=budget)

    full_result = replay_closed_candles(deployment, full, candles)
    bounded_result = replay_closed_candles(deployment, bounded, candles)

    assert bounded_result.events == full_result.events
    assert bounded_result.trades_emitted == full_result.trades_emitted
    assert tuple(full_result.state.trades) == full_result.trades_emitted
    _assert_forward_state_parity(full_result.state, bounded_result.state)
    engine = bounded_result.state.engine_state
    assert len(engine.candles) <= 18
    assert len(engine.equity_curve) <= 1
    assert engine.trades == ()
    assert engine.capacity_rejections == ()


def test_always_long_trailing_exit_best_close_and_cooldown_match_full_replay():
    params = {
        "max_hold_minutes": 20,
        "take_profit_bps": 10_000,
        "stop_loss_bps": 10_000,
        "trailing_stop_bps": 50,
        "cooldown_minutes": 3,
    }
    deployment = _deployment(params, family="always_long", budget=200)
    full, bounded = _started_pair(deployment, budget=200)
    candles = _pattern_candles(180)

    full_result = replay_closed_candles(deployment, full, candles)
    bounded_result = replay_closed_candles(deployment, bounded, candles)

    assert bounded_result.events == full_result.events
    assert bounded_result.trades_emitted == full_result.trades_emitted
    assert any(
        trade.exit_reason == "trailing_stop"
        for trade in bounded_result.trades_emitted
    )
    _assert_forward_state_parity(full_result.state, bounded_result.state)


def test_compacting_a_populated_legacy_state_matches_bounded_from_genesis():
    params = {
        "lookback": 5,
        "threshold_bps": 2,
        "max_hold_minutes": 19,
        "take_profit_bps": 35,
        "stop_loss_bps": 30,
        "trailing_stop_bps": 15,
        "cooldown_minutes": 4,
    }
    deployment = _deployment(params, family="momentum", budget=500)
    candles = _seeded_candles(420, seed=912)
    full, bounded = _started_pair(deployment, budget=500)

    legacy_prefix = replay_closed_candles(deployment, full, candles[:300])
    bounded_prefix = replay_closed_candles(deployment, bounded, candles[:300])
    compacted = select_bounded_shadow_retention(legacy_prefix.state)

    assert compacted.engine_state == bounded_prefix.state.engine_state
    compacted_suffix = replay_closed_candles(deployment, compacted, candles[300:])
    bounded_suffix = replay_closed_candles(
        deployment, bounded_prefix.state, candles[300:]
    )
    assert compacted_suffix.events == bounded_suffix.events
    assert compacted_suffix.trades_emitted == bounded_suffix.trades_emitted
    assert compacted_suffix.state == bounded_suffix.state


def test_idempotency_is_limited_to_retained_window_and_older_replay_pauses():
    deployment = _deployment(
        {"lookback": 2, "max_hold_minutes": 3},
        family="momentum",
        budget=100,
    )
    _, bounded = _started_pair(deployment, budget=100)
    candles = _seeded_candles(20)
    replay = replay_closed_candles(deployment, bounded, candles)
    retained = replay.state.engine_state.candles

    repeated = replay_closed_candles(deployment, replay.state, retained)
    assert repeated.state == replay.state
    assert repeated.ignored_idempotent_candles == len(retained)
    assert repeated.events == ()

    evicted = replay_closed_candles(deployment, replay.state, [candles[0]])
    assert evicted.state.phase == "paused"
    assert evicted.state.paused_reason == "replay_outside_retained_history"
    assert evicted.processed_candles == 0
    assert evicted.events[-1].event_type == "replay_paused"


def test_bounded_shadow_state_stays_structurally_bounded_beyond_10000_candles():
    deployment = _deployment(
        {"max_hold_minutes": 5, "cooldown_minutes": 1},
        family="always_long",
        budget=1000,
    )
    full = start_shadow_replay(deployment, _state(budget=1000))
    profile = bounded_shadow_retention_profile(full)
    current = select_bounded_shadow_retention(full)
    candles = _seeded_candles(10_050, seed=710)
    emitted_count = 0

    for offset in range(0, len(candles), 250):
        result = replay_closed_candles(
            deployment, current, candles[offset : offset + 250]
        )
        current = result.state
        emitted_count += len(result.trades_emitted)
        engine = current.engine_state
        assert len(engine.candles) <= profile["retained_history_candles"]
        assert len(engine.equity_curve) <= 1
        assert engine.trades == ()
        assert engine.capacity_rejections == ()

    assert current.engine_state.total_processed_candles == 10_050
    assert len(current.engine_state.candles) == 6
    assert emitted_count > 1_000
    assert current.engine_state.next_lot_sequence > 1_000
    assert current.engine_state.max_reserved_notional_usdc <= 1000.0
