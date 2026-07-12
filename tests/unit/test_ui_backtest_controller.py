"""Tests for the safe asynchronous training-research UI controller."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest

from ethusdc_bot.ui.backtest_controller import (
    TrainingResearchController,
    build_canonical_training_loop_config,
    build_initial_training_research_status,
    run_production_research_via_starter,
    run_training_research_async,
)


def _fake_result(report_path: Path) -> SimpleNamespace:
    return SimpleNamespace(report_paths=SimpleNamespace(json_path=report_path))


def _write_report(path: Path, freeze_status: str = "blocked_by_quality_gates") -> Path:
    path.write_text(json.dumps({"schema_version": 2, "freeze_status": freeze_status}), encoding="utf-8")
    return path


def test_initial_status_is_fail_closed() -> None:
    status = build_initial_training_research_status()

    assert status["phase"] == "initial"
    assert status["running"] is False
    assert status["blocked"] is True
    assert status["report_path"] is None
    assert status["final_holdout_evaluated"] is False
    assert status["shadow_eligible"] is False
    assert status["orders_created"] is False
    assert status["trading_api_used"] is False
    assert status["api_keys_used"] is False
    assert status["production_path"] == "ui_to_windows_starter_to_supervisor_to_pr12_runner"
    assert status["context_research_enabled"] is True


def test_canonical_config_is_exact_production_protocol(tmp_path: Path) -> None:
    config = build_canonical_training_loop_config(tmp_path / "raw", tmp_path / "reports")

    assert config.max_cycles == 8
    assert config.max_candidates_per_cycle == 40
    assert config.tested_candidates_per_cycle == 12
    assert config.walk_forward_candidates_per_cycle == 3
    assert config.finalists_per_cycle == 2
    assert config.walk_forward_fold_count == 6
    assert config.rolling_origin_limit == 3
    assert config.rolling_origin_step_days == 365
    assert config.required_days == 1095
    assert config.min_cycles == 3
    assert config.stagnation_cycles == 3
    assert config.enable_context is True
    assert config.data_end_day == "2026-07-07"


def test_production_runner_invokes_existing_pr12_windows_starter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = _write_report(tmp_path / "report.json")
    calls = []

    class FakeProcess:
        stdout = iter([f"Report JSON: {report_path}\n"])

        def wait(self):
            return 0

        def kill(self):  # pragma: no cover - stdout exists
            raise AssertionError("kill must not be called")

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(
        "ethusdc_bot.ui.backtest_controller.subprocess.Popen", fake_popen
    )
    config = build_canonical_training_loop_config(
        tmp_path / "raw", tmp_path / "reports"
    )

    result = run_production_research_via_starter(config)

    command, kwargs = calls[0]
    assert command[0] == "powershell.exe"
    assert "run_production_research.ps1" in " ".join(command)
    assert "-DataEndDay" in command
    assert "2026-07-07" in command
    assert "research_loop_runner" not in " ".join(command)
    assert kwargs["stderr"] is subprocess.STDOUT
    assert result["report_paths"]["json_path"] == report_path


def test_async_runner_receives_canonical_config_once_and_returns_blocked_report(
    tmp_path: Path,
) -> None:
    report_path = _write_report(tmp_path / "report.json")
    calls = []
    updates = []

    def fake_runner(config):
        calls.append(config)
        return _fake_result(report_path)

    thread, container = run_training_research_async(
        tmp_path / "raw",
        tmp_path / "reports",
        status_callback=updates.append,
        runner=fake_runner,
    )
    thread.join(timeout=5)

    assert thread.daemon is False
    assert not thread.is_alive()
    assert len(calls) == 1
    assert calls[0].required_days == 1095
    assert calls[0].max_cycles == 8
    assert calls[0].enable_context is True
    status = container["status"]
    assert status["phase"] == "completed"
    assert status["report_path"] == str(report_path)
    assert status["freeze_status"] == "blocked_by_quality_gates"
    assert status["blocked"] is True
    assert status["final_holdout_evaluated"] is False
    assert status["shadow_eligible"] is False
    assert {update["phase"] for update in updates} == {"running", "completed"}


def test_completed_frozen_training_candidate_still_does_not_unlock_shadow(
    tmp_path: Path,
) -> None:
    report_path = _write_report(
        tmp_path / "report.json", "frozen_for_separate_sealed_holdout"
    )
    controller = TrainingResearchController()

    thread, container = controller.start(
        tmp_path / "raw",
        tmp_path / "reports",
        runner=lambda config: _fake_result(report_path),
    )
    thread.join(timeout=5)

    status = container["status"]
    assert status["phase"] == "completed"
    assert status["freeze_status"] == "frozen_for_separate_sealed_holdout"
    assert status["blocked"] is False
    assert status["final_holdout_evaluated"] is False
    assert status["shadow_eligible"] is False
    assert status["orders_created"] is False


def test_duplicate_start_is_rejected_while_worker_is_running(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()
    report_path = _write_report(tmp_path / "report.json")
    calls = 0

    def blocking_runner(config):
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=5)
        return _fake_result(report_path)

    controller = TrainingResearchController()
    thread, _ = controller.start(tmp_path / "raw", tmp_path / "reports", runner=blocking_runner)
    assert entered.wait(timeout=2)

    with pytest.raises(RuntimeError, match="already running"):
        controller.start(tmp_path / "raw", tmp_path / "reports", runner=blocking_runner)

    release.set()
    thread.join(timeout=5)
    assert calls == 1
    assert controller.is_running is False


def test_new_run_is_allowed_after_previous_worker_finished(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path / "report.json")
    controller = TrainingResearchController()
    calls = []

    def fake_runner(config):
        calls.append(config)
        return _fake_result(report_path)

    first, _ = controller.start(tmp_path / "raw", tmp_path / "reports", runner=fake_runner)
    first.join(timeout=5)
    second, _ = controller.start(tmp_path / "raw", tmp_path / "reports", runner=fake_runner)
    second.join(timeout=5)

    assert len(calls) == 2
    assert controller.is_running is False


def test_runner_failure_is_published_without_background_exception(tmp_path: Path) -> None:
    updates = []
    controller = TrainingResearchController()

    def failed_runner(config):
        raise RuntimeError("data gate blocked")

    thread, container = controller.start(
        tmp_path / "raw",
        tmp_path / "reports",
        status_callback=updates.append,
        runner=failed_runner,
    )
    thread.join(timeout=5)

    status = container["status"]
    assert status["phase"] == "failed"
    assert status["freeze_status"] == "blocked"
    assert status["blocked"] is True
    assert status["blocked_reason"] == "training_research_failed"
    assert status["error"] == "RuntimeError: data gate blocked"
    assert status["final_holdout_evaluated"] is False
    assert status["shadow_eligible"] is False
    assert updates[-1]["phase"] == "failed"


@pytest.mark.parametrize(
    "runner_result",
    [None, {}, SimpleNamespace(report_paths=None), SimpleNamespace(report_paths={})],
)
def test_missing_report_is_completed_but_blocked(tmp_path: Path, runner_result: object) -> None:
    controller = TrainingResearchController()
    thread, container = controller.start(
        tmp_path / "raw",
        tmp_path / "reports",
        runner=lambda config: runner_result,
    )
    thread.join(timeout=5)

    status = container["status"]
    assert status["phase"] == "completed"
    assert status["freeze_status"] == "blocked_missing_report"
    assert status["blocked"] is True
    assert status["report_path"] is None


@pytest.mark.parametrize(
    ("content", "reason_fragment"),
    [
        ("not json", "report_unreadable"),
        ("[]", "report_root_is_not_an_object"),
        ("{}", "report_has_no_freeze_status"),
    ],
)
def test_invalid_report_is_fail_closed(
    tmp_path: Path, content: str, reason_fragment: str
) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(content, encoding="utf-8")
    controller = TrainingResearchController()

    thread, container = controller.start(
        tmp_path / "raw",
        tmp_path / "reports",
        runner=lambda config: _fake_result(report_path),
    )
    thread.join(timeout=5)

    status = container["status"]
    assert status["phase"] == "completed"
    assert status["freeze_status"] == "blocked_missing_freeze_status"
    assert status["blocked"] is True
    assert reason_fragment in status["blocked_reason"]
    assert status["final_holdout_evaluated"] is False
    assert status["shadow_eligible"] is False


def test_status_callback_cannot_break_or_repeat_runner(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path / "report.json")
    calls = 0

    def fake_runner(config):
        nonlocal calls
        calls += 1
        return _fake_result(report_path)

    def broken_callback(status):
        raise RuntimeError("UI disappeared")

    controller = TrainingResearchController()
    thread, container = controller.start(
        tmp_path / "raw",
        tmp_path / "reports",
        status_callback=broken_callback,
        runner=fake_runner,
    )
    thread.join(timeout=5)

    assert calls == 1
    assert container["status"]["phase"] == "completed"


@pytest.mark.parametrize("bad_runner", [None, 1, "runner"])
def test_rejects_non_callable_runner(tmp_path: Path, bad_runner: object) -> None:
    controller = TrainingResearchController()

    with pytest.raises(TypeError, match="runner"):
        controller.start(tmp_path / "raw", tmp_path / "reports", runner=bad_runner)  # type: ignore[arg-type]


def test_report_cannot_claim_holdout_or_shadow_in_controller_status(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "freeze_status": "blocked_by_quality_gates",
                "final_holdout_evaluated": True,
                "shadow_eligible": True,
                "orders_created": True,
            }
        ),
        encoding="utf-8",
    )
    controller = TrainingResearchController()

    thread, container = controller.start(
        tmp_path / "raw",
        tmp_path / "reports",
        runner=lambda config: _fake_result(report_path),
    )
    thread.join(timeout=5)

    status = container["status"]
    assert status["final_holdout_evaluated"] is False
    assert status["shadow_eligible"] is False
    assert status["orders_created"] is False
    assert status["trading_api_used"] is False
    assert status["api_keys_used"] is False
