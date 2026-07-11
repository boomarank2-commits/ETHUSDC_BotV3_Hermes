"""Deterministic proof producers for QualityGateV1 robustness evidence.

The functions in this module only reduce caller-supplied, training-safe data.
They do not load market data, select candidates, or inspect a sealed holdout.
Every timestamp is checked against one explicit half-open UTC window so rows
outside that window cannot silently leak into an evidence summary.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import fsum, isclose, isfinite
from typing import Any

from ethusdc_bot.backtest.equity import (
    EquityPoint,
    max_drawdown_usdc,
    max_underwater_calendar_days,
)
from ethusdc_bot.backtest.simulator import Trade


DAY_MS = 86_400_000
FAIL_CLOSED_RATIO_SENTINEL = -1.0
ZERO_DENOMINATOR_POLICY_ID = "finite_negative_one_fail_closed_v1"
ROLLING_EVIDENCE_ALGORITHM_ID = (
    "quality_gate_v1_rolling_concentration_mtm_utc_window_v1"
)
TEMPORAL_EVIDENCE_ALGORITHM_ID = "quality_gate_v1_temporal_utc_exit_calendar_v1"
NO_TRADE_GAP_ALGORITHM_ID = "consecutive_empty_utc_calendar_days_edges_included_v1"


@dataclass(frozen=True, slots=True)
class _EvidenceTrade:
    symbol: str
    side: str
    entry_time_ms: int
    exit_time_ms: int
    net_profit_usdc: float
    lot_id: str | None


def build_rolling_evidence(
    window_start_ms: int,
    window_end_ms_exclusive: int,
    trades: Sequence[Trade | Mapping[str, Any]],
    equity_points: Sequence[EquityPoint | Mapping[str, Any]],
) -> dict[str, Any]:
    """Derive rolling drawdown and concentration evidence from raw proof rows.

    The mark-to-market curve must start at the window boundary with zero
    equity, end at ``window_end_ms_exclusive - 1``, and finish at the sum of
    closed-trade net P&L.  This rejects truncated curves and mixed-window
    ledgers instead of manufacturing apparently safe drawdown evidence.
    """

    window = _validate_window(window_start_ms, window_end_ms_exclusive)
    normalized_trades = _normalize_trades(trades, *window)
    curve = _normalize_equity_points(equity_points, *window)
    total_net = fsum(trade.net_profit_usdc for trade in normalized_trades)
    if not isclose(
        curve[-1].equity_usdc,
        total_net,
        rel_tol=1e-10,
        abs_tol=1e-8,
    ):
        raise ValueError(
            "final mark-to-market equity must equal the in-window closed-trade net P&L"
        )

    indexed_positive = [
        (index, trade)
        for index, trade in enumerate(normalized_trades)
        if trade.net_profit_usdc > 0
    ]
    ranked_positive = sorted(
        indexed_positive,
        key=lambda item: (
            -item[1].net_profit_usdc,
            item[1].exit_time_ms,
            item[1].entry_time_ms,
            item[1].lot_id or "",
            item[0],
        ),
    )
    positive_pnl_total = fsum(
        trade.net_profit_usdc for _, trade in indexed_positive
    )
    top_one_pnl = ranked_positive[0][1].net_profit_usdc if ranked_positive else 0.0
    top_five = ranked_positive[:5]
    top_five_indices = {index for index, _ in top_five}
    top_five_pnl = fsum(trade.net_profit_usdc for _, trade in top_five)

    sentinel_fields: list[str] = []
    if positive_pnl_total > 0:
        top_one_share = _round(top_one_pnl / positive_pnl_total)
        top_five_share = _round(top_five_pnl / positive_pnl_total)
    else:
        top_one_share = FAIL_CLOSED_RATIO_SENTINEL
        top_five_share = FAIL_CLOSED_RATIO_SENTINEL
        sentinel_fields.extend(
            ["top1_positive_pnl_share", "top5_positive_pnl_share"]
        )

    remaining = [
        trade
        for index, trade in enumerate(normalized_trades)
        if index not in top_five_indices
    ]
    remaining_net = fsum(trade.net_profit_usdc for trade in remaining)
    remaining_gross_profit = fsum(
        trade.net_profit_usdc
        for trade in remaining
        if trade.net_profit_usdc > 0
    )
    remaining_gross_loss = abs(
        fsum(
            trade.net_profit_usdc
            for trade in remaining
            if trade.net_profit_usdc < 0
        )
    )
    if remaining_gross_loss > 0:
        profit_factor_without_top_five = _round(
            remaining_gross_profit / remaining_gross_loss
        )
    else:
        # A mathematical infinity would not be strict JSON and would let an
        # insufficient denominator pass.  The explicit finite sentinel fails
        # the QualityGateV1 minimum-PF check instead.
        profit_factor_without_top_five = FAIL_CLOSED_RATIO_SENTINEL
        sentinel_fields.append("profit_factor_without_top5")

    trade_rows = _trade_proof_rows(normalized_trades)
    equity_rows = [
        {
            "timestamp_ms": point.timestamp_ms,
            "equity_usdc": _round(point.equity_usdc),
        }
        for point in curve
    ]
    return {
        "algorithm_id": ROLLING_EVIDENCE_ALGORITHM_ID,
        "drawdown_method": "mark_to_market",
        "max_drawdown_usdc": max_drawdown_usdc(curve),
        "max_underwater_days": max_underwater_calendar_days(curve),
        "top1_positive_pnl_share": top_one_share,
        "top5_positive_pnl_share": top_five_share,
        "net_without_top5_usdc": _round(remaining_net),
        "profit_factor_without_top5": profit_factor_without_top_five,
        "proof": {
            "window": _window_proof(*window),
            "trade_assignment": "closed_trades_with_entry_and_exit_inside_window",
            "trade_count": len(normalized_trades),
            "trade_rows": trade_rows,
            "equity_point_count": len(curve),
            "equity_rows": equity_rows,
            "equity_start_required_zero": True,
            "equity_endpoint_matches_trade_net": True,
            "positive_pnl_total_usdc": _round(positive_pnl_total),
            "top1_positive_pnl_usdc": _round(top_one_pnl),
            "top5_positive_pnl_usdc": _round(top_five_pnl),
            "top5_removed_trade_indices": sorted(top_five_indices),
            "remaining_gross_profit_usdc": _round(remaining_gross_profit),
            "remaining_gross_loss_usdc": _round(remaining_gross_loss),
            "zero_denominator_policy": {
                "algorithm_id": ZERO_DENOMINATOR_POLICY_ID,
                "sentinel": FAIL_CLOSED_RATIO_SENTINEL,
                "applied_fields": sorted(sentinel_fields),
                "reason": "undefined ratios must fail QualityGateV1 and remain strict-JSON finite",
            },
        },
    }


def build_temporal_evidence(
    window_start_ms: int,
    window_end_ms_exclusive: int,
    trades: Sequence[Trade | Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate every touched UTC month and quarter by trade exit time.

    Empty periods are retained.  ``max_no_trade_gap_days`` is the longest run
    of UTC calendar dates without an exit and includes runs touching either
    edge of the fixed window.
    """

    window = _validate_window(window_start_ms, window_end_ms_exclusive)
    normalized_trades = _normalize_trades(trades, *window)
    month_rows = _calendar_period_rows(normalized_trades, *window, kind="month")
    quarter_rows = _calendar_period_rows(
        normalized_trades, *window, kind="quarter"
    )
    no_trade_gaps = _no_trade_gap_rows(normalized_trades, *window)

    return {
        "algorithm_id": TEMPORAL_EVIDENCE_ALGORITHM_ID,
        "months_observed": len(month_rows),
        "positive_months": sum(1 for row in month_rows if row["positive"]),
        "active_months": sum(1 for row in month_rows if row["active"]),
        "max_no_trade_gap_days": max(
            (int(row["days"]) for row in no_trade_gaps), default=0
        ),
        "quarters_observed": len(quarter_rows),
        "positive_quarters": sum(1 for row in quarter_rows if row["positive"]),
        "min_quarter_trade_count": min(
            (int(row["trade_count"]) for row in quarter_rows), default=0
        ),
        "worst_month_net_usdc": min(
            (float(row["net_profit_usdc"]) for row in month_rows), default=0.0
        ),
        "proof": {
            "window": _window_proof(*window),
            "assignment_timestamp": "exit_time_utc",
            "empty_calendar_periods_included": True,
            "trade_count": len(normalized_trades),
            "trade_rows": _trade_proof_rows(normalized_trades),
            "month_rows": month_rows,
            "quarter_rows": quarter_rows,
            "no_trade_gap_algorithm_id": NO_TRADE_GAP_ALGORITHM_ID,
            "no_trade_gap_rows": no_trade_gaps,
        },
    }


