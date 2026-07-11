"""Tests for strict read-only BTCUSDC/ETHBTC context data loading."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import zipfile

import pytest

from ethusdc_bot.backtest.data_loader import (
    ALLOWED_KLINE_SYMBOLS,
    CONTEXT_SYMBOLS,
    TRADE_SYMBOL,
    Candle,
    DataLoadError,
    align_market_candles,
    load_aligned_market_candles,
    load_context_1m_candles,
    load_symbol_1m_candles,
)


def _write_symbol_day(
    root: Path,
    symbol: str,
    day: datetime,
    *,
    minutes: int = 3,
    start_offset_minutes: int = 0,
    missing_index: int | None = None,
    inner_symbol: str | None = None,
) -> None:
    folder = root / "raw" / "binance" / "spot" / symbol / "klines" / "1m"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{symbol}-1m-{day.date().isoformat()}.zip"
    rows: list[str] = []
    for index in range(minutes):
        if index == missing_index:
            continue
        timestamp = day + timedelta(minutes=start_offset_minutes + index)
        open_time = int(timestamp.timestamp() * 1000)
        base = 100.0 + index
        rows.append(f"{open_time},{base},{base + 1},{base - 1},{base + 0.5},10")
    csv_symbol = inner_symbol or symbol
    inner_name = f"{csv_symbol}-1m-{day.date().isoformat()}.csv"
    with zipfile.ZipFile(folder / name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(inner_name, "\n".join(rows) + "\n")
    (folder / f"{name}.CHECKSUM").write_text("fixture checksum\n", encoding="utf-8")


def _candles(start_ms: int, count: int) -> list[Candle]:
    return [
        Candle(
            open_time=start_ms + index * 60_000,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1.0,
        )
        for index in range(count)
    ]


def test_symbol_allowlist_is_exact_and_keeps_one_trade_market() -> None:
    assert ALLOWED_KLINE_SYMBOLS == ("ETHUSDC", "BTCUSDC", "ETHBTC")
    assert TRADE_SYMBOL == "ETHUSDC"
    assert CONTEXT_SYMBOLS == ("BTCUSDC", "ETHBTC")


def test_loads_each_allowlisted_public_symbol_without_changing_role(tmp_path: Path) -> None:
    day = datetime(2024, 1, 1, tzinfo=UTC)
    for symbol in ALLOWED_KLINE_SYMBOLS:
        _write_symbol_day(tmp_path, symbol, day)

    for symbol in ALLOWED_KLINE_SYMBOLS:
        candles = load_symbol_1m_candles(tmp_path, symbol)
        assert len(candles) == 3
        assert candles[0].open_time == int(day.timestamp() * 1000)

    assert len(load_context_1m_candles(tmp_path, "btcusdc")) == 3
    assert len(load_context_1m_candles(tmp_path, "ethbtc")) == 3


def test_context_loader_rejects_trade_symbol_and_unknown_symbols(tmp_path: Path) -> None:
    with pytest.raises(DataLoadError, match="context symbol"):
        load_context_1m_candles(tmp_path, "ETHUSDC")
    with pytest.raises(DataLoadError, match="symbol must be one of"):
        load_symbol_1m_candles(tmp_path, "BNBUSDC")
    with pytest.raises(DataLoadError, match="symbol must be a string"):
        load_symbol_1m_candles(tmp_path, 123)  # type: ignore[arg-type]


def test_context_zip_must_identify_the_requested_symbol(tmp_path: Path) -> None:
    day = datetime(2024, 1, 1, tzinfo=UTC)
    _write_symbol_day(tmp_path, "BTCUSDC", day, inner_symbol="ETHUSDC")

    with pytest.raises(DataLoadError, match="CSV must identify BTCUSDC"):
        load_context_1m_candles(tmp_path, "BTCUSDC")


def test_loads_three_markets_with_exact_timestamp_alignment(tmp_path: Path) -> None:
    day = datetime(2024, 1, 1, tzinfo=UTC)
    for symbol in ALLOWED_KLINE_SYMBOLS:
        _write_symbol_day(tmp_path, symbol, day, minutes=5)

    aligned = load_aligned_market_candles(tmp_path)

    assert aligned.candle_count == 5
    assert aligned.open_times == tuple(candle.open_time for candle in aligned.ethusdc)
    assert tuple(candle.open_time for candle in aligned.btcusdc) == aligned.open_times
    assert tuple(candle.open_time for candle in aligned.ethbtc) == aligned.open_times
    assert aligned.context_for("BTCUSDC") == aligned.btcusdc
    assert aligned.context_for("ethbtc") == aligned.ethbtc


def test_alignment_rejects_different_lengths_without_forward_fill() -> None:
    start = 1_700_000_000_000

    with pytest.raises(DataLoadError, match="counts are not aligned"):
        align_market_candles(_candles(start, 3), _candles(start, 2), _candles(start, 3))


def test_alignment_rejects_shifted_context_timestamps() -> None:
    start = 1_700_000_000_000

    with pytest.raises(DataLoadError, match="not exactly aligned"):
        align_market_candles(
            _candles(start, 3),
            _candles(start + 60_000, 3),
            _candles(start, 3),
        )


def test_alignment_rejects_internal_context_gap() -> None:
    start = 1_700_000_000_000
    btc = _candles(start, 3)
    btc[1] = Candle(
        open_time=start + 120_000,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1.0,
    )

    with pytest.raises(DataLoadError, match="gap in BTCUSDC"):
        align_market_candles(_candles(start, 3), btc, _candles(start, 3))


def test_symbol_loader_rejects_missing_minute_inside_context_zip(tmp_path: Path) -> None:
    day = datetime(2024, 1, 1, tzinfo=UTC)
    _write_symbol_day(tmp_path, "BTCUSDC", day, minutes=4, missing_index=1)

    with pytest.raises(DataLoadError, match="gap"):
        load_context_1m_candles(tmp_path, "BTCUSDC")


def test_alignment_never_mutates_input_sequences() -> None:
    start = 1_700_000_000_000
    eth = _candles(start, 2)
    btc = _candles(start, 2)
    ratio = _candles(start, 2)

    aligned = align_market_candles(eth, btc, ratio)

    assert isinstance(aligned.ethusdc, tuple)
    assert isinstance(aligned.btcusdc, tuple)
    assert isinstance(aligned.ethbtc, tuple)
    eth.append(_candles(start + 120_000, 1)[0])
    assert aligned.candle_count == 2
