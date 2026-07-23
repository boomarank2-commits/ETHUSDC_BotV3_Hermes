"""Real local Task-33 evidence binding for the desktop dashboard."""
from __future__ import annotations

from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3.pipeline import build_pipeline_generation
from ethusdc_bot.protocol_v3.task33_preflight import (
    build_task33_preflight_report,
    write_task33_preflight_report,
)
from ethusdc_bot.ui import protocol_v3_local_evidence as local_evidence

REPO_ROOT = Path(__file__).resolve().parents[2]


def _report(local_root: Path):
    generation = build_pipeline_generation(REPO_ROOT)
    report = build_task33_preflight_report(
        repo_root=REPO_ROOT,
        run_id="task33-ui-test",
        created_at_utc="2026-07-22T14:31:02Z",
        code_commit="a" * 40,
        pipeline_generation_id=generation.generation_id,
        data_snapshot={
            "snapshot_sha256": "b" * 64,
            "availability": {"latest_common_complete_day": "2026-07-07"},
            "common_minute_grid_sha256": "c" * 64,
        },
        exchange_info_snapshot={"snapshot_sha256": "d" * 64},
        trial_ledger_status={
            "head_sha256": "e" * 64,
            "development_dsr_status": "INSUFFICIENT_TRIAL_HISTORY",
            "only_release_decision_allowed": "NO_TRADE",
            "historical_trial_count_is_lower_bound": True,
        },
        runtime_inputs={
            "active_lookbacks": [],
            "horizon_policy": None,
            "production_outer_origin_adapter": False,
        },
    )
    target = (
        local_root
        / "runtime"
        / "protocol_v3"
        / "task33"
        / "task33-preflight-ui-test.json"
    )
    write_task33_preflight_report(report, target)
    return report


def test_latest_validated_task33_report_drives_33_of_33_ui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _report(tmp_path)
    monkeypatch.setattr(local_evidence, "validate_frozen_data_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(local_evidence, "validate_exchange_info_snapshot", lambda *a, **k: None)

    evidence = local_evidence.load_latest_task33_ui_evidence(REPO_ROOT, tmp_path)

    assert evidence.task33_preflight == report
    assert evidence.data_status.to_dict()["state"] == "READY"
    assert evidence.data_status.to_dict()["common_watermark_open_time_ms"] == 1783468740000
    assert evidence.research_progress.to_dict()["phase"] == "blocked_preflight"
    assert evidence.lifecycle_status.to_dict()["process_oos"] == "FAILED"


def test_invalid_or_oversized_report_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "runtime" / "protocol_v3" / "task33"
    root.mkdir(parents=True)
    (root / "task33-preflight-bad.json").write_text('{"duplicate":1,"duplicate":2}', encoding="utf-8")

    with pytest.raises(local_evidence.ProtocolV3LocalEvidenceError, match="no valid"):
        local_evidence.load_latest_task33_ui_evidence(REPO_ROOT, tmp_path)
