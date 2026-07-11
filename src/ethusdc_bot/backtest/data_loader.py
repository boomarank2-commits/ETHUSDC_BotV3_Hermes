"""Read-only Binance Spot 1m ZIP loaders for ETHUSDC and context markets.

ETHUSDC remains the only tradable symbol. BTCUSDC and ETHBTC are accepted only
as context data and this module has no strategy, account, key or order path.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final
import zipfile

from ethusdc_bot.path_safety import is_path_within


TRADE_SYMBOL: Final = "ETHUSDC"
CONTEXT_SYMBOLS: Final = ("BTCUSDC", "ETHBTC")
ALLOWED_KLINE_SYMBOLS: Final = (TRADE_SYMBOL, *CONTEXT_SYMBOLS)
SYMBOL: Final = TRADE_SYMBOL  # Backward-compatible public constant.
INTERVAL: Final = "1m"
EXPECTED_STEP_MS: Final = 60_000
DEFAULT_RAW_ROOT = Path("C:/TradingBot/data/ETHUSDC_BotV3_Hermes")


class DataLoadError(ValueError):
    """Raised when local public market data is missing, unsafe, or invalid."""


@dataclass(frozen=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class AlignedMarketCandles:
    """Exactly timestamp-aligned ETHUSDC and context candle sequences."""

    ethusdc: tuple[Candle, ...]
    btcusdc: tuple[Candle, ...]
    ethbtc: tuple[Candle, ...]

    @property
    def open_times(self) -> tuple[int, ...]:
        return tuple(candle.open_time for candle in self.ethusdc)

    @property
    def candle_count(self) -> int:
        return len(self.ethusdc)

    def context_for(self, symbol: str) -> tuple[Candle, ...]:
        normalized = _validate_context_symbol(symbol)
        return self.btcusdc if normalized == "BTCUSDC" else self.ethbtc


def load_ethusdc_1m_candles(
    raw_root: str | Path = DEFAULT_RAW_ROOT,
    *,
    start_day: date | str | None = None,
    end_day: date | str | None = None,
    max_candles: int | None = None,
) -> list[Candle]:
    """Load deterministic ETHUSDC 1m candles from local public ZIP pairs."""

    return load_symbol_1m_candles(
        raw_root,
        TRADE_SYMBOL,
        start_day=start_day,
        end_day=end_day,
        max_candles=max_candles,
    )


def load_context_1m_candles(
    raw_root: str | Path,
    symbol: str,
    *,
    start_day: date | str | None = None,
    end_day: date | str | None = None,
    max_candles: int | None = None,
) -> list[Candle]:
    """Load one permitted context symbol without granting trading semantics."""

    normalized = _validate_context_symbol(symbol)
    return load_symbol_1m_candles(
        raw_root,
        normalized,
        start_day=start_day,
        end_day=end_day,
        max_candles=max_candles,
    )


def load_symbol_1m_candles(
    raw_root: str | Path,
    symbol: str,
    *,
    start_day: date | str | None = None,
    end_day: date | str | None = None,
    max_candles: int | None = None,
) -> list[Candle]:
    """Load one allowlisted Binance Spot 1m symbol from ZIP/CHECKSUM pairs.

    The loader is strictly read-only. The symbol controls only the public data
    folder and file-name validation; it never grants order or trade permission.
    """

    normalized = _validate_allowed_symbol(symbol)
    root = _validate_raw_root(Path(raw_root))
    folder = root / "raw" / "binance" / "spot" / normalized / "klines" / INTERVAL
    if not folder.exists():
        raise DataLoadError(f"{normalized} 1m kline folder missing: {folder}")
    start = date.fromisoformat(start_day) if isinstance(start_day, str) else start_day
    end = date.fromisoformat(end_day) if isinstance(end_day, str) else end_day
    if start is not None and end is not None and end < start:
        raise DataLoadError("end_day must not precede start_day")
    if max_candles is not None and (type(max_candles) is not int or max_candles <= 0):
        raise DataLoadError("max_candles must be a positive integer")

    candles: list[Candle] = []
    seen: set[int] = set()
    previous: int | None = None
    zip_files = _paired_zip_files(folder, normalized)
    if not zip_files:
        raise DataLoadError(f"No {normalized} 1m ZIP/CHECKSUM pairs found")
    for zip_path in zip_files:
        day = _day_from_name(zip_path.name)
        if start and day and day < start:
            continue
        if end and day and day > end:
            continue
        for candle in _read_zip(zip_path, normalized):
            if candle.open_time in seen:
                raise DataLoadError(
                    f"duplicate {normalized} open_time detected: {candle.open_time}"
                )
            if previous is not None and candle.open_time - previous != EXPECTED_STEP_MS:
                raise DataLoadError(
                    f"gap or non-1m step detected for {normalized} after {previous}"
                )
            seen.add(candle.open_time)
            candles.append(candle)
            previous = candle.open_time
            if max_candles is not None and len(candles) >= max_candles:
                return candles
    if not candles:
        raise DataLoadError(f"No {normalized} 1m candles loaded for requested window")
    return candles


def load_aligned_market_candles(
    raw_root: str | Path = DEFAULT_RAW_ROOT,
    *,
    start_day: date | str | None = None,
    end_day: date | str | None = None,
    max_candles: int | None = None,
) -> AlignedMarketCandles:
    """Load and require exact ETHUSDC/BTCUSDC/ETHBTC timestamp alignment."""

    ethusdc = load_ethusdc_1m_candles(
        raw_root,
        start_day=start_day,
        end_day=end_day,
        max_candles=max_candles,
    )
    btcusdc = load_context_1m_candles(
        raw_root,
        "BTCUSDC",
        start_day=start_day,
        end_day=end_day,
        max_candles=max_candles,
    )
    ethbtc = load_context_1m_candles(
        raw_root,
        "ETHBTC",
        start_day=start_day,
        end_day=end_day,
        max_candles=max_candles,
    )
    return align_market_candles(ethusdc, btcusdc, ethbtc)


def align_market_candles(
    ethusdc: list[Candle] | tuple[Candle, ...],
    btcusdc: list[Candle] | tuple[Candle, ...],
    ethbtc: list[Candle] | tuple[Candle, ...],
) -> AlignedMarketCandles:
    """Validate exact one-to-one UTC-minute alignment without filling gaps."""

    series = {
        "ETHUSDC": tuple(ethusdc),
        "BTCUSDC": tuple(btcusdc),
        "ETHBTC": tuple(ethbtc),
    }
    for symbol, candles in series.items():
        _validate_candle_sequence(symbol, candles)
    lengths = {symbol: len(candles) for symbol, candles in series.items()}
    if len(set(lengths.values())) != 1:
        raise DataLoadError(f"context candle counts are not aligned: {lengths}")

    reference = tuple(candle.open_time for candle in series[TRADE_SYMBOL])
    for symbol in CONTEXT_SYMBOLS:
        open_times = tuple(candle.open_time for candle in series[symbol])
        if open_times != reference:
            mismatch = next(
                (
                    index
                    for index, (expected, actual) in enumerate(zip(reference, open_times))
                    if expected != actual
                ),
                None,
            )
            raise DataLoadError(
                f"{symbol} timestamps are not exactly aligned with ETHUSDC"
                + (f" at index {mismatch}" if mismatch is not None else "")
            )
    return AlignedMarketCandles(
        ethusdc=series["ETHUSDC"],
        btcusdc=series["BTCUSDC"],
        ethbtc=series["ETHBTC"],
    )


def _paired_zip_files(folder: Path, symbol: str) -> list[Path]:
    zips = [
        path
        for path in folder.iterdir()
        if path.is_file() and path.name.endswith(".zip")
    ]
    checksum_names = {
        path.name[: -len(".CHECKSUM")]
        for path in folder.iterdir()
        if path.is_file()
        and path.name.endswith(".zip.CHECKSUM")
        and path.stat().st_size > 0
    }
    paired = [
        path
        for path in zips
        if path.name in checksum_names and path.stat().st_size > 0
    ]
    wrong = [
        path.name
        for path in zips
        if not path.name.startswith(f"{symbol}-{INTERVAL}-")
    ]
    if wrong:
        raise DataLoadError(
            f"Only {symbol} 1m ZIPs are allowed in this folder; wrong files: {wrong[:3]}"
        )
    return sorted(paired)


def _read_zip(zip_path: Path, symbol: str) -> list[Candle]:
    if not zip_path.name.startswith(f"{symbol}-{INTERVAL}-"):
        raise DataLoadError(
            f"ZIP file must identify {symbol} {INTERVAL}: {zip_path.name}"
        )
    with zipfile.ZipFile(zip_path) as archive:
        csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
        if len(csv_names) != 1:
            raise DataLoadError(f"ZIP must contain exactly one CSV: {zip_path.name}")
        inner = csv_names[0]
        if not Path(inner).name.startswith(f"{symbol}-{INTERVAL}-"):
            raise DataLoadError(f"CSV must identify {symbol} {INTERVAL}: {inner}")
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
                    raise DataLoadError(
                        f"duplicate open_time inside {zip_path.name}"
                    )
                if (
                    previous is not None
                    and candle.open_time - previous != EXPECTED_STEP_MS
                ):
                    raise DataLoadError(
                        f"gap or non-1m step inside {zip_path.name}"
                    )
                seen.add(candle.open_time)
                previous = candle.open_time
                rows.append(candle)
        return rows


def _parse_row(row: list[str]) -> Candle:
    try:
        open_time = int(row[0])
        if open_time > 9_999_999_999_999:
            open_time //= 1000
        candle = Candle(
            open_time=open_time,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
    except (IndexError, TypeError, ValueError) as exc:
        raise DataLoadError(
            "Invalid kline row; expected Binance kline columns"
        ) from exc
    if candle.open_time < 0:
        raise DataLoadError("kline open_time must be non-negative")
    if min(candle.open, candle.high, candle.low, candle.close) <= 0:
        raise DataLoadError("kline prices must be positive")
    if candle.volume < 0:
        raise DataLoadError("kline volume must be non-negative")
    if candle.high < max(candle.open, candle.close) or candle.low > min(
        candle.open, candle.close
    ):
        raise DataLoadError("kline OHLC values are inconsistent")
    return candle


def _validate_raw_root(path: Path) -> Path:
    candidate = path.resolve()
    repository_root = Path.cwd().resolve()
    if is_path_within(candidate, repository_root):
        raise DataLoadError("Backtest loader refuses repository-local raw data paths")
    return candidate


def _validate_allowed_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise DataLoadError("symbol must be a string")
    normalized = symbol.strip().upper()
    if normalized not in ALLOWED_KLINE_SYMBOLS:
        raise DataLoadError(
            f"symbol must be one of {ALLOWED_KLINE_SYMBOLS}; received {symbol!r}"
        )
    return normalized


def _validate_context_symbol(symbol: str) -> str:
    normalized = _validate_allowed_symbol(symbol)
    if normalized not in CONTEXT_SYMBOLS:
        raise DataLoadError(
            f"context symbol must be one of {CONTEXT_SYMBOLS}; received {symbol!r}"
        )
    return normalized


def _validate_candle_sequence(symbol: str, candles: tuple[Candle, ...]) -> None:
    if not candles:
        raise DataLoadError(f"{symbol} candle sequence must not be empty")
    previous: int | None = None
    seen: set[int] = set()
    for candle in candles:
        if not isinstance(candle, Candle):
            raise DataLoadError(f"{symbol} sequence contains a non-Candle value")
        if candle.open_time in seen:
            raise DataLoadError(f"duplicate {symbol} alignment open_time")
        if previous is not None and candle.open_time - previous != EXPECTED_STEP_MS:
            raise DataLoadError(f"gap in {symbol} alignment sequence after {previous}")
        seen.add(candle.open_time)
        previous = candle.open_time


def _day_from_name(name: str) -> date | None:
    tokens = name.replace("_", "-").split("-")
    for index in range(len(tokens) - 2):
        try:
            return date.fromisoformat("-".join(tokens[index : index + 3])[:10])
        except ValueError:
            continue
    return None


__all__ = [
    "ALLOWED_KLINE_SYMBOLS",
    "CONTEXT_SYMBOLS",
    "TRADE_SYMBOL",
    "AlignedMarketCandles",
    "Candle",
    "DataLoadError",
    "DEFAULT_RAW_ROOT",
    "EXPECTED_STEP_MS",
    "INTERVAL",
    "SYMBOL",
    "align_market_candles",
    "load_aligned_market_candles",
    "load_context_1m_candles",
    "load_ethusdc_1m_candles",
    "load_symbol_1m_candles",
]
