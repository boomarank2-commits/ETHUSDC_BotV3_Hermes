"""Context-data helpers for BTCUSDC/ETHBTC.

Context symbols may provide market filters, but they never trigger ETHUSDC orders.
"""

from __future__ import annotations

import csv
from pathlib import Path
import zipfile
from typing import Any

from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS, _parse_row, _validate_raw_root

CONTEXT_SYMBOLS = {"BTCUSDC", "ETHBTC"}


def context_symbol_can_trigger_trade(symbol: str) -> bool:
    return symbol == "ETHUSDC"


def load_context_1m_candles(raw_root: str | Path, symbol: str, *, max_candles: int | None = None) -> list[Candle]:
    if symbol not in CONTEXT_SYMBOLS:
        raise ValueError("Only BTCUSDC and ETHBTC are supported context symbols")
    root = _validate_raw_root(Path(raw_root))
    folder = root / "raw" / "binance" / "spot" / symbol / "klines" / "1m"
    if not folder.exists():
        return []
    candles: list[Candle] = []
    previous: int | None = None
    checksums = {p.name[: -len(".CHECKSUM")] for p in folder.glob("*.zip.CHECKSUM") if p.stat().st_size > 0}
    for zip_path in sorted(p for p in folder.glob("*.zip") if p.name in checksums and p.name.startswith(f"{symbol}-1m-")):
        with zipfile.ZipFile(zip_path) as archive:
            csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError(f"context zip must contain one CSV: {zip_path.name}")
            with archive.open(csv_names[0]) as raw:
                reader = csv.reader(line.decode("utf-8") for line in raw)
                for row in reader:
                    if not row:
                        continue
                    candle = _parse_row(row)
                    if previous is not None and candle.open_time - previous != EXPECTED_STEP_MS:
                        raise ValueError(f"context gap detected for {symbol}")
                    previous = candle.open_time
                    candles.append(candle)
                    if max_candles is not None and len(candles) >= max_candles:
                        return candles
    return candles


def build_context_summary(symbol: str, candles: list[Candle], *, lookback: int = 60) -> list[dict[str, Any]]:
    if symbol not in CONTEXT_SYMBOLS:
        raise ValueError("context summary only supports context symbols")
    rows: list[dict[str, Any]] = []
    for index, candle in enumerate(candles):
        reference = candles[max(0, index - lookback)].close
        history = candles[max(0, index - lookback + 1) : index + 1]
        avg_close = sum(c.close for c in history) / len(history) if history else candle.close
        rows.append(
            {
                "symbol": symbol,
                "open_time": candle.open_time,
                "context_return": (candle.close / reference - 1) if reference else 0.0,
                "context_trend": candle.close - avg_close,
                "may_trigger_trade": False,
            }
        )
    return rows
