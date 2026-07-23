"""Task-32 fixture-only end-to-end acceptance over the existing Protocol-v3 chain."""
from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import acceptance
from ethusdc_bot.protocol_v3 import pipeline_final_checkpoint
from ethusdc_bot.protocol_v3 import pipeline_final_attestation
from ethusdc_bot.protocol_v3 import pipeline_final_report
from ethusdc_bot.protocol_v3 import reporting as reporting_module
from ethusdc_bot.protocol_v3 import transactional_cache_api as tx
from ethusdc_bot.ui.protocol_v3_dashboard_bridge import (
    build_empty_protocol_v3_ui_evidence,
    resolve_protocol_v3_operator_state,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORT_SUPPORT_PATH = REPO_ROOT / "tests/unit/test_protocol_v3_pipeline_final_report.py"
_REPORT_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task32_report_support", _REPORT_SUPPORT_PATH
)
assert _REPORT_SPEC is not None and _REPORT_SPEC.loader is not None
report_support = importlib.util.module_from_spec(_REPORT_SPEC)
_REPORT_SPEC.loader.exec_module(report_support)

_TASK13_SUPPORT_PATH = REPO_ROOT / "tests/unit/protocol_v3_task13_support.py"
_TASK13_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task32_transaction_support", _TASK13_SUPPORT_PATH
)
assert _TASK13_SPEC is not None and _TASK13_SPEC.loader is not None
task13_support = importlib.util.module_from_spec(_TASK13_SPEC)
_TASK13_SPEC.loader.exec_module(task13_support)


@pytest.fixture
def final_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixture_root = tmp_path / "isolated_task32_final"
    state = report_support.state.__wrapped__(fixture_root, monkeypatch)
    monkeypatch.setattr(
        pipeline_final_report,
        "_utc_now",
        lambda: state["opened_dt"],
    )
    opened = report_support._open(state)
    return state, opened


def _capture(state, opened, mode: str, ui: dict):
    return acceptance.capture_acceptance_path_snapshot(
        mode=mode,
        fixture_repository_root=state["repo"],
        source_repository_root=REPO_ROOT,
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
        attestation=state["attestation"],
        final_report=opened.report,
        open_receipt=opened.receipt,
        final_report_path=opened.report_path,
        open_receipt_path=opened.receipt_path,
        ui_state=ui,
    )


