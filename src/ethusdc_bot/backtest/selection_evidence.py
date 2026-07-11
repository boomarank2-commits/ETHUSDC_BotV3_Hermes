"""Deterministic selection-only evidence producers for quality_gate_v1.

All functions operate on caller-supplied training/validation/WFV data.  This
module has no loader, report, audit, holdout, account, key or order dependency.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from math import isfinite
from statistics import median
from typing import Any, Protocol

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.quality_gates import QUALITY_GATE_V1, QualityGateV1
from ethusdc_bot.backtest.simulator import (
    SimulationResult,
    StrategyCandidate,
    Trade,
    simulate_strategy,
)


REGIME_DEFINITION = "trend_sign_x_training_median_volatility"
REGIME_THRESHOLD_SOURCE = "training_only"
REGIME_LABELS = ("down_low", "down_high", "up_low", "up_high")
STRUCTURAL_PARAMETER_KEYS = {
    "symbol",
    "side",
    "base_family",
    "context_symbol",
    "context_rule",
}
SESSION_PARAMETER_KEYS = {"session_start_hour", "session_end_hour"}
STRICTLY_POSITIVE_PARAMETER_KEYS = {
    "lookback",
    "trend_lookback",
    "volatility_lookback",
    "max_hold_minutes",
    "take_profit_bps",
    "stop_loss_bps",
    "max_vol_bps",
    "min_expected_move_bps",
}


class ResultLike(Protocol):
    trades: Sequence[Trade]
    max_drawdown_usdc: float
    max_underwater_days: int
    drawdown_method: str


@dataclass(frozen=True)
class NeighborEvaluation:
    parameter: str
    direction: str
    value: float | int
    candidate: StrategyCandidate
    result: SimulationResult


def build_rolling_evidence(result: ResultLike) -> dict[str, Any]:
    """Build drawdown and positive-trade concentration evidence."""

    trades = list(result.trades)
    positive_rows = sorted(
        ((index, float(trade.net_profit_usdc)) for index, trade in enumerate(trades) if trade.net_profit_usdc > 0),
        key=lambda item: (-item[1], item[0]),
    )
    positive_total = sum(value for _, value in positive_rows)
    top1 = sum(value for _, value in positive_rows[:1])
    top5 = sum(value for _, value in positive_rows[:5])
    removed = {index for index, _ in positive_rows[:5]}
    remaining = [
        float(trade.net_profit_usdc)
        for index, trade in enumerate(trades)
        if index not in removed
    ]
    remaining_net = sum(remaining)
    remaining_pf = _finite_profit_factor(remaining)
    return {
        "drawdown_method": str(result.drawdown_method),
        "max_drawdown_usdc": _round(result.max_drawdown_usdc),
        "max_underwater_days": int(result.max_underwater_days),
        "top1_positive_pnl_share": _round(top1 / positive_total) if positive_total > 0 else 0.0,
        "top5_positive_pnl_share": _round(top5 / positive_total) if positive_total > 0 else 0.0,
        "net_without_top5_usdc": _round(remaining_net),
        "profit_factor_without_top5": _round(remaining_pf),
        "positive_trade_count": len(positive_rows),
        "removed_positive_trade_count": min(5, len(positive_rows)),
        "method": "closed_trade_concentration_plus_mark_to_market_equity",
    }


def build_temporal_evidence(
    trades: Sequence[Trade],
    *,
    window_start_ms: int,
    window_end_ms: int,
) -> dict[str, Any]:
    """Build complete UTC month/quarter evidence including no-trade periods."""

    if window_end_ms < window_start_ms:
        raise ValueError("window_end_ms must not precede window_start_ms")
    start_day = _utc_date(window_start_ms)
    end_day = _utc_date(window_end_ms)
    month_keys = _month_keys(start_day, end_day)
    quarter_keys = _quarter_keys(start_day, end_day)
    monthly_net = {key: 0.0 for key in month_keys}
    monthly_trades = {key: 0 for key in month_keys}
    quarterly_net = {key: 0.0 for key in quarter_keys}
    quarterly_trades = {key: 0 for key in quarter_keys}
    entry_days: list[date] = []
    for trade in trades:
        entry = datetime.fromtimestamp(trade.entry_time / 1000, tz=UTC)
        day = entry.date()
        if day < start_day or day > end_day:
            raise ValueError("trade entry lies outside the declared temporal window")
        month_key = (entry.year, entry.month)
        quarter_key = (entry.year, (entry.month - 1) // 3 + 1)
        monthly_net[month_key] += float(trade.net_profit_usdc)
        monthly_trades[month_key] += 1
        quarterly_net[quarter_key] += float(trade.net_profit_usdc)
        quarterly_trades[quarter_key] += 1
        entry_days.append(day)
    month_rows = [
        {
            "year": year,
            "month": month,
            "trade_count": monthly_trades[(year, month)],
            "net_profit_usdc": _round(monthly_net[(year, month)]),
        }
        for year, month in month_keys
    ]
    quarter_rows = [
        {
            "year": year,
            "quarter": quarter,
            "trade_count": quarterly_trades[(year, quarter)],
            "net_profit_usdc": _round(quarterly_net[(year, quarter)]),
        }
        for year, quarter in quarter_keys
    ]
    return {
        "months_observed": len(month_rows),
        "positive_months": sum(1 for row in month_rows if row["net_profit_usdc"] > 0),
        "active_months": sum(1 for row in month_rows if row["trade_count"] > 0),
        "max_no_trade_gap_days": _max_no_trade_gap_days(entry_days, start_day, end_day),
        "quarters_observed": len(quarter_rows),
        "positive_quarters": sum(1 for row in quarter_rows if row["net_profit_usdc"] > 0),
        "min_quarter_trade_count": min((row["trade_count"] for row in quarter_rows), default=0),
        "worst_month_net_usdc": min((row["net_profit_usdc"] for row in month_rows), default=0.0),
        "window_start_utc": start_day.isoformat(),
        "window_end_utc": end_day.isoformat(),
        "months": month_rows,
        "quarters": quarter_rows,
    }


def build_regime_evidence(
    training_candles: Sequence[Candle],
    evaluation_candles: Sequence[Candle],
    trades: Sequence[Trade],
    *,
    lookback_minutes: int = 60,
) -> dict[str, Any]:
    """Assign trades to four entry-time regimes with training-only thresholds."""

    if lookback_minutes <= 1:
        raise ValueError("lookback_minutes must exceed one")
    if not training_candles or not evaluation_candles:
        return _empty_regime_evidence(lookback_minutes)
    training_volatility = [
        _trailing_state(training_candles, index, lookback_minutes)[1]
        for index in range(1, len(training_candles))
    ]
    finite_training_volatility = [value for value in training_volatility if isfinite(value)]
    volatility_threshold = median(finite_training_volatility) if finite_training_volatility else 0.0
    times = [candle.open_time for candle in evaluation_candles]
    rows: dict[str, list[float]] = {label: [] for label in REGIME_LABELS}
    for trade in trades:
        index = bisect_left(times, int(trade.entry_time))
        trend, volatility = _trailing_state(evaluation_candles, index, lookback_minutes)
        trend_label = "up" if trend >= 0 else "down"
        volatility_label = "high" if volatility > volatility_threshold else "low"
        rows[f"{trend_label}_{volatility_label}"].append(float(trade.net_profit_usdc))
    total_positive = sum(value for values in rows.values() for value in values if value > 0)
    regime_rows = []
    for label in REGIME_LABELS:
        values = rows[label]
        positive = sum(value for value in values if value > 0)
        regime_rows.append(
            {
                "regime": label,
                "trade_count": len(values),
                "net_profit_usdc": _round(sum(values)),
                "profit_factor": _round(_finite_profit_factor(values)),
                "positive_pnl_share": _round(positive / total_positive) if total_positive > 0 else 0.0,
            }
        )
    return {
        "definition": REGIME_DEFINITION,
        "threshold_source": REGIME_THRESHOLD_SOURCE,
        "assignment_uses_entry_time_trailing_data_only": True,
        "lookback_minutes": lookback_minutes,
        "training_median_volatility_bps": _round(volatility_threshold),
        "regime_count": len(regime_rows),
        "min_trades_per_regime": min((row["trade_count"] for row in regime_rows), default=0),
        "positive_regime_count": sum(1 for row in regime_rows if row["net_profit_usdc"] > 0),
        "regimes_pf_at_least_1_05": sum(1 for row in regime_rows if row["profit_factor"] >= 1.05),
        "worst_regime_profit_factor": min((row["profit_factor"] for row in regime_rows), default=0.0),
        "worst_regime_net_usdc": min((row["net_profit_usdc"] for row in regime_rows), default=0.0),
        "max_positive_pnl_share": max((row["positive_pnl_share"] for row in regime_rows), default=0.0),
        "regimes": regime_rows,
    }


def run_cost_stress(
    candles: list[Candle],
    candidate: StrategyCandidate,
    *,
    days: int,
    gate: QualityGateV1 = QUALITY_GATE_V1,
) -> dict[str, Any]:
    """Evaluate the frozen candidate under the gate's fixed friction profiles."""

    profiles = {
        "baseline": (gate.baseline_fee_bps_per_side, gate.baseline_slippage_bps_per_side),
        "joint": (gate.joint_stress_fee_bps_per_side, gate.joint_stress_slippage_bps_per_side),
        "slippage": (gate.slippage_stress_fee_bps_per_side, gate.slippage_stress_slippage_bps_per_side),
    }
    results: dict[str, SimulationResult] = {}
    evidence: dict[str, Any] = {}
    for name, (fee_bps, slippage_bps) in profiles.items():
        result = simulate_strategy(
            candles,
            candidate,
            days=days,
            trade_usdc=100.0,
            fee_rate=fee_bps / 10_000,
            slippage_bps=slippage_bps,
        )
        results[name] = result
        evidence[name] = {
            "fee_bps_per_side": fee_bps,
            "slippage_bps_per_side": slippage_bps,
            "net_usdc_per_day": result.metrics.net_usdc_per_day,
            "net_profit_usdc": result.metrics.net_profit_usdc,
            "profit_factor": _round(_finite_profit_factor([trade.net_profit_usdc for trade in result.trades])),
            "max_drawdown_usdc": result.max_drawdown_usdc,
            "drawdown_method": result.drawdown_method,
            "trade_count": result.trade_count,
        }
    baseline = results["baseline"]
    positive_pre_cost = sum(
        max(0.0, float(trade.net_profit_usdc + trade.fees_usdc + trade.slippage_usdc))
        for trade in baseline.trades
    )
    friction = sum(float(trade.fees_usdc + trade.slippage_usdc) for trade in baseline.trades)
    evidence["friction_share_of_positive_pre_cost_pnl"] = (
        _round(friction / positive_pre_cost) if positive_pre_cost > 0 else 1.0
    )
    evidence["candidate_family"] = candidate.family
    evidence["uses_audit_or_holdout"] = False
    return evidence


