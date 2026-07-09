"""Tests for walk-forward validation folds and ranking."""

from datetime import UTC, datetime, timedelta

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.backtest.walk_forward import build_walk_forward_folds, rank_with_walk_forward


def _candles(count: int) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Candle(
            open_time=int((start + timedelta(minutes=index)).timestamp() * 1000),
            open=100 + index * 0.01,
            high=100 + index * 0.01 + 0.1,
            low=100 + index * 0.01 - 0.1,
            close=100 + index * 0.01,
            volume=1.0,
        )
        for index in range(count)
    ]


def test_walk_forward_folds_are_chronological_without_lookahead():
    folds = build_walk_forward_folds(_candles(100), fold_count=4)

    assert len(folds) == 4
    previous_validation_end = -1
    for fold in folds:
        assert fold.train_window[0].open_time < fold.train_window[-1].open_time
        assert fold.validation_window[0].open_time > fold.train_window[-1].open_time
        assert fold.validation_window[0].open_time > previous_validation_end
        previous_validation_end = fold.validation_window[-1].open_time


def test_walk_forward_ranking_uses_no_blindtest_data():
    strong_wfv_bad_blind = {
        "candidate_id": "alpha_001",
        "candidate": StrategyCandidate("alpha", {}),
        "validation_metrics": BacktestMetrics(10, 1, 10, 0.5, 1, 1.2, 1, 1, 1, 1, 1),
        "walk_forward_summary": {
            "average_validation_net_usdc_per_day": 1.0,
            "worst_fold_net_usdc_per_day": 0.5,
            "positive_fold_count": 4,
            "trade_count": 40,
            "cost_load": 2,
        },
        "blindtest_metrics": {"net_usdc_per_day": -999},
    }
    weak_wfv_great_blind = {
        "candidate_id": "beta_001",
        "candidate": StrategyCandidate("beta", {}),
        "validation_metrics": BacktestMetrics(-1, -1, 10, 0.5, 1, 0.8, -0.1, 1, 1, 1, 1),
        "walk_forward_summary": {
            "average_validation_net_usdc_per_day": -1.0,
            "worst_fold_net_usdc_per_day": -2.0,
            "positive_fold_count": 0,
            "trade_count": 40,
            "cost_load": 2,
        },
        "blindtest_metrics": {"net_usdc_per_day": 999},
    }

    ranked = rank_with_walk_forward([weak_wfv_great_blind, strong_wfv_bad_blind])

    assert ranked[0]["candidate_id"] == "alpha_001"
    assert ranked[0]["walk_forward_rank_uses_blindtest"] is False
