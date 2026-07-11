"""Deprecated strategy-search compatibility types and fail-closed guards."""

from __future__ import annotations

from dataclasses import dataclass

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.simulator import SimulationResult, StrategyCandidate

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


def run_strategy_search(
    training: list[Candle],
    blindtest: list[Candle],
    *,
    training_days: int = 730,
    blindtest_days: int = 365,
) -> StrategySearchResult:
    """Reject the deprecated select-then-holdout workflow before evaluation."""

    raise RuntimeError(
        "Legacy strategy search is disabled by Research Protocol v2 because it evaluates holdout data; "
        "use ethusdc_bot.backtest.research_loop_runner"
    )


def evaluate_blindtest_once(
    candidate: StrategyCandidate,
    blindtest: list[Candle],
    *,
    days: int,
    training_days: int = 730,
    blindtest_days: int = 365,
) -> SimulationResult:
    """Reject direct legacy holdout evaluation; no sealed workflow exists yet."""

    raise RuntimeError(
        "Direct blindtest evaluation is disabled by Research Protocol v2; "
        "the separate one-shot sealed-holdout workflow is not implemented"
    )
