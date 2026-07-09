"""Read-only ETHUSDC 1m Binance ZIP data loader."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import zipfile

SYMBOL = "ETHUSDC"
INTERVAL = "1m"
EXPECTED_STEP_MS = 60_000
DEFAULT_RAW_ROOT = Path("C:/TradingBot/data/ETHUSDC_BotV3_Hermes")


class DataLoadError(ValueError):
    """Raised when local backtest data is missing, unsafe, or invalid."""


@dataclass(frozen=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def load_ethusdc_1m_candles(
    raw_root: str | Path = DEFAULT_RAW_ROOT,
    *,
    start_day: date | str | None = None,
    end_day: date | str | None = None,
    max_candles: int | None = None,
) -> list[Candle]:
    """Load deterministic ETHUSDC 1m candles from local public ZIP/CHECKSUM pairs.

    The loader is read-only. It rejects repository-local raw-data paths and only
    returns no-lookahead candle fields needed by the first backtest engine.
    """

    root = _validate_raw_root(Path(raw_root))
    folder = root / "raw" / "binance" / "spot" / SYMBOL / "klines" / INTERVAL
    if not folder.exists():
        raise DataLoadError(f"ETHUSDC 1m kline folder missing: {folder}")
    start = date.fromisoformat(start_day) if isinstance(start_day, str) else start_day
    end = date.fromisoformat(end_day) if isinstance(end_day, str) else end_day
    candles: list[Candle] = []
    seen: set[int] = set()
    previous: int | None = None
    zip_files = _paired_zip_files(folder)
    if not zip_files:
        raise DataLoadError("No ETHUSDC 1m ZIP/CHECKSUM pairs found")
    for zip_path in zip_files:
        day = _day_from_name(zip_path.name)
        if start and day and day < start:
            continue
        if end and day and day > end:
            continue
        for candle in _read_zip(zip_path):
            if candle.open_time in seen:
                raise DataLoadError(f"duplicate open_time detected: {candle.open_time}")
            if previous is not None and candle.open_time - previous != EXPECTED_STEP_MS:
                raise DataLoadError(f"gap or non-1m step detected after {previous}")
            seen.add(candle.open_time)
            candles.append(candle)
            previous = candle.open_time
            if max_candles is not None and len(candles) >= max_candles:
                return candles
    if not candles:
        raise DataLoadError("No ETHUSDC 1m candles loaded for requested window")
    return candles


def _paired_zip_files(folder: Path) -> list[Path]:
    zips = [path for path in folder.iterdir() if path.is_file() and path.name.endswith(".zip")]
    checksum_names = {path.name[: -len(".CHECKSUM")] for path in folder.iterdir() if path.is_file() and path.name.endswith(".zip.CHECKSUM") and path.stat().st_size > 0}
    paired = [path for path in zips if path.name in checksum_names and path.stat().st_size > 0]
    wrong = [path.name for path in zips if not path.name.startswith(f"{SYMBOL}-{INTERVAL}-")]
    if wrong:
        raise DataLoadError(f"Only ETHUSDC 1m ZIPs are allowed; wrong symbol files: {wrong[:3]}")
    return sorted(paired)


def _read_zip(zip_path: Path) -> list[Candle]:
    if not zip_path.name.startswith(f"{SYMBOL}-{INTERVAL}-"):
        raise DataLoadError(f"ZIP file must identify ETHUSDC 1m: {zip_path.name}")
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(csv_names) != 1:
            raise DataLoadError(f"ZIP must contain exactly one CSV: {zip_path.name}")
        inner = csv_names[0]
        if not Path(inner).name.startswith(f"{SYMBOL}-{INTERVAL}-"):
            raise DataLoadError(f"CSV must identify ETHUSDC 1m: {inner}")
        rows: list[Candle] = []
        with archive.open(inner) as raw:
            reader = csv.reader(line.decode("utf-8") for line in raw)
            previous: int | None = None
            seen: set[int] = set()
            for row in reader:
                if not row:
                    continue
                candle = _parse_row(row)
                if candle.open_time in seen:
                    raise DataLoadError(f"duplicate open_time inside {zip_path.name}")
                if previous is not None and candle.open_time - previous != EXPECTED_STEP_MS:
                    raise DataLoadError(f"gap or non-1m step inside {zip_path.name}")
                seen.add(candle.open_time)
                previous = candle.open_time
                rows.append(candle)
        return rows


def _parse_row(row: list[str]) -> Candle:
    try:
        open_time = int(row[0])
        if open_time > 9_999_999_999_999:
            open_time //= 1000
        return Candle(
            open_time=open_time,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
    except (IndexError, TypeError, ValueError) as exc:
        raise DataLoadError("Invalid kline row; expected Binance kline columns") from exc


def _validate_raw_root(path: Path) -> Path:
    candidate = path.resolve()
    cwd = Path.cwd().resolve()
    try:
        candidate.relative_to(cwd)
    except ValueError:
        return candidate
    # Explicitly block repo-local raw market data, while allowing pytest tmp dirs outside the repo.
    forbidden_names = {"data", "raw", "market_data"}
    if any(part in forbidden_names for part in candidate.relative_to(cwd).parts):
        raise DataLoadError("Backtest loader refuses repository-local raw data paths")
    raise DataLoadError("Backtest loader refuses repository-local raw data paths")


def _day_from_name(name: str) -> date | None:
    tokens = name.replace("_", "-").split("-")
    for index in range(len(tokens) - 2):
        try:
            return date.fromisoformat("-".join(tokens[index : index + 3])[:10])
        except ValueError:
            continue
    return None
