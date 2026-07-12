from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "src" / "ethusdc_bot" / "ui" / "dashboard.py"
DISPLAY = ROOT / "src" / "ethusdc_bot" / "ui" / "backtest_display.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_dashboard() -> None:
    text = DASHBOARD.read_text(encoding="utf-8")
    marker = "def _apply_backtest_display_status("
    if marker in text:
        print("dashboard patch already applied")
        return

    text = replace_once(
        text,
        "from ethusdc_bot.ui.backtest_controller import (\n",
        "from ethusdc_bot.ui.backtest_display import (\n"
        "    collect_backtest_display_status,\n"
        "    format_backtest_log_for_display,\n"
        "    format_backtest_summary_for_display,\n"
        ")\n"
        "from ethusdc_bot.ui.backtest_controller import (\n",
        "backtest display import",
    )
    text = replace_once(
        text,
        "        self.training_research_status = build_initial_training_research_status()\n",
        "        self.training_research_status = build_initial_training_research_status()\n"
        "        self.backtest_display_status: dict[str, object] | None = None\n",
        "backtest display state",
    )
    text = replace_once(
        text,
        "        ttk.Progressbar(runtime_frame, maximum=100, variable=self.progress_var).pack(fill=tk.X, pady=(6, 0))\n",
        "        self.progress_bar = ttk.Progressbar(\n"
        "            runtime_frame, maximum=100, variable=self.progress_var\n"
        "        )\n"
        "        self.progress_bar.pack(fill=tk.X, pady=(6, 0))\n",
        "named reusable progress bar",
    )

    start = text.index("    def refresh_status(self) -> None:\n")
    end = text.index("    def open_data_folder(self) -> None:\n", start)
    replacement = '''    def refresh_status(self, *, log_refresh: bool = True) -> None:
        """Refresh the existing three display areas for data or backtest mode."""

        show_backtest = False
        try:
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
            self.current_snapshot = snapshot
            display = collect_backtest_display_status(
                self.training_reports_root,
                controller_status=self.training_research_status,
            )
            self.backtest_display_status = display
            data_running = bool(
                self.active_data_thread is not None
                and self.active_data_thread.is_alive()
            )
            show_backtest = not data_running and display.get("mode") != "idle"

            self._apply_product_status(snapshot)
            if show_backtest:
                self._apply_backtest_display_status(display)
                text = format_backtest_summary_for_display(display)
                self._replace_log_text(format_backtest_log_for_display(display))
            else:
                if data_running and self.current_runtime_status:
                    self._apply_runtime_status(self.current_runtime_status)
                else:
                    self._apply_runtime_status(snapshot["data_prep_runtime_status"])
                self._apply_overall_data_status(snapshot)
                self._apply_last_run_status(snapshot["data_prep_last_run_status"])
                self._set_progress_visible(True)
                text = format_operator_summary_for_display(snapshot)
        except Exception as exc:  # pragma: no cover - defensive UI reporting
            text = f"Failed to collect dashboard snapshot: {exc}\\n"
            self._log(text)
        self.status_text.configure(state=tk.NORMAL)
        self.status_text.delete("1.0", tk.END)
        self.status_text.insert(tk.END, text)
        self.status_text.configure(state=tk.DISABLED)
        if log_refresh and not show_backtest:
            self._log("Refreshed status snapshot.")

'''
    text = text[:start] + replacement + text[end:]

    start = text.index("    def _heartbeat_active_run(self) -> None:\n")
    end = text.index("    def _finalize_active_data_run(self) -> None:\n", start)
    replacement = '''    def _heartbeat_active_run(self) -> None:
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

'''
    text = text[:start] + replacement + text[end:]

    insert_at = text.index("    def _apply_runtime_status(self, status: dict[str, object]) -> None:\n")
    methods = '''    def _apply_backtest_display_status(self, status: dict[str, object]) -> None:
        """Switch the existing overview widgets to the current backtest."""

        mode = str(status.get("mode", "idle"))
        completed = int(status.get("completed_cycles", 0) or 0)
        maximum = int(status.get("max_cycles", 8) or 8)
        active_cycle = status.get("active_cycle")
        progress = float(status.get("progress_pct", 0.0) or 0.0)
        elapsed = int(status.get("elapsed_seconds", 0) or 0)
        latest = status.get("latest_cycle")
        latest_row = latest if isinstance(latest, dict) else {}
        final = status.get("final_summary")
        final_row = final if isinstance(final, dict) else {}

        if mode in {"starting", "running"}:
            self.bot_state_var.set("Bot-Status: Backtest läuft")
            phase = (
                f"Zyklus {active_cycle}/{maximum} läuft"
                if active_cycle is not None
                else f"{completed}/{maximum} Zyklen abgeschlossen"
            )
            self.phase_var.set(f"Backteststatus: {phase}")
            self.mode_var.set("Modus: PR12 Protocol v2 / Kontext aktiv / kein V1")
            self.count_var.set(
                f"Backtestfortschritt: {progress:.1f}% ({completed}/{maximum} Zyklen vollständig)"
            )
            self.task_var.set(f"Aktueller Schritt: {phase}")
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

        self.progress_var.set(int(progress))
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

'''
    text = text[:insert_at] + methods + text[insert_at:]
    DASHBOARD.write_text(text, encoding="utf-8")
    print("patched dashboard.py")


def patch_display() -> None:
    text = DISPLAY.read_text(encoding="utf-8")
    if "_FINAL_REPORT_CACHE" not in text:
        text = replace_once(
            text,
            "_CYCLE_TEXT = re.compile(\n",
            "_FINAL_REPORT_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}\n\n"
            "_CYCLE_TEXT = re.compile(\n",
            "final report cache declaration",
        )
        text = replace_once(
            text,
            "    if not path.is_file():\n        return {}\n    top_keys = {\n",
            "    if not path.is_file():\n        return {}\n"
            "    stat = path.stat()\n"
            "    cache_key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)\n"
            "    cached = _FINAL_REPORT_CACHE.get(cache_key)\n"
            "    if cached is not None:\n"
            "        return dict(cached)\n"
            "    top_keys = {\n",
            "final report cache lookup",
        )
        text = replace_once(
            text,
            "    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):\n        return extracted\n\n    cycle_count = max(\n",
            "    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):\n"
            "        _FINAL_REPORT_CACHE[cache_key] = dict(extracted)\n"
            "        return extracted\n\n"
            "    cycle_count = max(\n",
            "final report cache on partial extraction",
        )
        text = replace_once(
            text,
            "        extracted[\"cycles\"].append(row)\n    return extracted\n\n\ndef _iter_selected_pretty_json_values(\n",
            "        extracted[\"cycles\"].append(row)\n"
            "    _FINAL_REPORT_CACHE[cache_key] = dict(extracted)\n"
            "    return extracted\n\n\n"
            "def _iter_selected_pretty_json_values(\n",
            "final report cache store",
        )
    text = text.replace(
        "    if isinstance(best, Mapping) and best is not latest:\n",
        "    if (\n"
        "        isinstance(best, Mapping)\n"
        "        and best.get(\"cycle\")\n"
        "        != (latest.get(\"cycle\") if isinstance(latest, Mapping) else None)\n"
        "    ):\n",
        1,
    )
    DISPLAY.write_text(text, encoding="utf-8")
    print("patched backtest_display.py")


if __name__ == "__main__":
    patch_dashboard()
    patch_display()
