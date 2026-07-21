"""Task-31 sealed final attestation and transitive source regressions."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import boundaries, outer_mtm_ledger, outer_origins
from ethusdc_bot.protocol_v3 import pipeline_final, pipeline_final_attestation
from ethusdc_bot.protocol_v3 import pipeline_final_attestation_api
from ethusdc_bot.protocol_v3 import pipeline_final_checkpoint
from ethusdc_bot.protocol_v3 import pipeline_final_progress
from ethusdc_bot.protocol_v3 import monthly_quality_gate

_TASK23_PATH = Path(__file__).with_name("test_protocol_v3_outer_origins.py")
_SPEC23 = importlib.util.spec_from_file_location(
    "protocol_v3_task31_attestation_task23_support", _TASK23_PATH
)
assert _SPEC23 is not None and _SPEC23.loader is not None
task23 = importlib.util.module_from_spec(_SPEC23)
_SPEC23.loader.exec_module(task23)

_TASK25_PATH = Path(__file__).with_name("test_protocol_v3_outer_mtm_ledger.py")
_SPEC25 = importlib.util.spec_from_file_location(
    "protocol_v3_task31_attestation_task25_support", _TASK25_PATH
)
assert _SPEC25 is not None and _SPEC25.loader is not None
task25 = importlib.util.module_from_spec(_SPEC25)
_SPEC25.loader.exec_module(task25)

_TASK26_PATH = Path(__file__).with_name("test_protocol_v3_monthly_quality_gate.py")
_SPEC26 = importlib.util.spec_from_file_location(
    "protocol_v3_task31_attestation_task26_support", _TASK26_PATH
)
assert _SPEC26 is not None and _SPEC26.loader is not None
task26 = importlib.util.module_from_spec(_SPEC26)
_SPEC26.loader.exec_module(task26)

_TASK27_PATH = Path(__file__).with_name("test_protocol_v3_historical_diagnostics.py")
_SPEC27 = importlib.util.spec_from_file_location(
    "protocol_v3_task31_attestation_task27_support", _TASK27_PATH
)
assert _SPEC27 is not None and _SPEC27.loader is not None
task27 = importlib.util.module_from_spec(_SPEC27)
_SPEC27.loader.exec_module(task27)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _manifest(base, plan) -> dict[str, str]:
    run = base["identity"].to_dict()["run_fingerprint"]
    return {
        "bootstrap_contract_sha256": "1" * 64,
        "boundary_plan_sha256": pipeline_final.pipeline_final_boundary_plan_sha256(
            plan
        ),
        "code_commit": run["code"]["git_commit"],
        "context_contract_sha256": "2" * 64,
        "cost_contract_sha256": "3" * 64,
        "data_contract_sha256": "4" * 64,
        "exchange_info_contract_sha256": "5" * 64,
        "execution_contract_sha256": "6" * 64,
        "feature_contract_sha256": "7" * 64,
        "pipeline_contract_sha256": "8" * 64,
        "pipeline_generation_id": run["pipeline"]["generation_id"],
        "quality_gate_contract_sha256": "9" * 64,
        "report_contract_sha256": "a" * 64,
        "run_fingerprint": "protocol_v3_run_sha256:" + run["fingerprint_sha256"],
        "search_budget_sha256": "b" * 64,
        "seed_policy_sha256": "c" * 64,
        "simulator_contract_sha256": "d" * 64,
        "stop_policy_sha256": "e" * 64,
        "trial_ledger_head_sha256": run["trial_ledger_head"]["head_sha256"],
    }


def _completion_identities(index: int, base) -> dict[str, str]:
    run = base["identity"].to_dict()["run_fingerprint"]
    values = {
        "context_binding_sha256": index + 10,
        "cost_identity_sha256": index + 20,
        "data_snapshot_sha256": index + 30,
        "exchange_info_snapshot_sha256": index + 40,
        "execution_identity_sha256": index + 50,
        "feature_store_sha256": index + 60,
        "origin_artifact_index_sha256": index + 70,
        "rotation_state_sha256": index + 80,
        "transaction_checkpoint_sha256": index + 90,
    }
    return {
        **{name: f"{value:064x}" for name, value in values.items()},
        "trial_ledger_head_sha256": run["trial_ledger_head"]["head_sha256"],
    }


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    future_plan = boundaries.build_monthly_process_boundary_plan("2027-07-08")
    original_task23_builder = task23.boundaries.build_monthly_process_boundary_plan
    original_task13_builder = task23.support.build_monthly_process_boundary_plan
    monkeypatch.setattr(
        task23.boundaries,
        "build_monthly_process_boundary_plan",
        lambda *_args, **_kwargs: future_plan,
    )
    monkeypatch.setattr(
        task23.support,
        "build_monthly_process_boundary_plan",
        lambda *_args, **_kwargs: future_plan,
    )
    base, plan, requests = task23.state.__wrapped__(tmp_path, monkeypatch)
    monkeypatch.setattr(
        task23.boundaries,
        "build_monthly_process_boundary_plan",
        original_task23_builder,
    )
    monkeypatch.setattr(
        task23.support,
        "build_monthly_process_boundary_plan",
        original_task13_builder,
    )
    assert plan == future_plan
    process = outer_origins.orchestrate_outer_origins(plan, requests)
    baseline = outer_mtm_ledger.build_outer_mtm_ledger(
        plan,
        process,
        task25._inputs(plan, process),
    )
    stress_identity = task26._stress_identity()
    regime_evidence = {}
    integrity_evidence = task26._integrity()
    gate = monthly_quality_gate.evaluate_monthly_quality_gate(
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        joint_stress_ledger=baseline,
        slippage_stress_ledger=baseline,
        stress_identity_evidence=stress_identity,
        regime_evidence=regime_evidence,
        integrity_evidence=integrity_evidence,
    )
    bound = task27._bound(plan, process, baseline)

    start = datetime.combine(plan.process_start_inclusive, datetime.min.time(), UTC)
    registered = start - timedelta(days=7)
    claimed = start - timedelta(days=6)
    monkeypatch.setattr(pipeline_final, "_utc_now", lambda: registered)
    registration = pipeline_final.build_pipeline_final_registration(
        registration_id="task31_attestation_fixture",
        registered_at_utc=_utc_text(registered),
        start_inclusive_utc=_utc_text(start),
        end_exclusive_utc=_utc_text(
            datetime.combine(plan.process_end_exclusive, datetime.min.time(), UTC)
        ),
        frozen_identity_manifest=_manifest(base, plan),
        visible_forward_registration_head_sha256=(
            pipeline_final.visible_forward_registration_head(tmp_path)
        ),
    )
    registration_path = pipeline_final.write_pipeline_final_registration(
        registration,
        tmp_path,
    )
    monkeypatch.setattr(pipeline_final, "_utc_now", lambda: claimed)
    claim = pipeline_final.claim_pipeline_final_evaluation(
        registration_path,
        tmp_path,
        claimed_at_utc=_utc_text(claimed),
    )
    progress = pipeline_final_progress.start_pipeline_final_progress(
        registration,
        claim,
    )
    for origin, row in zip(plan.origins, process.to_dict()["origins"], strict=True):
        selection = outer_origins.validate_outer_origin_selection(row, origin=origin)
        completed = datetime.combine(origin.test_end_exclusive, datetime.min.time(), UTC)
        progress = pipeline_final_progress.append_pipeline_final_origin_completion(
            progress,
            selection,
            registration=registration,
            claim=claim,
            completion_identities=_completion_identities(origin.origin_index, base),
            completed_at_utc=_utc_text(completed),
        )
    receipt = pipeline_final_checkpoint.build_pipeline_final_checkpoint_receipt(
        progress,
        registration=registration,
        claim=claim,
    )
    pipeline_final_checkpoint.commit_pipeline_final_checkpoint(
        receipt,
        registration=registration,
        claim=claim,
        identity=base["identity"],
        pre_run_manifest=base["manifest"],
        seed_state=base["seed"],
        budget_usage=base["budget"],
        stop_state=base["stop"],
        repository_root=base["repo"],
        trial_ledger_root=base["ledger_root"],
        owner_id="task31-attestation-checkpoint",
    )
    checkpoint = pipeline_final_checkpoint.read_pipeline_final_checkpoint(
        current_registration=registration,
        current_claim=claim,
        current_identity=base["identity"],
        current_pre_run_manifest=base["manifest"],
        repository_root=base["repo"],
    )
    assert checkpoint is not None
    completed_at = datetime.combine(plan.process_end_exclusive, datetime.min.time(), UTC)
    return {
        "base": base,
        "plan": plan,
        "process": process,
        "baseline": baseline,
        "gate": gate,
        "stress_identity": stress_identity,
        "regime_evidence": regime_evidence,
        "integrity_evidence": integrity_evidence,
        "bound": bound,
        "registration": registration,
        "claim": claim,
        "progress": progress,
        "checkpoint": checkpoint,
        "completed_at": _utc_text(completed_at),
        "repo": tmp_path,
    }


def _build(state):
    return pipeline_final_attestation.build_pipeline_final_attestation(
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
        completed_at_utc=state["completed_at"],
    )


def _dependencies(state) -> dict[str, object]:
    return {
        "registration": state["registration"],
        "claim": state["claim"],
        "progress": state["progress"],
        "checkpoint": state["checkpoint"],
        "boundary_plan": state["plan"],
        "outer_process": state["process"],
        "baseline_ledger": state["baseline"],
        "joint_stress_ledger": state["baseline"],
        "slippage_stress_ledger": state["baseline"],
        "monthly_quality_report": state["gate"],
        "stress_identity_evidence": state["stress_identity"],
        "regime_evidence": state["regime_evidence"],
        "integrity_evidence": state["integrity_evidence"],
        "bound_hindsight_benchmarks": state["bound"],
    }


def test_attestation_recomputes_task25_26_27_and_derives_freshness(state) -> None:
    attestation = _build(state)
    payload = attestation.to_dict()
    assert payload["progress"]["completed_origin_count"] == 12
    assert payload["metrics"]["process_calendar_days"] == 365
    assert payload["metrics"]["monthly_quality_status"] == "RED"
    assert payload["evidence_status"] == {
        "historically_hit": False,
        "fresh_pre_registered_sealed_365": True,
        "sealed_bootstrap_target_supported": False,
        "statistically_supported": False,
        "canonical_adoption_eligible": False,
    }
    assert payload["final_evaluation_status"] == (
        "FRESH_FINAL_NOT_STATISTICALLY_SUPPORTED"
    )
    assert payload["result_feedback_to_pipeline_allowed"] is False
    assert payload["report_opened"] is False
    assert pipeline_final_attestation_api.__all__ == pipeline_final_attestation.__all__
    assert (
        pipeline_final_attestation.validate_pipeline_final_attestation(
            payload,
            **_dependencies(state),
        )
        == attestation
    )


def test_incomplete_or_early_final_evidence_is_blocked(state) -> None:
    start_progress = pipeline_final_progress.start_pipeline_final_progress(
        state["registration"],
        state["claim"],
    )
    with pytest.raises(
        pipeline_final_attestation.PipelineFinalAttestationError,
        match="twelve-origin complete",
    ):
        pipeline_final_attestation.build_pipeline_final_attestation(
            registration=state["registration"],
            claim=state["claim"],
            progress=start_progress,
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
            completed_at_utc=state["completed_at"],
        )
    early = _utc_text(
        datetime.combine(
            state["plan"].process_end_exclusive,
            datetime.min.time(),
            UTC,
        )
        - timedelta(seconds=1)
    )
    changed = dict(state)
    changed["completed_at"] = early
    with pytest.raises(
        pipeline_final_attestation.PipelineFinalAttestationError,
        match="cannot predate",
    ):
        _build(changed)


def test_forged_support_claim_or_changed_gate_source_is_rejected(state) -> None:
    attestation = _build(state)
    forged = deepcopy(attestation.to_dict())
    forged["evidence_status"]["statistically_supported"] = True
    forged["final_evaluation_status"] = "STATISTICALLY_SUPPORTED"
    basis = dict(forged)
    basis.pop("attestation_id")
    basis.pop("attestation_sha256")
    digest = pipeline_final_attestation._digest(basis)
    forged["attestation_sha256"] = digest
    forged["attestation_id"] = (
        "protocol_v3_pipeline_final_attestation_sha256:" + digest
    )
    with pytest.raises(
        pipeline_final_attestation.PipelineFinalAttestationError,
        match="differs from source re-evaluation",
    ):
        pipeline_final_attestation.validate_pipeline_final_attestation(
            forged,
            **_dependencies(state),
        )

    gate_payload = deepcopy(state["gate"].to_dict())
    gate_payload["historically_hit"] = True
    with pytest.raises(Exception):
        pipeline_final_attestation.build_pipeline_final_attestation(
            **{
                **_dependencies(state),
                "monthly_quality_report": gate_payload,
                "completed_at_utc": state["completed_at"],
            }
        )


def test_attestation_is_create_only_and_persisted_bytes_are_canonical(
    state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attestation = _build(state)
    completed = datetime.fromisoformat(state["completed_at"][:-1] + "+00:00")
    monkeypatch.setattr(
        pipeline_final_attestation,
        "_utc_now",
        lambda: completed,
    )
    path = pipeline_final_attestation.write_pipeline_final_attestation(
        attestation,
        state["repo"],
    )
    assert (
        pipeline_final_attestation.read_pipeline_final_attestation(
            path,
            state["repo"],
        )
        == attestation
    )
    assert path.read_bytes() == (attestation.canonical_json + "\n").encode("utf-8")
    with pytest.raises(
        pipeline_final_attestation.PipelineFinalAttestationError,
        match="already has an attestation",
    ):
        pipeline_final_attestation.write_pipeline_final_attestation(
            attestation,
            state["repo"],
        )