def _validate_window(start_ms: int, end_ms: int) -> tuple[int, int]:
    if type(start_ms) is not int or type(end_ms) is not int:
        raise TypeError("UTC window boundaries must be integer epoch milliseconds")
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError("UTC window must be non-negative and non-empty")
    if start_ms % DAY_MS != 0 or end_ms % DAY_MS != 0:
        raise ValueError("UTC window boundaries must align to UTC midnight")
    _utc_datetime(start_ms)
    _utc_datetime(end_ms - 1)
    return start_ms, end_ms


def _normalize_trades(
    trades: Sequence[Trade | Mapping[str, Any]],
    start_ms: int,
    end_ms: int,
) -> tuple[_EvidenceTrade, ...]:
    if isinstance(trades, (str, bytes)) or not isinstance(trades, Sequence):
        raise TypeError("trades must be a sequence of Trade values or mappings")
    normalized: list[_EvidenceTrade] = []
    provided_lot_ids: set[str] = set()
    for index, source in enumerate(trades):
        if isinstance(source, Trade):
            values: Mapping[str, Any] = vars(source)
        elif isinstance(source, Mapping):
            values = source
        else:
            raise TypeError(f"trades[{index}] must be a Trade value or mapping")
        symbol = _required_string(values, "symbol", f"trades[{index}]")
        side = _required_string(values, "side", f"trades[{index}]")
        if symbol != "ETHUSDC":
            raise ValueError(f"trades[{index}].symbol must be ETHUSDC")
        if side != "LONG":
            raise ValueError(f"trades[{index}].side must be LONG")
        entry_time = _required_timestamp(values, "entry_time", f"trades[{index}]")
        exit_time = _required_timestamp(values, "exit_time", f"trades[{index}]")
        if not (start_ms <= entry_time <= exit_time < end_ms):
            raise ValueError(
                f"trades[{index}] entry and exit must both be inside the fixed UTC window"
            )
        net = _required_finite_number(
            values, "net_profit_usdc", f"trades[{index}]"
        )
        raw_lot_id = values.get("lot_id")
        if raw_lot_id is None or raw_lot_id == "":
            lot_id = None
        elif isinstance(raw_lot_id, str):
            lot_id = raw_lot_id
            if lot_id in provided_lot_ids:
                raise ValueError(f"duplicate lot_id in evidence ledger: {lot_id}")
            provided_lot_ids.add(lot_id)
        else:
            raise TypeError(f"trades[{index}].lot_id must be a string when present")
        normalized.append(
            _EvidenceTrade(
                symbol=symbol,
                side=side,
                entry_time_ms=entry_time,
                exit_time_ms=exit_time,
                net_profit_usdc=net,
                lot_id=lot_id,
            )
        )
    return tuple(
        sorted(
            normalized,
            key=lambda trade: (
                trade.exit_time_ms,
                trade.entry_time_ms,
                trade.lot_id or "",
                trade.net_profit_usdc,
            ),
        )
    )


