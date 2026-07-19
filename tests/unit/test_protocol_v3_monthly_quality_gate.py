"""Task-26 tests for the fail-closed monthly process quality gate."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import monthly_quality_gate as gate
from ethusdc_bot.protocol_v3 import monthly_quality_gate_api, outer_mtm_ledger

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK25_PATH = Path(__file__).with_name("test_protocol_v3_outer_mtm_ledger.py")
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task26_support", _TASK25_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
task25 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task25)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, process = task25.state.__wrapped__(tmp_path, monkeypatch)
    baseline = outer_mtm_ledger.build_outer_mtm_ledger(
        plan, process, task25._inputs(plan, process)
    )
    return plan, process, baseline


def _integrity(value: bool = True) -> dict[str, dict[str, object]]:
    return {
        name: {"passed": value, "evidence_sha256": "a" * 64}
        for name in gate._INTEGRITY_FIELDS
    }


def _stress_identity() -> dict[str, object]:
    value = {
        "baseline_fee_bps_per_side": 10,
        "baseline_slippage_bps_per_side": 5,
        "joint_fee_bps_per_side": 15,
        "joint_slippage_bps_per_side": 10,
        "slippage_fee_bps_per_side": 10,
        "slippage_slippage_bps_per_side": 15,
        "same_execution_simulator": True,
    }
    return {**value, "evidence_sha256": gate._digest(value)}


def _regime() -> dict[str, object]:
    value = {
        "definition": "trend_sign_x_training_median_volatility",
        "threshold_source": "training_only",
        "assignment_uses_entry_time_trailing_data_only": True,
        "regime_count": 4,
        "min_trades_per_regime": 20,
        "positive_regime_count": 3,
        "regimes_pf_at_least_1_05": 3,
        "worst_regime_profit_factor": 0.9,
        "worst_regime_net_usdc": -5,
        "max_positive_pnl_share": 0.6,
    }
    return {**value, "evidence_sha256": gate._digest(value)}


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = gate.load_monthly_quality_gate_contract(REPO_ROOT)
    assert contract["contract_version"] == gate.CONTRACT_VERSION
    assert contract["target_policy"]["historical_result_is_diagnostic_only"] is True
    assert monthly_quality_gate_api.__all__ == gate.__all__
    pipeline = json.loads(
        (REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text()
    )
    assert gate.CONTRACT_VERSION in pipeline["component_contracts"]["quality_gates"]
    for path in (
        "configs/protocol_v3_monthly_quality_gate_contract.json",
        "src/ethusdc_bot/protocol_v3/monthly_quality_gate.py",
        "src/ethusdc_bot/protocol_v3/monthly_quality_gate_api.py",
    ):
        assert path in pipeline["source_bindings"]["quality_gates"]


def test_no_trade_process_is_honest_red_not_green_or_yellow(state) -> None:
    plan, process, baseline = state
    report = gate.evaluate_monthly_quality_gate(
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        joint_stress_ledger=baseline,
        slippage_stress_ledger=baseline,
        stress_identity_evidence=_stress_identity(),
        regime_evidence={},
        integrity_evidence=_integrity(),
    )
    payload = report.to_dict()
    assert payload["status"] == gate.RED
    assert payload["historically_hit"] is False
    assert payload["robustness_passed"] is False
    assert payload["statistically_supported"] is False
    assert payload["canonical_adoption_eligible"] is False
    assert all(
        row["passed"]
        for row in payload["checks"]
        if row["code"].startswith("inner.origin_")
    )
    assert "outer.trade_count" in payload["failed_check_codes"]
    assert "regime.complete" in payload["failed_check_codes"]
    assert (
        gate.validate_monthly_quality_gate_report(
            payload,
            boundary_plan=plan,
            outer_process=process,
            baseline_ledger=baseline,
            joint_stress_ledger=baseline,
            slippage_stress_ledger=baseline,
            stress_identity_evidence=_stress_identity(),
            regime_evidence={},
            integrity_evidence=_integrity(),
        )
        == report
    )


def test_all_frozen_threshold_families_have_a_passing_boundary_fixture() -> None:
    metrics = {
        "net_usdc": gate.Decimal("1095"),
        "trade_count": 120,
        "profit_factor": gate.Decimal("1.25"),
        "average_trade": gate.Decimal("0.01"),
        "drawdown": gate.Decimal("15"),
        "underwater_days": 60,
        "top1": gate.Decimal("0.10"),
        "top5": gate.Decimal("0.35"),
        "net_without_top5": gate.Decimal("1"),
        "pf_without_top5": gate.Decimal("1.05"),
        "friction_share": gate.Decimal("0.40"),
        "max_no_trade_gap": 30,
    }
    deployments = [{"net_mtm_usdc": "1", "active": True} for _ in range(12)]
    months = [
        {"net_mtm_usdc": "1", "positive": True, "active": True} for _ in range(13)
    ]
    quarters = [
        {"net_mtm_usdc": "1", "positive": True, "active": True, "exit_trade_count": 20}
        for _ in range(5)
    ]
    baseline = {
        "deployment_intervals": deployments,
        "calendar_months": months,
        "calendar_quarters": quarters,
    }
    regime = _regime()
    checks = (
        gate._outer_checks(metrics)
        + gate._deployment_checks(baseline)
        + gate._calendar_checks(baseline, metrics)
    )
    checks += gate._concentration_checks(metrics) + gate._stress_checks(
        metrics, metrics, metrics
    )
    checks += gate._stress_identity_checks(_stress_identity())
    checks += gate._regime_checks(regime) + gate._integrity_checks(_integrity())
    assert checks
    assert all(row["passed"] for row in checks)


def test_one_failure_in_each_evidence_family_is_fail_closed() -> None:
    assert (
        gate._outer_checks(
            {
                "trade_count": 119,
                "profit_factor": gate.Decimal("1.25"),
                "average_trade": gate.Decimal("1"),
                "drawdown": gate.Decimal("1"),
                "underwater_days": 1,
                "net_usdc": gate.Decimal("1"),
            }
        )[0]["passed"]
        is False
    )
    assert gate._integrity_checks(_integrity(False))[0]["passed"] is False
    assert gate._regime_checks({})[0]["passed"] is False


def test_rehashed_green_or_final_claim_on_historical_report_is_rejected(state) -> None:
    plan, process, baseline = state
    payload = gate.evaluate_monthly_quality_gate(
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        joint_stress_ledger=baseline,
        slippage_stress_ledger=baseline,
        stress_identity_evidence=_stress_identity(),
        regime_evidence={},
        integrity_evidence=_integrity(),
    ).to_dict()
    bad = deepcopy(payload)
    bad["status"] = gate.GREEN
    bad["statistically_supported"] = True
    basis = dict(bad)
    basis.pop("report_sha256")
    bad["report_sha256"] = gate._digest(basis)
    with pytest.raises(gate.MonthlyQualityGateError):
        gate.validate_monthly_quality_gate_report(
            bad,
            boundary_plan=plan,
            outer_process=process,
            baseline_ledger=baseline,
            joint_stress_ledger=baseline,
            slippage_stress_ledger=baseline,
            stress_identity_evidence=_stress_identity(),
            regime_evidence={},
            integrity_evidence=_integrity(),
        )


def test_changed_or_unvalidated_ledger_cannot_reuse_gate_report(state) -> None:
    plan, process, baseline = state
    bad = deepcopy(baseline.to_dict())
    bad["daily_mtm"][0]["net_mtm_usdc"] = "1"
    with pytest.raises(Exception):
        gate.evaluate_monthly_quality_gate(
            boundary_plan=plan,
            outer_process=process,
            baseline_ledger=bad,
            joint_stress_ledger=baseline,
            slippage_stress_ledger=baseline,
            stress_identity_evidence=_stress_identity(),
            regime_evidence={},
            integrity_evidence=_integrity(),
        )
