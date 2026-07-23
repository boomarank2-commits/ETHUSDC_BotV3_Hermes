from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
from ethusdc_bot.backtest.equity import EquityPoint
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3 import boundaries, inner_folds
from ethusdc_bot.protocol_v3 import production_fold_evaluator as evaluator
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy

REPO_ROOT = Path(__file__).resolve().parents[2]
HORIZON = HorizonPolicy(10_080, 10_080, 2)


def _candle(timestamp: int) -> Candle:
    return Candle(timestamp, 100.0, 101.0, 99.0, 100.0, 1.0)


@pytest.fixture
def fold_plan():
    origin = boundaries.build_monthly_process_boundary_plan(
        "2026-07-08"
    ).origins[0]
    return inner_folds.build_inner_fold_plan_for_origin(
        origin, HORIZON, repo_root=REPO_ROOT
    )


@pytest.fixture
def evaluation(fold_plan, monkeypatch: pytest.MonkeyPatch):
    def fake_slice(context, *, start_ms, end_ms):
        candle = _candle(start_ms)
        return AlignedMarketCandles((candle,), (candle,), (candle,))

    def fake_simulator(candles, candidate, **kwargs):
        start_ms = candles[0].open_time
        points = [EquityPoint(start_ms, 0.0)]
        for index in range(60):
            points.append(
                EquityPoint(
                    start_ms + (index + 1) * 86_400_000 - 1,
                    round((index + 1) * 0.1, 10),
                )
            )
        metrics = SimpleNamespace(
            trade_count=0,
            net_profit_usdc=6.0,
            net_usdc_per_day=0.1,
            fees_usdc=0.0,
            slippage_usdc=0.0,
            max_drawdown_usdc=0.0,
            profit_factor=0.0,
        )
        return SimpleNamespace(
            equity_curve=tuple(points),
            metrics=metrics,
            trades=[],
            signal_funnel={"observations_total": 86_400},
            rejection_reasons={},
        )

    monkeypatch.setattr(evaluator, "_slice_fold_context", fake_slice)
    monkeypatch.setattr(
        evaluator, "simulate_protocol_v3_intrabar_strategy", fake_simulator
    )
    candle = _candle(0)
    context = AlignedMarketCandles((candle,), (candle,), (candle,))
    return evaluator.evaluate_candidate_on_inner_folds(
        context=context,
        candidate=StrategyCandidate(
            "momentum_trend_filter",
            {"symbol": "ETHUSDC", "max_hold_minutes": 120},
        ),
        fold_plan=fold_plan,
        exchange_info_snapshot={},
        horizon_policy=HORIZON,
    )


def test_exact_six_by_sixty_evaluation_and_matrix_projection(
    evaluation, fold_plan
) -> None:
    payload = evaluation.to_dict()
    assert payload["aggregate"]["validation_days"] == 360
    assert payload["aggregate"]["net_profit_usdc"] == pytest.approx(36.0)
    assert len(payload["folds"]) == 6
    assert all(len(row["daily_net_mtm_usdc"]) == 60 for row in payload["folds"])
    assert len(evaluation.candidate_matrix_folds) == 6
    assert evaluator.validate_production_fold_evaluation(
        evaluation, fold_plan=fold_plan
    ) == evaluation
    assert payload["safety"]["orders"] == "locked"


def test_tampered_daily_mtm_and_fold_identity_fail_closed(
    evaluation, fold_plan
) -> None:
    bad_daily = deepcopy(evaluation.to_dict())
    bad_daily["folds"][0]["daily_net_mtm_usdc"][0]["net_usdc"] = "fake"
    with pytest.raises(
        evaluator.ProductionFoldEvaluationError,
        match="provenance or day count",
    ):
        evaluator.validate_production_fold_evaluation(
            bad_daily, fold_plan=fold_plan
        )

    bad_plan = deepcopy(evaluation.to_dict())
    bad_plan["fold_plan_sha256"] = "f" * 64
    with pytest.raises(
        evaluator.ProductionFoldEvaluationError,
        match="another fold plan",
    ):
        evaluator.validate_production_fold_evaluation(
            bad_plan, fold_plan=fold_plan
        )


def test_slice_requires_complete_aligned_minute_grid() -> None:
    start = int(datetime(2026, 7, 1, tzinfo=UTC).timestamp() * 1000)
    candles = tuple(_candle(start + index * 60_000) for index in range(2))
    context = AlignedMarketCandles(candles, candles, candles)
    assert evaluator._slice_fold_context(
        context, start_ms=start, end_ms=start + 120_000
    ).candle_count == 2
    with pytest.raises(
        evaluator.ProductionFoldEvaluationError,
        match="complete fold minute grid",
    ):
        evaluator._slice_fold_context(
            context, start_ms=start, end_ms=start + 180_000
        )


def test_daily_mtm_uses_each_utc_closing_equity_delta() -> None:
    start = datetime(2026, 7, 1, tzinfo=UTC)
    points = (
        EquityPoint(int(start.timestamp() * 1000), 0.0),
        EquityPoint(
            int((start + timedelta(days=1)).timestamp() * 1000) - 1, 1.25
        ),
        EquityPoint(
            int((start + timedelta(days=2)).timestamp() * 1000) - 1, 0.75
        ),
    )
    assert evaluator._daily_mtm(points, start=start, days=2) == [
        {"day": "2026-07-01", "net_usdc": 1.25},
        {"day": "2026-07-02", "net_usdc": -0.5},
    ]
