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
    assert backtest["stages"] == ["data_gate", "research_protocol_v2", "engine_locked"]
    assert backtest["enabled"] is False
    assert "download" not in backtest["status_text"].lower()


def test_backtest_button_remains_locked_until_protocol_v2_is_wired(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    button = snapshot["ui_status"]["backtest_start_button"]

    assert button["visible"] is True
    assert button["action"] == "research_protocol_v2_not_wired"
    assert button["enabled"] is False
    assert button["engine_locked"] is True
    assert button["uses_trading_api"] is False
    assert button["live_paper_testtrade_locked"] is True


def test_data_ready_status_does_not_advertise_the_disabled_legacy_search():
    text = dashboard_state._build_bot_status_text(  # noqa: SLF001 - pure UI model unit
        {"data_gate_ready": True}, {"phase": "idle"}
    )

    assert "dashboard engine remains locked" in text
    assert "strategy search can run" not in text
