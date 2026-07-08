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
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from ethusdc_bot.ui.dashboard_state import (
    BACKTEST_DISABLED_HINT,
    build_dashboard_snapshot,
    default_local_root,
    default_repository_root,
    format_snapshot_for_display,
)
from ethusdc_bot.ui.data_update_controller import run_data_update_plan_async


class DashboardApp:
    """Small safe tkinter dashboard."""

    def __init__(self, root: tk.Tk, repository_root: Path | None = None, local_root: Path | None = None):
        self.root = root
        self.repository_root = repository_root or default_repository_root()
        self.local_root = local_root or default_local_root()
        self.log_queue: queue.Queue[object] = queue.Queue()
        self.active_data_thread: threading.Thread | None = None
        self.data_prep_running = False

        self.root.title("ETHUSDC Bot V3 Hermes - Local Control Dashboard")
        self.root.geometry("1100x760")

        self._build_widgets()
        self.refresh_status()
        self._drain_log_queue()

    def _build_widgets(self) -> None:
        toolbar = ttk.Frame(self.root, padding=8)
        toolbar.pack(fill=tk.X)

        ttk.Button(toolbar, text="Refresh Status", command=self.refresh_status).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Open Data Folder", command=self.open_data_folder).pack(side=tk.LEFT, padx=4)
        self.data_prep_button = ttk.Button(toolbar, text="Daten prüfen (Dry-run)", command=self.start_data_prep_dry_run)
        self.data_prep_button.pack(side=tk.LEFT, padx=4)
        self.backtest_button = ttk.Button(
            toolbar,
            text="Backtest starten / Daten laden",
            command=self.start_backtest_data_preparation,
        )
        self.backtest_button.pack(side=tk.LEFT, padx=4)

        hint = ttk.Label(toolbar, text=BACKTEST_DISABLED_HINT)
        hint.pack(side=tk.LEFT, padx=8)

        runtime_frame = ttk.LabelFrame(self.root, text="Bot-Zustand / Data Prep Fortschritt", padding=8)
        runtime_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.bot_state_var = tk.StringVar(value="Bot-Zustand: idle")
        self.phase_var = tk.StringVar(value="Data Prep Phase: idle")
        self.mode_var = tk.StringVar(value="Modus: Dry-run")
        self.progress_var = tk.IntVar(value=0)
        self.task_var = tk.StringVar(value="Aktueller Task: none")
        self.count_var = tk.StringVar(value="Tasks: 0 / 0")
        self.engine_var = tk.StringVar(value="Backtest-Engine: locked")
        for variable in (
            self.bot_state_var,
            self.phase_var,
            self.mode_var,
            self.task_var,
            self.count_var,
            self.engine_var,
        ):
            ttk.Label(runtime_frame, textvariable=variable).pack(anchor=tk.W)
        ttk.Progressbar(runtime_frame, maximum=100, variable=self.progress_var).pack(fill=tk.X, pady=(4, 0))

        panes = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        status_frame = ttk.LabelFrame(panes, text="Status")
        log_frame = ttk.LabelFrame(panes, text="Log")
        panes.add(status_frame, weight=3)
        panes.add(log_frame, weight=2)

        self.status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=24)
        self.status_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=14)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def refresh_status(self) -> None:
        try:
            snapshot = build_dashboard_snapshot(self.repository_root, self.local_root)
            self._apply_runtime_status(snapshot["data_prep_runtime_status"])
            text = format_snapshot_for_display(snapshot)
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

    def start_data_prep_dry_run(self) -> None:
        self._start_data_preparation(execute=False)

    def start_backtest_data_preparation(self) -> None:
        self._log("Backtest start currently runs data preparation only. Real engine start is still locked.")
        self._start_data_preparation(execute=True)

    def _start_data_preparation(self, execute: bool) -> None:
        if self.active_data_thread is not None and self.active_data_thread.is_alive():
            self._log("A data-preparation workflow is already running. No process was stopped.")
            return

        self.data_prep_running = True
        self._set_data_buttons_enabled(False)
        mode = "EXECUTE" if execute else "DRY-RUN"
        self._log(f"Starting {mode} data preparation workflow.")
        thread, _result_container = run_data_update_plan_async(
            self.local_root,
            execute=execute,
            log_callback=self.log_queue.put,
            progress_callback=self.log_queue.put,
        )
        self.active_data_thread = thread

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(message, dict):
                self._apply_runtime_status(message)
            else:
                self._log(str(message))
        if self.active_data_thread is not None and not self.active_data_thread.is_alive():
            self.active_data_thread = None
            self.data_prep_running = False
            self._set_data_buttons_enabled(True)
            self.refresh_status()
        self.root.after(250, self._drain_log_queue)

    def _apply_runtime_status(self, status: dict[str, object]) -> None:
        mode = "Download" if status.get("mode") == "execute" else "Dry-run"
        task = status.get("current_task_id") or "none"
        completed = status.get("completed_tasks", 0)
        total = status.get("total_tasks", 0)
        self.bot_state_var.set(f"Bot-Zustand: {status.get('last_message', 'unknown')}")
        self.phase_var.set(f"Data Prep Phase: {status.get('phase', 'unknown')}")
        self.mode_var.set(f"Modus: {mode}")
        self.progress_var.set(int(status.get("progress_pct", 0)))
        self.task_var.set(f"Aktueller Task: {task}")
        self.count_var.set(f"Tasks: {completed} / {total}")
        self.engine_var.set("Backtest-Engine: locked (echte Engine nicht gestartet)")

    def _set_data_buttons_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.data_prep_button.configure(state=state)
        self.backtest_button.configure(state=state)

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
