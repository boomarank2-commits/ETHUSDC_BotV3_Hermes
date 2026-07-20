"""Task-30 pure Protocol-v3 operator-state regressions."""
from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import pipeline
from ethusdc_bot.ui import protocol_v3_operator_state as ui_state

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK28_PATH = Path(__file__).with_name("test_protocol_v3_current_refit.py")
_SPEC28 = importlib.util.spec_from_file_location(
    "protocol_v3_task30_task28_support", _TASK28_PATH
)
assert _SPEC28 is not None and _SPEC28.loader is not None
task28 = importlib.util.module_from_spec(_SPEC28)
_SPEC28.loader.exec_module(task28)


def _report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return task28.state.__wrapped__(tmp_path, monkeypatch)[-1]


def _ready_data(now: datetime):
    watermark = (int(now.timestamp() * 1000) // 60_000 - 1) * 60_000
    return ui_state.build_protocol_v3_data_status(
        state="READY",
        common_watermark_open_time_ms=watermark,
        context_identity_sha256="c" * 64,
    )


def test_task_progress_is_only_done_100_over_33() -> None:
    state = ui_state.build_protocol_v3_operator_state(
        now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        data_status=ui_state.build_protocol_v3_data_status(
            state="MISSING", blockers=["three_market_data_missing"]
        ),
    ).to_dict()

    assert state["task_progress"] == {
        "done_tasks": 29,
        "total_tasks": 33,
        "progress_pct": 87.88,
        "active_task": 30,
        "active_task_status": "IN_PROGRESS",
    }
    assert state["outer_pnl_visible"] is False
    assert state["research_progress"] is None


def test_missing_evidence_disables_every_trading_related_action() -> None:
    state = ui_state.build_protocol_v3_operator_state(
        now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        data_status=ui_state.build_protocol_v3_data_status(
            state="STALE", blockers=["common_watermark_is_stale"]
        ),
    ).to_dict()

    start = state["buttons"]["challenger_start"]
    assert start["enabled"] is False
    assert "validated_task28_provenance_missing" in start["blockers"]
    assert "data:common_watermark_is_stale" in start["blockers"]
    for name in ("paper", "testtrade", "live", "canonical_adoption"):
        assert state["buttons"][name]["enabled"] is False
    assert state["safety"] == {
        "orders": "gesperrt",
        "paper": "gesperrt",
        "testtrade": "gesperrt",
        "live": "gesperrt",
        "trading_api_private_endpoints": "nicht verwendet",
        "canonical_adoption": "nicht zulässig",
        "bot_start": "nicht erlaubt",
    }


def test_valid_task28_generation_and_watermark_enable_manual_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(tmp_path, monkeypatch)
    generation = pipeline.build_pipeline_generation(REPO_ROOT)
    now = datetime(2026, 7, 9, 12, tzinfo=UTC)

    first = ui_state.build_protocol_v3_operator_state(
        now_utc=now,
        data_status=_ready_data(now),
        pipeline_generation=generation,
        current_refit=report,
        resume_worker_available=True,
    )
    second = ui_state.build_protocol_v3_operator_state(
        now_utc=now,
        data_status=_ready_data(now),
        pipeline_generation=generation,
        current_refit=report,
        resume_worker_available=True,
    )
    payload = first.to_dict()

    assert first == second
    assert payload["operator_mode"] == "current_refit"
    assert payload["current_refit"]["status"] == "CASH"
    assert payload["buttons"]["challenger_start"] == {
        "enabled": True,
        "blockers": [],
    }
    assert payload["buttons"]["canonical_adoption"]["enabled"] is False
    assert payload["ui_may_create_orders"] is False
    assert payload["ui_may_write_active_config"] is False


def test_ready_label_cannot_hide_stale_or_unclosed_watermark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(tmp_path, monkeypatch)
    generation = pipeline.build_pipeline_generation(REPO_ROOT)
    now = datetime(2026, 7, 20, 12, 30, tzinfo=UTC)
    expected = (int(now.timestamp() * 1000) // 60_000 - 1) * 60_000

    stale = ui_state.build_protocol_v3_data_status(
        state="READY",
        common_watermark_open_time_ms=expected - 60_000,
        context_identity_sha256="c" * 64,
    )
    future = ui_state.build_protocol_v3_data_status(
        state="READY",
        common_watermark_open_time_ms=expected + 60_000,
        context_identity_sha256="c" * 64,
    )
    stale_state = ui_state.build_protocol_v3_operator_state(
        now_utc=now,
        data_status=stale,
        pipeline_generation=generation,
        current_refit=report,
    ).to_dict()
    future_state = ui_state.build_protocol_v3_operator_state(
        now_utc=now,
        data_status=future,
        pipeline_generation=generation,
        current_refit=report,
    ).to_dict()

    assert "three_market_watermark_is_stale" in stale_state["buttons"][
        "challenger_start"
    ]["blockers"]
    assert "three_market_watermark_is_future_or_unclosed" in future_state[
        "buttons"
    ]["challenger_start"]["blockers"]


def test_expired_refit_shows_next_anchor_and_never_backfills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(tmp_path, monkeypatch)
    now = datetime(2026, 8, 8, tzinfo=UTC)
    state = ui_state.build_protocol_v3_operator_state(
        now_utc=now,
        data_status=_ready_data(now),
        pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
        current_refit=report,
    ).to_dict()

    assert state["current_refit"]["status"] == "EXPIRED"
    assert state["current_refit"]["next_month_anchor_utc"] == (
        "2026-08-08T00:00:00Z"
    )
    button = state["buttons"]["challenger_start"]
    assert button["enabled"] is False
    assert "task28_window_expired_use_next_month_anchor" in button["blockers"]


def test_progress_keeps_outer_pnl_hidden() -> None:
    progress = ui_state.build_protocol_v3_research_progress(
        phase="inner_selection",
        completed_origins=3,
        active_origin=4,
        completed_folds=2,
        active_fold=3,
        completed_cycles=1,
        total_cycles=8,
        tested_candidates=12,
        current_step="evaluate fold 3",
    ).to_dict()

    assert progress["completed_origins"] == 3
    assert progress["active_origin"] == 4
    assert progress["completed_folds"] == 2
    assert progress["active_fold"] == 3
    assert progress["outer_pnl_visible"] is False
    assert "pnl" not in {key.lower() for key in progress if key != "outer_pnl_visible"}


def test_untyped_task28_and_contradictory_worker_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(tmp_path, monkeypatch)
    now = datetime(2026, 7, 9, 12, tzinfo=UTC)
    with pytest.raises(
        ui_state.ProtocolV3OperatorStateError,
        match="typed validated Task-28",
    ):
        ui_state.build_protocol_v3_operator_state(
            now_utc=now,
            data_status=_ready_data(now),
            pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
            current_refit=report.to_dict(),  # type: ignore[arg-type]
        )

    with pytest.raises(
        ui_state.ProtocolV3OperatorStateError,
        match="contradictory",
    ):
        ui_state.build_protocol_v3_operator_state(
            now_utc=datetime(2026, 7, 20, tzinfo=UTC),
            data_status=_ready_data(datetime(2026, 7, 20, tzinfo=UTC)),
            worker_status={"phase": "running", "running": False},
        )
