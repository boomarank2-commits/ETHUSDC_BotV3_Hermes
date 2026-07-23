"""Compact, replayable batch DSR evidence for one matrix cycle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from . import dsr as scalar_dsr
from .legacy_multiplicity import (
    LegacyMultiplicityError,
    load_legacy_multiplicity_policy,
)
from .pbo import (
    COMPLETE as PBO_COMPLETE,
    PBOEvidence,
    validate_pbo_evidence,
    validate_pbo_identity_payload,
)
from .trial_ledger import TrialLedgerSnapshot, read_trial_ledger

PROTOCOL_VERSION: Final = "3.0.0"
EVIDENCE_SCHEMA_VERSION: Final = "protocol_v3_dsr_batch_evidence_v1"
IDENTITY_SCHEMA_VERSION: Final = "protocol_v3_dsr_batch_identity_v1"
CONTRACT_VERSION: Final = "protocol_v3_shared_statistics_batch_dsr_v1"
COMPLETE: Final = scalar_dsr.COMPLETE
INSUFFICIENT_EVIDENCE: Final = scalar_dsr.INSUFFICIENT_EVIDENCE
INSUFFICIENT_TRIAL_HISTORY: Final = scalar_dsr.INSUFFICIENT_TRIAL_HISTORY
_SHARED_RESULT_KEYS: Final = {
    "n_raw",
    "complete_native_trial_count",
    "same_grid_native_trial_count",
    "trial_rows",
    "trial_set_sha256",
    "sigma_sr",
    "correlation_matrix",
    "correlation_sha256",
    "n_eff_trials",
    "sr0",
}
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class DSRBatchError(ValueError):
    """Raised when shared DSR evidence is incomplete or contradictory."""


@dataclass(frozen=True)
class DSRBatchEvidence:
    canonical_json: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["evidence_sha256"] = self.evidence_sha256
        return payload

    @property
    def identity_payload(self) -> dict[str, Any]:
        basis = {
            "identity_schema_version": IDENTITY_SCHEMA_VERSION,
            "evidence": self.to_dict(),
            "evidence_sha256": self.evidence_sha256,
        }
        return {**basis, "identity_sha256": _digest(basis)}


def calculate_dsr_batch_evidence(
    *,
    pbo_evidence: PBOEvidence | Mapping[str, Any],
    cycle_index: int,
    trial_ledger: TrialLedgerSnapshot,
) -> DSRBatchEvidence:
    pbo = validate_pbo_evidence(pbo_evidence)
    ledger = _current_ledger(trial_ledger)
    basis = _batch_basis(pbo, cycle_index, ledger)
    return validate_dsr_batch_evidence(
        {**basis, "evidence_sha256": _digest(basis)}
    )


def validate_dsr_batch_evidence(
    value: DSRBatchEvidence | Mapping[str, Any],
) -> DSRBatchEvidence:
    root = (
        value.to_dict()
        if isinstance(value, DSRBatchEvidence)
        else dict(_mapping(value, "dsr_batch_evidence"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "pbo_identity",
        "cycle_index",
        "matrix_sha256",
        "ledger_head_sha256",
        "legacy_multiplicity_policy",
        "shared_statistics",
        "profiles",
        "safety",
        "evidence_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != EVIDENCE_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
        or root["safety"] != _SAFETY
    ):
        raise DSRBatchError("DSR batch fields are missing or invalid")
    pbo_identity = validate_pbo_identity_payload(root["pbo_identity"])
    pbo = validate_pbo_evidence(pbo_identity["evidence"])
    pbo_payload = pbo.to_dict()
    matrix = pbo_payload["matrix_identity"]["matrix"]
    cycle = _positive(root["cycle_index"], "cycle_index")
    rows = [row for row in matrix["cycles"] if row["cycle_index"] == cycle]
    if (
        len(rows) != 1
        or root["matrix_sha256"] != matrix["matrix_sha256"]
        or root["ledger_head_sha256"]
        != matrix["trial_ledger_head_sha256"]
    ):
        raise DSRBatchError("DSR batch matrix binding is invalid")
    profiles = root["profiles"]
    if (
        not isinstance(profiles, list)
        or [row.get("profile_id") for row in profiles]
        != [row["profile_id"] for row in rows[0]["profiles"]]
        or [row.get("candidate_id") for row in profiles]
        != [row["candidate_id"] for row in rows[0]["profiles"]]
    ):
        raise DSRBatchError("DSR batch profile inventory is invalid")
    policy = load_legacy_multiplicity_policy(
        Path(__file__).resolve().parents[3]
    )
    if root["legacy_multiplicity_policy"] != policy.to_dict():
        raise DSRBatchError("DSR batch multiplicity policy is invalid")
    shared = dict(_mapping(root["shared_statistics"], "shared_statistics"))
    if shared.get("state") == COMPLETE:
        trial_rows = shared.get("trial_rows")
        if not isinstance(trial_rows, list):
            raise DSRBatchError("DSR batch trial rows are invalid")
        recomputed = scalar_dsr._shared_statistics(
            trial_rows,
            legacy_multiplicity_policy=policy.to_dict(),
            n_raw=shared.get("n_raw"),
            complete_native_trial_count=shared.get(
                "complete_native_trial_count"
            ),
        )
        expected_shared = {
            "state": COMPLETE,
            "reason": "complete_shared_trial_statistics",
            "n_raw": shared["n_raw"],
            "complete_native_trial_count": shared[
                "complete_native_trial_count"
            ],
            "trial_rows": trial_rows,
            **recomputed,
        }
        if shared != expected_shared:
            raise DSRBatchError("DSR batch shared statistics differ")
        for source, matrix_profile in zip(
            profiles,
            rows[0]["profiles"],
            strict=True,
        ):
            values = [
                float(row["net_usdc"])
                for row in matrix_profile["daily_net_mtm_usdc"]
            ]
            try:
                full = scalar_dsr._statistics(
                    values,
                    trial_rows,
                    legacy_multiplicity_policy=policy.to_dict(),
                    n_raw=shared["n_raw"],
                    complete_native_trial_count=shared[
                        "complete_native_trial_count"
                    ],
                    shared_statistics=recomputed,
                )
                expected_result = _compact_result(
                    {
                        "state": COMPLETE,
                        "reason": "complete_deflated_sharpe",
                        **full,
                    }
                )
            except scalar_dsr._InsufficientStatistics as exc:
                expected_result = _compact_result(
                    scalar_dsr._empty_result(
                        INSUFFICIENT_EVIDENCE,
                        str(exc),
                    )
                )
            if source.get("result") != expected_result:
                raise DSRBatchError("DSR batch profile statistics differ")
    elif shared.get("state") in {
        INSUFFICIENT_EVIDENCE,
        INSUFFICIENT_TRIAL_HISTORY,
    }:
        if any(
            row.get("result", {}).get("state") == COMPLETE
            for row in profiles
        ):
            raise DSRBatchError(
                "incomplete shared DSR cannot contain a complete profile"
            )
    else:
        raise DSRBatchError("DSR batch shared state is invalid")
    for row in profiles:
        basis = {
            "profile_id": row["profile_id"],
            "candidate_id": row["candidate_id"],
            "result": row["result"],
            "shared_statistics_sha256": _digest(shared),
            "pbo_evidence_sha256": pbo.evidence_sha256,
        }
        if row.get("profile_evidence_sha256") != _digest(basis):
            raise DSRBatchError("DSR batch profile digest mismatch")
    observed = root.pop("evidence_sha256")
    if observed != _digest(root):
        raise DSRBatchError("DSR batch evidence digest mismatch")
    return DSRBatchEvidence(_canonical(root), observed)


def validate_dsr_batch_for_ledger(
    value: DSRBatchEvidence | Mapping[str, Any],
    trial_ledger: TrialLedgerSnapshot,
) -> DSRBatchEvidence:
    validated = validate_dsr_batch_evidence(value)
    current = _current_ledger(trial_ledger)
    payload = validated.to_dict()
    pbo = validate_pbo_evidence(payload["pbo_identity"]["evidence"])
    expected = _batch_basis(pbo, payload["cycle_index"], current)
    observed = dict(payload)
    observed.pop("evidence_sha256")
    if observed != expected:
        raise DSRBatchError(
            "DSR batch differs from current permanent ledger replay"
        )
    return validated


def validate_dsr_batch_identity_payload(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    root = dict(_mapping(value, "dsr_batch_identity"))
    if set(root) != {
        "identity_schema_version",
        "evidence",
        "evidence_sha256",
        "identity_sha256",
    }:
        raise DSRBatchError("DSR batch identity fields are invalid")
    evidence = validate_dsr_batch_evidence(root["evidence"])
    basis = {
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "evidence": evidence.to_dict(),
        "evidence_sha256": evidence.evidence_sha256,
    }
    if (
        root["identity_schema_version"] != IDENTITY_SCHEMA_VERSION
        or root["evidence_sha256"] != evidence.evidence_sha256
        or root["identity_sha256"] != _digest(basis)
    ):
        raise DSRBatchError("DSR batch identity digest mismatch")
    return {**basis, "identity_sha256": root["identity_sha256"]}


def _batch_basis(
    pbo: PBOEvidence,
    cycle_index: int,
    ledger: TrialLedgerSnapshot,
) -> dict[str, Any]:
    pbo_payload = pbo.to_dict()
    matrix = pbo_payload["matrix_identity"]["matrix"]
    cycle = _positive(cycle_index, "cycle_index")
    rows = [row for row in matrix["cycles"] if row["cycle_index"] == cycle]
    if len(rows) != 1:
        raise DSRBatchError("PBO matrix lacks the requested DSR cycle")
    if matrix["trial_ledger_head_sha256"] != ledger.status.head_sha256:
        raise DSRBatchError("DSR batch ledger differs from matrix")
    policy = load_legacy_multiplicity_policy(
        Path(__file__).resolve().parents[3]
    )
    prepared = None
    shared: dict[str, Any]
    if pbo_payload["state"] != PBO_COMPLETE:
        shared = {
            "state": INSUFFICIENT_EVIDENCE,
            "reason": "PBO_evidence_is_incomplete",
        }
    else:
        try:
            prepared = scalar_dsr._prepare_dsr_inputs(pbo, ledger)
            _, trial_rows, count, n_raw, statistics = prepared
            shared = {
                "state": COMPLETE,
                "reason": "complete_shared_trial_statistics",
                "n_raw": n_raw,
                "complete_native_trial_count": count,
                "trial_rows": trial_rows,
                **statistics,
            }
        except LegacyMultiplicityError:
            shared = {
                "state": INSUFFICIENT_TRIAL_HISTORY,
                "reason": (
                    "legacy_multiplicity_floor_or_native_history_is_incomplete"
                ),
            }
        except scalar_dsr._InsufficientStatistics as exc:
            shared = {
                "state": INSUFFICIENT_EVIDENCE,
                "reason": str(exc),
            }
    profiles = []
    for profile in rows[0]["profiles"]:
        if prepared is None:
            result = _compact_result(
                scalar_dsr._empty_result(
                    shared["state"],
                    shared["reason"],
                )
            )
        else:
            _, trial_rows, count, n_raw, statistics = prepared
            values = [
                float(row["net_usdc"])
                for row in profile["daily_net_mtm_usdc"]
            ]
            try:
                full = scalar_dsr._statistics(
                    values,
                    trial_rows,
                    legacy_multiplicity_policy=policy.to_dict(),
                    n_raw=n_raw,
                    complete_native_trial_count=count,
                    shared_statistics=statistics,
                )
                result = _compact_result(
                    {
                        "state": COMPLETE,
                        "reason": "complete_deflated_sharpe",
                        **full,
                    }
                )
            except scalar_dsr._InsufficientStatistics as exc:
                result = _compact_result(
                    scalar_dsr._empty_result(
                        INSUFFICIENT_EVIDENCE,
                        str(exc),
                    )
                )
        profile_basis = {
            "profile_id": profile["profile_id"],
            "candidate_id": profile["candidate_id"],
            "result": result,
            "shared_statistics_sha256": _digest(shared),
            "pbo_evidence_sha256": pbo.evidence_sha256,
        }
        profiles.append(
            {
                "profile_id": profile["profile_id"],
                "candidate_id": profile["candidate_id"],
                "result": result,
                "profile_evidence_sha256": _digest(profile_basis),
            }
        )
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "pbo_identity": pbo.identity_payload,
        "cycle_index": cycle,
        "matrix_sha256": matrix["matrix_sha256"],
        "ledger_head_sha256": ledger.status.head_sha256,
        "legacy_multiplicity_policy": policy.to_dict(),
        "shared_statistics": shared,
        "profiles": profiles,
        "safety": dict(_SAFETY),
    }


def _compact_result(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if key not in _SHARED_RESULT_KEYS
    }


def _current_ledger(value: TrialLedgerSnapshot) -> TrialLedgerSnapshot:
    if not isinstance(value, TrialLedgerSnapshot):
        raise DSRBatchError("trial_ledger must be a verified snapshot")
    current = read_trial_ledger(value.root)
    if current.status.head_sha256 != value.status.head_sha256:
        raise DSRBatchError("DSR batch trial ledger is stale")
    return current


def _positive(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DSRBatchError(f"{path} must be a positive integer")
    return value


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DSRBatchError(f"{path} must be an object")
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
    "COMPLETE",
    "CONTRACT_VERSION",
    "DSRBatchError",
    "DSRBatchEvidence",
    "EVIDENCE_SCHEMA_VERSION",
    "IDENTITY_SCHEMA_VERSION",
    "INSUFFICIENT_EVIDENCE",
    "INSUFFICIENT_TRIAL_HISTORY",
    "calculate_dsr_batch_evidence",
    "validate_dsr_batch_evidence",
    "validate_dsr_batch_for_ledger",
    "validate_dsr_batch_identity_payload",
]
