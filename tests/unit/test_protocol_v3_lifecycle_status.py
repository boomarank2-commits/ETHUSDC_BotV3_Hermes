"""Task-30 lifecycle, final-window, and report-open regressions."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ethusdc_bot.protocol_v3.reporting import (
    PROTOCOL_V3_RESEARCH,
    RESEARCH_CHALLENGER_SHADOW,
    build_protocol_v3_report,
)
from ethusdc_bot.ui.protocol_v3_dashboard_bridge import (
    ProtocolV3UiEvidence,
    format_protocol_v3_operator_view,
    resolve_protocol_v3_operator_state,
)
from ethusdc_bot.ui.protocol_v3_lifecycle_status import (
    ProtocolV3LifecycleStatusError,
    build_protocol_v3_lifecycle_status,
    validate_protocol_v3_lifecycle_status,
)
from ethusdc_bot.ui.protocol_v3_operator_state import (
    ProtocolV3OperatorStateError,
    build_protocol_v3_data_status,
    build_protocol_v3_operator_state,
)


def _missing_data():
    return build_protocol_v3_data_status(
        state="MISSING", blockers=("three_market_data_missing",)
    )


def _report(kind: str):
    return build_protocol_v3_report(
        artifact_kind=kind,
        report_id="task30_report_fixture",
        created_at_utc="2026-07-11T00:00:00Z",
        run_fingerprint="protocol_v3_run_sha256:" + "1" * 64,
        pipeline_generation="protocol_v3_pipeline_sha256:" + "2" * 64,
        window_id="task30_window_fixture",
        start_inclusive_utc="2026-07-09T00:00:00Z",
        end_exclusive_utc="2026-07-10T00:00:00Z",
        process_oos_net_usdc=None,
        producer="task30_fixture",
        producer_status="completed_diagnostic",
    )


def test_lifecycle_states_are_typed_display_only_and_hashed() -> None:
    lifecycle = build_protocol_v3_lifecycle_status(
        process_oos="COMPLETED_DIAGNOSTIC",
        current_refit="RUNNING",
        final_window="SEALED",
        canonical_shadow="NOT_ALLOWED",
        reason_codes=("final_window_still_sealed",),
    )
    payload = lifecycle.to_dict()

    assert validate_protocol_v3_lifecycle_status(lifecycle) == lifecycle
    assert payload["process_oos"] == "COMPLETED_DIAGNOSTIC"
    assert payload["current_refit"] == "RUNNING"
    assert payload["final_window"] == "SEALED"
    assert payload["canonical_shadow"] == "NOT_ALLOWED"
    assert payload["display_only"] is True
    assert payload["runtime_permission_claimed"] is False
    assert len(payload["status_sha256"]) == 64


def test_shadow_eligibility_before_final_evaluation_is_rejected() -> None:
    with pytest.raises(
        ProtocolV3LifecycleStatusError,
        match="cannot be eligible before",
    ):
        build_protocol_v3_lifecycle_status(
            final_window="SEALED",
            canonical_shadow="ELIGIBLE_FROM_VALID_FINAL_REPORT",
        )


def test_final_window_and_process_oos_are_visible_but_unlock_nothing() -> None:
    lifecycle = build_protocol_v3_lifecycle_status(
        process_oos="COMPLETED_DIAGNOSTIC",
        current_refit="FAILED",
        final_window="CONSUMED",
        canonical_shadow="NOT_ALLOWED",
        reason_codes=("sealed_window_consumed_without_valid_final_report",),
    )
    state = build_protocol_v3_operator_state(
        now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        data_status=_missing_data(),
        lifecycle_status=lifecycle,
    )
    payload = state.to_dict()
    text = format_protocol_v3_operator_view(state)

    assert payload["current_refit"]["status"] == "FAILED"
    assert payload["result_meaning"]["process_oos_status"] == (
        "COMPLETED_DIAGNOSTIC"
    )
    assert payload["result_meaning"]["final_window_status"] == "CONSUMED"
    assert payload["buttons"]["canonical_adoption"]["enabled"] is False
    assert payload["result_meaning"]["protocol_v3_final_status"] is False
    assert "Historisches Prozess-OOS: COMPLETED_DIAGNOSTIC" in text
    assert "Späteres Finalfenster: CONSUMED" in text


def test_only_task29_report_with_backend_opener_enables_open_action() -> None:
    report = _report(RESEARCH_CHALLENGER_SHADOW)
    state = resolve_protocol_v3_operator_state(
        ProtocolV3UiEvidence(
            data_status=_missing_data(),
            challenger_report=report,
            challenger_report_opener=lambda: None,
        ),
        now_utc=datetime(2026, 7, 20, tzinfo=UTC),
    ).to_dict()

    assert state["buttons"]["challenger_report_open"] == {
        "enabled": True,
        "blockers": [],
    }
    assert state["research_challenger"]["report_id"] == report.report_id
    assert state["research_challenger"]["report_freshness"] == "NOT_FRESH"


def test_report_without_opener_and_legacy_report_fail_closed() -> None:
    report = _report(RESEARCH_CHALLENGER_SHADOW)
    state = build_protocol_v3_operator_state(
        now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        data_status=_missing_data(),
        challenger_report=report,
    ).to_dict()
    assert state["buttons"]["challenger_report_open"]["enabled"] is False
    assert "report_open_action_missing" in state["buttons"][
        "challenger_report_open"
    ]["blockers"]

    with pytest.raises(
        ProtocolV3OperatorStateError,
        match="only a research_challenger_shadow report",
    ):
        build_protocol_v3_operator_state(
            now_utc=datetime(2026, 7, 20, tzinfo=UTC),
            data_status=_missing_data(),
            challenger_report=_report(PROTOCOL_V3_RESEARCH),
            report_open_available=True,
        )