def generate_parameter_neighbors(
    candidate: StrategyCandidate,
    *,
    perturbation_fraction: float = QUALITY_GATE_V1.parameter_perturbation_fraction,
    session_hour_step: int = QUALITY_GATE_V1.parameter_session_hour_step,
) -> tuple[list[tuple[str, str, float | int, StrategyCandidate]], int]:
    """Generate deterministic canonical neighbours for every numeric parameter."""

    if not 0 < perturbation_fraction < 1:
        raise ValueError("perturbation_fraction must be between zero and one")
    if session_hour_step <= 0:
        raise ValueError("session_hour_step must be positive")
    rows: list[tuple[str, str, float | int, StrategyCandidate]] = []
    numeric_count = 0
    seen: set[tuple[str, tuple[tuple[str, object], ...]]] = set()
    for key in sorted(candidate.params):
        value = candidate.params[key]
        if key in STRUCTURAL_PARAMETER_KEYS or isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric_count += 1
        for direction, neighbor_value in _neighbor_values(
            key,
            value,
            perturbation_fraction=perturbation_fraction,
            session_hour_step=session_hour_step,
        ):
            params = dict(candidate.params)
            params[key] = neighbor_value
            signature = (candidate.family, tuple(sorted(params.items())))
            if params[key] == value or signature in seen:
                continue
            seen.add(signature)
            rows.append((key, direction, neighbor_value, StrategyCandidate(candidate.family, params)))
    return rows, numeric_count


