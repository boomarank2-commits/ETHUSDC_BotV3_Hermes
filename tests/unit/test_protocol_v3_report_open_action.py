"""Task-30 report-open delegation remains typed and read-only."""
from __future__ import annotations

from datetime import UTC, datetime

from ethusdc_bot.protocol_v3.reporting import (
    RESEARCH_CHALLENGER_SHADOW,
    build_protocol_v3_report,
)
from ethusdc_bot.ui.operator_dashboard import OperatorDashboardApp
from ethusdc_bot.ui.protocol_v3_dashboard_bridge import ProtocolV3UiEvidence
from ethusdc_bot.ui.protocol_v3_operator_state import build_protocol_v3_data_status
from ethusdc_bot.ui.research_challenger_controller import ResearchChallengerController


def _report():
    return build_protocol_v3_report(
        artifact_kind=RESEARCH_CHALLENGER_SHADOW,
        report_id="task30_open_report_fixture",
        created_at_utc="2026-07-11T00:00:00Z",
        run_fingerprint="protocol_v3_run_sha256:" + "1" * 64,
        pipeline_generation="protocol_v3_pipeline_sha256:" + "2" * 64,
        window_id="task30_open_window_fixture",
        start_inclusive_utc="2026-07-09T00:00:00Z",
        end_exclusive_utc="2026-07-10T00:00:00Z",
        process_oos_net_usdc=None,
        producer="task30_open_fixture",
        producer_status="completed_diagnostic",
    )


def _app(evidence: ProtocolV3UiEvidence) -> OperatorDashboardApp:
    app = object.__new__(OperatorDashboardApp)
    app.protocol_v3_evidence_provider = lambda: evidence
    app.protocol_v3_challenger_controller = ResearchChallengerController()
    app.protocol_v3_operator_state = None
    app.active_data_thread = None
    app._log = lambda _message: None
    return app


def test_report_open_delegates_once_without_reading_or_mutating_report() -> None:
    calls: list[str] = []
    report = _report()
    before = report.to_dict()
    evidence = ProtocolV3UiEvidence(
        data_status=build_protocol_v3_data_status(
            state="MISSING", blockers=("three_market_data_missing",)
        ),
        challenger_report=report,
        challenger_report_opener=lambda: calls.append("opened"),
    )
    app = _app(evidence)

    app.open_protocol_v3_challenger_report()

    assert calls == ["opened"]
    assert report.to_dict() == before
    assert app.protocol_v3_operator_state is not None
    assert app.protocol_v3_operator_state.to_dict()["buttons"][
        "challenger_report_open"
    ]["enabled"] is True


def test_report_open_stays_disabled_without_validated_report() -> None:
    warnings: list[str] = []
    evidence = ProtocolV3UiEvidence(
        data_status=build_protocol_v3_data_status(
            state="MISSING", blockers=("three_market_data_missing",)
        ),
        challenger_report_opener=lambda: warnings.append("must_not_open"),
    )
    app = _app(evidence)
    app._show_protocol_v3_blocked = lambda button, title: warnings.append(
        f"{button}:{title}"
    )

    app.open_protocol_v3_challenger_report()

    assert warnings == ["challenger_report_open:Diagnosebericht"]
