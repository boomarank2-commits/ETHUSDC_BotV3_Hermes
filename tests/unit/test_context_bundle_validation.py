"""Regression tests for internal context timeline validation."""

from datetime import UTC, datetime, timedelta

import pytest

from ethusdc_bot.backtest.context_features import (
    ContextVetoPolicy,
    validate_context_against_trade_candles,
)
from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle, DataLoadError


def _series(start: datetime, count: int) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            open_time=int((start + timedelta(minutes=index)).timestamp() * 1000),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1.0,
        )
        for index in range(count)
    )


def test_context_bundle_rejects_shifted_btc_timeline() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    eth = _series(start, 5)
    btc = list(_series(start, 5))
    btc[2] = Candle(
        open_time=btc[2].open_time + 60_000,
        open=btc[2].open,
        high=btc[2].high,
        low=btc[2].low,
        close=btc[2].close,
        volume=btc[2].volume,
    )
    context = AlignedMarketCandles(
        ethusdc=eth,
        btcusdc=tuple(btc),
        ethbtc=_series(start, 5),
    )

    with pytest.raises(DataLoadError, match="BTCUSDC market context timestamps differ"):
        validate_context_against_trade_candles(eth, context)


def test_context_bundle_rejects_shifted_ethbtc_timeline() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    eth = _series(start, 5)
    ratio = list(_series(start, 5))
    ratio[3] = Candle(
        open_time=ratio[3].open_time + 60_000,
        open=ratio[3].open,
        high=ratio[3].high,
        low=ratio[3].low,
        close=ratio[3].close,
        volume=ratio[3].volume,
    )
    context = AlignedMarketCandles(
        ethusdc=eth,
        btcusdc=_series(start, 5),
        ethbtc=tuple(ratio),
    )

    with pytest.raises(DataLoadError, match="ETHBTC market context timestamps differ"):
        validate_context_against_trade_candles(eth, context)


def test_context_bundle_accepts_exact_three_market_identity() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    eth = _series(start, 5)
    context = AlignedMarketCandles(
        ethusdc=eth,
        btcusdc=_series(start, 5),
        ethbtc=_series(start, 5),
    )

    validate_context_against_trade_candles(eth, context)
    assert ContextVetoPolicy(btc_trend_lookback=2).warmup_candles >= 2
