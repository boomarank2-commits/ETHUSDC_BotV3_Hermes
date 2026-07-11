"""Integration tests for context vetoes inside the existing ETHUSDC simulator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle, DataLoadError
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy


def _candles(
    closes: list[float],
    *,
    start: datetime | None = None,
) -> list[Candle]:
    origin = start or datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(
            open_time=int((origin + timedelta(minutes=index)).timestamp() * 1000),
            open=close,
            high=close + 0.25,
            low=close - 0.25,
            close=close,
            volume=1.0,
        )
        for index, close in enumerate(closes)
    ]


def _context(
    eth: list[Candle],
    *,
    btc_closes: list[float] | None = None,
    ratio_closes: list[float] | None = None,
) -> AlignedMarketCandles:
    origin = datetime.fromtimestamp(eth[0].open_time / 1000, tz=UTC)
    btc = _candles(btc_closes or [100 + index * 0.1 for index in range(len(eth))], start=origin)
    ratio = _candles(
        ratio_closes or [1 + index * 0.001 for index in range(len(eth))],
        start=origin,
    )
    return AlignedMarketCandles(
        ethusdc=tuple(eth),
        btcusdc=tuple(btc),
        ethbtc=tuple(ratio),
    )


def _context_candidate(base_family: str = "always_long", **overrides: object) -> StrategyCandidate:
    params: dict[str, object] = {
        "symbol": "ETHUSDC",
        "base_family": base_family,
        "max_hold_minutes": 1,
        "take_profit_bps": 10_000,
        "stop_loss_bps": 10_000,
        "context_btc_trend_lookback": 2,
        "context_btc_min_trend_bps": -10.0,
        "context_btc_volatility_lookback": 2,
        "context_btc_max_volatility_bps": 100.0,
        "context_ethbtc_trend_lookback": 2,
        "context_ethbtc_min_trend_bps": -10.0,
    }
    params.update(overrides)
    return StrategyCandidate("context_filter", params)  # type: ignore[arg-type]


def test_missing_context_fails_closed_and_never_replays_base_strategy() -> None:
    eth = _candles([100 + index * 0.1 for index in range(12)])

    result = simulate_strategy(eth, _context_candidate(), days=1)

    assert result.trade_count == 0
    assert result.rejections["context_data_missing"] > 0
    assert result.rejections.get("context_allowed", 0) == 0


def test_favorable_context_confirms_existing_ethusdc_base_signals() -> None:
    eth = _candles([100 + index * 0.1 for index in range(12)])

    result = simulate_strategy(
        eth,
        _context_candidate(),
        days=1,
        market_context=_context(eth),
    )

    assert result.trade_count > 0
    assert all(trade.symbol == "ETHUSDC" for trade in result.trades)
    assert all(trade.side == "LONG" for trade in result.trades)
    assert result.rejections.get("context_data_missing", 0) == 0


def test_btc_downtrend_veto_blocks_base_signals_and_is_reported() -> None:
    eth = _candles([100 + index * 0.1 for index in range(12)])
    btc = [100 - index * 0.2 for index in range(12)]

    result = simulate_strategy(
        eth,
        _context_candidate(context_btc_min_trend_bps=-5.0),
        days=1,
        market_context=_context(eth, btc_closes=btc),
    )

    assert result.trade_count == 0
    assert result.rejections["context_veto_btc_trend"] > 0


def test_context_never_creates_a_trade_without_a_base_signal() -> None:
    eth = _candles([100.0] * 12)
    candidate = _context_candidate(
        "momentum",
        lookback=2,
        threshold_bps=10_000,
    )

    result = simulate_strategy(
        eth,
        candidate,
        days=1,
        market_context=_context(eth),
    )

    assert result.trade_count == 0
    assert result.rejections.get("context_data_missing", 0) == 0
    assert result.rejections.get("context_veto_btc_trend", 0) == 0
    assert result.rejections.get("context_veto_btc_volatility", 0) == 0
    assert result.rejections.get("context_veto_ethbtc_relative_strength", 0) == 0


def test_recursive_context_base_is_rejected_without_recursion() -> None:
    eth = _candles([100 + index * 0.1 for index in range(12)])

    result = simulate_strategy(
        eth,
        _context_candidate("context_filter"),
        days=1,
        market_context=_context(eth),
    )

    assert result.trade_count == 0
    assert result.rejections["context_recursive_base_forbidden"] > 0


def test_misaligned_context_is_rejected_before_simulation() -> None:
    eth = _candles([100 + index * 0.1 for index in range(12)])
    aligned = _context(eth)
    shifted_eth = list(aligned.ethusdc)
    shifted_eth[3] = Candle(
        open_time=shifted_eth[3].open_time + 60_000,
        open=shifted_eth[3].open,
        high=shifted_eth[3].high,
        low=shifted_eth[3].low,
        close=shifted_eth[3].close,
        volume=shifted_eth[3].volume,
    )
    bad_context = AlignedMarketCandles(
        ethusdc=tuple(shifted_eth),
        btcusdc=aligned.btcusdc,
        ethbtc=aligned.ethbtc,
    )

    with pytest.raises(DataLoadError, match="timestamps differ"):
        simulate_strategy(
            eth,
            _context_candidate(),
            days=1,
            market_context=bad_context,
        )


def test_non_context_strategy_is_identical_with_or_without_market_context() -> None:
    eth = _candles([100 + index * 0.1 for index in range(12)])
    candidate = StrategyCandidate(
        "always_long",
        {
            "symbol": "ETHUSDC",
            "max_hold_minutes": 1,
            "take_profit_bps": 10_000,
            "stop_loss_bps": 10_000,
        },
    )

    without_context = simulate_strategy(eth, candidate, days=1)
    with_context = simulate_strategy(
        eth,
        candidate,
        days=1,
        market_context=_context(
            eth,
            btc_closes=[200 - index * 10 for index in range(12)],
            ratio_closes=[2 - index * 0.1 for index in range(12)],
        ),
    )

    assert with_context == without_context


def test_non_ethusdc_symbol_remains_forbidden_even_with_context() -> None:
    eth = _candles([100 + index * 0.1 for index in range(12)])

    with pytest.raises(ValueError, match="Only ETHUSDC"):
        simulate_strategy(
            eth,
            _context_candidate(symbol="BTCUSDC"),
            days=1,
            market_context=_context(eth),
        )
