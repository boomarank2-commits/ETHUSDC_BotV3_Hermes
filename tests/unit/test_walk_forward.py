"""Tests for walk-forward validation folds and ranking."""

from datetime import UTC, datetime, timedelta

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.backtest.split import build_research_window_plan
from ethusdc_bot.backtest.walk_forward import (
    build_walk_forward_folds,
    evaluate_rolling_origins,
    evaluate_walk_forward,
    evaluate_walk_forward_frontier,
    rank_with_walk_forward,
)


def _intraday_candles(days: int, candles_per_day: int = 10) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Candle(
            open_time=int((start + timedelta(days=day, minutes=minute)).timestamp() * 1000),
            open=100 + index * 0.01,
            high=100 + index * 0.01 + 0.1,
            low=100 + index * 0.01 - 0.1,
            close=100 + index * 0.01,
            volume=1.0,
        )
        for day in range(days)
        for minute in range(candles_per_day)
        for index in [day * candles_per_day + minute]
    ]


def _daily_candles(days: int) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Candle(
            open_time=int((start + timedelta(days=index)).timestamp() * 1000),
            open=100 + index,
            high=101 + index,
            low=99 + index,
            close=100 + index,
            volume=1.0,
        )
        for index in range(days)
    ]


def _minute_day(day: datetime, *, displaced_minute: int | None = None) -> list[Candle]:
    return [
        Candle(
            open_time=int(
                (
                    day
                    + timedelta(
                        minutes=minute,
                        seconds=30 if minute == displaced_minute else 0,
                    )
                ).timestamp()
                * 1000
            ),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1.0,
        )
        for minute in range(1440)
    ]


def test_walk_forward_folds_are_chronological_without_lookahead():
    folds = build_walk_forward_folds(
        _intraday_candles(10),
        fold_count=4,
        expected_candles_per_day=10,
    )

    assert len(folds) == 4
    previous_validation_end = -1
    for fold in folds:
        assert fold.train_window[0].open_time < fold.train_window[-1].open_time
        assert fold.validation_window[0].open_time > fold.train_window[-1].open_time
        assert fold.validation_window[0].open_time > previous_validation_end
        validation_days = {
            datetime.fromtimestamp(candle.open_time / 1000, tz=UTC).date()
            for candle in fold.validation_window
        }
        assert len(fold.validation_window) == len(validation_days) * 10
        previous_validation_end = fold.validation_window[-1].open_time


def test_walk_forward_rejects_1440_rows_with_gap_compensated_timestamp():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    training = [
        *_minute_day(start),
        *_minute_day(start + timedelta(days=1), displaced_minute=500),
    ]

    with pytest.raises(ValueError, match="expected 1440"):
        build_walk_forward_folds(
            training,
            fold_count=1,
            expected_candles_per_day=1440,
        )


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
            "aggregate_metrics": {
                "net_usdc_per_day": 1.0,
                "profit_factor": 1.2,
                "max_drawdown_usdc": 1.0,
                "fees_usdc": 1.0,
                "slippage_usdc": 1.0,
            },
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
            "aggregate_metrics": {
                "net_usdc_per_day": -1.0,
                "profit_factor": 0.8,
                "max_drawdown_usdc": 1.0,
                "fees_usdc": 1.0,
                "slippage_usdc": 1.0,
            },
        },
        "blindtest_metrics": {"net_usdc_per_day": 999},
    }

    ranked = rank_with_walk_forward([weak_wfv_great_blind, strong_wfv_bad_blind])

    assert ranked[0]["candidate_id"] == "alpha_001"
    assert ranked[0]["walk_forward_rank_uses_blindtest"] is False


def test_walk_forward_ranking_uses_day_weighted_aggregate_not_unweighted_fold_average():
    misleading_average = {
        "candidate_id": "misleading",
        "candidate": StrategyCandidate("alpha", {}),
        "validation_metrics": BacktestMetrics(1, 1, 10, 0.5, 1, 1.2, 1, 1, 1, 1, 1),
        "walk_forward_summary": {
            "average_validation_net_usdc_per_day": 100.0,
            "worst_fold_net_usdc_per_day": 0.0,
            "positive_fold_count": 6,
            "aggregate_metrics": {
                "net_usdc_per_day": -1.0,
                "profit_factor": 1.2,
                "max_drawdown_usdc": 1.0,
                "fees_usdc": 1.0,
                "slippage_usdc": 1.0,
            },
        },
    }
    better_aggregate = {
        "candidate_id": "better",
        "candidate": StrategyCandidate("beta", {}),
        "validation_metrics": BacktestMetrics(1, 1, 10, 0.5, 1, 1.2, 1, 1, 1, 1, 1),
        "walk_forward_summary": {
            "average_validation_net_usdc_per_day": -100.0,
            "worst_fold_net_usdc_per_day": 0.0,
            "positive_fold_count": 6,
            "aggregate_metrics": {
                "net_usdc_per_day": 0.1,
                "profit_factor": 1.2,
                "max_drawdown_usdc": 1.0,
                "fees_usdc": 1.0,
                "slippage_usdc": 1.0,
            },
        },
    }

    ranked = rank_with_walk_forward([misleading_average, better_aggregate])

    assert ranked[0]["candidate_id"] == "better"