def run_parameter_stability(
    candles: list[Candle],
    candidate: StrategyCandidate,
    *,
    days: int,
    gate: QualityGateV1 = QUALITY_GATE_V1,
) -> dict[str, Any]:
    """Evaluate all deterministic numeric neighbours on the same selection data."""

    baseline = simulate_strategy(candles, candidate, days=days)
    neighbor_specs, numeric_count = generate_parameter_neighbors(
        candidate,
        perturbation_fraction=gate.parameter_perturbation_fraction,
        session_hour_step=gate.parameter_session_hour_step,
    )
    evaluations: list[NeighborEvaluation] = []
    for parameter, direction, value, neighbor in neighbor_specs:
        evaluations.append(
            NeighborEvaluation(
                parameter=parameter,
                direction=direction,
                value=value,
                candidate=neighbor,
                result=simulate_strategy(candles, neighbor, days=days),
            )
        )
    passing = [
        row
        for row in evaluations
        if row.result.net_usdc_per_day > 0
        and _finite_profit_factor([trade.net_profit_usdc for trade in row.result.trades])
        >= gate.min_validation_profit_factor
        and row.result.max_drawdown_usdc <= gate.max_validation_drawdown_usdc
    ]
    baseline_net = baseline.net_usdc_per_day
    neighbor_nets = [row.result.net_usdc_per_day for row in evaluations]
    retention_values = [value / baseline_net for value in neighbor_nets] if baseline_net > 0 else []
    return {
        "all_numeric_parameters_perturbed": len(evaluations) >= numeric_count * 2,
        "numeric_parameter_count": numeric_count,
        "neighbor_count": len(evaluations),
        "perturbation_fraction": gate.parameter_perturbation_fraction,
        "session_hour_step": gate.parameter_session_hour_step,
        "passing_neighbor_fraction": _round(len(passing) / len(evaluations)) if evaluations else 0.0,
        "median_net_retention": _round(median(retention_values)) if retention_values else 0.0,
        "worst_neighbor_net_usdc_per_day": _round(min(neighbor_nets)) if neighbor_nets else 0.0,
        "baseline_net_usdc_per_day": baseline_net,
        "neighbors": [
            {
                "parameter": row.parameter,
                "direction": row.direction,
                "value": row.value,
                "net_usdc_per_day": row.result.net_usdc_per_day,
                "profit_factor": _round(
                    _finite_profit_factor([trade.net_profit_usdc for trade in row.result.trades])
                ),
                "max_drawdown_usdc": row.result.max_drawdown_usdc,
                "trade_count": row.result.trade_count,
            }
            for row in evaluations
        ],
        "uses_audit_or_holdout": False,
    }


