"""Task-31 result-blind progress checkpoints over the existing Task-13 store.

The adapter stores only the compact, already validated Task-31 progress identity.
It never persists outer PnL, MTM, equity, trades, rankings, gate results, market
bars, or a final report.  Resume therefore restores an immutable receipt and
requires the caller to replay and revalidate the causal twelve-origin process.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from ethusdc_bot.protocol_v3.pipeline import BudgetUsage, PreRunManifest
from ethusdc_bot.protocol_v3.pipeline_final import (
    PipelineFinalClaim,
    PipelineFinalError,
    PipelineFinalRegistration,
    validate_pipeline_final_claim,
    validate_pipeline_final_registration,
)
from ethusdc_bot.protocol_v3.pipeline_final_progress import (
    ZERO_HASH,
    PipelineFinalProgress,
    validate_pipeline_final_progress,
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

RECEIPT_SCHEMA_VERSION: Final = "protocol_v3_pipeline_final_checkpoint_receipt_v1"
RECEIPT_CONTRACT_VERSION: Final = (
    "protocol_v3_task13_result_blind_pipeline_final_checkpoint_v1"
)
_RUN_PREFIX: Final = "protocol_v3_run_sha256"
_FORBIDDEN_RESULT_KEYS: Final = {
    "pnl",
    "profit",
    "net_profit",
    "gross_profit",
    "mtm",
    "equity",
    "trades",
    "trade_results",
    "rankings",
    "outer_rankings",
    "gate_results",
    "quality_gate_result",
    "daily_results",
    "monthly_results",
    "candles",
    "ohlcv",
    "raw_market_data",
}
_SAFETY: Final = {
    "api_keys": "forbidden",
    "canonical_adoption": "locked",
    "final_report_visible": False,
    "live": "locked",
    "orders": "locked",
    "outer_result_values_stored": False,
    "paper": "locked",
    "task31_attestation_available": False,
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class PipelineFinalCheckpointError(PipelineFinalError):
    """Raised when a Task-31 compact checkpoint fails closed."""


@dataclass(frozen=True)
class PipelineFinalCheckpointReceipt:
    canonical_json: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


@dataclass(frozen=True)
class PipelineFinalCheckpoint:
    checkpoint: TransactionCheckpoint
    receipt: PipelineFinalCheckpointReceipt


def build_pipeline_final_checkpoint_receipt(
    progress: PipelineFinalProgress,
    *,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
) -> PipelineFinalCheckpointReceipt:
    registration_payload = validate_pipeline_final_registration(registration).to_dict()
    claim_payload = validate_pipeline_final_claim(claim).to_dict()
    progress_payload = validate_pipeline_final_progress(
        progress,
        registration=registration,
        claim=claim,
    ).to_dict()
    if (
        claim_payload["registration_sha256"] != registration.registration_sha256
        or progress_payload["registration_sha256"] != registration.registration_sha256
        or progress_payload["claim_sha256"] != claim.claim_sha256
    ):
        raise PipelineFinalCheckpointError(
            "pipeline-final checkpoint sources do not share one registration and claim"
        )
    manifest = registration_payload["frozen_identity_manifest"]
    basis = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "contract_version": RECEIPT_CONTRACT_VERSION,
        "registration_id": registration_payload["registration_id"],
        "registration_sha256": registration.registration_sha256,
        "claim_id": claim.claim_id,
        "claim_sha256": claim.claim_sha256,
        "frozen_identity_manifest_sha256": registration_payload[
            "frozen_identity_manifest_sha256"
        ],
        "run_fingerprint": manifest["run_fingerprint"],
        "pipeline_generation_id": progress_payload["pipeline_generation_id"],
        "code_commit": progress_payload["code_commit"],
        "trial_ledger_head_sha256": manifest["trial_ledger_head_sha256"],
        "progress_sha256": progress.progress_sha256,
        "completed_origin_count": progress_payload["completed_origin_count"],
        "next_origin_index": progress_payload["next_origin_index"],
        "origin_chain_head_sha256": progress_payload["origin_chain_head_sha256"],
        "progress_status": progress_payload["status"],
        "checkpoint_role": "RESULT_BLIND_PROGRESS_ONLY",
        "safety": _SAFETY,
    }
    return validate_pipeline_final_checkpoint_receipt(
        {**basis, "receipt_sha256": _digest(basis)}
    )


def validate_pipeline_final_checkpoint_receipt(
    value: PipelineFinalCheckpointReceipt | Mapping[str, Any],
) -> PipelineFinalCheckpointReceipt:
    root = (
        value.to_dict()
        if isinstance(value, PipelineFinalCheckpointReceipt)
        else dict(_mapping(value, "pipeline_final_checkpoint_receipt"))
    )
    required = {
        "schema_version",
        "contract_version",
        "registration_id",
        "registration_sha256",
        "claim_id",
        "claim_sha256",
        "frozen_identity_manifest_sha256",
        "run_fingerprint",
        "pipeline_generation_id",
        "code_commit",
        "trial_ledger_head_sha256",
        "progress_sha256",
        "completed_origin_count",
        "next_origin_index",
        "origin_chain_head_sha256",
        "progress_status",
        "checkpoint_role",
        "safety",
        "receipt_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != RECEIPT_SCHEMA_VERSION
        or root["contract_version"] != RECEIPT_CONTRACT_VERSION
        or root["checkpoint_role"] != "RESULT_BLIND_PROGRESS_ONLY"
    ):
        raise PipelineFinalCheckpointError(
            "pipeline-final checkpoint receipt fields or versions are invalid"
        )
    for name in (
        "registration_sha256",
        "claim_sha256",
        "frozen_identity_manifest_sha256",
        "trial_ledger_head_sha256",
        "progress_sha256",
        "origin_chain_head_sha256",
        "receipt_sha256",
    ):
        _sha(root[name], name)
    if (
        not isinstance(root["run_fingerprint"], str)
        or not root["run_fingerprint"].startswith(f"{_RUN_PREFIX}:")
        or len(root["run_fingerprint"].rsplit(":", 1)[-1]) != 64
    ):
        raise PipelineFinalCheckpointError("checkpoint run fingerprint is invalid")
    _sha(root["run_fingerprint"].rsplit(":", 1)[-1], "run_fingerprint")
    if (
        not isinstance(root["pipeline_generation_id"], str)
        or not root["pipeline_generation_id"].startswith(
            "protocol_v3_pipeline_sha256:"
        )
    ):
        raise PipelineFinalCheckpointError(
            "checkpoint pipeline generation is invalid"
        )
    _sha(
        root["pipeline_generation_id"].rsplit(":", 1)[-1],
        "pipeline_generation_id",
    )
    if (
        not isinstance(root["code_commit"], str)
        or len(root["code_commit"]) != 40
        or any(char not in "0123456789abcdef" for char in root["code_commit"])
    ):
        raise PipelineFinalCheckpointError("checkpoint code identity is invalid")
    count = root["completed_origin_count"]
    if type(count) is not int or not 0 <= count <= 12:
        raise PipelineFinalCheckpointError("checkpoint origin count is invalid")
    expected_next = None if count == 12 else count + 1
    expected_status = (
        "CLAIMED_NOT_STARTED"
        if count == 0
        else (
            "ORIGINS_COMPLETE_RESULTS_HIDDEN"
            if count == 12
            else "RUNNING_RESULTS_HIDDEN"
        )
    )
    expected_head_is_zero = count == 0
    if (
        root["next_origin_index"] != expected_next
        or root["progress_status"] != expected_status
        or (root["origin_chain_head_sha256"] == ZERO_HASH) != expected_head_is_zero
    ):
        raise PipelineFinalCheckpointError(
            "checkpoint progress cursor, status, or chain head is inconsistent"
        )
    if root["safety"] != _SAFETY:
        raise PipelineFinalCheckpointError(
            "pipeline-final checkpoint safety locks are invalid"
        )
    _reject_result_keys(root, "pipeline_final_checkpoint_receipt")
    observed = root["receipt_sha256"]
    basis = dict(root)
    basis.pop("receipt_sha256")
    if observed != _digest(basis):
        raise PipelineFinalCheckpointError(
            "pipeline-final checkpoint receipt digest mismatch"
        )
    return PipelineFinalCheckpointReceipt(_canonical(basis), observed)


def commit_pipeline_final_checkpoint(
    receipt: PipelineFinalCheckpointReceipt,
    *,
    identity: TransactionIdentity,
    pre_run_manifest: PreRunManifest,
    seed_state: Mapping[str, Any],
    budget_usage: BudgetUsage,
    stop_state: Mapping[str, Any],
    repository_root: str | Path,
    trial_ledger_root: str | Path,
    owner_id: str,
) -> PipelineFinalCheckpoint:
    validated = validate_pipeline_final_checkpoint_receipt(receipt)
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
            result_payload={"task31_pipeline_final_checkpoint_receipt": validated.to_dict()},
            repository_root=repository_root,
            trial_ledger_root=trial_ledger_root,
            lock=lock,
        )
    finally:
        release_transaction_lock(lock, repository_root)
    return PipelineFinalCheckpoint(checkpoint, validated)


def read_pipeline_final_checkpoint(
    *,
    current_identity: TransactionIdentity,
    current_pre_run_manifest: PreRunManifest,
    repository_root: str | Path,
) -> PipelineFinalCheckpoint | None:
    checkpoint = resume_last_committed_checkpoint(
        current_identity=current_identity,
        current_pre_run_manifest=current_pre_run_manifest,
        repository_root=repository_root,
    )
    if checkpoint is None:
        return None
    result = dict(_mapping(checkpoint.to_dict()["result"], "checkpoint.result"))
    if result.get("status") != "IN_PROGRESS":
        raise PipelineFinalCheckpointError(
            "Task-31 checkpoint must remain an in-progress result-blind receipt"
        )
    payload = dict(_mapping(result.get("payload"), "checkpoint.result.payload"))
    if set(payload) != {"task31_pipeline_final_checkpoint_receipt"}:
        raise PipelineFinalCheckpointError(
            "Task-31 checkpoint payload contains unexpected state"
        )
    receipt = validate_pipeline_final_checkpoint_receipt(
        payload["task31_pipeline_final_checkpoint_receipt"]
    )
    _assert_receipt_identity(receipt, current_identity, repository_root)
    return PipelineFinalCheckpoint(checkpoint, receipt)


def verify_replayed_pipeline_final_checkpoint(
    receipt: PipelineFinalCheckpointReceipt,
    replayed_progress: PipelineFinalProgress,
    *,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
) -> PipelineFinalProgress:
    expected = validate_pipeline_final_checkpoint_receipt(receipt).to_dict()
    progress = validate_pipeline_final_progress(
        replayed_progress,
        registration=registration,
        claim=claim,
    )
    rebuilt = build_pipeline_final_checkpoint_receipt(
        progress,
        registration=registration,
        claim=claim,
    ).to_dict()
    if rebuilt != expected:
        raise PipelineFinalCheckpointError(
            "replayed pipeline-final progress differs from the committed checkpoint"
        )
    return progress


def _assert_receipt_identity(
    receipt: PipelineFinalCheckpointReceipt,
    identity: TransactionIdentity,
    repository_root: str | Path,
) -> None:
    expected = validate_pipeline_final_checkpoint_receipt(receipt).to_dict()
    tx = validate_transaction_identity(
        identity,
        repository_root=repository_root,
    ).to_dict()
    run = dict(_mapping(tx["run_fingerprint"], "transaction.run_fingerprint"))
    run_key = f"{_RUN_PREFIX}:{run['fingerprint_sha256']}"
    if expected["run_fingerprint"] != run_key:
        raise PipelineFinalCheckpointError(
            "Task-13 transaction uses another run fingerprint"
        )
    if expected["pipeline_generation_id"] != run["pipeline"]["generation_id"]:
        raise PipelineFinalCheckpointError(
            "Task-13 transaction uses another pipeline generation"
        )
    if expected["code_commit"] != run["code"]["git_commit"]:
        raise PipelineFinalCheckpointError(
            "Task-13 transaction uses another code commit"
        )
    if (
        expected["trial_ledger_head_sha256"]
        != run["trial_ledger_head"]["head_sha256"]
    ):
        raise PipelineFinalCheckpointError(
            "Task-13 transaction uses another permanent trial-ledger head"
        )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PipelineFinalCheckpointError(f"{name} must be an object")
    return value


def _sha(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise PipelineFinalCheckpointError(f"{name} must be lowercase sha256")
    return value


def _reject_result_keys(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).lower() in _FORBIDDEN_RESULT_KEYS:
                raise PipelineFinalCheckpointError(
                    f"{path} contains forbidden result key: {key}"
                )
            _reject_result_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_result_keys(child, f"{path}[{index}]")


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
    "PipelineFinalCheckpoint",
    "PipelineFinalCheckpointError",
    "PipelineFinalCheckpointReceipt",
    "build_pipeline_final_checkpoint_receipt",
    "commit_pipeline_final_checkpoint",
    "read_pipeline_final_checkpoint",
    "validate_pipeline_final_checkpoint_receipt",
    "verify_replayed_pipeline_final_checkpoint",
]