def test_walk_forward_ranking_uses_aggregate_profit_factor_and_drawdown_tiebreakers():
    def record(candidate_id: str, profit_factor: float, drawdown: float) -> dict[str, object]:
        return {
            "candidate_id": candidate_id,
            "candidate": StrategyCandidate(candidate_id, {}),
            "validation_metrics": BacktestMetrics(1, 1, 10, 0.5, 1, 1.2, 1, 1, 1, 1, 1),
            "walk_forward_summary": {
                "worst_fold_net_usdc_per_day": 0.0,
                "positive_fold_count": 6,
                "aggregate_metrics": {
                    "net_usdc_per_day": 1.0,
                    "profit_factor": profit_factor,
                    "max_drawdown_usdc": drawdown,
                    "fees_usdc": 1.0,
                    "slippage_usdc": 1.0,
                },
            },
        }

    ranked = rank_with_walk_forward(
        [
            record("lower_pf", 1.1, 1.0),
            record("higher_pf_higher_dd", 1.2, 10.0),
            record("higher_pf_lower_dd", 1.2, 5.0),
        ]
    )

    assert [row["candidate_id"] for row in ranked] == [
        "higher_pf_lower_dd",
        "higher_pf_higher_dd",
        "lower_pf",
    ]


def test_walk_forward_frontier_evaluates_multiple_ranked_candidates():
    records = [
        {
            "candidate_id": f"candidate_{index}",
            "candidate": StrategyCandidate("always_long", {"max_hold_minutes": index + 1}),
            "validation_metrics": BacktestMetrics(1, 1, 10, 0.5, 1, 1.2, 0.1, 1, 1, 1, 1),
        }
        for index in range(4)
    ]

    evaluated = evaluate_walk_forward_frontier(
        _intraday_candles(8),
        records,
        candidate_limit=3,
        fold_count=2,
        training_days=8,
        blindtest_days=0,
        expected_candles_per_day=10,
    )

    assert [row["candidate_id"] for row in evaluated] == ["candidate_0", "candidate_1", "candidate_2"]
    assert all(row["walk_forward_summary"]["fold_count"] == 2 for row in evaluated)
    assert all(row["walk_forward_summary"]["ranking_uses_blindtest"] is False for row in evaluated)


def test_walk_forward_sample_uses_actual_simulated_calendar_day_denominator():
    summary = evaluate_walk_forward(
        _intraday_candles(9),
        StrategyCandidate("always_long", {"max_hold_minutes": 1}),
        fold_count=1,
        training_days=730,
        blindtest_days=365,
        max_candles_per_fold=20,
        expected_candles_per_day=10,
    )

    fold = summary["folds"][0]
    assert fold["simulated_validation_days"] == 2
    assert fold["sampled_validation_candles"] == 20
    assert fold["metrics"]["net_usdc_per_day"] == pytest.approx(
        fold["metrics"]["net_profit_usdc"] / 2
    )


def test_walk_forward_sampling_rejects_partial_day_cap():
    with pytest.raises(ValueError, match="smaller than one complete UTC validation day"):
        evaluate_walk_forward(
            _intraday_candles(9),
            StrategyCandidate("always_long", {"max_hold_minutes": 1}),
            fold_count=1,
            max_candles_per_fold=5,
            expected_candles_per_day=10,
        )


def test_rolling_origin_evaluation_never_uses_final_audit_window():
    plan = build_research_window_plan(
        _daily_candles(8), training_days=4, blindtest_days=2, rolling_step_days=2
    )

    summary = evaluate_rolling_origins(
        list(plan.historical_origins), StrategyCandidate("always_long", {"max_hold_minutes": 1})
    )

    assert summary["origin_count"] == 1
    assert summary["uses_final_audit"] is False
    assert summary["pipeline_refit_per_origin"] is False
    assert summary["eligible_as_quality_gate_evidence"] is False
    assert summary["origins"][0]["uses_final_audit"] is False
    assert summary["origins"][0]["oos_end"] < plan.final_window.blind_start
