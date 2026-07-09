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
    assert backtest["stages"] == ["data_gate", "load_data", "training", "strategy_search", "blindtest", "result"]
    assert "download" not in backtest["status_text"].lower()


def test_backtest_button_starts_local_workflow_only(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    button = snapshot["ui_status"]["backtest_start_button"]

    assert button["visible"] is True
    assert button["action"] == "local_backtest_strategy_search"
    assert button["uses_trading_api"] is False
    assert button["live_paper_testtrade_locked"] is True
