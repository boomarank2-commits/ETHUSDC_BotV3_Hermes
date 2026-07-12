"""Tests for minimal backtest mode UI state."""

from pathlib import Path

from ethusdc_bot.ui import dashboard_state


def test_data_mode_remains_available(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)

    assert snapshot["ui_status"]["data_prep_button"]["action"] == "data_preparation_only"
    assert snapshot["can_start_data_prep"] is True


def test_backtest_mode_shows_backtest_status_not_data_check_status(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)

    backtest = snapshot["backtest_status"]
    assert backtest["mode"] == "backtest"
    assert backtest["phase"] == "idle"
    assert backtest["stages"] == [
        "data_gate",
        "training_validation",
        "walk_forward",
        "quality_gates",
        "sealed_holdout_separate",
    ]
    assert backtest["enabled"] is False
    assert "download" not in backtest["status_text"].lower()


def test_training_button_is_wired_but_missing_data_keeps_it_locked(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    button = snapshot["ui_status"]["backtest_start_button"]

    assert button["visible"] is True
    assert button["action"] == "pr12_production_starter_supervised_context_protocol_v2"
    assert button["enabled"] is False
    assert button["engine_locked"] is True
    assert button["uses_trading_api"] is False
    assert button["live_paper_testtrade_locked"] is True


def test_data_ready_status_advertises_only_protocol_v2_training_wfv():
    text = dashboard_state._build_bot_status_text(  # noqa: SLF001 - pure UI model unit
        {"data_gate_ready": True}, {"phase": "idle"}
    )

    assert "training/validation/WFV can be started" in text
    assert "Final holdout remains sealed" in text
    assert "strategy search can run" not in text


def test_data_ready_enables_training_wfv_but_never_claims_final_or_shadow():
    status = dashboard_state.build_initial_backtest_status(
        {"data_gate_ready": True}
    )

    assert status["enabled"] is True
    assert status["final_holdout_evaluated"] is False
    assert status["shadow_eligible"] is False
    assert status["live_paper_testtrade"] == "locked"


def test_running_training_disables_second_start_and_keeps_holdout_closed():
    status = dashboard_state.build_initial_backtest_status(
        {"data_gate_ready": True},
        {"phase": "running", "running": True, "freeze_status": "not_evaluated_training_running"},
    )

    assert status["enabled"] is False
    assert status["phase"] == "running"
    assert status["final_holdout_evaluated"] is False
