"""Tests for conservative LONG-only backtest simulation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy


def _candles(closes: list[float]) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Candle(open_time=int((start + timedelta(minutes=i)).timestamp() * 1000), open=close, high=close + 1, low=close - 1, close=close, volume=1)
        for i, close in enumerate(closes)
    ]


def test_long_only_trades_are_created_for_ethusdc_signals():
    strategy = StrategyCandidate(family="momentum", params={"lookback": 1, "threshold_bps": 1, "take_profit_bps": 10, "stop_loss_bps": 50, "max_hold_minutes": 2})

    result = simulate_strategy(_candles([100, 101, 102, 103, 104]), strategy, days=1)

    assert result.trade_count >= 1
    assert all(trade.side == "LONG" and trade.symbol == "ETHUSDC" for trade in result.trades)


def test_rejects_short_strategy():
    strategy = StrategyCandidate(family="momentum", params={"side": "SHORT"})

    with pytest.raises(ValueError, match="LONG-only"):
        simulate_strategy(_candles([100, 101, 102]), strategy, days=1)


def test_fees_reduce_result():
    strategy = StrategyCandidate(family="always_long", params={"max_hold_minutes": 1})
    no_fee = simulate_strategy(_candles([100, 102, 104]), strategy, days=1, fee_rate=0, slippage_bps=0)
    with_fee = simulate_strategy(_candles([100, 102, 104]), strategy, days=1, fee_rate=0.001, slippage_bps=0)

    assert with_fee.net_profit_usdc < no_fee.net_profit_usdc
    assert with_fee.fees_usdc > 0


def test_slippage_reduces_result():
    strategy = StrategyCandidate(family="always_long", params={"max_hold_minutes": 1})
    no_slip = simulate_strategy(_candles([100, 102, 104]), strategy, days=1, fee_rate=0, slippage_bps=0)
    with_slip = simulate_strategy(_candles([100, 102, 104]), strategy, days=1, fee_rate=0, slippage_bps=10)

    assert with_slip.net_profit_usdc < no_slip.net_profit_usdc
    assert with_slip.slippage_usdc > 0


def test_no_trades_without_signal():
    strategy = StrategyCandidate(family="momentum", params={"lookback": 2, "threshold_bps": 10_000})

    result = simulate_strategy(_candles([100, 100, 100, 100]), strategy, days=1)

    assert result.trade_count == 0
    assert result.net_profit_usdc == 0


def test_tradecount_is_correct():
    strategy = StrategyCandidate(family="always_long", params={"max_hold_minutes": 1})

    result = simulate_strategy(_candles([100, 101, 102, 103]), strategy, days=1, fee_rate=0, slippage_bps=0)

    assert result.trade_count == len(result.trades)


def test_entry_uses_next_candle_after_signal_no_lookahead():
    strategy = StrategyCandidate(family="momentum", params={"lookback": 1, "threshold_bps": 1, "max_hold_minutes": 1})
    candles = _candles([100, 110, 90, 90])

    result = simulate_strategy(candles, strategy, days=1, fee_rate=0, slippage_bps=0)

    assert result.trades[0].entry_time == candles[2].open_time
    assert result.trades[0].entry_price == candles[2].open
