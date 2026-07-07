"""Pure local data audit helpers.

The functions in this module inspect caller-provided artificial or already-loaded
records only. They do not read market data files, download data, call Binance,
run a strategy, create trades, or produce backtest metrics.
"""

from collections.abc import Mapping, Sequence
from typing import Any


BLOCKED = "blocked"
INCOMPLETE = "incomplete"
USABLE = "usable"


def audit_kline_records(
    records: Sequence[Mapping[str, Any]], symbol: str, interval_seconds: int
) -> dict[str, Any]:
    """Audit in-memory kline records for symbol, order, duplicates, and gaps.

    Expected record shape is intentionally small and explicit:
    - symbol: trading/context symbol string
    - open_time_utc: integer UTC timestamp in seconds
    - interval_seconds: integer kline interval in seconds
    """

    expected_interval_valid = isinstance(interval_seconds, int) and interval_seconds > 0
    open_times: list[int] = []
    symbol_validated = bool(symbol) and isinstance(symbol, str)
    interval_validated = expected_interval_valid
    malformed_rows = 0

    for record in records:
        if record.get("symbol") != symbol:
            symbol_validated = False
        if record.get("interval_seconds") != interval_seconds:
            interval_validated = False

        open_time = record.get("open_time_utc")
        if type(open_time) is int:
            open_times.append(open_time)
        else:
            malformed_rows += 1

    duplicate_rows = len(open_times) - len(set(open_times))
    sorted_ascending = all(
        earlier < later for earlier, later in zip(open_times, open_times[1:])
    )

    gap_count = 0
    max_gap_seconds = 0
    if expected_interval_valid and sorted_ascending:
        for earlier, later in zip(open_times, open_times[1:]):
            delta = later - earlier
            if delta > interval_seconds:
                gap_count += (delta // interval_seconds) - 1
                max_gap_seconds = max(max_gap_seconds, delta)

    has_gaps = gap_count > 0
    quality_status = _quality_status(
        symbol_validated=symbol_validated,
        interval_validated=interval_validated,
        malformed_rows=malformed_rows,
        duplicate_rows=duplicate_rows,
        sorted_ascending=sorted_ascending,
        has_gaps=has_gaps,
    )

    return {
        "symbol": symbol,
        "interval_seconds": interval_seconds,
        "records_checked": len(records),
        "malformed_rows": malformed_rows,
        "symbol_validated": symbol_validated,
        "interval_validated": interval_validated,
        "sorted_ascending": sorted_ascending,
        "has_gaps": has_gaps,
        "gap_count": gap_count,
        "max_gap_seconds": max_gap_seconds,
        "duplicate_rows": duplicate_rows,
        "quality_status": quality_status,
    }


def _quality_status(
    *,
    symbol_validated: bool,
    interval_validated: bool,
    malformed_rows: int,
    duplicate_rows: int,
    sorted_ascending: bool,
    has_gaps: bool,
) -> str:
    if (
        not symbol_validated
        or not interval_validated
        or malformed_rows
        or duplicate_rows
        or not sorted_ascending
    ):
        return BLOCKED
    if has_gaps:
        return INCOMPLETE
    return USABLE
