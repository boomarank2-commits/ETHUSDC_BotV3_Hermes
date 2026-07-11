"""Tests for durable progress observation around the unchanged research runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import ethusdc_bot.backtest.research_supervisor as supervisor


class _FakeProcess:
    def __init__(self, lines: list[str], returncode: int) -> None:
        self.stdout = iter(lines)
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def wait(self, timeout: int | None = None) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def test_parse_cycle_progress_accepts_only_canonical_completion_lines() -> None:
    progress = supervisor.parse_cycle_progress(
        "cycle 3/8: generated=40 tested=12 walk_forward=3 finalists=2 "
        "selected_rank=(0.0, -0.031)"
    )

    assert progress == supervisor.CycleProgress(
        cycle=3,
        maximum=8,
        generated=40,
        tested=12,
        walk_forward=3,
        finalists=2,
        selected_rank_text="(0.0, -0.031)",
    )
    assert supervisor.parse_cycle_progress("cycle 3/8: starting") is None
    assert supervisor.parse_cycle_progress("unrelated output") is None


def test_parse_cycle_progress_rejects_impossible_indexes() -> None:
    with pytest.raises(ValueError, match="indexes"):
        supervisor.parse_cycle_progress(
            "cycle 9/8: generated=40 tested=12 walk_forward=3 finalists=2 "
            "selected_rank=(0.0,)"
        )


def test_checkpoint_payload_is_explicitly_order_free_and_not_a_result_claim(monkeypatch) -> None:
    monkeypatch.setattr(supervisor, "_git_value", lambda *args: "fixed")
    payload = supervisor._checkpoint_payload(
        run_id="run",
        status="running",
        max_cycles=8,
        started_at_utc="2026-07-11T00:00:00Z",
        completed_cycles=(
            supervisor.CycleProgress(1, 8, 40, 12, 3, 2, "(-0.1,)"),
        ),
        active_cycle=2,
        child_exit_code=None,
        report_json=None,
    )

    assert payload["result_truth"] == "canonical_runner_json_only"
    assert payload["resume_supported"] is False
    assert payload["audit_evaluated"] is False
    assert payload["final_holdout_evaluated"] is False
    assert payload["safety"] == {
        "live": "locked",
        "paper": "locked",
        "testtrade": "locked",
        "orders": "not_created",
        "trading_api": "not_used",
        "api_keys": "not_used",
    }


def test_write_checkpoint_atomically_replaces_strict_json(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    supervisor.write_checkpoint(path, {"value": 1.0})
    supervisor.write_checkpoint(path, {"value": 2.0})

    assert json.loads(path.read_text(encoding="utf-8")) == {"value": 2.0}
    assert not path.with_name(path.name + ".tmp").exists()


def test_supervisor_persists_each_completed_cycle_and_final_report(
    tmp_path: Path, monkeypatch
) -> None:
    lines = [
        "cycle 1/2: starting\n",
        "cycle 1/2: generated=40 tested=12 walk_forward=3 finalists=2 "
        "selected_rank=(0.0, -0.1)\n",
        "cycle 2/2: starting\n",
        "cycle 2/2: generated=40 tested=12 walk_forward=3 finalists=2 "
        "selected_rank=(1.0, -0.05)\n",
        "Report JSON: reports/research_loop/final.json\n",
    ]
    process = _FakeProcess(lines, returncode=0)
    captured_command: list[str] = []

    def fake_popen(command, **kwargs):
        captured_command.extend(command)
        return process

    monkeypatch.setattr(supervisor.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(supervisor, "_git_value", lambda *args: "fixed")

    exit_code = supervisor.supervise(
        ["--reports-root", str(tmp_path), "--max-cycles", "2", "--fixture-smoke"]
    )

    assert exit_code == 0
    assert captured_command[1:3] == ["-m", "ethusdc_bot.backtest.research_loop_runner"]
    assert "--fixture-smoke" in captured_command
    checkpoints = list(tmp_path.glob("production_research_supervisor_*.checkpoint.json"))
    assert len(checkpoints) == 1
    data = json.loads(checkpoints[0].read_text(encoding="utf-8"))
    assert data["status"] == "completed"
    assert data["completed_cycle_count"] == 2
    assert data["active_cycle"] is None
    assert data["child_exit_code"] == 0
    assert data["report_json"] == "reports/research_loop/final.json"
    assert [row["cycle"] for row in data["cycles"]] == [1, 2]


def test_supervisor_preserves_progress_when_child_fails(tmp_path: Path, monkeypatch) -> None:
    process = _FakeProcess(
        [
            "cycle 1/8: starting\n",
            "cycle 1/8: generated=40 tested=12 walk_forward=3 finalists=2 "
            "selected_rank=(-0.1,)\n",
            "cycle 2/8: starting\n",
            "fatal child error\n",
        ],
        returncode=7,
    )
    monkeypatch.setattr(supervisor.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(supervisor, "_git_value", lambda *args: "fixed")

    assert supervisor.supervise(
        ["--reports-root", str(tmp_path), "--max-cycles", "8"]
    ) == 7

    checkpoint = next(tmp_path.glob("production_research_supervisor_*.checkpoint.json"))
    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert data["status"] == "failed"
    assert data["completed_cycle_count"] == 1
    assert data["active_cycle"] == 2
    assert data["child_exit_code"] == 7
    assert data["report_json"] is None
