"""Tests for conservative LONG-only backtest simulation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.equity import EquityPoint, max_underwater_calendar_days
from ethusdc_bot.backtest.simulator import StrategyCandidate, _exit_trade, simulate_strategy


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


def _flat_roundtrips(count: int, *, fee_rate: float = 0.0, slippage_bps: float = 5.0):
    strategy = StrategyCandidate(family="always_long", params={"max_hold_minutes": 1})
    return simulate_strategy(
        _candles([100.0] * (count * 2 + 1)), strategy, days=1, fee_rate=fee_rate, slippage_bps=slippage_bps
    )


def _single_exit(entry_mid: float, exit_mid: float, *, fee_rate: float = 0.0, slippage_bps: float = 5.0, reason: str = "time_exit"):
    execution = entry_mid * (1 + slippage_bps / 10_000)
    quantity = 100.0 / execution
    candle = Candle(open_time=120_000, open=exit_mid, high=exit_mid, low=exit_mid, close=exit_mid, volume=1)
    return _exit_trade(
        candle,
        {"entry_mid_price": entry_mid, "entry_price": execution, "quantity": quantity, "entry_time": 60_000, "entry_index": 1},
        fee_rate,
        slippage_bps,
        100.0,
        exit_reason=reason,
    )


def test_flat_roundtrip_reports_execution_slippage_once():
    trade = _single_exit(100.0, 100.0)
    assert trade.entry_slippage_usdc == pytest.approx(0.0499750125, abs=1e-10)
    assert trade.exit_slippage_usdc == pytest.approx(0.0499750125, abs=1e-10)
    assert trade.slippage_usdc == pytest.approx(0.099950025, abs=1e-10)
    assert trade.net_profit_usdc == pytest.approx(-0.099950025, abs=1e-10)


def test_flat_roundtrip_fees_and_slippage_are_not_double_counted():
    trade = _single_exit(100.0, 100.0, fee_rate=0.001)
    assert trade.slippage_usdc == pytest.approx(0.099950025, abs=1e-10)
    assert trade.fees_usdc == pytest.approx(0.19990005, abs=1e-10)
    assert trade.net_profit_usdc == pytest.approx(-0.299850075, abs=1e-10)


@pytest.mark.parametrize("exit_mid", [99.0, 101.0, 120.0])
def test_market_movement_is_not_reported_as_slippage(exit_mid: float):
    trade = _single_exit(100.0, exit_mid)
    expected = (100.0 * 0.0005 + exit_mid * 0.0005) * trade.quantity
    assert trade.slippage_usdc == pytest.approx(expected, abs=1e-10)


def test_identical_flat_roundtrips_scale_costs_linearly():
    one = _flat_roundtrips(1)
    ten = _flat_roundtrips(10)
    many = _flat_roundtrips(1623)
    assert ten.trade_count == 10
    assert ten.slippage_usdc == pytest.approx(one.slippage_usdc * 10, abs=1e-8)
    assert many.trade_count == 1623
    assert many.slippage_usdc == pytest.approx(162.2188906, abs=1e-6)
    assert many.slippage_usdc < 200


def test_holding_duration_does_not_change_flat_trade_slippage():
    short = simulate_strategy(_candles([100.0] * 3), StrategyCandidate("always_long", {"max_hold_minutes": 1}), days=1, fee_rate=0, slippage_bps=5)
    long = simulate_strategy(_candles([100.0] * 8), StrategyCandidate("always_long", {"max_hold_minutes": 6}), days=1, fee_rate=0, slippage_bps=5)
    assert short.trades[0].slippage_usdc == long.trades[0].slippage_usdc


def test_entry_and_exit_fees_are_each_charged_exactly_once():
    trade = _single_exit(100.0, 101.0, fee_rate=0.001)
    assert trade.entry_fee_usdc == pytest.approx(0.1)
    assert trade.exit_fee_usdc == pytest.approx(trade.exit_price * trade.quantity * 0.001)
    assert trade.fees_usdc == pytest.approx(trade.entry_fee_usdc + trade.exit_fee_usdc)


def test_net_profit_identity_uses_execution_gross_minus_fees():
    trade = _single_exit(100.0, 120.0, fee_rate=0.001)
    assert trade.net_profit_usdc == pytest.approx(trade.gross_profit_usdc - trade.fees_usdc, abs=1e-10)


def test_quantity_uses_actual_entry_execution_price():
    trade = _single_exit(100.0, 100.0)
    assert trade.quantity == pytest.approx(100.0 / trade.entry_price)
    assert trade.entry_price * trade.quantity == pytest.approx(100.0)


def test_forced_end_of_data_exit_uses_same_cost_logic():
    result = simulate_strategy(_candles([100.0, 100.0]), StrategyCandidate("always_long", {"max_hold_minutes": 99}), days=1, fee_rate=0.001, slippage_bps=5)
    trade = result.trades[0]
    assert trade.exit_reason == "end_of_data"
    assert trade.slippage_usdc == pytest.approx(trade.entry_slippage_usdc + trade.exit_slippage_usdc)
    assert trade.net_profit_usdc == pytest.approx(trade.gross_profit_usdc - trade.fees_usdc)


@pytest.mark.parametrize("reason", ["take_profit", "stop_loss", "time_exit", "break_even", "trailing_stop"])
def test_all_rule_exit_reasons_share_one_execution_cost_formula(reason: str):
    trade = _single_exit(100.0, 101.0, fee_rate=0.001, reason=reason)
    assert trade.exit_reason == reason
    assert trade.slippage_usdc == pytest.approx(trade.entry_slippage_usdc + trade.exit_slippage_usdc)
    assert trade.fees_usdc == pytest.approx(trade.entry_fee_usdc + trade.exit_fee_usdc)
    assert trade.net_profit_usdc == pytest.approx(trade.gross_profit_usdc - trade.fees_usdc)


def test_mark_to_market_curve_is_timestamped_and_ends_at_realized_net_profit():
    candles = _candles([100.0, 100.0, 100.0])
    result = simulate_strategy(
        candles,
        StrategyCandidate("always_long", {"max_hold_minutes": 99}),
        days=1,
        fee_rate=0.001,
        slippage_bps=5,
    )

    assert result.drawdown_method == "mark_to_market"
    assert len(result.equity_curve) == len(candles) + 1
    assert result.equity_curve[0] == EquityPoint(candles[0].open_time, 0.0)
    assert result.equity_curve[-1].timestamp_ms == candles[-1].open_time + 59_999
    assert result.equity_curve[-1].equity_usdc == result.metrics.net_profit_usdc
    assert result.equity_curve_usdc[-1] == result.net_profit_usdc
    assert result.equity_curve_timestamps_ms == sorted(result.equity_curve_timestamps_ms)
    assert len(set(result.equity_curve_timestamps_ms)) == len(result.equity_curve_timestamps_ms)


def test_open_position_adverse_mark_is_visible_before_a_flat_realized_exit():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    prices = [
        (100.0, 100.0),
        (100.0, 100.0),
        (100.0, 50.0),
        (100.0, 100.0),
        (100.0, 100.0),
    ]
    candles = [
        Candle(
            open_time=int((start + timedelta(minutes=index)).timestamp() * 1000),
            open=open_price,
            high=max(open_price, close_price),
            low=min(open_price, close_price),
            close=close_price,
            volume=1.0,
        )
        for index, (open_price, close_price) in enumerate(prices)
    ]
    result = simulate_strategy(
        candles,
        StrategyCandidate(
            "always_long",
            {
                "max_hold_minutes": 99,
                "take_profit_bps": 10_000,
                "stop_loss_bps": 10_000,
            },
        ),
        days=1,
        fee_rate=0.001,
        slippage_bps=5,
    )

    assert result.trade_count == 1
    assert result.trades[0].exit_reason == "end_of_data"
    assert result.net_profit_usdc == pytest.approx(-0.299850075, abs=1e-10)
    assert min(result.equity_curve_usdc) < -50.0
    assert result.max_drawdown_usdc > 50.0
    assert result.max_drawdown_usdc > abs(result.net_profit_usdc)


def test_open_flat_position_liquidation_mark_books_costs_once():
    result = simulate_strategy(
        _candles([100.0, 100.0, 100.0]),
        StrategyCandidate("always_long", {"max_hold_minutes": 99}),
        days=1,
        fee_rate=0.001,
        slippage_bps=5,
    )

    entry_close_mark = result.equity_curve[2].equity_usdc
    assert entry_close_mark == pytest.approx(-0.299850075, abs=1e-10)
    assert entry_close_mark == pytest.approx(result.trades[0].net_profit_usdc, abs=1e-10)


def test_underwater_metric_counts_distinct_utc_calendar_days():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    points = (
        EquityPoint(int(start.timestamp() * 1000), 0.0),
        EquityPoint(int((start + timedelta(hours=1)).timestamp() * 1000), -1.0),
        EquityPoint(int((start + timedelta(days=1, hours=1)).timestamp() * 1000), -0.5),
        EquityPoint(int((start + timedelta(days=2)).timestamp() * 1000), 0.0),
    )

    assert max_underwater_calendar_days(points) == 2
