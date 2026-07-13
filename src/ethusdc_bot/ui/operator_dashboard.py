"""Contextual single-window operator dashboard for the existing Hermes UI.

The module extends the existing :mod:`ethusdc_bot.ui.dashboard` without adding a
second state authority or any trading logic.  It keeps the same controllers and
widgets, but presents one clear operator context at a time:

* data check/download,
* running research backtest,
* completed/failed/interrupted research result.

It also installs two UI-only recovery guards when the real dashboard starts:

* a durable ``running`` checkpoint blocks a new run only while the existing
  exclusive PowerShell run lock is actually owned;
* frozen-report discovery invalidates a cached result when the compact text
  report appears or changes after the large JSON was written.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import threading
import tkinter as tk
from typing import Any, Mapping

from ethusdc_bot.ui import backtest_controller as _backtest_controller
from ethusdc_bot.ui import backtest_display as _backtest_display
from ethusdc_bot.ui import dashboard as _base_dashboard
from ethusdc_bot.ui import final_evaluation_controller as _final_evaluation_controller


_ACTIVE_DATA_PHASES = {
    "checking_readiness",
    "planning",
    "dry_run",
    "downloading",
    "refreshing_readiness",
}
_ACTIVE_BACKTEST_MODES = {"starting", "running"}
_RESULT_BACKTEST_MODES = {"completed", "failed", "interrupted"}
_RUN_LOCK_NAME = "production_research.active.lock"


@dataclass
class RefreshGate:
    """Prevent a finished-but-not-yet-applied refresh from being overtaken.

    Tk applies queued payloads after the worker thread has already terminated.
    Merely checking ``thread.is_alive()`` therefore permits a second worker in
    that small window.  This gate remains pending until the matching payload is
    consumed on Tk's thread.
    """

    generation: int = 0
    pending: bool = False

    def begin(self) -> int | None:
        if self.pending:
            return None
        self.generation += 1
        self.pending = True
        return self.generation

    def finish(self, generation: int) -> bool:
        if generation != self.generation:
            return False
        self.pending = False
        return True


_ORIGINAL_ACTIVE_CHECKPOINT_DISCOVERY = (
    _backtest_controller.discover_active_research_checkpoint
)
_ORIGINAL_RESEARCH_DISCOVERY_READER = (
    _final_evaluation_controller._read_research_discovery_fields
)
_COMPACT_DISCOVERY_STAMPS: dict[str, tuple[bool, int, int]] = {}
_RUNTIME_GUARDS_INSTALLED = False


def _run_lock_is_owned(reports_root: str | Path) -> bool:
    """Return true only when another process owns the exclusive run lock.

    The PowerShell production starter opens this file with ``FileShare.None``.
    A stale file left on disk is therefore harmless and can be opened here,
    while a genuinely owned lock fails closed with ``OSError`` on Windows.
    """

    lock_path = Path(reports_root) / _RUN_LOCK_NAME
    if not lock_path.is_file():
        return False
    try:
        with lock_path.open("a+b"):
            return False
    except OSError:
        return True


def discover_active_research_checkpoint_lock_aware(
    reports_root: str | Path,
) -> dict[str, Any] | None:
    """Treat a durable running checkpoint as active only with an owned lock."""

    checkpoint = _ORIGINAL_ACTIVE_CHECKPOINT_DISCOVERY(reports_root)
    if checkpoint is None:
        return None
    return checkpoint if _run_lock_is_owned(reports_root) else None


def _compact_report_stamp(report_path: Path) -> tuple[bool, int, int]:
    compact_path = report_path.with_suffix(".txt")
    try:
        stat = compact_path.stat()
    except OSError:
        return False, 0, 0
    return True, stat.st_size, stat.st_mtime_ns


def read_research_discovery_fields_compact_aware(
    report_path: Path,
) -> dict[str, Any] | None:
    """Invalidate JSON discovery cache when its compact companion changes."""

    resolved = str(report_path.resolve())
    stamp = _compact_report_stamp(report_path)
    previous = _COMPACT_DISCOVERY_STAMPS.get(resolved)
    if previous != stamp:
        for cache_key in list(_final_evaluation_controller._DISCOVERY_CACHE):
            if cache_key[0] == resolved:
                _final_evaluation_controller._DISCOVERY_CACHE.pop(cache_key, None)
        _COMPACT_DISCOVERY_STAMPS[resolved] = stamp
    return _ORIGINAL_RESEARCH_DISCOVERY_READER(report_path)


def _install_runtime_guards() -> None:
    """Install idempotent UI-process guards without affecting import-time tests."""

    global _RUNTIME_GUARDS_INSTALLED
    if _RUNTIME_GUARDS_INSTALLED:
        return
    _backtest_controller.discover_active_research_checkpoint = (
        discover_active_research_checkpoint_lock_aware
    )
    _final_evaluation_controller._read_research_discovery_fields = (
        read_research_discovery_fields_compact_aware
    )
    _RUNTIME_GUARDS_INSTALLED = True


def normalise_stale_backtest_status(
    status: Mapping[str, Any], reports_root: str | Path
) -> dict[str, Any]:
    """Expose an orphaned durable checkpoint as interrupted, never as running."""

    result = dict(status)
    if (
        result.get("mode") in _ACTIVE_BACKTEST_MODES
        and result.get("checkpoint_path")
        and not _run_lock_is_owned(reports_root)
    ):
        result.update(
            {
                "mode": "interrupted",
                "status_text": (
                    "Backtest-Checkpoint ist veraltet – kein aktiver Supervisor-Lock"
                ),
                "progress_visible": False,
                "error": "stale_checkpoint_without_active_run_lock",
                "stale_checkpoint": True,
            }
        )
    return result


def select_operator_view(
    *, data_running: bool, backtest_mode: str, runtime_phase: str | None = None
) -> str:
    """Return the one visible operator context for the current state."""

    if data_running or runtime_phase in _ACTIVE_DATA_PHASES:
        return "download"
    if backtest_mode in _ACTIVE_BACKTEST_MODES:
        return "backtest_running"
    if backtest_mode in _RESULT_BACKTEST_MODES:
        return "backtest_result"
    return "download"


def format_download_view(
    snapshot: Mapping[str, Any],
    runtime_status: Mapping[str, Any],
    last_run_status: Mapping[str, Any],
) -> str:
    """Format the complete data-check/download operator view."""

    readiness = _mapping(snapshot.get("data_readiness_report"))
    audit = _mapping(snapshot.get("kline_audit_status"))
    prep = _mapping(snapshot.get("data_prep_status"))
    inventory = _mapping(snapshot.get("inventory_status"))
    rows = snapshot.get("operator_data_status_rows")
    data_rows = rows if isinstance(rows, list) else []
    progress = _number(runtime_status.get("progress_pct"), 1)
    elapsed = _duration(runtime_status.get("elapsed_seconds"))
    phase = _text(runtime_status.get("phase"))
    execute_mode = str(runtime_status.get("mode", "dry_run")) == "execute"

    lines = [
        "DATEN PRÜFEN / AKTUALISIEREN",
        "",
        f"Status: {_download_status_text(phase)}",
        f"Modus: {'Prüfen und fehlende öffentliche Daten laden' if execute_mode else 'Nur prüfen – kein Download'}",
        f"Fortschritt: {progress} %",
        f"Laufzeit: {elapsed}",
        f"Gestartet: {_text(runtime_status.get('started_at'))}",
        f"Letzte Meldung: {_text(runtime_status.get('last_message'))}",
        "",
        "AKTUELLER SCHRITT",
        f"- Phase: {phase}",
        f"- Schritt: {_text(runtime_status.get('current_step'))}",
        f"- Task: {_text(runtime_status.get('current_task_id'))}",
        f"- Markt / Datenart: {_text(runtime_status.get('current_symbol'))} / {_text(runtime_status.get('current_data_type'))}",
        f"- Datei: {_text(runtime_status.get('current_file_name'))}",
        f"- Dateiindex: {_text(runtime_status.get('current_file_index'))} von {_text(runtime_status.get('planned_file_count'))}",
        "",
        "TASKS UND DATEIEN",
        (
            "- Tasks: "
            f"{_text(runtime_status.get('completed_tasks'))}/{_text(runtime_status.get('total_tasks'))} fertig, "
            f"{_text(runtime_status.get('skipped_tasks'))} übersprungen, "
            f"{_text(runtime_status.get('failed_tasks'))} Fehler"
        ),
        (
            "- Dateien: "
            f"{_text(runtime_status.get('completed_file_count'))}/{_text(runtime_status.get('planned_file_count'))} verarbeitet, "
            f"{_text(runtime_status.get('downloaded_file_count'))} neu geladen, "
            f"{_text(runtime_status.get('skipped_file_count'))} vorhanden/übersprungen, "
            f"{_text(runtime_status.get('failed_file_count'))} Fehler"
        ),
        (
            "- Plan: "
            f"{_text(prep.get('supported_download_task_count'))} unterstützte Downloads, "
            f"{_text(prep.get('unsupported_task_count'))} nicht unterstützt, "
            f"{_text(prep.get('live_collector_task_count'))} nur Live-Sammlung"
        ),
        "",
        "DATENABDECKUNG",
        f"- Data Gate: {_text(readiness.get('overall_status'))}",
        f"- Gesamtstand: {_number(snapshot.get('overall_data_progress_pct'), 2)} %",
    ]
    for row in data_rows:
        if not isinstance(row, Mapping):
            continue
        reason = str(row.get("reason") or "").strip()
        suffix = f" – {reason}" if reason else ""
        lines.append(
            f"- {_text(row.get('label'))}: {_text(row.get('files_text'))} Tage/Einheiten, "
            f"{_text(row.get('status'))}{suffix}"
        )

    lines.extend(
        [
            "",
            "QUALITÄTSPRÜFUNG ETHUSDC 1m",
            f"- Auditstatus: {_text(audit.get('audit_status'))}",
            f"- Beobachteter Zeitraum: {_text(audit.get('observed_start_utc'))} bis {_text(audit.get('observed_end_utc'))}",
            f"- Vollständige UTC-Tage: {_text(audit.get('complete_utc_days'))}",
            f"- Fehlende Tage: {_text(audit.get('missing_utc_days_count'))}",
            f"- Doppelte Zeilen: {_text(audit.get('duplicate_rows'))}",
            f"- Lücken: {_text(audit.get('gap_count'))}; größte Lücke {_text(audit.get('max_gap_seconds'))} Sekunden",
            f"- Backtest-ready: {_text(audit.get('backtest_ready'))}",
            "",
            "LETZTER DATENLAUF",
            f"- Status / Modus: {_text(last_run_status.get('last_run_status'))} / {_text(last_run_status.get('last_run_mode'))}",
            f"- Zeit: {_duration(last_run_status.get('last_run_duration_seconds'))}",
            f"- Readiness vorher/nachher: {_text(last_run_status.get('last_run_readiness_before'))} -> {_text(last_run_status.get('last_run_readiness_after'))}",
            f"- Zusammenfassung: {_text(last_run_status.get('last_run_summary_text'))}",
            f"- Nächster Blocker: {_text(last_run_status.get('last_run_next_blocker') or snapshot.get('backtest_blocker_summary'))}",
            f"- Fehler: {_text(last_run_status.get('error'))}",
            "",
            "PFAD UND SICHERHEIT",
            f"- Lokaler Datenpfad: {_text(inventory.get('local_root'))}",
            "- Während Datenprüfung/Download startet kein Backtest.",
            "- Keine Orders, keine Trading-API, keine API-Keys.",
        ]
    )
    return "\n".join(lines) + "\n"


def format_running_backtest_view(status: Mapping[str, Any]) -> str:
    """Format all useful progress information for a running research backtest."""

    latest = _mapping(status.get("latest_cycle"))
    best = _mapping(status.get("best_cycle"))
    completed = _text(status.get("completed_cycles"))
    maximum = _text(status.get("max_cycles"))
    lines = [
        "BACKTEST LÄUFT – TRAINING / VALIDATION / WALK-FORWARD",
        "",
        f"Status: {_text(status.get('status_text'))}",
        f"Fortschritt: {_number(status.get('progress_pct'), 1)} %",
        f"Zyklen: {completed}/{maximum} vollständig; aktiv {_text(status.get('active_cycle'))}",
        f"Laufzeit: {_duration(status.get('elapsed_seconds'))}",
        f"Start / letzte Aktualisierung: {_text(status.get('started_at_utc'))} / {_text(status.get('updated_at_utc'))}",
        f"Run-ID: {_text(status.get('run_id'))}",
        f"Branch / Commit: {_text(status.get('git_branch'))} / {_text(status.get('git_commit'))}",
        "",
        "LETZTER ABGESCHLOSSENER ZYKLUS",
        *_cycle_result_lines(latest),
    ]
    if best and best != latest:
        lines.extend(["", "BESTER ZWISCHENSTAND", *_cycle_result_lines(best)])
    lines.extend(
        [
            "",
            "LAUFKETTE UND SCHUTZ",
            f"- Kontext aktiv: {_text(status.get('context_enabled'))} (BTCUSDC und ETHBTC nur Kontext)",
            f"- Audit ausgewertet: {_text(status.get('audit_evaluated'))}",
            f"- Finaler Holdout ausgewertet: {_text(status.get('final_holdout_evaluated'))}",
            "- Portfolio: 100 USDC je Lot, ETHUSDC Spot LONG-only, kein Compounding.",
            "- Live / Paper / Testtrade / Orders bleiben gesperrt.",
            f"- Checkpoint: {_text(status.get('checkpoint_path'))}",
            f"- Konsolenlog: {_text(status.get('console_log_path'))}",
        ]
    )
    return "\n".join(lines) + "\n"


def format_backtest_result_view(status: Mapping[str, Any]) -> str:
    """Format the completed or failed research result without mixed data panels."""

    mode = str(status.get("mode", "failed"))
    if mode != "completed":
        latest = _mapping(status.get("latest_cycle"))
        return "\n".join(
            [
                "BACKTEST BEENDET – FEHLER / UNTERBRECHUNG",
                "",
                f"Status: {_text(status.get('status_text'))}",
                f"Run-ID: {_text(status.get('run_id'))}",
                f"Fortschritt: {_number(status.get('progress_pct'), 1)} %",
                f"Zyklen: {_text(status.get('completed_cycles'))}/{_text(status.get('max_cycles'))}",
                f"Laufzeit: {_duration(status.get('elapsed_seconds'))}",
                f"Fehler: {_text(status.get('error'))}",
                f"Child-Exit-Code: {_text(status.get('child_exit_code'))}",
                "",
                "LETZTER VERWERTBARER ZYKLUS",
                *_cycle_result_lines(latest),
                "",
                f"Checkpoint: {_text(status.get('checkpoint_path'))}",
                f"Konsolenlog: {_text(status.get('console_log_path'))}",
                "Ein neuer Backtest darf nur gestartet werden, wenn kein aktiver Run-Lock mehr besteht.",
            ]
        ) + "\n"

    final = _mapping(status.get("final_summary"))
    selected = _mapping(final.get("selected_candidate"))
    validation = _mapping(final.get("best_validation"))
    training = _mapping(final.get("full_training"))
    rolling = _mapping(final.get("rolling"))
    exits = _mapping(final.get("exit_summary"))
    failed_gates = final.get("quality_gate_failed_codes")
    gate_text = (
        ", ".join(str(value) for value in failed_gates)
        if isinstance(failed_gates, list) and failed_gates
        else "keine"
    )

    lines = [
        "BACKTEST ABGESCHLOSSEN – ERGEBNIS",
        "",
        f"Run-ID: {_text(status.get('run_id'))}",
        f"Branch / Commit: {_text(status.get('git_branch'))} / {_text(status.get('git_commit'))}",
        f"Laufzeit: {_duration(status.get('elapsed_seconds'))}",
        f"Zyklen: {_text(final.get('cycles_executed'))}/{_text(final.get('max_cycles'))}",
        f"Stop-Grund: {_text(final.get('stop_reason'))}",
        f"Freeze-Status: {_text(final.get('freeze_status'))}",
        f"Report: {_text(status.get('report_path'))}",
        "",
        "AUSGEWÄHLTER KANDIDAT",
        f"- ID: {_text(selected.get('candidate_id'))}",
        f"- Familie: {_text(selected.get('family'))}",
        f"- Parameter: {_format_parameters(selected.get('params'))}",
        "",
        "WALK-FORWARD-ERGEBNIS",
        f"- Netto pro Tag: {_usdc(final.get('wfv_net_usdc_per_day'))}",
        f"- Ziel: {_usdc(final.get('target_usdc_per_day'))} pro Tag; Abstand {_usdc(final.get('target_gap_usdc_per_day'))}",
        f"- Netto gesamt: {_usdc(final.get('wfv_net_profit_usdc'))}",
        f"- Trades: {_text(final.get('wfv_trade_count'))}; {_number(final.get('wfv_trades_per_day'), 4)} pro Tag",
        f"- Profit Factor: {_number(final.get('wfv_profit_factor'), 4)}",
        f"- Winrate: {_percent(final.get('wfv_winrate'))}",
        f"- Durchschnittlicher Trade: {_usdc(final.get('wfv_average_trade_usdc'))}",
        f"- Maximaler Drawdown: {_usdc(final.get('wfv_max_drawdown_usdc'))}",
        f"- Schlechtester Fold netto/Tag: {_usdc(final.get('wfv_worst_fold_net_usdc_per_day'))}",
        f"- Positive Folds: {_text(final.get('wfv_positive_fold_count'))}/6",
        f"- Gebühren: {_usdc(final.get('wfv_fees_usdc'))}",
        f"- Slippage: {_usdc(final.get('wfv_slippage_usdc'))}",
        f"- Gesamtkosten: {_usdc(final.get('wfv_cost_load_usdc'))}",
        "",
        "VALIDATION",
        f"- Netto pro Tag: {_usdc(validation.get('net_usdc_per_day'))}",
        f"- Netto gesamt: {_usdc(validation.get('net_profit_usdc'))}",
        f"- Trades / Trades pro Tag: {_text(validation.get('trade_count'))} / {_number(final.get('validation_trades_per_day'), 4)}",
        f"- Profit Factor: {_number(validation.get('profit_factor'), 4)}",
        f"- Winrate: {_percent(validation.get('winrate'))}",
        f"- Maximaler Drawdown: {_usdc(validation.get('max_drawdown_usdc'))}",
        "",
        "VOLLES TRAINING",
        f"- Netto pro Tag: {_usdc(training.get('net_usdc_per_day'))}",
        f"- Netto gesamt: {_usdc(training.get('net_profit_usdc'))}",
        f"- Trades / Trades pro Tag: {_text(training.get('trade_count'))} / {_number(final.get('full_training_trades_per_day'), 4)}",
        f"- Profit Factor: {_number(training.get('profit_factor'), 4)}",
        f"- Winrate: {_percent(training.get('winrate'))}",
        f"- Maximaler Drawdown: {_usdc(training.get('max_drawdown_usdc'))}",
        "",
        "ROLLING ORIGINS / ROBUSTHEIT",
        f"- Ø OOS netto pro Tag: {_usdc(rolling.get('average_oos_net_usdc_per_day'))}",
        f"- Schlechtester OOS netto pro Tag: {_usdc(rolling.get('worst_oos_net_usdc_per_day'))}",
        f"- Positive Origins: {_text(rolling.get('positive_origin_count'))}/{_text(rolling.get('origin_count'))}",
        f"- Rolling Trades/Tag: {_number(final.get('rolling_trades_per_day'), 4)}",
        "",
        "QUALITY GATES UND DIAGNOSE",
        f"- Quality Gate bestanden: {_text(final.get('quality_gate_passed'))}",
        f"- Fehlgeschlagene Gates: {gate_text}",
        f"- Qualifizierte Finalisten: {_text(final.get('qualified_finalists'))}",
        f"- Kontext aktiv: {_text(final.get('context_enabled'))}",
        f"- Kandidatenstufen: {_format_mapping(final.get('candidate_stage_totals'))}",
        f"- Exit-Gründe: {_format_mapping(exits)}",
        "",
        "SICHERHEIT / NÄCHSTER SCHRITT",
        f"- Audit ausgewertet: {_text(status.get('audit_evaluated'))}",
        f"- Finaler Holdout ausgewertet: {_text(status.get('final_holdout_evaluated'))}",
        "- Dieses Ergebnis ist Selection-/WFV-Evidenz, noch kein neuer versiegelter Final-Blindtest.",
        "- Live / Paper / Testtrade / Orders bleiben gesperrt.",
    ]
    return "\n".join(lines) + "\n"


class OperatorDashboardApp(_base_dashboard.DashboardApp):
    """Single existing dashboard with contextual operator presentation."""

    def __init__(
        self,
        root: tk.Tk,
        repository_root: Path | None = None,
        local_root: Path | None = None,
    ) -> None:
        _install_runtime_guards()
        self._refresh_gate = RefreshGate()
        super().__init__(root, repository_root=repository_root, local_root=local_root)

    def _build_widgets(self) -> None:
        super()._build_widgets()
        self._data_toolbar = self.load_button.master
        self._backtest_action_bar = self.training_button.master
        self._shadow_action_bar = self.shadow_start_button.master
        self._overview_frame = self.progress_bar.master
        self.status_text.configure(height=25)
        self.log_text.configure(height=9)
        self.root.minsize(940, 680)

    def refresh_status(self, *, log_refresh: bool = True) -> None:
        """Collect exactly one generation and keep it pending until Tk applies it."""

        generation = self._refresh_gate.begin()
        if generation is None:
            return
        data_running = bool(
            self.active_data_thread is not None and self.active_data_thread.is_alive()
        )
        inputs = {
            "data_prep_last_run_status": dict(self.last_run_status),
            "deployment_budget_usdc": self._selected_deployment_budget(),
            "training_research_status": dict(self.training_research_status),
            "final_evaluation_runtime_status": dict(
                self.final_evaluation_runtime_status
            ),
            "shadow_controller_status": dict(self.shadow_controller_status),
        }
        runtime_status = dict(self.current_runtime_status or {})

        def worker() -> None:
            try:
                snapshot = _base_dashboard.build_dashboard_snapshot(
                    self.repository_root,
                    self.local_root,
                    **inputs,
                    training_reports_root=self.training_reports_root,
                    final_reports_root=self.final_reports_root,
                    shadow_root=self.shadow_root,
                )
                display = _backtest_display.collect_backtest_display_status(
                    self.training_reports_root,
                    controller_status=inputs["training_research_status"],
                )
                display = normalise_stale_backtest_status(
                    display, self.training_reports_root
                )
                effective_runtime = runtime_status or dict(
                    snapshot["data_prep_runtime_status"]
                )
                view_mode = select_operator_view(
                    data_running=data_running,
                    backtest_mode=str(display.get("mode", "idle")),
                    runtime_phase=str(effective_runtime.get("phase", "idle")),
                )
                if view_mode == "backtest_running":
                    text = format_running_backtest_view(display)
                elif view_mode == "backtest_result":
                    text = format_backtest_result_view(display)
                else:
                    text = format_download_view(
                        snapshot,
                        effective_runtime,
                        inputs["data_prep_last_run_status"],
                    )
                payload: dict[str, object] = {
                    "generation": generation,
                    "snapshot": snapshot,
                    "display": display,
                    "runtime_status": effective_runtime,
                    "view_mode": view_mode,
                    "text": text,
                    "log_refresh": log_refresh,
                }
                if view_mode in {"backtest_running", "backtest_result"}:
                    payload["log_text"] = (
                        _backtest_display.format_backtest_log_for_display(display)
                    )
            except Exception as exc:  # defensive worker boundary
                payload = {
                    "generation": generation,
                    "error": f"Failed to collect dashboard snapshot: {exc}\n",
                }
            self.log_queue.put(("dashboard_refresh", payload))

        thread = threading.Thread(
            target=worker,
            name=f"ethusdc-dashboard-refresh-{generation}",
            daemon=True,
        )
        self.active_refresh_thread = thread
        thread.start()

    def _apply_dashboard_refresh(self, payload: dict[str, object]) -> None:
        """Apply only the current generation and switch to its one visible view."""

        try:
            generation = int(payload.get("generation", -1))
        except (TypeError, ValueError):
            return
        if not self._refresh_gate.finish(generation):
            return
        self.active_refresh_thread = None

        error = payload.get("error")
        if error is not None:
            text = str(error)
            self._log(text)
        else:
            snapshot = payload.get("snapshot")
            display = payload.get("display")
            runtime_status = payload.get("runtime_status")
            if not isinstance(snapshot, dict) or not isinstance(display, dict):
                self._log("Dashboard refresh returned an invalid payload.")
                return
            self.current_snapshot = snapshot
            self.backtest_display_status = display
            self._apply_product_status(snapshot)
            view_mode = str(payload.get("view_mode", "download"))
            if view_mode in {"backtest_running", "backtest_result"}:
                self._apply_backtest_display_status(display)
                log_text = payload.get("log_text")
                if isinstance(log_text, str):
                    self._replace_log_text(log_text)
            else:
                current = (
                    runtime_status
                    if isinstance(runtime_status, dict)
                    else snapshot["data_prep_runtime_status"]
                )
                self._apply_runtime_status(current)
                self._apply_overall_data_status(snapshot)
                self._apply_last_run_status(snapshot["data_prep_last_run_status"])
                self._set_progress_visible(True)
            self._set_context_layout(view_mode)
            text = str(payload.get("text", ""))

        self.status_text.configure(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert(tk.END, text)
        self.status_text.configure(state=tk.DISABLED)
        if payload.get("log_refresh") and payload.get("view_mode") == "download":
            self._log("Refreshed data/download status snapshot.")

    def _set_context_layout(self, view_mode: str) -> None:
        """Show only controls relevant to the active operator context."""

        if view_mode == "download":
            self._show_before_overview(self._data_toolbar)
            self._hide_frame(self._backtest_action_bar)
            self._hide_frame(self._shadow_action_bar)
            return
        if view_mode == "backtest_running":
            self._hide_frame(self._data_toolbar)
            self._hide_frame(self._backtest_action_bar)
            self._hide_frame(self._shadow_action_bar)
            return
        self._hide_frame(self._data_toolbar)
        self._show_before_overview(self._backtest_action_bar)
        self._hide_frame(self._shadow_action_bar)

    def _show_before_overview(self, frame: tk.Misc) -> None:
        if frame.winfo_manager():
            return
        frame.pack(fill=tk.X, before=self._overview_frame)

    @staticmethod
    def _hide_frame(frame: tk.Misc) -> None:
        if frame.winfo_manager():
            frame.pack_forget()


def _cycle_result_lines(row: Mapping[str, Any]) -> list[str]:
    if not row:
        return ["- Noch kein Zyklus vollständig abgeschlossen."]
    return [
        f"- Zyklus: {_text(row.get('cycle'))}/{_text(row.get('maximum'))}",
        (
            "- Kandidaten: "
            f"{_text(row.get('generated'))} erzeugt / "
            f"{_text(row.get('tested'))} getestet / "
            f"{_text(row.get('walk_forward'))} Walk-Forward / "
            f"{_text(row.get('finalists'))} Finalisten"
        ),
        f"- WFV netto pro Tag: {_usdc(row.get('wfv_net_usdc_per_day'))}",
        f"- Validation netto pro Tag: {_usdc(row.get('validation_net_usdc_per_day'))}",
        f"- Profit Factor: {_number(row.get('wfv_profit_factor'), 4)}",
        f"- Maximaler Drawdown: {_usdc(row.get('wfv_max_drawdown_usdc'))}",
        f"- Schlechtester Fold: {_usdc(row.get('worst_fold_net_usdc_per_day'))} pro Tag",
        f"- Positive Folds: {_text(row.get('positive_fold_count'))}/{_text(row.get('walk_forward_folds') or 6)}",
        f"- Gebühren + Slippage: {_usdc(row.get('wfv_cost_load'))}",
        f"- Quality Gate bestanden: {_text(row.get('quality_gate_passed'))}",
        f"- Kontext: {_text(row.get('context_enabled'))} ({_text(row.get('context_generated'))}/{_text(row.get('context_tested'))})",
    ]


def _download_status_text(phase: str) -> str:
    if phase == "downloading":
        return "Download läuft"
    if phase in _ACTIVE_DATA_PHASES:
        return "Datenprüfung läuft"
    if phase == "finished":
        return "Datenlauf abgeschlossen"
    if phase == "failed":
        return "Datenlauf fehlgeschlagen"
    return "Bereit / Datenstand anzeigen"


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: object) -> str:
    if value is None or value == "":
        return "noch nicht verfügbar"
    return str(value)


def _number(value: object, digits: int) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError, OverflowError):
        return "noch nicht verfügbar"


def _usdc(value: object) -> str:
    number = _number(value, 6)
    return number if number == "noch nicht verfügbar" else f"{number} USDC"


def _percent(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return "noch nicht verfügbar"
    if abs(number) <= 1.0:
        number *= 100.0
    return f"{number:.2f} %"


def _duration(value: object) -> str:
    try:
        seconds = max(0, int(float(value)))
    except (TypeError, ValueError, OverflowError):
        return "noch nicht verfügbar"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _format_mapping(value: object) -> str:
    if not isinstance(value, Mapping) or not value:
        return "noch nicht verfügbar"
    return ", ".join(f"{key}={item}" for key, item in sorted(value.items()))


def _format_parameters(value: object) -> str:
    if not isinstance(value, Mapping) or not value:
        return "noch nicht verfügbar"
    return ", ".join(f"{key}={item}" for key, item in sorted(value.items()))


def main() -> int:
    root = tk.Tk()
    OperatorDashboardApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OperatorDashboardApp",
    "RefreshGate",
    "discover_active_research_checkpoint_lock_aware",
    "format_backtest_result_view",
    "format_download_view",
    "format_running_backtest_view",
    "normalise_stale_backtest_status",
    "read_research_discovery_fields_compact_aware",
    "select_operator_view",
]
