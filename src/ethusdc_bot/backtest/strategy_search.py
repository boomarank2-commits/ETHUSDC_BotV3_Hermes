"""Small deterministic strategy search over training/validation only."""

from __future__ import annotations

from dataclasses import dataclass

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.simulator import SimulationResult, StrategyCandidate, simulate_strategy

TARGET_USDC_PER_DAY = 3.0


@dataclass(frozen=True)
class StrategySearchResult:
    candidates: list[StrategyCandidate]
    selected_candidate: StrategyCandidate
    training_results: list[SimulationResult]
    validation_result: SimulationResult
    blindtest_result: SimulationResult
    training_metrics: BacktestMetrics
    blindtest_metrics: BacktestMetrics
    target_reached: bool
    target_status: str
    selection_source: str
    event_log: list[str]
    training_candle_count: int
    blindtest_candle_count: int
    strategy_families: list[str]


def build_candidate_grid() -> list[StrategyCandidate]:
    return [
        StrategyCandidate("momentum", {"lookback": 3, "threshold_bps": 20, "take_profit_bps": 70, "stop_loss_bps": 50, "max_hold_minutes": 12}),
        StrategyCandidate("momentum", {"lookback": 10, "threshold_bps": 40, "take_profit_bps": 90, "stop_loss_bps": 60, "max_hold_minutes": 30}),
        StrategyCandidate("mean_reversion", {"lookback": 5, "threshold_bps": 25, "take_profit_bps": 55, "stop_loss_bps": 45, "max_hold_minutes": 15}),
        StrategyCandidate("mean_reversion", {"lookback": 20, "threshold_bps": 60, "take_profit_bps": 80, "stop_loss_bps": 80, "max_hold_minutes": 45}),
        StrategyCandidate("breakout", {"lookback": 15, "threshold_bps": 5, "take_profit_bps": 80, "stop_loss_bps": 55, "max_hold_minutes": 25}),
        StrategyCandidate("breakout", {"lookback": 60, "threshold_bps": 10, "take_profit_bps": 120, "stop_loss_bps": 80, "max_hold_minutes": 90}),
    ]


def run_strategy_search(training: list[Candle], blindtest: list[Candle], *, training_days: int = 730, blindtest_days: int = 365) -> StrategySearchResult:
    if not training:
        raise ValueError("training candles required")
    if not blindtest:
        raise ValueError("blindtest candles required")
    event_log = ["candidate_grid_built"]
    candidates = build_candidate_grid()
    validation_start = max(1, int(len(training) * 0.8)) if len(training) > 5 else max(1, len(training) - 1)
    subtrain = training[:validation_start]
    validation = training[validation_start:] or training[-1:]
    training_results = [
        simulate_strategy(subtrain, candidate, days=max(1, training_days * len(subtrain) // max(1, len(training))), training_days=training_days, blindtest_days=blindtest_days)
        for candidate in candidates
    ]
    event_log.append("training_candidates_evaluated")
    ranked = sorted(training_results, key=lambda result: (result.metrics.net_usdc_per_day, -result.metrics.max_drawdown_usdc, result.trade_count), reverse=True)
    shortlisted = [result.strategy for result in ranked[:3]] or [candidates[0]]
    validation_results = [
        simulate_strategy(validation, candidate, days=max(1, training_days * len(validation) // max(1, len(training))), training_days=training_days, blindtest_days=blindtest_days)
        for candidate in shortlisted
    ]
    validation_result = sorted(validation_results, key=lambda result: (result.metrics.net_usdc_per_day, -result.metrics.max_drawdown_usdc, result.trade_count), reverse=True)[0]
    selected = validation_result.strategy
    event_log.append("candidate_selected")
    full_training_result = simulate_strategy(training, selected, days=max(1, training_days), training_days=training_days, blindtest_days=blindtest_days)
    blindtest_result = evaluate_blindtest_once(selected, blindtest, days=max(1, blindtest_days), training_days=training_days, blindtest_days=blindtest_days)
    event_log.append("blindtest_evaluated")
    target_reached = blindtest_result.metrics.net_usdc_per_day >= TARGET_USDC_PER_DAY
    return StrategySearchResult(
        candidates=candidates,
        selected_candidate=selected,
        training_results=training_results,
        validation_result=validation_result,
        blindtest_result=blindtest_result,
        training_metrics=full_training_result.metrics,
        blindtest_metrics=blindtest_result.metrics,
        target_reached=target_reached,
        target_status="target_reached" if target_reached else "target_not_reached",
        selection_source="training_validation_only",
        event_log=event_log,
        training_candle_count=len(training),
        blindtest_candle_count=len(blindtest),
        strategy_families=sorted({candidate.family for candidate in candidates}),
    )


def evaluate_blindtest_once(candidate: StrategyCandidate, blindtest: list[Candle], *, days: int, training_days: int = 730, blindtest_days: int = 365) -> SimulationResult:
    return simulate_strategy(blindtest, candidate, days=days, training_days=training_days, blindtest_days=blindtest_days)
