"""Result-blind Task-31 progress receipts for the twelve-origin final process.

The receipt is intentionally not a report and not an execution result.  It stores
only immutable identities and cursors needed to prove ordered completion and to
replay after a restart.  Outer PnL, MTM, equity, trades, rankings and gate results
are forbidden from this object and remain unavailable until the later Task-31
seal/open layer validates the completed process.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Final

from ethusdc_bot.protocol_v3.outer_origins import (
    OuterOriginError,
    OuterOriginSelection,
    validate_outer_origin_selection,
)
from ethusdc_bot.protocol_v3.pipeline_final import (
    PipelineFinalClaim,
    PipelineFinalError,
    PipelineFinalRegistration,
    pipeline_final_boundary_plan,
    validate_pipeline_final_claim,
    validate_pipeline_final_registration,
)

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_pipeline_final_progress_contract.json"
)
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_pipeline_final_progress_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_result_blind_twelve_origin_progress_v1"
PROGRESS_SCHEMA_VERSION: Final = "protocol_v3_pipeline_final_progress_v1"
ORIGIN_RECEIPT_SCHEMA_VERSION: Final = (
    "protocol_v3_pipeline_final_origin_receipt_v1"
)
ZERO_HASH: Final = "0" * 64
_HEX = re.compile(r"^[0-9a-f]{64}$")
_PIPE = re.compile(r"^protocol_v3_pipeline_sha256:[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ORIGIN_IDENTITY_FIELDS: Final = (
    "context_binding_sha256",
    "cost_identity_sha256",
    "data_snapshot_sha256",
    "exchange_info_snapshot_sha256",
    "execution_identity_sha256",
    "feature_store_sha256",
    "origin_artifact_index_sha256",
    "rotation_state_sha256",
    "transaction_checkpoint_sha256",
    "trial_ledger_head_sha256",
)
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
}
_SAFETY: Final = {
    "api_keys": "forbidden",
    "canonical_adoption": "locked",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "progress_schema_version": PROGRESS_SCHEMA_VERSION,
    "origin_receipt_schema_version": ORIGIN_RECEIPT_SCHEMA_VERSION,
    "progress_policy": {
        "exact_origin_count": 12,
        "strict_origin_order": True,
        "hash_chained_origin_receipts": True,
        "registration_and_claim_required": True,
        "task2_boundaries_revalidated": True,
        "pipeline_and_code_identity_revalidated": True,
        "replay_must_match_committed_receipt": True,
        "cross_generation_resume_forbidden": True,
    },
    "hidden_result_policy": {
        "outer_pnl_stored": False,
        "outer_mtm_stored": False,
        "outer_equity_stored": False,
        "outer_trades_stored": False,
        "outer_rankings_stored": False,
        "outer_gate_results_stored": False,
        "intermediate_result_channel_visible": False,
        "final_report_visible_before_task31_attestation": False,
    },
    "required_origin_identity_fields": list(_ORIGIN_IDENTITY_FIELDS),
    "safety": _SAFETY,
}


class PipelineFinalProgressError(PipelineFinalError):
    """Raised when result-blind final-process progress is inconsistent."""


@dataclass(frozen=True)
class PipelineFinalProgress:
    canonical_json: str
    progress_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["progress_sha256"] = self.progress_sha256
        return value


@dataclass(frozen=True)
class PipelineFinalOriginCompletion:
    canonical_json: str
    origin_receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["origin_receipt_sha256"] = self.origin_receipt_sha256
        return value


def load_pipeline_final_progress_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = _strict_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineFinalProgressError(
            "pipeline-final progress contract is missing or invalid"
        ) from exc
    validate_pipeline_final_progress_contract(value)
    return value


def validate_pipeline_final_progress_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize(value) != _CANONICAL_CONTRACT:
        raise PipelineFinalProgressError(
            "pipeline-final progress contract is not canonical"
        )


def start_pipeline_final_progress(
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
) -> PipelineFinalProgress:
    registration_payload, claim_payload = _validated_sources(registration, claim)
    basis = {
        "schema_version": PROGRESS_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "registration_id": registration_payload["registration_id"],
        "registration_sha256": registration.registration_sha256,
        "claim_id": claim.claim_id,
        "claim_sha256": claim.claim_sha256,
        "frozen_identity_manifest_sha256": registration_payload[
            "frozen_identity_manifest_sha256"
        ],
        "pipeline_generation_id": registration_payload[
            "frozen_identity_manifest"
        ]["pipeline_generation_id"],
        "code_commit": registration_payload["frozen_identity_manifest"][
            "code_commit"
        ],
        "expected_origin_count": 12,
        "completed_origins": [],
        "completed_origin_count": 0,
        "next_origin_index": 1,
        "origin_chain_head_sha256": ZERO_HASH,
        "status": "CLAIMED_NOT_STARTED",
        "outer_result_values_stored": False,
        "outer_result_channel_visible": False,
        "final_report_visible": False,
        "task31_attestation_available": False,
        "safety": _SAFETY,
    }
    return validate_pipeline_final_progress(
        {**basis, "progress_sha256": _digest(basis)},
        registration=registration,
        claim=claim,
    )


def append_pipeline_final_origin_completion(
    progress: PipelineFinalProgress,
    origin_selection: OuterOriginSelection,
    *,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
    completion_identities: Mapping[str, Any],
    completed_at_utc: str,
) -> PipelineFinalProgress:
    current = validate_pipeline_final_progress(
        progress,
        registration=registration,
        claim=claim,
    ).to_dict()
    if current["status"] == "ORIGINS_COMPLETE_RESULTS_HIDDEN":
        raise PipelineFinalProgressError(
            "all twelve final origins are already complete"
        )
    expected_index = current["next_origin_index"]
    if type(expected_index) is not int or not 1 <= expected_index <= 12:
        raise PipelineFinalProgressError("next origin cursor is invalid")
    selection_sha = _validate_origin_selection(
        origin_selection,
        registration=registration,
        expected_origin_index=expected_index,
    )
    identities = _origin_identities(completion_identities)
    registration_payload = registration.to_dict()
    expected_boundary = registration_payload["boundary_plan"]["origins"][
        expected_index - 1
    ]
    completed_at = _utc(completed_at_utc, "completed_at_utc")
    test_end = _midnight_day(expected_boundary["test_end_exclusive"])
    if completed_at < test_end:
        raise PipelineFinalProgressError(
            "origin completion cannot predate its closed OOS interval"
        )
    previous_rows = current["completed_origins"]
    if previous_rows:
        previous_completed_at = _utc(
            previous_rows[-1]["completed_at_utc"], "previous.completed_at_utc"
        )
        if completed_at < previous_completed_at:
            raise PipelineFinalProgressError(
                "origin completion timestamps must be monotonic"
            )
    receipt_basis = {
        "schema_version": ORIGIN_RECEIPT_SCHEMA_VERSION,
        "origin_index": expected_index,
        "training_start_inclusive": expected_boundary[
            "training_start_inclusive"
        ],
        "training_end_exclusive": expected_boundary["training_end_exclusive"],
        "test_start_inclusive": expected_boundary["test_start_inclusive"],
        "test_end_exclusive": expected_boundary["test_end_exclusive"],
        "valid_from": expected_boundary["valid_from"],
        "valid_until": expected_boundary["valid_until"],
        "origin_selection_sha256": selection_sha,
        "completion_identities": identities,
        "completed_at_utc": _fmt(completed_at),
        "previous_origin_receipt_sha256": current[
            "origin_chain_head_sha256"
        ],
        "outer_result_values_stored": False,
        "outer_result_channel_visible": False,
        "safety": _SAFETY,
    }
    receipt = validate_pipeline_final_origin_completion(
        {**receipt_basis, "origin_receipt_sha256": _digest(receipt_basis)},
        registration=registration,
        expected_origin_index=expected_index,
    )
    rows = [*previous_rows, receipt.to_dict()]
    count = len(rows)
    next_index = None if count == 12 else count + 1
    status = (
        "ORIGINS_COMPLETE_RESULTS_HIDDEN" if count == 12 else "RUNNING_RESULTS_HIDDEN"
    )
    basis = {
        key: value
        for key, value in current.items()
        if key not in {
            "completed_origins",
            "completed_origin_count",
            "next_origin_index",
            "origin_chain_head_sha256",
            "status",
            "progress_sha256",
        }
    }
    basis.update(
        {
            "completed_origins": rows,
            "completed_origin_count": count,
            "next_origin_index": next_index,
            "origin_chain_head_sha256": receipt.origin_receipt_sha256,
            "status": status,
        }
    )
    return validate_pipeline_final_progress(
        {**basis, "progress_sha256": _digest(basis)},
        registration=registration,
        claim=claim,
    )


def validate_pipeline_final_origin_completion(
    value: PipelineFinalOriginCompletion | Mapping[str, Any],
    *,
    registration: PipelineFinalRegistration,
    expected_origin_index: int,
) -> PipelineFinalOriginCompletion:
    registration_payload = validate_pipeline_final_registration(
        registration
    ).to_dict()
    root = (
        value.to_dict()
        if isinstance(value, PipelineFinalOriginCompletion)
        else dict(_mapping(value, "pipeline_final_origin_completion"))
    )
    required = {
        "schema_version",
        "origin_index",
        "training_start_inclusive",
        "training_end_exclusive",
        "test_start_inclusive",
        "test_end_exclusive",
        "valid_from",
        "valid_until",
        "origin_selection_sha256",
        "completion_identities",
        "completed_at_utc",
        "previous_origin_receipt_sha256",
        "outer_result_values_stored",
        "outer_result_channel_visible",
        "safety",
        "origin_receipt_sha256",
    }
    if set(root) != required or root["schema_version"] != ORIGIN_RECEIPT_SCHEMA_VERSION:
        raise PipelineFinalProgressError(
            "pipeline-final origin receipt fields or version are invalid"
        )
    if root["origin_index"] != expected_origin_index:
        raise PipelineFinalProgressError(
            "pipeline-final origin receipt is out of order"
        )
    expected_boundary = registration_payload["boundary_plan"]["origins"][
        expected_origin_index - 1
    ]
    for key in (
        "training_start_inclusive",
        "training_end_exclusive",
        "test_start_inclusive",
        "test_end_exclusive",
        "valid_from",
        "valid_until",
    ):
        if root[key] != expected_boundary[key]:
            raise PipelineFinalProgressError(
                "pipeline-final origin receipt boundary mismatch"
            )
    _sha(root["origin_selection_sha256"], "origin_selection_sha256")
    identities = _origin_identities(root["completion_identities"])
    if root["completion_identities"] != identities:
        raise PipelineFinalProgressError(
            "pipeline-final origin identities are not canonical"
        )
    completed = _utc(root["completed_at_utc"], "completed_at_utc")
    if completed < _midnight_day(root["test_end_exclusive"]):
        raise PipelineFinalProgressError(
            "origin receipt predates its closed OOS interval"
        )
    _sha(
        root["previous_origin_receipt_sha256"],
        "previous_origin_receipt_sha256",
    )
    if (
        root["outer_result_values_stored"] is not False
        or root["outer_result_channel_visible"] is not False
        or root["safety"] != _SAFETY
    ):
        raise PipelineFinalProgressError(
            "pipeline-final origin receipt exposes results or weakens safety"
        )
    _reject_result_keys(root, "origin_receipt")
    observed = _sha(root["origin_receipt_sha256"], "origin_receipt_sha256")
    basis = dict(root)
    basis.pop("origin_receipt_sha256")
    if observed != _digest(basis):
        raise PipelineFinalProgressError(
            "pipeline-final origin receipt digest mismatch"
        )
    return PipelineFinalOriginCompletion(_canonical(basis), observed)


def validate_pipeline_final_progress(
    value: PipelineFinalProgress | Mapping[str, Any],
    *,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
) -> PipelineFinalProgress:
    registration_payload, claim_payload = _validated_sources(registration, claim)
    root = (
        value.to_dict()
        if isinstance(value, PipelineFinalProgress)
        else dict(_mapping(value, "pipeline_final_progress"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "registration_id",
        "registration_sha256",
        "claim_id",
        "claim_sha256",
        "frozen_identity_manifest_sha256",
        "pipeline_generation_id",
        "code_commit",
        "expected_origin_count",
        "completed_origins",
        "completed_origin_count",
        "next_origin_index",
        "origin_chain_head_sha256",
        "status",
        "outer_result_values_stored",
        "outer_result_channel_visible",
        "final_report_visible",
        "task31_attestation_available",
        "safety",
        "progress_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != PROGRESS_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
    ):
        raise PipelineFinalProgressError(
            "pipeline-final progress fields or versions are invalid"
        )
    expected_source = {
        "registration_id": registration_payload["registration_id"],
        "registration_sha256": registration.registration_sha256,
        "claim_id": claim.claim_id,
        "claim_sha256": claim.claim_sha256,
        "frozen_identity_manifest_sha256": registration_payload[
            "frozen_identity_manifest_sha256"
        ],
        "pipeline_generation_id": registration_payload[
            "frozen_identity_manifest"
        ]["pipeline_generation_id"],
        "code_commit": registration_payload["frozen_identity_manifest"][
            "code_commit"
        ],
    }
    if any(root[key] != expected for key, expected in expected_source.items()):
        raise PipelineFinalProgressError(
            "pipeline-final progress belongs to another registration, claim, or generation"
        )
    if not _PIPE.fullmatch(root["pipeline_generation_id"]):
        raise PipelineFinalProgressError("pipeline generation identity is invalid")
    if not _COMMIT.fullmatch(root["code_commit"]):
        raise PipelineFinalProgressError("pipeline code identity is invalid")
    if root["expected_origin_count"] != 12 or type(root["expected_origin_count"]) is not int:
        raise PipelineFinalProgressError(
            "pipeline-final progress must expect exactly twelve origins"
        )
    rows = root["completed_origins"]
    if not isinstance(rows, list) or len(rows) > 12:
        raise PipelineFinalProgressError(
            "pipeline-final completed origins are invalid"
        )
    normalized: list[dict[str, Any]] = []
    previous = ZERO_HASH
    previous_time: datetime | None = None
    for index, raw in enumerate(rows, start=1):
        receipt = validate_pipeline_final_origin_completion(
            raw,
            registration=registration,
            expected_origin_index=index,
        )
        payload = receipt.to_dict()
        if payload["previous_origin_receipt_sha256"] != previous:
            raise PipelineFinalProgressError(
                "pipeline-final origin receipt chain is broken"
            )
        completed = _utc(payload["completed_at_utc"], "completed_at_utc")
        if previous_time is not None and completed < previous_time:
            raise PipelineFinalProgressError(
                "pipeline-final origin completion timestamps are reordered"
            )
        normalized.append(payload)
        previous = receipt.origin_receipt_sha256
        previous_time = completed
    count = len(normalized)
    if root["completed_origins"] != normalized or root["completed_origin_count"] != count:
        raise PipelineFinalProgressError(
            "pipeline-final origin count or canonical receipts mismatch"
        )
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
    if (
        root["next_origin_index"] != expected_next
        or root["origin_chain_head_sha256"] != previous
        or root["status"] != expected_status
    ):
        raise PipelineFinalProgressError(
            "pipeline-final progress cursor, chain head, or status is inconsistent"
        )
    if (
        root["outer_result_values_stored"] is not False
        or root["outer_result_channel_visible"] is not False
        or root["final_report_visible"] is not False
        or root["task31_attestation_available"] is not False
        or root["safety"] != _SAFETY
    ):
        raise PipelineFinalProgressError(
            "pipeline-final progress exposes results or weakens safety"
        )
    _reject_result_keys(root, "pipeline_final_progress")
    observed = _sha(root["progress_sha256"], "progress_sha256")
    basis = dict(root)
    basis.pop("progress_sha256")
    if observed != _digest(basis):
        raise PipelineFinalProgressError(
            "pipeline-final progress digest mismatch"
        )
    return PipelineFinalProgress(_canonical(basis), observed)


def verify_replayed_pipeline_final_progress(
    progress: PipelineFinalProgress,
    replayed_origin_selections: Sequence[OuterOriginSelection],
    *,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
) -> PipelineFinalProgress:
    validated = validate_pipeline_final_progress(
        progress,
        registration=registration,
        claim=claim,
    )
    payload = validated.to_dict()
    if (
        isinstance(replayed_origin_selections, (str, bytes))
        or not isinstance(replayed_origin_selections, Sequence)
        or len(replayed_origin_selections) != payload["completed_origin_count"]
    ):
        raise PipelineFinalProgressError(
            "replayed origin selection count differs from committed progress"
        )
    for index, (selection, receipt) in enumerate(
        zip(replayed_origin_selections, payload["completed_origins"], strict=True),
        start=1,
    ):
        observed_sha = _validate_origin_selection(
            selection,
            registration=registration,
            expected_origin_index=index,
        )
        if observed_sha != receipt["origin_selection_sha256"]:
            raise PipelineFinalProgressError(
                "replayed origin selection differs from committed progress"
            )
    return validated


def _validated_sources(
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(registration, PipelineFinalRegistration):
        raise PipelineFinalProgressError(
            "validated PipelineFinalRegistration required"
        )
    if not isinstance(claim, PipelineFinalClaim):
        raise PipelineFinalProgressError("validated PipelineFinalClaim required")
    registration_payload = validate_pipeline_final_registration(
        registration
    ).to_dict()
    claim_payload = validate_pipeline_final_claim(claim).to_dict()
    if (
        claim_payload["registration_id"] != registration_payload["registration_id"]
        or claim_payload["registration_sha256"]
        != registration.registration_sha256
        or claim_payload["result_opened"] is not False
    ):
        raise PipelineFinalProgressError(
            "pipeline-final claim does not belong to the registration"
        )
    return registration_payload, claim_payload


def _validate_origin_selection(
    selection: OuterOriginSelection,
    *,
    registration: PipelineFinalRegistration,
    expected_origin_index: int,
) -> str:
    if not isinstance(selection, OuterOriginSelection):
        raise PipelineFinalProgressError(
            "typed OuterOriginSelection required"
        )
    registration_payload = registration.to_dict()
    plan = pipeline_final_boundary_plan(
        start_inclusive_utc=registration_payload["start_inclusive_utc"],
        end_exclusive_utc=registration_payload["end_exclusive_utc"],
    )
    if type(expected_origin_index) is not int or not 1 <= expected_origin_index <= 12:
        raise PipelineFinalProgressError("expected origin index is invalid")
    try:
        validated = validate_outer_origin_selection(
            selection,
            origin=plan.origins[expected_origin_index - 1],
        )
    except OuterOriginError as exc:
        raise PipelineFinalProgressError(
            "outer origin selection failed the full Task-23 validation"
        ) from exc
    root = validated.to_dict()
    manifest = registration_payload["frozen_identity_manifest"]
    if (
        root["pipeline_generation_id"] != manifest["pipeline_generation_id"]
        or root["code_commit"] != manifest["code_commit"]
        or root["outer_results_visible_during_fit"] is not False
    ):
        raise PipelineFinalProgressError(
            "outer origin selection changed pipeline, code, or visibility"
        )
    if selection.origin_sha256 != validated.origin_sha256:
        raise PipelineFinalProgressError(
            "outer origin selection typed digest mismatch"
        )
    return validated.origin_sha256

def _origin_identities(value: Mapping[str, Any]) -> dict[str, str]:
    root = dict(_mapping(value, "completion_identities"))
    if set(root) != set(_ORIGIN_IDENTITY_FIELDS):
        raise PipelineFinalProgressError(
            "origin completion identities are incomplete or unexpected"
        )
    normalized: dict[str, str] = {}
    for key in _ORIGIN_IDENTITY_FIELDS:
        normalized[key] = _sha(root[key], key)
    return normalized


def _reject_result_keys(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in _FORBIDDEN_RESULT_KEYS:
                raise PipelineFinalProgressError(
                    f"{path} contains forbidden outer result field: {key}"
                )
            _reject_result_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_result_keys(item, f"{path}[{index}]")


def _midnight_day(value: Any) -> datetime:
    if not isinstance(value, str):
        raise PipelineFinalProgressError("boundary day must be text")
    try:
        parsed = datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError as exc:
        raise PipelineFinalProgressError("boundary day is invalid") from exc
    if parsed.date().isoformat() != value:
        raise PipelineFinalProgressError("boundary day is not canonical")
    return parsed


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PipelineFinalProgressError(f"{name} must be an object")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise PipelineFinalProgressError(f"{name} must be lowercase sha256")
    return value


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PipelineFinalProgressError(f"{name} must be canonical UTC text")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PipelineFinalProgressError(f"{name} is invalid") from exc
    if parsed.utcoffset() != timedelta(0) or _fmt(parsed) != value:
        raise PipelineFinalProgressError(f"{name} is not canonical UTC")
    return parsed.astimezone(UTC)


def _fmt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _strict_load(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise PipelineFinalProgressError(
                    f"duplicate pipeline-final progress JSON key: {key}"
                )
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise PipelineFinalProgressError(
            f"non-finite pipeline-final progress JSON constant: {value}"
        )

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _normalize(value: Any) -> Any:
    return json.loads(_canonical(value))


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_VERSION",
    "ORIGIN_RECEIPT_SCHEMA_VERSION",
    "PROGRESS_SCHEMA_VERSION",
    "PipelineFinalOriginCompletion",
    "PipelineFinalProgress",
    "PipelineFinalProgressError",
    "ZERO_HASH",
    "append_pipeline_final_origin_completion",
    "load_pipeline_final_progress_contract",
    "start_pipeline_final_progress",
    "validate_pipeline_final_origin_completion",
    "validate_pipeline_final_progress",
    "validate_pipeline_final_progress_contract",
    "verify_replayed_pipeline_final_progress",
]
