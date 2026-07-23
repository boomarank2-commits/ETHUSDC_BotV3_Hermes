from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
from ethusdc_bot.backtest.equity import EquityPoint
from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.simulator import SimulationResult, StrategyCandidate
from ethusdc_bot.protocol_v3 import boundaries, inner_folds
from ethusdc_bot.protocol_v3 import production_finalist_quality as quality
from ethusdc_bot.protocol_v3 import production_finalist_quality_api
from ethusdc_bot.protocol_v3.intrabar_execution import BASELINE_COST_PROFILE
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy
from protocol_v3_quality_support import complete_quality_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]
HORIZON = HorizonPolicy(10_080, 10_080, 2)


@pytest.fixture
def plan():
    origin = boundaries.build_monthly_process_boundary_plan(
        "2026-07-08"
    ).origins[0]
    return inner_folds.build_inner_fold_plan_for_origin(
        origin,
        HORIZON,
        repo_root=REPO_ROOT,
    )


def _context(timestamp: int = 0) -> AlignedMarketCandles:
    candle = Candle(timestamp, 100.0, 101.0, 99.0, 100.0, 1.0)
    return AlignedMarketCandles((candle,), (candle,), (candle,))


def _zero_result(timestamp: int, candidate: StrategyCandidate):
    metrics = BacktestMetrics(
        net_profit_usdc=0.0,
        net_usdc_per_day=0.0,
        trade_count=0,
        winrate=0.0,
        max_drawdown_usdc=0.0,
        profit_factor=0.0,
        average_trade_usdc=0.0,
        fees_usdc=0.0,
        slippage_usdc=0.0,
        training_days=730,
        blindtest_days=0,
    )
    return SimulationResult(
        strategy=candidate,
        metrics=metrics,
        trades=[],
        equity_curve=(EquityPoint(timestamp, 0.0),),
        max_underwater_days=0,
        drawdown_method="mark_to_market",
    )


def test_contract_api_and_exact_profile_summary(
    plan,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = quality.load_production_finalist_quality_contract(REPO_ROOT)
    assert contract["evaluation_policy"][
        "simulator"
    ] == "protocol_v3_intrabar_execution"
    assert production_finalist_quality_api.__all__ == quality.__all__

    monkeypatch.setattr(
        quality,
        "_slice_fold_context",
        lambda context, *, start_ms, end_ms: _context(start_ms),
    )
    monkeypatch.setattr(
        quality,
        "_simulate",
        lambda context, candidate, **kwargs: _zero_result(
            context.ethusdc[0].open_time,
            candidate,
        ),
    )
    summary = quality._profile_summary(
        context=_context(),
        candidate=StrategyCandidate(
            "momentum_trend_filter",
            {"symbol": "ETHUSDC", "max_hold_minutes": 120},
        ),
        plan=plan,
        exchange_info_snapshot={},
        horizon_policy=HORIZON,
        cost_profile=BASELINE_COST_PROFILE,
        include_selection_evidence=True,
    )
    assert summary["fold_count"] == 6
    assert all(row["days"] == 60 for row in summary["folds"])
    assert summary["selection_evidence"]["uses_audit_or_holdout"] is False


def test_complete_builder_is_gate_consumable_and_tamper_closed(
    plan,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = complete_quality_evidence()
    baseline = {
        "fold_count": 6,
        "folds": fixture["wfv"]["folds"],
        "aggregate_metrics": fixture["wfv"]["aggregate"],
        "positive_fold_count": fixture["wfv"]["aggregate"][
            "positive_fold_count"
        ],
        "folds_pf_at_least_1_05": fixture["wfv"]["aggregate"][
            "folds_pf_at_least_1_05"
        ],
        "worst_fold_profit_factor": fixture["wfv"]["aggregate"][
            "worst_fold_profit_factor"
        ],
        "median_fold_net_usdc_per_day": fixture["wfv"]["aggregate"][
            "median_fold_net_usdc_per_day"
        ],
        "worst_fold_net_usdc_per_day": fixture["wfv"]["aggregate"][
            "worst_fold_net_usdc_per_day"
        ],
        "fold_net_coefficient_of_variation": fixture["wfv"]["aggregate"][
            "fold_net_coefficient_of_variation"
        ],
        "selection_evidence": {
            "rolling": fixture["rolling"],
            "temporal": fixture["temporal"],
            "regime": fixture["regime"],
            "friction_share_of_positive_pre_cost_pnl": fixture["stress"][
                "friction_share_of_positive_pre_cost_pnl"
            ],
        },
    }
    monkeypatch.setattr(
        quality,
        "_profile_summary",
        lambda **kwargs: baseline,
    )
    monkeypatch.setattr(
        quality,
        "_slice_fold_context",
        lambda context, **kwargs: context,
    )
    metrics = SimpleNamespace(
        net_usdc_per_day=0.25,
        to_dict=lambda: {
            "trade_count": 180,
            "net_profit_usdc": 90.0,
            "net_usdc_per_day": 0.25,
            "profit_factor": 1.5,
            "max_drawdown_usdc": 5.0,
        },
    )
    monkeypatch.setattr(
        quality,
        "_simulate",
        lambda *args, **kwargs: SimpleNamespace(
            metrics=metrics,
            drawdown_method="mark_to_market",
            max_underwater_days=10,
        ),
    )
    monkeypatch.setattr(
        quality,
        "_parameter_stability",
        lambda **kwargs: fixture["parameter_stability"],
    )
    evidence = quality.build_production_finalist_quality_evidence(
        repo_root=REPO_ROOT,
        context=_context(
            int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)
        ),
        candidate=StrategyCandidate(
            "momentum_trend_filter",
            {"symbol": "ETHUSDC", "max_hold_minutes": 120},
        ),
        fold_plan=plan,
        exchange_info_snapshot={},
        horizon_policy=HORIZON,
    )
    assert evidence["protocol"]["target_usdc_per_day_used"] is False
    assert evidence["selection_evidence_provenance"][
        "uses_audit_or_holdout"
    ] is False
    assert quality.validate_production_finalist_quality_evidence(
        evidence
    ) == evidence

    tampered = deepcopy(evidence)
    tampered["wfv"]["folds"].pop()
    with pytest.raises(
        quality.ProductionFinalistQualityError,
        match="6x60",
    ):
        quality.validate_production_finalist_quality_evidence(tampered)

    missing = deepcopy(evidence)
    missing["stress"].pop("joint")
    with pytest.raises(
        quality.ProductionFinalistQualityError,
        match="missing or invalid",
    ):
        quality.validate_production_finalist_quality_evidence(missing)