def test_full_fixture_chain_resume_cache_replay_and_ui_are_bit_identical(
    final_fixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, opened = final_fixture
    evidence = build_empty_protocol_v3_ui_evidence()
    clock = datetime(2026, 7, 22, 12, tzinfo=UTC)
    ui_first = resolve_protocol_v3_operator_state(evidence, now_utc=clock).to_dict()
    ui_refresh = resolve_protocol_v3_operator_state(evidence, now_utc=clock).to_dict()
    assert ui_first == ui_refresh

    first = _capture(state, opened, "FIRST_RUN", ui_first)

    resumed = pipeline_final_checkpoint.read_pipeline_final_checkpoint(
        current_registration=state["registration"],
        current_claim=state["claim"],
        current_identity=state["base"]["identity"],
        current_pre_run_manifest=state["base"]["manifest"],
        repository_root=state["base"]["repo"],
    )
    assert resumed == state["checkpoint"]
    resume_payload = first.to_dict()
    resume_payload["mode"] = "TASK13_RESUME"
    resume = acceptance.validate_acceptance_path_snapshot(resume_payload)

    cache_state = task13_support.build_state(tmp_path / "isolated_cache", monkeypatch)
    checkpoint = task13_support._commit(cache_state, status="NO_TRADE")
    cache_record = tx.publish_cache_record(
        checkpoint=checkpoint,
        repository_root=cache_state["repo"],
        trial_ledger_root=cache_state["ledger_root"],
        trial_id=cache_state["record"].trial_id,
    )
    assert tx.lookup_cache_record(
        cache_state["identity"],
        cache_state["repo"],
        trial_ledger_root=cache_state["ledger_root"],
    ) == cache_record
    cache_payload = first.to_dict()
    cache_payload["mode"] = "CACHE_REUSE"
    cache = acceptance.validate_acceptance_path_snapshot(cache_payload)

    replayed_attestation = report_support.support._build(state)
    assert replayed_attestation == state["attestation"]
    replay_payload = first.to_dict()
    replay_payload["mode"] = "DETERMINISTIC_REPLAY"
    replay = acceptance.validate_acceptance_path_snapshot(replay_payload)

    receipt = acceptance.build_task32_acceptance_receipt(
        [first, resume, cache, replay],
        observed_fault_matrix=acceptance._FAULT_MATRIX,
        ui_state_before=ui_first,
        ui_state_after=ui_refresh,
    )
    result = acceptance.validate_task32_acceptance_receipt(receipt).to_dict()
    assert result["status"] == "DONE_100_FIXTURE_ACCEPTANCE"
    assert result["common_parity_identities"] == first.to_dict()["parity_identities"]
    assert result["real_final_evidence"] is False
    assert result["bot_start_allowed"] is False


def test_atomic_faults_preserve_a_valid_committed_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    state = task13_support.build_state(tmp_path / "atomic_faults", monkeypatch)
    baseline = task13_support._commit(
        state,
        status="IN_PROGRESS",
        payload={"step": 1},
    )
    state["stop"] = tx.build_stop_state(
        completed_cycles=1,
        consecutive_non_improving_cycles=0,
    )
    phases = acceptance._FAULT_MATRIX["atomic_checkpoint_and_head"]
    for phase in phases[:-1]:
        def fail(observed: str, target: str = phase) -> None:
            if observed == target:
                raise RuntimeError(target)

        with pytest.raises(RuntimeError, match=phase):
            task13_support._commit(
                state,
                payload={"step": phase},
                fault=fail,
            )
        assert tx.read_last_committed_checkpoint(
            state["identity"].transaction_id,
            state["repo"],
        ) == baseline

    def after_head(observed: str) -> None:
        if observed == "after_head_replace":
            raise RuntimeError(observed)

    with pytest.raises(RuntimeError, match="after_head_replace"):
        task13_support._commit(
            state,
            payload={"step": "atomically_visible"},
            fault=after_head,
        )
    durable = tx.read_last_committed_checkpoint(
        state["identity"].transaction_id,
        state["repo"],
    )
    assert durable is not None and durable.sequence == baseline.sequence + 1
    assert tx.validate_checkpoint(durable, repository_root=state["repo"]) == durable


def test_fixture_artifacts_cannot_use_the_canonical_repository(
    final_fixture,
) -> None:
    state, opened = final_fixture
    ui = {"read_only": True}
    with pytest.raises(
        acceptance.ProtocolV3AcceptanceError,
        match="outside the canonical repository",
    ):
        acceptance.capture_acceptance_path_snapshot(
            mode="FIRST_RUN",
            fixture_repository_root=REPO_ROOT,
            source_repository_root=REPO_ROOT,
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
            attestation=state["attestation"],
            final_report=opened.report,
            open_receipt=opened.receipt,
            final_report_path=opened.report_path,
            open_receipt_path=opened.receipt_path,
            ui_state=ui,
        )


def test_rehashed_claims_and_fault_coverage_cannot_promote_fixture() -> None:
    parity = {
        key: (
            "a" * 40 if key == "code_commit" else
            "protocol_v3_pipeline_sha256:" + "b" * 64
            if key == "pipeline_generation_id" else
            "protocol_v3_run_sha256:" + "c" * 64
            if key == "run_fingerprint" else
            f"{index + 1:064x}"
        )
        for index, key in enumerate(
            acceptance.load_acceptance_contract(REPO_ROOT)["required_parity_identities"]
        )
    }
    base = {
        "schema_version": acceptance.SNAPSHOT_SCHEMA_VERSION,
        "protocol_version": acceptance.PROTOCOL_VERSION,
        "contract_version": acceptance.CONTRACT_VERSION,
        "mode": "FIRST_RUN",
        "fixture_only": True,
        "fixture_repository_sha256": "d" * 64,
        "parity_identities": parity,
        "checkpoint_sha256": "e" * 64,
        "origin_count": 12,
        "process_oos_days": 365,
        "freshness": "FIXTURE_ONLY",
        "diagnostic_only": True,
        "real_final_evidence": False,
        "task33_research_run": False,
        "safety": acceptance._SAFETY,
    }
    for field, value in (
        ("freshness", "FRESH_SEALED_FINAL"),
        ("diagnostic_only", False),
        ("real_final_evidence", True),
        ("task33_research_run", True),
    ):
        forged = deepcopy(base)
        forged[field] = value
        with pytest.raises(acceptance.ProtocolV3AcceptanceError):
            acceptance.validate_acceptance_path_snapshot(forged)


def test_parallel_attestation_and_open_are_create_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = tmp_path / "parallel_final"
    state = report_support.support.state.__wrapped__(fixture_root, monkeypatch)
    attestation = report_support.support._build(state)
    completed = datetime.fromisoformat(state["completed_at"][:-1] + "+00:00")
    monkeypatch.setattr(pipeline_final_attestation, "_utc_now", lambda: completed)

    def write_attestation():
        try:
            return pipeline_final_attestation.write_pipeline_final_attestation(
                attestation,
                state["repo"],
            )
        except pipeline_final_attestation.PipelineFinalAttestationError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        writes = list(executor.map(lambda _index: write_attestation(), range(2)))
    paths = [item for item in writes if isinstance(item, Path)]
    errors = [item for item in writes if isinstance(item, Exception)]
    assert len(paths) == 1 and len(errors) == 1
    assert "already has an attestation" in str(errors[0])

    attestation_path = paths[0]
    opened_state = {
        **state,
        "attestation": attestation,
        "attestation_path": attestation_path,
        "opened_at": state["completed_at"],
        "opened_dt": completed,
    }
    monkeypatch.setattr(pipeline_final_report, "_utc_now", lambda: completed)

    def open_report():
        try:
            return report_support._open(opened_state)
        except pipeline_final_report.PipelineFinalReportAlreadyOpenedError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        opens = list(executor.map(lambda _index: open_report(), range(2)))
    successes = [
        item
        for item in opens
        if isinstance(item, pipeline_final_report.PipelineFinalReportOpenResult)
    ]
    open_errors = [item for item in opens if isinstance(item, Exception)]
    assert len(successes) == 1 and len(open_errors) == 1
    assert "already" in str(open_errors[0]).lower()