def _normalize_equity_points(
    points: Sequence[EquityPoint | Mapping[str, Any]],
    start_ms: int,
    end_ms: int,
) -> tuple[EquityPoint, ...]:
    if isinstance(points, (str, bytes)) or not isinstance(points, Sequence):
        raise TypeError("equity_points must be a sequence of EquityPoint values or mappings")
    curve: list[EquityPoint] = []
    previous_timestamp: int | None = None
    for index, source in enumerate(points):
        if isinstance(source, EquityPoint):
            values: Mapping[str, Any] = {
                "timestamp_ms": source.timestamp_ms,
                "equity_usdc": source.equity_usdc,
            }
        elif isinstance(source, Mapping):
            values = source
        else:
            raise TypeError(
                f"equity_points[{index}] must be an EquityPoint value or mapping"
            )
        timestamp = _required_timestamp(
            values, "timestamp_ms", f"equity_points[{index}]"
        )
        equity = _required_finite_number(
            values, "equity_usdc", f"equity_points[{index}]"
        )
        if not start_ms <= timestamp < end_ms:
            raise ValueError(f"equity_points[{index}] is outside the fixed UTC window")
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ValueError("equity points must be strictly chronological")
        previous_timestamp = timestamp
        curve.append(EquityPoint(timestamp_ms=timestamp, equity_usdc=equity))
    if len(curve) < 2:
        raise ValueError("mark-to-market evidence needs at least both window endpoints")
    if curve[0].timestamp_ms != start_ms:
        raise ValueError("mark-to-market evidence must start at window_start_ms")
    if curve[-1].timestamp_ms != end_ms - 1:
        raise ValueError(
            "mark-to-market evidence must end at window_end_ms_exclusive - 1"
        )
    if not isclose(curve[0].equity_usdc, 0.0, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError("mark-to-market evidence must start at zero equity")
    return tuple(curve)


def _calendar_period_rows(
    trades: tuple[_EvidenceTrade, ...],
    start_ms: int,
    end_ms: int,
    *,
    kind: str,
) -> list[dict[str, Any]]:
    if kind == "month":
        period_start = _month_start(_utc_datetime(start_ms))
        final_period_start = _month_start(_utc_datetime(end_ms - 1))
        next_period = _next_month
        label = lambda value: value.strftime("%Y-%m")
    elif kind == "quarter":
        period_start = _quarter_start(_utc_datetime(start_ms))
        final_period_start = _quarter_start(_utc_datetime(end_ms - 1))
        next_period = _next_quarter
        label = lambda value: f"{value.year}-Q{((value.month - 1) // 3) + 1}"
    else:  # pragma: no cover - private caller fixes this at development time.
        raise ValueError("kind must be month or quarter")

    rows: list[dict[str, Any]] = []
    while period_start <= final_period_start:
        period_end = next_period(period_start)
        observed_start = max(start_ms, _to_ms(period_start))
        observed_end = min(end_ms, _to_ms(period_end))
        period_trades = [
            trade
            for trade in trades
            if observed_start <= trade.exit_time_ms < observed_end
        ]
        net = _round(fsum(trade.net_profit_usdc for trade in period_trades))
        rows.append(
            {
                "period": label(period_start),
                "observed_start_ms": observed_start,
                "observed_end_ms_exclusive": observed_end,
                "trade_count": len(period_trades),
                "net_profit_usdc": net,
                "active": bool(period_trades),
                "positive": net > 0,
            }
        )
        period_start = period_end
    return rows


def _no_trade_gap_rows(
    trades: tuple[_EvidenceTrade, ...], start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    first_day = _utc_datetime(start_ms).date()
    last_day = _utc_datetime(end_ms - 1).date()
    active_days = {_utc_datetime(trade.exit_time_ms).date() for trade in trades}
    gaps: list[dict[str, Any]] = []
    cursor = first_day
    gap_start: date | None = None
    while cursor <= last_day:
        if cursor not in active_days and gap_start is None:
            gap_start = cursor
        if cursor in active_days and gap_start is not None:
            gaps.append(_gap_row(gap_start, cursor - timedelta(days=1), first_day, last_day))
            gap_start = None
        cursor += timedelta(days=1)
    if gap_start is not None:
        gaps.append(_gap_row(gap_start, last_day, first_day, last_day))
    return gaps


def _gap_row(start: date, end: date, first: date, last: date) -> dict[str, Any]:
    return {
        "start_utc_date": start.isoformat(),
        "end_utc_date": end.isoformat(),
        "days": (end - start).days + 1,
        "touches_window_start": start == first,
        "touches_window_end": end == last,
    }


def _trade_proof_rows(trades: tuple[_EvidenceTrade, ...]) -> list[dict[str, Any]]:
    return [
        {
            "trade_index": index,
            "symbol": trade.symbol,
            "side": trade.side,
            "entry_time_ms": trade.entry_time_ms,
            "exit_time_ms": trade.exit_time_ms,
            "net_profit_usdc": _round(trade.net_profit_usdc),
            "lot_id": trade.lot_id,
        }
        for index, trade in enumerate(trades)
    ]


def _window_proof(start_ms: int, end_ms: int) -> dict[str, Any]:
    return {
        "interval": "[start_ms,end_ms_exclusive)",
        "timezone": "UTC",
        "start_ms": start_ms,
        "end_ms_exclusive": end_ms,
        "start_utc_date": _utc_datetime(start_ms).date().isoformat(),
        "end_utc_date_exclusive": _utc_datetime(end_ms).date().isoformat(),
        "calendar_days": (end_ms - start_ms) // DAY_MS,
    }


def _required_string(values: Mapping[str, Any], field: str, path: str) -> str:
    value = values.get(field)
    if not isinstance(value, str) or not value:
        raise TypeError(f"{path}.{field} must be a non-empty string")
    return value


def _required_timestamp(values: Mapping[str, Any], field: str, path: str) -> int:
    value = values.get(field)
    if type(value) is not int or value < 0:
        raise TypeError(f"{path}.{field} must be a non-negative integer timestamp")
    _utc_datetime(value)
    return value


def _required_finite_number(
    values: Mapping[str, Any], field: str, path: str
) -> float:
    value = values.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{path}.{field} must be numeric")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{path}.{field} must be finite")
    return number


def _utc_datetime(timestamp_ms: int) -> datetime:
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("timestamp is outside the supported UTC datetime range") from exc


def _month_start(value: datetime) -> datetime:
    return datetime(value.year, value.month, 1, tzinfo=UTC)


def _quarter_start(value: datetime) -> datetime:
    month = ((value.month - 1) // 3) * 3 + 1
    return datetime(value.year, month, 1, tzinfo=UTC)


def _next_month(value: datetime) -> datetime:
    if value.month == 12:
        return datetime(value.year + 1, 1, 1, tzinfo=UTC)
    return datetime(value.year, value.month + 1, 1, tzinfo=UTC)


def _next_quarter(value: datetime) -> datetime:
    result = value
    for _ in range(3):
        result = _next_month(result)
    return result


def _to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _round(value: float) -> float:
    return round(float(value), 10)


__all__ = [
    "FAIL_CLOSED_RATIO_SENTINEL",
    "NO_TRADE_GAP_ALGORITHM_ID",
    "ROLLING_EVIDENCE_ALGORITHM_ID",
    "TEMPORAL_EVIDENCE_ALGORITHM_ID",
    "ZERO_DENOMINATOR_POLICY_ID",
    "build_rolling_evidence",
    "build_temporal_evidence",
]
