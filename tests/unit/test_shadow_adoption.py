"""Final-report assessment and order-free Shadow adoption tests.

The ``_final_report`` fixture is also the executable producer contract for the
future sealed-holdout runner: the report has exact top-level keys, a canonical
candidate signature, complete final-stage gate evidence, the freshly computed
gate report, and the canonical locked safety declaration.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from statistics import median, pstdev

import pytest

from ethusdc_bot.backtest.quality_gates import evaluate_quality_gates
from ethusdc_bot.backtest.research_protocol import safety_status
from ethusdc_bot.shadow.adoption import (
    FINAL_REPORT_KEYS,
    ShadowAdoptionError,
    adopt_for_shadow,
    assess_final_report,
)
from ethusdc_bot.shadow.schema import canonical_signature_payload
from ethusdc_bot.shadow.store import (
    load_deployment,
    load_shadow_state,
    read_event_log,
)


def _passing_evidence() -> dict[str, object]:
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
    return {
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
                "net_profit_usdc": sum(fold["metrics"]["net_profit_usdc"] for fold in folds),
                "net_usdc_per_day": sum(fold["metrics"]["net_profit_usdc"] for fold in folds)
                / sum(fold["days"] for fold in folds),
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
        "final": {
            "sealed_holdout_evaluations": 1,
            "trade_count": 140,
            "net_usdc_per_day": 3.20,
            "profit_factor": 1.30,
            "average_trade_usdc": 0.25,
            "max_drawdown_usdc": 12.0,
            "drawdown_method": "mark_to_market",
        },
    }


def _final_report(*, final_net_usdc_per_day: float = 3.20) -> dict[str, object]:
    params = {
        "symbol": "ETHUSDC",
        "side": "LONG",
        "lookback": 60,
        "threshold_bps": 20,
    }
    evidence = _passing_evidence()
    evidence["final"]["net_usdc_per_day"] = final_net_usdc_per_day
    report = {
        "schema_version": 1,
        "report_type": "final_evaluation",
        "final_evaluation_id": "final_20260711T080000Z",
        "created_at_utc": "2026-07-11T08:00:00Z",
        "git_commit": "c2b65c8",
        "source_research_run_id": "research_loop_20260711T070000Z",
        "candidate": {
            "candidate_id": "momentum_final_001",
            "family": "momentum",
            "params": params,
            "candidate_signature": canonical_signature_payload("momentum", params),
        },
        "quality_gate_evidence": evidence,
        "quality_gate": evaluate_quality_gates(evidence, stage="final").to_dict(),
        "safety": safety_status(),
    }
    assert set(report) == FINAL_REPORT_KEYS
    return report


def _write_report(tmp_path, report: dict[str, object], name: str = "final.json"):
    path = tmp_path / name
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def test_green_requires_all_final_quality_gates_including_target(tmp_path):
    path = _write_report(tmp_path, _final_report())

    assessment = assess_final_report(path)

    assert assessment.color == "green"
    assert assessment.shadow_eligible is True
    assert assessment.target_reached is True
    assert assessment.live_eligible is False
    assert assessment.reason_codes == ("all_quality_gates_passed",)


def test_yellow_is_allowed_only_when_final_target_is_the_sole_failed_check(tmp_path):
    report = _final_report(final_net_usdc_per_day=2.50)
    path = _write_report(tmp_path, report)

    assessment = assess_final_report(path)

    failed = {
        check["code"]
        for check in assessment.recomputed_quality_gate["checks"]
        if not check["passed"]
    }
    assert failed == {"final.target"}
    assert assessment.color == "yellow"
    assert assessment.shadow_eligible is True
    assert assessment.target_reached is False
    assert assessment.live_eligible is False


def test_yellow_report_can_be_adopted_for_shadow_but_never_live(tmp_path):
    report_path = _write_report(tmp_path, _final_report(final_net_usdc_per_day=2.50))

    result = adopt_for_shadow(report_path, 100, tmp_path / "state")

    assert result.deployment["assessment"]["color"] == "yellow"
    assert result.deployment["assessment"]["shadow_eligible"] is True
    assert result.deployment["assessment"]["live_eligible"] is False
    assert result.deployment["safety"]["live"] == "locked"
    assert result.deployment["safety"]["orders_enabled"] is False


def test_any_non_target_gate_failure_is_red_and_not_eligible(tmp_path):
    report = _final_report(final_net_usdc_per_day=2.50)
    report["quality_gate_evidence"]["final"]["profit_factor"] = 1.0
    report["quality_gate"] = evaluate_quality_gates(
        report["quality_gate_evidence"], stage="final"
    ).to_dict()
    path = _write_report(tmp_path, report)

    assessment = assess_final_report(path)

    assert assessment.color == "red"
    assert assessment.shadow_eligible is False
    assert "gate_failed:final.profit_factor" in assessment.reason_codes


@pytest.mark.parametrize("mutation", ["forged_gate", "forged_signature", "second_holdout", "unknown_field"])
def test_final_report_tampering_or_noncanonical_shape_fails_closed(tmp_path, mutation):
    report = _final_report()
    if mutation == "forged_gate":
        report["quality_gate"]["passed"] = False
    elif mutation == "forged_signature":
        report["candidate"]["candidate_signature"]["family"] = "breakout"
    elif mutation == "second_holdout":
        report["quality_gate_evidence"]["final"]["sealed_holdout_evaluations"] = 2
        report["quality_gate"] = evaluate_quality_gates(
            report["quality_gate_evidence"], stage="final"
        ).to_dict()
    else:
        report["candidate_adoptable"] = True
    path = _write_report(tmp_path, report, f"{mutation}.json")

    assessment = assess_final_report(path)

    assert assessment.color == "red"
    assert assessment.shadow_eligible is False
    assert assessment.reason_codes == ("invalid_final_evaluation_report",)


def test_research_loop_report_is_not_an_explicit_final_evaluation(tmp_path):
    path = _write_report(
        tmp_path,
        {
            "schema_version": 2,
            "loop_run_id": "research_loop_1",
            "freeze_status": "frozen_for_separate_sealed_holdout",
            "frozen_candidate": {"candidate_id": "not_final"},
        },
    )

    assert assess_final_report(path).color == "red"


@pytest.mark.parametrize("budget", [100, 200, 500, 1000])
def test_adoption_atomically_persists_fixed_lot_policy_and_hash_bound_receipt(tmp_path, budget):
    report_path = _write_report(tmp_path, _final_report())
    source_bytes = report_path.read_bytes()
    state_root = tmp_path / "external_shadow_state"

    result = adopt_for_shadow(report_path, budget, state_root)

    assert result.deployment_dir.parent == state_root
    assert sorted(path.name for path in result.deployment_dir.iterdir()) == [
        "deployment.json",
        "events.jsonl",
        "state.json",
    ]
    deployment = load_deployment(result.deployment_path)
    state = load_shadow_state(result.state_path)
    events = read_event_log(result.events_path)
    assert deployment["source_report"]["sha256"] == sha256(source_bytes).hexdigest()
    policy = deployment["portfolio_policy"]["policy"]
    assert policy["lot_notional_usdc"] == 100.0
    assert policy["deployment_budget_usdc"] == budget
    assert policy["max_concurrent_lots"] == budget // 100
    assert policy["compounding_enabled"] is False
    assert deployment["safety"]["orders_enabled"] is False
    assert deployment["safety"]["trading_api_enabled"] is False
    assert deployment["safety"]["api_keys_used"] is False
    assert deployment["assessment"]["live_eligible"] is False
    assert state["phase"] == "adopted_stopped"
    assert state["event_count"] == 1
    assert state["last_event_hash"] == events[0]["event_hash"]
    assert events[0]["event_type"] == "deployment_adopted"
    assert events[0]["payload"]["orders_enabled"] is False
    assert list(state_root.glob(".*.tmp")) == []


@pytest.mark.parametrize("budget", [0, -100, 50, 150, 100.0, True])
def test_adoption_rejects_invalid_budget_without_creating_a_deployment(tmp_path, budget):
    report_path = _write_report(tmp_path, _final_report())
    state_root = tmp_path / "state"

    with pytest.raises(ShadowAdoptionError):
        adopt_for_shadow(report_path, budget, state_root)

    assert not state_root.exists()


def test_red_report_cannot_be_adopted(tmp_path):
    report = _final_report()
    report["quality_gate_evidence"]["final"]["net_usdc_per_day"] = -0.1
    report["quality_gate"] = evaluate_quality_gates(
        report["quality_gate_evidence"], stage="final"
    ).to_dict()
    report_path = _write_report(tmp_path, report)

    with pytest.raises(ShadowAdoptionError, match="not Shadow-eligible"):
        adopt_for_shadow(report_path, 100, tmp_path / "state")
