"""Fail-closed real-data preflight and blocker evidence for Protocol-v3 Task 33."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Final

from .production_runtime import (
    ProductionRuntimeError,
    build_task33_runtime_inputs,
)

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_task33_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_task33_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_real_research_preflight_and_blocker_report_v1"
REPORT_SCHEMA_VERSION: Final = "protocol_v3_task33_preflight_report_v1"
READY = "READY_FOR_FULL_RESEARCH_RUN"
BLOCKED_HISTORY = "BLOCKED_INSUFFICIENT_TRIAL_HISTORY"
BLOCKED_INPUTS = "BLOCKED_MISSING_FROZEN_RUNTIME_INPUTS"
_HEX = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_PIPELINE = re.compile(r"^protocol_v3_pipeline_sha256:[0-9a-f]{64}$")
_RESULT_FIELDS: Final = (
    "tested_candidates", "valid_candidates", "router_setups",
    "router_trade_signals", "engine_entry_attempts", "trades",
    "net_usdc_per_calendar_day", "total_profit_usdc", "fees_usdc",
    "slippage_usdc", "max_drawdown_usdc", "win_rate", "profit_factor",
    "active_days", "no_trade_days", "monthly_gate", "stress_gate", "dsr",
    "pbo", "hindsight_capture", "bootstrap_support",
)
_SAFETY: Final = {
    "api_keys": "forbidden", "canonical_adoption": "locked", "live": "locked",
    "orders": "locked", "paper": "locked", "testtrade": "locked",
    "trading_api": "forbidden",
}


class Task33PreflightError(ValueError):
    """Raised when Task-33 evidence is malformed, incomplete, or unsafe."""


@dataclass(frozen=True)
class Task33PreflightReport:
    canonical_json: str
    report_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


def load_task33_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve() / CONTRACT_PATH
    try:
        value = _strict_json(path.read_text(encoding="utf-8"), "Task-33 contract")
    except (OSError, UnicodeError) as exc:
        raise Task33PreflightError("Task-33 contract is unreadable") from exc
    if not isinstance(value, dict):
        raise Task33PreflightError("Task-33 contract must be an object")
    validate_task33_contract(value)
    return value


def validate_task33_contract(value: Mapping[str, Any]) -> None:
    if dict(value) != _canonical_contract():
        raise Task33PreflightError("Task-33 contract is not canonical")


def build_task33_preflight_report(
    *,
    repo_root: str | Path,
    run_id: str,
    created_at_utc: str,
    code_commit: str,
    pipeline_generation_id: str,
    data_snapshot: Mapping[str, Any],
    exchange_info_snapshot: Mapping[str, Any],
    trial_ledger_status: Mapping[str, Any],
    runtime_inputs: Mapping[str, Any],
) -> Task33PreflightReport:
    """Build evidence that either authorizes the real run or names its first blocker."""
    load_task33_contract(repo_root)
    _text(run_id, "run_id")
    _text(created_at_utc, "created_at_utc")
    if not _COMMIT.fullmatch(code_commit):
        raise Task33PreflightError("code_commit must be a full lowercase git SHA")
    if not _PIPELINE.fullmatch(pipeline_generation_id):
        raise Task33PreflightError("pipeline_generation_id is invalid")
    data = _mapping(data_snapshot, "data_snapshot")
    exchange = _mapping(exchange_info_snapshot, "exchange_info_snapshot")
    ledger = _mapping(trial_ledger_status, "trial_ledger_status")
    inputs = _mapping(runtime_inputs, "runtime_inputs")
    _require_digest(data.get("snapshot_sha256"), "data snapshot")
    _require_digest(exchange.get("snapshot_sha256"), "exchange-info snapshot")
    _require_digest(ledger.get("head_sha256"), "trial-ledger head")

    missing = _missing_runtime_inputs(inputs, repo_root=repo_root)
    history_blocked = (
        ledger.get("development_dsr_status") == "INSUFFICIENT_TRIAL_HISTORY"
        or ledger.get("only_release_decision_allowed") == "NO_TRADE"
        or ledger.get("historical_trial_count_is_lower_bound") is True
    )
    if history_blocked:
        status = BLOCKED_HISTORY
        blockers = ["INSUFFICIENT_TRIAL_HISTORY", *missing]
    elif missing:
        status = BLOCKED_INPUTS
        blockers = missing
    else:
        status = READY
        blockers = []

    blocked = status != READY
    results = {key: None for key in _RESULT_FIELDS}
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "run_id": run_id,
        "created_at_utc": created_at_utc,
        "status": status,
        "code_commit": code_commit,
        "pipeline_generation_id": pipeline_generation_id,
        "data": data,
        "exchange_info": exchange,
        "trial_ledger": ledger,
        "runtime_inputs": inputs,
        "research_execution": {
            "full_research_run_started": False,
            "completed_outer_origins": 0,
            "required_outer_origins": 12,
            "training_days_per_origin": 730,
            "process_oos_days": 365,
            "embargo_hours": 24,
            "result_status": "not_executed_due_blocker" if blocked else "awaiting_explicit_execution",
        },
        "results": results,
        "blockers": blockers,
        "release_decision": "NO_TRADE",
        "freshness": "NOT_EVALUATED",
        "adoption_eligible": False,
        "bot_start_allowed": False,
        "safety": dict(_SAFETY),
    }
    canonical = _canonical_json(payload)
    report = Task33PreflightReport(canonical, _sha256(canonical.encode("utf-8")))
    validate_task33_preflight_report(report)
    return report


def validate_task33_preflight_report(
    value: Task33PreflightReport | Mapping[str, Any],
) -> Task33PreflightReport:
    if isinstance(value, Task33PreflightReport):
        payload = value.to_dict()
        observed_sha = value.report_sha256
        canonical = value.canonical_json
    else:
        payload = dict(value)
        canonical = _canonical_json(payload)
        observed_sha = _sha256(canonical.encode("utf-8"))
    required = {
        "schema_version", "protocol_version", "contract_version", "run_id",
        "created_at_utc", "status", "code_commit", "pipeline_generation_id",
        "data", "exchange_info", "trial_ledger", "runtime_inputs",
        "research_execution", "results", "blockers", "release_decision",
        "freshness", "adoption_eligible", "bot_start_allowed", "safety",
    }
    if set(payload) != required:
        raise Task33PreflightError("Task-33 report fields are incomplete or unknown")
    if payload["schema_version"] != REPORT_SCHEMA_VERSION or payload["protocol_version"] != PROTOCOL_VERSION or payload["contract_version"] != CONTRACT_VERSION:
        raise Task33PreflightError("Task-33 report version mismatch")
    if payload["status"] not in {READY, BLOCKED_HISTORY, BLOCKED_INPUTS}:
        raise Task33PreflightError("Task-33 report status is invalid")
    if payload["safety"] != _SAFETY or payload["release_decision"] != "NO_TRADE" or payload["adoption_eligible"] is not False or payload["bot_start_allowed"] is not False:
        raise Task33PreflightError("Task-33 report safety claim is invalid")
    execution = _mapping(payload["research_execution"], "research_execution")
    if execution.get("full_research_run_started") is not False or execution.get("completed_outer_origins") != 0:
        raise Task33PreflightError("preflight cannot claim research execution")
    results = _mapping(payload["results"], "results")
    if set(results) != set(_RESULT_FIELDS) or any(item is not None for item in results.values()):
        raise Task33PreflightError("preflight result metrics must be complete and null")
    if payload["status"] != READY and execution.get("result_status") != "not_executed_due_blocker":
        raise Task33PreflightError("blocked preflight must identify non-execution")
    if payload["status"] != READY and not payload["blockers"]:
        raise Task33PreflightError("blocked preflight must include a blocker")
    if not _COMMIT.fullmatch(str(payload["code_commit"])) or not _PIPELINE.fullmatch(str(payload["pipeline_generation_id"])):
        raise Task33PreflightError("Task-33 report identity is invalid")
    _finite(payload)
    if canonical != _canonical_json(payload):
        raise Task33PreflightError("Task-33 report bytes are not canonical")
    digest = _sha256(canonical.encode("utf-8"))
    if observed_sha != digest:
        raise Task33PreflightError("Task-33 report digest mismatch")
    return Task33PreflightReport(canonical, digest)


def write_task33_preflight_report(report: Task33PreflightReport, path: str | Path) -> Path:
    validated = validate_task33_preflight_report(report)
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = (validated.canonical_json + "\n").encode("utf-8")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise Task33PreflightError("Task-33 report is create-only") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def _missing_runtime_inputs(
    value: Mapping[str, Any], *, repo_root: str | Path
) -> list[str]:
    missing: list[str] = []
    lookbacks = value.get("active_lookbacks")
    horizon = value.get("horizon_policy")
    try:
        expected = build_task33_runtime_inputs(
            repo_root,
            production_outer_origin_adapter=(
                value.get("production_outer_origin_adapter") is True
            ),
        )
    except ProductionRuntimeError:
        expected = None
    if expected is None or lookbacks != expected["active_lookbacks"]:
        missing.append("MISSING_FROZEN_ACTIVE_LOOKBACKS")
    if expected is None or horizon != expected["horizon_policy"]:
        missing.append("MISSING_FROZEN_HORIZON_POLICY")
    if value.get("production_outer_origin_adapter") is not True:
        missing.append("MISSING_PRODUCTION_OUTER_ORIGIN_ADAPTER")
    return missing


def _canonical_contract() -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "allowed_statuses": [READY, BLOCKED_HISTORY, BLOCKED_INPUTS],
        "required_runtime_inputs": ["active_lookbacks", "horizon_policy", "production_outer_origin_adapter"],
        "required_result_fields": list(_RESULT_FIELDS),
        "blocker_precedence": ["INSUFFICIENT_TRIAL_HISTORY", "MISSING_FROZEN_RUNTIME_INPUTS"],
        "blocked_result_policy": {"full_research_run_started": False, "not_executed_metrics_are_null": True, "release_decision": "NO_TRADE", "adoption_eligible": False, "bot_start_allowed": False},
        "safety": dict(_SAFETY),
    }


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise Task33PreflightError(f"{name} must be an object")
    return dict(value)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Task33PreflightError(f"{name} must be non-empty text")
    return value


def _require_digest(value: Any, name: str) -> None:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise Task33PreflightError(f"{name} digest is invalid")


def _strict_json(raw: str, name: str) -> Any:
    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in rows:
            if key in value:
                raise Task33PreflightError(f"{name} contains a duplicate JSON key")
            value[key] = item
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(Task33PreflightError(f"{name} contains {token}")))
    except json.JSONDecodeError as exc:
        raise Task33PreflightError(f"{name} is invalid JSON") from exc


def _finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise Task33PreflightError("Task-33 report contains a non-finite number")
    if isinstance(value, Mapping):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def _canonical_json(value: Any) -> str:
    _finite(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "BLOCKED_HISTORY", "BLOCKED_INPUTS", "CONTRACT_VERSION", "PROTOCOL_VERSION",
    "READY", "REPORT_SCHEMA_VERSION", "Task33PreflightError",
    "Task33PreflightReport", "build_task33_preflight_report",
    "load_task33_contract", "validate_task33_contract",
    "validate_task33_preflight_report", "write_task33_preflight_report",
]
