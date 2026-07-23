"""Task-29 adapter from one validated challenger state to Task-11/12 evidence.

The adapter creates no new report or storage architecture.  It only translates a
validated order-free forward ledger into the existing Protocol-v3 report schema
and compact content-addressed artifact payloads.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ethusdc_bot.protocol_v3.artifact_store_api import (
    DAILY_MTM,
    DIAGNOSTICS,
    EQUITY_UNDERWATER,
    TRADES,
    ArtifactPayload,
    build_artifact_payload,
    persist_compact_artifact_bundle,
)
from ethusdc_bot.protocol_v3.reporting_api import (
    RESEARCH_CHALLENGER_SHADOW,
    REPORT_STORAGE_ROOTS,
    ProtocolV3Report,
    build_protocol_v3_report,
    read_protocol_v3_report,
    write_protocol_v3_report,
)
from ethusdc_bot.protocol_v3.research_challenger import (
    ResearchChallengerError,
    ResearchChallengerState,
    validate_research_challenger_state,
)


@dataclass(frozen=True)
class ResearchChallengerEvidence:
    report: ProtocolV3Report
    artifacts: Mapping[str, ArtifactPayload]
    work_unit_id: str
    work_unit_identity: Mapping[str, Any]


@dataclass(frozen=True)
class PersistedResearchChallengerEvidence:
    report_path: Path
    artifact_index_path: Path


def build_research_challenger_evidence(
    state: ResearchChallengerState,
    *,
    report_id: str,
    created_at_utc: datetime,
) -> ResearchChallengerEvidence:
    """Build one retrospective, non-adoptable report for complete UTC days only."""

    validated = validate_research_challenger_state(state)
    root = validated.to_dict()
    records = root["forward_ledger"]["records"]
    start, end = _complete_window(records)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    window_records = [
        record for record in records if start_ms <= record["open_time_ms"] < end_ms
    ]
    if not window_records:
        raise ResearchChallengerError(
            "research-challenger evidence requires at least one complete UTC day"
        )

    run_fingerprint = f"protocol_v3_run_sha256:{root['run_fingerprint_sha256']}"
    pipeline_generation = root["pipeline_generation_id"]
    report = build_protocol_v3_report(
        artifact_kind=RESEARCH_CHALLENGER_SHADOW,
        report_id=report_id,
        created_at_utc=_utc_text(created_at_utc),
        run_fingerprint=run_fingerprint,
        pipeline_generation=pipeline_generation,
        window_id=f"{report_id}_window",
        start_inclusive_utc=_utc_text(start),
        end_exclusive_utc=_utc_text(end),
        process_oos_net_usdc=None,
        producer="protocol_v3.research_challenger",
        producer_status="completed_diagnostic",
        source_artifact_ids=(
            root["task28_report_sha256"],
            root["bundle_sha256"],
            root["forward_ledger"]["head_sha256"],
            validated.state_sha256,
        ),
        reason_codes=(
            "not_fresh",
            "order_free",
            "retrospective_research_challenger",
        ),
    )

    daily_rows = _daily_mtm_rows(records, start, end)
    coverage = {
        "start_inclusive_utc": _utc_text(start),
        "end_exclusive_utc": _utc_text(end),
        "calendar_days": (end.date() - start.date()).days,
    }
    artifacts = {
        "trades": build_artifact_payload(
            TRADES,
            _trade_rows(root["engine_state"]["trades"], start_ms, end_ms),
        ),
        "daily_mtm": build_artifact_payload(
            DAILY_MTM,
            daily_rows,
            coverage=coverage,
        ),
        "equity_underwater": build_artifact_payload(
            EQUITY_UNDERWATER,
            _equity_rows(records, start_ms, end_ms),
        ),
        "diagnostics": build_artifact_payload(
            DIAGNOSTICS,
            _diagnostic_rows(window_records),
        ),
    }
    work_identity = {
        "schema_version": "protocol_v3_research_challenger_work_unit_v1",
        "state_sha256": validated.state_sha256,
        "task28_report_sha256": root["task28_report_sha256"],
        "bundle_sha256": root["bundle_sha256"],
        "forward_ledger_head_sha256": root["forward_ledger"]["head_sha256"],
        "start_inclusive_utc": _utc_text(start),
        "end_exclusive_utc": _utc_text(end),
        "orders_created": 0,
        "private_api_calls": 0,
        "canonical_adoption_eligible": False,
    }
    return ResearchChallengerEvidence(
        report=report,
        artifacts=artifacts,
        work_unit_id=f"challenger-{root['forward_ledger']['head_sha256'][:24]}",
        work_unit_identity=work_identity,
    )


def persist_research_challenger_evidence(
    evidence: ResearchChallengerEvidence,
    *,
    repository_root: str | Path,
) -> PersistedResearchChallengerEvidence:
    """Persist through the existing Task-11 report and Task-12 artifact stores."""

    if not isinstance(evidence, ResearchChallengerEvidence):
        raise ResearchChallengerError(
            "validated ResearchChallengerEvidence is required"
        )
    repo = Path(repository_root).resolve(strict=True)
    report_payload = evidence.report.to_dict()
    report_path = (
        repo
        / REPORT_STORAGE_ROOTS[RESEARCH_CHALLENGER_SHADOW]
        / f"{evidence.report.report_id}.json"
    )
    if report_path.exists():
        existing = read_protocol_v3_report(report_path, repo)
        if existing != evidence.report:
            raise ResearchChallengerError(
                "existing research-challenger report conflicts with evidence"
            )
    else:
        report_path = write_protocol_v3_report(evidence.report, repo)
    index_path = persist_compact_artifact_bundle(
        parent_report_path=report_path,
        repository_root=repo,
        work_unit_id=evidence.work_unit_id,
        work_unit_identity=evidence.work_unit_identity,
        artifacts=evidence.artifacts,
    )
    if report_payload["evidence_status"]["canonical_adoption_eligible"] is not False:
        raise ResearchChallengerError(
            "research-challenger report unexpectedly became adoption-eligible"
        )
    return PersistedResearchChallengerEvidence(report_path, index_path)


def _complete_window(records: list[dict[str, Any]]) -> tuple[datetime, datetime]:
    if not records:
        raise ResearchChallengerError(
            "research-challenger evidence requires forward records"
        )
    first = _minute(records[0]["open_time_ms"])
    last = _minute(records[-1]["open_time_ms"])
    first_midnight = first.replace(hour=0, minute=0, second=0, microsecond=0)
    start = first_midnight if first == first_midnight else first_midnight + timedelta(days=1)
    last_midnight = last.replace(hour=0, minute=0, second=0, microsecond=0)
    end = (
        last_midnight + timedelta(days=1)
        if last.hour == 23 and last.minute == 59
        else last_midnight
    )
    if end <= start:
        raise ResearchChallengerError(
            "research-challenger evidence requires at least one complete UTC day"
        )
    return start, end


def _daily_mtm_rows(
    records: list[dict[str, Any]], start: datetime, end: datetime
) -> list[dict[str, Any]]:
    by_time = {record["open_time_ms"]: record for record in records}
    rows: list[dict[str, Any]] = []
    current = start
    previous_equity = _equity_before(by_time, int(start.timestamp() * 1000))
    while current < end:
        end_open_ms = int((current + timedelta(days=1, minutes=-1)).timestamp() * 1000)
        end_record = by_time.get(end_open_ms)
        if end_record is None:
            raise ResearchChallengerError(
                "complete challenger day is missing its final UTC minute"
            )
        closing = float(end_record["closing_equity_usdc"])
        rows.append(
            {
                "day_utc": current.date().isoformat(),
                "net_mtm_usdc": round(closing - previous_equity, 10),
            }
        )
        previous_equity = closing
        current += timedelta(days=1)
    return rows


def _equity_before(by_time: Mapping[int, Mapping[str, Any]], start_ms: int) -> float:
    previous = by_time.get(start_ms - 60_000)
    return 0.0 if previous is None else float(previous["closing_equity_usdc"])


def _trade_rows(
    trades: list[dict[str, Any]], start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, trade in enumerate(trades, start=1):
        exit_time = int(trade["exit_time"])
        if not start_ms <= exit_time < end_ms:
            continue
        lot_id = str(trade.get("lot_id") or f"lot-{index:08d}")
        rows.append(
            {
                "trade_id": lot_id,
                "entry_time_utc": _ms_text(int(trade["entry_time"])),
                "exit_time_utc": _ms_text(exit_time),
                "net_usdc": float(trade["net_profit_usdc"]),
                "data": dict(trade),
            }
        )
    rows.sort(key=lambda row: (row["entry_time_utc"], row["trade_id"]))
    return rows


def _equity_rows(
    records: list[dict[str, Any]], start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    peak = 0.0
    rows: list[dict[str, Any]] = []
    for record in records:
        equity = float(record["closing_equity_usdc"])
        peak = max(peak, equity)
        if not start_ms <= record["open_time_ms"] < end_ms:
            continue
        rows.append(
            {
                "timestamp_utc": _ms_text(int(record["decision_time_ms"])),
                "equity_usdc": equity,
                "underwater_usdc": round(equity - peak, 10),
            }
        )
    return rows


def _diagnostic_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "record_id": f"minute-{int(record['sequence']):010d}",
            "category": "research_challenger_forward_minute",
            "data": {
                key: value
                for key, value in record.items()
                if key not in {"sequence", "record_sha256"}
            },
        }
        for record in records
    ]


def _minute(value: Any) -> datetime:
    if type(value) is not int or value < 0 or value % 60_000:
        raise ResearchChallengerError("challenger record is not on the UTC 1m grid")
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _ms_text(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace(
        "+00:00", "Z"
    )


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ResearchChallengerError("evidence timestamp must be UTC")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "PersistedResearchChallengerEvidence",
    "ResearchChallengerEvidence",
    "build_research_challenger_evidence",
    "persist_research_challenger_evidence",
]
