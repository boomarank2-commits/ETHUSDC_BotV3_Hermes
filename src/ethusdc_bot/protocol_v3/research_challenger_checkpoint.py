"""Task-29 compact checkpoint receipts over the existing Task-13 store.

No market bars or duplicate runtime state are stored here.  A checkpoint contains
only content identities and cursors.  After restart, Task 29 must replay the
public three-market prefix and prove that the rebuilt state matches this receipt.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from ethusdc_bot.protocol_v3.pipeline import BudgetUsage, PreRunManifest
from ethusdc_bot.protocol_v3.research_challenger import (
    ResearchChallengerError,
    ResearchChallengerState,
    ZERO_HASH,
    validate_research_challenger_state,
)
from ethusdc_bot.protocol_v3.transactional_cache_api import (
    TransactionCheckpoint,
    TransactionIdentity,
    acquire_transaction_lock,
    commit_checkpoint,
    release_transaction_lock,
    resume_last_committed_checkpoint,
    validate_transaction_identity,
)

RECEIPT_SCHEMA_VERSION: Final = (
    "protocol_v3_research_challenger_checkpoint_receipt_v1"
)
RECEIPT_CONTRACT_VERSION: Final = (
    "protocol_v3_task13_replay_verified_research_challenger_checkpoint_v1"
)
_SAFETY: Final = {
    "raw_market_data_stored": False,
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "live": "locked",
    "trading_api": "forbidden",
}


@dataclass(frozen=True)
class ResearchChallengerCheckpointReceipt:
    canonical_json: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


@dataclass(frozen=True)
class ResearchChallengerCheckpoint:
    checkpoint: TransactionCheckpoint
    receipt: ResearchChallengerCheckpointReceipt


def build_research_challenger_checkpoint_receipt(
    state: ResearchChallengerState,
) -> ResearchChallengerCheckpointReceipt:
    root = validate_research_challenger_state(state).to_dict()
    ledger = root["forward_ledger"]
    task28 = root["task28_decision"]
    selection = task28["current_origin"]["selection_decision"]
    basis = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "contract_version": RECEIPT_CONTRACT_VERSION,
        "research_state_sha256": root["state_sha256"],
        "task28_report_sha256": root["task28_report_sha256"],
        "task28_bundle_sha256": root["bundle_sha256"],
        "selection_decision_sha256": selection["decision_sha256"],
        "run_fingerprint_sha256": root["run_fingerprint_sha256"],
        "pipeline_generation_id": root["pipeline_generation_id"],
        "forward_ledger_namespace": root["forward_ledger_namespace"],
        "forward_ledger_head_sha256": ledger["head_sha256"],
        "forward_ledger_record_count": ledger["record_count"],
        "started_at_utc": root["started_at_utc"],
        "activation_open_time_ms": root["activation_open_time_ms"],
        "warmup_start_open_time_ms": root["warmup_start_open_time_ms"],
        "last_engine_open_time_ms": root["last_engine_open_time_ms"],
        "last_processed_open_time_ms": root["last_processed_open_time_ms"],
        "mode": root["mode"],
        "safety": _SAFETY,
    }
    return validate_research_challenger_checkpoint_receipt(
        {**basis, "receipt_sha256": _digest(basis)}
    )


def validate_research_challenger_checkpoint_receipt(
    value: ResearchChallengerCheckpointReceipt | Mapping[str, Any],
) -> ResearchChallengerCheckpointReceipt:
    root = (
        value.to_dict()
        if isinstance(value, ResearchChallengerCheckpointReceipt)
        else dict(_mapping(value, "research_challenger_checkpoint_receipt"))
    )
    required = {
        "schema_version",
        "contract_version",
        "research_state_sha256",
        "task28_report_sha256",
        "task28_bundle_sha256",
        "selection_decision_sha256",
        "run_fingerprint_sha256",
        "pipeline_generation_id",
        "forward_ledger_namespace",
        "forward_ledger_head_sha256",
        "forward_ledger_record_count",
        "started_at_utc",
        "activation_open_time_ms",
        "warmup_start_open_time_ms",
        "last_engine_open_time_ms",
        "last_processed_open_time_ms",
        "mode",
        "safety",
        "receipt_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != RECEIPT_SCHEMA_VERSION
        or root["contract_version"] != RECEIPT_CONTRACT_VERSION
    ):
        raise ResearchChallengerError(
            "research-challenger checkpoint receipt fields are invalid"
        )
    for name in (
        "research_state_sha256",
        "task28_report_sha256",
        "task28_bundle_sha256",
        "selection_decision_sha256",
        "run_fingerprint_sha256",
        "forward_ledger_head_sha256",
        "receipt_sha256",
    ):
        _sha(root[name], name)
    if not isinstance(root["pipeline_generation_id"], str) or not root[
        "pipeline_generation_id"
    ]:
        raise ResearchChallengerError("checkpoint pipeline generation is invalid")
    if not isinstance(root["forward_ledger_namespace"], str) or not root[
        "forward_ledger_namespace"
    ]:
        raise ResearchChallengerError("checkpoint forward namespace is invalid")
    count = root["forward_ledger_record_count"]
    if type(count) is not int or count < 0:
        raise ResearchChallengerError("checkpoint ledger count is invalid")
    if count == 0 and root["forward_ledger_head_sha256"] != ZERO_HASH:
        raise ResearchChallengerError("empty checkpoint ledger must use the zero head")
    if count > 0 and root["forward_ledger_head_sha256"] == ZERO_HASH:
        raise ResearchChallengerError("non-empty checkpoint ledger cannot use zero head")
    for name in (
        "activation_open_time_ms",
        "warmup_start_open_time_ms",
    ):
        value_ms = root[name]
        if type(value_ms) is not int or value_ms < 0 or value_ms % 60_000:
            raise ResearchChallengerError(f"checkpoint {name} is invalid")
    if root["warmup_start_open_time_ms"] > root["activation_open_time_ms"]:
        raise ResearchChallengerError("checkpoint warmup begins after activation")
    for name in ("last_engine_open_time_ms", "last_processed_open_time_ms"):
        value_ms = root[name]
        if value_ms is not None and (
            type(value_ms) is not int or value_ms < 0 or value_ms % 60_000
        ):
            raise ResearchChallengerError(f"checkpoint {name} is invalid")
    if count == 0 and root["last_processed_open_time_ms"] is not None:
        raise ResearchChallengerError("empty checkpoint ledger has a forward cursor")
    if count > 0 and root["last_processed_open_time_ms"] is None:
        raise ResearchChallengerError("non-empty checkpoint ledger lacks a cursor")
    if root["mode"] not in {"CASH", "RESEARCH_CHALLENGER"}:
        raise ResearchChallengerError("checkpoint challenger mode is invalid")
    if not isinstance(root["started_at_utc"], str) or not root[
        "started_at_utc"
    ].endswith("Z"):
        raise ResearchChallengerError("checkpoint start timestamp is invalid")
    if root["safety"] != _SAFETY:
        raise ResearchChallengerError("checkpoint safety locks are invalid")
    observed = root["receipt_sha256"]
    basis = dict(root)
    basis.pop("receipt_sha256")
    if observed != _digest(basis):
        raise ResearchChallengerError("checkpoint receipt digest mismatch")
    return ResearchChallengerCheckpointReceipt(_canonical(basis), observed)


def commit_research_challenger_checkpoint(
    receipt: ResearchChallengerCheckpointReceipt,
    *,
    identity: TransactionIdentity,
    pre_run_manifest: PreRunManifest,
    seed_state: Mapping[str, Any],
    budget_usage: BudgetUsage,
    stop_state: Mapping[str, Any],
    repository_root: str | Path,
    trial_ledger_root: str | Path,
    owner_id: str,
) -> ResearchChallengerCheckpoint:
    validated = validate_research_challenger_checkpoint_receipt(receipt)
    _assert_receipt_identity(validated, identity, repository_root)
    lock = acquire_transaction_lock(
        identity.transaction_id,
        repository_root,
        owner_id=owner_id,
    )
    try:
        checkpoint = commit_checkpoint(
            identity=identity,
            pre_run_manifest=pre_run_manifest,
            seed_state=seed_state,
            budget_usage=budget_usage,
            stop_state=stop_state,
            result_status="IN_PROGRESS",
            result_payload={"task29_checkpoint_receipt": validated.to_dict()},
            repository_root=repository_root,
            trial_ledger_root=trial_ledger_root,
            lock=lock,
        )
    finally:
        release_transaction_lock(lock, repository_root)
    return ResearchChallengerCheckpoint(checkpoint, validated)


def read_research_challenger_checkpoint(
    *,
    current_identity: TransactionIdentity,
    current_pre_run_manifest: PreRunManifest,
    repository_root: str | Path,
) -> ResearchChallengerCheckpoint | None:
    checkpoint = resume_last_committed_checkpoint(
        current_identity=current_identity,
        current_pre_run_manifest=current_pre_run_manifest,
        repository_root=repository_root,
    )
    if checkpoint is None:
        return None
    payload = checkpoint.to_dict()
    result = dict(_mapping(payload["result"], "checkpoint.result"))
    if result.get("status") != "IN_PROGRESS":
        raise ResearchChallengerError(
            "Task-29 checkpoint must remain an in-progress research receipt"
        )
    result_payload = dict(_mapping(result.get("payload"), "checkpoint.result.payload"))
    if set(result_payload) != {"task29_checkpoint_receipt"}:
        raise ResearchChallengerError(
            "Task-29 checkpoint payload contains unexpected state"
        )
    receipt = validate_research_challenger_checkpoint_receipt(
        result_payload["task29_checkpoint_receipt"]
    )
    _assert_receipt_identity(receipt, current_identity, repository_root)
    return ResearchChallengerCheckpoint(checkpoint, receipt)


def verify_replayed_research_challenger_checkpoint(
    receipt: ResearchChallengerCheckpointReceipt,
    replayed_state: ResearchChallengerState,
) -> ResearchChallengerState:
    expected = validate_research_challenger_checkpoint_receipt(receipt).to_dict()
    state = validate_research_challenger_state(replayed_state)
    rebuilt = build_research_challenger_checkpoint_receipt(state).to_dict()
    if rebuilt != expected:
        raise ResearchChallengerError(
            "replayed public-data state differs from the committed Task-29 checkpoint"
        )
    return state


def _assert_receipt_identity(
    receipt: ResearchChallengerCheckpointReceipt,
    identity: TransactionIdentity,
    repository_root: str | Path,
) -> None:
    expected = validate_research_challenger_checkpoint_receipt(receipt).to_dict()
    tx = validate_transaction_identity(identity, repository_root=repository_root).to_dict()
    run = tx["run_fingerprint"]
    if run["fingerprint_sha256"] != expected["run_fingerprint_sha256"]:
        raise ResearchChallengerError(
            "Task-13 transaction uses another run fingerprint"
        )
    pipeline = run["pipeline"]
    if (
        pipeline["generation_id"] != expected["pipeline_generation_id"]
        or pipeline["forward_ledger_namespace"]
        != expected["forward_ledger_namespace"]
    ):
        raise ResearchChallengerError(
            "Task-13 transaction uses another pipeline generation"
        )
    slots = {row["name"]: row for row in tx["identity_slots"]}
    candidate = slots["candidate_identity"]["payload"]
    if candidate["decision_sha256"] != expected["selection_decision_sha256"]:
        raise ResearchChallengerError(
            "Task-13 candidate identity differs from the Task-29 source decision"
        )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchChallengerError(f"{name} must be an object")
    return value


def _sha(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ResearchChallengerError(f"{name} must be lowercase sha256")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


__all__ = [
    "RECEIPT_CONTRACT_VERSION",
    "RECEIPT_SCHEMA_VERSION",
    "ResearchChallengerCheckpoint",
    "ResearchChallengerCheckpointReceipt",
    "build_research_challenger_checkpoint_receipt",
    "commit_research_challenger_checkpoint",
    "read_research_challenger_checkpoint",
    "validate_research_challenger_checkpoint_receipt",
    "verify_replayed_research_challenger_checkpoint",
]
