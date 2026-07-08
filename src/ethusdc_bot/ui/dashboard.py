"""Tkinter local control dashboard for ETHUSDC_BotV3_Hermes.

This UI is status and downloader control only. It does not implement an engine,
strategy, backtest, paper trading, testtrade, live trading, orders, or API keys.
"""

from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Any

from ethusdc_bot.ui.dashboard_state import (
    BACKTEST_DISABLED_HINT,
    build_dashboard_snapshot,
    default_local_root,
    default_repository_root,
    format_snapshot_for_display,
)

DOWNLOAD_MODULE = "ethusdc_bot.data_pipeline.public_kline_downloader"


class DashboardApp:
    """Small safe tkinter dashboard."""

    def __init__(self, root: tk.Tk, repository_root: Path | None = None, local_root: Path | None = None):
        self.root = root
        self.repository_root = repository_root or default_repository_root()
        self.local_root = local_root or default_local_root()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.active_process: subprocess.Popen[str] | None = None

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
        ttk.Button(toolbar, text="Dry-Run 1095 Download Plan", command=self.start_dry_run).pack(
            side=tk.LEFT, padx=4
        )
        ttk.Button(toolbar, text="Start ETHUSDC 1095 Download", command=self.start_execute_download).pack(
            side=tk.LEFT, padx=4
        )
        backtest_button = ttk.Button(toolbar, text="Backtest starten", state=tk.DISABLED)
        backtest_button.pack(side=tk.LEFT, padx=4)

        hint = ttk.Label(toolbar, text=BACKTEST_DISABLED_HINT)
        hint.pack(side=tk.LEFT, padx=8)

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

    def start_dry_run(self) -> None:
        self._start_downloader(execute=False)

    def start_execute_download(self) -> None:
        self._start_downloader(execute=True)

    def _start_downloader(self, execute: bool) -> None:
        if self.active_process is not None and self.active_process.poll() is None:
            self._log(
                "A downloader process started by this UI is already running. "
                "No process was stopped. Existing separate terminal downloads are not touched."
            )
            return

        command = [
            sys.executable,
            "-m",
            DOWNLOAD_MODULE,
            "--last-days",
            "1095",
            "--raw-root",
            str(self.local_root),
        ]
        if execute:
            command.append("--execute")

        mode = "EXECUTE" if execute else "DRY-RUN"
        self._log(f"Starting {mode} downloader command: {' '.join(command)}")
        self.active_process = subprocess.Popen(
            command,
            cwd=str(self.repository_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        thread = threading.Thread(target=self._capture_process_output, args=(self.active_process,), daemon=True)
        thread.start()

    def _capture_process_output(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self.log_queue.put(line.rstrip("\n"))
        exit_code = process.wait()
        self.log_queue.put(f"Downloader process exited with code {exit_code}.")
        self.log_queue.put("__REFRESH_AFTER_PROCESS__")

    def _drain_log_queue(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if message == "__REFRESH_AFTER_PROCESS__":
                self.refresh_status()
            else:
                self._log(message)
        self.root.after(250, self._drain_log_queue)

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