def _neighbor_values(
    key: str,
    value: float | int,
    *,
    perturbation_fraction: float,
    session_hour_step: int,
) -> list[tuple[str, float | int]]:
    if key in SESSION_PARAMETER_KEYS:
        base = int(value) % 24
        return [
            ("minus", (base - session_hour_step) % 24),
            ("plus", (base + session_hour_step) % 24),
        ]
    if isinstance(value, int):
        delta = max(1, int(round(abs(value) * perturbation_fraction)))
        minimum = 1 if key in STRICTLY_POSITIVE_PARAMETER_KEYS else 0
        return [("minus", max(minimum, value - delta)), ("plus", value + delta)]
    delta = max(abs(float(value)) * perturbation_fraction, perturbation_fraction)
    minimum = 1e-9 if key in STRICTLY_POSITIVE_PARAMETER_KEYS else 0.0
    return [
        ("minus", max(minimum, float(value) - delta)),
        ("plus", float(value) + delta),
    ]


def _trailing_state(
    candles: Sequence[Candle],
    end_index: int,
    lookback: int,
) -> tuple[float, float]:
    end = min(max(0, end_index), len(candles))
    if end < 2:
        return 0.0, 0.0
    start = max(0, end - lookback)
    first = float(candles[start].close)
    last = float(candles[end - 1].close)
    trend_bps = ((last / first) - 1) * 10_000 if first else 0.0
    moves: list[float] = []
    for index in range(max(start + 1, 1), end):
        previous = float(candles[index - 1].close)
        if previous:
            moves.append(abs(float(candles[index].close) / previous - 1) * 10_000)
    return trend_bps, sum(moves) / len(moves) if moves else 0.0


