"""Load the latest validated local Task-33 preflight for the desktop UI.

The loader is read-only.  It accepts only create-only Task-33 reports whose
embedded data, exchange snapshot, and pipeline generation still validate.  It
never scans the multi-gigabyte Protocol-v2 report directory and never starts a
research, trading, or network action.
"""
from __future__ import annotations

from datetime import UTC, datetime, time
import json
from pathlib import Path
from typing import Any

from ethusdc_bot.protocol_v3.data_snapshot import validate_frozen_data_snapshot
from ethusdc_bot.protocol_v3.pipeline import build_pipeline_generation
from ethusdc_bot.protocol_v3.run_identity import (
    FrozenExchangeInfoSnapshot,
    validate_exchange_info_snapshot,
)
from ethusdc_bot.protocol_v3.task33_preflight import (
    Task33PreflightError,
    Task33PreflightReport,
    validate_task33_preflight_report,
)
from ethusdc_bot.ui.protocol_v3_dashboard_bridge import ProtocolV3UiEvidence
from ethusdc_bot.ui.protocol_v3_lifecycle_status import (
    build_protocol_v3_lifecycle_status,
)
from ethusdc_bot.ui.protocol_v3_operator_state import (
    build_protocol_v3_data_status,
    build_protocol_v3_research_progress,
)

_MAX_REPORT_BYTES = 2_000_000


class ProtocolV3LocalEvidenceError(RuntimeError):
    """Raised when local UI evidence is missing, ambiguous, or invalid."""


def load_latest_task33_ui_evidence(
    repository_root: str | Path,
    local_root: str | Path,
) -> ProtocolV3UiEvidence:
    """Return typed UI evidence from the newest fully validated Task-33 report."""

    repo = Path(repository_root).resolve()
    report_root = Path(local_root).resolve() / "runtime" / "protocol_v3" / "task33"
    if not report_root.is_dir() or report_root.is_symlink():
        raise ProtocolV3LocalEvidenceError("Task-33 report root is missing or unsafe")
    candidates = sorted(report_root.glob("task33-preflight-*.json"))
    if not candidates:
        raise ProtocolV3LocalEvidenceError("no Task-33 preflight report exists")

    validated: list[tuple[datetime, Path, Task33PreflightReport]] = []
    failures: list[str] = []
    for path in candidates:
        try:
            report = _read_report(path)
            payload = report.to_dict()
            validate_frozen_data_snapshot(payload["data"], repo_root=repo)
            exchange = _exchange_snapshot(payload["exchange_info"])
            validate_exchange_info_snapshot(exchange, repo_root=repo)
            generation = build_pipeline_generation(repo)
            if payload["pipeline_generation_id"] != generation.generation_id:
                raise ProtocolV3LocalEvidenceError(
                    "Task-33 report belongs to a different pipeline generation"
                )
            validated.append((_utc(payload["created_at_utc"]), path, report))
        except Exception as exc:
            failures.append(f"{path.name}:{type(exc).__name__}")
    if not validated:
        detail = ",".join(failures) if failures else "unknown"
        raise ProtocolV3LocalEvidenceError(
            f"no valid Task-33 preflight report remains: {detail}"
        )

    _created, _path, report = max(validated, key=lambda row: (row[0], row[1].name))
    root = report.to_dict()
    generation = build_pipeline_generation(repo)
    exchange = _exchange_snapshot(root["exchange_info"])
    data = root["data"]
    latest_day = data["availability"]["latest_common_complete_day"]
    watermark = datetime.combine(
        datetime.fromisoformat(latest_day).date(), time(23, 59), tzinfo=UTC
    )
    context_sha = data["common_minute_grid_sha256"]
    blockers = tuple(str(value) for value in root["blockers"])
    lifecycle = build_protocol_v3_lifecycle_status(
        process_oos="FAILED" if blockers else "NOT_STARTED",
        current_refit="NOT_STARTED",
        final_window="NOT_REGISTERED",
        canonical_shadow="NOT_ALLOWED",
        reason_codes=blockers,
    )
    progress = build_protocol_v3_research_progress(
        phase="blocked_preflight" if blockers else "preflight_ready",
        completed_origins=int(root["research_execution"]["completed_outer_origins"]),
        total_origins=int(root["research_execution"]["required_outer_origins"]),
        completed_folds=0,
        total_folds=6,
        completed_cycles=0,
        total_cycles=96,
        tested_candidates=0,
        current_step=root["status"],
    )
    return ProtocolV3UiEvidence(
        data_status=build_protocol_v3_data_status(
            state="READY",
            common_watermark_open_time_ms=int(watermark.timestamp() * 1000),
            context_identity_sha256=context_sha,
        ),
        pipeline_generation=generation,
        exchange_info_snapshot=exchange,
        research_progress=progress,
        lifecycle_status=lifecycle,
        task33_preflight=report,
    )


def build_local_task33_evidence_provider(
    repository_root: str | Path,
    local_root: str | Path,
):
    """Build the zero-argument provider expected by the existing dashboard."""

    repo = Path(repository_root).resolve()
    local = Path(local_root).resolve()
    return lambda: load_latest_task33_ui_evidence(repo, local)


def _read_report(path: Path) -> Task33PreflightReport:
    if not path.is_file() or path.is_symlink():
        raise ProtocolV3LocalEvidenceError("Task-33 report path is unsafe")
    if path.stat().st_size > _MAX_REPORT_BYTES:
        raise ProtocolV3LocalEvidenceError("Task-33 report exceeds UI size limit")
    try:
        root = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda token: _invalid_constant(token),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolV3LocalEvidenceError("Task-33 report is unreadable") from exc
    if not isinstance(root, dict):
        raise ProtocolV3LocalEvidenceError("Task-33 report root must be an object")
    try:
        return validate_task33_preflight_report(root)
    except Task33PreflightError as exc:
        raise ProtocolV3LocalEvidenceError("Task-33 report validation failed") from exc


def _exchange_snapshot(value: dict[str, Any]) -> FrozenExchangeInfoSnapshot:
    payload = dict(value)
    digest = payload.pop("snapshot_sha256", None)
    if not isinstance(digest, str):
        raise ProtocolV3LocalEvidenceError("exchange snapshot digest is missing")
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return FrozenExchangeInfoSnapshot(canonical, digest)


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ProtocolV3LocalEvidenceError("created_at_utc is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ProtocolV3LocalEvidenceError("created_at_utc is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ProtocolV3LocalEvidenceError("created_at_utc must be UTC")
    return parsed.astimezone(UTC)


def _unique_pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in rows:
        if key in value:
            raise ProtocolV3LocalEvidenceError("duplicate JSON key")
        value[key] = item
    return value


def _invalid_constant(token: str) -> None:
    raise ProtocolV3LocalEvidenceError(f"invalid JSON constant: {token}")


__all__ = [
    "ProtocolV3LocalEvidenceError",
    "build_local_task33_evidence_provider",
    "load_latest_task33_ui_evidence",
]
