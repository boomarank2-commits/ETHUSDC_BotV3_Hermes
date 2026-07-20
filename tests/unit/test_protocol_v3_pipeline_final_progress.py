"""Task-31 result-blind twelve-origin progress and replay tests."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import (
    outer_origins,
    pipeline_final,
    pipeline_final_progress,
    pipeline_final_progress_api,
)
from ethusdc_bot.protocol_v3.pipeline_final_progress import (
    PipelineFinalProgressError,
    append_pipeline_final_origin_completion,
    load_pipeline_final_progress_contract,
    start_pipeline_final_progress,
    validate_pipeline_final_progress,
    validate_pipeline_final_progress_contract,
    verify_replayed_pipeline_final_progress,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTER_TEST_PATH = Path(__file__).with_name("test_protocol_v3_outer_origins.py")
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task31_outer_support", _OUTER_TEST_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
outer_support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(outer_support)


def _fmt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _manifest(plan, first_selection) -> dict[str, str]:
    first = first_selection.to_dict()
    values = {
        "bootstrap_contract_sha256": "1" * 64,
        "boundary_plan_sha256": pipeline_final.pipeline_final_boundary_plan_sha256(
            plan
        ),
        "code_commit": first["code_commit"],
        "context_contract_sha256": "2" * 64,
        "cost_contract_sha256": "3" * 64,
        "data_contract_sha256": "4" * 64,
        "exchange_info_contract_sha256": "5" * 64,
        "execution_contract_sha256": "6" * 64,
        "feature_contract_sha256": "7" * 64,
        "pipeline_contract_sha256": "8" * 64,
        "pipeline_generation_id": first["pipeline_generation_id"],
        "quality_gate_contract_sha256": "9" * 64,
        "report_contract_sha256": "a" * 64,
        "run_fingerprint": "protocol_v3_run_sha256:" + "b" * 64,
        "search_budget_sha256": "b" * 64,
        "seed_policy_sha256": "c" * 64,
        "simulator_contract_sha256": "d" * 64,
        "stop_policy_sha256": "e" * 64,
        "trial_ledger_head_sha256": "f" * 64,
    }
    return values


def _identities(seed: int = 1) -> dict[str, str]:
    alphabet = "123456789abcdef"
    return {
        key: alphabet[(seed + offset) % len(alphabet)] * 64
        for offset, key in enumerate(
            pipeline_final_progress._ORIGIN_IDENTITY_FIELDS
        )
    }


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    outer_root = tmp_path / "outer"
    outer_root.mkdir()
    _, plan, requests = outer_support.state.__wrapped__(outer_root, monkeypatch)
    process = outer_origins.orchestrate_outer_origins(plan, requests)
    selections = tuple(
        outer_origins.validate_outer_origin_selection(row, origin=origin)
        for row, origin in zip(
            process.to_dict()["origins"], plan.origins, strict=True
        )
    )

    # Task-31 preregistration overlap rules are already covered independently.
    # This fixture moves only the fixed consumed interval away so that the
    # existing, fully validated Task-23 test process can exercise progress.
    monkeypatch.setattr(
        pipeline_final,
        "CONSUMED_AUDIT_START",
        datetime(2024, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(
        pipeline_final,
        "CONSUMED_AUDIT_END_EXCLUSIVE",
        datetime(2025, 1, 1, tzinfo=UTC),
    )
    start = datetime.combine(plan.process_start_inclusive, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(plan.process_end_exclusive, datetime.min.time(), tzinfo=UTC)
    registered = start - timedelta(days=7)
    claimed = start - timedelta(days=6)
    monkeypatch.setattr(pipeline_final, "_utc_now", lambda: registered)
    registration = pipeline_final.build_pipeline_final_registration(
        registration_id="task31_progress_fixture",
        registered_at_utc=_fmt(registered),
        start_inclusive_utc=_fmt(start),
        end_exclusive_utc=_fmt(end),
        frozen_identity_manifest=_manifest(plan, selections[0]),
        visible_forward_registration_head_sha256=(
            pipeline_final.visible_forward_registration_head(tmp_path)
        ),
    )
    registration_path = pipeline_final.write_pipeline_final_registration(
        registration, tmp_path
    )
    monkeypatch.setattr(pipeline_final, "_utc_now", lambda: claimed)
    claim = pipeline_final.claim_pipeline_final_evaluation(
        registration_path,
        tmp_path,
        claimed_at_utc=_fmt(claimed),
    )
    return plan, selections, registration, claim


def _append(progress, selection, index, *, state, identities=None, completed=None):
    plan, _, registration, claim = state
    origin = plan.origins[index - 1]
    completed_text = completed or f"{origin.test_end_exclusive.isoformat()}T00:00:00Z"
    return append_pipeline_final_origin_completion(
        progress,
        selection,
        registration=registration,
        claim=claim,
        completion_identities=identities or _identities(index),
        completed_at_utc=completed_text,
    )


def test_progress_contract_and_public_api_are_exact() -> None:
    contract = load_pipeline_final_progress_contract(REPO_ROOT)
    assert contract["contract_version"] == (
        "protocol_v3_result_blind_twelve_origin_progress_v1"
    )
    assert contract["progress_policy"]["exact_origin_count"] == 12
    assert contract["hidden_result_policy"]["outer_pnl_stored"] is False
    assert contract["hidden_result_policy"]["outer_rankings_stored"] is False
    changed = json.loads(json.dumps(contract))
    changed["hidden_result_policy"]["outer_pnl_stored"] = True
    with pytest.raises(PipelineFinalProgressError, match="not canonical"):
        validate_pipeline_final_progress_contract(changed)
    assert pipeline_final_progress_api.__all__ == pipeline_final_progress.__all__


def test_start_progress_is_claim_bound_and_result_blind(state) -> None:
    _, _, registration, claim = state
    progress = start_pipeline_final_progress(registration, claim)
    payload = progress.to_dict()
    assert payload["registration_sha256"] == registration.registration_sha256
    assert payload["claim_sha256"] == claim.claim_sha256
    assert payload["completed_origins"] == []
    assert payload["completed_origin_count"] == 0
    assert payload["next_origin_index"] == 1
    assert payload["origin_chain_head_sha256"] == pipeline_final_progress.ZERO_HASH
    assert payload["status"] == "CLAIMED_NOT_STARTED"
    assert payload["outer_result_values_stored"] is False
    assert payload["outer_result_channel_visible"] is False
    assert payload["final_report_visible"] is False
    assert payload["task31_attestation_available"] is False
    assert not any(
        key in json.dumps(payload).lower()
        for key in ('"pnl"', '"mtm"', '"equity"', '"trades"', '"rankings"')
    )


def test_origin_receipts_advance_strictly_and_complete_twelve_hidden_origins(state) -> None:
    _, selections, registration, claim = state
    progress = start_pipeline_final_progress(registration, claim)
    first = _append(progress, selections[0], 1, state=state)
    first_payload = first.to_dict()
    assert first_payload["completed_origin_count"] == 1
    assert first_payload["next_origin_index"] == 2
    assert first_payload["status"] == "RUNNING_RESULTS_HIDDEN"
    assert first_payload["origin_chain_head_sha256"] != pipeline_final_progress.ZERO_HASH
    assert first_payload["completed_origins"][0]["previous_origin_receipt_sha256"] == (
        pipeline_final_progress.ZERO_HASH
    )

    current = first
    for index, selection in enumerate(selections[1:], start=2):
        current = _append(current, selection, index, state=state)
    payload = current.to_dict()
    assert payload["completed_origin_count"] == 12
    assert payload["next_origin_index"] is None
    assert payload["status"] == "ORIGINS_COMPLETE_RESULTS_HIDDEN"
    assert payload["final_report_visible"] is False
    assert payload["task31_attestation_available"] is False
    with pytest.raises(PipelineFinalProgressError, match="already complete"):
        _append(current, selections[-1], 12, state=state)


def test_reordered_or_duplicate_origin_is_blocked(state) -> None:
    _, selections, registration, claim = state
    progress = start_pipeline_final_progress(registration, claim)
    with pytest.raises(PipelineFinalProgressError, match="Task-23 validation"):
        _append(progress, selections[1], 1, state=state)
    first = _append(progress, selections[0], 1, state=state)
    with pytest.raises(PipelineFinalProgressError, match="Task-23 validation"):
        _append(first, selections[0], 2, state=state)


def test_full_task23_validation_rejects_rehashed_visibility_or_bundle_tampering(state) -> None:
    _, selections, registration, claim = state
    progress = start_pipeline_final_progress(registration, claim)
    payload = deepcopy(selections[0].to_dict())
    payload["outer_results_visible_during_fit"] = True
    basis = dict(payload)
    basis.pop("origin_sha256")
    payload["origin_sha256"] = outer_origins._digest(basis)
    forged = outer_origins.OuterOriginSelection(
        outer_origins._canonical(basis), payload["origin_sha256"]
    )
    with pytest.raises(PipelineFinalProgressError, match="Task-23 validation"):
        _append(progress, forged, 1, state=state)

    payload = deepcopy(selections[0].to_dict())
    payload["frozen_candidate_bundle"]["canonical_adoption_eligible"] = True
    bundle = payload["frozen_candidate_bundle"]
    bundle_basis = dict(bundle)
    bundle_basis.pop("bundle_sha256")
    bundle["bundle_sha256"] = outer_origins._digest(bundle_basis)
    basis = dict(payload)
    basis.pop("origin_sha256")
    payload["origin_sha256"] = outer_origins._digest(basis)
    forged = outer_origins.OuterOriginSelection(
        outer_origins._canonical(basis), payload["origin_sha256"]
    )
    with pytest.raises(PipelineFinalProgressError, match="Task-23 validation"):
        _append(progress, forged, 1, state=state)


def test_completion_identities_are_exact_and_result_values_cannot_be_added(state) -> None:
    _, selections, registration, claim = state
    progress = start_pipeline_final_progress(registration, claim)
    missing = _identities()
    missing.pop("cost_identity_sha256")
    with pytest.raises(PipelineFinalProgressError, match="incomplete or unexpected"):
        _append(progress, selections[0], 1, state=state, identities=missing)
    extra = _identities()
    extra["pnl"] = "1" * 64
    with pytest.raises(PipelineFinalProgressError, match="incomplete or unexpected"):
        _append(progress, selections[0], 1, state=state, identities=extra)
    malformed = _identities()
    malformed["data_snapshot_sha256"] = "not-a-hash"
    with pytest.raises(PipelineFinalProgressError, match="lowercase sha256"):
        _append(progress, selections[0], 1, state=state, identities=malformed)


def test_completion_time_must_follow_closed_oos_and_remain_monotonic(state) -> None:
    plan, selections, registration, claim = state
    progress = start_pipeline_final_progress(registration, claim)
    early = f"{plan.origins[0].test_start_inclusive.isoformat()}T00:00:00Z"
    with pytest.raises(PipelineFinalProgressError, match="cannot predate"):
        _append(progress, selections[0], 1, state=state, completed=early)
    first = _append(progress, selections[0], 1, state=state)
    earlier_than_first = f"{plan.origins[0].test_end_exclusive.isoformat()}T00:00:00Z"
    with pytest.raises(PipelineFinalProgressError, match="monotonic"):
        _append(first, selections[1], 2, state=state, completed=earlier_than_first)


def test_progress_digest_chain_visibility_and_cross_generation_tampering_fail(state) -> None:
    _, selections, registration, claim = state
    first = _append(
        start_pipeline_final_progress(registration, claim),
        selections[0],
        1,
        state=state,
    )
    payload = first.to_dict()
    payload["completed_origins"][0]["previous_origin_receipt_sha256"] = "1" * 64
    receipt = payload["completed_origins"][0]
    receipt_basis = dict(receipt)
    receipt_basis.pop("origin_receipt_sha256")
    receipt["origin_receipt_sha256"] = pipeline_final_progress._digest(receipt_basis)
    payload["origin_chain_head_sha256"] = receipt["origin_receipt_sha256"]
    basis = dict(payload)
    basis.pop("progress_sha256")
    payload["progress_sha256"] = pipeline_final_progress._digest(basis)
    with pytest.raises(PipelineFinalProgressError, match="chain is broken"):
        validate_pipeline_final_progress(
            payload, registration=registration, claim=claim
        )

    payload = first.to_dict()
    payload["final_report_visible"] = True
    basis = dict(payload)
    basis.pop("progress_sha256")
    payload["progress_sha256"] = pipeline_final_progress._digest(basis)
    with pytest.raises(PipelineFinalProgressError, match="exposes results"):
        validate_pipeline_final_progress(
            payload, registration=registration, claim=claim
        )

    payload = first.to_dict()
    payload["pipeline_generation_id"] = "protocol_v3_pipeline_sha256:" + "0" * 64
    basis = dict(payload)
    basis.pop("progress_sha256")
    payload["progress_sha256"] = pipeline_final_progress._digest(basis)
    with pytest.raises(PipelineFinalProgressError, match="another registration"):
        validate_pipeline_final_progress(
            payload, registration=registration, claim=claim
        )


def test_replay_must_match_every_committed_origin_selection(state) -> None:
    _, selections, registration, claim = state
    progress = start_pipeline_final_progress(registration, claim)
    for index, selection in enumerate(selections[:3], start=1):
        progress = _append(progress, selection, index, state=state)
    assert (
        verify_replayed_pipeline_final_progress(
            progress,
            selections[:3],
            registration=registration,
            claim=claim,
        )
        == progress
    )
    with pytest.raises(PipelineFinalProgressError, match="count differs"):
        verify_replayed_pipeline_final_progress(
            progress,
            selections[:2],
            registration=registration,
            claim=claim,
        )
    reordered = (selections[1], selections[0], selections[2])
    with pytest.raises(PipelineFinalProgressError, match="Task-23 validation"):
        verify_replayed_pipeline_final_progress(
            progress,
            reordered,
            registration=registration,
            claim=claim,
        )


def test_claim_from_another_registration_cannot_start_progress(state) -> None:
    _, _, registration, claim = state
    payload = claim.to_dict()
    payload["registration_sha256"] = "0" * 64
    basis = dict(payload)
    basis.pop("claim_id")
    basis.pop("claim_sha256")
    digest = pipeline_final._digest(basis)
    payload["claim_sha256"] = digest
    payload["claim_id"] = f"protocol_v3_pipeline_final_claim_sha256:{digest}"
    forged = pipeline_final.validate_pipeline_final_claim(payload)
    with pytest.raises(PipelineFinalProgressError, match="does not belong"):
        start_pipeline_final_progress(registration, forged)
