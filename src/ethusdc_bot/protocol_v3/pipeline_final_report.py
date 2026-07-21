"""Exactly-once opening of the Protocol-v3 pipeline-final report.

The report is derived only from a persisted and transitively revalidated Task-31
attestation.  The fixed report is published before a create-only open receipt.
That ordering permits one crash-recovery case: when the exact report exists but
its receipt does not, the receipt may be completed after the report is fully
revalidated.  Once the receipt exists, every second open attempt fails closed.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Final

from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.protocol_v3.hindsight_binding import BoundHindsightBenchmarks
from ethusdc_bot.protocol_v3.monthly_quality_gate import MonthlyQualityGateReport
from ethusdc_bot.protocol_v3.outer_mtm_ledger import OuterMtmLedger
from ethusdc_bot.protocol_v3.outer_origins import OuterOriginProcess
from ethusdc_bot.protocol_v3.pipeline_final import (
    PipelineFinalClaim,
    PipelineFinalRegistration,
    validate_pipeline_final_registration,
)
from ethusdc_bot.protocol_v3.pipeline_final_attestation import (
    PipelineFinalAttestation,
    PipelineFinalAttestationError,
    read_pipeline_final_attestation,
    validate_pipeline_final_attestation,
)
from ethusdc_bot.protocol_v3.pipeline_final_checkpoint import PipelineFinalCheckpoint
from ethusdc_bot.protocol_v3.pipeline_final_progress import PipelineFinalProgress
from ethusdc_bot.protocol_v3.reporting import (
    PROTOCOL_V3_PIPELINE_FINAL,
    PROTOCOL_VERSION,
    REPORT_SCHEMA_VERSION,
    REPORT_STORAGE_ROOTS,
    ProtocolV3Report,
)

FINAL_REPORT_CONTRACT_VERSION: Final = (
    "protocol_v3_exactly_once_pipeline_final_report_open_v1"
)
OPEN_RECEIPT_SCHEMA_VERSION: Final = (
    "protocol_v3_pipeline_final_open_receipt_v1"
)
OPEN_RECEIPT_ROOT: Final = "reports/protocol_v3/pipeline_final_open_receipts"
REPORT_ROOT: Final = REPORT_STORAGE_ROOTS[PROTOCOL_V3_PIPELINE_FINAL]
_CLOCK_TOLERANCE: Final = timedelta(minutes=5)
_TARGET: Final = Decimal("3")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PIPE = re.compile(r"^protocol_v3_pipeline_sha256:[0-9a-f]{64}$")
_RUN = re.compile(r"^protocol_v3_run_sha256:[0-9a-f]{64}$")
_REPORT_KEYS: Final = {
    "schema_version",
    "protocol_version",
    "artifact_kind",
    "report_id",
    "created_at_utc",
    "run_fingerprint",
    "pipeline_generation",
    "evidence_window",
    "metrics",
    "evidence_inputs",
    "evidence_status",
    "details",
    "safety",
}
_WINDOW_KEYS: Final = {
    "window_id",
    "window_class",
    "start_inclusive_utc",
    "end_exclusive_utc",
    "calendar_days",
    "registration_id",
    "registration_sha256",
}
_METRIC_KEYS: Final = {
    "process_oos_net_usdc",
    "process_oos_calendar_days",
    "target_usdc_per_calendar_day",
}
_INPUT_KEYS: Final = {
    "historical_bootstrap_attestation_sha256",
    "sealed_bootstrap_attestation_sha256",
    "task31_final_attestation_sha256",
}
_STATUS_KEYS: Final = {
    "historically_hit",
    "historical_bootstrap_lower_bound",
    "freshness",
    "fresh_pre_registered_sealed_365",
    "sealed_bootstrap_target_supported",
    "statistically_supported",
    "canonical_adoption_eligible",
    "diagnostic_only",
}
_DETAIL_KEYS: Final = {
    "producer",
    "producer_status",
    "source_artifact_ids",
    "reason_codes",
}
_REPORT_SAFETY: Final = {
    "public_data_only": True,
    "orders_enabled": False,
    "trading_api_enabled": False,
    "api_keys_used": False,
    "live": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "short_margin_futures_leverage": "forbidden",
    "canonical_adoption_enabled": False,
}
_RECEIPT_SAFETY: Final = {
    "api_keys": "forbidden",
    "canonical_adoption": "locked",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "result_feedback_to_pipeline": False,
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class PipelineFinalReportError(ValueError):
    """Raised when a final report or open receipt fails closed."""


class PipelineFinalReportAlreadyOpenedError(PipelineFinalReportError):
    """Raised after the one permitted report-open receipt exists."""


@dataclass(frozen=True)
class PipelineFinalOpenReceipt:
    canonical_json: str
    receipt_sha256: str
    receipt_id: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


@dataclass(frozen=True)
class PipelineFinalReportOpenResult:
    report: ProtocolV3Report
    report_path: Path
    receipt: PipelineFinalOpenReceipt
    receipt_path: Path


def build_pipeline_final_report(
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
    *,
    created_at_utc: str,
) -> ProtocolV3Report:
    if not isinstance(attestation, PipelineFinalAttestation):
        raise PipelineFinalReportError(
            "validated PipelineFinalAttestation required to build final report"
        )
    attested = validate_pipeline_final_attestation(attestation)
    registered = validate_pipeline_final_registration(registration)
    source = attested.to_dict()
    registration_payload = registered.to_dict()
    if (
        source["registration_id"] != registration_payload["registration_id"]
        or source["registration_sha256"] != registered.registration_sha256
    ):
        raise PipelineFinalReportError(
            "pipeline-final report registration differs from attestation"
        )
    manifest = dict(
        _mapping(
            registration_payload["frozen_identity_manifest"],
            "registration.frozen_identity_manifest",
        )
    )
    created = _utc(created_at_utc, "created_at_utc")
    window = dict(_mapping(source["window"], "attestation.window"))
    end = _utc(window["end_exclusive_utc"], "attestation.window.end")
    if created < end:
        raise PipelineFinalReportError(
            "pipeline-final report cannot predate the sealed window end"
        )
    metrics_source = dict(_mapping(source["metrics"], "attestation.metrics"))
    evidence_source = dict(
        _mapping(source["evidence_status"], "attestation.evidence_status")
    )
    source_evidence = dict(
        _mapping(source["source_evidence"], "attestation.source_evidence")
    )
    net = _decimal(metrics_source["process_net_usdc"], "process_net_usdc")
    reasons: list[str] = []
    if not evidence_source["historically_hit"]:
        reasons.append("target_not_historically_hit")
    if not evidence_source["sealed_bootstrap_target_supported"]:
        reasons.append("sealed_bootstrap_lower_bound_below_target")
    if not metrics_source["monthly_robustness_passed"]:
        reasons.append("monthly_robustness_gate_not_passed")
    if evidence_source["statistically_supported"]:
        reasons.append("statistically_supported")
    basis = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "artifact_kind": PROTOCOL_V3_PIPELINE_FINAL,
        "report_id": _report_id(source["registration_sha256"]),
        "created_at_utc": _fmt(created),
        "run_fingerprint": manifest["run_fingerprint"],
        "pipeline_generation": manifest["pipeline_generation_id"],
        "evidence_window": {
            "window_id": "sealed_final_" + source["registration_sha256"][:24],
            "window_class": "sealed_final_holdout",
            "start_inclusive_utc": window["start_inclusive_utc"],
            "end_exclusive_utc": window["end_exclusive_utc"],
            "calendar_days": 365,
            "registration_id": source["registration_id"],
            "registration_sha256": source["registration_sha256"],
        },
        "metrics": {
            "process_oos_net_usdc": float(net),
            "process_oos_calendar_days": 365,
            "target_usdc_per_calendar_day": 3.0,
        },
        "evidence_inputs": {
            "historical_bootstrap_attestation_sha256": None,
            "sealed_bootstrap_attestation_sha256": source_evidence[
                "task27_diagnostics_sha256"
            ],
            "task31_final_attestation_sha256": attested.attestation_sha256,
        },
        "evidence_status": {
            "historically_hit": evidence_source["historically_hit"],
            "historical_bootstrap_lower_bound": False,
            "freshness": "FRESH_SEALED_FINAL",
            "fresh_pre_registered_sealed_365": True,
            "sealed_bootstrap_target_supported": evidence_source[
                "sealed_bootstrap_target_supported"
            ],
            "statistically_supported": evidence_source[
                "statistically_supported"
            ],
            "canonical_adoption_eligible": False,
            "diagnostic_only": False,
        },
        "details": {
            "producer": "protocol_v3_pipeline_final_evaluator",
            "producer_status": "completed_task31_final",
            "source_artifact_ids": sorted(
                {
                    attested.attestation_id,
                    source["checkpoint"]["checkpoint_id"],
                    source_evidence["monthly_quality_report_sha256"],
                }
            ),
            "reason_codes": sorted(set(reasons)),
        },
        "safety": _REPORT_SAFETY,
    }
    return _validate_report_structure(basis)


def open_pipeline_final_report(
    *,
    attestation_path: str | Path,
    repository_root: str | Path,
    source_repository_root: str | Path,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
    progress: PipelineFinalProgress,
    checkpoint: PipelineFinalCheckpoint,
    boundary_plan: Any,
    outer_process: OuterOriginProcess,
    baseline_ledger: OuterMtmLedger,
    joint_stress_ledger: OuterMtmLedger,
    slippage_stress_ledger: OuterMtmLedger,
    monthly_quality_report: MonthlyQualityGateReport,
    stress_identity_evidence: Mapping[str, Any],
    regime_evidence: Mapping[str, Any],
    integrity_evidence: Mapping[str, Any],
    bound_hindsight_benchmarks: BoundHindsightBenchmarks,
    opened_at_utc: str,
) -> PipelineFinalReportOpenResult:
    repo = _repo(repository_root)
    stored = read_pipeline_final_attestation(attestation_path, repo)
    try:
        attested = validate_pipeline_final_attestation(
            stored.to_dict(),
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
            source_repository_root=source_repository_root,
        )
    except PipelineFinalAttestationError as exc:
        raise PipelineFinalReportError(
            "pipeline-final attestation failed transitive revalidation"
        ) from exc
    registration_payload = registration.to_dict()
    manifest = dict(
        _mapping(
            registration_payload["frozen_identity_manifest"],
            "registration.frozen_identity_manifest",
        )
    )
    report = build_pipeline_final_report(
        attested,
        registration,
        created_at_utc=opened_at_utc,
    )
    opened = _utc(opened_at_utc, "opened_at_utc")
    if abs(_utc_now() - opened) > _CLOCK_TOLERANCE:
        raise PipelineFinalReportError(
            "pipeline-final report open timestamp is not current"
        )
    report_root = _safe_root(repo, REPORT_ROOT, create=True)
    receipt_root = _safe_root(repo, OPEN_RECEIPT_ROOT, create=True)
    report_path = report_root / f"{report.report_id}.json"
    receipt_path = receipt_root / f"{attested.to_dict()['registration_sha256']}.json"
    if receipt_path.exists() or receipt_path.is_symlink():
        existing = read_pipeline_final_open_receipt(
            receipt_path,
            repo,
            attestation=attested,
            registration=registration,
            report=report,
        )
        raise PipelineFinalReportAlreadyOpenedError(
            f"pipeline-final report was already opened: {existing.receipt_id}"
        )
    if report_path.exists() or report_path.is_symlink():
        existing_report = read_pipeline_final_report(
            report_path,
            repo,
            attestation=attested,
            registration=registration,
        )
        if existing_report != report:
            raise PipelineFinalReportError(
                "existing pipeline-final report differs from the attestation"
            )
    else:
        _write_create_only(report_path, _bytes(report.canonical_json))
        existing_report = read_pipeline_final_report(
            report_path,
            repo,
            attestation=attested,
            registration=registration,
        )
        if existing_report != report:
            raise PipelineFinalReportError("pipeline-final report reload mismatch")
    receipt = build_pipeline_final_open_receipt(
        attested,
        registration,
        report,
        opened_at_utc=opened_at_utc,
        report_path=report_path.relative_to(repo).as_posix(),
    )
    try:
        _write_create_only(receipt_path, _bytes(receipt.canonical_json))
    except FileExistsError as exc:
        raise PipelineFinalReportAlreadyOpenedError(
            "pipeline-final report open receipt already exists"
        ) from exc
    reloaded_receipt = read_pipeline_final_open_receipt(
        receipt_path,
        repo,
        attestation=attested,
        registration=registration,
        report=report,
    )
    if reloaded_receipt != receipt:
        raise PipelineFinalReportError("pipeline-final open receipt reload mismatch")
    return PipelineFinalReportOpenResult(
        report,
        report_path,
        receipt,
        receipt_path,
    )


def validate_pipeline_final_report(
    value: ProtocolV3Report | Mapping[str, Any],
    *,
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
) -> ProtocolV3Report:
    attested = validate_pipeline_final_attestation(attestation)
    root = value.to_dict() if isinstance(value, ProtocolV3Report) else dict(
        _mapping(value, "pipeline_final_report")
    )
    validated = _validate_report_structure(root)
    expected_report = build_pipeline_final_report(
        attested,
        registration,
        created_at_utc=root["created_at_utc"],
    )
    if validated.to_dict() != expected_report.to_dict():
        raise PipelineFinalReportError(
            "pipeline-final report differs from its Task-31 attestation"
        )
    return validated


def read_pipeline_final_report(
    path: str | Path,
    repository_root: str | Path,
    *,
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
) -> ProtocolV3Report:
    repo = _repo(repository_root)
    root = _safe_root(repo, REPORT_ROOT, create=False)
    guarded = _exact_child(Path(path), root, repo)
    value, raw = _read(guarded, "pipeline-final report")
    report = validate_pipeline_final_report(
        value,
        attestation=attestation,
        registration=registration,
    )
    expected = root / f"{report.report_id}.json"
    if guarded.resolve(strict=True) != expected.resolve(strict=True):
        raise PipelineFinalReportError(
            "pipeline-final report is stored under the wrong path"
        )
    if raw != _bytes(report.canonical_json):
        raise PipelineFinalReportError(
            "pipeline-final report bytes are not canonical"
        )
    return report


def build_pipeline_final_open_receipt(
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
    report: ProtocolV3Report,
    *,
    opened_at_utc: str,
    report_path: str,
) -> PipelineFinalOpenReceipt:
    attested = validate_pipeline_final_attestation(attestation)
    validated_report = validate_pipeline_final_report(
        report,
        attestation=attested,
        registration=registration,
    )
    opened = _utc(opened_at_utc, "opened_at_utc")
    path = PurePosixPath(report_path)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != report_path:
        raise PipelineFinalReportError("pipeline-final report path is unsafe")
    source = attested.to_dict()
    report_payload = validated_report.to_dict()
    basis = {
        "schema_version": OPEN_RECEIPT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": FINAL_REPORT_CONTRACT_VERSION,
        "registration_id": source["registration_id"],
        "registration_sha256": source["registration_sha256"],
        "claim_id": source["claim_id"],
        "claim_sha256": source["claim_sha256"],
        "attestation_id": attested.attestation_id,
        "attestation_sha256": attested.attestation_sha256,
        "report_id": report_payload["report_id"],
        "report_sha256": validated_report.report_sha256,
        "report_path": report_path,
        "opened_at_utc": _fmt(opened),
        "open_count": 1,
        "result_feedback_to_pipeline_allowed": False,
        "safety": _RECEIPT_SAFETY,
    }
    digest = _digest(basis)
    receipt_id = f"protocol_v3_pipeline_final_open_sha256:{digest}"
    root = {
        **basis,
        "receipt_id": receipt_id,
        "receipt_sha256": digest,
    }
    return validate_pipeline_final_open_receipt(
        PipelineFinalOpenReceipt(_canonical(root), digest, receipt_id),
        attestation=attested,
        registration=registration,
        report=validated_report,
    )


def validate_pipeline_final_open_receipt(
    value: PipelineFinalOpenReceipt | Mapping[str, Any],
    *,
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
    report: ProtocolV3Report,
) -> PipelineFinalOpenReceipt:
    source = validate_pipeline_final_attestation(attestation).to_dict()
    validated_report = validate_pipeline_final_report(
        report,
        attestation=attestation,
        registration=registration,
    )
    report_payload = validated_report.to_dict()
    root = value.to_dict() if isinstance(value, PipelineFinalOpenReceipt) else dict(
        _mapping(value, "pipeline_final_open_receipt")
    )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "registration_id",
        "registration_sha256",
        "claim_id",
        "claim_sha256",
        "attestation_id",
        "attestation_sha256",
        "report_id",
        "report_sha256",
        "report_path",
        "opened_at_utc",
        "open_count",
        "result_feedback_to_pipeline_allowed",
        "safety",
        "receipt_id",
        "receipt_sha256",
    }
    if set(root) != required:
        raise PipelineFinalReportError("pipeline-final open receipt fields are invalid")
    if (
        root["schema_version"] != OPEN_RECEIPT_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != FINAL_REPORT_CONTRACT_VERSION
    ):
        raise PipelineFinalReportError(
            "pipeline-final open receipt versions are invalid"
        )
    expected = {
        "registration_id": source["registration_id"],
        "registration_sha256": source["registration_sha256"],
        "claim_id": source["claim_id"],
        "claim_sha256": source["claim_sha256"],
        "attestation_id": attestation.attestation_id,
        "attestation_sha256": attestation.attestation_sha256,
        "report_id": report_payload["report_id"],
        "report_sha256": validated_report.report_sha256,
    }
    if any(root[key] != item for key, item in expected.items()):
        raise PipelineFinalReportError(
            "pipeline-final open receipt identity mismatch"
        )
    _utc(root["opened_at_utc"], "opened_at_utc")
    path = PurePosixPath(root["report_path"])
    if path.is_absolute() or ".." in path.parts:
        raise PipelineFinalReportError("pipeline-final receipt report path is unsafe")
    if (
        root["open_count"] != 1
        or root["result_feedback_to_pipeline_allowed"] is not False
        or root["safety"] != _RECEIPT_SAFETY
    ):
        raise PipelineFinalReportError(
            "pipeline-final open receipt count or safety is invalid"
        )
    observed = _sha(root["receipt_sha256"], "receipt_sha256")
    expected_id = f"protocol_v3_pipeline_final_open_sha256:{observed}"
    if root["receipt_id"] != expected_id:
        raise PipelineFinalReportError("pipeline-final open receipt id mismatch")
    basis = dict(root)
    basis.pop("receipt_id")
    basis.pop("receipt_sha256")
    if observed != _digest(basis):
        raise PipelineFinalReportError("pipeline-final open receipt digest mismatch")
    return PipelineFinalOpenReceipt(_canonical(root), observed, expected_id)


def read_pipeline_final_open_receipt(
    path: str | Path,
    repository_root: str | Path,
    *,
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
    report: ProtocolV3Report,
) -> PipelineFinalOpenReceipt:
    repo = _repo(repository_root)
    root = _safe_root(repo, OPEN_RECEIPT_ROOT, create=False)
    guarded = _exact_child(Path(path), root, repo)
    value, raw = _read(guarded, "pipeline-final open receipt")
    receipt = validate_pipeline_final_open_receipt(
        value,
        attestation=attestation,
        registration=registration,
        report=report,
    )
    expected = root / f"{receipt.to_dict()['registration_sha256']}.json"
    if guarded.resolve(strict=True) != expected.resolve(strict=True):
        raise PipelineFinalReportError(
            "pipeline-final open receipt is stored under the wrong path"
        )
    if raw != _bytes(receipt.canonical_json):
        raise PipelineFinalReportError(
            "pipeline-final open receipt bytes are not canonical"
        )
    return receipt


def _validate_report_structure(value: Mapping[str, Any]) -> ProtocolV3Report:
    root = dict(_mapping(value, "pipeline_final_report"))
    if set(root) != _REPORT_KEYS:
        raise PipelineFinalReportError("pipeline-final report fields are invalid")
    if (
        root["schema_version"] != REPORT_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["artifact_kind"] != PROTOCOL_V3_PIPELINE_FINAL
    ):
        raise PipelineFinalReportError(
            "pipeline-final report schema or artifact kind is invalid"
        )
    _identifier(root["report_id"], "report_id")
    created = _utc(root["created_at_utc"], "created_at_utc")
    if not isinstance(root["run_fingerprint"], str) or not _RUN.fullmatch(
        root["run_fingerprint"]
    ):
        raise PipelineFinalReportError("pipeline-final run fingerprint is invalid")
    if not isinstance(root["pipeline_generation"], str) or not _PIPE.fullmatch(
        root["pipeline_generation"]
    ):
        raise PipelineFinalReportError("pipeline-final pipeline generation is invalid")
    window = dict(_mapping(root["evidence_window"], "evidence_window"))
    if set(window) != _WINDOW_KEYS or window["window_class"] != "sealed_final_holdout":
        raise PipelineFinalReportError("pipeline-final evidence window is invalid")
    _identifier(window["window_id"], "window_id")
    start = _utc(window["start_inclusive_utc"], "evidence_window.start")
    end = _utc(window["end_exclusive_utc"], "evidence_window.end")
    if end - start != timedelta(days=365) or window["calendar_days"] != 365:
        raise PipelineFinalReportError(
            "pipeline-final evidence window must contain 365 UTC days"
        )
    if created < end:
        raise PipelineFinalReportError(
            "pipeline-final report timestamp predates window completion"
        )
    _identifier(window["registration_id"], "registration_id")
    _sha(window["registration_sha256"], "registration_sha256")
    metrics = dict(_mapping(root["metrics"], "metrics"))
    if set(metrics) != _METRIC_KEYS:
        raise PipelineFinalReportError("pipeline-final report metrics are invalid")
    net = _number(metrics["process_oos_net_usdc"], "process_oos_net_usdc")
    if metrics["process_oos_calendar_days"] != 365 or metrics[
        "target_usdc_per_calendar_day"
    ] != 3.0:
        raise PipelineFinalReportError("pipeline-final report metric policy is invalid")
    inputs = dict(_mapping(root["evidence_inputs"], "evidence_inputs"))
    if set(inputs) != _INPUT_KEYS or inputs[
        "historical_bootstrap_attestation_sha256"
    ] is not None:
        raise PipelineFinalReportError("pipeline-final evidence inputs are invalid")
    _sha(inputs["sealed_bootstrap_attestation_sha256"], "sealed bootstrap input")
    _sha(inputs["task31_final_attestation_sha256"], "Task-31 attestation input")
    evidence = dict(_mapping(root["evidence_status"], "evidence_status"))
    if set(evidence) != _STATUS_KEYS:
        raise PipelineFinalReportError("pipeline-final evidence status fields are invalid")
    expected_hit = net / 365 >= 3.0
    if (
        evidence["historically_hit"] is not expected_hit
        or evidence["historical_bootstrap_lower_bound"] is not False
        or evidence["freshness"] != "FRESH_SEALED_FINAL"
        or evidence["fresh_pre_registered_sealed_365"] is not True
        or type(evidence["sealed_bootstrap_target_supported"]) is not bool
        or type(evidence["statistically_supported"]) is not bool
        or evidence["canonical_adoption_eligible"] is not False
        or evidence["diagnostic_only"] is not False
    ):
        raise PipelineFinalReportError(
            "pipeline-final evidence status is invalid or not derived"
        )
    details = dict(_mapping(root["details"], "details"))
    if set(details) != _DETAIL_KEYS:
        raise PipelineFinalReportError("pipeline-final report details are invalid")
    if (
        details["producer"] != "protocol_v3_pipeline_final_evaluator"
        or details["producer_status"] != "completed_task31_final"
        or details["source_artifact_ids"]
        != _strings(details["source_artifact_ids"], "source_artifact_ids")
        or details["reason_codes"]
        != _strings(details["reason_codes"], "reason_codes")
        or root["safety"] != _REPORT_SAFETY
    ):
        raise PipelineFinalReportError(
            "pipeline-final report details or safety are invalid"
        )
    _finite_json(root, "pipeline_final_report")
    canonical = _canonical(root)
    return ProtocolV3Report(canonical, hashlib.sha256(canonical.encode()).hexdigest())


def _report_id(registration_sha256: str) -> str:
    return "pipeline_final_" + _sha(registration_sha256, "registration_sha256")[:24]


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PipelineFinalReportError(f"{name} must be an object")
    return value


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SAFE.fullmatch(value):
        raise PipelineFinalReportError(f"{name} must be a safe identifier")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise PipelineFinalReportError(f"{name} must be lowercase sha256")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineFinalReportError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise PipelineFinalReportError(f"{name} must be a finite number")
    return result


def _decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise PipelineFinalReportError(f"{name} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PipelineFinalReportError(f"{name} must be a finite decimal") from exc
    if not result.is_finite():
        raise PipelineFinalReportError(f"{name} must be a finite decimal")
    return result


def _strings(value: Any, name: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise PipelineFinalReportError(f"{name} must be a string sequence")
    rows: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise PipelineFinalReportError(f"{name} contains an invalid string")
        rows.append(item)
    return sorted(set(rows))


def _finite_json(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PipelineFinalReportError(f"{path} contains a non-string key")
            _finite_json(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _finite_json(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise PipelineFinalReportError(f"{path} contains a non-finite number")
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise PipelineFinalReportError(f"{path} contains unsupported JSON")


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PipelineFinalReportError(f"{name} must be canonical UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PipelineFinalReportError(f"{name} is invalid") from exc
    if parsed.utcoffset() != timedelta(0) or _fmt(parsed) != value:
        raise PipelineFinalReportError(f"{name} is not canonical UTC")
    return parsed.astimezone(UTC)


def _fmt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


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


def _bytes(canonical: str) -> bytes:
    return (canonical + "\n").encode("utf-8")


def _repo(value: str | Path) -> Path:
    path = Path(value)
    if not path.exists() or not path.is_dir() or path.is_symlink():
        raise PipelineFinalReportError(
            "repository_root must be an existing real directory"
        )
    return path.resolve()


def _safe_root(repo: Path, relative_text: str, *, create: bool) -> Path:
    relative = PurePosixPath(relative_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise PipelineFinalReportError("pipeline-final report root is unsafe")
    root = repo.joinpath(*relative.parts)
    _no_symlinks(repo, root)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.exists() or not root.is_dir() or root.is_symlink():
        raise PipelineFinalReportError("pipeline-final report root is missing or unsafe")
    resolved = root.resolve()
    if not is_path_within(resolved, repo):
        raise PipelineFinalReportError("pipeline-final report root escapes repository")
    _no_symlinks(repo, resolved)
    return resolved


def _exact_child(path_value: Path, root: Path, repo: Path) -> Path:
    candidate = path_value if path_value.is_absolute() else repo / path_value
    _no_symlinks(repo, candidate)
    if candidate.is_symlink():
        raise PipelineFinalReportError("pipeline-final path must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PipelineFinalReportError("pipeline-final path is missing") from exc
    if not is_path_within(resolved, root) or resolved.parent != root:
        raise PipelineFinalReportError("pipeline-final path lies outside fixed root")
    return resolved


def _no_symlinks(repo: Path, target: Path) -> None:
    try:
        parts = target.relative_to(repo).parts
    except ValueError as exc:
        raise PipelineFinalReportError("pipeline-final path escapes repository") from exc
    current = repo
    for part in parts:
        current /= part
        if current.exists() and current.is_symlink():
            raise PipelineFinalReportError("symlinked pipeline-final paths are forbidden")


def _write_create_only(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise
    except OSError as exc:
        raise PipelineFinalReportError(f"could not persist pipeline-final JSON: {path}") from exc


def _read(path: Path, name: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineFinalReportError(f"{name} is unreadable or invalid") from exc
    if not isinstance(value, dict):
        raise PipelineFinalReportError(f"{name} must contain one object")
    return value, raw


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "FINAL_REPORT_CONTRACT_VERSION",
    "OPEN_RECEIPT_ROOT",
    "OPEN_RECEIPT_SCHEMA_VERSION",
    "REPORT_ROOT",
    "PipelineFinalOpenReceipt",
    "PipelineFinalReportAlreadyOpenedError",
    "PipelineFinalReportError",
    "PipelineFinalReportOpenResult",
    "build_pipeline_final_open_receipt",
    "build_pipeline_final_report",
    "open_pipeline_final_report",
    "read_pipeline_final_open_receipt",
    "read_pipeline_final_report",
    "validate_pipeline_final_open_receipt",
    "validate_pipeline_final_report",
]
