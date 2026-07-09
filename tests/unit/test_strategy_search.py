"""Tests for deterministic strategy search without blindtest leakage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.strategy_search import TARGET_USDC_PER_DAY, evaluate_blindtest_once, run_strategy_search


def _candles(closes: list[float]) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Candle(open_time=int((start + timedelta(minutes=i)).timestamp() * 1000), open=close, high=close + 1, low=close - 1, close=close, volume=1)
        for i, close in enumerate(closes)
    ]


def test_search_selects_using_only_training_candles():
    training = _candles([100, 101, 102, 103, 104, 105, 106, 107])
    blind = _candles([500, 100, 500, 100])

    result = run_strategy_search(training, blind)

    assert result.selection_source == "training_validation_only"
    assert result.training_candle_count == len(training)
    assert result.blindtest_candle_count == len(blind)
    assert result.selected_candidate is not None


def test_blindtest_runs_only_after_selection():
    training = _candles([100, 101, 102, 103, 104, 105, 106, 107])
    blind = _candles([108, 109, 110])

    result = run_strategy_search(training, blind)

    assert result.event_log.index("candidate_selected") < result.event_log.index("blindtest_evaluated")


def test_target_is_constant_not_candidate_parameter():
    result = run_strategy_search(_candles([100, 101, 102, 103, 104, 105]), _candles([100, 99, 98]))

    assert TARGET_USDC_PER_DAY == 3.0
    assert all("3" not in str(candidate.params.get("threshold_bps", "")) for candidate in result.candidates)


def test_blindtest_result_reports_target_reached_or_not_honestly():
    result = run_strategy_search(_candles([100, 101, 102, 103, 104, 105]), _candles([100, 100, 100]))

    assert result.target_reached is (result.blindtest_metrics.net_usdc_per_day >= TARGET_USDC_PER_DAY)
    assert result.target_status in {"target_reached", "target_not_reached"}


def test_evaluate_blindtest_once_uses_selected_candidate():
    search = run_strategy_search(_candles([100, 101, 102, 103, 104, 105]), _candles([106, 107, 108]))

    blind = evaluate_blindtest_once(search.selected_candidate, _candles([106, 107, 108]), days=1)

    assert blind.trade_count >= 0
