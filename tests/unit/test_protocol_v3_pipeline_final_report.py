"""Task-31 final report, crash recovery, and exactly-once regressions."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import pipeline_final_attestation
from ethusdc_bot.protocol_v3 import pipeline_final_report
from ethusdc_bot.protocol_v3 import pipeline_final_report_api
from ethusdc_bot.protocol_v3.reporting import (
    PROTOCOL_V3_PIPELINE_FINAL,
    ProtocolV3Report,
)

_SUPPORT_PATH = Path(__file__).with_name(
    "test_protocol_v3_pipeline_final_attestation.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task31_final_report_support", _SUPPORT_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    built = support.state.__wrapped__(tmp_path, monkeypatch)
    attestation = support._build(built)
    completed = datetime.fromisoformat(
        built["completed_at"][:-1] + "+00:00"
    )
    monkeypatch.setattr(
        pipeline_final_attestation,
        "_utc_now",
        lambda: completed,
    )
    attestation_path = pipeline_final_attestation.write_pipeline_final_attestation(
        attestation,
        built["repo"],
    )
    return {
        **built,
        "attestation": attestation,
        "attestation_path": attestation_path,
        "opened_at": built["completed_at"],
        "opened_dt": completed,
    }


def _open(state):
    return pipeline_final_report.open_pipeline_final_report(
        attestation_path=state["attestation_path"],
        repository_root=state["repo"],
        source_repository_root=support.REPO_ROOT,
        registration=state["registration"],
        claim=state["claim"],
        progress=state["progress"],
        checkpoint=state["checkpoint"],
        boundary_plan=state["plan"],
        outer_process=state["process"],
        baseline_ledger=state["baseline"],
        joint_stress_ledger=state["baseline"],
        slippage_stress_ledger=state["baseline"],
        monthly_quality_report=state["gate"],
        stress_identity_evidence=state["stress_identity"],
        regime_evidence=state["regime_evidence"],
        integrity_evidence=state["integrity_evidence"],
        bound_hindsight_benchmarks=state["bound"],
        opened_at_utc=state["opened_at"],
    )


def test_final_report_is_derived_from_attestation_and_opened_once(
    state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_final_report,
        "_utc_now",
        lambda: state["opened_dt"],
    )
    opened = _open(state)
    payload = opened.report.to_dict()
    manifest = state["registration"].to_dict()["frozen_identity_manifest"]
    assert payload["artifact_kind"] == PROTOCOL_V3_PIPELINE_FINAL
    assert "report_type" not in payload
    assert payload["run_fingerprint"] == manifest["run_fingerprint"]
    assert payload["pipeline_generation"] == manifest["pipeline_generation_id"]
    assert payload["evidence_window"]["calendar_days"] == 365
    assert payload["evidence_status"] == {
        "historically_hit": False,
        "historical_bootstrap_lower_bound": False,
        "freshness": "FRESH_SEALED_FINAL",
        "fresh_pre_registered_sealed_365": True,
        "sealed_bootstrap_target_supported": False,
        "statistically_supported": False,
        "canonical_adoption_eligible": False,
        "diagnostic_only": False,
    }
    assert payload["safety"]["orders_enabled"] is False
    assert payload["safety"]["canonical_adoption_enabled"] is False
    assert opened.receipt.to_dict()["open_count"] == 1
    assert opened.receipt.to_dict()["result_feedback_to_pipeline_allowed"] is False
    assert (
        pipeline_final_report.read_pipeline_final_report(
            opened.report_path,
            state["repo"],
            attestation=state["attestation"],
            registration=state["registration"],
        )
        == opened.report
    )
    assert (
        pipeline_final_report.read_pipeline_final_open_receipt(
            opened.receipt_path,
            state["repo"],
            attestation=state["attestation"],
            registration=state["registration"],
            report=opened.report,
        )
        == opened.receipt
    )
    assert pipeline_final_report_api.__all__ == pipeline_final_report.__all__

    with pytest.raises(
        pipeline_final_report.PipelineFinalReportAlreadyOpenedError,
        match="already opened",
    ):
        _open(state)


def test_exact_report_without_receipt_can_finish_crash_recovery(
    state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_final_report,
        "_utc_now",
        lambda: state["opened_dt"],
    )
    report = pipeline_final_report.build_pipeline_final_report(
        state["attestation"],
        state["registration"],
        created_at_utc=state["opened_at"],
    )
    root = pipeline_final_report._safe_root(
        Path(state["repo"]).resolve(),
        pipeline_final_report.REPORT_ROOT,
        create=True,
    )
    report_path = root / f"{report.report_id}.json"
    pipeline_final_report._write_create_only(
        report_path,
        pipeline_final_report._bytes(report.canonical_json),
    )
    original = report_path.read_bytes()
    opened = _open(state)
    assert opened.report == report
    assert report_path.read_bytes() == original
    assert opened.receipt_path.exists()


def test_forged_report_evidence_or_legacy_source_is_blocked(state) -> None:
    report = pipeline_final_report.build_pipeline_final_report(
        state["attestation"],
        state["registration"],
        created_at_utc=state["opened_at"],
    )
    payload = deepcopy(report.to_dict())
    payload["evidence_status"]["statistically_supported"] = True
    canonical = pipeline_final_report._canonical(payload)
    forged = ProtocolV3Report(
        canonical,
        hashlib.sha256(canonical.encode()).hexdigest(),
    )
    with pytest.raises(
        pipeline_final_report.PipelineFinalReportError,
        match="differs from its Task-31 attestation",
    ):
        pipeline_final_report.validate_pipeline_final_report(
            forged,
            attestation=state["attestation"],
            registration=state["registration"],
        )

    with pytest.raises(
        pipeline_final_report.PipelineFinalReportError,
        match="PipelineFinalAttestation required",
    ):
        pipeline_final_report.build_pipeline_final_report(
            state["bound"],
            state["registration"],
            created_at_utc=state["opened_at"],
        )


def test_missing_attestation_or_early_report_is_blocked(
    state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        pipeline_final_report,
        "_utc_now",
        lambda: state["opened_dt"],
    )
    missing = Path(state["repo"]) / "missing_attestation.json"
    changed = dict(state)
    changed["attestation_path"] = missing
    with pytest.raises(Exception):
        _open(changed)

    end = datetime.fromisoformat(
        state["registration"].to_dict()["end_exclusive_utc"][:-1] + "+00:00"
    )
    early = (end.replace(microsecond=0) - support.timedelta(seconds=1)).isoformat().replace(
        "+00:00", "Z"
    )
    with pytest.raises(
        pipeline_final_report.PipelineFinalReportError,
        match="cannot predate",
    ):
        pipeline_final_report.build_pipeline_final_report(
            state["attestation"],
            state["registration"],
            created_at_utc=early,
        )
