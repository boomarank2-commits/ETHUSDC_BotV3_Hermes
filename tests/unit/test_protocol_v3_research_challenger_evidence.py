"""Task-29 integration with the existing Task-11 and Task-12 stores."""
from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import research_challenger
from ethusdc_bot.protocol_v3.artifact_store_api import read_compact_artifact_bundle
from ethusdc_bot.protocol_v3.reporting_api import (
    RESEARCH_CHALLENGER_SHADOW,
    read_protocol_v3_report,
)
from ethusdc_bot.protocol_v3 import research_challenger_evidence
from ethusdc_bot.protocol_v3 import research_challenger_evidence_api

_TASK29_PATH = Path(__file__).with_name("test_protocol_v3_research_challenger.py")
_SPEC29 = importlib.util.spec_from_file_location(
    "protocol_v3_task29_evidence_support", _TASK29_PATH
)
assert _SPEC29 is not None and _SPEC29.loader is not None
task29 = importlib.util.module_from_spec(_SPEC29)
_SPEC29.loader.exec_module(task29)
_REPORT_CLOCK = datetime(2026, 7, 16, tzinfo=UTC)


def _state_with_minutes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    count: int,
):
    report = task29.task28.state.__wrapped__(tmp_path / "task28", monkeypatch)[-1]
    valid_from = datetime(2026, 7, 9, tzinfo=UTC)
    state = research_challenger.start_research_challenger(
        report,
        started_at_utc=valid_from,
    )
    binding = task29._binding(int(valid_from.timestamp() * 1000), count=count)
    monkeypatch.setattr(
        research_challenger, "validate_context_parity_binding", lambda value: None
    )
    monkeypatch.setattr(
        research_challenger, "evaluate_closed_bar_context", task29._allow_context
    )
    observed = datetime.fromtimestamp(
        (binding.common_watermark_open_time_ms + 59_999) / 1000,
        tz=UTC,
    )
    return research_challenger.advance_research_challenger(
        state,
        binding,
        observed_at_utc=observed,
    ).state


def test_complete_cash_day_builds_and_persists_existing_report_and_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _state_with_minutes(tmp_path, monkeypatch, 1440)
    evidence = research_challenger_evidence.build_research_challenger_evidence(
        state,
        report_id="task29_cash_day",
        created_at_utc=_REPORT_CLOCK,
    )

    report = evidence.report.to_dict()
    assert report["artifact_kind"] == RESEARCH_CHALLENGER_SHADOW
    assert report["evidence_window"]["calendar_days"] == 1
    assert report["evidence_status"]["freshness"] == "NOT_FRESH"
    assert report["evidence_status"]["diagnostic_only"] is True
    assert report["evidence_status"]["statistically_supported"] is False
    assert report["evidence_status"]["canonical_adoption_eligible"] is False
    assert evidence.artifacts["trades"].logical_cardinality == 0
    assert evidence.artifacts["daily_mtm"].logical_cardinality == 1
    assert evidence.artifacts["daily_mtm"].to_dict()["records"] == [
        {"day_utc": "2026-07-09", "net_mtm_usdc": 0.0}
    ]
    assert evidence.artifacts["equity_underwater"].logical_cardinality == 1440
    assert evidence.artifacts["diagnostics"].logical_cardinality == 1440

    repository = tmp_path / "repository"
    repository.mkdir()
    persisted = research_challenger_evidence.persist_research_challenger_evidence(
        evidence,
        repository_root=repository,
    )
    assert read_protocol_v3_report(persisted.report_path, repository) == evidence.report
    bundle = read_compact_artifact_bundle(
        persisted.artifact_index_path,
        repository,
    )
    assert set(bundle.artifacts) == {
        "trades",
        "daily_mtm",
        "equity_underwater",
        "diagnostics",
    }
    assert bundle.index.to_dict()["work_unit"]["identity"] == dict(
        evidence.work_unit_identity
    )


def test_incomplete_utc_day_cannot_be_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _state_with_minutes(tmp_path, monkeypatch, 1439)

    with pytest.raises(
        research_challenger.ResearchChallengerError,
        match="complete UTC day",
    ):
        research_challenger_evidence.build_research_challenger_evidence(
            state,
            report_id="task29_incomplete",
            created_at_utc=_REPORT_CLOCK,
        )


def test_task29_evidence_api_is_exact() -> None:
    assert (
        research_challenger_evidence_api.__all__
        == research_challenger_evidence.__all__
    )
