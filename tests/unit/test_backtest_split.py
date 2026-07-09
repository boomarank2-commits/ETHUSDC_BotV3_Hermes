"""Tests for train/blind split boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.split import split_train_blind


def _daily_candles(days: int) -> list[Candle]:
    start = datetime(2023, 1, 1, tzinfo=UTC)
    return [
        Candle(open_time=int((start + timedelta(days=day)).timestamp() * 1000), open=100, high=101, low=99, close=100, volume=1)
        for day in range(days)
    ]


def test_split_uses_730_training_and_365_blindtest_days():
    result = split_train_blind(_daily_candles(1095))

    assert result.training_days == 730
    assert result.blindtest_days == 365
    assert len(result.training) == 730
    assert len(result.blindtest) == 365


def test_split_has_no_overlap():
    result = split_train_blind(_daily_candles(1095))

    training_times = {c.open_time for c in result.training}
    blind_times = {c.open_time for c in result.blindtest}
    assert training_times.isdisjoint(blind_times)
    assert max(training_times) < min(blind_times)


def test_blindtest_data_is_not_in_training():
    result = split_train_blind(_daily_candles(1095))

    assert result.training_end < result.blind_start
    assert result.data_start == result.training_start
    assert result.data_end == result.blind_end
