"""No-lookahead deterministic feature construction from ETHUSDC 1m candles."""

from __future__ import annotations

from datetime import UTC, datetime
from math import sqrt
from statistics import mean
from typing import Any

from ethusdc_bot.backtest.data_loader import Candle


def build_feature_rows(candles: list[Candle], *, windows: tuple[int, ...] = (5, 15, 60)) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    returns_1 = [0.0]
    for index in range(1, len(candles)):
        previous = candles[index - 1].close
        returns_1.append((candles[index].close / previous - 1) if previous else 0.0)
    for index, candle in enumerate(candles):
        dt = datetime.fromtimestamp(candle.open_time / 1000, tz=UTC)
        row: dict[str, Any] = {
            "open_time": candle.open_time,
            "intraday_range_bps": _bps((candle.high - candle.low) / candle.open) if candle.open else 0.0,
            "hour_utc": dt.hour,
            "minute_of_day": dt.hour * 60 + dt.minute,
        }
        for window in windows:
            start = max(0, index - window + 1)
            history = candles[start : index + 1]
            reference_index = max(0, index - window)
            reference = candles[reference_index].close
            closes = [c.close for c in history]
            volumes = [c.volume for c in history]
            highs = [c.high for c in history]
            lows = [c.low for c in history]
            window_returns = returns_1[max(0, index - window + 1) : index + 1]
            avg_close = mean(closes) if closes else candle.close
            avg_volume = mean(volumes) if volumes else candle.volume
            row[f"return_{window}"] = (candle.close / reference - 1) if reference else 0.0
            row[f"rolling_volatility_{window}"] = _stddev(window_returns)
            row[f"breakout_distance_{window}"] = (candle.close / max(highs) - 1) if highs and max(highs) else 0.0
            row[f"mean_reversion_distance_{window}"] = (candle.close / avg_close - 1) if avg_close else 0.0
            row[f"trend_slope_{window}"] = (closes[-1] - closes[0]) / max(1, len(closes) - 1) if len(closes) > 1 else 0.0
            row[f"relative_volume_{window}"] = candle.volume / avg_volume if avg_volume else 1.0
            row[f"range_position_{window}"] = (candle.close - min(lows)) / (max(highs) - min(lows)) if highs and max(highs) > min(lows) else 0.5
        rows.append(row)
    return rows


def _stddev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    avg = mean(values)
    return sqrt(sum((value - avg) ** 2 for value in values) / len(values))


def _bps(value: float) -> float:
    return value * 10_000
