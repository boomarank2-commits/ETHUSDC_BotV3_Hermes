"""Tkinter local control dashboard for ETHUSDC_BotV3_Hermes.

This UI controls public-data preparation, Protocol-v2 training/WFV research,
and explicit adoption of a verified final report into order-free Shadow mode.
It has no live/paper/testtrade unlock, account access, API keys, or orders.
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

from ethusdc_bot.portfolio import ALLOWED_DEPLOYMENT_BUDGETS_USDC
from ethusdc_bot.shadow.adoption import ShadowAdoptionError, adopt_for_shadow
from ethusdc_bot.ui.backtest_display import (
    collect_backtest_display_status,
    format_backtest_log_for_display,
    format_backtest_summary_for_display,
)
from ethusdc_bot.ui.backtest_controller import (
    TrainingResearchController,
    build_initial_training_research_status,
)
from ethusdc_bot.ui.final_evaluation_controller import (
    FinalEvaluationController,
    build_initial_final_evaluation_status,
)
from ethusdc_bot.ui.shadow_controller import (
    ShadowController,
    build_initial_shadow_status,
)
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
        self.active_refresh_thread: threading.Thread | None = None
        self.active_result_container: dict[str, object] | None = None
        self.data_prep_running = False
        self.last_run_status = build_initial_data_prep_last_run_status()
        self.current_runtime_status: dict[str, object] | None = None
        self.last_file_event_monotonic = time.monotonic()
        self.training_research_controller = TrainingResearchController()
        self.training_research_status = build_initial_training_research_status()
        self.backtest_display_status: dict[str, object] | None = None
        self.final_evaluation_controller = FinalEvaluationController()
        self.final_evaluation_runtime_status = build_initial_final_evaluation_status()
        self.shadow_controller = ShadowController()
        self.shadow_controller_status = build_initial_shadow_status()
        self.current_snapshot: dict[str, object] | None = None
        self.training_reports_root = self.local_root / "runtime" / "reports" / "research_loop"
        self.reports_root = self.local_root / "runtime" / "reports"
        self.final_reports_root = self.local_root / "runtime" / "reports" / "sealed_holdout_final"
        self.shadow_root = self.local_root / "runtime" / "shadow"

        self.root.title("ETHUSDC Bot V3 Hermes - Local Control Dashboard")
        self.root.geometry("1180x900")

        self._build_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.close_dashboard)
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
        action_bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        action_bar.pack(fill=tk.X)
        self.training_button = ttk.Button(
            action_bar,
            text="Backtest starten (Training/WFV)",
            command=self.start_training_research,
        )
        self.training_button.pack(side=tk.LEFT, padx=4)
        self.final_evaluation_button = ttk.Button(
            action_bar,
            text="Finaltest einmalig ausfuehren",
            command=self.start_sealed_final_evaluation,
        )
        self.final_evaluation_button.pack(side=tk.LEFT, padx=4)
        ttk.Label(action_bar, text="Deployment-Budget:").pack(
            side=tk.LEFT, padx=(16, 4)
        )
        self.deployment_budget_var = tk.StringVar(value="100")
        self.deployment_budget_combo = ttk.Combobox(
            action_bar,
            textvariable=self.deployment_budget_var,
            values=[str(value) for value in ALLOWED_DEPLOYMENT_BUDGETS_USDC],
            state="readonly",
            width=8,
        )
        self.deployment_budget_combo.pack(side=tk.LEFT, padx=4)
        self.deployment_budget_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self.refresh_status()
        )
        ttk.Label(action_bar, text="USDC (immer 100 USDC je Lot)").pack(
            side=tk.LEFT, padx=4
        )
        self.adopt_shadow_button = ttk.Button(
            action_bar,
            text="Backtest uebernehmen (nur Shadow)",
            command=self.adopt_verified_final_to_shadow,
        )
        self.adopt_shadow_button.pack(side=tk.LEFT, padx=(16, 4))

        shadow_action_bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        shadow_action_bar.pack(fill=tk.X)
        ttk.Label(
            shadow_action_bar,
            text="Oeffentliche ETHUSDC-Daten / nur hypothetischer Shadow:",
        ).pack(side=tk.LEFT, padx=4)
        self.shadow_start_button = ttk.Button(
            shadow_action_bar,
            text="Shadow starten/fortsetzen",
            command=self.start_shadow_runtime,
        )
        self.shadow_start_button.pack(side=tk.LEFT, padx=4)
        self.shadow_stop_button = ttk.Button(
            shadow_action_bar,
            text="Shadow stoppen",
            command=self.stop_shadow_runtime,
        )
        self.shadow_stop_button.pack(side=tk.LEFT, padx=4)
        ttk.Label(
            shadow_action_bar,
            text="Keine Orders | keine API-Keys | kein Konto-Zugriff",
        ).pack(side=tk.LEFT, padx=(16, 4))

        runtime_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        self.bot_state_var = tk.StringVar(value="Bot-Status: Bereit")
        self.phase_var = tk.StringVar(value="Datenstatus: wird ermittelt")
        self.mode_var = tk.StringVar(value="Modus: bereit")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.task_var = tk.StringVar(value="Aktueller Vorgang: keiner")
        self.count_var = tk.StringVar(value="Gesamtfortschritt: 0%")
        self.file_var = tk.StringVar(value="Dateien: 0/0")
        self.elapsed_var = tk.StringVar(value="Laufzeit: 0 Sekunden")
        self.engine_var = tk.StringVar(value="Backtest: gesperrt, Daten/Engine fehlen, keine Fake-Ergebnisse")
        self.last_run_var = tk.StringVar(value="Letzter Lauf: noch keiner")
        self.last_run_detail_var = tk.StringVar(value="Nächster Blocker: noch kein Lauf gestartet")
        self.portfolio_var = tk.StringVar(value="Portfolio: 100 USDC / 1 Lot")
        self.final_var = tk.StringVar(value="Final-Ampel: kein Finalbericht")
        self.shadow_var = tk.StringVar(value="Shadow: noch nicht uebernommen; Orders aus")
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
            self.portfolio_var,
            self.final_var,
            self.shadow_var,
        ):
            ttk.Label(runtime_frame, textvariable=variable).pack(anchor=tk.W)
        self.progress_bar = ttk.Progressbar(
            runtime_frame, maximum=100, variable=self.progress_var
        )
        self.progress_bar.pack(fill=tk.X, pady=(6, 0))

        status_frame = ttk.LabelFrame(self.root, text="Kurzübersicht", padding=8)
        status_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.status_text = scrolledtext.ScrolledText(status_frame, wrap=tk.WORD, height=12)
        self.status_text.pack(fill=tk.BOTH, expand=True)

        log_frame = ttk.LabelFrame(self.root, text="Kurzes Laufprotokoll", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 8))
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=6)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def refresh_status(self, *, log_refresh: bool = True) -> None:
        """Request a status refresh without running file scans on Tk's thread."""

        if self.active_refresh_thread is not None and self.active_refresh_thread.is_alive():
            return
        data_running = bool(
            self.active_data_thread is not None and self.active_data_thread.is_alive()
        )
        inputs = {
            "data_prep_last_run_status": dict(self.last_run_status),
            "deployment_budget_usdc": self._selected_deployment_budget(),
            "training_research_status": dict(self.training_research_status),
            "final_evaluation_runtime_status": dict(self.final_evaluation_runtime_status),
            "shadow_controller_status": dict(self.shadow_controller_status),
        }

        def worker() -> None:
            try:
                snapshot = build_dashboard_snapshot(
                    self.repository_root,
                    self.local_root,
                    **inputs,
                    training_reports_root=self.training_reports_root,
                    final_reports_root=self.final_reports_root,
                    shadow_root=self.shadow_root,
                )
                display = collect_backtest_display_status(
                    self.training_reports_root,
                    controller_status=inputs["training_research_status"],
                )
                show_backtest = not data_running and display.get("mode") != "idle"
                payload: dict[str, object] = {
                    "snapshot": snapshot,
                    "display": display,
                    "show_backtest": show_backtest,
                    "log_refresh": log_refresh,
                }
                if show_backtest:
                    payload["text"] = format_backtest_summary_for_display(display)
                    payload["log_text"] = format_backtest_log_for_display(display)
                else:
                    payload["text"] = format_operator_summary_for_display(snapshot)
            except Exception as exc:  # defensive worker boundary
                payload = {"error": f"Failed to collect dashboard snapshot: {exc}\n"}
            self.log_queue.put(("dashboard_refresh", payload))

        thread = threading.Thread(
            target=worker,
            name="ethusdc-dashboard-refresh",
            daemon=True,
        )
        self.active_refresh_thread = thread
        thread.start()

    def _apply_dashboard_refresh(self, payload: dict[str, object]) -> None:
        """Apply one completed background refresh on Tk's main thread."""

        self.active_refresh_thread = None
        error = payload.get("error")
        if error is not None:
            text = str(error)
            self._log(text)
        else:
            snapshot = payload["snapshot"]
            display = payload["display"]
            if not isinstance(snapshot, dict) or not isinstance(display, dict):
                self._log("Dashboard refresh returned an invalid payload.")
                return
            self.current_snapshot = snapshot
            self.backtest_display_status = display
            show_backtest = bool(payload.get("show_backtest"))
            self._apply_product_status(snapshot)
            if show_backtest:
                self._apply_backtest_display_status(display)
                log_text = payload.get("log_text")
                if isinstance(log_text, str):
                    self._replace_log_text(log_text)
            else:
                data_running = bool(
                    self.active_data_thread is not None
                    and self.active_data_thread.is_alive()
                )
                if data_running and self.current_runtime_status:
                    self._apply_runtime_status(self.current_runtime_status)
                else:
                    self._apply_runtime_status(snapshot["data_prep_runtime_status"])
                self._apply_overall_data_status(snapshot)
                self._apply_last_run_status(snapshot["data_prep_last_run_status"])
                self._set_progress_visible(True)
            text = str(payload.get("text", ""))
        self.status_text.configure(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert(tk.END, text)
        self.status_text.configure(state=tk.DISABLED)
        if payload.get("log_refresh") and not payload.get("show_backtest"):
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

    def start_training_research(self) -> None:
        """Start canonical training/validation/WFV without opening the holdout."""

        if self.final_evaluation_controller.is_running:
            messagebox.showwarning(
                "Finaltest aktiv",
                "Bitte den irreversiblen Finaltest zuerst beenden lassen.",
            )
            return
        if self.active_data_thread is not None and self.active_data_thread.is_alive():
            messagebox.showwarning(
                "Datenlauf aktiv",
                "Bitte den laufenden Datenprozess zuerst beenden lassen.",
            )
            return
        if self.training_research_controller.is_running:
            self._log("Training/WFV research is already running.")
            return
        durable_display = getattr(self, "backtest_display_status", None) or {}
        if durable_display.get("mode") in {"starting", "running"}:
            self._log(
                f"Durable Research-Lauf {durable_display.get('run_id') or 'unbekannt'} "
                "ist bereits aktiv; kein zweiter Supervisor wurde gestartet."
            )
            return
        snapshot = build_dashboard_snapshot(
            self.repository_root,
            self.local_root,
            data_prep_last_run_status=self.last_run_status,
            deployment_budget_usdc=self._selected_deployment_budget(),
            training_research_status=self.training_research_status,
            final_evaluation_runtime_status=self.final_evaluation_runtime_status,
            shadow_controller_status=self.shadow_controller_status,
            training_reports_root=self.training_reports_root,
            final_reports_root=self.final_reports_root,
            shadow_root=self.shadow_root,
        )
        if not snapshot["ui_status"]["backtest_start_button"]["enabled"]:
            messagebox.showwarning(
                "Training/WFV gesperrt",
                str(snapshot["backtest_blocker_summary"]),
            )
            return
        self._log(
            "Starting PR12 production research: UI -> Windows starter -> "
            "research supervisor -> context-enabled Protocol-v2 runner. "
            "No V1/legacy runner; the sealed final holdout remains closed."
        )
        try:
            _thread, container = self.training_research_controller.start(
                self.local_root,
                self.training_reports_root,
                status_callback=lambda status: self.log_queue.put(
                    ("training_research", status)
                ),
            )
        except Exception as exc:
            self._log(f"Could not start training/WFV: {exc}")
            messagebox.showerror("Training/WFV Fehler", str(exc))
            return
        self.training_research_status = dict(container["status"])
        self._apply_training_research_status(self.training_research_status)
        self._set_data_buttons_enabled(False)

    def start_sealed_final_evaluation(self) -> None:
        """Run the explicitly confirmed irreversible one-shot holdout step."""

        if self.training_research_controller.is_running:
            messagebox.showwarning(
                "Training/WFV aktiv",
                "Bitte die laufende Training/WFV-Forschung zuerst beenden lassen.",
            )
            return
        if self.final_evaluation_controller.is_running:
            self._log("Sealed final evaluation is already running.")
            return
        snapshot = build_dashboard_snapshot(
            self.repository_root,
            self.local_root,
            data_prep_last_run_status=self.last_run_status,
            deployment_budget_usdc=self._selected_deployment_budget(),
            training_research_status=self.training_research_status,
            final_evaluation_runtime_status=self.final_evaluation_runtime_status,
            shadow_controller_status=self.shadow_controller_status,
            training_reports_root=self.training_reports_root,
            final_reports_root=self.final_reports_root,
            shadow_root=self.shadow_root,
        )
        button = snapshot["ui_status"]["sealed_final_button"]
        source = button.get("source_report_path")
        if not button.get("enabled") or not isinstance(source, str):
            messagebox.showwarning(
                "Finaltest gesperrt",
                "Kein kanonisch eingefrorener Kandidat mit ungeoeffnetem Holdout verfuegbar.",
            )
            return
        confirmed = messagebox.askyesno(
            "Irreversiblen Finaltest ausfuehren",
            (
                "Der versiegelte 365-Tage-Holdout wird genau einmal geoeffnet. "
                "Vor dem Datenzugriff entsteht ein permanenter Claim. Auch nach einem "
                "Fehler darf dieser Lauf nicht wiederholt werden. Fortfahren?\n\n"
                "Keine Orders, keine Trading-API, keine API-Keys."
            ),
        )
        if not confirmed:
            return
        try:
            _thread, container = self.final_evaluation_controller.start(
                source,
                self.local_root,
                self.reports_root,
                status_callback=lambda status: self.log_queue.put(
                    ("final_evaluation", status)
                ),
            )
        except Exception as exc:
            self._log(f"Could not start sealed final evaluation: {exc}")
            messagebox.showerror("Finaltest Fehler", str(exc))
            return
        self.final_evaluation_runtime_status = dict(container["status"])
        self._apply_final_evaluation_runtime_status(
            self.final_evaluation_runtime_status
        )
        self._set_data_buttons_enabled(False)

    def adopt_verified_final_to_shadow(self) -> None:
        """Adopt one green/yellow final report without starting real trading."""

        snapshot = build_dashboard_snapshot(
            self.repository_root,
            self.local_root,
            data_prep_last_run_status=self.last_run_status,
            deployment_budget_usdc=self._selected_deployment_budget(),
            training_research_status=self.training_research_status,
            final_evaluation_runtime_status=self.final_evaluation_runtime_status,
            shadow_controller_status=self.shadow_controller_status,
            training_reports_root=self.training_reports_root,
            final_reports_root=self.final_reports_root,
            shadow_root=self.shadow_root,
        )
        button = snapshot["ui_status"]["shadow_adopt_button"]
        report_path = button.get("report_path")
        if not button.get("enabled") or not isinstance(report_path, str):
            messagebox.showwarning(
                "Shadow-Uebernahme gesperrt",
                "Es gibt keinen frisch verifizierten gruenen oder gelben Finalbericht.",
            )
            return
        budget = self._selected_deployment_budget()
        confirmed = messagebox.askyesno(
            "Nur Shadow uebernehmen",
            (
                f"Finalbericht mit {budget} USDC Deployment-Budget uebernehmen?\n\n"
                "Es werden ausschliesslich hypothetische Trades vorbereitet. "
                "Keine Orders, keine Trading-API, keine API-Keys, kein Live-Handel."
            ),
        )
        if not confirmed:
            return
        try:
            result = adopt_for_shadow(report_path, budget, self.shadow_root)
        except (OSError, ValueError, ShadowAdoptionError) as exc:
            self._log(f"Shadow adoption failed closed: {exc}")
            messagebox.showerror("Shadow-Uebernahme fehlgeschlagen", str(exc))
            return
        self._log(
            f"Adopted {result.deployment['deployment_id']} into stopped order-free Shadow state."
        )
        messagebox.showinfo(
            "Shadow uebernommen",
            "Kandidat wurde orderfrei uebernommen und bleibt gestoppt. Keine echte Order wurde erzeugt.",
        )
        self.refresh_status()

    def start_shadow_runtime(self) -> None:
        """Explicitly start or resume public-data-only hypothetical replay."""

        if self.shadow_controller.is_running:
            self._log("Shadow public-data runtime is already running.")
            return
        snapshot = build_dashboard_snapshot(
            self.repository_root,
            self.local_root,
            data_prep_last_run_status=self.last_run_status,
            deployment_budget_usdc=self._selected_deployment_budget(),
            training_research_status=self.training_research_status,
            final_evaluation_runtime_status=self.final_evaluation_runtime_status,
            shadow_controller_status=self.shadow_controller_status,
            training_reports_root=self.training_reports_root,
            final_reports_root=self.final_reports_root,
            shadow_root=self.shadow_root,
        )
        button = snapshot["ui_status"]["shadow_start_button"]
        deployment_dir = button.get("deployment_dir")
        if not button.get("enabled") or not isinstance(deployment_dir, str):
            messagebox.showwarning(
                "Shadow-Start gesperrt",
                (
                    "Kein gueltiges gestopptes/fortsetzbares Shadow-Deployment. "
                    "Bei Datenintegritaetsfehlern bleibt Shadow absichtlich pausiert."
                ),
            )
            return
        try:
            _thread, container = self.shadow_controller.start(
                deployment_dir,
                status_callback=lambda status: self.log_queue.put(
                    ("shadow_controller", status)
                ),
            )
        except Exception as exc:
            self._log(f"Could not start public Shadow runtime: {exc}")
            messagebox.showerror("Shadow-Start fehlgeschlagen", str(exc))
            return
        self.shadow_controller_status = dict(container["status"])
        self._apply_shadow_controller_status(self.shadow_controller_status)
        self.refresh_status()

    def stop_shadow_runtime(self) -> None:
        """Cooperatively stop the poller without closing hypothetical lots."""

        self.shadow_controller_status = self.shadow_controller.stop()
        self._apply_shadow_controller_status(self.shadow_controller_status)
        self.refresh_status()

    def close_dashboard(self) -> None:
        """Request an orderly Shadow stop before closing the local UI."""

        if self.shadow_controller.is_running:
            self.shadow_controller_status = self.shadow_controller.stop()
            self._log("Dashboard closes after the public Shadow worker stops.")
            self._wait_for_shadow_shutdown(0)
            return
        self.root.destroy()

    def _wait_for_shadow_shutdown(self, attempt: int) -> None:
        if not self.shadow_controller.is_running or attempt >= 120:
            self.root.destroy()
            return
        self.root.after(100, lambda: self._wait_for_shadow_shutdown(attempt + 1))

    def _selected_deployment_budget(self) -> int:
        value = getattr(self, "deployment_budget_var", None)
        raw = value.get() if value is not None else "100"
        try:
            budget = int(raw)
        except (TypeError, ValueError):
            return 100
        return budget if budget in ALLOWED_DEPLOYMENT_BUDGETS_USDC else 100

    def _start_data_preparation(self, execute: bool) -> None:
        if self.active_data_thread is not None and self.active_data_thread.is_alive():
            self._log("A data-preparation workflow is already running. No process was stopped.")
            return
        research_controller = getattr(self, "training_research_controller", None)
        if research_controller is not None and research_controller.is_running:
            self._log("Training/WFV is running; data preparation was not started.")
            return
        final_controller = getattr(self, "final_evaluation_controller", None)
        if final_controller is not None and final_controller.is_running:
            self._log("Sealed final evaluation is running; data preparation was not started.")
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
        """Apply worker messages without allowing one bad payload to stall Tk."""

        try:
            self._drain_log_queue_impl()
        except Exception as exc:  # defensive UI boundary; workers must not freeze the view
            self._log(f"UI-Queue-Fehler: {exc}")
        finally:
            self.root.after(250, self._drain_log_queue)

    def _drain_log_queue_impl(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if (
                isinstance(message, tuple)
                and len(message) == 2
                and message[0] == "dashboard_refresh"
                and isinstance(message[1], dict)
            ):
                self._apply_dashboard_refresh(message[1])
                continue
            if (
                isinstance(message, tuple)
                and len(message) == 2
                and message[0] == "shadow_controller"
                and isinstance(message[1], dict)
            ):
                self.shadow_controller_status = dict(message[1])
                self._apply_shadow_controller_status(
                    self.shadow_controller_status
                )
                self.refresh_status()
                continue
            if (
                isinstance(message, tuple)
                and len(message) == 2
                and message[0] == "final_evaluation"
                and isinstance(message[1], dict)
            ):
                self.final_evaluation_runtime_status = dict(message[1])
                self._apply_final_evaluation_runtime_status(
                    self.final_evaluation_runtime_status
                )
                if not self.final_evaluation_runtime_status.get("running"):
                    self._set_data_buttons_enabled(True)
                    self.refresh_status()
                continue
            if (
                isinstance(message, tuple)
                and len(message) == 2
                and message[0] == "training_research"
                and isinstance(message[1], dict)
            ):
                self.training_research_status = dict(message[1])
                self._apply_training_research_status(self.training_research_status)
                if not self.training_research_status.get("running"):
                    self._set_data_buttons_enabled(True)
                    self.refresh_status()
                continue
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

    def _heartbeat_active_run(self) -> None:
        data_running = bool(
            self.active_data_thread is not None
            and self.active_data_thread.is_alive()
            and self.current_runtime_status is not None
        )
        if data_running:
            heartbeat = build_data_prep_heartbeat_status(self.current_runtime_status)
            self.current_runtime_status = heartbeat
            self._apply_runtime_status(heartbeat)
            self.last_run_status = build_running_data_prep_last_run_status(heartbeat)
            self._apply_last_run_status(self.last_run_status)
        else:
            display = self.backtest_display_status or {}
            if (
                self.training_research_controller.is_running
                or display.get("mode") in {"starting", "running"}
            ):
                self.refresh_status(log_refresh=False)
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

    def _apply_backtest_display_status(self, status: dict[str, object]) -> None:
        """Switch the existing overview widgets to the current backtest."""

        mode = str(status.get("mode", "idle"))
        completed = int(status.get("completed_cycles", 0) or 0)
        maximum = int(status.get("max_cycles", 8) or 8)
        active_cycle = status.get("active_cycle")
        progress = float(status.get("progress_pct", 0.0) or 0.0)
        cycle_progress = float(status.get("cycle_progress_pct", 0.0) or 0.0)
        progress_message = status.get("progress_message") or status.get("progress_stage")
        elapsed = int(status.get("elapsed_seconds", 0) or 0)
        latest = status.get("latest_cycle")
        latest_row = latest if isinstance(latest, dict) else {}
        final = status.get("final_summary")
        final_row = final if isinstance(final, dict) else {}

        if mode in {"starting", "running"}:
            self.training_button.configure(state=tk.DISABLED)
            self.bot_state_var.set("Bot-Status: Backtest läuft")
            phase = (
                f"Zyklus {active_cycle}/{maximum} läuft"
                if active_cycle is not None
                else f"{completed}/{maximum} Zyklen abgeschlossen"
            )
            self.phase_var.set(f"Backteststatus: {phase}")
            self.mode_var.set("Modus: PR12 Protocol v2 / Kontext aktiv / kein V1")
            self.count_var.set(
                f"Backtestfortschritt: {progress:.2f}% gesamt / "
                f"{cycle_progress:.1f}% im aktiven Zyklus "
                f"({completed}/{maximum} Zyklen vollständig)"
            )
            self.task_var.set(f"Aktueller Schritt: {progress_message or phase}")
            self.file_var.set(
                "Kandidaten letzter Zyklus: "
                f"{latest_row.get('generated', '–')} erzeugt / "
                f"{latest_row.get('tested', '–')} getestet / "
                f"{latest_row.get('walk_forward', '–')} WFV / "
                f"{latest_row.get('finalists', '–')} Finalisten"
            )
            self.last_run_detail_var.set(
                "Bester Zwischenstand: "
                f"WFV {self._format_usdc(latest_row.get('wfv_net_usdc_per_day'))}/Tag / "
                f"Validation {self._format_usdc(latest_row.get('validation_net_usdc_per_day'))}/Tag"
            )
        elif mode == "completed":
            self.bot_state_var.set("Bot-Status: Backtest abgeschlossen")
            self.phase_var.set("Backteststatus: vollständig abgeschlossen")
            self.mode_var.set("Modus: Ergebnisansicht PR12 Protocol v2")
            self.count_var.set(f"Backtest: {completed}/{maximum} Zyklen / 100% abgeschlossen")
            self.task_var.set(
                f"Stop-Grund: {final_row.get('stop_reason') or 'im Report dokumentiert'}"
            )
            selected = final_row.get("selected_candidate")
            selected_row = selected if isinstance(selected, dict) else {}
            self.file_var.set(
                "Bestes Profil: "
                f"{selected_row.get('candidate_id') or '–'} / "
                f"{selected_row.get('family') or '–'}"
            )
            self.last_run_detail_var.set(
                "Endergebnis: "
                f"WFV {self._format_usdc(final_row.get('wfv_net_usdc_per_day'))}/Tag / "
                f"Abstand zu 3 USDC {self._format_usdc(final_row.get('target_gap_usdc_per_day'))}/Tag"
            )
        else:
            self.bot_state_var.set(f"Bot-Status: {status.get('status_text', 'Backtestfehler')}")
            self.phase_var.set(f"Backteststatus: {mode}")
            self.mode_var.set("Modus: PR12 Protocol v2 – fail-closed")
            self.count_var.set(
                f"Backtestfortschritt: {progress:.1f}% ({completed}/{maximum} Zyklen vollständig)"
            )
            self.task_var.set(f"Fehler/Unterbrechung: {status.get('error') or 'siehe Laufprotokoll'}")
            self.file_var.set(f"Child-Exit-Code: {status.get('child_exit_code')}")

        self.progress_var.set(progress)
        self._set_progress_visible(bool(status.get("progress_visible")))
        self.elapsed_var.set(f"Backtest-Laufzeit: {self._format_duration(elapsed)}")
        self.last_run_var.set(
            f"Backtest-Run: {status.get('run_id') or 'wird erstellt'} / "
            f"Commit {status.get('git_commit') or 'wird ermittelt'}"
        )
        self.engine_var.set(
            "Backtestpfad: UI → Produktionsstarter → Supervisor → PR12 Runner; "
            "Audit und finaler Holdout geschlossen"
        )
        self.portfolio_var.set(
            "Portfolio: 100 USDC / exakt 1 Lot / kein Compounding / ETHUSDC LONG-only"
        )
        if mode == "completed":
            self.final_var.set(
                "Research-Ergebnis: "
                f"WFV {self._format_usdc(final_row.get('wfv_net_usdc_per_day'))}/Tag / "
                f"PF {self._format_number(final_row.get('wfv_profit_factor'), 4)} / "
                f"Trades/Tag {self._format_number(final_row.get('wfv_trades_per_day'), 4)}"
            )
        else:
            self.final_var.set(
                "Aktueller Research-Stand: "
                f"WFV {self._format_usdc(latest_row.get('wfv_net_usdc_per_day'))}/Tag / "
                f"PF {self._format_number(latest_row.get('wfv_profit_factor'), 4)}"
            )
        self.shadow_var.set(
            "Sicherheit: Live/Paper/Testtrade gesperrt / Orders keine / "
            "BTCUSDC und ETHBTC nur Kontext"
        )

        active = mode in {"starting", "running"}
        if active:
            self._set_data_buttons_enabled(False)
            self.training_button.configure(state=tk.DISABLED)
            self.final_evaluation_button.configure(state=tk.DISABLED)
            self.adopt_shadow_button.configure(state=tk.DISABLED)
            self.shadow_start_button.configure(state=tk.DISABLED)
            self.shadow_stop_button.configure(state=tk.DISABLED)

    def _set_progress_visible(self, visible: bool) -> None:
        if visible:
            if not self.progress_bar.winfo_manager():
                self.progress_bar.pack(fill=tk.X, pady=(6, 0))
            return
        if self.progress_bar.winfo_manager():
            self.progress_bar.pack_forget()

    def _replace_log_text(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    @staticmethod
    def _format_number(value: object, digits: int) -> str:
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError, OverflowError):
            return "–"

    @classmethod
    def _format_usdc(cls, value: object) -> str:
        number = cls._format_number(value, 6)
        return "–" if number == "–" else f"{number} USDC"

    @staticmethod
    def _format_duration(seconds: int) -> str:
        hours, remainder = divmod(max(0, seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _apply_runtime_status(self, status: dict[str, object]) -> None:
        seconds_since_file_event = int(time.monotonic() - self.last_file_event_monotonic)
        text = build_operator_runtime_text(status, seconds_since_file_event=seconds_since_file_event)
        self.bot_state_var.set(f"Bot-Status: {text['bot_status']} ({text['activity_note']})")
        self.phase_var.set(f"Datenstatus: {text['mode']}")
        self.mode_var.set(f"Modus: {text['mode']}")
        self.task_var.set(f"Aktueller Lauf: {text['progress']} seit Start - {text['current_download']}")
        self.file_var.set(f"Dateien: {text['files']}")
        self.elapsed_var.set(f"Laufzeit: {text['elapsed']}")
        self.engine_var.set(
            "Backtest: wartet waehrend der Datenvorbereitung; keine Fake-Ergebnisse."
        )

    def _apply_overall_data_status(self, snapshot: dict[str, object]) -> None:
        progress = float(snapshot.get("overall_data_progress_pct", 0) or 0)
        self.progress_var.set(progress)
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

    def _apply_training_research_status(self, status: dict[str, object]) -> None:
        phase = str(status.get("phase", "initial"))
        freeze = str(status.get("freeze_status", "not_run"))
        report = status.get("report_path")
        if status.get("running"):
            self.bot_state_var.set("Bot-Status: Training/Validation/WFV laeuft")
            self.engine_var.set(
                "Backtest: Training/WFV laeuft; Final-Holdout bleibt versiegelt."
            )
            self.training_button.configure(state=tk.DISABLED)
            self.adopt_shadow_button.configure(state=tk.DISABLED)
            return
        self.engine_var.set(
            f"Backtest: {phase} / {freeze}; Final-Holdout ausgewertet=false"
        )
        if phase in {"completed", "failed"}:
            self._log(
                f"Training/WFV {phase}: freeze_status={freeze}, report={report}, "
                "final_holdout_evaluated=false"
            )

    def _apply_final_evaluation_runtime_status(
        self, status: dict[str, object]
    ) -> None:
        phase = str(status.get("phase", "initial"))
        outcome = str(status.get("final_holdout_outcome", "not_run"))
        color = str(status.get("assessment_color", "none"))
        if status.get("running"):
            self.bot_state_var.set("Bot-Status: irreversibler Finaltest laeuft")
            self.engine_var.set(
                "Finaltest: One-shot laeuft; permanenter Claim aktiv; nicht wiederholen."
            )
            self.training_button.configure(state=tk.DISABLED)
            self.final_evaluation_button.configure(state=tk.DISABLED)
            self.adopt_shadow_button.configure(state=tk.DISABLED)
            return
        if phase in {"completed", "failed"}:
            self._log(
                f"Sealed final evaluation {phase}: outcome={outcome}, color={color}, "
                f"report={status.get('final_report_path')}, retry_allowed=false"
            )

    def _apply_shadow_controller_status(self, status: dict[str, object]) -> None:
        phase = str(status.get("phase", "initial"))
        if status.get("running"):
            self.bot_state_var.set("Bot-Status: Shadow beobachtet oeffentliche Daten")
            self.shadow_var.set(
                "Shadow: "
                f"{phase} / nur hypothetisch / Orders aus / Trading-API aus"
            )
            return
        if phase == "completed":
            self._log(
                "Shadow public-data runtime stopped cleanly; open hypothetical "
                "lots were retained."
            )
        elif phase == "failed":
            self._log(
                "Shadow public-data runtime failed closed: "
                f"{status.get('error')}"
            )

    def _apply_product_status(self, snapshot: dict[str, object]) -> None:
        portfolio = snapshot["portfolio_status"]
        final = snapshot["final_evaluation_status"]
        shadow = snapshot["shadow_runtime_status"]
        shadow_control = snapshot["shadow_controller_status"]
        backtest_button = snapshot["ui_status"]["backtest_start_button"]
        adopt_button = snapshot["ui_status"]["shadow_adopt_button"]
        final_button = snapshot["ui_status"]["sealed_final_button"]
        shadow_start_button = snapshot["ui_status"]["shadow_start_button"]
        shadow_stop_button = snapshot["ui_status"]["shadow_stop_button"]
        self.portfolio_var.set(
            "Portfolio: "
            f"{portfolio['deployment_budget_usdc']} USDC / "
            f"{portfolio['lot_notional_usdc']} USDC je Lot / "
            f"max. {portfolio['max_concurrent_lots']} Lots / Compounding aus"
        )
        self.final_var.set(
            "Final-Ampel: "
            f"{str(final['color']).upper()} / "
            f"Netto pro Tag {final['final_net_usdc_per_day']} / "
            f"Shadow-uebernehmbar {final['shadow_eligible']}"
        )
        self.shadow_var.set(
            "Shadow: "
            f"{shadow['status']} / {shadow['phase']} / "
            f"Lots {shadow['open_lots']}/{shadow['max_open_lots']} / "
            f"Steuerung {shadow_control.get('phase')} / "
            "Orders aus / Trading-API aus"
        )
        data_running = self.active_data_thread is not None and self.active_data_thread.is_alive()
        self.training_button.configure(
            state=(
                tk.NORMAL
                if backtest_button["enabled"] and not data_running
                else tk.DISABLED
            )
        )
        self.final_evaluation_button.configure(
            state=tk.NORMAL if final_button["enabled"] else tk.DISABLED
        )
        self.adopt_shadow_button.configure(
            state=tk.NORMAL if adopt_button["enabled"] else tk.DISABLED
        )
        self.shadow_start_button.configure(
            state=tk.NORMAL if shadow_start_button["enabled"] else tk.DISABLED
        )
        self.shadow_stop_button.configure(
            state=tk.NORMAL if shadow_stop_button["enabled"] else tk.DISABLED
        )
        if (
            not self.training_research_status.get("running")
            and not self.final_evaluation_runtime_status.get("running")
        ):
            self.engine_var.set(
                "Backtest: "
                f"{snapshot['backtest_status']['status_text']} / "
                f"Status {snapshot['backtest_status']['result_status']}"
            )

    def _set_data_buttons_enabled(self, enabled: bool) -> None:
        controller = getattr(self, "training_research_controller", None)
        if controller is not None and controller.is_running:
            enabled = False
        final_controller = getattr(self, "final_evaluation_controller", None)
        if final_controller is not None and final_controller.is_running:
            enabled = False
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
