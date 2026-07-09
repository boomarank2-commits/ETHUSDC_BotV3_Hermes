"""Train/blind split logic for ETHUSDC backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ethusdc_bot.backtest.data_loader import Candle

TRAINING_DAYS = 730
BLINDTEST_DAYS = 365
REQUIRED_DAYS = TRAINING_DAYS + BLINDTEST_DAYS


@dataclass(frozen=True)
class SplitResult:
    training: list[Candle]
    blindtest: list[Candle]
    data_start: str
    data_end: str
    training_start: str
    training_end: str
    blind_start: str
    blind_end: str
    training_days: int
    blindtest_days: int


def split_train_blind(candles: list[Candle], *, required_days: int | None = REQUIRED_DAYS) -> SplitResult:
    if not candles:
        raise ValueError("Cannot split empty candles")
    dates = sorted({_utc_day(candle.open_time) for candle in candles})
    if required_days is not None and len(dates) != required_days:
        raise ValueError(f"Expected exactly {required_days} complete UTC days, observed {len(dates)}")
    if required_days is not None:
        training_day_count = TRAINING_DAYS
        blind_day_count = BLINDTEST_DAYS
    else:
        training_day_count = max(1, len(dates) * 2 // 3)
        blind_day_count = len(dates) - training_day_count
        if blind_day_count <= 0:
            training_day_count = max(1, len(dates) - 1)
            blind_day_count = len(dates) - training_day_count
    training_days = set(dates[:training_day_count])
    blind_days = set(dates[training_day_count : training_day_count + blind_day_count])
    training = [candle for candle in candles if _utc_day(candle.open_time) in training_days]
    blindtest = [candle for candle in candles if _utc_day(candle.open_time) in blind_days]
    if not training or not blindtest:
        raise ValueError("Split requires non-empty training and blindtest windows")
    if max(c.open_time for c in training) >= min(c.open_time for c in blindtest):
        raise ValueError("Training and blindtest windows overlap")
    return SplitResult(
        training=training,
        blindtest=blindtest,
        data_start=dates[0],
        data_end=dates[-1],
        training_start=dates[0],
        training_end=dates[training_day_count - 1],
        blind_start=dates[training_day_count],
        blind_end=dates[training_day_count + blind_day_count - 1],
        training_days=training_day_count,
        blindtest_days=blind_day_count,
    )


def _utc_day(open_time_ms: int) -> str:
    return datetime.fromtimestamp(open_time_ms / 1000, tz=UTC).date().isoformat()
