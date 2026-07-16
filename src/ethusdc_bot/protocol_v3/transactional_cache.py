"""Stable Protocol v3 Task-13 cache and transactional-resume surface."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from . import transactional_cache_model as _model
from . import transactional_cache_store as _store
from .trial_ledger import read_trial_ledger, record_cache_reuse


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


# Bind the Task-13 adapter to the actual immutable Task-4 ledger schema.
_store._resolve_ledger_receipt = _resolve_ledger_receipt
_store._validate_cache_ledger = _validate_cache_ledger
_store._verify_receipt_event = _verify_receipt_event

for _module in (_model, _store):
    for _name in _module.__all__:
        globals()[_name] = getattr(_module, _name)

__all__ = list(dict.fromkeys([*_model.__all__, *_store.__all__]))
