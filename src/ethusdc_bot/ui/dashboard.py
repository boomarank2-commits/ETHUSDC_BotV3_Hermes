"""Tkinter local control dashboard for ETHUSDC_BotV3_Hermes.

This UI is status and data-preparation control only. It does not implement an
engine, strategy, backtest, paper trading, testtrade, live trading, orders, or
API keys.
"""

from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from ethusdc_bot.ui.dashboard_state import (
    BACKTEST_DISABLED_HINT,
    build_dashboard_snapshot,
    default_local_root,
    default_repository_root,
    format_operator_summary_for_display,
)
from ethusdc_bot.ui.data_update_controller import (
    build_failed_data_prep_last_run_status,
    build_finished_data_prep_last_run_status,
    build_initial_data_prep_last_run_status,
    build_running_data_prep_last_run_status,
    build_data_prep_heartbeat_status,
    run_data_update_plan_async,
)


def build_operator_runtime_text(
    status: dict[str, object],
    seconds_since_file_event: int = 0,
) -> dict[str, str]:
    """Map technical runtime status to concise operator-facing labels."""

    phase = str(status.get("phase", "idle"))
    mode = str(status.get("mode", "dry_run"))
    if phase == "failed":
        bot_status = "Fehler"
    elif phase == "downloading":
        bot_status = "Lädt Daten"
    elif phase in {"checking_readiness", "planning", "dry_run", "refreshing_readiness"}:
        bot_status = "Prüft Daten"
    elif phase == "finished":
        bot_status = "Fertig"
    else:
        bot_status = "Bereit"

    if phase == "failed":
        activity_note = f"Fehler: {status.get('error') or status.get('last_message') or 'unbekannter Fehler'}"
    elif phase in {"downloading", "checking_readiness", "planning", "dry_run", "refreshing_readiness"}:
        if seconds_since_file_event >= 60:
            activity_note = "läuft noch, möglicherweise großer Download oder Netzwerk langsam"
        elif seconds_since_file_event >= 10:
            activity_note = "läuft noch, warte auf nächsten Datei-Fortschritt"
        else:
            activity_note = "läuft"
    elif phase == "finished":
        activity_note = "fertig"
    else:
        activity_note = "bereit"

    current_symbol = status.get("current_symbol") or ""
    current_data_type = status.get("current_data_type") or ""
    current_task = status.get("current_task_id") or "kein Task"
    current_file = status.get("current_file_name") or "warte auf Datei-Ereignis"
    completed_files = int(status.get("completed_file_count", 0) or 0)
    planned_files = int(status.get("planned_file_count", 0) or 0)
    return {
        "bot_status": bot_status,
        "mode": "lädt unterstützte öffentliche Daten" if mode == "execute" else "prüft nur, lädt nichts",
        "progress": f"{int(status.get('progress_pct', 0) or 0)}%",
        "current_download": f"{current_symbol} {current_data_type} - {current_task} - {current_file}".strip(),
        "files": (
            f"{completed_files}/{planned_files} "
            f"geladen {status.get('downloaded_file_count', 0)}, "
            f"übersprungen {status.get('skipped_file_count', 0)}, "
            f"Fehler {status.get('failed_file_count', 0)}"
        ),
        "elapsed": f"{status.get('elapsed_seconds', 0)} Sekunden",
        "activity_note": activity_note,
    }


