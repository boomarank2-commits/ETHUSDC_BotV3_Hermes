"""Protocol-v3 Task-31 preregistration and single-claim tests."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import pipeline_final, pipeline_final_api, reporting
from ethusdc_bot.protocol_v3.pipeline_final import (
    PipelineFinalAlreadyClaimedError,
    PipelineFinalError,
    build_pipeline_final_registration,
    claim_pipeline_final_evaluation,
    load_pipeline_final_contract,
    pipeline_final_boundary_plan,
    pipeline_final_boundary_plan_sha256,
    read_pipeline_final_claim,
    read_pipeline_final_registration,
    validate_pipeline_final_claim,
    validate_pipeline_final_contract,
    validate_pipeline_final_registration,
    visible_forward_registration_head,
    write_pipeline_final_registration,
)
from ethusdc_bot.protocol_v3.reporting import (
    build_forward_window_registration,
    write_forward_window_registration,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
START = "2026-07-08T00:00:00Z"
END = "2027-07-08T00:00:00Z"
REGISTERED = "2026-07-01T00:00:00Z"
PIPELINE = "protocol_v3_pipeline_sha256:" + "a" * 64
RUN = "protocol_v3_run_sha256:" + "b" * 64


def _manifest() -> dict[str, str]:
    plan = pipeline_final_boundary_plan(
        start_inclusive_utc=START,
        end_exclusive_utc=END,
    )
    values = {
        "bootstrap_contract_sha256": "1" * 64,
        "boundary_plan_sha256": pipeline_final_boundary_plan_sha256(plan),
        "code_commit": "c" * 40,
        "context_contract_sha256": "2" * 64,
        "cost_contract_sha256": "3" * 64,
        "data_contract_sha256": "4" * 64,
        "exchange_info_contract_sha256": "5" * 64,
        "execution_contract_sha256": "6" * 64,
        "feature_contract_sha256": "7" * 64,
        "pipeline_contract_sha256": "8" * 64,
        "pipeline_generation_id": PIPELINE,
        "quality_gate_contract_sha256": "9" * 64,
        "report_contract_sha256": "a" * 64,
        "run_fingerprint": RUN,
        "search_budget_sha256": "b" * 64,
        "seed_policy_sha256": "c" * 64,
        "simulator_contract_sha256": "d" * 64,
        "stop_policy_sha256": "e" * 64,
        "trial_ledger_head_sha256": "f" * 64,
    }
    return values


def _registration(tmp_path: Path, *, registration_id: str = "final_2026_2027"):
    return build_pipeline_final_registration(
        registration_id=registration_id,
        registered_at_utc=REGISTERED,
        start_inclusive_utc=START,
        end_exclusive_utc=END,
        frozen_identity_manifest=_manifest(),
        visible_forward_registration_head_sha256=visible_forward_registration_head(
            tmp_path
        ),
    )


def _persist_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, registration_id: str = "final_2026_2027"
):
    monkeypatch.setattr(
        pipeline_final,
        "_utc_now",
        lambda: datetime(2026, 7, 1, tzinfo=UTC),
    )
    registration = _registration(tmp_path, registration_id=registration_id)
    path = write_pipeline_final_registration(registration, tmp_path)
    return registration, path


def _persist_forward(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reporting,
        "_utc_now",
        lambda: datetime(2026, 7, 1, tzinfo=UTC),
    )
    forward = build_forward_window_registration(
        registration_id="visible_august_2026",
        registered_at_utc="2026-07-01T00:00:00Z",
        start_inclusive_utc="2026-08-01T00:00:00Z",
        end_exclusive_utc="2026-09-01T00:00:00Z",
        pipeline_generation=PIPELINE,
        run_fingerprint=RUN,
    )
    write_forward_window_registration(forward, tmp_path)


def test_pipeline_final_contract_is_exact_and_explicitly_separate_from_legacy() -> None:
    contract = load_pipeline_final_contract(REPO_ROOT)
    assert contract["contract_version"] == (
        "protocol_v3_preregistered_single_open_pipeline_final_v1"
    )
    assert contract["window_policy"]["calendar_days"] == 365
    assert contract["window_policy"]["outer_origins"] == 12
    assert contract["claim_policy"]["exactly_one_evaluation_attempt"] is True
    assert contract["sealing_policy"]["intermediate_outer_pnl_visible"] is False
    assert contract["legacy_separation"]["legacy_report_type_forbidden"] == (
        "final_evaluation"
    )
    changed = json.loads(json.dumps(contract))
    changed["claim_policy"]["retry_after_claim_forbidden"] = False
    with pytest.raises(PipelineFinalError, match="not canonical"):
        validate_pipeline_final_contract(changed)


def test_registration_binds_exact_task2_plan_and_every_required_identity(tmp_path: Path) -> None:
    registration = _registration(tmp_path)
    payload = registration.to_dict()
    assert payload["window_class"] == "sealed_final_holdout"
    assert payload["calendar_days"] == 365
    assert payload["boundary_plan"]["origin_count"] == 12
    assert len(payload["boundary_plan"]["origins"]) == 12
    assert payload["boundary_plan"]["training_days_per_origin"] == 730
    assert payload["boundary_plan"]["activation_delay_hours"] == 24
    assert payload["frozen_identity_manifest"] == _manifest()
    assert payload["evaluation_attempt_limit"] == 1
    assert payload["intermediate_results_visible"] is False
    assert payload["safety"]["orders"] == "locked"
    assert validate_pipeline_final_registration(registration) == registration


def test_window_must_be_exact_task2_365_days_and_exclude_consumed_audit(tmp_path: Path) -> None:
    with pytest.raises(PipelineFinalError, match="365 UTC days"):
        pipeline_final_boundary_plan(
            start_inclusive_utc="2026-07-09T00:00:00Z",
            end_exclusive_utc=END,
        )
    with pytest.raises(PipelineFinalError, match="Task-2 boundary"):
        pipeline_final_boundary_plan(
            start_inclusive_utc="2026-07-09T00:00:00Z",
            end_exclusive_utc="2027-07-09T00:00:00Z",
        )
    plan = pipeline_final_boundary_plan(
        start_inclusive_utc="2025-07-08T00:00:00Z",
        end_exclusive_utc="2026-07-08T00:00:00Z",
    )
    manifest = _manifest()
    manifest["boundary_plan_sha256"] = pipeline_final_boundary_plan_sha256(plan)
    with pytest.raises(PipelineFinalError, match="consumed audit"):
        build_pipeline_final_registration(
            registration_id="consumed_window",
            registered_at_utc="2025-07-01T00:00:00Z",
            start_inclusive_utc="2025-07-08T00:00:00Z",
            end_exclusive_utc="2026-07-08T00:00:00Z",
            frozen_identity_manifest=manifest,
            visible_forward_registration_head_sha256=visible_forward_registration_head(
                tmp_path
            ),
        )


def test_registration_persists_create_only_before_start_with_canonical_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registration, path = _persist_registration(tmp_path, monkeypatch)
    assert read_pipeline_final_registration(path, tmp_path) == registration
    assert path.read_text(encoding="utf-8") == registration.canonical_json
    with pytest.raises(PipelineFinalError, match="already exists"):
        write_pipeline_final_registration(registration, tmp_path)


def test_late_or_backdated_registration_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registration = _registration(tmp_path)
    monkeypatch.setattr(
        pipeline_final,
        "_utc_now",
        lambda: datetime(2026, 7, 8, tzinfo=UTC),
    )
    with pytest.raises(PipelineFinalError, match="before start"):
        write_pipeline_final_registration(registration, tmp_path)
    monkeypatch.setattr(
        pipeline_final,
        "_utc_now",
        lambda: datetime(2026, 7, 2, tzinfo=UTC),
    )
    with pytest.raises(PipelineFinalError, match="not current"):
        write_pipeline_final_registration(registration, tmp_path)


def test_visible_forward_head_change_and_overlap_are_both_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale_head_registration = _registration(tmp_path, registration_id="stale_head")
    _persist_forward(tmp_path, monkeypatch)
    monkeypatch.setattr(
        pipeline_final,
        "_utc_now",
        lambda: datetime(2026, 7, 1, tzinfo=UTC),
    )
    with pytest.raises(PipelineFinalError, match="head changed"):
        write_pipeline_final_registration(stale_head_registration, tmp_path)

    overlapping = _registration(tmp_path, registration_id="overlapping_forward")
    with pytest.raises(PipelineFinalError, match="visible forward month"):
        write_pipeline_final_registration(overlapping, tmp_path)


def test_identity_manifest_and_registration_digest_are_recomputed(tmp_path: Path) -> None:
    payload = _registration(tmp_path).to_dict()
    payload["frozen_identity_manifest"]["cost_contract_sha256"] = "0" * 64
    with pytest.raises(PipelineFinalError, match="identity manifest"):
        validate_pipeline_final_registration(payload)

    payload = _registration(tmp_path).to_dict()
    payload["intermediate_results_visible"] = True
    with pytest.raises(PipelineFinalError, match="safety or sealing"):
        validate_pipeline_final_registration(payload)


def test_claim_is_create_only_before_start_and_survives_as_single_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registration, path = _persist_registration(tmp_path, monkeypatch)
    monkeypatch.setattr(
        pipeline_final,
        "_utc_now",
        lambda: datetime(2026, 7, 2, tzinfo=UTC),
    )
    claim = claim_pipeline_final_evaluation(
        path,
        tmp_path,
        claimed_at_utc="2026-07-02T00:00:00Z",
    )
    payload = claim.to_dict()
    assert payload["registration_sha256"] == registration.registration_sha256
    assert payload["evaluation_attempt"] == 1
    assert payload["status"] == "CLAIMED_BEFORE_WINDOW"
    assert payload["retry_allowed"] is False
    assert payload["claim_survives_failure"] is True
    assert payload["result_opened"] is False
    claim_path = tmp_path / pipeline_final.CLAIM_ROOT / f"{registration.registration_sha256}.json"
    assert read_pipeline_final_claim(claim_path, tmp_path) == claim
    with pytest.raises(PipelineFinalAlreadyClaimedError, match="single evaluation claim"):
        claim_pipeline_final_evaluation(
            path,
            tmp_path,
            claimed_at_utc="2026-07-02T00:00:00Z",
        )


def test_claim_tampering_late_claim_and_wrong_path_are_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, path = _persist_registration(tmp_path, monkeypatch)
    monkeypatch.setattr(
        pipeline_final,
        "_utc_now",
        lambda: datetime(2026, 7, 8, tzinfo=UTC),
    )
    with pytest.raises(PipelineFinalError, match="before window start"):
        claim_pipeline_final_evaluation(
            path,
            tmp_path,
            claimed_at_utc="2026-07-08T00:00:00Z",
        )

    forged = {
        "schema_version": pipeline_final.CLAIM_SCHEMA_VERSION,
        "protocol_version": "3.0.0",
        "contract_version": pipeline_final.CONTRACT_VERSION,
        "registration_id": "forged",
        "registration_sha256": "1" * 64,
        "claimed_at_utc": REGISTERED,
        "evaluation_attempt": 1,
        "status": "CLAIMED_BEFORE_WINDOW",
        "result_opened": True,
        "retry_allowed": False,
        "claim_survives_failure": True,
        "intermediate_results_visible": False,
        "safety": {
            "api_keys": "forbidden",
            "canonical_adoption": "locked",
            "live": "locked",
            "orders": "locked",
            "paper": "locked",
            "testtrade": "locked",
            "trading_api": "forbidden",
        },
        "claim_id": "protocol_v3_pipeline_final_claim_sha256:" + "2" * 64,
        "claim_sha256": "2" * 64,
    }
    with pytest.raises(PipelineFinalError, match="one-shot sealing"):
        validate_pipeline_final_claim(forged)
    with pytest.raises(PipelineFinalError, match="outside its fixed root"):
        read_pipeline_final_registration(path, tmp_path / "other")


def test_legacy_final_evaluation_or_task27_payload_has_no_task31_input_path(
    tmp_path: Path,
) -> None:
    legacy = {
        "report_type": "final_evaluation",
        "candidate": {"candidate_id": "legacy_single_candidate"},
        "quality_gate": {"passed": True},
    }
    with pytest.raises(PipelineFinalError, match="registration fields"):
        validate_pipeline_final_registration(legacy)
    historical = {
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "historical_bootstrap_lower_bound": True,
    }
    with pytest.raises(PipelineFinalError, match="registration fields"):
        validate_pipeline_final_registration(historical)
    assert visible_forward_registration_head(tmp_path) == pipeline_final._digest([])


def test_pipeline_final_public_api_is_exact() -> None:
    assert pipeline_final_api.__all__ == pipeline_final.__all__
