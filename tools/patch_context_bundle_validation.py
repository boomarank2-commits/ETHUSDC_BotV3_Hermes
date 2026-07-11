from pathlib import Path

path = Path(__file__).resolve().parents[1] / "src/ethusdc_bot/backtest/context_features.py"
text = path.read_text(encoding="utf-8")
old = '''    expected = tuple(candle.open_time for candle in trade_candles)\n    if expected != context.open_times:\n        raise DataLoadError(\n            "ETHUSDC simulation candles and market context timestamps differ"\n        )\n'''
new = '''    expected = tuple(candle.open_time for candle in trade_candles)\n    if expected != context.open_times:\n        raise DataLoadError(\n            "ETHUSDC simulation candles and market context timestamps differ"\n        )\n    for symbol, candles in (\n        ("BTCUSDC", context.btcusdc),\n        ("ETHBTC", context.ethbtc),\n    ):\n        open_times = tuple(candle.open_time for candle in candles)\n        if open_times != expected:\n            raise DataLoadError(\n                f"{symbol} market context timestamps differ from ETHUSDC"\n            )\n'''
if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
elif new not in text:
    raise RuntimeError("expected context alignment fragment not found")
