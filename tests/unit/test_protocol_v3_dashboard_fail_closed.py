"""Additional Task-30 fail-closed UI boundary tests."""
from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from ethusdc_bot.protocol_v3 import pipeline
from ethusdc_bot.ui import protocol_v3_dashboard_mixin as mixin_module
from ethusdc_bot.ui.operator_dashboard import OperatorDashboardApp
from ethusdc_bot.ui.protocol_v3_dashboard_bridge import ProtocolV3UiEvidence
from ethusdc_bot.ui.protocol_v3_operator_state import build_protocol_v3_data_status
from ethusdc_bot.ui.research_challenger_controller import ResearchChallengerController

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK28_PATH = Path(__file__).with_name("test_protocol_v3_current_refit.py")
_SPEC28 = importlib.util.spec_from_file_location(
    "protocol_v3_task30_fail_closed_task28_support", _TASK28_PATH
)
assert _SPEC28 is not None and _SPEC28.loader is not None
task28 = importlib.util.module_from_spec(_SPEC28)
_SPEC28.loader.exec_module(task28)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 20, 12, tzinfo=tz or UTC)


def _report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    return task28.state.__wrapped__(tmp_path, monkeypatch)[-1]


def _ready_data(now: datetime):
    watermark = (int(now.timestamp() * 1000) // 60_000 - 1) * 60_000
    return build_protocol_v3_data_status(
        state="READY",
        common_watermark_open_time_ms=watermark,
        context_identity_sha256="c" * 64,
    )


def _app() -> OperatorDashboardApp:
    app = object.__new__(OperatorDashboardApp)
    app.protocol_v3_challenger_controller = ResearchChallengerController()
    app.protocol_v3_operator_state = None
    app._requested_view = None
    app.active_data_thread = None
    app._log_messages = []
    app._log = app._log_messages.append
    app.refresh_status = lambda **_kwargs: None
    return app


def test_provider_exception_becomes_error_evidence_instead_of_ui_exception() -> None:
    app = _app()

    def broken_provider():
        raise RuntimeError("must not escape into Tk")

    app.protocol_v3_evidence_provider = broken_provider
    evidence = app._protocol_v3_evidence_snapshot()
    payload = evidence.data_status.to_dict()

    assert payload["state"] == "ERROR"
    assert payload["blockers"] == [
        "protocol_v3_evidence_provider_failed:RuntimeError"
    ]
    assert app._log_messages == [
        "Protocol-v3-Evidence-Provider wurde fail-closed blockiert: RuntimeError"
    ]


def test_direct_click_rechecks_parallel_runtime_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mixin_module, "datetime", _FixedDateTime)
    warnings: list[str] = []
    monkeypatch.setattr(
        mixin_module.messagebox,
        "showwarning",
        lambda _title, text: warnings.append(text),
    )
    monkeypatch.setattr(
        mixin_module.messagebox,
        "askyesno",
        lambda *_args, **_kwargs: pytest.fail("confirmation must not open"),
    )
    now = _FixedDateTime.now(UTC)
    app = _app()
    app.protocol_v3_evidence_provider = lambda: ProtocolV3UiEvidence(
        data_status=_ready_data(now),
        pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
        current_refit=_report(tmp_path, monkeypatch),
    )
    app.training_research_controller = SimpleNamespace(is_running=True)

    app.start_protocol_v3_challenger()

    assert app.protocol_v3_challenger_controller.state_snapshot() is None
    assert warnings and "training_research_is_running" in warnings[0]


def test_wrong_provider_type_is_not_treated_as_canonical_evidence() -> None:
    app = _app()
    app.protocol_v3_evidence_provider = lambda: {"data_status": "READY"}

    evidence = app._protocol_v3_evidence_snapshot()

    assert evidence.data_status.to_dict()["state"] == "ERROR"
    assert "TypeError" in evidence.data_status.to_dict()["blockers"][0]
