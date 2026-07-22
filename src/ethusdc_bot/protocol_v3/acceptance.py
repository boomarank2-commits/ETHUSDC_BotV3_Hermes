"""Fixture-isolated Protocol-v3 Task-32 acceptance evidence.

This module does not run a second research pipeline.  It revalidates the
existing Task-23..31 objects, captures their semantic identities for the four
required execution modes, and refuses to accept fixture artifacts written
inside the canonical repository.  The resulting receipt is diagnostic test
evidence only and can never become final or adoption evidence.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Final

from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.protocol_v3.boundaries import MonthlyProcessBoundaryPlan
from ethusdc_bot.protocol_v3.hindsight_binding import BoundHindsightBenchmarks
from ethusdc_bot.protocol_v3.monthly_quality_gate import MonthlyQualityGateReport
from ethusdc_bot.protocol_v3.outer_mtm_ledger import OuterMtmLedger
from ethusdc_bot.protocol_v3.outer_origins import OuterOriginProcess
from ethusdc_bot.protocol_v3.pipeline_final import (
    PipelineFinalClaim,
    PipelineFinalRegistration,
    pipeline_final_boundary_plan_sha256,
    validate_pipeline_final_claim,
    validate_pipeline_final_registration,
)
from ethusdc_bot.protocol_v3.pipeline_final_attestation import (
    PipelineFinalAttestation,
    validate_pipeline_final_attestation,
)
from ethusdc_bot.protocol_v3.pipeline_final_checkpoint import (
    PipelineFinalCheckpoint,
    validate_pipeline_final_checkpoint_receipt,
    verify_replayed_pipeline_final_checkpoint,
)
from ethusdc_bot.protocol_v3.pipeline_final_progress import (
    PipelineFinalProgress,
    validate_pipeline_final_progress,
)
from ethusdc_bot.protocol_v3.pipeline_final_report import (
    PipelineFinalOpenReceipt,
    read_pipeline_final_open_receipt,
    read_pipeline_final_report,
    validate_pipeline_final_open_receipt,
    validate_pipeline_final_report,
)
from ethusdc_bot.protocol_v3.reporting import ProtocolV3Report

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_acceptance_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_acceptance_contract_v1"
CONTRACT_VERSION: Final = (
    "protocol_v3_fixture_isolated_e2e_parity_and_fault_acceptance_v1"
)
SNAPSHOT_SCHEMA_VERSION: Final = "protocol_v3_acceptance_path_snapshot_v1"
RECEIPT_SCHEMA_VERSION: Final = "protocol_v3_task32_acceptance_receipt_v1"
EXECUTION_MODES: Final = (
    "FIRST_RUN",
    "TASK13_RESUME",
    "CACHE_REUSE",
    "DETERMINISTIC_REPLAY",
)
_PARITY_IDENTITIES: Final = (
    "attestation_sha256", "baseline_ledger_sha256", "bootstrap_contract_sha256",
    "boundary_plan_sha256", "claim_sha256", "code_commit",
    "context_contract_sha256", "cost_contract_sha256", "data_contract_sha256",
    "exchange_info_contract_sha256", "execution_contract_sha256",
    "feature_contract_sha256", "final_report_sha256", "hindsight_binding_sha256",
    "monthly_quality_report_sha256", "open_receipt_sha256", "outer_process_sha256",
    "pipeline_contract_sha256", "pipeline_generation_id", "progress_sha256",
    "quality_gate_contract_sha256", "registration_sha256", "report_contract_sha256",
    "run_fingerprint", "search_budget_sha256", "seed_policy_sha256",
    "simulator_contract_sha256", "stop_policy_sha256", "trial_ledger_head_sha256",
    "ui_state_sha256",
)
_FAULT_MATRIX: Final = {
    "atomic_checkpoint_and_head": [
        "before_checkpoint_temp", "after_checkpoint_temp_fsync",
        "after_checkpoint_temp_validate", "after_checkpoint_replace",
        "after_checkpoint_reload", "before_head_replace", "after_head_replace",
    ],
    "final_report_open": [
        "crash_after_report_before_receipt", "orphan_receipt", "second_open",
    ],
    "identity_mutation": [
        "pipeline_generation", "code", "snapshot", "feature", "context",
        "exchange", "execution", "cost", "gate", "bootstrap", "seed",
        "trial_ledger", "boundary",
    ],
    "origin_topology": [
        "missing_origin", "duplicate_origin", "reordered_origin", "wrong_origin",
    ],
    "data_context_and_warmup": [
        "data_gap", "context_gap", "stale_watermark", "future_watermark",
        "misaligned_watermark", "incomplete_warmup",
    ],
    "resume_cache_sources": [
        "registration", "claim", "progress", "checkpoint", "final_attestation",
    ],
    "result_claim_mutation": [
        "pnl", "ranking", "freshness", "bootstrap_support", "final_status",
        "adoption", "safety",
    ],
    "path_and_encoding": [
        "symlink", "root_escape", "duplicate_json_key", "nan", "infinity",
        "noncanonical_bytes", "foreign_temp_path",
    ],
    "create_only_races": [
        "parallel_claim", "parallel_checkpoint", "parallel_attestation", "parallel_open",
    ],
}
_HEX = re.compile(r"^[0-9a-f]{64}$")
_SAFETY: Final = {
    "api_keys": "forbidden",
    "canonical_adoption": "locked",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class ProtocolV3AcceptanceError(ValueError):
    """Raised when Task-32 acceptance evidence is incomplete or unsafe."""


@dataclass(frozen=True)
class AcceptancePathSnapshot:
    canonical_json: str
    snapshot_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


@dataclass(frozen=True)
class Task32AcceptanceReceipt:
    canonical_json: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def load_acceptance_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root) / CONTRACT_PATH
    try:
        raw = path.read_bytes()
        value = _strict_json(raw.decode("utf-8"), "acceptance contract")
    except (OSError, UnicodeError) as exc:
        raise ProtocolV3AcceptanceError("acceptance contract is unreadable") from exc
    if not isinstance(value, dict):
        raise ProtocolV3AcceptanceError("acceptance contract must be an object")
    validate_acceptance_contract(value)
    return value


def validate_acceptance_contract(value: Mapping[str, Any]) -> None:
    root = dict(_mapping(value, "acceptance contract"))
    if root != _canonical_contract():
        raise ProtocolV3AcceptanceError("Protocol-v3 acceptance contract is not canonical")


def capture_acceptance_path_snapshot(
    *,
    mode: str,
    fixture_repository_root: str | Path,
    source_repository_root: str | Path,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
    progress: PipelineFinalProgress,
    checkpoint: PipelineFinalCheckpoint,
    boundary_plan: MonthlyProcessBoundaryPlan,
    outer_process: OuterOriginProcess,
    baseline_ledger: OuterMtmLedger,
    joint_stress_ledger: OuterMtmLedger,
    slippage_stress_ledger: OuterMtmLedger,
    monthly_quality_report: MonthlyQualityGateReport,
    stress_identity_evidence: Mapping[str, Any],
    regime_evidence: Mapping[str, Any],
    integrity_evidence: Mapping[str, Any],
    bound_hindsight_benchmarks: BoundHindsightBenchmarks,
    attestation: PipelineFinalAttestation,
    final_report: ProtocolV3Report,
    open_receipt: PipelineFinalOpenReceipt,
    final_report_path: str | Path,
    open_receipt_path: str | Path,
    ui_state: Mapping[str, Any],
) -> AcceptancePathSnapshot:
    contract = load_acceptance_contract(source_repository_root)
    if mode not in EXECUTION_MODES:
        raise ProtocolV3AcceptanceError("acceptance execution mode is invalid")
    fixture_root = _real_directory(fixture_repository_root, "fixture_repository_root")
    source_root = _real_directory(source_repository_root, "source_repository_root")
    if fixture_root == source_root or is_path_within(fixture_root, source_root):
        raise ProtocolV3AcceptanceError(
            "Task-32 fixture root must remain outside the canonical repository"
        )
    report_path = _fixture_file(final_report_path, fixture_root, source_root)
    receipt_path = _fixture_file(open_receipt_path, fixture_root, source_root)

    registered = validate_pipeline_final_registration(registration)
    claimed = validate_pipeline_final_claim(claim)
    progressed = validate_pipeline_final_progress(
        progress, registration=registered, claim=claimed
    )
    checkpoint_receipt = validate_pipeline_final_checkpoint_receipt(
        checkpoint.receipt
    )
    verify_replayed_pipeline_final_checkpoint(
        checkpoint_receipt,
        progressed,
        registration=registered,
        claim=claimed,
    )
    attested = validate_pipeline_final_attestation(
        attestation.to_dict(),
        registration=registered,
        claim=claimed,
        progress=progressed,
        checkpoint=checkpoint,
        boundary_plan=boundary_plan,
        outer_process=outer_process,
        baseline_ledger=baseline_ledger,
        joint_stress_ledger=joint_stress_ledger,
        slippage_stress_ledger=slippage_stress_ledger,
        monthly_quality_report=monthly_quality_report,
        stress_identity_evidence=stress_identity_evidence,
        regime_evidence=regime_evidence,
        integrity_evidence=integrity_evidence,
        bound_hindsight_benchmarks=bound_hindsight_benchmarks,
        source_repository_root=source_root,
    )
    report = validate_pipeline_final_report(
        final_report,
        attestation=attested,
        registration=registered,
    )
    receipt = validate_pipeline_final_open_receipt(
        open_receipt,
        attestation=attested,
        registration=registered,
        report=report,
    )
    if read_pipeline_final_report(
        report_path,
        fixture_root,
        attestation=attested,
        registration=registered,
    ) != report:
        raise ProtocolV3AcceptanceError("fixture final report reload differs")
    if read_pipeline_final_open_receipt(
        receipt_path,
        fixture_root,
        attestation=attested,
        registration=registered,
        report=report,
    ) != receipt:
        raise ProtocolV3AcceptanceError("fixture open receipt reload differs")

    registration_payload = registered.to_dict()
    manifest = dict(registration_payload["frozen_identity_manifest"])
    progress_payload = progressed.to_dict()
    checkpoint_payload = checkpoint.checkpoint.to_dict()
    report_payload = report.to_dict()
    if (
        progress_payload["completed_origin_count"] != 12
        or len(outer_process.to_dict()["process_oos_day_grid"]) != 365
        or report_payload["safety"]["orders_enabled"] is not False
        or report_payload["safety"]["canonical_adoption_enabled"] is not False
    ):
        raise ProtocolV3AcceptanceError("fixture path violates Task-32 scope")
    ui = _finite_mapping(ui_state, "ui_state")
    parity = {
        "attestation_sha256": attested.attestation_sha256,
        "baseline_ledger_sha256": baseline_ledger.ledger_sha256,
        "bootstrap_contract_sha256": manifest["bootstrap_contract_sha256"],
        "boundary_plan_sha256": pipeline_final_boundary_plan_sha256(boundary_plan),
        "claim_sha256": claimed.claim_sha256,
        "code_commit": manifest["code_commit"],
        "context_contract_sha256": manifest["context_contract_sha256"],
        "cost_contract_sha256": manifest["cost_contract_sha256"],
        "data_contract_sha256": manifest["data_contract_sha256"],
        "exchange_info_contract_sha256": manifest["exchange_info_contract_sha256"],
        "execution_contract_sha256": manifest["execution_contract_sha256"],
        "feature_contract_sha256": manifest["feature_contract_sha256"],
        "final_report_sha256": report.report_sha256,
        "hindsight_binding_sha256": bound_hindsight_benchmarks.binding_sha256,
        "monthly_quality_report_sha256": monthly_quality_report.report_sha256,
        "open_receipt_sha256": receipt.receipt_sha256,
        "outer_process_sha256": outer_process.process_sha256,
        "pipeline_contract_sha256": manifest["pipeline_contract_sha256"],
        "pipeline_generation_id": manifest["pipeline_generation_id"],
        "progress_sha256": progressed.progress_sha256,
        "quality_gate_contract_sha256": manifest["quality_gate_contract_sha256"],
        "registration_sha256": registered.registration_sha256,
        "report_contract_sha256": manifest["report_contract_sha256"],
        "run_fingerprint": manifest["run_fingerprint"],
        "search_budget_sha256": manifest["search_budget_sha256"],
        "seed_policy_sha256": manifest["seed_policy_sha256"],
        "simulator_contract_sha256": manifest["simulator_contract_sha256"],
        "stop_policy_sha256": manifest["stop_policy_sha256"],
        "trial_ledger_head_sha256": manifest["trial_ledger_head_sha256"],
        "ui_state_sha256": _digest(ui),
    }
    if list(parity) != contract["required_parity_identities"]:
        raise ProtocolV3AcceptanceError("acceptance parity identities are incomplete")
    basis = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "mode": mode,
        "fixture_only": True,
        "fixture_repository_sha256": _digest(str(fixture_root)),
        "parity_identities": parity,
        "checkpoint_sha256": checkpoint_payload["checkpoint_sha256"],
        "origin_count": 12,
        "process_oos_days": 365,
        "freshness": "FIXTURE_ONLY",
        "diagnostic_only": True,
        "real_final_evidence": False,
        "task33_research_run": False,
        "safety": _SAFETY,
    }
    canonical = _canonical(basis)
    return AcceptancePathSnapshot(canonical, hashlib.sha256(canonical.encode()).hexdigest())


def build_task32_acceptance_receipt(
    snapshots: Sequence[AcceptancePathSnapshot],
    *,
    observed_fault_matrix: Mapping[str, Sequence[str]],
    ui_state_before: Mapping[str, Any],
    ui_state_after: Mapping[str, Any],
) -> Task32AcceptanceReceipt:
    if len(snapshots) != len(EXECUTION_MODES):
        raise ProtocolV3AcceptanceError("Task-32 requires exactly four path snapshots")
    rows = [validate_acceptance_path_snapshot(item).to_dict() for item in snapshots]
    if [row["mode"] for row in rows] != list(EXECUTION_MODES):
        raise ProtocolV3AcceptanceError("Task-32 path modes are missing or reordered")
    reference = rows[0]["parity_identities"]
    if any(row["parity_identities"] != reference for row in rows[1:]):
        raise ProtocolV3AcceptanceError("Task-32 execution paths are not bit-identical")
    expected_faults = _canonical_contract()["fault_matrix"]
    observed = {
        key: list(value)
        for key, value in observed_fault_matrix.items()
    }
    if observed != expected_faults:
        raise ProtocolV3AcceptanceError("Task-32 fault matrix is incomplete or reordered")
    before = _finite_mapping(ui_state_before, "ui_state_before")
    after = _finite_mapping(ui_state_after, "ui_state_after")
    if _canonical(before) != _canonical(after):
        raise ProtocolV3AcceptanceError("UI refresh or restart mutated Protocol-v3 state")
    basis = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "status": "DONE_100_FIXTURE_ACCEPTANCE",
        "execution_modes": list(EXECUTION_MODES),
        "common_parity_identities": reference,
        "path_snapshot_sha256": [row_snapshot.snapshot_sha256 for row_snapshot in snapshots],
        "fault_matrix_sha256": _digest(observed),
        "fault_groups": list(observed),
        "ui_state_sha256": _digest(before),
        "origin_count": 12,
        "process_oos_days": 365,
        "freshness": "FIXTURE_ONLY",
        "diagnostic_only": True,
        "real_final_evidence": False,
        "canonical_adoption_eligible": False,
        "bot_start_allowed": False,
        "task33_research_run": False,
        "safety": _SAFETY,
    }
    canonical = _canonical(basis)
    return Task32AcceptanceReceipt(canonical, hashlib.sha256(canonical.encode()).hexdigest())


def validate_acceptance_path_snapshot(
    value: AcceptancePathSnapshot | Mapping[str, Any],
) -> AcceptancePathSnapshot:
    root = value.to_dict() if isinstance(value, AcceptancePathSnapshot) else dict(
        _mapping(value, "acceptance path snapshot")
    )
    required = {
        "schema_version", "protocol_version", "contract_version", "mode",
        "fixture_only", "fixture_repository_sha256", "parity_identities",
        "checkpoint_sha256", "origin_count", "process_oos_days", "freshness",
        "diagnostic_only", "real_final_evidence", "task33_research_run", "safety",
    }
    if set(root) != required:
        raise ProtocolV3AcceptanceError("acceptance path snapshot fields are invalid")
    if (
        root["schema_version"] != SNAPSHOT_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
        or root["mode"] not in EXECUTION_MODES
        or root["fixture_only"] is not True
        or root["origin_count"] != 12
        or root["process_oos_days"] != 365
        or root["freshness"] != "FIXTURE_ONLY"
        or root["diagnostic_only"] is not True
        or root["real_final_evidence"] is not False
        or root["task33_research_run"] is not False
        or root["safety"] != _SAFETY
    ):
        raise ProtocolV3AcceptanceError("acceptance path snapshot violates fixture safety")
    _sha(root["fixture_repository_sha256"], "fixture_repository_sha256")
    _sha(root["checkpoint_sha256"], "checkpoint_sha256")
    parity = dict(_mapping(root["parity_identities"], "parity_identities"))
    expected = _canonical_contract()["required_parity_identities"]
    if list(parity) != expected:
        raise ProtocolV3AcceptanceError("acceptance path parity fields are invalid")
    for key, item in parity.items():
        if key in {"code_commit", "pipeline_generation_id", "run_fingerprint"}:
            if not isinstance(item, str) or not item:
                raise ProtocolV3AcceptanceError(f"{key} is invalid")
        else:
            _sha(item, key)
    canonical = _canonical(root)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if isinstance(value, AcceptancePathSnapshot) and value.snapshot_sha256 != digest:
        raise ProtocolV3AcceptanceError("acceptance path snapshot digest mismatch")
    return AcceptancePathSnapshot(canonical, digest)


def validate_task32_acceptance_receipt(
    value: Task32AcceptanceReceipt | Mapping[str, Any],
) -> Task32AcceptanceReceipt:
    root = value.to_dict() if isinstance(value, Task32AcceptanceReceipt) else dict(
        _mapping(value, "Task-32 acceptance receipt")
    )
    required = {
        "schema_version", "protocol_version", "contract_version", "status",
        "execution_modes", "common_parity_identities", "path_snapshot_sha256",
        "fault_matrix_sha256", "fault_groups", "ui_state_sha256", "origin_count",
        "process_oos_days", "freshness", "diagnostic_only", "real_final_evidence",
        "canonical_adoption_eligible", "bot_start_allowed", "task33_research_run", "safety",
    }
    if set(root) != required:
        raise ProtocolV3AcceptanceError("Task-32 acceptance receipt fields are invalid")
    if (
        root["schema_version"] != RECEIPT_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
        or root["status"] != "DONE_100_FIXTURE_ACCEPTANCE"
        or root["execution_modes"] != list(EXECUTION_MODES)
        or len(root["path_snapshot_sha256"]) != 4
        or root["fault_groups"] != list(_canonical_contract()["fault_matrix"])
        or root["origin_count"] != 12
        or root["process_oos_days"] != 365
        or root["freshness"] != "FIXTURE_ONLY"
        or root["diagnostic_only"] is not True
        or root["real_final_evidence"] is not False
        or root["canonical_adoption_eligible"] is not False
        or root["bot_start_allowed"] is not False
        or root["task33_research_run"] is not False
        or root["safety"] != _SAFETY
    ):
        raise ProtocolV3AcceptanceError("Task-32 acceptance receipt violates policy")
    for digest in root["path_snapshot_sha256"]:
        _sha(digest, "path_snapshot_sha256")
    _sha(root["fault_matrix_sha256"], "fault_matrix_sha256")
    if root["fault_matrix_sha256"] != _digest(_FAULT_MATRIX):
        raise ProtocolV3AcceptanceError("Task-32 fault matrix digest is invalid")
    _sha(root["ui_state_sha256"], "ui_state_sha256")
    parity = dict(_mapping(root["common_parity_identities"], "common_parity_identities"))
    if list(parity) != _canonical_contract()["required_parity_identities"]:
        raise ProtocolV3AcceptanceError("Task-32 receipt parity identities are invalid")
    for key, item in parity.items():
        if key in {"code_commit", "pipeline_generation_id", "run_fingerprint"}:
            if not isinstance(item, str) or not item:
                raise ProtocolV3AcceptanceError(f"Task-32 receipt {key} is invalid")
        else:
            _sha(item, f"Task-32 receipt {key}")
    canonical = _canonical(root)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    if isinstance(value, Task32AcceptanceReceipt) and value.receipt_sha256 != digest:
        raise ProtocolV3AcceptanceError("Task-32 acceptance receipt digest mismatch")
    return Task32AcceptanceReceipt(canonical, digest)


def _canonical_contract() -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "execution_modes": list(EXECUTION_MODES),
        "required_parity_identities": list(_PARITY_IDENTITIES),
        "fault_matrix": _FAULT_MATRIX,
        "fixture_isolation": {
            "canonical_repository_root_forbidden": True,
            "canonical_report_roots_forbidden": True,
            "real_final_evidence": False,
            "freshness_claim": "FIXTURE_ONLY",
            "diagnostic_only": True,
            "task33_research_run": False,
        },
        "acceptance": {
            "outer_origins": 12,
            "process_oos_days": 365,
            "all_modes_bit_identical": True,
            "ui_reads_are_state_neutral": True,
            "all_faults_fail_closed": True,
            "last_committed_head_remains_valid": True,
        },
        "safety": _SAFETY,
    }


def _fixture_file(value: str | Path, fixture_root: Path, source_root: Path) -> Path:
    path = Path(value)
    if path.is_symlink():
        raise ProtocolV3AcceptanceError("fixture artifact is unsafe")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ProtocolV3AcceptanceError("fixture artifact is missing") from exc
    if resolved.is_symlink() or not resolved.is_file():
        raise ProtocolV3AcceptanceError("fixture artifact is unsafe")
    if not is_path_within(resolved, fixture_root) or is_path_within(resolved, source_root):
        raise ProtocolV3AcceptanceError("fixture artifact escaped its isolated root")
    return resolved


def _real_directory(value: str | Path, name: str) -> Path:
    path = Path(value)
    if not path.exists() or not path.is_dir() or path.is_symlink():
        raise ProtocolV3AcceptanceError(f"{name} must be a real directory")
    return path.resolve()


def _finite_mapping(value: Mapping[str, Any], name: str) -> dict[str, Any]:
    root = dict(_mapping(value, name))
    _finite(root, name)
    _canonical(root)
    return root


def _finite(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolV3AcceptanceError(f"{path} contains a non-string key")
            _finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ProtocolV3AcceptanceError(f"{path} contains a non-finite value")
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise ProtocolV3AcceptanceError(f"{path} contains unsupported JSON")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolV3AcceptanceError(f"{name} must be an object")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ProtocolV3AcceptanceError(f"{name} must be lowercase sha256")
    return value


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProtocolV3AcceptanceError("acceptance evidence is not canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _strict_json(text: str, name: str) -> Any:
    def pairs(pairs_value: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs_value:
            if key in result:
                raise ValueError(f"duplicate key: {key}")
            result[key] = item
        return result
    try:
        return json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise ProtocolV3AcceptanceError(f"{name} is invalid JSON") from exc


__all__ = [
    "AcceptancePathSnapshot",
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "EXECUTION_MODES",
    "ProtocolV3AcceptanceError",
    "Task32AcceptanceReceipt",
    "build_task32_acceptance_receipt",
    "capture_acceptance_path_snapshot",
    "load_acceptance_contract",
    "validate_acceptance_contract",
    "validate_acceptance_path_snapshot",
    "validate_task32_acceptance_receipt",
]
