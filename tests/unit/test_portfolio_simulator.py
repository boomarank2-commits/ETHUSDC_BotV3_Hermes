"""Fixed-lot multi-position simulator contract tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.portfolio_simulator import simulate_portfolio_strategy
from ethusdc_bot.backtest.simulator import StrategyCandidate, Trade, simulate_strategy
from ethusdc_bot.portfolio import PortfolioPolicy


def _candles(closes: list[float]) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
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


def _base_trade_values(trade: Trade) -> tuple[object, ...]:
    return tuple(getattr(trade, name) for name in Trade.__dataclass_fields__)


def test_100_usdc_policy_is_trade_and_equity_exact_with_single_lot_simulator():
    candles = _candles([100, 101, 102, 100, 99, 101, 102, 103])
    strategy = StrategyCandidate(
        "always_long",
        {
            "max_hold_minutes": 2,
            "take_profit_bps": 10_000,
            "stop_loss_bps": 10_000,
            "cooldown_minutes": 1,
        },
    )

    single = simulate_strategy(candles, strategy, days=1)
    portfolio = simulate_portfolio_strategy(
        candles, strategy, days=1, policy=PortfolioPolicy(100)
    )

    assert portfolio.metrics == single.metrics
    assert portfolio.equity_curve == single.equity_curve
    assert [_base_trade_values(trade) for trade in portfolio.trades] == [
        _base_trade_values(trade) for trade in single.trades
    ]
    assert all(trade.entry_notional_usdc == 100.0 for trade in portfolio.trades)


@pytest.mark.parametrize(
    ("budget", "expected_lots"), [(100, 1), (200, 2), (500, 5), (1000, 10)]
)
def test_manual_budget_limits_fixed_lot_capacity_and_reserved_notional(
    budget: int, expected_lots: int
):
    candles = _candles([100.0] * (expected_lots + 4))
    result = simulate_portfolio_strategy(
        candles,
        StrategyCandidate("always_long", {"max_hold_minutes": 999}),
        days=1,
        policy=PortfolioPolicy(budget),
    )

    assert result.max_concurrent_lots == expected_lots
    assert result.max_open_entry_exposure_usdc == expected_lots * 100.0
    assert result.max_reserved_notional_usdc == budget
    assert result.max_reserved_notional_usdc <= result.policy.deployment_budget_usdc
    assert all(trade.entry_notional_usdc == 100.0 for trade in result.trades)


def test_500_budget_rejects_the_first_signal_beyond_five_reserved_lots():
    candles = _candles([100.0] * 8)
    result = simulate_portfolio_strategy(
        candles,
        StrategyCandidate("always_long", {"max_hold_minutes": 999}),
        days=1,
        policy=PortfolioPolicy(500),
    )

    first = result.capacity_rejections[0]
    assert first.signal_time_ms == candles[5].open_time
    assert first.open_lots == 5
    assert first.pending_entries == 0
    assert first.reserved_notional_usdc == 500.0
    assert result.rejection_reasons["deployment_budget_capacity"] >= 1


def test_losses_never_reduce_the_next_entry_below_fixed_100_usdc():
    result = simulate_portfolio_strategy(
        _candles([100, 99, 98, 97, 96, 95]),
        StrategyCandidate("always_long", {"max_hold_minutes": 1}),
        days=1,
        policy=PortfolioPolicy(100),
    )

    assert len(result.trades) >= 2
    assert result.trades[0].net_profit_usdc < 0
    assert result.trades[1].net_profit_usdc < 0
    for trade in result.trades:
        assert trade.entry_notional_usdc == 100.0
        assert trade.entry_price * trade.quantity == pytest.approx(100.0)


def test_end_of_data_closes_every_open_lot_with_the_shared_cost_model():
    result = simulate_portfolio_strategy(
        _candles([100.0] * 8),
        StrategyCandidate("always_long", {"max_hold_minutes": 999}),
        days=1,
        policy=PortfolioPolicy(500),
    )

    assert len(result.trades) == 5
    assert all(trade.exit_reason == "end_of_data" for trade in result.trades)
    assert result.equity_curve[-1].equity_usdc == result.net_profit_usdc
    assert result.max_reserved_notional_usdc == 500.0


def test_final_candle_fill_is_counted_in_peak_exposure_before_eod_exit():
    result = simulate_portfolio_strategy(
        _candles([100.0, 100.0]),
        StrategyCandidate("always_long", {"max_hold_minutes": 999}),
        days=1,
        policy=PortfolioPolicy(100),
    )

    assert result.trade_count == 1
    assert result.trades[0].exit_reason == "end_of_data"
    assert result.max_concurrent_lots == 1
    assert result.max_open_entry_exposure_usdc == 100.0


@pytest.mark.parametrize("kind", ["off_grid", "duplicate", "gap"])
def test_portfolio_candle_timestamps_fail_closed_on_invalid_1m_raster(kind: str):
    candles = _candles([100.0, 100.0, 100.0])
    if kind == "off_grid":
        candles[0] = replace(candles[0], open_time=candles[0].open_time + 1)
    elif kind == "duplicate":
        candles[1] = replace(candles[1], open_time=candles[0].open_time)
    else:
        candles[1] = replace(candles[1], open_time=candles[1].open_time + 60_000)

    with pytest.raises(ValueError, match="1m"):
        simulate_portfolio_strategy(
            candles,
            StrategyCandidate("always_long", {"max_hold_minutes": 1}),
            days=1,
            policy=PortfolioPolicy(),
        )


def test_short_is_forbidden_and_non_eth_trade_context_is_rejected():
    with pytest.raises(ValueError, match="LONG-only"):
        simulate_portfolio_strategy(
            _candles([100, 101]),
            StrategyCandidate("always_long", {"side": "SHORT"}),
            days=1,
            policy=PortfolioPolicy(),
        )

    result = simulate_portfolio_strategy(
        _candles([100, 101]),
        StrategyCandidate("always_long", {"symbol": "BTCUSDC"}),
        days=1,
        policy=PortfolioPolicy(),
    )
    assert result.trade_count == 0
    assert result.rejection_reasons == {"context_symbol_not_tradeable": 1}
