"""Tests for context data loading safety."""

from ethusdc_bot.backtest.context_loader import CONTEXT_SYMBOLS, context_symbol_can_trigger_trade, build_context_summary
from ethusdc_bot.backtest.data_loader import Candle


def test_context_symbols_never_trigger_trades():
    assert CONTEXT_SYMBOLS == {"BTCUSDC", "ETHBTC"}
    assert context_symbol_can_trigger_trade("BTCUSDC") is False
    assert context_symbol_can_trigger_trade("ETHBTC") is False
    assert context_symbol_can_trigger_trade("ETHUSDC") is True


def test_context_summary_is_past_based_and_not_order_source():
    rows = build_context_summary(
        "BTCUSDC",
        [
            Candle(open_time=1, open=100, high=101, low=99, close=100, volume=1),
            Candle(open_time=2, open=100, high=102, low=99, close=101, volume=1),
            Candle(open_time=3, open=101, high=103, low=100, close=102, volume=1),
        ],
        lookback=2,
    )

    assert rows[-1]["symbol"] == "BTCUSDC"
    assert rows[-1]["may_trigger_trade"] is False
    assert rows[-1]["context_return"] > 0
