"""Walk-forward validation helpers for training-only strategy ranking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_window: list[Candle]
    validation_window: list[Candle]


def build_walk_forward_folds(training: list[Candle], *, fold_count: int = 4) -> list[WalkForwardFold]:
    """Create chronological expanding train / forward validation folds.

    Validation windows are always after each fold's train window. The function
    never exposes blindtest candles because it accepts only the caller-provided
    training slice.
    """

    if fold_count <= 0:
        raise ValueError("fold_count must be positive")
    if len(training) < fold_count * 2:
        return []
    validation_size = max(1, len(training) // (fold_count + 2))
    initial_train_size = len(training) - validation_size * fold_count
    if initial_train_size <= 0:
        initial_train_size = validation_size
    folds: list[WalkForwardFold] = []
    for index in range(fold_count):
        validation_start = initial_train_size + index * validation_size
        validation_end = validation_start + validation_size if index < fold_count - 1 else len(training)
        if validation_start <= 0 or validation_start >= len(training):
            break
        train_window = training[:validation_start]
        validation_window = training[validation_start:validation_end]
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
) -> dict[str, Any]:
    folds = build_walk_forward_folds(training, fold_count=fold_count)
    fold_rows: list[dict[str, Any]] = []
    for fold in folds:
        fold_days = max(1, training_days * len(fold.validation_window) // max(1, len(training)))
        validation_window = fold.validation_window[-max_candles_per_fold:] if max_candles_per_fold else fold.validation_window
        result = simulate_strategy(
            validation_window,
            candidate,
            days=fold_days,
            training_days=training_days,
            blindtest_days=blindtest_days,
        )
        fold_rows.append(
            {
                "fold_id": fold.fold_id,
                "train_start": fold.train_window[0].open_time,
                "train_end": fold.train_window[-1].open_time,
                "validation_start": validation_window[0].open_time,
                "validation_end": validation_window[-1].open_time,
                "sampled_validation_candles": len(validation_window),
                "metrics": result.metrics.to_dict(),
            }
        )
    return summarize_walk_forward(fold_rows)


def summarize_walk_forward(fold_rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["metrics"]["net_usdc_per_day"] for row in fold_rows]
    drawdowns = [row["metrics"].get("max_drawdown_usdc", 0.0) for row in fold_rows]
    trades = [row["metrics"].get("trade_count", 0) for row in fold_rows]
    costs = [row["metrics"].get("fees_usdc", 0.0) + row["metrics"].get("slippage_usdc", 0.0) for row in fold_rows]
    return {
        "ranking_uses_blindtest": False,
        "fold_count": len(fold_rows),
        "folds": fold_rows,
        "average_validation_net_usdc_per_day": round(sum(values) / len(values), 10) if values else 0.0,
        "worst_fold_net_usdc_per_day": round(min(values), 10) if values else 0.0,
        "positive_fold_count": sum(1 for value in values if value > 0),
        "max_drawdown_usdc": round(max(drawdowns), 10) if drawdowns else 0.0,
        "trade_count": sum(int(value) for value in trades),
        "cost_load": round(sum(costs), 10),
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


def _wfv_score(record: dict[str, Any]) -> float:
    summary = record.get("walk_forward_summary", {})
    validation: BacktestMetrics | None = record.get("validation_metrics")
    validation_net = validation.net_usdc_per_day if validation is not None else 0.0
    return (
        float(summary.get("average_validation_net_usdc_per_day", 0.0))
        + float(summary.get("worst_fold_net_usdc_per_day", 0.0)) * 0.5
        + float(summary.get("positive_fold_count", 0)) * 0.1
        + validation_net * 0.25
        - float(summary.get("max_drawdown_usdc", 0.0)) / 100
        - float(summary.get("cost_load", 0.0)) / 1000
    )