class DashboardApp:
    """Small safe tkinter dashboard."""

    def __init__(self, root: tk.Tk, repository_root: Path | None = None, local_root: Path | None = None):
        self.root = root
        self.repository_root = repository_root or default_repository_root()
        self.local_root = local_root or default_local_root()
        self.log_queue: queue.Queue[object] = queue.Queue()
        self.active_data_thread: threading.Thread | None = None
        self.active_result_container: dict[str, object] | None = None
        self.data_prep_running = False
        self.last_run_status = build_initial_data_prep_last_run_status()
        self.current_runtime_status: dict[str, object] | None = None
        self.last_file_event_monotonic = time.monotonic()

        self.root.title("ETHUSDC Bot V3 Hermes - Local Control Dashboard")
        self.root.geometry("1100x760")

        self._build_widgets()
        self.refresh_status()
        self._drain_log_queue()
        self._heartbeat_active_run()

    def _build_widgets(self) -> None:
        title = ttk.Label(self.root, text="ETHUSDC Bot V3 Hermes", font=("Segoe UI", 18, "bold"), padding=8)
        title.pack(fill=tk.X)

        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill=tk.X)

        self.load_button = ttk.Button(
            toolbar,
            text="Daten prüfen & fehlende Daten laden",
            command=self.start_data_check_and_load,
        )
        self.load_button.pack(side=tk.LEFT, padx=4)
        self.check_button = ttk.Button(
            toolbar,
            text="Nur prüfen ohne Download",
            command=self.start_check_without_download,
        )
        self.check_button.pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Refresh", command=self.refresh_status).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Datenordner öffnen", command=self.open_data_folder).pack(side=tk.LEFT, padx=4)

        runtime_frame = ttk.LabelFrame(self.root, text="Übersicht", padding=10)
        runtime_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.bot_state_var = tk.StringVar(value="Bot-Status: Bereit")
        self.phase_var = tk.StringVar(value="Datenstatus: wird ermittelt")
        self.mode_var = tk.StringVar(value="Modus: bereit")
        self.progress_var = tk.IntVar(value=0)
        self.task_var = tk.StringVar(value="Aktueller Vorgang: keiner")
        self.count_var = tk.StringVar(value="Gesamtfortschritt: 0%")
        self.file_var = tk.StringVar(value="Dateien: 0/0")
        self.elapsed_var = tk.StringVar(value="Laufzeit: 0 Sekunden")
        self.engine_var = tk.StringVar(value="Backtest: gesperrt, Daten/Engine fehlen, keine Fake-Ergebnisse")
        self.last_run_var = tk.StringVar(value="Letzter Lauf: noch keiner")
        self.last_run_detail_var = tk.StringVar(value="Nächster Blocker: noch kein Lauf gestartet")
        for variable in (
            self.bot_state_var,
            self.phase_var,
            self.mode_var,
            self.count_var,
            self.task_var,
            self.file_var,
            self.elapsed_var,
            self.last_run_var,
            self.last_run_detail_var,
            self.engine_var,
        ):
            ttk.Label(runtime_frame, textvariable=variable).pack(anchor=tk.W)
        ttk.Progressbar(runtime_frame, maximum=100, variable=self.progress_var).pack(fill=tk.X, pady=(6, 0))

        status_frame = ttk.LabelFrame(self.root, text="Kurzübersicht", padding=8)
        status_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=12)
        self.status_text.pack(fill=tk.BOTH, expand=True)

        log_frame = ttk.LabelFrame(self.root, text="Kurzes Laufprotokoll", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=6)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def refresh_status(self) -> None:
        try:
            snapshot = build_dashboard_snapshot(
                self.repository_root,
                self.local_root,
                data_prep_last_run_status=self.last_run_status,
            )
            if self.active_data_thread is not None and self.active_data_thread.is_alive() and self.current_runtime_status:
                self._apply_runtime_status(self.current_runtime_status)
            else:
                self._apply_runtime_status(snapshot["data_prep_runtime_status"])
            self._apply_overall_data_status(snapshot)
            self._apply_last_run_status(snapshot["data_prep_last_run_status"])
            text = format_operator_summary_for_display(snapshot)
        except Exception as exc:  # pragma: no cover - defensive UI reporting
            text = f"Failed to collect dashboard snapshot: {exc}\n"
            self._log(text)
        self.status_text.configure(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert(tk.END, text)
        self.status_text.configure(state=tk.DISABLED)
        self._log("Refreshed status snapshot.")

    def open_data_folder(self) -> None:
        self._log(
            "Open Data Folder öffnet den externen Rohdatenordner: "
            "C:/TradingBot/data/ETHUSDC_BotV3_Hermes"
        )
        if not self.local_root.exists():
            message = f"Local data folder does not exist: {self.local_root}"
            self._log(message)
            messagebox.showwarning("Data folder missing", message)
            return
        self._log(f"Opening local data folder: {self.local_root}")
        if os.name == "nt":
            os.startfile(str(self.local_root))  # type: ignore[attr-defined]
        else:  # pragma: no cover - Windows is the target host
            subprocess.Popen(["xdg-open", str(self.local_root)])

    def start_data_check_and_load(self) -> None:
        if hasattr(self, "log_text"):
            self._log("Daten prüfen & fehlende Daten laden: supported public downloads enabled. Real engine bleibt gesperrt.")
        self._start_data_preparation(execute=True)

    def start_check_without_download(self) -> None:
        if hasattr(self, "log_text"):
            self._log("Nur prüfen ohne Download: Dry-run, keine Downloads werden ausgeführt.")
        self._start_data_preparation(execute=False)

    def start_data_prep_dry_run(self) -> None:
        self.start_check_without_download()

    def start_backtest_data_preparation(self) -> None:
        self.start_data_check_and_load()

    def _start_data_preparation(self, execute: bool) -> None:
        if self.active_data_thread is not None and self.active_data_thread.is_alive():
            self._log("A data-preparation workflow is already running. No process was stopped.")
            return

        self.data_prep_running = True
        self.last_file_event_monotonic = time.monotonic()
        self._set_data_buttons_enabled(False)
        mode = "EXECUTE" if execute else "DRY-RUN"
        self._log(f"Starting {mode} data preparation workflow.")
        initial_runtime = {
            "mode": "execute" if execute else "dry_run",
            "phase": "checking_readiness",
            "started_at": None,
            "current_task_id": None,
            "current_symbol": None,
            "current_data_type": None,
            "supported_download_task_count": 0,
            "completed_tasks": 0,
            "skipped_tasks": 0,
            "failed_tasks": 0,
            "last_message": "Datenlauf läuft gerade...",
        }
        self.last_run_status = build_running_data_prep_last_run_status(initial_runtime)
        self.current_runtime_status = dict(initial_runtime)
        self._apply_last_run_status(self.last_run_status)
        thread, result_container = run_data_update_plan_async(
            self.local_root,
            execute=execute,
            log_callback=self.log_queue.put,
            progress_callback=self.log_queue.put,
        )
        self.active_data_thread = thread
        self.active_result_container = result_container

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(message, dict):
                if message.get("current_file_name") or message.get("current_file_index"):
                    self.last_file_event_monotonic = time.monotonic()
                self.current_runtime_status = dict(message)
                self._apply_runtime_status(message)
                self.last_run_status = build_running_data_prep_last_run_status(message)
                self._apply_last_run_status(self.last_run_status)
            else:
                self._log(str(message))
        if self.active_data_thread is not None and not self.active_data_thread.is_alive():
            self._finalize_active_data_run()
            self.active_data_thread = None
            self.active_result_container = None
            self.current_runtime_status = None
            self.data_prep_running = False
            self._set_data_buttons_enabled(True)
            self.refresh_status()
        self.root.after(250, self._drain_log_queue)

    def _heartbeat_active_run(self) -> None:
        if (
            self.active_data_thread is not None
            and self.active_data_thread.is_alive()
            and self.current_runtime_status is not None
        ):
            heartbeat = build_data_prep_heartbeat_status(self.current_runtime_status)
            self.current_runtime_status = heartbeat
            self._apply_runtime_status(heartbeat)
            self.last_run_status = build_running_data_prep_last_run_status(heartbeat)
            self._apply_last_run_status(self.last_run_status)
        self.root.after(1000, self._heartbeat_active_run)

    def _finalize_active_data_run(self) -> None:
        if self.active_result_container is None:
            return
        result = self.active_result_container.get("result")
        error = self.active_result_container.get("error")
        if isinstance(result, dict):
            self.last_run_status = build_finished_data_prep_last_run_status(result)
        elif error is not None:
            self.last_run_status = build_failed_data_prep_last_run_status(self.last_run_status, error)
        self._apply_last_run_status(self.last_run_status)

    def _apply_runtime_status(self, status: dict[str, object]) -> None:
        seconds_since_file_event = int(time.monotonic() - self.last_file_event_monotonic)
        text = build_operator_runtime_text(status, seconds_since_file_event=seconds_since_file_event)
        self.bot_state_var.set(f"Bot-Status: {text['bot_status']} ({text['activity_note']})")
        self.phase_var.set(f"Datenstatus: {text['mode']}")
        self.mode_var.set(f"Modus: {text['mode']}")
        self.task_var.set(f"Aktueller Lauf: {text['progress']} seit Start - {text['current_download']}")
        self.file_var.set(f"Dateien: {text['files']}")
        self.elapsed_var.set(f"Laufzeit: {text['elapsed']}")
        self.engine_var.set("Backtest: gesperrt, weil Daten/Engine fehlen. Keine Fake-Ergebnisse.")

    def _apply_overall_data_status(self, snapshot: dict[str, object]) -> None:
        progress = float(snapshot.get("overall_data_progress_pct", 0) or 0)
        self.progress_var.set(int(progress))
        self.count_var.set(f"Gesamtdatenstand: {progress}%")

    def _apply_last_run_status(self, status: dict[str, object]) -> None:
        self.last_run_var.set(
            "Letzter Lauf: "
            f"{status.get('last_run_status')} / {status.get('last_run_mode')} / "
            f"{status.get('last_run_duration_seconds')}s"
        )
        self.last_run_detail_var.set(f"Nächster Blocker: {status.get('last_run_next_blocker')}")
        if status.get("last_run_status") == "finished":
            self.bot_state_var.set("Bot-Status: Fertig")
        elif status.get("last_run_status") == "failed":
            self.bot_state_var.set(f"Bot-Status: Fehler ({status.get('error')})")

    def _set_data_buttons_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.load_button.configure(state=state)
        self.check_button.configure(state=state)

    def _log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message.rstrip() + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)


def main() -> int:
    root = tk.Tk()
    DashboardApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
