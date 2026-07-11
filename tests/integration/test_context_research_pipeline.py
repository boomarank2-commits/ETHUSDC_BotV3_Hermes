"""Integration tests for aligned context throughout selection research stages."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ethusdc_bot.backtest.context_features import ContextVetoPolicy
from ethusdc_bot.backtest.context_research import wrap_candidate_with_context
from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
from ethusdc_bot.backtest.search_space import (
    SearchSpaceState,
    generate_search_space,
    search_frontier_summary,
    select_candidates_for_testing,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy
from ethusdc_bot.backtest.walk_forward import evaluate_walk_forward


def _candles(
    *,
    days: int,
    candles_per_day: int,
    start_price: float,
    minute_step: int = 1,
) -> tuple[Candle, ...]:
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    result: list[Candle] = []
    for day in range(days):
        for minute in range(candles_per_day):
            index = day * candles_per_day + minute
            timestamp = origin + timedelta(days=day, minutes=minute * minute_step)
            close = start_price + index * 0.05
            result.append(
                Candle(
                    open_time=int(timestamp.timestamp() * 1000),
                    open=close,
                    high=close + 0.1,
                    low=close - 0.1,
                    close=close,
                    volume=1.0,
                )
            )
    return tuple(result)


def _aligned(*, days: int = 8, candles_per_day: int = 12) -> AlignedMarketCandles:
    eth = _candles(days=days, candles_per_day=candles_per_day, start_price=100.0)
    btc = _candles(days=days, candles_per_day=candles_per_day, start_price=200.0)
    ratio = _candles(days=days, candles_per_day=candles_per_day, start_price=1.0)
    return AlignedMarketCandles(ethusdc=eth, btcusdc=btc, ethbtc=ratio)


def _permissive_policy() -> ContextVetoPolicy:
    return ContextVetoPolicy(
        btc_trend_lookback=2,
        btc_min_trend_bps=-10_000,
        btc_volatility_lookback=2,
        btc_max_volatility_bps=10_000,
        ethbtc_trend_lookback=2,
        ethbtc_min_trend_bps=-10_000,
    )


def test_context_enabled_frontier_stays_bounded_and_family_balanced() -> None:
    state = SearchSpaceState(cycle_index=0)
    candidates = generate_search_space(
        state,
        max_candidates=40,
        context_enabled=True,
    )
    tested = select_candidates_for_testing(candidates, 12)
    summary = search_frontier_summary(
        candidates,
        state,
        requested_cap=40,
        context_enabled=True,
    )

    assert len(candidates) == 40
    assert len(tested) == 12
    assert sum(candidate.family == "context_filter" for candidate in candidates) == 6
    assert sum(candidate.family == "context_filter" for candidate in tested) == 2
    assert summary["context_candidates_enabled"] is True
    assert summary["context_disabled_reason"] is None
    assert summary["family_counts"]["context_filter"] == 6
    assert summary["uses_audit_or_holdout"] is False
    assert summary["target_used_as_parameter"] is False
    assert all(
        "target_usdc_per_day" not in candidate.params
        and all("blindtest" not in key for key in candidate.params)
        for candidate in candidates
    )


def test_context_wrapper_preserves_nested_base_family_in_real_simulation() -> None:
    context = _aligned(days=1, candles_per_day=24)
    base = StrategyCandidate(
        "cooldown_fee_aware",
        {
            "symbol": "ETHUSDC",
            "base_family": "momentum",
            "lookback": 2,
            "threshold_bps": 0,
            "min_expected_move_bps": 0,
            "max_hold_minutes": 2,
            "take_profit_bps": 10_000,
            "stop_loss_bps": 10_000,
        },
    )
    candidate = wrap_candidate_with_context(base, _permissive_policy())

    result = simulate_strategy(
        list(context.ethusdc),
        candidate,
        days=1,
        market_context=context,
    )

    assert result.trade_count > 0
    assert result.rejection_reasons.get("context_data_missing", 0) == 0
    assert all(trade.symbol == "ETHUSDC" and trade.side == "LONG" for trade in result.trades)


def test_walk_forward_context_uses_exact_fold_slices() -> None:
    context = _aligned(days=8, candles_per_day=12)
    candidate = wrap_candidate_with_context(
        StrategyCandidate(
            "always_long",
            {
                "symbol": "ETHUSDC",
                "max_hold_minutes": 2,
                "take_profit_bps": 10_000,
                "stop_loss_bps": 10_000,
            },
        ),
        _permissive_policy(),
    )

    summary = evaluate_walk_forward(
        list(context.ethusdc),
        candidate,
        fold_count=2,
        training_days=8,
        blindtest_days=0,
        market_context=context,
    )

    assert summary["fold_count"] == 2
    assert summary["trade_count"] > 0
    assert summary["ranking_uses_blindtest"] is False
    assert all(row["metrics"]["trade_count"] > 0 for row in summary["folds"])
