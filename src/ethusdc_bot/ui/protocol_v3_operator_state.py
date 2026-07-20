"""Pure Task-30 Protocol-v3 operator state for the existing dashboard.

The adapter derives one display state from already validated Protocol-v3 objects.
It performs no file writes, runtime starts, report creation, adoption, orders, API
access, or PnL calculation.  Missing or contradictory evidence only disables UI
actions with a concrete blocker.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from typing import Any, Final

from ethusdc_bot.protocol_v3.current_refit import (
    CASH,
    CurrentRefitDecision,
    validate_current_refit_decision,
)
from ethusdc_bot.protocol_v3.pipeline import PipelineGeneration, validate_pipeline_generation
from ethusdc_bot.protocol_v3.reporting import (
    RESEARCH_CHALLENGER_SHADOW,
    ProtocolV3Report,
    validate_protocol_v3_report,
)
from ethusdc_bot.protocol_v3.research_challenger import (
    ResearchChallengerState,
    validate_research_challenger_state,
)
from ethusdc_bot.protocol_v3.research_challenger_checkpoint import (
    ResearchChallengerCheckpointReceipt,
    validate_research_challenger_checkpoint_receipt,
)

PROTOCOL_V3_TOTAL_TASKS: Final = 33
PROTOCOL_V3_DONE_TASKS: Final = 29
PROTOCOL_V3_PROGRESS_PCT: Final = round(
    PROTOCOL_V3_DONE_TASKS / PROTOCOL_V3_TOTAL_TASKS * 100, 2
)
DATA_STATES: Final = {
    "READY",
    "MISSING",
    "STALE",
    "FUTURE",
    "MISALIGNED",
    "INCOMPLETE",
    "ERROR",
}
ACTIVE_WORKER_PHASES: Final = {"starting", "running", "stopping"}
_SAFETY: Final = {
    "orders": "gesperrt",
    "paper": "gesperrt",
    "testtrade": "gesperrt",
    "live": "gesperrt",
    "trading_api_private_endpoints": "nicht verwendet",
    "canonical_adoption": "nicht zulässig",
    "bot_start": "nicht erlaubt",
}


class ProtocolV3OperatorStateError(ValueError):
    """Raised when a UI input tries to bypass canonical Protocol-v3 evidence."""


@dataclass(frozen=True)
class ProtocolV3DataStatus:
    canonical_json: str
    status_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


@dataclass(frozen=True)
class ProtocolV3ResearchProgress:
    canonical_json: str
    progress_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


@dataclass(frozen=True)
class ProtocolV3OperatorState:
    canonical_json: str
    state_sha256: str

    def to_dict(self) -> dict[str, Any]:
        root = json.loads(self.canonical_json)
        root["state_sha256"] = self.state_sha256
        return root


def build_protocol_v3_data_status(
    *,
    state: str,
    common_watermark_open_time_ms: int | None = None,
    context_identity_sha256: str | None = None,
    blockers: Sequence[str] = (),
) -> ProtocolV3DataStatus:
    """Build one explicit public three-market readiness state."""

    normalized_state = str(state).upper()
    if normalized_state not in DATA_STATES:
        raise ProtocolV3OperatorStateError("Protocol-v3 data state is invalid")
    blocker_rows = _strings(blockers, "data blockers")
    if normalized_state == "READY":
        if blocker_rows:
            raise ProtocolV3OperatorStateError("READY data cannot contain blockers")
        if (
            type(common_watermark_open_time_ms) is not int
            or common_watermark_open_time_ms < 0
            or common_watermark_open_time_ms % 60_000
        ):
            raise ProtocolV3OperatorStateError(
                "READY data requires an exact closed 1m watermark"
            )
        _sha(context_identity_sha256, "context_identity_sha256")
    else:
        if not blocker_rows:
            raise ProtocolV3OperatorStateError(
                "non-ready data requires at least one canonical blocker"
            )
        if common_watermark_open_time_ms is not None and (
            type(common_watermark_open_time_ms) is not int
            or common_watermark_open_time_ms < 0
            or common_watermark_open_time_ms % 60_000
        ):
            raise ProtocolV3OperatorStateError("data watermark is invalid")
        if context_identity_sha256 is not None:
            _sha(context_identity_sha256, "context_identity_sha256")
    basis = {
        "schema_version": "protocol_v3_ui_data_status_v1",
        "state": normalized_state,
        "common_watermark_open_time_ms": common_watermark_open_time_ms,
        "context_identity_sha256": context_identity_sha256,
        "blockers": blocker_rows,
    }
    return ProtocolV3DataStatus(_canonical(basis), _digest(basis))


def build_protocol_v3_research_progress(
    *,
    phase: str,
    completed_origins: int,
    total_origins: int = 12,
    active_origin: int | None = None,
    completed_folds: int = 0,
    total_folds: int = 6,
    active_fold: int | None = None,
    completed_cycles: int = 0,
    total_cycles: int | None = None,
    tested_candidates: int = 0,
    current_step: str | None = None,
) -> ProtocolV3ResearchProgress:
    """Build canonical progress without estimating time or unpublished PnL."""

    phase_text = _text(phase, "research phase")
    completed_origins = _count(completed_origins, total_origins, "completed_origins")
    total_origins = _positive(total_origins, "total_origins")
    completed_folds = _count(completed_folds, total_folds, "completed_folds")
    total_folds = _positive(total_folds, "total_folds")
    completed_cycles = _nonnegative(completed_cycles, "completed_cycles")
    tested_candidates = _nonnegative(tested_candidates, "tested_candidates")
    if total_cycles is not None:
        total_cycles = _positive(total_cycles, "total_cycles")
        if completed_cycles > total_cycles:
            raise ProtocolV3OperatorStateError("completed_cycles exceeds total_cycles")
    _optional_index(active_origin, total_origins, "active_origin")
    _optional_index(active_fold, total_folds, "active_fold")
    basis = {
        "schema_version": "protocol_v3_ui_research_progress_v1",
        "phase": phase_text,
        "completed_origins": completed_origins,
        "total_origins": total_origins,
        "active_origin": active_origin,
        "completed_folds": completed_folds,
        "total_folds": total_folds,
        "active_fold": active_fold,
        "completed_cycles": completed_cycles,
        "total_cycles": total_cycles,
        "tested_candidates": tested_candidates,
        "current_step": None if current_step is None else _text(current_step, "current_step"),
        "outer_pnl_visible": False,
    }
    return ProtocolV3ResearchProgress(_canonical(basis), _digest(basis))


def build_protocol_v3_operator_state(
    *,
    now_utc: datetime,
    data_status: ProtocolV3DataStatus,
    pipeline_generation: PipelineGeneration | None = None,
    current_refit: CurrentRefitDecision | None = None,
    challenger_state: ResearchChallengerState | None = None,
    challenger_report: ProtocolV3Report | None = None,
    challenger_checkpoint: ResearchChallengerCheckpointReceipt | None = None,
    research_progress: ProtocolV3ResearchProgress | None = None,
    worker_status: Mapping[str, Any] | None = None,
) -> ProtocolV3OperatorState:
    """Derive one fail-closed dashboard state from typed canonical inputs."""

    now = _utc(now_utc, "now_utc")
    if not isinstance(data_status, ProtocolV3DataStatus):
        raise ProtocolV3OperatorStateError("typed Protocol-v3 data status is required")
    data = data_status.to_dict()

    generation_payload: dict[str, Any] | None = None
    if pipeline_generation is not None:
        validate_pipeline_generation(pipeline_generation)
        generation_payload = pipeline_generation.to_dict()

    refit: dict[str, Any] | None = None
    if current_refit is not None:
        if not isinstance(current_refit, CurrentRefitDecision):
            raise ProtocolV3OperatorStateError(
                "typed validated Task-28 decision is required"
            )
        refit = validate_current_refit_decision(current_refit).to_dict()

    challenger: dict[str, Any] | None = None
    if challenger_state is not None:
        if not isinstance(challenger_state, ResearchChallengerState):
            raise ProtocolV3OperatorStateError(
                "typed validated Task-29 state is required"
            )
        challenger = validate_research_challenger_state(challenger_state).to_dict()

    report: dict[str, Any] | None = None
    if challenger_report is not None:
        if not isinstance(challenger_report, ProtocolV3Report):
            raise ProtocolV3OperatorStateError(
                "typed validated Task-29 report is required"
            )
        report = validate_protocol_v3_report(challenger_report).to_dict()
        if report["artifact_kind"] != RESEARCH_CHALLENGER_SHADOW:
            raise ProtocolV3OperatorStateError(
                "only a research_challenger_shadow report belongs in this panel"
            )

    checkpoint: dict[str, Any] | None = None
    if challenger_checkpoint is not None:
        if not isinstance(
            challenger_checkpoint, ResearchChallengerCheckpointReceipt
        ):
            raise ProtocolV3OperatorStateError(
                "typed validated Task-29 checkpoint receipt is required"
            )
        checkpoint = validate_research_challenger_checkpoint_receipt(
            challenger_checkpoint
        ).to_dict()

    progress = None
    if research_progress is not None:
        if not isinstance(research_progress, ProtocolV3ResearchProgress):
            raise ProtocolV3OperatorStateError(
                "typed Protocol-v3 research progress is required"
            )
        progress = research_progress.to_dict()

    worker = _worker_status(worker_status)
    refit_summary = _refit_summary(refit, now)
    challenger_summary = _challenger_summary(
        challenger=challenger,
        report=report,
        checkpoint=checkpoint,
        worker=worker,
    )
    blockers = _challenger_start_blockers(
        now=now,
        data=data,
        generation=generation_payload,
        refit=refit,
        challenger=challenger,
        worker=worker,
    )
    start_enabled = not blockers
    stop_enabled = worker["phase"] in ACTIVE_WORKER_PHASES and worker["running"]
    resume_blockers = _resume_blockers(
        challenger=challenger,
        checkpoint=checkpoint,
        generation=generation_payload,
        worker=worker,
    )
    resume_enabled = not resume_blockers
    operator_mode = _operator_mode(
        worker=worker,
        challenger=challenger,
        report=report,
        refit=refit,
        progress=progress,
    )
    next_anchor = refit_summary.get("next_month_anchor_utc")

    basis = {
        "schema_version": "protocol_v3_operator_state_v1",
        "protocol_version": "3.0.0",
        "operator_mode": operator_mode,
        "task_progress": {
            "done_tasks": PROTOCOL_V3_DONE_TASKS,
            "total_tasks": PROTOCOL_V3_TOTAL_TASKS,
            "progress_pct": PROTOCOL_V3_PROGRESS_PCT,
            "active_task": 30,
            "active_task_status": "IN_PROGRESS",
        },
        "data_status": data,
        "research_progress": progress,
        "current_refit": refit_summary,
        "research_challenger": challenger_summary,
        "worker_status": worker,
        "buttons": {
            "challenger_start": _button(start_enabled, blockers),
            "challenger_resume": _button(resume_enabled, resume_blockers),
            "challenger_stop": _button(
                stop_enabled,
                [] if stop_enabled else ["research_challenger_worker_not_running"],
            ),
            "paper": _button(False, ["protocol_v3_paper_locked"]),
            "testtrade": _button(False, ["protocol_v3_testtrade_locked"]),
            "live": _button(False, ["protocol_v3_live_locked"]),
            "canonical_adoption": _button(
                False, ["task29_is_diagnostic_and_not_adoption_eligible"]
            ),
        },
        "result_meaning": {
            "task27_task28_freshness": "NOT_FRESH",
            "task27_task28_role": "diagnostic_only",
            "task29_freshness": "NOT_FRESH",
            "task29_role": "order_free_diagnostic_only",
            "statistically_supported": False,
            "protocol_v3_final_status": False,
            "next_month_anchor_utc": next_anchor,
        },
        "safety": dict(_SAFETY),
        "outer_pnl_visible": False,
        "ui_may_create_orders": False,
        "ui_may_write_active_config": False,
    }
    return ProtocolV3OperatorState(_canonical(basis), _digest(basis))


def _refit_summary(refit: dict[str, Any] | None, now: datetime) -> dict[str, Any]:
    if refit is None:
        return {
            "status": "MISSING",
            "choice": None,
            "report_sha256": None,
            "valid_from_utc": None,
            "valid_until_utc": None,
            "next_month_anchor_utc": None,
            "freshness": "NOT_FRESH",
            "diagnostic_only": True,
        }
    manifest = refit["identity_manifest"]
    valid_from = _parse_utc(manifest["valid_from_utc"], "valid_from_utc")
    valid_until = _parse_utc(manifest["valid_until_utc"], "valid_until_utc")
    choice = refit["champion_challenger_cash_decision"]["choice"]
    if now < valid_from:
        status = "WAITING_VALID_FROM"
    elif now >= valid_until:
        status = "EXPIRED"
    else:
        status = choice
    return {
        "status": status,
        "choice": choice,
        "report_sha256": refit["report_sha256"],
        "valid_from_utc": manifest["valid_from_utc"],
        "valid_until_utc": manifest["valid_until_utc"],
        "next_month_anchor_utc": manifest["valid_until_utc"] if now >= valid_until else None,
        "freshness": refit["freshness"],
        "diagnostic_only": refit["diagnostic_only"],
    }


def _challenger_summary(
    *,
    challenger: dict[str, Any] | None,
    report: dict[str, Any] | None,
    checkpoint: dict[str, Any] | None,
    worker: dict[str, Any],
) -> dict[str, Any]:
    if worker["phase"] in ACTIVE_WORKER_PHASES:
        status = "RUNNING" if worker["phase"] != "stopping" else "STOPPING"
    elif challenger is not None and checkpoint is not None:
        status = "RESUME_READY"
    elif challenger is not None:
        status = "PAUSED"
    elif report is not None:
        status = "COMPLETED_DIAGNOSTIC"
    else:
        status = "NOT_STARTED"
    ledger = challenger["forward_ledger"] if challenger is not None else None
    return {
        "status": status,
        "mode": None if challenger is None else challenger["mode"],
        "state_sha256": None if challenger is None else challenger["state_sha256"],
        "ledger_head_sha256": None if ledger is None else ledger["head_sha256"],
        "ledger_record_count": 0 if ledger is None else ledger["record_count"],
        "checkpoint_receipt_sha256": (
            None if checkpoint is None else checkpoint["receipt_sha256"]
        ),
        "report_id": None if report is None else report["report_id"],
        "report_freshness": (
            None if report is None else report["evidence_status"]["freshness"]
        ),
        "orders_created": 0,
        "private_api_calls": 0,
        "canonical_adoption_eligible": False,
        "protocol_v3_final_status": False,
    }


def _challenger_start_blockers(
    *,
    now: datetime,
    data: dict[str, Any],
    generation: dict[str, Any] | None,
    refit: dict[str, Any] | None,
    challenger: dict[str, Any] | None,
    worker: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if refit is None:
        blockers.append("validated_task28_provenance_missing")
    if generation is None:
        blockers.append("current_pipeline_generation_missing")
    if data["state"] != "READY":
        blockers.extend(f"data:{value}" for value in data["blockers"])
    if challenger is not None:
        blockers.append("research_challenger_already_initialized")
    if worker["running"]:
        blockers.append("research_challenger_worker_already_running")
    if refit is not None:
        manifest = refit["identity_manifest"]
        valid_from = _parse_utc(manifest["valid_from_utc"], "valid_from_utc")
        valid_until = _parse_utc(manifest["valid_until_utc"], "valid_until_utc")
        if now < valid_from:
            blockers.append("task28_valid_from_not_reached")
        if now >= valid_until:
            blockers.append("task28_window_expired_use_next_month_anchor")
        if generation is not None and generation["generation_id"] != manifest[
            "current_pipeline_generation_id"
        ]:
            blockers.append("task28_pipeline_generation_mismatch")
    return sorted(set(blockers))


def _resume_blockers(
    *,
    challenger: dict[str, Any] | None,
    checkpoint: dict[str, Any] | None,
    generation: dict[str, Any] | None,
    worker: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if challenger is None:
        blockers.append("validated_task29_state_missing")
    if checkpoint is None:
        blockers.append("validated_task29_checkpoint_missing")
    if generation is None:
        blockers.append("current_pipeline_generation_missing")
    if worker["running"]:
        blockers.append("research_challenger_worker_already_running")
    if challenger is not None and generation is not None:
        if (
            challenger["pipeline_generation_id"] != generation["generation_id"]
            or challenger["forward_ledger_namespace"]
            != generation["forward_ledger_namespace"]
        ):
            blockers.append("cross_generation_resume_forbidden")
    if challenger is not None and checkpoint is not None:
        if checkpoint["research_state_sha256"] != challenger["state_sha256"]:
            blockers.append("checkpoint_state_hash_mismatch")
        if checkpoint["forward_ledger_head_sha256"] != challenger[
            "forward_ledger"
        ]["head_sha256"]:
            blockers.append("checkpoint_ledger_head_mismatch")
    return sorted(set(blockers))


def _operator_mode(
    *,
    worker: dict[str, Any],
    challenger: dict[str, Any] | None,
    report: dict[str, Any] | None,
    refit: dict[str, Any] | None,
    progress: dict[str, Any] | None,
) -> str:
    if worker["phase"] in ACTIVE_WORKER_PHASES:
        return "research_challenger"
    if challenger is not None or report is not None:
        return "research_challenger"
    if refit is not None:
        return "current_refit"
    if progress is not None:
        return "protocol_v3_research"
    return "protocol_v3_overview"


def _worker_status(value: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    phase = str(raw.get("phase", "idle"))
    running = bool(raw.get("running", False))
    if running != (phase in ACTIVE_WORKER_PHASES):
        raise ProtocolV3OperatorStateError("worker phase/running state is contradictory")
    return {
        "phase": phase,
        "running": running,
        "stop_requested": bool(raw.get("stop_requested", False)),
        "error": raw.get("error"),
    }


def _button(enabled: bool, blockers: Sequence[str]) -> dict[str, Any]:
    rows = _strings(blockers, "button blockers")
    if enabled and rows:
        raise ProtocolV3OperatorStateError("enabled button cannot contain blockers")
    if not enabled and not rows:
        raise ProtocolV3OperatorStateError("disabled button requires a blocker")
    return {"enabled": enabled, "blockers": rows}


def _strings(values: Sequence[str], name: str) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ProtocolV3OperatorStateError(f"{name} must be a sequence")
    rows = sorted(set(_text(value, name) for value in values))
    return rows


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolV3OperatorStateError(f"{name} must be non-empty text")
    return value.strip()


def _positive(value: Any, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ProtocolV3OperatorStateError(f"{name} must be a positive integer")
    return value


def _nonnegative(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ProtocolV3OperatorStateError(f"{name} must be a nonnegative integer")
    return value


def _count(value: Any, total: Any, name: str) -> int:
    total_value = _positive(total, name.replace("completed", "total"))
    count = _nonnegative(value, name)
    if count > total_value:
        raise ProtocolV3OperatorStateError(f"{name} exceeds total")
    return count


def _optional_index(value: Any, total: int, name: str) -> None:
    if value is None:
        return
    if type(value) is not int or not 1 <= value <= total:
        raise ProtocolV3OperatorStateError(f"{name} is outside its canonical range")


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ProtocolV3OperatorStateError(f"{name} must be timezone-aware UTC")
    result = value.astimezone(UTC)
    if value.utcoffset() != timedelta(0):
        raise ProtocolV3OperatorStateError(f"{name} must be UTC")
    return result


def _parse_utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtocolV3OperatorStateError(f"{name} must be canonical UTC text")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolV3OperatorStateError(f"{name} is invalid") from exc
    return _utc(result, name)


def _sha(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ProtocolV3OperatorStateError(f"{name} must be lowercase sha256")
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
    "PROTOCOL_V3_DONE_TASKS",
    "PROTOCOL_V3_PROGRESS_PCT",
    "PROTOCOL_V3_TOTAL_TASKS",
    "ProtocolV3DataStatus",
    "ProtocolV3OperatorState",
    "ProtocolV3OperatorStateError",
    "ProtocolV3ResearchProgress",
    "build_protocol_v3_data_status",
    "build_protocol_v3_operator_state",
    "build_protocol_v3_research_progress",
]