def _empty_regime_evidence(lookback_minutes: int) -> dict[str, Any]:
    rows = [
        {
            "regime": label,
            "trade_count": 0,
            "net_profit_usdc": 0.0,
            "profit_factor": 0.0,
            "positive_pnl_share": 0.0,
        }
        for label in REGIME_LABELS
    ]
    return {
        "definition": REGIME_DEFINITION,
        "threshold_source": REGIME_THRESHOLD_SOURCE,
        "assignment_uses_entry_time_trailing_data_only": True,
        "lookback_minutes": lookback_minutes,
        "training_median_volatility_bps": 0.0,
        "regime_count": 4,
        "min_trades_per_regime": 0,
        "positive_regime_count": 0,
        "regimes_pf_at_least_1_05": 0,
        "worst_regime_profit_factor": 0.0,
        "worst_regime_net_usdc": 0.0,
        "max_positive_pnl_share": 0.0,
        "regimes": rows,
    }


def _finite_profit_factor(values: Sequence[float]) -> float:
    positive = sum(float(value) for value in values if value > 0)
    negative = abs(sum(float(value) for value in values if value < 0))
    if negative > 0:
        return positive / negative
    if positive > 0:
        return 1_000_000_000_000.0
    return 0.0


def _max_no_trade_gap_days(entry_days: Sequence[date], start_day: date, end_day: date) -> int:
    unique = sorted(set(entry_days))
    if not unique:
        return (end_day - start_day).days + 1
    gaps = [(unique[0] - start_day).days, (end_day - unique[-1]).days]
    gaps.extend(max(0, (right - left).days - 1) for left, right in zip(unique, unique[1:]))
    return max(gaps, default=0)


def _month_keys(start: date, end: date) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        result.append((year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return result


def _quarter_keys(start: date, end: date) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    year, quarter = start.year, (start.month - 1) // 3 + 1
    end_key = (end.year, (end.month - 1) // 3 + 1)
    while (year, quarter) <= end_key:
        result.append((year, quarter))
        quarter += 1
        if quarter == 5:
            year += 1
            quarter = 1
    return result


def _utc_date(timestamp_ms: int) -> date:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).date()


def _round(value: float | int) -> float:
    return round(float(value), 10)


__all__ = [
    "NeighborEvaluation",
    "REGIME_DEFINITION",
    "REGIME_LABELS",
    "REGIME_THRESHOLD_SOURCE",
    "build_regime_evidence",
    "build_rolling_evidence",
    "build_temporal_evidence",
    "generate_parameter_neighbors",
    "run_cost_stress",
    "run_parameter_stability",
]
