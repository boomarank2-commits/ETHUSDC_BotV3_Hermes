"""Walk-forward validation helpers for training-only strategy ranking."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from statistics import median, pstdev
from typing import Any

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.equity import (
    EquityPoint,
    chain_equity_curves,
    max_drawdown_usdc,
    max_underwater_calendar_days,
)
from ethusdc_bot.backtest.metrics import BacktestMetrics, compute_metrics
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy
from ethusdc_bot.backtest.walk_forward_evidence import (
    FoldSelectionObservation,
    build_walk_forward_selection_evidence,
)
from ethusdc_bot.backtest.split import SplitResult


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_window: list[Candle]
    validation_window: list[Candle]


def build_walk_forward_folds(
    training: list[Candle],
    *,
    fold_count: int = 4,
    expected_candles_per_day: int | None = None,
) -> list[WalkForwardFold]:
    """Create chronological expanding train / forward validation folds.

    Validation windows are always after each fold's train window and UTC days
    are never split between folds. The function never exposes blindtest
    candles because it accepts only the caller-provided training slice.
    """

    if fold_count <= 0:
        raise ValueError("fold_count must be positive")
    if expected_candles_per_day is not None and (
        isinstance(expected_candles_per_day, bool)
        or not isinstance(expected_candles_per_day, int)
        or expected_candles_per_day <= 0
    ):
        raise ValueError("expected_candles_per_day must be a positive integer or None")
    day_groups = _group_candles_by_utc_day(training)
    _validate_day_groups(day_groups, expected_candles_per_day)
    days = list(day_groups)
    if len(days) < fold_count * 2:
        return []
    validation_size = max(1, len(days) // (fold_count + 2))
    initial_train_size = len(days) - validation_size * fold_count
    if initial_train_size <= 0:
        initial_train_size = validation_size
    folds: list[WalkForwardFold] = []
    for index in range(fold_count):
        validation_start = initial_train_size + index * validation_size
        validation_end = validation_start + validation_size if index < fold_count - 1 else len(days)
        if validation_start <= 0 or validation_start >= len(days):
            break
        train_window = _flatten_day_groups(day_groups, days[:validation_start])
        validation_window = _flatten_day_groups(day_groups, days[validation_start:validation_end])
        if train_window and validation_window:
            folds.append(WalkForwardFold(index + 1, train_window, validation_window))
    return folds


def evaluate_walk_forward(
    training: list[Candle],
    candidate: StrategyCandidate,
    *,
    fold_count: int = 4,
    training_days: int = 730,
    blindtest_days: int = 365,
    max_candles_per_fold: int | None = None,
    expected_candles_per_day: int | None = None,
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
    include_selection_evidence: bool = True,
) -> dict[str, Any]:
    if max_candles_per_fold is not None and (
        isinstance(max_candles_per_fold, bool)
        or not isinstance(max_candles_per_fold, int)
        or max_candles_per_fold <= 0
    ):
        raise ValueError("max_candles_per_fold must be a positive integer or None")
    if fee_rate < 0 or slippage_bps < 0:
        raise ValueError("fee_rate and slippage_bps must be non-negative")
    folds = build_walk_forward_folds(
        training,
        fold_count=fold_count,
        expected_candles_per_day=expected_candles_per_day,
    )
    fold_rows: list[dict[str, Any]] = []
    all_trades = []
    fold_equity_curves: list[tuple[EquityPoint, ...]] = []
    selection_observations: list[FoldSelectionObservation] = []
    simulated_days = 0
    for fold in folds:
        validation_window = _sample_whole_utc_days(
            fold.validation_window,
            max_candles=max_candles_per_fold,
        )
        fold_days = _calendar_day_count(validation_window)
        result = simulate_strategy(
            validation_window,
            candidate,
            days=fold_days,
            training_days=training_days,
            blindtest_days=blindtest_days,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
        )
        selection_observations.append(
            FoldSelectionObservation(
                fold_id=fold.fold_id,
                training_candles=tuple(fold.train_window),
                validation_candles=tuple(validation_window),
                result=result,
            )
        )
        fold_metrics = result.metrics.to_dict()
        fold_metrics["drawdown_method"] = result.drawdown_method
        fold_net_profits = [float(trade.net_profit_usdc) for trade in result.trades]
        fold_metrics["gross_profit_usdc"] = round(
            sum(value for value in fold_net_profits if value > 0), 10
        )
        fold_metrics["gross_loss_usdc"] = round(
            abs(sum(value for value in fold_net_profits if value < 0)), 10
        )
        all_trades.extend(result.trades)
        fold_equity_curves.append(result.equity_curve)
        simulated_days += fold_days
        fold_rows.append(
            {
                "fold_id": fold.fold_id,
                "train_start": fold.train_window[0].open_time,
                "train_end": fold.train_window[-1].open_time,
                "validation_start": validation_window[0].open_time,
                "validation_end": validation_window[-1].open_time,
                "sampled_validation_candles": len(validation_window),
                "simulated_validation_days": fold_days,
                "days": fold_days,
                "metrics": fold_metrics,
                "equity_curve_usdc": result.equity_curve_usdc,
                "equity_curve_timestamps_ms": result.equity_curve_timestamps_ms,
            }
        )
    chained_equity = chain_equity_curves(fold_equity_curves)
    aggregate = compute_metrics(
        all_trades,
        days=max(1, simulated_days),
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
    aggregate = replace(
        aggregate,
        max_drawdown_usdc=max_drawdown_usdc(chained_equity),
    )
    summary = summarize_walk_forward(
        fold_rows,
        aggregate_metrics=aggregate,
        aggregate_max_underwater_days=max_underwater_calendar_days(chained_equity),
    )
    if include_selection_evidence:
        summary["selection_evidence"] = build_walk_forward_selection_evidence(
            selection_observations,
            chained_equity=chained_equity,
        )
    else:
        summary["selection_evidence"] = {
            "not_computed_reason": "stress_profile_reuses_baseline_selection_evidence",
            "uses_audit_or_holdout": False,
        }
    summary["fee_bps_per_side"] = fee_rate * 10_000
    summary["slippage_bps_per_side"] = slippage_bps
    return summary


def evaluate_walk_forward_frontier(
    training: list[Candle],
    ranked_records: list[dict[str, Any]],
    *,
    candidate_limit: int,
    fold_count: int = 6,
    training_days: int = 730,
    blindtest_days: int = 365,
    max_candles_per_fold: int | None = None,
    expected_candles_per_day: int | None = None,
) -> list[dict[str, Any]]:
    """Evaluate a deterministic validation-ranked frontier with WFV.

    The caller supplies records already ranked without audit/holdout data. Only
    the explicit candidate budget limits work; input order otherwise remains
    stable and reproducible.
    """

    if candidate_limit <= 0:
        return []
    evaluated: list[dict[str, Any]] = []
    for record in ranked_records[:candidate_limit]:
        row = dict(record)
        row["walk_forward_summary"] = evaluate_walk_forward(
            training,
            record["candidate"],
            fold_count=fold_count,
            training_days=training_days,
            blindtest_days=blindtest_days,
            max_candles_per_fold=max_candles_per_fold,
            expected_candles_per_day=expected_candles_per_day,
        )
        evaluated.append(row)
    return evaluated


def evaluate_rolling_origins(
    origins: list[SplitResult],
    candidate: StrategyCandidate,
    *,
    origin_limit: int | None = None,
) -> dict[str, Any]:
    """Replay a fixed candidate on historical windows before the final holdout.

    ``build_research_window_plan`` is responsible for the no-overlap invariant.
    This evaluator never receives or evaluates the plan's final holdout. A
    fixed-candidate backcast is not a time-local refit and therefore remains
    ineligible as formal rolling-origin selection evidence.
    """

    selected = origins[:origin_limit] if origin_limit is not None else origins
    rows: list[dict[str, Any]] = []
    for origin_index, origin in enumerate(selected, start=1):
        result = simulate_strategy(
            origin.blindtest,
            candidate,
            days=origin.blindtest_days,
            training_days=origin.training_days,
            blindtest_days=origin.blindtest_days,
        )
        rows.append(
            {
                "origin_id": origin_index,
                "training_start": origin.training_start,
                "training_end": origin.training_end,
                "oos_start": origin.blind_start,
                "oos_end": origin.blind_end,
                "uses_final_audit": False,
                "metrics": result.metrics.to_dict(),
            }
        )
    values = [row["metrics"]["net_usdc_per_day"] for row in rows]
    drawdowns = [row["metrics"]["max_drawdown_usdc"] for row in rows]
    return {
        "uses_final_audit": False,
        "method": "fixed_candidate_historical_replay",
        "pipeline_refit_per_origin": False,
        "eligible_as_quality_gate_evidence": False,
        "origin_count": len(rows),
        "origins": rows,
        "average_oos_net_usdc_per_day": round(sum(values) / len(values), 10) if values else 0.0,
        "worst_oos_net_usdc_per_day": round(min(values), 10) if values else 0.0,
        "positive_origin_count": sum(1 for value in values if value > 0),
        "trade_count": sum(int(row["metrics"]["trade_count"]) for row in rows),
        "max_drawdown_usdc": round(max(drawdowns), 10) if drawdowns else 0.0,
        "cost_load": round(
            sum(row["metrics"]["fees_usdc"] + row["metrics"]["slippage_usdc"] for row in rows), 10
        ),
    }


def summarize_walk_forward(
    fold_rows: list[dict[str, Any]],
    *,
    aggregate_metrics: BacktestMetrics | None = None,
    aggregate_max_underwater_days: int | None = None,
) -> dict[str, Any]:
    values = [row["metrics"]["net_usdc_per_day"] for row in fold_rows]
    profit_factors = [row["metrics"].get("profit_factor", 0.0) for row in fold_rows]
    drawdowns = [row["metrics"].get("max_drawdown_usdc", 0.0) for row in fold_rows]
    trades = [row["metrics"].get("trade_count", 0) for row in fold_rows]
    costs = [row["metrics"].get("fees_usdc", 0.0) + row["metrics"].get("slippage_usdc", 0.0) for row in fold_rows]
    mean = sum(values) / len(values) if values else 0.0
    if len(values) > 1:
        dispersion = pstdev(values)
        if mean:
            coefficient_of_variation = dispersion / abs(mean)
        elif dispersion == 0:
            coefficient_of_variation = 0.0
        else:
            coefficient_of_variation = None
    else:
        coefficient_of_variation = None
    aggregate = aggregate_metrics.to_dict() if aggregate_metrics is not None else {}
    if aggregate_metrics is not None:
        aggregate["drawdown_method"] = "mark_to_market"
        aggregate["max_underwater_days"] = aggregate_max_underwater_days
    return {
        "ranking_uses_blindtest": False,
        "fold_count": len(fold_rows),
        "folds": fold_rows,
        "average_validation_net_usdc_per_day": round(mean, 10) if values else 0.0,
        "worst_fold_net_usdc_per_day": round(min(values), 10) if values else 0.0,
        "median_fold_net_usdc_per_day": round(median(values), 10) if values else 0.0,
        "fold_net_coefficient_of_variation": round(coefficient_of_variation, 10)
        if coefficient_of_variation is not None
        else None,
        "positive_fold_count": sum(1 for value in values if value > 0),
        "folds_pf_at_least_1_05": sum(1 for value in profit_factors if value >= 1.05),
        "worst_fold_profit_factor": round(min(profit_factors), 10) if profit_factors else 0.0,
        "max_drawdown_usdc": round(max(drawdowns), 10) if drawdowns else 0.0,
        "trade_count": sum(int(value) for value in trades),
        "cost_load": round(sum(costs), 10),
        "aggregate_metrics": aggregate,
    }


def rank_with_walk_forward(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(records, key=_wfv_score, reverse=True)
    output: list[dict[str, Any]] = []
    for position, record in enumerate(ranked, start=1):
        row = dict(record)
        row["walk_forward_rank_position"] = position
        row["walk_forward_rank_uses_blindtest"] = False
        output.append(row)
    return output


def _wfv_score(record: dict[str, Any]) -> tuple[float, float, float, float, float, float, float]:
    summary = record.get("walk_forward_summary", {})
    aggregate = summary.get("aggregate_metrics", {})
    if not isinstance(aggregate, dict):
        aggregate = {}
    validation: BacktestMetrics | None = record.get("validation_metrics")
    validation_net = validation.net_usdc_per_day if validation is not None else 0.0
    aggregate_cost = _safe_float(aggregate.get("fees_usdc")) + _safe_float(
        aggregate.get("slippage_usdc")
    )
    # Ranking and quality gates consume the same chained, day-weighted WFV
    # aggregate. Fold diagnostics remain deterministic tie-breakers only.
    return (
        _safe_float(aggregate.get("net_usdc_per_day")),
        _safe_float(aggregate.get("profit_factor")),
        -_safe_float(aggregate.get("max_drawdown_usdc")),
        _safe_float(summary.get("worst_fold_net_usdc_per_day")),
        _safe_float(summary.get("positive_fold_count")),
        float(validation_net),
        -aggregate_cost,
    )


def _calendar_day_count(candles: list[Candle]) -> int:
    days = {datetime.fromtimestamp(candle.open_time / 1000, tz=UTC).date() for candle in candles}
    return len(days)


def _group_candles_by_utc_day(candles: list[Candle]) -> dict[date, list[Candle]]:
    groups: dict[date, list[Candle]] = {}
    seen: set[int] = set()
    for candle in sorted(candles, key=lambda item: item.open_time):
        if candle.open_time in seen:
            raise ValueError("Duplicate candle open_time prevents UTC-day walk-forward folds")
        seen.add(candle.open_time)
        day = datetime.fromtimestamp(candle.open_time / 1000, tz=UTC).date()
        groups.setdefault(day, []).append(candle)
    return groups


def _validate_day_groups(
    groups: dict[date, list[Candle]], expected_candles_per_day: int | None
) -> None:
    days = list(groups)
    for previous, current in zip(days, days[1:]):
        if current != previous + timedelta(days=1):
            raise ValueError(
                f"Walk-forward UTC days must be continuous; expected "
                f"{(previous + timedelta(days=1)).isoformat()}, observed {current.isoformat()}"
            )
    if expected_candles_per_day is None:
        return
    incomplete = [
        day
        for day, rows in groups.items()
        if len(rows) != expected_candles_per_day
        or not _has_expected_utc_grid(day, rows, expected_candles_per_day)
    ]
    if incomplete:
        first = incomplete[0]
        raise ValueError(
            f"Walk-forward UTC day {first.isoformat()} has {len(groups[first])} candles; "
            f"expected {expected_candles_per_day}"
        )


def _has_expected_utc_grid(
    day: date, candles: list[Candle], expected_candles_per_day: int
) -> bool:
    if expected_candles_per_day != 1440:
        return True
    day_start_ms = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    return all(
        candle.open_time == day_start_ms + minute * 60_000
        for minute, candle in enumerate(candles)
    )


def _flatten_day_groups(groups: dict[date, list[Candle]], days: list[date]) -> list[Candle]:
    return [candle for day in days for candle in groups[day]]


def _sample_whole_utc_days(
    candles: list[Candle], *, max_candles: int | None
) -> list[Candle]:
    if max_candles is None:
        return candles
    groups = _group_candles_by_utc_day(candles)
    selected_days: list[date] = []
    sampled_count = 0
    for day in reversed(list(groups)):
        day_count = len(groups[day])
        if sampled_count + day_count > max_candles:
            break
        selected_days.append(day)
        sampled_count += day_count
    if not selected_days:
        raise ValueError(
            "max_candles_per_fold is smaller than one complete UTC validation day"
        )
    selected_days.reverse()
    return _flatten_day_groups(groups, selected_days)


def _safe_float(value: object) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0
