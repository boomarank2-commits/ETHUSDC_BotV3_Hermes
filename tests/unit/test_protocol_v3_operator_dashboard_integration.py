"""Task-30 integration tests for the single existing OperatorDashboardApp."""
from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
import inspect
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import pipeline
from ethusdc_bot.protocol_v3.research_challenger_checkpoint import (
    build_research_challenger_checkpoint_receipt,
)
from ethusdc_bot.ui import protocol_v3_dashboard_mixin as mixin_module
from ethusdc_bot.ui.operator_dashboard import OperatorDashboardApp
from ethusdc_bot.ui.protocol_v3_dashboard_bridge import ProtocolV3UiEvidence
from ethusdc_bot.ui.protocol_v3_dashboard_mixin import ProtocolV3DashboardMixin
from ethusdc_bot.ui.protocol_v3_operator_state import (
    build_protocol_v3_data_status,
    build_protocol_v3_operator_state,
)
from ethusdc_bot.ui.research_challenger_controller import (
    ResearchChallengerController,
    ResearchChallengerUiRunResult,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK28_PATH = Path(__file__).with_name("test_protocol_v3_current_refit.py")
_SPEC28 = importlib.util.spec_from_file_location(
    "protocol_v3_task30_dashboard_task28_support", _TASK28_PATH
)
assert _SPEC28 is not None and _SPEC28.loader is not None
task28 = importlib.util.module_from_spec(_SPEC28)
_SPEC28.loader.exec_module(task28)

_TASK29_PATH = Path(__file__).with_name(
    "test_protocol_v3_research_challenger_checkpoint.py"
)
_SPEC29 = importlib.util.spec_from_file_location(
    "protocol_v3_task30_dashboard_task29_support", _TASK29_PATH
)
assert _SPEC29 is not None and _SPEC29.loader is not None
task29 = importlib.util.module_from_spec(_SPEC29)
_SPEC29.loader.exec_module(task29)


class _Button:
    def __init__(self) -> None:
        self.state = None

    def configure(self, **values) -> None:
        self.state = values.get("state")


class _Var:
    def __init__(self) -> None:
        self.value = None

    def set(self, value) -> None:
        self.value = value


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


def _fake_app() -> OperatorDashboardApp:
    app = object.__new__(OperatorDashboardApp)
    app.protocol_v3_start_button = _Button()
    app.protocol_v3_resume_button = _Button()
    app.protocol_v3_stop_button = _Button()
    app.load_button = _Button()
    app.check_button = _Button()
    app.training_button = _Button()
    app.final_evaluation_button = _Button()
    app.adopt_shadow_button = _Button()
    app.shadow_start_button = _Button()
    app.bot_state_var = _Var()
    app.phase_var = _Var()
    app.shadow_var = _Var()
    return app


def test_single_existing_dashboard_uses_protocol_v3_mixin_and_provider() -> None:
    assert issubclass(OperatorDashboardApp, ProtocolV3DashboardMixin)
    signature = inspect.signature(OperatorDashboardApp.__init__)
    assert "protocol_v3_evidence_provider" in signature.parameters
    assert OperatorDashboardApp.__mro__.count(OperatorDashboardApp) == 1


def test_apply_state_sets_only_snapshot_derived_button_states() -> None:
    app = _fake_app()
    state = build_protocol_v3_operator_state(
        now_utc=datetime(2026, 7, 20, tzinfo=UTC),
        data_status=build_protocol_v3_data_status(
            state="MISSING", blockers=("three_market_data_missing",)
        ),
    )

    app._apply_protocol_v3_operator_state(state)

    assert app.protocol_v3_start_button.state == "disabled"
    assert app.protocol_v3_resume_button.state == "disabled"
    assert app.protocol_v3_stop_button.state == "disabled"
    for control in (
        app.load_button,
        app.check_button,
        app.training_button,
        app.final_evaluation_button,
        app.adopt_shadow_button,
        app.shadow_start_button,
    ):
        assert control.state == "disabled"
    assert "Bot-Start bleibt gesperrt" in app.bot_state_var.value
    assert "Orders 0" in app.shadow_var.value


def test_protocol_v3_overview_navigation_is_read_only() -> None:
    app = _fake_app()
    app._requested_view = "protocol_v3"
    calls: list[dict] = []
    app.refresh_status = lambda **kwargs: calls.append(dict(kwargs))

    app.show_protocol_v3_overview()

    assert app._requested_view == "download"
    assert calls == [{"log_refresh": False}]


def test_parallel_runtime_blocker_disables_start_with_exact_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    state = build_protocol_v3_operator_state(
        now_utc=now,
        data_status=_ready_data(now),
        pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
        current_refit=_report(tmp_path, monkeypatch),
        ui_runtime_blockers=("training_research_is_running",),
    ).to_dict()

    assert state["buttons"]["challenger_start"]["enabled"] is False
    assert "training_research_is_running" in state["buttons"]["challenger_start"][
        "blockers"
    ]


def test_dashboard_manual_start_calls_only_task29_controller(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mixin_module, "datetime", _FixedDateTime)
    monkeypatch.setattr(mixin_module.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(mixin_module.messagebox, "showerror", lambda *a, **k: None)
    now = _FixedDateTime.now(UTC)

    def worker(current, _stop, _callback):
        return ResearchChallengerUiRunResult(
            current, build_research_challenger_checkpoint_receipt(current)
        )

    evidence = ProtocolV3UiEvidence(
        data_status=_ready_data(now),
        pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
        current_refit=_report(tmp_path, monkeypatch),
        resume_worker=worker,
    )
    app = _fake_app()
    app.protocol_v3_evidence_provider = lambda: evidence
    app.protocol_v3_challenger_controller = ResearchChallengerController()
    app.protocol_v3_operator_state = None
    app._requested_view = None
    app._log = lambda _message: None
    app.refresh_status = lambda **_kwargs: None

    app.start_protocol_v3_challenger()
    for _ in range(100):
        if not app.protocol_v3_challenger_controller.is_running:
            break
        import time

        time.sleep(0.01)

    state = app.protocol_v3_challenger_controller.state_snapshot()
    assert state is not None
    assert state.to_dict()["forward_ledger"]["record_count"] == 0
    status = app.protocol_v3_challenger_controller.status_snapshot()
    assert status["phase"] == "resume_ready"
    assert status["resume_ready"] is True
    assert status["checkpoint_receipt_sha256"] is not None
    assert status["orders_created"] == 0
    assert status["private_api_calls"] == 0
    assert app._requested_view == "protocol_v3"


def test_dashboard_resume_uses_validated_checkpoint_and_backend_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mixin_module, "datetime", _FixedDateTime)
    now = _FixedDateTime.now(UTC)
    state = task29._cash_state(tmp_path, monkeypatch)
    receipt = build_research_challenger_checkpoint_receipt(state)

    def worker(current, _stop, _callback):
        return ResearchChallengerUiRunResult(current, receipt)

    evidence = ProtocolV3UiEvidence(
        data_status=_ready_data(now),
        pipeline_generation=pipeline.build_pipeline_generation(REPO_ROOT),
        challenger_state=state,
        challenger_checkpoint=receipt,
        resume_worker=worker,
    )
    app = _fake_app()
    app.protocol_v3_evidence_provider = lambda: evidence
    app.protocol_v3_challenger_controller = ResearchChallengerController()
    app.protocol_v3_operator_state = None
    app._requested_view = None
    app._log = lambda _message: None
    app.refresh_status = lambda **_kwargs: None

    app.resume_protocol_v3_challenger()
    for _ in range(100):
        if not app.protocol_v3_challenger_controller.is_running:
            break
        import time

        time.sleep(0.01)

    status = app.protocol_v3_challenger_controller.status_snapshot()
    assert status["phase"] == "resume_ready"
    assert status["checkpoint_receipt_sha256"] == receipt.receipt_sha256
    assert status["orders_allowed"] is False
    assert status["canonical_adoption_eligible"] is False
