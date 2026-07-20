"""Task-30 asynchronous research-challenger controller regressions."""
from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
import threading

import pytest

from ethusdc_bot.protocol_v3 import pipeline, research_challenger
from ethusdc_bot.protocol_v3.research_challenger_checkpoint import (
    build_research_challenger_checkpoint_receipt,
)
from ethusdc_bot.ui.research_challenger_controller import (
    ResearchChallengerController,
    ResearchChallengerUiRunResult,
    build_initial_research_challenger_ui_status,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK28_PATH = Path(__file__).with_name("test_protocol_v3_current_refit.py")
_SPEC28 = importlib.util.spec_from_file_location(
    "protocol_v3_task30_controller_task28_support", _TASK28_PATH
)
assert _SPEC28 is not None and _SPEC28.loader is not None
task28 = importlib.util.module_from_spec(_SPEC28)
_SPEC28.loader.exec_module(task28)


def _report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return task28.state.__wrapped__(tmp_path, monkeypatch)[-1]


def _start_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return research_challenger.start_research_challenger(
        _report(tmp_path, monkeypatch),
        started_at_utc=datetime(2026, 7, 9, 12, tzinfo=UTC),
        current_pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
    )


def test_initial_status_is_inert_and_fully_locked() -> None:
    status = build_initial_research_challenger_ui_status()

    assert status["phase"] == "initial"
    assert status["running"] is False
    assert status["resume_ready"] is False
    assert status["orders_allowed"] is False
    assert status["orders_created"] == 0
    assert status["private_api_calls"] == 0
    assert status["canonical_adoption_eligible"] is False
    assert status["protocol_v3_final_status"] is False


def test_manual_start_initializes_only_validated_empty_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = ResearchChallengerController()
    updates: list[dict] = []
    thread, result = controller.start(
        _report(tmp_path, monkeypatch),
        started_at_utc=datetime(2026, 7, 9, 12, tzinfo=UTC),
        current_pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
        status_callback=updates.append,
    )
    thread.join(timeout=10)

    assert thread.is_alive() is False
    state = result["state"]
    payload = state.to_dict()
    status = result["status"]
    assert payload["forward_ledger"]["record_count"] == 0
    assert status["phase"] == "initialized"
    assert status["resume_ready"] is False
    assert status["checkpoint_receipt_sha256"] is None
    assert status["state_sha256"] == state.state_sha256
    assert status["ledger_head_sha256"] == research_challenger.ZERO_HASH
    assert status["orders_created"] == 0
    assert status["private_api_calls"] == 0
    assert controller.state_snapshot() == state
    assert controller.checkpoint_snapshot() is None
    assert updates[0]["phase"] == "starting"
    assert updates[-1]["phase"] == "initialized"


def test_double_start_is_blocked_while_initializer_is_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = ResearchChallengerController()
    entered = threading.Event()
    release = threading.Event()
    report = _report(tmp_path, monkeypatch)
    generation = pipeline.build_pipeline_generation(REPO_ROOT)

    def initializer(task28_decision, **kwargs):
        entered.set()
        assert release.wait(timeout=10)
        return research_challenger.start_research_challenger(
            task28_decision,
            started_at_utc=kwargs["started_at_utc"],
            current_pipeline_generation=kwargs["current_pipeline_generation"],
            exchange_info_snapshot=kwargs["exchange_info_snapshot"],
        )

    thread, _ = controller.start(
        report,
        started_at_utc=datetime(2026, 7, 9, 12, tzinfo=UTC),
        current_pipeline_generation=generation,
        initializer=initializer,
    )
    assert entered.wait(timeout=10)
    with pytest.raises(RuntimeError, match="already running"):
        controller.start(
            report,
            started_at_utc=datetime(2026, 7, 9, 12, tzinfo=UTC),
            current_pipeline_generation=generation,
        )
    release.set()
    thread.join(timeout=10)
    assert thread.is_alive() is False


def test_resume_stop_requires_and_returns_bit_identical_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _start_state(tmp_path, monkeypatch)
    receipt = build_research_challenger_checkpoint_receipt(state)
    controller = ResearchChallengerController()
    entered = threading.Event()

    def worker(current, stop_event, _callback):
        entered.set()
        assert stop_event.wait(timeout=10)
        return ResearchChallengerUiRunResult(
            current,
            build_research_challenger_checkpoint_receipt(current),
        )

    thread, result = controller.resume(state, receipt, worker=worker)
    assert entered.wait(timeout=10)
    stopping = controller.stop()
    thread.join(timeout=10)

    assert stopping["phase"] == "stopping"
    assert stopping["stop_requested"] is True
    assert result["status"]["phase"] == "paused"
    assert result["status"]["resume_ready"] is True
    assert result["status"]["state_sha256"] == state.state_sha256
    assert result["status"]["checkpoint_receipt_sha256"] == receipt.receipt_sha256
    assert result["status"]["orders_allowed"] is False
    assert result["status"]["paper_allowed"] is False
    assert result["status"]["live_allowed"] is False
    assert result["status"]["active_config_written"] is False
    assert controller.state_snapshot() == state
    assert controller.checkpoint_snapshot() == receipt


def test_resume_rejects_worker_result_without_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _start_state(tmp_path, monkeypatch)
    receipt = build_research_challenger_checkpoint_receipt(state)
    controller = ResearchChallengerController()

    thread, result = controller.resume(
        state,
        receipt,
        worker=lambda current, _stop, _callback: ResearchChallengerUiRunResult(
            current, None
        ),
    )
    thread.join(timeout=10)

    assert result["status"]["phase"] == "failed"
    assert result["status"]["resume_ready"] is False
    assert "checkpoint receipt" in result["status"]["error"]


def test_untyped_start_and_resume_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = ResearchChallengerController()
    report = _report(tmp_path, monkeypatch)
    generation = pipeline.build_pipeline_generation(REPO_ROOT)
    state = _start_state(tmp_path / "state", monkeypatch)
    receipt = build_research_challenger_checkpoint_receipt(state)

    with pytest.raises(TypeError, match="CurrentRefitDecision"):
        controller.start(
            report.to_dict(),  # type: ignore[arg-type]
            started_at_utc=datetime(2026, 7, 9, 12, tzinfo=UTC),
            current_pipeline_generation=generation,
        )
    with pytest.raises(TypeError, match="ResearchChallengerState"):
        controller.resume(  # type: ignore[arg-type]
            {},
            receipt,
            worker=lambda current, stop, callback: ResearchChallengerUiRunResult(
                current, receipt
            ),
        )
    with pytest.raises(TypeError, match="ResearchChallengerCheckpointReceipt"):
        controller.resume(  # type: ignore[arg-type]
            state,
            {},
            worker=lambda current, stop, callback: ResearchChallengerUiRunResult(
                current, receipt
            ),
        )
