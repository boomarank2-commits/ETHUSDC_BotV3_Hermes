"""Task-24 tests for origin-bound, resumable outer rotation state."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import importlib.util
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import inner_selection, outer_origins
from ethusdc_bot.protocol_v3 import runtime_state as runtime
from ethusdc_bot.protocol_v3 import transactional_cache_model as tx

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK23_PATH = Path(__file__).with_name("test_protocol_v3_outer_origins.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task24_support", _TASK23_PATH)
assert _SPEC is not None and _SPEC.loader is not None
task23 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task23)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base, plan, requests = task23.state.__wrapped__(tmp_path, monkeypatch)
    process = outer_origins.orchestrate_outer_origins(plan, requests)
    row = process.to_dict()["origins"][0]
    rotation = runtime.build_outer_rotation_state(
        plan.origins[0],
        new_candidate_bundle_sha256=row["frozen_candidate_bundle"]["bundle_sha256"],
    )
    slot = tx.build_rotation_state_identity_slot(
        rotation,
        origin=plan.origins[0],
        outer_process=process,
        boundary_plan=plan,
    )
    decision = inner_selection.validate_selection_decision(row["selection_decision"])
    fold_identity = requests[0].frozen_selection_config.to_dict()["fold_identity"]
    identity = tx.build_transaction_identity(
        run_fingerprint=base["fingerprint"],
        context_binding=base["binding"],
        horizon_policy=task23.support.HORIZON,
        work_unit_id="origin_01_cycle_01",
        candidate_identity=tx.build_bound_identity_slot(
            tx.CANDIDATE_SLOT,
            tx.CANDIDATE_SELECTION_IDENTITY_SCHEMA,
            decision.candidate_identity_payload,
        ),
        fold_identity=tx.build_bound_identity_slot(
            tx.FOLD_SLOT, tx.FOLD_IDENTITY_SCHEMA, fold_identity
        ),
        rotation_state_identity=slot,
        sealed_store_heads=tx.build_sealed_store_heads_slot(
            [base["index_path"]], base["repo"]
        ),
        repository_root=base["repo"],
    )
    return base, plan, process, rotation, slot, identity, requests


def test_rotation_identity_binds_task22_bundle_task23_origin_and_t_plus_24(state) -> None:
    _, plan, process, rotation, slot, identity, _ = state
    payload = slot.to_dict()["payload"]
    row = process.to_dict()["origins"][0]
    assert payload["outer_process_sha256"] == process.process_sha256
    assert payload["origin_selection_sha256"] == row["origin_sha256"]
    assert payload["selection_decision_sha256"] == row["selection_decision"]["decision_sha256"]
    assert payload["candidate_bundle_sha256"] == row["frozen_candidate_bundle"]["bundle_sha256"]
    assert rotation.valid_from_utc - rotation.anchor_utc == timedelta(hours=24)
    assert rotation.entry_enabled_at_utc == rotation.valid_from_utc
    assert rotation.entry_allowed_at(rotation.valid_from_utc)
    assert runtime.restore_outer_rotation_state(
        payload["rotation_state"], origin=plan.origins[0]
    ) == rotation
    assert tx.validate_transaction_identity(
        identity, repository_root=state[0]["repo"]
    ) == identity


def test_rotation_binding_rejects_wrong_origin_or_frozen_bundle(state) -> None:
    _, plan, process, rotation, _, _, _ = state
    with pytest.raises(runtime.RuntimeStateError, match="origin index"):
        tx.build_rotation_state_identity_slot(
            rotation, origin=plan.origins[1], outer_process=process, boundary_plan=plan
        )
    wrong_bundle = runtime.build_outer_rotation_state(
        plan.origins[0], new_candidate_bundle_sha256="9" * 64
    )
    with pytest.raises(tx.ProtocolV3TransactionError, match="frozen bundle"):
        tx.build_rotation_state_identity_slot(
            wrong_bundle,
            origin=plan.origins[0],
            outer_process=process,
            boundary_plan=plan,
        )


def test_rehashed_rotation_semantic_tampering_fails_closed(state) -> None:
    base, _, _, _, _, identity, _ = state
    bad = deepcopy(identity.to_dict())
    rotation_slot = next(
        row for row in bad["identity_slots"] if row["name"] == tx.ROTATION_SLOT
    )
    rotation_slot["payload"]["rotation_state"]["entry_enabled_at_utc"] = (
        rotation_slot["payload"]["rotation_state"]["anchor_utc"]
    )
    rotation_slot["payload"]["rotation_state_sha256"] = tx.digest(
        rotation_slot["payload"]["rotation_state"]
    )
    slot_basis = dict(rotation_slot)
    slot_basis.pop("slot_sha256")
    rotation_slot["slot_sha256"] = tx.digest(slot_basis)
    identity_basis = dict(bad)
    identity_basis.pop("identity_sha256")
    identity_basis.pop("transaction_id")
    changed_sha = tx.digest(identity_basis)
    bad["identity_sha256"] = changed_sha
    bad["transaction_id"] = f"{tx.TRANSACTION_PREFIX}:{changed_sha}"
    with pytest.raises((runtime.RuntimeStateError, tx.ProtocolV3TransactionError)):
        tx.validate_transaction_identity(bad, repository_root=base["repo"])


def test_rotation_change_changes_transaction_and_resume_namespace(state) -> None:
    base, plan, process, rotation, _, identity, requests = state
    second_row = process.to_dict()["origins"][1]
    changed_rotation = runtime.build_outer_rotation_state(
        plan.origins[1],
        new_candidate_bundle_sha256=second_row["frozen_candidate_bundle"]["bundle_sha256"],
    )
    changed_slot = tx.build_rotation_state_identity_slot(
        changed_rotation,
        origin=plan.origins[1],
        outer_process=process,
        boundary_plan=plan,
    )
    decision = inner_selection.validate_selection_decision(second_row["selection_decision"])
    changed_identity = tx.build_transaction_identity(
        run_fingerprint=base["fingerprint"],
        context_binding=base["binding"],
        horizon_policy=task23.support.HORIZON,
        work_unit_id="origin_02_cycle_01",
        candidate_identity=tx.build_bound_identity_slot(
            tx.CANDIDATE_SLOT,
            tx.CANDIDATE_SELECTION_IDENTITY_SCHEMA,
            decision.candidate_identity_payload,
        ),
        fold_identity=tx.build_bound_identity_slot(
            tx.FOLD_SLOT,
            tx.FOLD_IDENTITY_SCHEMA,
            requests[1].frozen_selection_config.to_dict()["fold_identity"],
        ),
        rotation_state_identity=changed_slot,
        sealed_store_heads=tx.build_sealed_store_heads_slot(
            [base["index_path"]], base["repo"]
        ),
        repository_root=base["repo"],
    )
    assert changed_identity.identity_sha256 != identity.identity_sha256
    assert changed_identity.transaction_id != identity.transaction_id
    assert changed_rotation.state_sha256 != rotation.state_sha256
    assert runtime.restore_outer_rotation_state(changed_rotation.basis()) == changed_rotation


def test_noncanonical_persisted_timestamp_is_rejected(state) -> None:
    _, _, _, rotation, _, _, _ = state
    bad = deepcopy(rotation.basis())
    bad["anchor_utc"] = bad["anchor_utc"].replace("Z", "+00:00")
    with pytest.raises(runtime.RuntimeStateError, match="not canonical"):
        runtime.restore_outer_rotation_state(bad)
