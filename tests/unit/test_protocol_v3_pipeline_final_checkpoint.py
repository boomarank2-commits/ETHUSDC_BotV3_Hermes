"""Task-31 compact Task-13 checkpoint and replay regressions."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path

import pytest

import ethusdc_bot.protocol_v3.reporting as reporting_module
from ethusdc_bot.protocol_v3 import pipeline_final
from ethusdc_bot.protocol_v3 import pipeline_final_checkpoint as checkpointing
from ethusdc_bot.protocol_v3 import pipeline_final_checkpoint_api
from ethusdc_bot.protocol_v3.pipeline_final_progress import (
    start_pipeline_final_progress,
)

_TASK13_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC13 = importlib.util.spec_from_file_location(
    "protocol_v3_task31_checkpoint_transaction_support", _TASK13_PATH
)
assert _SPEC13 is not None and _SPEC13.loader is not None
task13 = importlib.util.module_from_spec(_SPEC13)
_SPEC13.loader.exec_module(task13)

START = "2026-07-08T00:00:00Z"
END = "2027-07-08T00:00:00Z"
REGISTERED = "2026-07-01T00:00:00Z"
CLAIMED = "2026-07-02T00:00:00Z"


def _manifest(identity) -> dict[str, str]:
    run = identity.to_dict()["run_fingerprint"]
    plan = pipeline_final.pipeline_final_boundary_plan(
        start_inclusive_utc=START,
        end_exclusive_utc=END,
    )
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
        "run_fingerprint": (
            "protocol_v3_run_sha256:" + run["fingerprint_sha256"]
        ),
        "search_budget_sha256": "b" * 64,
        "seed_policy_sha256": "c" * 64,
        "simulator_contract_sha256": "d" * 64,
        "stop_policy_sha256": "e" * 64,
        "trial_ledger_head_sha256": run["trial_ledger_head"]["head_sha256"],
    }


def _sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, identity):
    registered = datetime(2026, 7, 1, tzinfo=UTC)
    claimed = datetime(2026, 7, 2, tzinfo=UTC)
    monkeypatch.setattr(pipeline_final, "_utc_now", lambda: registered)
    registration = pipeline_final.build_pipeline_final_registration(
        registration_id="task31_checkpoint_fixture",
        registered_at_utc=REGISTERED,
        start_inclusive_utc=START,
        end_exclusive_utc=END,
        frozen_identity_manifest=_manifest(identity),
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
        claimed_at_utc=CLAIMED,
    )
    progress = start_pipeline_final_progress(registration, claim)
    return registration, claim, progress


def _built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    built = task13.build_state(tmp_path, monkeypatch)
    registration, claim, progress = _sources(tmp_path, monkeypatch, built["identity"])
    receipt = checkpointing.build_pipeline_final_checkpoint_receipt(
        progress,
        registration=registration,
        claim=claim,
    )
    return built, registration, claim, progress, receipt


def test_receipt_roundtrip_is_result_blind_and_replay_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, registration, claim, progress, receipt = _built(tmp_path, monkeypatch)
    payload = receipt.to_dict()
    assert payload["completed_origin_count"] == 0
    assert payload["next_origin_index"] == 1
    assert payload["progress_status"] == "CLAIMED_NOT_STARTED"
    assert payload["checkpoint_role"] == "RESULT_BLIND_PROGRESS_ONLY"
    serialized = json.dumps(payload).lower()
    for forbidden in (
        '"pnl"',
        '"mtm"',
        '"equity"',
        '"trades"',
        '"rankings"',
        '"candles"',
        '"raw_market_data"',
    ):
        assert forbidden not in serialized
    assert (
        checkpointing.verify_replayed_pipeline_final_checkpoint(
            receipt,
            progress,
            registration=registration,
            claim=claim,
        )
        == progress
    )

    changed = deepcopy(payload)
    changed["progress_sha256"] = "0" * 64
    basis = dict(changed)
    basis.pop("receipt_sha256")
    changed["receipt_sha256"] = checkpointing._digest(basis)
    changed_receipt = checkpointing.validate_pipeline_final_checkpoint_receipt(
        changed
    )
    with pytest.raises(
        checkpointing.PipelineFinalCheckpointError,
        match="replayed pipeline-final progress differs",
    ):
        checkpointing.verify_replayed_pipeline_final_checkpoint(
            changed_receipt,
            progress,
            registration=registration,
            claim=claim,
        )


def test_task13_atomically_stores_and_resumes_only_the_compact_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built, _, _, _, receipt = _built(tmp_path, monkeypatch)
    committed = checkpointing.commit_pipeline_final_checkpoint(
        receipt,
        identity=built["identity"],
        pre_run_manifest=built["manifest"],
        seed_state=built["seed"],
        budget_usage=built["budget"],
        stop_state=built["stop"],
        repository_root=built["repo"],
        trial_ledger_root=built["ledger_root"],
        owner_id="task31-checkpoint-test",
    )
    resumed = checkpointing.read_pipeline_final_checkpoint(
        current_identity=built["identity"],
        current_pre_run_manifest=built["manifest"],
        repository_root=built["repo"],
    )
    assert resumed is not None
    assert resumed.receipt == receipt
    assert resumed.checkpoint == committed.checkpoint
    result = resumed.checkpoint.to_dict()["result"]
    assert result["status"] == "IN_PROGRESS"
    assert set(result["payload"]) == {
        "task31_pipeline_final_checkpoint_receipt"
    }
    stored = result["payload"]["task31_pipeline_final_checkpoint_receipt"]
    assert stored["safety"]["outer_result_values_stored"] is False
    assert stored["safety"]["final_report_visible"] is False
    assert stored["safety"]["task31_attestation_available"] is False


def test_transaction_run_pipeline_code_and_trial_head_mismatches_are_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built, _, _, _, receipt = _built(tmp_path, monkeypatch)
    cases = {
        "run_fingerprint": "protocol_v3_run_sha256:" + "0" * 64,
        "pipeline_generation_id": "protocol_v3_pipeline_sha256:" + "0" * 64,
        "code_commit": "0" * 40,
        "trial_ledger_head_sha256": "0" * 64,
    }
    for field, value in cases.items():
        changed = deepcopy(receipt.to_dict())
        changed[field] = value
        basis = dict(changed)
        basis.pop("receipt_sha256")
        changed["receipt_sha256"] = checkpointing._digest(basis)
        wrong = checkpointing.validate_pipeline_final_checkpoint_receipt(changed)
        with pytest.raises(
            checkpointing.PipelineFinalCheckpointError,
            match="Task-13 transaction uses another",
        ):
            checkpointing.commit_pipeline_final_checkpoint(
                wrong,
                identity=built["identity"],
                pre_run_manifest=built["manifest"],
                seed_state=built["seed"],
                budget_usage=built["budget"],
                stop_state=built["stop"],
                repository_root=built["repo"],
                trial_ledger_root=built["ledger_root"],
                owner_id=f"task31-wrong-{field}",
            )


def test_receipt_rejects_result_keys_and_inconsistent_progress_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, _, _, receipt = _built(tmp_path, monkeypatch)
    payload = receipt.to_dict()
    payload["pnl"] = "hidden"
    basis = dict(payload)
    basis.pop("receipt_sha256")
    payload["receipt_sha256"] = checkpointing._digest(basis)
    with pytest.raises(
        checkpointing.PipelineFinalCheckpointError,
        match="fields or versions",
    ):
        checkpointing.validate_pipeline_final_checkpoint_receipt(payload)

    payload = receipt.to_dict()
    payload["completed_origin_count"] = 1
    basis = dict(payload)
    basis.pop("receipt_sha256")
    payload["receipt_sha256"] = checkpointing._digest(basis)
    with pytest.raises(
        checkpointing.PipelineFinalCheckpointError,
        match="cursor, status, or chain head",
    ):
        checkpointing.validate_pipeline_final_checkpoint_receipt(payload)


def test_task31_checkpoint_api_is_exact() -> None:
    assert checkpointing.__all__ == pipeline_final_checkpoint_api.__all__
