"""Regression tests for user-visible granular backtest progress."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ethusdc_bot.backtest.research_progress import ResearchProgressEmitter
from ethusdc_bot.ui.backtest_display import _running_progress_values


def _read(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_progress_starts_visible_moves_monotonically_and_finishes_at_100(
    tmp_path: Path,
) -> None:
    emitter = ResearchProgressEmitter(tmp_path, "research_loop_example", 8)
    emitter.restore_completed(0)
    emitter.start_cycle(1, total_work_units=100)

    started = _read(emitter.path)
    assert started["cycle_progress_pct"] == 2.0
    assert started["overall_progress_pct"] == pytest.approx(0.25)

    emitter.update_cycle(
        1,
        stage="training_validation",
        completed_work_units=50,
        message="Training/Validation Kandidat 6/12 abgeschlossen",
    )
    halfway = _read(emitter.path)
    assert halfway["cycle_progress_pct"] == 50.0
    assert halfway["overall_progress_pct"] == pytest.approx(6.25)
    assert halfway["selection_behavior_changed"] is False
    assert halfway["uses_audit_or_holdout"] is False

    emitter.update_cycle(
        1,
        stage="training_validation",
        completed_work_units=40,
        message="veraltetes Ereignis",
    )
    assert _read(emitter.path)["cycle_progress_pct"] == 50.0

    emitter.complete_cycle(1)
    assert _read(emitter.path)["overall_progress_pct"] == pytest.approx(12.5)

    emitter.complete_run(
        stop_reason="selection_stagnation_3_cycles",
        cycles_executed=7,
    )
    completed = _read(emitter.path)
    assert completed["status"] == "completed"
    assert completed["overall_progress_pct"] == 100.0
    assert not emitter.path.with_name(emitter.path.name + ".tmp").exists()


def test_display_uses_active_cycle_fraction_and_falls_back_fail_closed() -> None:
    progress, cycle_progress, stage, message = _running_progress_values(
        status="running",
        completed_cycles=0,
        max_cycles=8,
        active_cycle=1,
        live_progress={
            "active_cycle": 1,
            "cycle_progress_pct": 50.0,
            "overall_progress_pct": 6.25,
            "stage": "training_validation",
            "message": "Kandidat 6/12 abgeschlossen",
        },
    )
    assert progress == pytest.approx(6.25)
    assert cycle_progress == pytest.approx(50.0)
    assert stage == "training_validation"
    assert message == "Kandidat 6/12 abgeschlossen"

    fallback = _running_progress_values(
        status="running",
        completed_cycles=2,
        max_cycles=8,
        active_cycle=3,
        live_progress={"active_cycle": 99, "overall_progress_pct": 99.0},
    )
    assert fallback == (25.0, 0.0, None, None)

    completed = _running_progress_values(
        status="completed",
        completed_cycles=7,
        max_cycles=8,
        active_cycle=None,
        live_progress=None,
    )
    assert completed == (100.0, 100.0, "run_complete", "Backtest abgeschlossen")
