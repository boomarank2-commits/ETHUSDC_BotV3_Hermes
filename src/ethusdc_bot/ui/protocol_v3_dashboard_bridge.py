"""Typed Task-30 bridge between canonical Protocol-v3 evidence and the existing UI.

The bridge is read-only. A provider supplies already validated backend objects;
the dashboard derives one operator view from them. It never scans for a Task-28
report, trusts raw JSON, mutates a checkpoint, starts a runtime, or calculates a
result. This keeps the existing backend/controller objects as the only truth.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeAlias

from ethusdc_bot.protocol_v3.current_refit import CurrentRefitDecision
from ethusdc_bot.protocol_v3.pipeline import PipelineGeneration
from ethusdc_bot.protocol_v3.reporting import ProtocolV3Report
from ethusdc_bot.protocol_v3.research_challenger import ResearchChallengerState
from ethusdc_bot.protocol_v3.research_challenger_checkpoint import (
    ResearchChallengerCheckpointReceipt,
)
from ethusdc_bot.protocol_v3.run_identity import FrozenExchangeInfoSnapshot
from ethusdc_bot.ui.protocol_v3_lifecycle_status import (
    ProtocolV3LifecycleStatus,
    build_protocol_v3_lifecycle_status,
)
from ethusdc_bot.ui.protocol_v3_operator_state import (
    ProtocolV3DataStatus,
    ProtocolV3OperatorState,
    ProtocolV3ResearchProgress,
    build_protocol_v3_data_status,
    build_protocol_v3_operator_state,
)
from ethusdc_bot.ui.research_challenger_controller import ChallengerResumeWorker


@dataclass(frozen=True)
class ProtocolV3UiEvidence:
    """One immutable read-only evidence snapshot supplied by the backend."""

    data_status: ProtocolV3DataStatus
    pipeline_generation: PipelineGeneration | None = None
    current_refit: CurrentRefitDecision | None = None
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | None = None
    challenger_state: ResearchChallengerState | None = None
    challenger_report: ProtocolV3Report | None = None
    challenger_checkpoint: ResearchChallengerCheckpointReceipt | None = None
    research_progress: ProtocolV3ResearchProgress | None = None
    lifecycle_status: ProtocolV3LifecycleStatus = field(
        default_factory=build_protocol_v3_lifecycle_status
    )
    resume_worker: ChallengerResumeWorker | None = None
    challenger_report_opener: Callable[[], None] | None = None


ProtocolV3EvidenceProvider: TypeAlias = Callable[[], ProtocolV3UiEvidence]


def build_empty_protocol_v3_ui_evidence() -> ProtocolV3UiEvidence:
    """Return the fail-closed default used until a backend provider is attached."""

    return ProtocolV3UiEvidence(
        data_status=build_protocol_v3_data_status(
            state="MISSING",
            blockers=("validated_three_market_watermark_not_supplied",),
        )
    )


def resolve_protocol_v3_operator_state(
    evidence: ProtocolV3UiEvidence,
    *,
    now_utc: datetime,
    worker_status: Mapping[str, Any] | None = None,
    controller_state: ResearchChallengerState | None = None,
    controller_checkpoint: ResearchChallengerCheckpointReceipt | None = None,
    ui_runtime_blockers: tuple[str, ...] = (),
) -> ProtocolV3OperatorState:
    """Resolve one display state without copying or altering backend evidence."""

    if not isinstance(evidence, ProtocolV3UiEvidence):
        raise TypeError("ProtocolV3UiEvidence is required")
    active_state = controller_state or evidence.challenger_state
    active_checkpoint = controller_checkpoint or evidence.challenger_checkpoint
    return build_protocol_v3_operator_state(
        now_utc=now_utc,
        data_status=evidence.data_status,
        pipeline_generation=evidence.pipeline_generation,
        current_refit=evidence.current_refit,
        challenger_state=active_state,
        challenger_report=evidence.challenger_report,
        challenger_checkpoint=active_checkpoint,
        research_progress=evidence.research_progress,
        exchange_info_snapshot=evidence.exchange_info_snapshot,
        lifecycle_status=evidence.lifecycle_status,
        resume_worker_available=evidence.resume_worker is not None,
        report_open_available=evidence.challenger_report_opener is not None,
        ui_runtime_blockers=ui_runtime_blockers,
        worker_status=worker_status,
    )


def format_protocol_v3_operator_view(state: ProtocolV3OperatorState) -> str:
    """Render the complete Task-30 operator view without deriving new evidence."""

    if not isinstance(state, ProtocolV3OperatorState):
        raise TypeError("typed ProtocolV3OperatorState is required")
    root = state.to_dict()
    tasks = root["task_progress"]
    data = root["data_status"]
    refit = root["current_refit"]
    lifecycle = root["lifecycle_status"]
    challenger = root["research_challenger"]
    worker = root["worker_status"]
    progress = root["research_progress"]
    buttons = root["buttons"]
    meaning = root["result_meaning"]
    safety = root["safety"]

    lines = [
        "PROTOCOL V3 – FORSCHUNG UND ORDERFREIE DIAGNOSE",
        "",
        (
            "Aufgabenfortschritt: "
            f"{tasks['done_tasks']}/{tasks['total_tasks']} DONE_100 = "
            f"{tasks['progress_pct']} %; Aufgabe {tasks['active_task']} "
            f"{tasks['active_task_status']}"
        ),
        f"Aktuelle Ansicht: {root['operator_mode']}",
        "",
        "PROTOCOL-V3-LEBENSZYKLUS",
        f"- Historisches Prozess-OOS: {lifecycle['process_oos']}",
        f"- Aktueller Monatsrefit: {lifecycle['current_refit']}",
        f"- Späteres Finalfenster: {lifecycle['final_window']}",
        f"- Kanonischer Shadow: {lifecycle['canonical_shadow']}",
        f"- Gründe: {_blockers(lifecycle.get('reason_codes'))}",
        "",
        "DREI-MARKT-DATEN",
        f"- Status: {data['state']}",
        f"- Gemeinsame geschlossene 1m-Watermark: {_watermark(data.get('common_watermark_open_time_ms'))}",
        f"- Kontextidentität: {_text(data.get('context_identity_sha256'))}",
        f"- Datenblocker: {_blockers(data.get('blockers'))}",
        "- ETHUSDC ist einziges virtuelles Handelssymbol; BTCUSDC und ETHBTC sind nur Kontext.",
        "",
        "AKTUELLER 730-TAGE-REFIT",
        f"- Status / Entscheidung: {refit['status']} / {_text(refit.get('choice'))}",
        f"- Gültig ab/bis: {_text(refit.get('valid_from_utc'))} / {_text(refit.get('valid_until_utc'))}",
        f"- Nächster Monatsanker: {_text(refit.get('next_month_anchor_utc'))}",
        f"- Evidenz: {refit['freshness']} / diagnostic_only={refit['diagnostic_only']}",
    ]
    if progress is not None:
        lines.extend(
            [
                "",
                "RESEARCH-FORTSCHRITT",
                f"- Phase / Schritt: {progress['phase']} / {_text(progress.get('current_step'))}",
                f"- Origins: {progress['completed_origins']}/{progress['total_origins']} abgeschlossen; aktiv {_text(progress.get('active_origin'))}",
                f"- Folds: {progress['completed_folds']}/{progress['total_folds']} abgeschlossen; aktiv {_text(progress.get('active_fold'))}",
                f"- Cycles: {progress['completed_cycles']}/{_text(progress.get('total_cycles'))}; getestete Kandidaten {progress['tested_candidates']}",
                "- Outer-PnL bleibt bis zu einem vollständig publizierten Ergebnis verborgen.",
            ]
        )
    lines.extend(
        [
            "",
            "RESEARCH-CHALLENGER-SHADOW",
            f"- Status / Modus: {challenger['status']} / {_text(challenger.get('mode'))}",
            f"- Worker: {worker['phase']} / running={worker['running']} / stop_requested={worker['stop_requested']}",
            f"- Ledger: {challenger['ledger_record_count']} Zeilen / Head {_text(challenger.get('ledger_head_sha256'))}",
            f"- State / Checkpoint: {_text(challenger.get('state_sha256'))} / {_text(challenger.get('checkpoint_receipt_sha256'))}",
            f"- Report: {_text(challenger.get('report_id'))} / Freshness {_text(challenger.get('report_freshness'))}",
            "- Orders erzeugt: 0; private API-Aufrufe: 0.",
            "",
            "BEDIENZUSTÄNDE",
            _button_line("Manuell starten", buttons["challenger_start"]),
            _button_line("Aus Checkpoint fortsetzen", buttons["challenger_resume"]),
            _button_line("Diagnose stoppen", buttons["challenger_stop"]),
            _button_line(
                "Diagnosebericht öffnen", buttons["challenger_report_open"]
            ),
            _button_line("Paper", buttons["paper"]),
            _button_line("Testtrade", buttons["testtrade"]),
            _button_line("Live", buttons["live"]),
            _button_line("Kanonische Adoption", buttons["canonical_adoption"]),
            "",
            "ERGEBNISBEDEUTUNG",
            f"- Task 27/28: {meaning['task27_task28_freshness']} / {meaning['task27_task28_role']}",
            f"- Task 29: {meaning['task29_freshness']} / {meaning['task29_role']}",
            f"- Statistisch unterstützt: {meaning['statistically_supported']}",
            f"- Protocol-v3-Finalstatus: {meaning['protocol_v3_final_status']}",
            f"- Finalfensterstatus: {meaning['final_window_status']}",
            f"- Kanonischer Shadowstatus: {meaning['canonical_shadow_status']}",
            "",
            "SICHERHEIT",
            f"- Orders: {safety['orders']}",
            f"- Paper: {safety['paper']}",
            f"- Testtrade: {safety['testtrade']}",
            f"- Live: {safety['live']}",
            f"- Trading-API/private Endpunkte: {safety['trading_api_private_endpoints']}",
            f"- Kanonische Adoption: {safety['canonical_adoption']}",
            f"- Bot-Start: {safety['bot_start']}",
        ]
    )
    return "\n".join(lines) + "\n"


def protocol_v3_button_blocker_text(
    state: ProtocolV3OperatorState, button_name: str
) -> str:
    """Return concrete blockers for one disabled button."""

    if not isinstance(state, ProtocolV3OperatorState):
        raise TypeError("typed ProtocolV3OperatorState is required")
    button = state.to_dict()["buttons"].get(button_name)
    if not isinstance(button, Mapping):
        raise KeyError(button_name)
    blockers = button.get("blockers")
    return _blockers(blockers)


def _button_line(label: str, value: Mapping[str, Any]) -> str:
    status = "AKTIV" if value.get("enabled") is True else "GESPERRT"
    return f"- {label}: {status}; Blocker: {_blockers(value.get('blockers'))}"


def _blockers(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "keine"
    return ", ".join(str(item) for item in value)


def _text(value: Any) -> str:
    return "nicht verfügbar" if value is None or value == "" else str(value)


def _watermark(value: Any) -> str:
    if type(value) is not int:
        return "nicht verfügbar"
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace(
        "+00:00", "Z"
    )


__all__ = [
    "ProtocolV3EvidenceProvider",
    "ProtocolV3UiEvidence",
    "build_empty_protocol_v3_ui_evidence",
    "format_protocol_v3_operator_view",
    "protocol_v3_button_blocker_text",
    "resolve_protocol_v3_operator_state",
]
