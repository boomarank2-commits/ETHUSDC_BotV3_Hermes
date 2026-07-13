"""Durable progress truth for long offline ETHUSDC research runs.

Only completed compute work is reported. This module does not select candidates,
evaluate gates, read a holdout, or alter strategy behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any


MIN_ACTIVE_CYCLE_PROGRESS_PCT = 2.0
MAX_RUNNING_CYCLE_PROGRESS_PCT = 99.5


@dataclass
class ResearchProgressEmitter:
    reports_root: str | Path
    run_id: str
    max_cycles: int

    def __post_init__(self) -> None:
        self.reports_root = Path(self.reports_root)
        if not self.run_id:
            raise ValueError("run_id must not be empty")
        if self.max_cycles <= 0:
            raise ValueError("max_cycles must be positive")
        self.completed_cycles = 0
        self.active_cycle: int | None = None
        self.cycle_progress_pct = 0.0
        self.overall_progress_pct = 0.0
        self.stage = "initializing"
        self.message = "Backtest wird vorbereitet"
        self.completed_work_units = 0
        self.total_work_units = 0

    @property
    def path(self) -> Path:
        return Path(self.reports_root) / f"{self.run_id}.progress.json"

    def restore_completed(self, completed_cycles: int) -> None:
        if completed_cycles < 0 or completed_cycles > self.max_cycles:
            raise ValueError("completed_cycles is outside the configured range")
        self.completed_cycles = completed_cycles
        self.active_cycle = None
        self.cycle_progress_pct = 100.0 if completed_cycles else 0.0
        self.overall_progress_pct = round(
            completed_cycles / self.max_cycles * 100.0, 3
        )
        self.stage = "resume_loaded" if completed_cycles else "initializing"
        self.message = (
            f"{completed_cycles}/{self.max_cycles} Zyklen aus Checkpoint geladen"
            if completed_cycles
            else "Backtest wird vorbereitet"
        )
        self.completed_work_units = 0
        self.total_work_units = 0
        self._write("running")

    def start_cycle(self, cycle: int, *, total_work_units: int) -> None:
        if cycle < 1 or cycle > self.max_cycles:
            raise ValueError("cycle is outside the configured range")
        if cycle != self.completed_cycles + 1:
            raise ValueError("active cycle must follow completed cycles")
        if total_work_units <= 0:
            raise ValueError("total_work_units must be positive")
        self.active_cycle = cycle
        self.cycle_progress_pct = MIN_ACTIVE_CYCLE_PROGRESS_PCT
        self.overall_progress_pct = round(
            ((cycle - 1) + self.cycle_progress_pct / 100.0)
            / self.max_cycles
            * 100.0,
            3,
        )
        self.stage = "cycle_setup"
        self.message = f"Zyklus {cycle}/{self.max_cycles} wird vorbereitet"
        self.completed_work_units = 0
        self.total_work_units = total_work_units
        self._write("running")

    def update_cycle(
        self,
        cycle: int,
        *,
        stage: str,
        completed_work_units: int,
        message: str,
    ) -> None:
        if self.active_cycle != cycle:
            raise ValueError("progress update is not bound to the active cycle")
        if self.total_work_units <= 0:
            raise ValueError("active cycle has no work-unit budget")
        if completed_work_units < 0:
            raise ValueError("completed_work_units must not be negative")
        completed = min(completed_work_units, self.total_work_units)
        raw_cycle_pct = min(
            MAX_RUNNING_CYCLE_PROGRESS_PCT,
            completed / self.total_work_units * 100.0,
        )
        self.cycle_progress_pct = round(
            max(
                self.cycle_progress_pct,
                MIN_ACTIVE_CYCLE_PROGRESS_PCT,
                raw_cycle_pct,
            ),
            3,
        )
        self.overall_progress_pct = round(
            ((cycle - 1) + self.cycle_progress_pct / 100.0)
            / self.max_cycles
            * 100.0,
            3,
        )
        self.stage = str(stage)
        self.message = str(message)
        self.completed_work_units = completed
        self._write("running")

    def complete_cycle(self, cycle: int) -> None:
        if self.active_cycle != cycle:
            raise ValueError("completed cycle is not the active cycle")
        self.completed_cycles = cycle
        self.active_cycle = None
        self.cycle_progress_pct = 100.0
        self.overall_progress_pct = round(cycle / self.max_cycles * 100.0, 3)
        self.stage = "cycle_complete"
        self.message = f"Zyklus {cycle}/{self.max_cycles} vollständig abgeschlossen"
        self.completed_work_units = self.total_work_units
        self._write("running")

    def complete_run(self, *, stop_reason: str, cycles_executed: int) -> None:
        self.completed_cycles = max(0, min(cycles_executed, self.max_cycles))
        self.active_cycle = None
        self.cycle_progress_pct = 100.0
        self.overall_progress_pct = 100.0
        self.stage = "run_complete"
        self.message = f"Backtest abgeschlossen: {stop_reason}"
        self._write("completed")

    def _payload(self, status: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact_kind": "research_loop_progress",
            "run_id": self.run_id,
            "status": status,
            "max_cycles": self.max_cycles,
            "completed_cycles": self.completed_cycles,
            "active_cycle": self.active_cycle,
            "cycle_progress_pct": self.cycle_progress_pct,
            "overall_progress_pct": self.overall_progress_pct,
            "stage": self.stage,
            "message": self.message,
            "completed_work_units": self.completed_work_units,
            "total_work_units": self.total_work_units,
            "updated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "selection_behavior_changed": False,
            "uses_audit_or_holdout": False,
        }

    def _write(self, status: str) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(
                self._payload(status),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
