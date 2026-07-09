"""Tests for backtest metrics."""

from ethusdc_bot.backtest.metrics import compute_metrics
from ethusdc_bot.backtest.simulator import Trade


def test_metrics_include_required_fields():
    trades = [
        Trade(symbol="ETHUSDC", side="LONG", entry_time=1, exit_time=2, entry_price=100, exit_price=101, quantity=1, gross_profit_usdc=1, fees_usdc=0.2, slippage_usdc=0.1, net_profit_usdc=0.7, exit_reason="test"),
        Trade(symbol="ETHUSDC", side="LONG", entry_time=3, exit_time=4, entry_price=100, exit_price=99, quantity=1, gross_profit_usdc=-1, fees_usdc=0.2, slippage_usdc=0.1, net_profit_usdc=-1.3, exit_reason="test"),
    ]

    metrics = compute_metrics(trades, days=2, training_days=730, blindtest_days=365)

    assert metrics.net_profit_usdc == -0.6
    assert metrics.net_usdc_per_day == -0.3
    assert metrics.trade_count == 2
    assert metrics.winrate == 0.5
    assert metrics.max_drawdown_usdc >= 0
    assert metrics.profit_factor >= 0
    assert metrics.average_trade_usdc == -0.3
    assert metrics.fees_usdc == 0.4
    assert metrics.slippage_usdc == 0.2
    assert metrics.training_days == 730
    assert metrics.blindtest_days == 365
