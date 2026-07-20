"""Task-30 typed dashboard bridge, formatting, and restart regressions."""
from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import pipeline
from ethusdc_bot.protocol_v3.research_challenger_checkpoint import (
    build_research_challenger_checkpoint_receipt,
)
from ethusdc_bot.ui.protocol_v3_dashboard_bridge import (
    ProtocolV3UiEvidence,
    build_empty_protocol_v3_ui_evidence,
    format_protocol_v3_operator_view,
    protocol_v3_button_blocker_text,
    resolve_protocol_v3_operator_state,
)
from ethusdc_bot.ui.protocol_v3_operator_state import (
    build_protocol_v3_data_status,
    build_protocol_v3_research_progress,
)
from ethusdc_bot.ui.research_challenger_controller import ResearchChallengerUiRunResult

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK28_PATH = Path(__file__).with_name("test_protocol_v3_current_refit.py")
_SPEC28 = importlib.util.spec_from_file_location(
    "protocol_v3_task30_bridge_task28_support", _TASK28_PATH
)
assert _SPEC28 is not None and _SPEC28.loader is not None
task28 = importlib.util.module_from_spec(_SPEC28)
_SPEC28.loader.exec_module(task28)

_TASK29_PATH = Path(__file__).with_name(
    "test_protocol_v3_research_challenger_checkpoint.py"
)
_SPEC29 = importlib.util.spec_from_file_location(
    "protocol_v3_task30_bridge_task29_support", _TASK29_PATH
)
assert _SPEC29 is not None and _SPEC29.loader is not None
task29 = importlib.util.module_from_spec(_SPEC29)
_SPEC29.loader.exec_module(task29)


def _report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return task28.state.__wrapped__(tmp_path, monkeypatch)[-1]


def _ready_data():
    return build_protocol_v3_data_status(
        state="READY",
        common_watermark_open_time_ms=1_752_105_600_000,
        context_identity_sha256="c" * 64,
    )


def test_empty_bridge_is_fail_closed_and_explains_every_button() -> None:
    state = resolve_protocol_v3_operator_state(
        build_empty_protocol_v3_ui_evidence(),
        now_utc=datetime(2026, 7, 20, tzinfo=UTC),
    )
    payload = state.to_dict()
    text = format_protocol_v3_operator_view(state)

    assert payload["buttons"]["challenger_start"]["enabled"] is False
    assert "validated_task28_provenance_missing" in protocol_v3_button_blocker_text(
        state, "challenger_start"
    )
    assert "PROTOCOL V3" in text
    assert "Orders: gesperrt" in text
    assert "Bot-Start: nicht erlaubt" in text
    assert "Kanonische Adoption: GESPERRT" in text


def test_valid_refit_view_is_idempotent_and_never_displays_outer_pnl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = ProtocolV3UiEvidence(
        data_status=_ready_data(),
        pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
        current_refit=_report(tmp_path, monkeypatch),
        research_progress=build_protocol_v3_research_progress(
            phase="inner_selection",
            completed_origins=3,
            active_origin=4,
            completed_folds=2,
            active_fold=3,
            completed_cycles=9,
            total_cycles=96,
            tested_candidates=108,
            current_step="Task-18 DSR",
        ),
    )
    first = resolve_protocol_v3_operator_state(
        evidence, now_utc=datetime(2026, 7, 9, 12, tzinfo=UTC)
    )
    second = resolve_protocol_v3_operator_state(
        evidence, now_utc=datetime(2026, 7, 9, 12, tzinfo=UTC)
    )
    text = format_protocol_v3_operator_view(first)

    assert first == second
    assert first.to_dict()["buttons"]["challenger_start"]["enabled"] is True
    assert "Origins: 3/12" in text
    assert "Folds: 2/6" in text
    assert "Outer-PnL bleibt" in text
    assert "Netto pro Tag" not in text
    assert "Profit Factor" not in text


def test_restart_uses_exact_state_and_checkpoint_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = task29._cash_state(tmp_path, monkeypatch)
    receipt = build_research_challenger_checkpoint_receipt(state)

    def worker(current, _stop, _callback):
        return ResearchChallengerUiRunResult(current, receipt)

    evidence = ProtocolV3UiEvidence(
        data_status=_ready_data(),
        pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
        current_refit=_report(tmp_path / "refit", monkeypatch),
        challenger_state=state,
        challenger_checkpoint=receipt,
        resume_worker=worker,
    )
    before = state.to_dict()
    first = resolve_protocol_v3_operator_state(
        evidence, now_utc=datetime(2026, 7, 20, tzinfo=UTC)
    )
    second = resolve_protocol_v3_operator_state(
        evidence, now_utc=datetime(2026, 7, 20, tzinfo=UTC)
    )

    assert first == second
    assert state.to_dict() == before
    payload = first.to_dict()
    assert payload["research_challenger"]["state_sha256"] == state.state_sha256
    assert payload["research_challenger"]["checkpoint_receipt_sha256"] == (
        receipt.receipt_sha256
    )
    assert payload["buttons"]["challenger_resume"]["enabled"] is True
    assert payload["buttons"]["canonical_adoption"]["enabled"] is False


def test_checkpoint_without_backend_worker_stays_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = task29._cash_state(tmp_path, monkeypatch)
    receipt = build_research_challenger_checkpoint_receipt(state)
    evidence = ProtocolV3UiEvidence(
        data_status=_ready_data(),
        pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
        challenger_state=state,
        challenger_checkpoint=receipt,
    )
    operator = resolve_protocol_v3_operator_state(
        evidence, now_utc=datetime(2026, 7, 20, tzinfo=UTC)
    )

    assert operator.to_dict()["buttons"]["challenger_resume"]["enabled"] is False
    assert "public_data_resume_worker_missing" in protocol_v3_button_blocker_text(
        operator, "challenger_resume"
    )
