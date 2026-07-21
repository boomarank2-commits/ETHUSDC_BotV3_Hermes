"""Transitive Task-31 attestation for one completed sealed pipeline-final year.

This module is downstream of the create-only registration/claim, the result-blind
Task-13 checkpoint, and Tasks 23 through 27.  It opens no report by itself.  A
fresh attestation can be built only after all twelve origins and all 365 UTC days
are complete, with every result source recomputed from its typed dependencies.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Final

from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.protocol_v3.boundaries import (
    MonthlyProcessBoundaryPlan,
    validate_monthly_process_boundary_plan,
)
from ethusdc_bot.protocol_v3.hindsight_binding import BoundHindsightBenchmarks
from ethusdc_bot.protocol_v3.historical_diagnostics import (
    HistoricalDiagnostics,
    build_historical_diagnostics,
    validate_historical_diagnostics,
)
from ethusdc_bot.protocol_v3.monthly_quality_gate import (
    MonthlyQualityGateReport,
    validate_monthly_quality_gate_report,
)
from ethusdc_bot.protocol_v3.outer_mtm_ledger import (
    OuterMtmLedger,
    validate_outer_mtm_ledger,
)
from ethusdc_bot.protocol_v3.outer_origins import (
    OuterOriginProcess,
    validate_outer_origin_process,
)
from ethusdc_bot.protocol_v3.pipeline_final import (
    PipelineFinalClaim,
    PipelineFinalError,
    PipelineFinalRegistration,
    pipeline_final_boundary_plan,
    pipeline_final_boundary_plan_sha256,
    validate_pipeline_final_claim,
    validate_pipeline_final_registration,
)
from ethusdc_bot.protocol_v3.pipeline_final_checkpoint import (
    PipelineFinalCheckpoint,
    PipelineFinalCheckpointReceipt,
    validate_pipeline_final_checkpoint_receipt,
    verify_replayed_pipeline_final_checkpoint,
)
from ethusdc_bot.protocol_v3.pipeline_final_progress import (
    PipelineFinalProgress,
    validate_pipeline_final_progress,
)

PROTOCOL_VERSION: Final = "3.0.0"
ATTESTATION_SCHEMA_VERSION: Final = "protocol_v3_pipeline_final_attestation_v1"
ATTESTATION_CONTRACT_VERSION: Final = (
    "protocol_v3_transitively_revalidated_pipeline_final_attestation_v1"
)
ATTESTATION_ROOT: Final = "reports/protocol_v3/pipeline_final/attestations"
_CLOCK_TOLERANCE: Final = timedelta(minutes=5)
_TARGET: Final = Decimal("3")
_SAFETY: Final = {
    "api_keys": "forbidden",
    "canonical_adoption": "locked",
    "final_report_opened": False,
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "result_feedback_to_pipeline": False,
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class PipelineFinalAttestationError(PipelineFinalError):
    """Raised when sealed final evidence cannot be transitively attested."""


@dataclass(frozen=True)
class PipelineFinalAttestation:
    canonical_json: str
    attestation_sha256: str
    attestation_id: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def build_pipeline_final_attestation(
    *,
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
    completed_at_utc: str,
) -> PipelineFinalAttestation:
    reg = validate_pipeline_final_registration(registration)
    reg_payload = reg.to_dict()
    claimed = validate_pipeline_final_claim(claim)
    claim_payload = claimed.to_dict()
    if (
        claim_payload["registration_id"] != reg_payload["registration_id"]
        or claim_payload["registration_sha256"] != reg.registration_sha256
        or claim_payload["result_opened"] is not False
    ):
        raise PipelineFinalAttestationError(
            "pipeline-final claim differs from registration or is already opened"
        )
    plan = _validate_registered_plan(reg, boundary_plan)
    completed = _utc(completed_at_utc, "completed_at_utc")
    window_end = _utc(reg_payload["end_exclusive_utc"], "end_exclusive_utc")
    if completed < window_end:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation cannot predate the complete sealed window"
        )

    validated_progress = validate_pipeline_final_progress(
        progress,
        registration=reg,
        claim=claimed,
    )
    progress_payload = validated_progress.to_dict()
    if (
        progress_payload["completed_origin_count"] != 12
        or progress_payload["next_origin_index"] is not None
        or progress_payload["status"] != "ORIGINS_COMPLETE_RESULTS_HIDDEN"
        or progress_payload["final_report_visible"] is not False
        or progress_payload["task31_attestation_available"] is not False
    ):
        raise PipelineFinalAttestationError(
            "pipeline-final progress is not twelve-origin complete and sealed"
        )
    if not isinstance(checkpoint, PipelineFinalCheckpoint):
        raise PipelineFinalAttestationError(
            "a validated Task-13 PipelineFinalCheckpoint is required"
        )
    receipt = validate_pipeline_final_checkpoint_receipt(checkpoint.receipt)
    verify_replayed_pipeline_final_checkpoint(
        receipt,
        validated_progress,
        registration=reg,
        claim=claimed,
    )
    checkpoint_payload = checkpoint.checkpoint.to_dict()
    result = _mapping(checkpoint_payload.get("result"), "checkpoint.result")
    result_payload = _mapping(result.get("payload"), "checkpoint.result.payload")
    if (
        result.get("status") != "IN_PROGRESS"
        or set(result_payload) != {"task31_pipeline_final_checkpoint_receipt"}
        or result_payload["task31_pipeline_final_checkpoint_receipt"]
        != receipt.to_dict()
    ):
        raise PipelineFinalAttestationError(
            "Task-13 checkpoint does not contain the exact final progress receipt"
        )

    process = validate_outer_origin_process(outer_process, boundary_plan=plan)
    process_payload = process.to_dict()
    _bind_process_to_progress_and_registration(
        process_payload,
        progress_payload,
        reg_payload,
    )
    baseline = validate_outer_mtm_ledger(
        baseline_ledger,
        boundary_plan=plan,
        outer_process=process,
    )
    joint = validate_outer_mtm_ledger(
        joint_stress_ledger,
        boundary_plan=plan,
        outer_process=process,
    )
    slippage = validate_outer_mtm_ledger(
        slippage_stress_ledger,
        boundary_plan=plan,
        outer_process=process,
    )
    gate = validate_monthly_quality_gate_report(
        monthly_quality_report.to_dict(),
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        joint_stress_ledger=joint,
        slippage_stress_ledger=slippage,
        stress_identity_evidence=stress_identity_evidence,
        regime_evidence=regime_evidence,
        integrity_evidence=integrity_evidence,
    )
    task27 = build_historical_diagnostics(
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        monthly_quality_report=gate,
        bound_hindsight_benchmarks=bound_hindsight_benchmarks,
    )
    task27 = validate_historical_diagnostics(
        task27.to_dict(),
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        monthly_quality_report=gate,
        bound_hindsight_benchmarks=bound_hindsight_benchmarks,
    )
    gate_payload = gate.to_dict()
    task27_payload = task27.to_dict()
    baseline_payload = baseline.to_dict()
    net_total = _decimal(
        baseline_payload["totals"]["net_mtm_usdc"],
        "baseline net_mtm_usdc",
    )
    net_per_day = net_total / Decimal(365)
    historically_hit = net_per_day >= _TARGET
    if historically_hit is not gate_payload["historically_hit"]:
        raise PipelineFinalAttestationError(
            "Task-25 net result and Task-26 historical target claim differ"
        )
    bootstrap_supported = bool(
        task27_payload["historical_bootstrap_lower_bound"]
    )
    statistically_supported = bool(
        gate_payload["robustness_passed"] and bootstrap_supported
    )
    evidence_status = {
        "historically_hit": historically_hit,
        "fresh_pre_registered_sealed_365": True,
        "sealed_bootstrap_target_supported": bootstrap_supported,
        "statistically_supported": statistically_supported,
        "canonical_adoption_eligible": False,
    }
    basis = {
        "schema_version": ATTESTATION_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": ATTESTATION_CONTRACT_VERSION,
        "registration_id": reg_payload["registration_id"],
        "registration_sha256": reg.registration_sha256,
        "claim_id": claimed.claim_id,
        "claim_sha256": claimed.claim_sha256,
        "frozen_identity_manifest_sha256": reg_payload[
            "frozen_identity_manifest_sha256"
        ],
        "window": {
            "start_inclusive_utc": reg_payload["start_inclusive_utc"],
            "end_exclusive_utc": reg_payload["end_exclusive_utc"],
            "calendar_days": 365,
            "boundary_plan_sha256": pipeline_final_boundary_plan_sha256(plan),
        },
        "completed_at_utc": _fmt(completed),
        "checkpoint": {
            "checkpoint_id": checkpoint_payload["checkpoint_id"],
            "checkpoint_sha256": checkpoint_payload["checkpoint_sha256"],
            "checkpoint_sequence": checkpoint_payload["sequence"],
            "checkpoint_receipt_sha256": receipt.receipt_sha256,
        },
        "progress": {
            "progress_sha256": validated_progress.progress_sha256,
            "completed_origin_count": 12,
            "origin_chain_head_sha256": progress_payload[
                "origin_chain_head_sha256"
            ],
        },
        "source_evidence": {
            "outer_process_sha256": process.process_sha256,
            "baseline_ledger_sha256": baseline.ledger_sha256,
            "joint_stress_ledger_sha256": joint.ledger_sha256,
            "slippage_stress_ledger_sha256": slippage.ledger_sha256,
            "monthly_quality_report_sha256": gate.report_sha256,
            "task27_diagnostics_sha256": task27.report_sha256,
            "task27_pre_bootstrap_manifest_sha256": task27_payload[
                "pre_bootstrap_input_manifest_sha256"
            ],
            "bound_hindsight_benchmarks_sha256": task27_payload[
                "bound_hindsight_benchmarks_sha256"
            ],
        },
        "metrics": {
            "process_net_usdc": _decimal_text(net_total),
            "process_net_usdc_per_calendar_day": _decimal_text(net_per_day),
            "process_calendar_days": 365,
            "monthly_quality_status": gate_payload["status"],
            "monthly_robustness_passed": gate_payload["robustness_passed"],
            "bootstrap_results": task27_payload["bootstrap_results"],
        },
        "evidence_status": evidence_status,
        "final_evaluation_status": (
            "STATISTICALLY_SUPPORTED"
            if statistically_supported
            else "FRESH_FINAL_NOT_STATISTICALLY_SUPPORTED"
        ),
        "result_feedback_to_pipeline_allowed": False,
        "report_opened": False,
        "safety": _SAFETY,
    }
    digest = _digest(basis)
    attestation_id = f"protocol_v3_pipeline_final_attestation_sha256:{digest}"
    candidate = PipelineFinalAttestation(
        _canonical(
            {
                **basis,
                "attestation_id": attestation_id,
                "attestation_sha256": digest,
            }
        ),
        digest,
        attestation_id,
    )
    return validate_pipeline_final_attestation(candidate)


def validate_pipeline_final_attestation(
    value: PipelineFinalAttestation | Mapping[str, Any],
    *,
    registration: PipelineFinalRegistration | None = None,
    claim: PipelineFinalClaim | None = None,
    progress: PipelineFinalProgress | None = None,
    checkpoint: PipelineFinalCheckpoint | None = None,
    boundary_plan: MonthlyProcessBoundaryPlan | None = None,
    outer_process: OuterOriginProcess | None = None,
    baseline_ledger: OuterMtmLedger | None = None,
    joint_stress_ledger: OuterMtmLedger | None = None,
    slippage_stress_ledger: OuterMtmLedger | None = None,
    monthly_quality_report: MonthlyQualityGateReport | None = None,
    stress_identity_evidence: Mapping[str, Any] | None = None,
    regime_evidence: Mapping[str, Any] | None = None,
    integrity_evidence: Mapping[str, Any] | None = None,
    bound_hindsight_benchmarks: BoundHindsightBenchmarks | None = None,
) -> PipelineFinalAttestation:
    root = (
        value.to_dict()
        if isinstance(value, PipelineFinalAttestation)
        else dict(_mapping(value, "pipeline_final_attestation"))
    )
    if not isinstance(value, PipelineFinalAttestation):
        dependencies = (
            registration,
            claim,
            progress,
            checkpoint,
            boundary_plan,
            outer_process,
            baseline_ledger,
            joint_stress_ledger,
            slippage_stress_ledger,
            monthly_quality_report,
            stress_identity_evidence,
            regime_evidence,
            integrity_evidence,
            bound_hindsight_benchmarks,
        )
        if any(item is None for item in dependencies):
            raise PipelineFinalAttestationError(
                "persisted Task-31 attestation requires every source dependency"
            )
        expected = build_pipeline_final_attestation(
            registration=registration,
            claim=claim,
            progress=progress,
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
            completed_at_utc=root.get("completed_at_utc"),
        ).to_dict()
        if root != expected:
            raise PipelineFinalAttestationError(
                "persisted Task-31 attestation differs from source re-evaluation"
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
        "window",
        "completed_at_utc",
        "checkpoint",
        "progress",
        "source_evidence",
        "metrics",
        "evidence_status",
        "final_evaluation_status",
        "result_feedback_to_pipeline_allowed",
        "report_opened",
        "safety",
        "attestation_id",
        "attestation_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != ATTESTATION_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != ATTESTATION_CONTRACT_VERSION
    ):
        raise PipelineFinalAttestationError(
            "pipeline-final attestation fields or versions are invalid"
        )
    for name in (
        "registration_sha256",
        "claim_sha256",
        "frozen_identity_manifest_sha256",
        "attestation_sha256",
    ):
        _sha(root[name], name)
    window = dict(_mapping(root["window"], "attestation.window"))
    if set(window) != {
        "start_inclusive_utc",
        "end_exclusive_utc",
        "calendar_days",
        "boundary_plan_sha256",
    }:
        raise PipelineFinalAttestationError("attestation window fields are invalid")
    start = _utc(window["start_inclusive_utc"], "attestation.window.start")
    end = _utc(window["end_exclusive_utc"], "attestation.window.end")
    if end - start != timedelta(days=365) or window["calendar_days"] != 365:
        raise PipelineFinalAttestationError(
            "attestation window must be exactly 365 complete UTC days"
        )
    completed = _utc(root["completed_at_utc"], "completed_at_utc")
    if completed < end:
        raise PipelineFinalAttestationError(
            "attestation completion predates the sealed window end"
        )
    checkpoint_payload = dict(_mapping(root["checkpoint"], "attestation.checkpoint"))
    if set(checkpoint_payload) != {
        "checkpoint_id",
        "checkpoint_sha256",
        "checkpoint_sequence",
        "checkpoint_receipt_sha256",
    }:
        raise PipelineFinalAttestationError("attestation checkpoint fields are invalid")
    for name in (
        "checkpoint_sha256",
        "checkpoint_receipt_sha256",
    ):
        _sha(checkpoint_payload[name], name)
    if (
        type(checkpoint_payload["checkpoint_sequence"]) is not int
        or checkpoint_payload["checkpoint_sequence"] < 1
    ):
        raise PipelineFinalAttestationError("checkpoint sequence is invalid")
    progress_payload = dict(_mapping(root["progress"], "attestation.progress"))
    if set(progress_payload) != {
        "progress_sha256",
        "completed_origin_count",
        "origin_chain_head_sha256",
    }:
        raise PipelineFinalAttestationError("attestation progress fields are invalid")
    _sha(progress_payload["progress_sha256"], "progress_sha256")
    _sha(progress_payload["origin_chain_head_sha256"], "origin_chain_head_sha256")
    if progress_payload["completed_origin_count"] != 12:
        raise PipelineFinalAttestationError("attestation requires twelve origins")
    source = dict(_mapping(root["source_evidence"], "attestation.source_evidence"))
    expected_sources = {
        "outer_process_sha256",
        "baseline_ledger_sha256",
        "joint_stress_ledger_sha256",
        "slippage_stress_ledger_sha256",
        "monthly_quality_report_sha256",
        "task27_diagnostics_sha256",
        "task27_pre_bootstrap_manifest_sha256",
        "bound_hindsight_benchmarks_sha256",
    }
    if set(source) != expected_sources:
        raise PipelineFinalAttestationError("attestation source evidence is incomplete")
    for name, item in source.items():
        _sha(item, name)
    metrics = dict(_mapping(root["metrics"], "attestation.metrics"))
    if set(metrics) != {
        "process_net_usdc",
        "process_net_usdc_per_calendar_day",
        "process_calendar_days",
        "monthly_quality_status",
        "monthly_robustness_passed",
        "bootstrap_results",
    }:
        raise PipelineFinalAttestationError("attestation metrics fields are invalid")
    net = _decimal(metrics["process_net_usdc"], "process_net_usdc")
    per_day = _decimal(
        metrics["process_net_usdc_per_calendar_day"],
        "process_net_usdc_per_calendar_day",
    )
    if metrics["process_calendar_days"] != 365 or per_day != net / Decimal(365):
        raise PipelineFinalAttestationError("attestation process metrics are inconsistent")
    bootstrap = metrics["bootstrap_results"]
    if (
        not isinstance(bootstrap, list)
        or [row.get("expected_block_length") for row in bootstrap] != [5, 10, 20]
        or any(
            row.get("replications") != 10_000
            or row.get("order_statistic_one_based") != 500
            for row in bootstrap
        )
    ):
        raise PipelineFinalAttestationError("attestation bootstrap results are invalid")
    evidence = dict(_mapping(root["evidence_status"], "attestation.evidence_status"))
    if set(evidence) != {
        "historically_hit",
        "fresh_pre_registered_sealed_365",
        "sealed_bootstrap_target_supported",
        "statistically_supported",
        "canonical_adoption_eligible",
    }:
        raise PipelineFinalAttestationError("attestation evidence status fields are invalid")
    historically_hit = per_day >= _TARGET
    bootstrap_supported = all(
        _decimal(row.get("lower_bound_usdc_per_day"), "bootstrap lower bound")
        >= _TARGET
        for row in bootstrap
    )
    statistically_supported = bool(
        metrics["monthly_robustness_passed"] and bootstrap_supported
    )
    expected_evidence = {
        "historically_hit": historically_hit,
        "fresh_pre_registered_sealed_365": True,
        "sealed_bootstrap_target_supported": bootstrap_supported,
        "statistically_supported": statistically_supported,
        "canonical_adoption_eligible": False,
    }
    if evidence != expected_evidence:
        raise PipelineFinalAttestationError(
            "attestation evidence booleans are not derived from source metrics"
        )
    expected_status = (
        "STATISTICALLY_SUPPORTED"
        if statistically_supported
        else "FRESH_FINAL_NOT_STATISTICALLY_SUPPORTED"
    )
    if (
        root["final_evaluation_status"] != expected_status
        or root["result_feedback_to_pipeline_allowed"] is not False
        or root["report_opened"] is not False
        or root["safety"] != _SAFETY
    ):
        raise PipelineFinalAttestationError(
            "attestation final status, sealing, or safety is invalid"
        )
    observed = _sha(root["attestation_sha256"], "attestation_sha256")
    expected_id = f"protocol_v3_pipeline_final_attestation_sha256:{observed}"
    if root["attestation_id"] != expected_id:
        raise PipelineFinalAttestationError("attestation id does not match its digest")
    basis = dict(root)
    basis.pop("attestation_id")
    basis.pop("attestation_sha256")
    if observed != _digest(basis):
        raise PipelineFinalAttestationError("pipeline-final attestation digest mismatch")
    return PipelineFinalAttestation(_canonical(root), observed, expected_id)


def write_pipeline_final_attestation(
    attestation: PipelineFinalAttestation,
    repository_root: str | Path,
) -> Path:
    if not isinstance(attestation, PipelineFinalAttestation):
        raise PipelineFinalAttestationError(
            "validated PipelineFinalAttestation required"
        )
    validated = validate_pipeline_final_attestation(attestation)
    payload = validated.to_dict()
    now = _utc_now()
    completed = _utc(payload["completed_at_utc"], "completed_at_utc")
    end = _utc(payload["window"]["end_exclusive_utc"], "window.end")
    if now < end:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation cannot be persisted before window end"
        )
    if abs(now - completed) > _CLOCK_TOLERANCE:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation completion timestamp is not current"
        )
    repo = _repo(repository_root)
    root = _safe_root(repo, ATTESTATION_ROOT, create=True)
    path = root / f"{payload['registration_sha256']}.json"
    try:
        _write_create_only(path, _bytes(validated.canonical_json))
    except FileExistsError as exc:
        raise PipelineFinalAttestationError(
            "pipeline-final registration already has an attestation"
        ) from exc
    reloaded = read_pipeline_final_attestation(path, repo)
    if reloaded != validated:
        raise PipelineFinalAttestationError("pipeline-final attestation reload mismatch")
    return path


def read_pipeline_final_attestation(
    path: str | Path,
    repository_root: str | Path,
) -> PipelineFinalAttestation:
    repo = _repo(repository_root)
    root = _safe_root(repo, ATTESTATION_ROOT, create=False)
    guarded = _exact_child(Path(path), root, repo)
    value, raw = _read(guarded)
    candidate = PipelineFinalAttestation(
        _canonical(value),
        str(value.get("attestation_sha256", "")),
        str(value.get("attestation_id", "")),
    )
    attestation = validate_pipeline_final_attestation(candidate)
    expected = root / f"{attestation.to_dict()['registration_sha256']}.json"
    if guarded.resolve(strict=True) != expected.resolve(strict=True):
        raise PipelineFinalAttestationError(
            "pipeline-final attestation is stored under the wrong path"
        )
    if raw != _bytes(attestation.canonical_json):
        raise PipelineFinalAttestationError(
            "pipeline-final attestation bytes are not canonical"
        )
    return attestation


def _validate_registered_plan(
    registration: PipelineFinalRegistration,
    boundary_plan: MonthlyProcessBoundaryPlan,
) -> MonthlyProcessBoundaryPlan:
    validate_monthly_process_boundary_plan(boundary_plan)
    payload = registration.to_dict()
    expected = pipeline_final_boundary_plan(
        start_inclusive_utc=payload["start_inclusive_utc"],
        end_exclusive_utc=payload["end_exclusive_utc"],
    )
    if boundary_plan != expected:
        raise PipelineFinalAttestationError(
            "Task-31 boundary plan differs from preregistration"
        )
    manifest = payload["frozen_identity_manifest"]
    if pipeline_final_boundary_plan_sha256(boundary_plan) != manifest[
        "boundary_plan_sha256"
    ]:
        raise PipelineFinalAttestationError(
            "Task-31 boundary digest differs from frozen identity manifest"
        )
    return boundary_plan


def _bind_process_to_progress_and_registration(
    process: Mapping[str, Any],
    progress: Mapping[str, Any],
    registration: Mapping[str, Any],
) -> None:
    process_origins = process["origins"]
    progress_origins = progress["completed_origins"]
    if len(process_origins) != 12 or len(progress_origins) != 12:
        raise PipelineFinalAttestationError(
            "Task-31 process/progress must contain exactly twelve origins"
        )
    for expected_index, (selected, completed) in enumerate(
        zip(process_origins, progress_origins, strict=True),
        start=1,
    ):
        if (
            selected["origin_index"] != expected_index
            or completed["origin_index"] != expected_index
            or completed["origin_selection_sha256"]
            != selected["origin_sha256"]
        ):
            raise PipelineFinalAttestationError(
                "Task-31 progress and outer process origin chains differ"
            )
    manifest = registration["frozen_identity_manifest"]
    run_fingerprints = {
        row["selection_decision"]["frozen_pipeline_config"]["run_fingerprint"][
            "fingerprint_sha256"
        ]
        for row in process_origins
    }
    if run_fingerprints != {manifest["run_fingerprint"].rsplit(":", 1)[1]}:
        raise PipelineFinalAttestationError(
            "Task-31 outer origins use another run fingerprint"
        )
    if (
        process_origins[0]["pipeline_generation_id"]
        != manifest["pipeline_generation_id"]
        or process_origins[0]["code_commit"] != manifest["code_commit"]
    ):
        raise PipelineFinalAttestationError(
            "Task-31 outer process changed pipeline generation or code"
        )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PipelineFinalAttestationError(f"{name} must be an object")
    return value


def _decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise PipelineFinalAttestationError(f"{name} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PipelineFinalAttestationError(f"{name} must be a finite decimal") from exc
    if not result.is_finite():
        raise PipelineFinalAttestationError(f"{name} must be a finite decimal")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PipelineFinalAttestationError(f"{name} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PipelineFinalAttestationError(f"{name} is invalid") from exc
    if parsed.tzinfo != UTC:
        raise PipelineFinalAttestationError(f"{name} must be UTC")
    return parsed


def _fmt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise PipelineFinalAttestationError(f"{name} must be lowercase sha256")
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


def _bytes(value: str) -> bytes:
    return (value + "\n").encode("utf-8")


def _repo(value: str | Path) -> Path:
    path = Path(value)
    if not path.exists() or not path.is_dir() or path.is_symlink():
        raise PipelineFinalAttestationError(
            "repository_root must be an existing real directory"
        )
    return path.resolve()


def _safe_root(repo: Path, relative_text: str, *, create: bool) -> Path:
    relative = PurePosixPath(relative_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation root must be repository-relative"
        )
    root = repo.joinpath(*relative.parts)
    _no_symlinks(repo, root)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.exists() or not root.is_dir() or root.is_symlink():
        raise PipelineFinalAttestationError(
            "pipeline-final attestation root is missing or unsafe"
        )
    resolved = root.resolve()
    if not is_path_within(resolved, repo):
        raise PipelineFinalAttestationError(
            "pipeline-final attestation root escapes repository_root"
        )
    _no_symlinks(repo, resolved)
    return resolved


def _exact_child(path_value: Path, root: Path, repo: Path) -> Path:
    candidate = path_value if path_value.is_absolute() else repo / path_value
    _no_symlinks(repo, candidate)
    if candidate.is_symlink():
        raise PipelineFinalAttestationError(
            "pipeline-final attestation path must not be a symlink"
        )
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation path is missing or unreadable"
        ) from exc
    if not is_path_within(resolved, root) or resolved.parent != root:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation path lies outside its fixed root"
        )
    return resolved


def _no_symlinks(repo: Path, target: Path) -> None:
    try:
        parts = target.relative_to(repo).parts
    except ValueError as exc:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation target escapes repository root"
        ) from exc
    current = repo
    for part in parts:
        current /= part
        if current.exists() and current.is_symlink():
            raise PipelineFinalAttestationError(
                "symlinked pipeline-final attestation paths are forbidden"
            )


def _write_create_only(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation is unreadable or invalid"
        ) from exc
    if not isinstance(value, dict):
        raise PipelineFinalAttestationError(
            "pipeline-final attestation must contain one object"
        )
    return value, raw


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "ATTESTATION_CONTRACT_VERSION",
    "ATTESTATION_ROOT",
    "ATTESTATION_SCHEMA_VERSION",
    "PipelineFinalAttestation",
    "PipelineFinalAttestationError",
    "build_pipeline_final_attestation",
    "read_pipeline_final_attestation",
    "validate_pipeline_final_attestation",
    "write_pipeline_final_attestation",
]
