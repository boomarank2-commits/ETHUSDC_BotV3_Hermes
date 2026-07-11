"""Tests for selection-only context research adapters."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ethusdc_bot.backtest.context_features import ContextVetoPolicy
from ethusdc_bot.backtest.context_research import (
    CONTEXT_BASE_FAMILY_KEY,
    context_for_candidate,
    context_policy_for_profile,
    context_research_provenance,
    slice_aligned_context,
    wrap_candidate_with_context,
)
from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle, DataLoadError
from ethusdc_bot.backtest.simulator import StrategyCandidate


def _candles(count: int, *, start_minute: int = 0, price: float = 100.0) -> tuple[Candle, ...]:
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        Candle(
            open_time=int((origin + timedelta(minutes=start_minute + index)).timestamp() * 1000),
            open=price + index * 0.01,
            high=price + index * 0.01 + 0.1,
            low=price + index * 0.01 - 0.1,
            close=price + index * 0.01,
            volume=1.0,
        )
        for index in range(count)
    )


def _aligned(count: int = 20) -> AlignedMarketCandles:
    return AlignedMarketCandles(
        ethusdc=_candles(count, price=100.0),
        btcusdc=_candles(count, price=200.0),
        ethbtc=_candles(count, price=1.0),
    )


def test_slice_aligned_context_returns_exact_middle_window() -> None:
    context = _aligned()
    trade_window = list(context.ethusdc[5:12])

    sliced = slice_aligned_context(context, trade_window)

    assert sliced.ethusdc == context.ethusdc[5:12]
    assert sliced.btcusdc == context.btcusdc[5:12]
    assert sliced.ethbtc == context.ethbtc[5:12]
    assert sliced.candle_count == 7


def test_slice_aligned_context_rejects_gap_or_outside_window() -> None:
    context = _aligned()
    with pytest.raises(DataLoadError, match="contiguous"):
        slice_aligned_context(context, [context.ethusdc[2], context.ethusdc[4]])

    before = list(_candles(2, start_minute=-2))
    with pytest.raises(DataLoadError, match="timeline"):
        slice_aligned_context(context, before)


def test_slice_aligned_context_rechecks_all_three_timelines() -> None:
    context = _aligned()
    shifted = list(context.btcusdc)
    candle = shifted[7]
    shifted[7] = Candle(
        open_time=candle.open_time + 60_000,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )
    bad = AlignedMarketCandles(context.ethusdc, tuple(shifted), context.ethbtc)

    with pytest.raises(DataLoadError, match="BTCUSDC"):
        slice_aligned_context(bad, context.ethusdc[5:10])


def test_context_for_candidate_slices_only_context_filter() -> None:
    context = _aligned()
    base = StrategyCandidate("momentum", {"symbol": "ETHUSDC", "lookback": 2})
    wrapped = wrap_candidate_with_context(base, ContextVetoPolicy())

    assert context_for_candidate(context, context.ethusdc[3:9], base) is None
    sliced = context_for_candidate(context, context.ethusdc[3:9], wrapped)
    assert sliced is not None
    assert sliced.open_times == tuple(candle.open_time for candle in context.ethusdc[3:9])

    with pytest.raises(DataLoadError, match="requires aligned"):
        context_for_candidate(None, context.ethusdc[3:9], wrapped)


def test_context_wrapper_preserves_nested_base_family_without_collision() -> None:
    base = StrategyCandidate(
        "cooldown_fee_aware",
        {
            "symbol": "ETHUSDC",
            "base_family": "breakout",
            "lookback": 60,
            "threshold_bps": 20,
        },
    )
    policy = context_policy_for_profile(2)

    wrapped = wrap_candidate_with_context(base, policy)

    assert wrapped.family == "context_filter"
    assert wrapped.params[CONTEXT_BASE_FAMILY_KEY] == "cooldown_fee_aware"
    assert wrapped.params["base_family"] == "breakout"
    assert wrapped.params["context_btc_trend_lookback"] == 240
    assert wrapped.params["context_btc_min_trend_bps"] == -25.0
    assert wrapped.params["context_ethbtc_min_trend_bps"] == -15.0


def test_context_wrapper_rejects_recursive_or_non_ethusdc_base() -> None:
    with pytest.raises(ValueError, match="cannot wrap itself"):
        wrap_candidate_with_context(
            StrategyCandidate("context_filter", {"symbol": "ETHUSDC"}),
            ContextVetoPolicy(),
        )
    with pytest.raises(ValueError, match="only ETHUSDC"):
        wrap_candidate_with_context(
            StrategyCandidate("momentum", {"symbol": "BTCUSDC"}),
            ContextVetoPolicy(),
        )


def test_context_policy_profiles_are_bounded_deterministic_and_distinct() -> None:
    first = context_policy_for_profile(0)
    last = context_policy_for_profile(6)

    assert first == context_policy_for_profile(0)
    assert first.btc_min_trend_bps == -50.0
    assert last.btc_min_trend_bps == 20.0
    assert first.btc_max_volatility_bps > last.btc_max_volatility_bps
    assert first != last
    with pytest.raises(ValueError, match="0 through 6"):
        context_policy_for_profile(7)


def test_context_provenance_never_claims_target_or_direct_trigger() -> None:
    context = _aligned()
    base = StrategyCandidate("momentum", {"symbol": "ETHUSDC"})
    wrapped = wrap_candidate_with_context(base, context_policy_for_profile(1))

    proof = context_research_provenance(context, [base, wrapped])

    assert proof["enabled"] is True
    assert proof["symbols"] == {
        "trade": "ETHUSDC",
        "context_only": ["BTCUSDC", "ETHBTC"],
    }
    assert proof["context_candidate_count"] == 1
    assert proof["context_direct_trigger_allowed"] is False
    assert proof["context_may_only_confirm_or_veto_base_signal"] is True
    assert proof["uses_audit_or_holdout"] is False
    assert proof["target_used_as_parameter"] is False
