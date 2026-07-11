"""Tests for the explicit one-shot final-evaluation UI boundary."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import threading

import pytest

from ethusdc_bot.ui.final_evaluation_controller import (
    FinalEvaluationController,
    build_initial_final_evaluation_status,
    discover_latest_frozen_research_report,
)


def test_initial_status_keeps_every_external_action_locked():
    status = build_initial_final_evaluation_status()

    assert status["phase"] == "initial"
    assert status["final_holdout_evaluated"] is False
    assert status["retry_allowed"] is False
    assert status["shadow_eligible"] is False
    assert status["orders_created"] is False
    assert status["trading_api_used"] is False
    assert status["api_keys_used"] is False
    assert status["live_eligible"] is False


def test_discovery_is_read_only_and_requires_unconsumed_sealed_freeze(tmp_path):
    root = tmp_path / "research"
    root.mkdir()
    payload = {
        "schema_version": 2,
        "execution_profile": "production_protocol",
        "fixture_data_only": False,
        "freeze_status": "frozen_for_separate_sealed_holdout",
        "frozen_candidate": {"candidate_id": "candidate_1"},
        "loop_run_id": "research_1",
        "audit_policy": {"freeze_eligible": True},
        "window_plan": {
            "final_holdout_window": {
                "status": "sealed_unopened",
                "consumed_audit_window": False,
                "evaluated": False,
                "days": 365,
            }
        },
    }
    path = root / "research_1.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = path.read_bytes()

    status = discover_latest_frozen_research_report(root)

    assert status["status"] == "ready_for_explicit_one_shot"
    assert status["report_path"] == str(path)
    assert status["candidate_id"] == "candidate_1"
    assert path.read_bytes() == before


def test_discovery_rejects_consumed_or_evaluated_holdout(tmp_path):
    root = tmp_path / "research"
    root.mkdir()
    for index, mutation in enumerate(("consumed", "evaluated")):
        payload = {
            "schema_version": 2,
            "execution_profile": "production_protocol",
            "fixture_data_only": False,
            "freeze_status": "frozen_for_separate_sealed_holdout",
            "frozen_candidate": {"candidate_id": "candidate_1"},
            "audit_policy": {"freeze_eligible": True},
            "window_plan": {
                "final_holdout_window": {
                    "status": "sealed_unopened",
                    "consumed_audit_window": mutation == "consumed",
                    "evaluated": mutation == "evaluated",
                    "days": 365,
                }
            },
        }
        (root / f"{index}.json").write_text(json.dumps(payload), encoding="utf-8")

    assert discover_latest_frozen_research_report(root)["status"] == "not_ready"


def test_controller_runs_once_and_reassesses_final_report(monkeypatch, tmp_path):
    source = tmp_path / "research.json"
    final = tmp_path / "final.json"
    source.write_text("{}", encoding="utf-8")
    final.write_text("{}", encoding="utf-8")
    calls = []
    callbacks = []
    controller = FinalEvaluationController()

    def runner(source_path, raw_root, reports_root):
        calls.append((source_path, raw_root, reports_root))
        return SimpleNamespace(final_report_path=final)

    monkeypatch.setattr(
        "ethusdc_bot.ui.final_evaluation_controller.assess_final_report",
        lambda path: SimpleNamespace(
            color="yellow",
            target_reached=False,
            shadow_eligible=True,
        ),
    )
    thread, container = controller.start(
        source,
        tmp_path / "raw",
        tmp_path / "reports",
        status_callback=callbacks.append,
        runner=runner,
    )
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(calls) == 1
    assert callbacks[0]["phase"] == "running"
    assert callbacks[-1]["phase"] == "completed"
    status = container["status"]
    assert status["final_holdout_evaluated"] is True
    assert status["assessment_color"] == "yellow"
    assert status["shadow_eligible"] is True
    assert status["live_eligible"] is False
    assert status["orders_created"] is False


def test_failure_is_non_retryable_and_never_claims_shadow_or_live(tmp_path):
    controller = FinalEvaluationController()

    def runner(*_args):
        raise RuntimeError("claim may already exist")

    thread, container = controller.start(
        tmp_path / "source.json",
        tmp_path / "raw",
        tmp_path / "reports",
        runner=runner,
    )
    thread.join(timeout=5)
    status = container["status"]

    assert status["phase"] == "failed"
    assert status["retry_allowed"] is False
    assert status["final_holdout_evaluated"] is False
    assert status["final_holdout_outcome"] == "failed_or_claimed_manual_audit_required"
    assert status["shadow_eligible"] is False
    assert status["live_eligible"] is False


def test_controller_rejects_overlapping_final_evaluations(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    controller = FinalEvaluationController()

    def runner(*_args):
        entered.set()
        release.wait(timeout=5)
        raise RuntimeError("stop test")

    thread, _ = controller.start(
        tmp_path / "source.json",
        tmp_path / "raw",
        tmp_path / "reports",
        runner=runner,
    )
    assert entered.wait(timeout=5)
    with pytest.raises(RuntimeError, match="already running"):
        controller.start(
            tmp_path / "source.json",
            tmp_path / "raw",
            tmp_path / "reports",
            runner=runner,
        )
    release.set()
    thread.join(timeout=5)
