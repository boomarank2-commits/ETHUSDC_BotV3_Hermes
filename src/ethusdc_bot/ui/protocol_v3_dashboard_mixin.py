"""Task-30 controls mixed into the single existing operator dashboard.

This module adds one diagnostic action bar and delegates all state construction to
the typed Task-30 bridge. It does not create another Tk root, another report store,
another checkpoint store, or any trading path.
"""
from __future__ import annotations

from datetime import UTC, datetime
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from ethusdc_bot.ui.protocol_v3_dashboard_bridge import (
    ProtocolV3EvidenceProvider,
    ProtocolV3UiEvidence,
    build_empty_protocol_v3_ui_evidence,
    protocol_v3_button_blocker_text,
    resolve_protocol_v3_operator_state,
)
from ethusdc_bot.ui.protocol_v3_operator_state import (
    ProtocolV3OperatorState,
    build_protocol_v3_data_status,
)
from ethusdc_bot.ui.research_challenger_controller import ResearchChallengerController


class ProtocolV3DashboardMixin:
    """Small UI-only extension for the existing OperatorDashboardApp."""

    def _initialize_protocol_v3_ui(
        self,
        provider: ProtocolV3EvidenceProvider | None,
    ) -> None:
        if provider is not None and not callable(provider):
            raise TypeError("protocol_v3_evidence_provider must be callable or None")
        self.protocol_v3_evidence_provider = provider
        self.protocol_v3_challenger_controller = ResearchChallengerController()
        self.protocol_v3_operator_state: ProtocolV3OperatorState | None = None
        self.protocol_v3_controller_status = (
            self.protocol_v3_challenger_controller.status_snapshot()
        )
        self._protocol_v3_last_worker_status = dict(self.protocol_v3_controller_status)
        self._protocol_v3_action_bar: tk.Misc | None = None

    def _build_protocol_v3_widgets(self) -> None:
        bar = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        bar.pack(fill=tk.X)
        self._protocol_v3_action_bar = bar
        ttk.Label(
            bar,
            text="Protocol v3 / Research-Challenger / strikt orderfrei:",
        ).pack(side=tk.LEFT, padx=4)
        self.protocol_v3_show_button = ttk.Button(
            bar,
            text="Protocol v3 anzeigen",
            command=self.show_protocol_v3_view,
        )
        self.protocol_v3_show_button.pack(side=tk.LEFT, padx=4)
        self.protocol_v3_start_button = ttk.Button(
            bar,
            text="Diagnose manuell starten",
            command=self.start_protocol_v3_challenger,
            state=tk.DISABLED,
        )
        self.protocol_v3_start_button.pack(side=tk.LEFT, padx=4)
        self.protocol_v3_resume_button = ttk.Button(
            bar,
            text="Aus Checkpoint fortsetzen",
            command=self.resume_protocol_v3_challenger,
            state=tk.DISABLED,
        )
        self.protocol_v3_resume_button.pack(side=tk.LEFT, padx=4)
        self.protocol_v3_stop_button = ttk.Button(
            bar,
            text="Diagnose stoppen",
            command=self.stop_protocol_v3_challenger,
            state=tk.DISABLED,
        )
        self.protocol_v3_stop_button.pack(side=tk.LEFT, padx=4)
        ttk.Label(
            bar,
            text="NOT_FRESH | diagnostic_only | keine Adoption | keine Orders",
        ).pack(side=tk.LEFT, padx=(16, 4))

    def _protocol_v3_evidence_snapshot(self) -> ProtocolV3UiEvidence:
        provider = self.protocol_v3_evidence_provider
        if provider is None:
            return build_empty_protocol_v3_ui_evidence()
        try:
            evidence = provider()
            if not isinstance(evidence, ProtocolV3UiEvidence):
                raise TypeError(
                    "Protocol-v3 provider returned an invalid evidence object"
                )
            return evidence
        except Exception as exc:
            logger = getattr(self, "_log", None)
            if callable(logger):
                logger(
                    "Protocol-v3-Evidence-Provider wurde fail-closed blockiert: "
                    f"{type(exc).__name__}"
                )
            return ProtocolV3UiEvidence(
                data_status=build_protocol_v3_data_status(
                    state="ERROR",
                    blockers=(
                        f"protocol_v3_evidence_provider_failed:{type(exc).__name__}",
                    ),
                )
            )

    def _resolve_protocol_v3_operator_state(
        self,
        evidence: ProtocolV3UiEvidence | None = None,
        *,
        now_utc: datetime | None = None,
    ) -> ProtocolV3OperatorState:
        source = evidence or self._protocol_v3_evidence_snapshot()
        state = resolve_protocol_v3_operator_state(
            source,
            now_utc=now_utc or datetime.now(UTC),
            worker_status=self.protocol_v3_challenger_controller.status_snapshot(),
            controller_state=self.protocol_v3_challenger_controller.state_snapshot(),
            controller_checkpoint=(
                self.protocol_v3_challenger_controller.checkpoint_snapshot()
            ),
            ui_runtime_blockers=self._protocol_v3_runtime_blockers(),
        )
        self.protocol_v3_operator_state = state
        return state

    def _protocol_v3_runtime_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        data_thread = getattr(self, "active_data_thread", None)
        if data_thread is not None and data_thread.is_alive():
            blockers.append("data_preparation_is_running")
        for attribute, blocker in (
            ("training_research_controller", "training_research_is_running"),
            ("final_evaluation_controller", "sealed_final_evaluation_is_running"),
            ("shadow_controller", "canonical_shadow_runtime_is_running"),
        ):
            controller = getattr(self, attribute, None)
            if controller is not None and controller.is_running:
                blockers.append(blocker)
        return tuple(sorted(set(blockers)))

    def _apply_protocol_v3_operator_state(
        self, state: ProtocolV3OperatorState
    ) -> None:
        if not isinstance(state, ProtocolV3OperatorState):
            raise TypeError("typed ProtocolV3OperatorState is required")
        self.protocol_v3_operator_state = state
        root = state.to_dict()
        buttons = root["buttons"]
        self.protocol_v3_start_button.configure(
            state=(
                tk.NORMAL
                if buttons["challenger_start"]["enabled"]
                else tk.DISABLED
            )
        )
        self.protocol_v3_resume_button.configure(
            state=(
                tk.NORMAL
                if buttons["challenger_resume"]["enabled"]
                else tk.DISABLED
            )
        )
        self.protocol_v3_stop_button.configure(
            state=(
                tk.NORMAL
                if buttons["challenger_stop"]["enabled"]
                else tk.DISABLED
            )
        )
        tasks = root["task_progress"]
        challenger = root["research_challenger"]
        self.bot_state_var.set(
            "Bot-Status: Protocol v3 Diagnose "
            f"{challenger['status']} – Bot-Start bleibt gesperrt"
        )
        self.phase_var.set(
            "Protocol-v3-Aufgaben: "
            f"{tasks['done_tasks']}/{tasks['total_tasks']} DONE_100 "
            f"({tasks['progress_pct']} %)"
        )
        self.shadow_var.set(
            "Research-Challenger: "
            f"{challenger['status']} / Ledger {challenger['ledger_record_count']} / "
            "Orders 0 / private API 0 / keine Adoption"
        )

    def show_protocol_v3_view(self) -> None:
        self._requested_view = "protocol_v3"
        self.refresh_status(log_refresh=False)

    def start_protocol_v3_challenger(self) -> None:
        evidence = self._protocol_v3_evidence_snapshot()
        state = self._resolve_protocol_v3_operator_state(evidence)
        button = state.to_dict()["buttons"]["challenger_start"]
        if button["enabled"] is not True:
            self._show_protocol_v3_blocked("challenger_start", "Diagnose-Start")
            return
        if evidence.current_refit is None or evidence.pipeline_generation is None:
            self._show_protocol_v3_blocked("challenger_start", "Diagnose-Start")
            return
        confirmed = messagebox.askyesno(
            "Orderfreie Protocol-v3-Diagnose starten",
            (
                "Der Research-Challenger wird ab der aktuellen Minute manuell "
                "initialisiert. Es gibt keinen rückwirkenden Backfill.\n\n"
                "NOT_FRESH, diagnostic_only, keine Adoption, keine Orders, "
                "keine Trading-API, kein Paper/Testtrade/Live. Fortfahren?"
            ),
        )
        if not confirmed:
            return
        try:
            _thread, _container = self.protocol_v3_challenger_controller.start(
                evidence.current_refit,
                started_at_utc=datetime.now(UTC),
                current_pipeline_generation=evidence.pipeline_generation,
                exchange_info_snapshot=evidence.exchange_info_snapshot,
                worker=evidence.resume_worker,
            )
        except Exception as exc:
            self._log(f"Protocol-v3-Diagnose konnte nicht starten: {exc}")
            messagebox.showerror("Diagnose-Start fehlgeschlagen", str(exc))
            return
        self._requested_view = "protocol_v3"
        self.refresh_status(log_refresh=False)

    def resume_protocol_v3_challenger(self) -> None:
        evidence = self._protocol_v3_evidence_snapshot()
        state = self._resolve_protocol_v3_operator_state(evidence)
        button = state.to_dict()["buttons"]["challenger_resume"]
        if button["enabled"] is not True:
            self._show_protocol_v3_blocked(
                "challenger_resume", "Diagnose-Fortsetzung"
            )
            return
        challenger = (
            self.protocol_v3_challenger_controller.state_snapshot()
            or evidence.challenger_state
        )
        checkpoint = (
            self.protocol_v3_challenger_controller.checkpoint_snapshot()
            or evidence.challenger_checkpoint
        )
        if challenger is None or checkpoint is None or evidence.resume_worker is None:
            self._show_protocol_v3_blocked(
                "challenger_resume", "Diagnose-Fortsetzung"
            )
            return
        try:
            _thread, _container = self.protocol_v3_challenger_controller.resume(
                challenger,
                checkpoint,
                worker=evidence.resume_worker,
            )
        except Exception as exc:
            self._log(f"Protocol-v3-Resume wurde fail-closed blockiert: {exc}")
            messagebox.showerror("Diagnose-Fortsetzung fehlgeschlagen", str(exc))
            return
        self._requested_view = "protocol_v3"
        self.refresh_status(log_refresh=False)

    def stop_protocol_v3_challenger(self) -> None:
        self.protocol_v3_controller_status = (
            self.protocol_v3_challenger_controller.stop()
        )
        self._requested_view = "protocol_v3"
        self.refresh_status(log_refresh=False)

    def _show_protocol_v3_blocked(self, button_name: str, title: str) -> None:
        state = self.protocol_v3_operator_state or self._resolve_protocol_v3_operator_state()
        blockers = protocol_v3_button_blocker_text(state, button_name)
        messagebox.showwarning(f"{title} gesperrt", f"Blocker: {blockers}")

    def _refresh_protocol_v3_worker_status(self) -> None:
        current = self.protocol_v3_challenger_controller.status_snapshot()
        if current == self._protocol_v3_last_worker_status:
            return
        self._protocol_v3_last_worker_status = dict(current)
        self.protocol_v3_controller_status = dict(current)
        self._requested_view = "protocol_v3"
        self.refresh_status(log_refresh=False)

    def close_dashboard(self) -> None:
        if self.protocol_v3_challenger_controller.is_running:
            self.protocol_v3_challenger_controller.stop()
            self._log(
                "Dashboard wartet auf kooperativen Protocol-v3-Diagnose-Stopp."
            )
            self._wait_for_protocol_v3_shutdown(0)
            return
        super().close_dashboard()

    def _wait_for_protocol_v3_shutdown(self, attempt: int) -> None:
        if (
            not self.protocol_v3_challenger_controller.is_running
            or attempt >= 120
        ):
            super().close_dashboard()
            return
        self.root.after(
            100, lambda: self._wait_for_protocol_v3_shutdown(attempt + 1)
        )


__all__ = ["ProtocolV3DashboardMixin"]
