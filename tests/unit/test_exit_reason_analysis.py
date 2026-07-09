"""Tests for exit-reason and trade-cause summaries."""

from ethusdc_bot.backtest.exit_reason_analysis import analyze_exit_reasons
from ethusdc_bot.backtest.simulator import Trade


def _trade(reason: str, net: float, fees: float = 0.2, slippage: float = 0.1) -> Trade:
    return Trade(
        symbol="ETHUSDC",
        side="LONG",
        entry_time=1,
        exit_time=2,
        entry_price=100,
        exit_price=101,
        quantity=1,
        gross_profit_usdc=net + fees,
        fees_usdc=fees,
        slippage_usdc=slippage,
        net_profit_usdc=net,
        exit_reason=reason,
    )


def test_exit_reason_analysis_counts_reasons_and_costs():
    summary = analyze_exit_reasons(
        [
            _trade("stop_loss", -1.0, fees=0.2, slippage=0.3),
            _trade("take_profit", 2.0, fees=0.2, slippage=0.1),
            _trade("take_profit", 1.0, fees=0.2, slippage=0.1),
            _trade("time_exit", -0.5, fees=0.2, slippage=0.1),
        ]
    )

    assert summary["total_trades"] == 4
    assert summary["by_exit_reason"]["take_profit"]["count"] == 2
    assert summary["by_exit_reason"]["take_profit"]["net_usdc"] == 3.0
    assert summary["by_exit_reason"]["stop_loss"]["fees_usdc"] == 0.2
    assert summary["by_exit_reason"]["stop_loss"]["slippage_usdc"] == 0.3
    assert summary["stop_loss_share"] == 0.25
    assert summary["take_profit_share"] == 0.5
    assert summary["time_exit_share"] == 0.25
    assert summary["cost_load_per_trade"] == 0.35
    assert summary["loss_per_losing_trade"] == -0.75


def test_exit_reason_analysis_empty_trades_is_explicit_zero_summary():
    summary = analyze_exit_reasons([])

    assert summary["total_trades"] == 0
    assert summary["by_exit_reason"] == {}
    assert summary["cost_load_per_trade"] == 0.0
