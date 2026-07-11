"""Timestamped mark-to-market equity helpers for offline backtests."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import isclose


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """Liquidation-value equity observed at one UTC timestamp."""

    timestamp_ms: int
    equity_usdc: float


def max_drawdown_usdc(points: Sequence[EquityPoint]) -> float:
    """Return peak-to-trough drawdown from a chronological equity curve."""

    if not points:
        return 0.0
    _assert_chronological(points)
    peak = float("-inf")
    maximum = 0.0
    for point in points:
        equity = float(point.equity_usdc)
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return round(maximum, 10)


def max_underwater_calendar_days(points: Sequence[EquityPoint]) -> int:
    """Count the longest run of UTC dates with equity below its prior peak."""

    if not points:
        return 0
    _assert_chronological(points)
    peak = float(points[0].equity_usdc)
    underwater_dates: set[date] = set()
    maximum = 0
    for point in points[1:]:
        equity = float(point.equity_usdc)
        if equity >= peak:
            maximum = max(maximum, len(underwater_dates))
            underwater_dates.clear()
            peak = equity
            continue
        underwater_dates.add(datetime.fromtimestamp(point.timestamp_ms / 1000, tz=UTC).date())
    return max(maximum, len(underwater_dates))


def chain_equity_curves(curves: Sequence[Sequence[EquityPoint]]) -> tuple[EquityPoint, ...]:
    """Chain zero-based fold curves without resetting equity between folds."""

    chained: list[EquityPoint] = []
    offset = 0.0
    for curve in curves:
        if not curve:
            continue
        _assert_chronological(curve)
        if not isclose(float(curve[0].equity_usdc), 0.0, rel_tol=0.0, abs_tol=1e-8):
            raise ValueError("Each fold equity curve must start at zero")
        source = curve if not chained else curve[1:]
        for point in source:
            if chained and point.timestamp_ms <= chained[-1].timestamp_ms:
                raise ValueError("Fold equity curves must be strictly chronological and non-overlapping")
            chained.append(
                EquityPoint(
                    timestamp_ms=point.timestamp_ms,
                    equity_usdc=round(offset + float(point.equity_usdc), 10),
                )
            )
        offset = round(offset + float(curve[-1].equity_usdc), 10)
    return tuple(chained)


def _assert_chronological(points: Sequence[EquityPoint]) -> None:
    previous: int | None = None
    for point in points:
        if previous is not None and point.timestamp_ms <= previous:
            raise ValueError("Equity points must have strictly increasing timestamps")
        previous = point.timestamp_ms
