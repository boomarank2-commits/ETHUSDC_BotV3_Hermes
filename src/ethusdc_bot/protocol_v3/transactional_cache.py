"""Stable Protocol v3 cache/resume surface with Task-15 selection binding."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import transactional_cache_model as _model
from . import transactional_cache_store as _store
from .inner_selection_api import (
    CANDIDATE_SELECTION_IDENTITY_SCHEMA,
    NO_TRADE,
    validate_candidate_selection_identity_payload,
)
from .trial_ledger import read_trial_ledger, record_cache_reuse


# The public facade patches the exact model object already used by the Task-13
# store. Public build, validate, checkpoint and cache calls therefore share one
# validation path without copying the persistence engine.
_model.TRANSACTION_CONTRACT_SCHEMA = "protocol_v3_transaction_contract_v3"
_model.TRANSACTION_CONTRACT_VERSION = (
    "protocol_v3_content_addressed_cache_and_transactional_resume_"
    "with_inner_selection_v3"
)
_model.TRANSACTION_IDENTITY_SCHEMA_VERSION = "protocol_v3_transaction_identity_v3"
_model.CANDIDATE_SELECTION_IDENTITY_SCHEMA = CANDIDATE_SELECTION_IDENTITY_SCHEMA

_task15_contract = deepcopy(_model.CANONICAL_CONTRACT)
_task15_contract["schema_version"] = _model.TRANSACTION_CONTRACT_SCHEMA
_task15_contract["contract_version"] = _model.TRANSACTION_CONTRACT_VERSION
_task15_contract["transaction_identity_schema_version"] = (
    _model.TRANSACTION_IDENTITY_SCHEMA_VERSION
)
_task15_contract["identity_policy"]["bound_candidate_selection_required"] = True
_task15_contract["deferred_scope"] = {
    "candidate_daily_matrix_task": 16,
    "pbo_task": 17,
    "dsr_task": 18,
    "router_task": 22,
    "outer_orchestration_task": 23,
    "rotation_persistence_task": 24,
    "final_evaluator_task": 31,
}
_model.CANONICAL_CONTRACT = _task15_contract


def _validate_candidate_slot(
    slots: Mapping[str, _model.IdentitySlot],
    repository_root: str | Path,
) -> None:
    del repository_root
    row = slots[_model.CANDIDATE_SLOT].to_dict()
    if row["state"] != _model.BOUND:
        raise _model.ProtocolV3TransactionError(
            "candidate_identity must be BOUND to a Task-15 selection decision"
        )
    if row["identity_schema"] != CANDIDATE_SELECTION_IDENTITY_SCHEMA:
        raise _model.ProtocolV3TransactionError(
            "candidate_identity schema is not the Task-15 selection schema"
        )
    if row["reason"] != "bound":
        raise _model.ProtocolV3TransactionError("candidate_identity reason is invalid")
    try:
        normalized = validate_candidate_selection_identity_payload(row["payload"])
    except Exception as exc:
        raise _model.ProtocolV3TransactionError(
            f"candidate_identity is not a valid Task-15 decision: {exc}"
        ) from exc
    if row["payload"] != normalized:
        raise _model.ProtocolV3TransactionError(
            "candidate_identity payload is not canonical"
        )

    decision = normalized["decision"]
    if decision["fixture_only"] is True:
        raise _model.ProtocolV3TransactionError(
            "synthetic Task-15 candidate decisions cannot enter transaction state"
        )
    if decision["outcome"] != NO_TRADE or decision["selected_candidate"] is not None:
        raise _model.ProtocolV3TransactionError(
            "Task-15 production transaction state must remain NO_TRADE until Tasks 16-18"
        )

    config = decision["frozen_pipeline_config"]
    run = config["run_fingerprint"]
    expected_slots = {
        _model.RAW_DATA_SLOT: run["raw_data"],
        _model.CODE_PIPELINE_SLOT: {
            "code": run["code"],
            "pipeline": run["pipeline"],
        },
        _model.FEATURE_SLOT: run["features"],
        _model.CONTEXT_SLOT: run["context"]["runtime_binding"],
        _model.BOUNDARY_SLOT: run["boundary"],
        _model.SIMULATOR_SLOT: run["simulator"],
        _model.COST_SLOT: run["cost_model"],
        _model.QUALITY_SLOT: run["quality_gates"],
        _model.EXCHANGE_SLOT: run["exchange_info"],
        _model.TRIAL_LEDGER_SLOT: run["trial_ledger_head"],
    }
    for name, expected in expected_slots.items():
        observed = slots[name].to_dict()
        if observed["state"] != _model.BOUND or observed["payload"] != expected:
            raise _model.ProtocolV3TransactionError(
                f"candidate selection identity differs from transaction slot: {name}"
            )
    if config["fold_identity"] != slots[_model.FOLD_SLOT].to_dict()["payload"]:
        raise _model.ProtocolV3TransactionError(
            "candidate selection and transaction use different Task-14 fold identities"
        )


def _validate_transition_slots_task15(
    slots: Mapping[str, _model.IdentitySlot],
    repository_root: str | Path,
    horizon_policy: Any,
) -> None:
    _validate_candidate_slot(slots, repository_root)
    rotation = slots[_model.ROTATION_SLOT].to_dict()
    if rotation != _model.build_genesis_identity_slot(
        _model.ROTATION_SLOT,
        _model.ROTATION_GENESIS_SCHEMA,
        "no_rotation_state",
    ).to_dict():
        raise _model.ProtocolV3TransactionError(
            "rotation_state_identity is not the canonical genesis state"
        )
    _model._validate_fold_slot(
        slots[_model.FOLD_SLOT], repository_root, horizon_policy
    )


_model._validate_transition_slots = _validate_transition_slots_task15
for _extra_name in (
    "CANDIDATE_SELECTION_IDENTITY_SCHEMA",
    "CANONICAL_CONTRACT",
):
    if _extra_name not in _model.__all__:
        _model.__all__.append(_extra_name)


def _event_sha256(event: Mapping[str, Any]) -> str:
    return _model.sha256(event.get("event_sha256"), "trial_ledger.event_sha256")


def _resolve_ledger_receipt(
    identity: _model.TransactionIdentity,
    trial_ledger_root: str | Path,
    cache_record: _model.CacheRecord | None,
    previous: _model.TransactionCheckpoint | None,
    fault: _store.FaultInjector | None,
    repo: Path,
) -> dict[str, Any]:
    decision = identity.to_dict()["run_fingerprint"]["trial_ledger_head"]
    ledger = read_trial_ledger(trial_ledger_root)
    if cache_record is None:
        if (
            previous is not None
            and previous.to_dict()["ledger_receipt"]["state"]
            == "CACHE_REUSE_RECORDED"
        ):
            receipt = previous.to_dict()["ledger_receipt"]
            _verify_receipt_event(ledger, receipt)
            return receipt
        if (
            ledger.status.head_sha256 != decision["head_sha256"]
            or ledger.status.event_count != decision["event_count"]
        ):
            raise _model.ProtocolV3TransactionError(
                "trial ledger changed after decision identity"
            )
        return {
            "schema_version": "protocol_v3_checkpoint_ledger_receipt_v1",
            "state": "NO_CACHE_REUSE",
            "decision_head_sha256": decision["head_sha256"],
            "decision_event_count": decision["event_count"],
            "event_key": "NOT_APPLICABLE",
            "event_sequence": 0,
            "event_hash": _model.ZERO_HASH,
        }

    record = _store.validate_cache_record(cache_record, repository_root=repo)
    payload = record.to_dict()
    trial_id = payload["trial_id"]
    reuse_scope = {
        "cache_record_id": payload["cache_record_id"],
        "transaction_id": identity.transaction_id,
        "checkpoint_id": payload["checkpoint_id"],
        "work_unit_id": identity.work_unit_id,
    }
    event_key = "cache_reuse:" + _model.digest(
        {"trial_id": trial_id, "reuse_scope": reuse_scope}
    )
    matching = [
        event
        for event in ledger.events
        if event.get("payload", {}).get("event_key") == event_key
    ]
    if matching:
        event = matching[0]
        event_sha = _event_sha256(event)
        if (
            len(matching) != 1
            or event["sequence"] != decision["event_count"] + 1
            or ledger.status.event_count != event["sequence"]
            or ledger.status.head_sha256 != event_sha
        ):
            raise _model.ProtocolV3TransactionError(
                "ledger advanced beyond the idempotent cache-reuse event"
            )
    else:
        if (
            ledger.status.head_sha256 != decision["head_sha256"]
            or ledger.status.event_count != decision["event_count"]
        ):
            raise _model.ProtocolV3TransactionError(
                "cache reuse decision ledger head is stale"
            )
        ledger = record_cache_reuse(
            trial_ledger_root,
            trial_id=trial_id,
            reuse_scope=reuse_scope,
        )
        matching = [
            event
            for event in ledger.events
            if event.get("payload", {}).get("event_key") == event_key
        ]
        if len(matching) != 1:
            raise _model.ProtocolV3TransactionError(
                "cache reuse ledger event was not committed exactly once"
            )
        event = matching[0]
        event_sha = _event_sha256(event)
        if (
            ledger.status.event_count != event["sequence"]
            or ledger.status.head_sha256 != event_sha
        ):
            raise _model.ProtocolV3TransactionError(
                "cache reuse ledger head does not match the committed event"
            )
    _store._fault(fault, "after_ledger_reuse_append")
    return {
        "schema_version": "protocol_v3_checkpoint_ledger_receipt_v1",
        "state": "CACHE_REUSE_RECORDED",
        "decision_head_sha256": decision["head_sha256"],
        "decision_event_count": decision["event_count"],
        "event_key": event_key,
        "event_sequence": event["sequence"],
        "event_hash": event_sha,
    }


def _validate_cache_ledger(
    record: _model.CacheRecord,
    identity: _model.TransactionIdentity,
    trial_ledger_root: str | Path,
) -> None:
    payload = record.to_dict()
    ledger = read_trial_ledger(trial_ledger_root)
    if payload["trial_id"] not in ledger.trials:
        raise _model.ProtocolV3TransactionError(
            "cache hit references a trial absent from the permanent ledger"
        )
    decision = identity.to_dict()["run_fingerprint"]["trial_ledger_head"]
    if (
        ledger.status.head_sha256 == decision["head_sha256"]
        and ledger.status.event_count == decision["event_count"]
    ):
        return
    reuse_scope = {
        "cache_record_id": payload["cache_record_id"],
        "transaction_id": identity.transaction_id,
        "checkpoint_id": payload["checkpoint_id"],
        "work_unit_id": identity.work_unit_id,
    }
    event_key = "cache_reuse:" + _model.digest(
        {"trial_id": payload["trial_id"], "reuse_scope": reuse_scope}
    )
    matching = [
        event
        for event in ledger.events
        if event.get("payload", {}).get("event_key") == event_key
    ]
    if len(matching) != 1:
        raise _model.ProtocolV3TransactionError(
            "cache hit ledger reuse event is missing or duplicated"
        )
    event = matching[0]
    if (
        event["sequence"] != decision["event_count"] + 1
        or ledger.status.event_count != event["sequence"]
        or ledger.status.head_sha256 != _event_sha256(event)
    ):
        raise _model.ProtocolV3TransactionError(
            "cache hit blocked: permanent ledger is not at the decision head "
            "or its single idempotent cache-reuse successor"
        )


def _verify_receipt_event(ledger: Any, receipt: Mapping[str, Any]) -> None:
    matching = [
        event
        for event in ledger.events
        if event.get("payload", {}).get("event_key") == receipt["event_key"]
    ]
    if len(matching) != 1:
        raise _model.ProtocolV3TransactionError(
            "checkpoint ledger receipt event is absent or duplicated"
        )
    event = matching[0]
    event_sha = _event_sha256(event)
    if (
        event["sequence"] != receipt["event_sequence"]
        or event_sha != receipt["event_hash"]
        or ledger.status.event_count != event["sequence"]
        or ledger.status.head_sha256 != event_sha
    ):
        raise _model.ProtocolV3TransactionError(
            "checkpoint ledger receipt event is changed or no longer the head"
        )


_store._resolve_ledger_receipt = _resolve_ledger_receipt
_store._validate_cache_ledger = _validate_cache_ledger
_store._verify_receipt_event = _verify_receipt_event

for _module in (_model, _store):
    for _name in _module.__all__:
        globals()[_name] = getattr(_module, _name)

__all__ = list(dict.fromkeys([*_model.__all__, *_store.__all__]))
