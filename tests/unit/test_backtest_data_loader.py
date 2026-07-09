"""Tests for read-only ETHUSDC backtest kline loading."""

from __future__ import annotations

import csv
from datetime import UTC, datetime, timedelta
from pathlib import Path
import zipfile

import pytest

from ethusdc_bot.backtest.data_loader import DataLoadError, load_ethusdc_1m_candles


def _write_kline_zip(root: Path, symbol: str, day: datetime, minutes: int = 3, *, duplicate: bool = False, gap: bool = False) -> None:
    folder = root / "raw" / "binance" / "spot" / symbol / "klines" / "1m"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{symbol}-1m-{day.date().isoformat()}.zip"
    rows = []
    for index in range(minutes):
        if gap and index == 1:
            continue
        open_time = int((day + timedelta(minutes=index)).timestamp() * 1000)
        rows.append([open_time, "100.0", "101.0", "99.0", "100.5", "10.0"])
    if duplicate and rows:
        rows.append(rows[-1])
    csv_text = "\n".join(",".join(str(value) for value in row) for row in rows) + "\n"
    with zipfile.ZipFile(folder / name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name.replace(".zip", ".csv"), csv_text)
    (folder / f"{name}.CHECKSUM").write_text("fixture checksum\n", encoding="utf-8")


def test_loads_fixture_zip_correctly(tmp_path):
    day = datetime(2024, 1, 1, tzinfo=UTC)
    _write_kline_zip(tmp_path, "ETHUSDC", day, minutes=3)

    candles = load_ethusdc_1m_candles(tmp_path)

    assert [c.open_time for c in candles] == [int((day + timedelta(minutes=i)).timestamp() * 1000) for i in range(3)]
    assert candles[0].open == 100.0
    assert candles[0].high == 101.0
    assert candles[0].low == 99.0
    assert candles[0].close == 100.5
    assert candles[0].volume == 10.0


def test_rejects_wrong_symbol(tmp_path):
    _write_kline_zip(tmp_path, "BTCUSDC", datetime(2024, 1, 1, tzinfo=UTC), minutes=3)

    with pytest.raises(DataLoadError, match="ETHUSDC"):
        load_ethusdc_1m_candles(tmp_path)


def test_rejects_gaps(tmp_path):
    _write_kline_zip(tmp_path, "ETHUSDC", datetime(2024, 1, 1, tzinfo=UTC), minutes=3, gap=True)

    with pytest.raises(DataLoadError, match="gap"):
        load_ethusdc_1m_candles(tmp_path)


def test_rejects_duplicates(tmp_path):
    _write_kline_zip(tmp_path, "ETHUSDC", datetime(2024, 1, 1, tzinfo=UTC), minutes=3, duplicate=True)

    with pytest.raises(DataLoadError, match="duplicate"):
        load_ethusdc_1m_candles(tmp_path)


def test_rejects_repo_raw_data_path():
    repo_raw = Path.cwd() / "raw" / "binance" / "spot" / "ETHUSDC" / "klines" / "1m"

    with pytest.raises(DataLoadError, match="repository"):
        load_ethusdc_1m_candles(repo_raw)
