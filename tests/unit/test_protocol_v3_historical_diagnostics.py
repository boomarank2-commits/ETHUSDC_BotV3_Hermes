"""Task-27 tests for hindsight capture diagnostics and stationary bootstrap."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import historical_diagnostics as diagnostics
from ethusdc_bot.protocol_v3 import historical_diagnostics_api, monthly_quality_gate

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK26_PATH = Path(__file__).with_name("test_protocol_v3_monthly_quality_gate.py")
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task27_support", _TASK26_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
task26 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task26)


def _benchmark(all_value="1", matched="1", max_roundtrips=1):
    constraints = {name: True for name in diagnostics._MATCHED_CONSTRAINTS}
    basis = {
        "all_candle_one_trade_close_hindsight_usdc_per_day": all_value,
        "candidate_matched_volume_filtered_hindsight_usdc_per_day": matched,
        "candidate_max_roundtrips_per_day": max_roundtrips,
        "candidate_matched_constraints": constraints,
    }
    return {**basis, "evidence_sha256": diagnostics._digest(basis)}


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, process, baseline = task26.state.__wrapped__(tmp_path, monkeypatch)
    gate = monthly_quality_gate.evaluate_monthly_quality_gate(
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        joint_stress_ledger=baseline,
        slippage_stress_ledger=baseline,
        stress_identity_evidence=task26._stress_identity(),
        regime_evidence={},
        integrity_evidence=task26._integrity(),
    )
    report = diagnostics.build_historical_diagnostics(
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        monthly_quality_report=gate,
        data_identity_sha256="1" * 64,
        code_commit="2" * 64,
        pipeline_generation_id="fixture_generation",
        benchmark_evidence=_benchmark(),
    )
    return plan, process, baseline, gate, report


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = diagnostics.load_historical_diagnostics_contract(REPO_ROOT)
    assert contract["bootstrap_policy"]["replications"] == 10_000
    assert contract["bootstrap_policy"]["expected_block_lengths"] == [5, 10, 20]
    assert historical_diagnostics_api.__all__ == diagnostics.__all__
    pipeline = json.loads(
        (REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text()
    )
    for path in (
        "configs/protocol_v3_historical_diagnostics_contract.json",
        "src/ethusdc_bot/protocol_v3/historical_diagnostics.py",
        "src/ethusdc_bot/protocol_v3/historical_diagnostics_api.py",
    ):
        assert path in pipeline["source_bindings"]["quality_gates"]


def test_zero_history_bootstrap_and_capture_are_honest_diagnostics(state) -> None:
    plan, process, baseline, gate_report, report = state
    payload = report.to_dict()
    assert [row["expected_block_length"] for row in payload["bootstrap_results"]] == [
        5,
        10,
        20,
    ]
    assert all(row["replications"] == 10_000 for row in payload["bootstrap_results"])
    assert all(
        row["lower_bound_usdc_per_day"] == "0" for row in payload["bootstrap_results"]
    )
    assert payload["historical_bootstrap_lower_bound"] is False
    assert payload["benchmarks"]["all_candle_one_trade_capture_ratio_diagnostic"] == "0"
    assert payload["benchmarks"]["candidate_matched_tradeable_capture_ratio"] == "0"
    assert payload["freshness"] == "NOT_FRESH"
    assert payload["statistically_supported"] is False
    assert payload["sealed_bootstrap_target_supported"] is False
    assert payload["canonical_adoption_eligible"] is False
    assert (
        diagnostics.validate_historical_diagnostics(
            payload,
            boundary_plan=plan,
            outer_process=process,
            baseline_ledger=baseline,
            monthly_quality_report=gate_report,
            data_identity_sha256="1" * 64,
            code_commit="2" * 64,
            pipeline_generation_id="fixture_generation",
            benchmark_evidence=_benchmark(),
        )
        == report
    )


def test_constant_three_series_uses_exact_500th_order_statistic() -> None:
    result = diagnostics._stationary_bootstrap([Decimal("3")] * 365, 123)
    assert all(row["lower_bound_usdc_per_day"] == "3" for row in result)
    assert all(row["order_statistic_one_based"] == 500 for row in result)


def test_manifest_seed_is_deterministic_and_excludes_outputs(state) -> None:
    _, _, _, _, report = state
    payload = report.to_dict()
    manifest = payload["pre_bootstrap_input_manifest"]
    digest = diagnostics._digest(manifest)
    assert payload["pre_bootstrap_input_manifest_sha256"] == digest
    assert payload["seed_uint64"] == int(digest[:16], 16)
    assert "bootstrap_results" not in manifest
    assert "report_sha256" not in manifest


def test_candidate_matched_constraints_and_benchmark_digest_fail_closed() -> None:
    bad = _benchmark()
    bad["candidate_matched_constraints"]["same_costs"] = False
    basis = dict(bad)
    basis.pop("evidence_sha256")
    bad["evidence_sha256"] = diagnostics._digest(basis)
    with pytest.raises(diagnostics.HistoricalDiagnosticsError, match="constraints"):
        diagnostics._benchmarks(bad, Decimal("1"))
    tampered = _benchmark()
    tampered["candidate_max_roundtrips_per_day"] = 2
    with pytest.raises(diagnostics.HistoricalDiagnosticsError, match="digest"):
        diagnostics._benchmarks(tampered, Decimal("1"))


def test_rehashed_fresh_statistical_or_adoption_claim_is_rejected(state) -> None:
    plan, process, baseline, gate_report, report = state
    bad = deepcopy(report.to_dict())
    bad["freshness"] = "FRESH"
    bad["statistically_supported"] = True
    bad["sealed_bootstrap_target_supported"] = True
    bad["canonical_adoption_eligible"] = True
    basis = dict(bad)
    basis.pop("report_sha256")
    bad["report_sha256"] = diagnostics._digest(basis)
    with pytest.raises(diagnostics.HistoricalDiagnosticsError):
        diagnostics.validate_historical_diagnostics(
            bad,
            boundary_plan=plan,
            outer_process=process,
            baseline_ledger=baseline,
            monthly_quality_report=gate_report,
            data_identity_sha256="1" * 64,
            code_commit="2" * 64,
            pipeline_generation_id="fixture_generation",
            benchmark_evidence=_benchmark(),
        )
