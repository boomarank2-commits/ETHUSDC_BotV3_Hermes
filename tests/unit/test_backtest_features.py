"""Tests for no-lookahead backtest feature construction."""

from datetime import UTC, datetime, timedelta

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.features import build_feature_rows


def _candles(closes: list[float]) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Candle(
            open_time=int((start + timedelta(minutes=index)).timestamp() * 1000),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=10 + index,
        )
        for index, close in enumerate(closes)
    ]


def test_features_include_required_fields():
    rows = build_feature_rows(_candles([100, 101, 102, 103, 104]), windows=(1, 3))

    row = rows[-1]
    for key in [
        "return_1",
        "return_3",
        "rolling_volatility_3",
        "intraday_range_bps",
        "breakout_distance_3",
        "mean_reversion_distance_3",
        "trend_slope_3",
        "relative_volume_3",
        "hour_utc",
        "minute_of_day",
    ]:
        assert key in row


def test_features_use_only_current_and_past_candles_no_lookahead():
    base = _candles([100, 101, 102, 103, 104, 999])
    without_future = build_feature_rows(base[:5], windows=(3,))
    with_future = build_feature_rows(base, windows=(3,))

    assert with_future[4] == without_future[4]


def test_features_are_aligned_to_source_candle_open_time():
    candles = _candles([100, 101, 102])
    rows = build_feature_rows(candles, windows=(1,))

    assert [row["open_time"] for row in rows] == [c.open_time for c in candles]
