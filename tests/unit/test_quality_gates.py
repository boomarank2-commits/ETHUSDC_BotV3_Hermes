"""Tests for fail-closed, audit-independent research quality gates."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from statistics import median, pstdev

import pytest

from ethusdc_bot.backtest.quality_gates import QUALITY_GATE_V1, QualityGateV1, evaluate_quality_gates


def _passing_evidence(*, include_final: bool = False) -> dict[str, object]:
    fold_net_values = [0.50 + index * 0.02 for index in range(6)]
    folds = []
    for net_per_day in fold_net_values:
        net_profit = net_per_day * 91
        gross_loss = net_profit / 0.30
        gross_profit = gross_loss + net_profit
        folds.append(
            {
                "days": 91,
                "equity_curve_usdc": [0.0, net_profit + 12.0, net_profit],
                "metrics": {
                    "trade_count": 34,
                    "net_profit_usdc": net_profit,
                    "net_usdc_per_day": net_per_day,
                    "profit_factor": 1.30,
                    "gross_profit_usdc": gross_profit,
                    "gross_loss_usdc": gross_loss,
                    "max_drawdown_usdc": 12.0,
                    "drawdown_method": "mark_to_market",
                },
            }
        )
    fold_mean = sum(fold_net_values) / len(fold_net_values)
    evidence: dict[str, object] = {
        "protocol": {
            "gate_version": "quality_gate_v1",
            "gate_frozen_before_evaluation": True,
            "selection_uses_audit": False,
        },
        "validation": {
            "trade_count": 60,
            "net_usdc_per_day": 0.60,
            "profit_factor": 1.25,
            "max_drawdown_usdc": 9.0,
            "drawdown_method": "mark_to_market",
        },
        "wfv": {
            "fold_count": 6,
            "folds": folds,
            "aggregate": {
                "trade_count": 204,
                "net_profit_usdc": sum(
                    fold["metrics"]["net_profit_usdc"] for fold in folds  # type: ignore[index]
                ),
                "net_usdc_per_day": sum(
                    fold["metrics"]["net_profit_usdc"] for fold in folds  # type: ignore[index]
                )
                / sum(fold["days"] for fold in folds),  # type: ignore[misc]
                "profit_factor": 1.30,
                "max_drawdown_usdc": 12.0,
                "drawdown_method": "mark_to_market",
                "positive_fold_count": 6,
                "folds_pf_at_least_1_05": 6,
                "worst_fold_profit_factor": 1.30,
                "median_fold_net_usdc_per_day": median(fold_net_values),
                "worst_fold_net_usdc_per_day": 0.50,
                "fold_net_coefficient_of_variation": pstdev(fold_net_values) / abs(fold_mean),
                "full_training_net_usdc_per_day": 0.80,
            },
        },
        "rolling": {
            "max_drawdown_usdc": 12.0,
            "drawdown_method": "mark_to_market",
            "max_underwater_days": 40,
            "top1_positive_pnl_share": 0.08,
            "top5_positive_pnl_share": 0.30,
            "net_without_top5_usdc": 10.0,
            "profit_factor_without_top5": 1.10,
        },
        "stress": {
            "baseline": {
                "fee_bps_per_side": 10.0,
                "slippage_bps_per_side": 5.0,
                "net_usdc_per_day": 3.20,
            },
            "joint": {
                "fee_bps_per_side": 15.0,
                "slippage_bps_per_side": 10.0,
                "net_usdc_per_day": 1.80,
                "profit_factor": 1.15,
                "max_drawdown_usdc": 18.0,
                "drawdown_method": "mark_to_market",
            },
            "slippage": {
                "fee_bps_per_side": 10.0,
                "slippage_bps_per_side": 15.0,
                "net_usdc_per_day": 1.20,
                "profit_factor": 1.08,
            },
            "friction_share_of_positive_pre_cost_pnl": 0.35,
        },
        "parameter_stability": {
            "all_numeric_parameters_perturbed": True,
            "numeric_parameter_count": 8,
            "neighbor_count": 16,
            "perturbation_fraction": 0.10,
            "session_hour_step": 1,
            "passing_neighbor_fraction": 0.85,
            "median_net_retention": 0.80,
            "worst_neighbor_net_usdc_per_day": 0.05,
        },
        "temporal": {
            "months_observed": 12,
            "positive_months": 10,
            "active_months": 12,
            "max_no_trade_gap_days": 20,
            "quarters_observed": 4,
            "positive_quarters": 4,
            "min_quarter_trade_count": 25,
            "worst_month_net_usdc": -2.0,
        },
        "regime": {
            "definition": "trend_sign_x_training_median_volatility",
            "threshold_source": "training_only",
            "assignment_uses_entry_time_trailing_data_only": True,
            "regime_count": 4,
            "min_trades_per_regime": 22,
            "positive_regime_count": 3,
            "regimes_pf_at_least_1_05": 3,
            "worst_regime_profit_factor": 0.95,
            "worst_regime_net_usdc": -3.0,
            "max_positive_pnl_share": 0.50,
        },
    }
    if include_final:
        evidence["final"] = {
            "sealed_holdout_evaluations": 1,
            "trade_count": 140,
            "net_usdc_per_day": 3.20,
            "profit_factor": 1.30,
            "average_trade_usdc": 0.25,
            "max_drawdown_usdc": 12.0,
            "drawdown_method": "mark_to_market",
        }
    return evidence


def test_quality_gate_v1_is_immutable_and_fixes_baseline_costs():
    assert QUALITY_GATE_V1.version == "quality_gate_v1"
    assert QUALITY_GATE_V1.baseline_fee_bps_per_side == 10.0
    assert QUALITY_GATE_V1.baseline_slippage_bps_per_side == 5.0

    with pytest.raises(FrozenInstanceError):
        QUALITY_GATE_V1.min_final_trades = 1  # type: ignore[misc]
    with pytest.raises(TypeError):
        QualityGateV1(min_final_trades=1)  # type: ignore[call-arg]


def test_missing_evidence_fails_closed_and_report_is_json_serializable():
    report = evaluate_quality_gates({}, stage="selection")

    assert report.passed is False
    assert report.status == "fail_missing_evidence"
    assert "validation.trade_count" in report.missing_evidence
    assert "wfv.folds" in report.missing_evidence
    assert report.stage_readiness["sealed_holdout_ready"] is False
    assert report.stage_readiness["candidate_adoption_ready"] is False
    assert report.stage_readiness["live_ready"] is False
    json.dumps(report.to_dict(), allow_nan=False)


def test_complete_selection_evidence_can_be_ready_for_one_sealed_holdout():
    report = evaluate_quality_gates(_passing_evidence(), stage="selection")

    assert report.passed is True
    assert report.status == "pass"
    assert report.stage_readiness == {
        "research_evidence_complete": True,
        "sealed_holdout_ready": True,
        "candidate_adoption_ready": False,
        "live_ready": False,
    }


def test_missing_and_passing_selection_reports_use_the_same_canonical_check_order():
    missing = evaluate_quality_gates({}, stage="selection")
    passing = evaluate_quality_gates(_passing_evidence(), stage="selection")

    assert [check.code for check in missing.checks] == [check.code for check in passing.checks]


@pytest.mark.parametrize(
    ("field", "poisoned_value"),
    [
        ("trade_count", 999),
        ("net_profit_usdc", 999.0),
        ("net_usdc_per_day", 0.75),
        ("profit_factor", 999.0),
        ("max_drawdown_usdc", 0.0),
        ("positive_fold_count", 7),
        ("folds_pf_at_least_1_05", 7),
        ("worst_fold_profit_factor", 1.31),
        ("median_fold_net_usdc_per_day", 0.56),
        ("worst_fold_net_usdc_per_day", 0.51),
        ("fold_net_coefficient_of_variation", 0.01),
    ],
)
def test_wfv_aggregate_must_match_values_derived_from_folds(field, poisoned_value):
    evidence = _passing_evidence()
    evidence["wfv"]["aggregate"][field] = poisoned_value  # type: ignore[index]

    report = evaluate_quality_gates(evidence, stage="selection")

    consistency = next(check for check in report.checks if check.code == "wfv.fold_derived_consistency")
    assert report.passed is False
    assert report.status == "fail_invalid_evidence"
    assert f"wfv.aggregate.{field}" in report.invalid_evidence
    assert report.stage_readiness["research_evidence_complete"] is False
    assert consistency.passed is False
    assert consistency.reason == "aggregate_fold_mismatch"


def test_invalid_fold_metric_is_tracked_as_incomplete_selection_evidence():
    evidence = _passing_evidence()
    evidence["wfv"]["folds"][0]["metrics"]["net_profit_usdc"] = "not-a-number"  # type: ignore[index]

    report = evaluate_quality_gates(evidence, stage="selection")

    assert report.status == "fail_invalid_evidence"
    assert "wfv.folds[0].metrics.net_profit_usdc" in report.invalid_evidence
    assert report.stage_readiness["research_evidence_complete"] is False
    assert report.stage_readiness["sealed_holdout_ready"] is False


def test_missing_fold_metric_is_tracked_as_incomplete_selection_evidence():
    evidence = _passing_evidence()
    del evidence["wfv"]["folds"][0]["metrics"]["net_profit_usdc"]  # type: ignore[index]

    report = evaluate_quality_gates(evidence, stage="selection")

    assert report.status == "fail_missing_evidence"
    assert "wfv.folds[0].metrics.net_profit_usdc" in report.missing_evidence
    assert report.stage_readiness["research_evidence_complete"] is False


def test_final_stage_requires_final_evidence_and_exactly_one_sealed_evaluation():
    missing = evaluate_quality_gates(_passing_evidence(), stage="final")
    repeated_evidence = _passing_evidence(include_final=True)
    repeated_evidence["final"]["sealed_holdout_evaluations"] = 2  # type: ignore[index]
    repeated = evaluate_quality_gates(repeated_evidence, stage="final")

    assert "final.trade_count" in missing.missing_evidence
    assert missing.stage_readiness["candidate_adoption_ready"] is False
    assert repeated.passed is False
    assert any(check.code == "final.single_sealed_evaluation" and not check.passed for check in repeated.checks)


def test_all_final_gates_must_pass_before_candidate_adoption_readiness():
    report = evaluate_quality_gates(_passing_evidence(include_final=True), stage="final")

    assert report.passed is True
    assert report.stage_readiness["candidate_adoption_ready"] is True
    assert report.stage_readiness["live_ready"] is False
    assert report.to_dict()["safety"]["candidate_adoptable"] is False
    assert report.to_dict()["safety"]["candidate_ready_for_human_adoption_review"] is True


@pytest.mark.parametrize(
    ("section", "nested_section", "check_code"),
    [
        ("validation", None, "validation.drawdown_method"),
        ("wfv", "aggregate", "wfv.drawdown_method"),
        ("rolling", None, "rolling.drawdown_method"),
        ("stress", "joint", "stress.joint_drawdown_method"),
    ],
)
def test_closed_trade_drawdown_evidence_never_passes(section, nested_section, check_code):
    evidence = _passing_evidence()
    target = evidence[section]
    if nested_section is not None:
        target = target[nested_section]  # type: ignore[index]
    target["drawdown_method"] = "closed_trade"  # type: ignore[index]

    report = evaluate_quality_gates(evidence, stage="selection")

    assert report.passed is False
    assert any(check.code == check_code and not check.passed for check in report.checks)
    assert report.stage_readiness["sealed_holdout_ready"] is False


def test_final_closed_trade_drawdown_evidence_never_passes():
    evidence = _passing_evidence(include_final=True)
    evidence["final"]["drawdown_method"] = "closed_trade"  # type: ignore[index]

    report = evaluate_quality_gates(evidence, stage="final")

    assert report.passed is False
    assert any(check.code == "final.drawdown_method" and not check.passed for check in report.checks)
    assert report.stage_readiness["candidate_adoption_ready"] is False


def test_temporal_gate_scales_month_and_quarter_ratios_beyond_minimum_window():
    evidence = _passing_evidence()
    evidence["temporal"].update(  # type: ignore[union-attr]
        {
            "months_observed": 18,
            "positive_months": 14,
            "active_months": 15,
            "quarters_observed": 6,
            "positive_quarters": 6,
        }
    )

    report = evaluate_quality_gates(evidence, stage="selection")

    assert report.passed is True


@pytest.mark.parametrize(
    ("field", "bad_value", "check_code"),
    [
        ("positive_months", 13, "temporal.positive_months"),
        ("active_months", 14, "temporal.active_months"),
        ("positive_quarters", 5, "temporal.positive_quarters"),
    ],
)
def test_temporal_ratios_fail_when_longer_window_dilutes_robustness(field, bad_value, check_code):
    evidence = _passing_evidence()
    evidence["temporal"].update(  # type: ignore[union-attr]
        {
            "months_observed": 18,
            "positive_months": 14,
            "active_months": 15,
            "quarters_observed": 6,
            "positive_quarters": 6,
        }
    )
    evidence["temporal"][field] = bad_value  # type: ignore[index]

    report = evaluate_quality_gates(evidence, stage="selection")

    assert report.passed is False
    assert any(check.code == check_code and not check.passed for check in report.checks)


@pytest.mark.parametrize(
    ("section", "field", "bad_value", "check_code"),
    [
        ("rolling", "top1_positive_pnl_share", 0.11, "rolling.top1_concentration"),
        ("stress", "friction_share_of_positive_pre_cost_pnl", 0.41, "stress.friction_share"),
        ("parameter_stability", "passing_neighbor_fraction", 0.79, "parameter.passing_neighbors"),
        ("temporal", "positive_months", 8, "temporal.positive_months"),
        ("regime", "positive_regime_count", 2, "regime.positive_count"),
    ],
)
def test_any_robustness_failure_blocks_stage_readiness(section, field, bad_value, check_code):
    evidence = _passing_evidence()
    evidence[section][field] = bad_value  # type: ignore[index]

    report = evaluate_quality_gates(evidence, stage="selection")

    assert report.passed is False
    assert report.stage_readiness["sealed_holdout_ready"] is False
    assert any(check.code == check_code and not check.passed for check in report.checks)


def test_protocol_rejects_audit_in_selection_and_unfrozen_gates():
    evidence = _passing_evidence()
    evidence["protocol"]["selection_uses_audit"] = True  # type: ignore[index]
    evidence["protocol"]["gate_frozen_before_evaluation"] = False  # type: ignore[index]

    report = evaluate_quality_gates(evidence, stage="selection")

    assert report.passed is False
    assert any(check.code == "protocol.no_audit_selection" and not check.passed for check in report.checks)
    assert any(check.code == "protocol.gate_frozen" and not check.passed for check in report.checks)
