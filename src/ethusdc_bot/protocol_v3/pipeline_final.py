"""Task-31 preregistration and one-shot claim for a future pipeline final.

This module deliberately does not read final-window market data, run the twelve
origins, calculate PnL, open a report, or grant adoption.  It only establishes
the immutable prerequisites that must exist before a future unseen 365-day
window starts:

* an exact Task-2 boundary plan;
* a complete frozen pipeline identity manifest;
* proof that the window excludes the consumed audit and all already visible
  forward registrations;
* a create-only registration receipt; and
* one create-only evaluation claim that survives every later failure.

The later execution/seal/open layers must consume these receipts.  Legacy
``final_evaluation`` documents and Protocol-v2 runners have no input path here.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Final

from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.protocol_v3.boundaries import (
    BoundaryValidationError,
    MonthlyProcessBoundaryPlan,
    build_monthly_process_boundary_plan,
    validate_monthly_process_boundary_plan,
)
from ethusdc_bot.protocol_v3.pipeline import build_pipeline_generation
from ethusdc_bot.protocol_v3.reporting import (
    FORWARD_REGISTRATION_ROOT,
    read_forward_window_registration,
)
from ethusdc_bot.protocol_v3.run_identity import (
    RunFingerprint,
    RunIdentityError,
    validate_run_fingerprint,
)

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_pipeline_final_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_pipeline_final_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_preregistered_single_open_pipeline_final_v1"
REGISTRATION_SCHEMA_VERSION: Final = "protocol_v3_pipeline_final_registration_v1"
CLAIM_SCHEMA_VERSION: Final = "protocol_v3_pipeline_final_claim_v1"
REGISTRATION_ROOT: Final = "reports/protocol_v3/evidence_windows/pipeline_final"
CLAIM_ROOT: Final = "reports/protocol_v3/pipeline_final_claims"
WINDOW_CLASS: Final = "sealed_final_holdout"
CONSUMED_AUDIT_START: Final = datetime(2025, 7, 8, tzinfo=UTC)
CONSUMED_AUDIT_END_EXCLUSIVE: Final = datetime(2026, 7, 8, tzinfo=UTC)
_CLOCK_TOLERANCE: Final = timedelta(minutes=5)
_ZERO_HASH: Final = "0" * 64
_HEX = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PIPE = re.compile(r"^protocol_v3_pipeline_sha256:[0-9a-f]{64}$")
_RUN = re.compile(r"^protocol_v3_run_sha256:[0-9a-f]{64}$")
_CLAIM_ID = re.compile(r"^protocol_v3_pipeline_final_claim_sha256:[0-9a-f]{64}$")
_SAFETY: Final = {
    "api_keys": "forbidden",
    "canonical_adoption": "locked",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_IDENTITY_FIELDS: Final = (
    "bootstrap_contract_sha256",
    "boundary_plan_sha256",
    "code_commit",
    "context_contract_sha256",
    "cost_contract_sha256",
    "data_contract_sha256",
    "exchange_info_contract_sha256",
    "execution_contract_sha256",
    "feature_contract_sha256",
    "pipeline_contract_sha256",
    "pipeline_generation_id",
    "quality_gate_contract_sha256",
    "report_contract_sha256",
    "run_fingerprint",
    "search_budget_sha256",
    "seed_policy_sha256",
    "simulator_contract_sha256",
    "stop_policy_sha256",
    "trial_ledger_head_sha256",
)
_IDENTITY_SOURCE_GROUPS: Final = {
    "bootstrap": (
        "configs/protocol_v3_historical_diagnostics_contract.json",
    ),
    "context": (
        "configs/protocol_v3_context_parity_contract.json",
        "configs/protocol_v3_data_snapshot_contract.json",
    ),
    "cost": (
        "configs/protocol_v3_execution_parity_contract.json",
        "configs/protocol_v3_intrabar_execution_contract.json",
    ),
    "data": (
        "configs/protocol_v3_data_snapshot_contract.json",
    ),
    "exchange_info": (
        "configs/protocol_v3_run_identity_contract.json",
    ),
    "execution": (
        "configs/protocol_v3_execution_parity_contract.json",
        "configs/protocol_v3_intrabar_execution_contract.json",
        "configs/protocol_v3_runtime_state_contract.json",
    ),
    "feature": (
        "configs/protocol_v3_data_snapshot_contract.json",
        "configs/protocol_v3_feature_store_contract.json",
        "configs/protocol_v3_opportunity_regime_contract.json",
    ),
    "quality_gate": (
        "configs/protocol_v3_historical_diagnostics_contract.json",
        "configs/protocol_v3_monthly_quality_gate_contract.json",
        "configs/protocol_v3_pipeline_final_contract.json",
        "configs/protocol_v3_pipeline_final_progress_contract.json",
        "configs/protocol_v3_report_contract.json",
        "configs/protocol_v3_transaction_contract.json",
    ),
    "report": (
        "configs/protocol_v3_report_contract.json",
    ),
    "simulator": (
        "configs/protocol_v3_context_parity_contract.json",
        "configs/protocol_v3_execution_parity_contract.json",
        "configs/protocol_v3_intrabar_execution_contract.json",
        "configs/protocol_v3_runtime_state_contract.json",
    ),
}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "registration_schema_version": REGISTRATION_SCHEMA_VERSION,
    "claim_schema_version": CLAIM_SCHEMA_VERSION,
    "roots": {
        "registration_root": REGISTRATION_ROOT,
        "claim_root": CLAIM_ROOT,
    },
    "window_policy": {
        "window_class": WINDOW_CLASS,
        "calendar_days": 365,
        "outer_origins": 12,
        "training_days_per_origin": 730,
        "activation_delay_hours": 24,
        "registration_must_precede_window": True,
        "registration_timestamp_must_be_current": True,
        "consumed_audit_overlap_forbidden": True,
        "visible_forward_month_overlap_forbidden": True,
        "exact_task2_boundary_plan_required": True,
    },
    "identity_policy": {
        "exact_identity_fields_required": True,
        "caller_digest_claims_recomputed": True,
        "required_fields": list(_IDENTITY_FIELDS),
    },
    "claim_policy": {
        "create_only": True,
        "exactly_one_evaluation_attempt": True,
        "claim_must_precede_window": True,
        "claim_survives_failure": True,
        "retry_after_claim_forbidden": True,
        "result_opened_at_claim": False,
    },
    "sealing_policy": {
        "intermediate_outer_pnl_visible": False,
        "intermediate_rankings_visible": False,
        "intermediate_strategy_switches_visible": False,
        "final_report_artifact_kind": "protocol_v3_pipeline_final",
        "task31_attestation_required_before_open": True,
        "open_exactly_once_after_complete": True,
    },
    "legacy_separation": {
        "legacy_report_type_forbidden": "final_evaluation",
        "protocol_v2_may_claim_task31": False,
        "single_candidate_runner_may_claim_task31": False,
        "task27_task28_task29_evidence_may_claim_freshness": False,
    },
    "safety": _SAFETY,
}


class PipelineFinalError(ValueError):
    """Raised when a future pipeline-final prerequisite fails closed."""


class PipelineFinalAlreadyClaimedError(PipelineFinalError):
    """Raised when a registration already owns its single evaluation claim."""


@dataclass(frozen=True)
class PipelineFinalRegistration:
    canonical_json: str
    registration_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


@dataclass(frozen=True)
class PipelineFinalClaim:
    canonical_json: str
    claim_sha256: str
    claim_id: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def load_pipeline_final_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = _strict_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineFinalError("pipeline-final contract is missing or invalid") from exc
    validate_pipeline_final_contract(value)
    return value


def validate_pipeline_final_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize(value) != _CANONICAL_CONTRACT:
        raise PipelineFinalError("pipeline-final contract is not canonical")


def pipeline_final_boundary_plan(
    *, start_inclusive_utc: str, end_exclusive_utc: str
) -> MonthlyProcessBoundaryPlan:
    start = _utc(start_inclusive_utc, "start_inclusive_utc")
    end = _utc(end_exclusive_utc, "end_exclusive_utc")
    _midnight(start, "start_inclusive_utc")
    _midnight(end, "end_exclusive_utc")
    if end - start != timedelta(days=365):
        raise PipelineFinalError("pipeline-final window must contain exactly 365 UTC days")
    try:
        plan = build_monthly_process_boundary_plan(end.date())
        validate_monthly_process_boundary_plan(plan)
    except BoundaryValidationError as exc:
        raise PipelineFinalError(
            "pipeline-final window is not an exact Task-2 boundary plan"
        ) from exc
    if plan.process_start_inclusive != start.date():
        raise PipelineFinalError("pipeline-final window differs from the exact Task-2 boundary plan")
    return plan


def pipeline_final_boundary_plan_payload(plan: MonthlyProcessBoundaryPlan) -> dict[str, Any]:
    validate_monthly_process_boundary_plan(plan)
    return {
        "process_start_inclusive": plan.process_start_inclusive.isoformat(),
        "process_end_exclusive": plan.process_end_exclusive.isoformat(),
        "boundary_dates": [item.isoformat() for item in plan.boundary_dates],
        "origin_count": len(plan.origins),
        "process_oos_days": plan.process_oos_days,
        "training_days_per_origin": plan.training_days_per_origin,
        "activation_delay_hours": plan.activation_delay_hours,
        "origins": [
            {
                "origin_index": origin.origin_index,
                "target_anchor": origin.target_anchor.isoformat(),
                "training_start_inclusive": origin.training_start_inclusive.isoformat(),
                "training_end_exclusive": origin.training_end_exclusive.isoformat(),
                "test_start_inclusive": origin.test_start_inclusive.isoformat(),
                "test_end_exclusive": origin.test_end_exclusive.isoformat(),
                "valid_from": _fmt(origin.valid_from),
                "valid_until": _fmt(origin.valid_until),
                "entry_enabled_at": _fmt(origin.entry_enabled_at),
            }
            for origin in plan.origins
        ],
    }


def pipeline_final_boundary_plan_sha256(plan: MonthlyProcessBoundaryPlan) -> str:
    return _digest(pipeline_final_boundary_plan_payload(plan))


def visible_forward_registration_head(repository_root: str | Path) -> str:
    rows = _visible_forward_registrations(repository_root)
    return _digest(rows)


def build_pipeline_final_identity_manifest(
    *,
    repository_root: str | Path,
    boundary_plan: MonthlyProcessBoundaryPlan,
    run_fingerprint: RunFingerprint | Mapping[str, Any],
) -> dict[str, str]:
    """Recompute every frozen Task-31 identity from typed runtime evidence."""

    repo = _repo(repository_root)
    validate_monthly_process_boundary_plan(boundary_plan)
    run = _validated_run_fingerprint_payload(run_fingerprint, repo)
    generation = build_pipeline_generation(repo)
    pipeline = dict(_mapping(run["pipeline"], "run_fingerprint.pipeline"))
    if (
        pipeline.get("generation_id") != generation.generation_id
        or pipeline.get("contract_sha256") != generation.contract_sha256
    ):
        raise PipelineFinalError(
            "run fingerprint differs from the current pipeline generation"
        )
    pipeline_contract_path = repo / "configs/protocol_v3_pipeline_contract.json"
    try:
        pipeline_contract = _strict_load(
            pipeline_contract_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineFinalError(
            "pipeline contract is missing during final identity derivation"
        ) from exc
    for key in ("budget_policy", "seed_policy", "stop_policy"):
        _mapping(pipeline_contract.get(key), f"pipeline_contract.{key}")
    trial = dict(
        _mapping(run["trial_ledger_head"], "run_fingerprint.trial_ledger_head")
    )
    code = dict(_mapping(run["code"], "run_fingerprint.code"))
    manifest = {
        "bootstrap_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["bootstrap"]
        ),
        "boundary_plan_sha256": pipeline_final_boundary_plan_sha256(boundary_plan),
        "code_commit": code["git_commit"],
        "context_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["context"]
        ),
        "cost_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["cost"]
        ),
        "data_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["data"]
        ),
        "exchange_info_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["exchange_info"]
        ),
        "execution_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["execution"]
        ),
        "feature_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["feature"]
        ),
        "pipeline_contract_sha256": generation.contract_sha256,
        "pipeline_generation_id": generation.generation_id,
        "quality_gate_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["quality_gate"]
        ),
        "report_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["report"]
        ),
        "run_fingerprint": "protocol_v3_run_sha256:" + run["fingerprint_sha256"],
        "search_budget_sha256": _digest(pipeline_contract["budget_policy"]),
        "seed_policy_sha256": _digest(pipeline_contract["seed_policy"]),
        "simulator_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["simulator"]
        ),
        "stop_policy_sha256": _digest(pipeline_contract["stop_policy"]),
        "trial_ledger_head_sha256": trial["head_sha256"],
    }
    return _identity_manifest(manifest)


def validate_pipeline_final_identity_manifest_against_repository(
    value: Mapping[str, Any],
    *,
    repository_root: str | Path,
    boundary_plan: MonthlyProcessBoundaryPlan,
    run_fingerprint: RunFingerprint | Mapping[str, Any],
) -> dict[str, str]:
    observed = _identity_manifest(value)
    expected = build_pipeline_final_identity_manifest(
        repository_root=repository_root,
        boundary_plan=boundary_plan,
        run_fingerprint=run_fingerprint,
    )
    if observed != expected:
        raise PipelineFinalError(
            "frozen pipeline-final identity manifest differs from repository truth"
        )
    return observed


def _validated_run_fingerprint_payload(
    value: RunFingerprint | Mapping[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    if isinstance(value, RunFingerprint):
        payload = value.to_dict()
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        raise PipelineFinalError("validated run fingerprint is required")
    try:
        validate_run_fingerprint(payload, repo_root=repository_root)
    except RunIdentityError as exc:
        raise PipelineFinalError(
            "run fingerprint failed repository revalidation"
        ) from exc
    return payload


def _source_group_sha256(repo: Path, relative_paths: Sequence[str]) -> str:
    rows: list[dict[str, str]] = []
    for relative_text in relative_paths:
        relative = PurePosixPath(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise PipelineFinalError("final identity source path is unsafe")
        path = repo.joinpath(*relative.parts)
        _no_symlinks(repo, path)
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise PipelineFinalError(
                f"final identity source is missing or unsafe: {relative_text}"
            )
        rows.append(
            {
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return _digest(rows)


def build_pipeline_final_registration(
    *,
    registration_id: str,
    registered_at_utc: str,
    start_inclusive_utc: str,
    end_exclusive_utc: str,
    frozen_identity_manifest: Mapping[str, Any],
    visible_forward_registration_head_sha256: str,
) -> PipelineFinalRegistration:
    _identifier(registration_id, "registration_id")
    registered = _utc(registered_at_utc, "registered_at_utc")
    start = _utc(start_inclusive_utc, "start_inclusive_utc")
    end = _utc(end_exclusive_utc, "end_exclusive_utc")
    if registered >= start:
        raise PipelineFinalError("pipeline-final registration must precede the window start")
    plan = pipeline_final_boundary_plan(
        start_inclusive_utc=start_inclusive_utc,
        end_exclusive_utc=end_exclusive_utc,
    )
    if _overlaps(start, end, CONSUMED_AUDIT_START, CONSUMED_AUDIT_END_EXCLUSIVE):
        raise PipelineFinalError("pipeline-final window overlaps the consumed audit")
    identity = _identity_manifest(frozen_identity_manifest)
    plan_sha = pipeline_final_boundary_plan_sha256(plan)
    if identity["boundary_plan_sha256"] != plan_sha:
        raise PipelineFinalError("frozen boundary identity differs from the exact Task-2 plan")
    visible_head = _sha(
        visible_forward_registration_head_sha256,
        "visible_forward_registration_head_sha256",
    )
    basis = {
        "schema_version": REGISTRATION_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "registration_id": registration_id,
        "registered_at_utc": _fmt(registered),
        "window_class": WINDOW_CLASS,
        "start_inclusive_utc": _fmt(start),
        "end_exclusive_utc": _fmt(end),
        "calendar_days": 365,
        "boundary_plan": pipeline_final_boundary_plan_payload(plan),
        "boundary_plan_sha256": plan_sha,
        "frozen_identity_manifest": identity,
        "frozen_identity_manifest_sha256": _digest(identity),
        "visible_forward_registration_head_sha256": visible_head,
        "consumed_audit_overlap": False,
        "visible_forward_overlap": False,
        "evaluation_attempt_limit": 1,
        "intermediate_results_visible": False,
        "safety": _SAFETY,
    }
    return validate_pipeline_final_registration(
        {**basis, "registration_sha256": _digest(basis)}
    )


def validate_pipeline_final_registration(
    value: PipelineFinalRegistration | Mapping[str, Any],
) -> PipelineFinalRegistration:
    root = (
        value.to_dict()
        if isinstance(value, PipelineFinalRegistration)
        else dict(_mapping(value, "pipeline_final_registration"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "registration_id",
        "registered_at_utc",
        "window_class",
        "start_inclusive_utc",
        "end_exclusive_utc",
        "calendar_days",
        "boundary_plan",
        "boundary_plan_sha256",
        "frozen_identity_manifest",
        "frozen_identity_manifest_sha256",
        "visible_forward_registration_head_sha256",
        "consumed_audit_overlap",
        "visible_forward_overlap",
        "evaluation_attempt_limit",
        "intermediate_results_visible",
        "safety",
        "registration_sha256",
    }
    if set(root) != required:
        raise PipelineFinalError("pipeline-final registration fields are invalid")
    if (
        root["schema_version"] != REGISTRATION_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
        or root["window_class"] != WINDOW_CLASS
    ):
        raise PipelineFinalError("pipeline-final registration version or class is invalid")
    _identifier(root["registration_id"], "registration_id")
    registered = _utc(root["registered_at_utc"], "registered_at_utc")
    start = _utc(root["start_inclusive_utc"], "start_inclusive_utc")
    end = _utc(root["end_exclusive_utc"], "end_exclusive_utc")
    if registered >= start:
        raise PipelineFinalError("pipeline-final registration must precede the window start")
    if root["calendar_days"] != 365 or type(root["calendar_days"]) is not int:
        raise PipelineFinalError("pipeline-final calendar_days must equal 365")
    plan = pipeline_final_boundary_plan(
        start_inclusive_utc=root["start_inclusive_utc"],
        end_exclusive_utc=root["end_exclusive_utc"],
    )
    expected_plan = pipeline_final_boundary_plan_payload(plan)
    if root["boundary_plan"] != expected_plan:
        raise PipelineFinalError("embedded boundary plan is not canonical")
    plan_sha = pipeline_final_boundary_plan_sha256(plan)
    if root["boundary_plan_sha256"] != plan_sha:
        raise PipelineFinalError("embedded boundary plan digest mismatch")
    identity = _identity_manifest(root["frozen_identity_manifest"])
    if (
        root["frozen_identity_manifest"] != identity
        or root["frozen_identity_manifest_sha256"] != _digest(identity)
        or identity["boundary_plan_sha256"] != plan_sha
    ):
        raise PipelineFinalError("pipeline-final frozen identity manifest is invalid")
    _sha(
        root["visible_forward_registration_head_sha256"],
        "visible_forward_registration_head_sha256",
    )
    if (
        root["consumed_audit_overlap"] is not False
        or root["visible_forward_overlap"] is not False
        or root["evaluation_attempt_limit"] != 1
        or type(root["evaluation_attempt_limit"]) is not int
        or root["intermediate_results_visible"] is not False
        or root["safety"] != _SAFETY
    ):
        raise PipelineFinalError("pipeline-final registration safety or sealing policy is invalid")
    if _overlaps(start, end, CONSUMED_AUDIT_START, CONSUMED_AUDIT_END_EXCLUSIVE):
        raise PipelineFinalError("pipeline-final window overlaps the consumed audit")
    observed = _sha(root["registration_sha256"], "registration_sha256")
    basis = dict(root)
    basis.pop("registration_sha256")
    if observed != _digest(basis):
        raise PipelineFinalError("pipeline-final registration digest mismatch")
    return PipelineFinalRegistration(_canonical(root), observed)


def write_pipeline_final_registration(
    registration: PipelineFinalRegistration,
    repository_root: str | Path,
) -> Path:
    if not isinstance(registration, PipelineFinalRegistration):
        raise PipelineFinalError("validated PipelineFinalRegistration required")
    validated = validate_pipeline_final_registration(registration)
    payload = validated.to_dict()
    now = _utc_now()
    registered = _utc(payload["registered_at_utc"], "registered_at_utc")
    start = _utc(payload["start_inclusive_utc"], "start_inclusive_utc")
    if now >= start:
        raise PipelineFinalError("pipeline-final registration must be persisted before start")
    if abs(now - registered) > _CLOCK_TOLERANCE:
        raise PipelineFinalError("pipeline-final registration timestamp is not current")
    rows = _visible_forward_registrations(repository_root)
    current_head = _digest(rows)
    if current_head != payload["visible_forward_registration_head_sha256"]:
        raise PipelineFinalError("visible forward registration head changed before persistence")
    _assert_no_forward_overlap(payload, rows)
    repo = _repo(repository_root)
    root = _safe_root(repo, REGISTRATION_ROOT, create=True)
    path = root / f"{payload['registration_id']}.json"
    try:
        _write_create_only(path, _bytes(validated.canonical_json))
    except FileExistsError as exc:
        raise PipelineFinalError("pipeline-final registration id already exists") from exc
    reloaded = read_pipeline_final_registration(path, repo)
    if reloaded != validated:
        raise PipelineFinalError("pipeline-final registration reload mismatch")
    return path


def read_pipeline_final_registration(
    path: str | Path,
    repository_root: str | Path,
) -> PipelineFinalRegistration:
    repo = _repo(repository_root)
    root = _safe_root(repo, REGISTRATION_ROOT, create=False)
    guarded = _exact_child(Path(path), root, repo)
    value, raw = _read(guarded)
    registration = validate_pipeline_final_registration(value)
    expected = root / f"{registration.to_dict()['registration_id']}.json"
    if guarded.resolve(strict=True) != expected.resolve(strict=True):
        raise PipelineFinalError("pipeline-final registration is stored under the wrong path")
    if raw != _bytes(registration.canonical_json):
        raise PipelineFinalError("pipeline-final registration bytes are not canonical")
    return registration


def claim_pipeline_final_evaluation(
    registration_path: str | Path,
    repository_root: str | Path,
    *,
    claimed_at_utc: str,
) -> PipelineFinalClaim:
    repo = _repo(repository_root)
    registration = read_pipeline_final_registration(registration_path, repo)
    payload = registration.to_dict()
    claimed = _utc(claimed_at_utc, "claimed_at_utc")
    registered = _utc(payload["registered_at_utc"], "registered_at_utc")
    start = _utc(payload["start_inclusive_utc"], "start_inclusive_utc")
    now = _utc_now()
    if claimed < registered:
        raise PipelineFinalError("pipeline-final claim cannot predate registration")
    if claimed >= start or now >= start:
        raise PipelineFinalError("pipeline-final claim must be persisted before window start")
    if abs(now - claimed) > _CLOCK_TOLERANCE:
        raise PipelineFinalError("pipeline-final claim timestamp is not current")
    rows = _visible_forward_registrations(repo)
    if _digest(rows) != payload["visible_forward_registration_head_sha256"]:
        raise PipelineFinalError("visible forward registration head changed after preregistration")
    _assert_no_forward_overlap(payload, rows)
    basis = {
        "schema_version": CLAIM_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "registration_id": payload["registration_id"],
        "registration_sha256": registration.registration_sha256,
        "claimed_at_utc": _fmt(claimed),
        "evaluation_attempt": 1,
        "status": "CLAIMED_BEFORE_WINDOW",
        "result_opened": False,
        "retry_allowed": False,
        "claim_survives_failure": True,
        "intermediate_results_visible": False,
        "safety": _SAFETY,
    }
    claim_sha = _digest(basis)
    claim = validate_pipeline_final_claim(
        {
            **basis,
            "claim_id": f"protocol_v3_pipeline_final_claim_sha256:{claim_sha}",
            "claim_sha256": claim_sha,
        }
    )
    root = _safe_root(repo, CLAIM_ROOT, create=True)
    path = root / f"{registration.registration_sha256}.json"
    try:
        _write_create_only(path, _bytes(claim.canonical_json))
    except FileExistsError as exc:
        raise PipelineFinalAlreadyClaimedError(
            "pipeline-final registration already has its single evaluation claim"
        ) from exc
    reloaded = read_pipeline_final_claim(path, repo)
    if reloaded != claim:
        raise PipelineFinalError("pipeline-final claim reload mismatch")
    return claim


def validate_pipeline_final_claim(
    value: PipelineFinalClaim | Mapping[str, Any],
) -> PipelineFinalClaim:
    root = (
        value.to_dict()
        if isinstance(value, PipelineFinalClaim)
        else dict(_mapping(value, "pipeline_final_claim"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "registration_id",
        "registration_sha256",
        "claimed_at_utc",
        "evaluation_attempt",
        "status",
        "result_opened",
        "retry_allowed",
        "claim_survives_failure",
        "intermediate_results_visible",
        "safety",
        "claim_id",
        "claim_sha256",
    }
    if set(root) != required:
        raise PipelineFinalError("pipeline-final claim fields are invalid")
    if (
        root["schema_version"] != CLAIM_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
    ):
        raise PipelineFinalError("pipeline-final claim version is invalid")
    _identifier(root["registration_id"], "registration_id")
    _sha(root["registration_sha256"], "registration_sha256")
    _utc(root["claimed_at_utc"], "claimed_at_utc")
    if (
        root["evaluation_attempt"] != 1
        or type(root["evaluation_attempt"]) is not int
        or root["status"] != "CLAIMED_BEFORE_WINDOW"
        or root["result_opened"] is not False
        or root["retry_allowed"] is not False
        or root["claim_survives_failure"] is not True
        or root["intermediate_results_visible"] is not False
        or root["safety"] != _SAFETY
    ):
        raise PipelineFinalError("pipeline-final claim contradicts one-shot sealing policy")
    observed = _sha(root["claim_sha256"], "claim_sha256")
    if not isinstance(root["claim_id"], str) or not _CLAIM_ID.fullmatch(root["claim_id"]):
        raise PipelineFinalError("pipeline-final claim_id is invalid")
    if root["claim_id"] != f"protocol_v3_pipeline_final_claim_sha256:{observed}":
        raise PipelineFinalError("pipeline-final claim_id does not match its digest")
    basis = dict(root)
    basis.pop("claim_id")
    basis.pop("claim_sha256")
    if observed != _digest(basis):
        raise PipelineFinalError("pipeline-final claim digest mismatch")
    return PipelineFinalClaim(_canonical(root), observed, root["claim_id"])


def read_pipeline_final_claim(
    path: str | Path,
    repository_root: str | Path,
) -> PipelineFinalClaim:
    repo = _repo(repository_root)
    root = _safe_root(repo, CLAIM_ROOT, create=False)
    guarded = _exact_child(Path(path), root, repo)
    value, raw = _read(guarded)
    claim = validate_pipeline_final_claim(value)
    expected = root / f"{claim.to_dict()['registration_sha256']}.json"
    if guarded.resolve(strict=True) != expected.resolve(strict=True):
        raise PipelineFinalError("pipeline-final claim is stored under the wrong path")
    if raw != _bytes(claim.canonical_json):
        raise PipelineFinalError("pipeline-final claim bytes are not canonical")
    return claim


def _identity_manifest(value: Mapping[str, Any]) -> dict[str, str]:
    root = dict(_mapping(value, "frozen_identity_manifest"))
    if set(root) != set(_IDENTITY_FIELDS):
        raise PipelineFinalError("frozen identity manifest fields are incomplete or unexpected")
    normalized: dict[str, str] = {}
    for key in _IDENTITY_FIELDS:
        raw = root[key]
        if key == "code_commit":
            if not isinstance(raw, str) or not _COMMIT.fullmatch(raw):
                raise PipelineFinalError("frozen identity code_commit is invalid")
        elif key == "pipeline_generation_id":
            if not isinstance(raw, str) or not _PIPE.fullmatch(raw):
                raise PipelineFinalError("frozen pipeline_generation_id is invalid")
        elif key == "run_fingerprint":
            if not isinstance(raw, str) or not _RUN.fullmatch(raw):
                raise PipelineFinalError("frozen run_fingerprint is invalid")
        else:
            _sha(raw, key)
        normalized[key] = raw
    return normalized


def _visible_forward_registrations(repository_root: str | Path) -> list[dict[str, Any]]:
    repo = _repo(repository_root)
    relative = PurePosixPath(FORWARD_REGISTRATION_ROOT)
    root = repo.joinpath(*relative.parts)
    _no_symlinks(repo, root)
    if not root.exists():
        return []
    if not root.is_dir() or root.is_symlink():
        raise PipelineFinalError("forward registration root is unsafe")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise PipelineFinalError("forward registration root contains an unsafe entry")
        registration = read_forward_window_registration(path, repo)
        payload = registration.to_dict()
        rows.append(
            {
                "registration_id": payload["registration_id"],
                "registration_sha256": registration.registration_sha256,
                "start_inclusive_utc": payload["start_inclusive_utc"],
                "end_exclusive_utc": payload["end_exclusive_utc"],
                "pipeline_generation": payload["pipeline_generation"],
                "run_fingerprint": payload["run_fingerprint"],
            }
        )
    return rows


def _assert_no_forward_overlap(
    registration: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> None:
    start = _utc(registration["start_inclusive_utc"], "start_inclusive_utc")
    end = _utc(registration["end_exclusive_utc"], "end_exclusive_utc")
    for row in rows:
        forward_start = _utc(row["start_inclusive_utc"], "forward.start")
        forward_end = _utc(row["end_exclusive_utc"], "forward.end")
        if _overlaps(start, end, forward_start, forward_end):
            raise PipelineFinalError(
                "pipeline-final window overlaps an already visible forward month"
            )


def _overlaps(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> bool:
    return start < other_end and other_start < end


def _repo(value: str | Path) -> Path:
    path = Path(value)
    if not path.exists() or not path.is_dir() or path.is_symlink():
        raise PipelineFinalError("repository_root must be an existing real directory")
    return path.resolve()


def _safe_root(repo: Path, relative_text: str, *, create: bool) -> Path:
    relative = PurePosixPath(relative_text)
    if relative.is_absolute() or ".." in relative.parts:
        raise PipelineFinalError("pipeline-final storage root must be repository-relative")
    root = repo.joinpath(*relative.parts)
    _no_symlinks(repo, root)
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if not root.exists() or not root.is_dir() or root.is_symlink():
        raise PipelineFinalError("pipeline-final storage root is missing or unsafe")
    resolved = root.resolve()
    if not is_path_within(resolved, repo):
        raise PipelineFinalError("pipeline-final storage root escapes repository_root")
    _no_symlinks(repo, resolved)
    return resolved


def _exact_child(path_value: Path, root: Path, repo: Path) -> Path:
    candidate = path_value if path_value.is_absolute() else repo / path_value
    _no_symlinks(repo, candidate)
    if candidate.is_symlink():
        raise PipelineFinalError("pipeline-final path must not be a symlink")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PipelineFinalError("pipeline-final path is missing or unreadable") from exc
    if not is_path_within(resolved, root) or resolved.parent != root:
        raise PipelineFinalError("pipeline-final path lies outside its fixed root")
    return resolved


def _no_symlinks(repo: Path, target: Path) -> None:
    try:
        parts = target.relative_to(repo).parts
    except ValueError as exc:
        raise PipelineFinalError("pipeline-final path escapes repository_root") from exc
    current = repo
    for part in parts:
        current /= part
        if current.exists() and current.is_symlink():
            raise PipelineFinalError("symlinked pipeline-final paths are forbidden")


def _write_create_only(path: Path, raw: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_dir(path.parent)
    except FileExistsError:
        raise
    except OSError as exc:
        raise PipelineFinalError(f"could not persist pipeline-final JSON: {path}") from exc


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = _strict_load(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineFinalError(f"pipeline-final JSON is unreadable or invalid: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineFinalError("pipeline-final JSON must contain one object")
    return value, raw


def _strict_load(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise PipelineFinalError(f"duplicate pipeline-final JSON key: {key}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise PipelineFinalError(f"non-finite pipeline-final JSON constant: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PipelineFinalError(f"{name} must be an object")
    return value


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SAFE.fullmatch(value):
        raise PipelineFinalError(f"{name} must be a safe identifier")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise PipelineFinalError(f"{name} must be lowercase sha256")
    return value


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PipelineFinalError(f"{name} must be canonical UTC text")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PipelineFinalError(f"{name} is invalid") from exc
    if parsed.utcoffset() != timedelta(0) or _fmt(parsed) != value:
        raise PipelineFinalError(f"{name} is not canonically serialized")
    return parsed.astimezone(UTC)


def _midnight(value: datetime, name: str) -> None:
    if any((value.hour, value.minute, value.second, value.microsecond)):
        raise PipelineFinalError(f"{name} must be UTC midnight")


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


def _bytes(value: str) -> bytes:
    return value.encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _normalize(value: Any) -> Any:
    return json.loads(_canonical(value))


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "CLAIM_ROOT",
    "CLAIM_SCHEMA_VERSION",
    "CONTRACT_PATH",
    "CONTRACT_VERSION",
    "PipelineFinalAlreadyClaimedError",
    "PipelineFinalClaim",
    "PipelineFinalError",
    "PipelineFinalRegistration",
    "REGISTRATION_ROOT",
    "REGISTRATION_SCHEMA_VERSION",
    "build_pipeline_final_identity_manifest",
    "build_pipeline_final_registration",
    "claim_pipeline_final_evaluation",
    "load_pipeline_final_contract",
    "pipeline_final_boundary_plan",
    "pipeline_final_boundary_plan_payload",
    "pipeline_final_boundary_plan_sha256",
    "read_pipeline_final_claim",
    "read_pipeline_final_registration",
    "validate_pipeline_final_claim",
    "validate_pipeline_final_contract",
    "validate_pipeline_final_identity_manifest_against_repository",
    "validate_pipeline_final_registration",
    "visible_forward_registration_head",
    "write_pipeline_final_registration",
]
