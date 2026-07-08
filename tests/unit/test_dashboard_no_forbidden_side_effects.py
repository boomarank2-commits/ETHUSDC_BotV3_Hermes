"""Dashboard import and forbidden-side-effect tests."""

from pathlib import Path
import importlib

from ethusdc_bot.ui import dashboard_state


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_REPOSITORY_PATHS = [
    "src/ethusdc_bot/data_pipeline/binance_client.py",
    "src/ethusdc_bot/exchange",
    "src/ethusdc_bot/engine",
    "src/ethusdc_bot/strategy",
    "src/ethusdc_bot/backtest",
    "data",
    "raw",
    "market_data",
]
FORBIDDEN_SECRET_PATHS = [".env", "api_key.txt", "binance_key.txt", "secrets.json"]
FORBIDDEN_REPORT_DIRS = ["reports/backtests", "reports/summary"]


def test_dashboard_module_is_importable():
    module = importlib.import_module("ethusdc_bot.ui.dashboard")

    assert module.BACKTEST_DISABLED_HINT == (
        "Backtest engine not implemented yet. Next step after data audit."
    )


def test_backtest_button_model_is_disabled():
    snapshot = dashboard_state.build_dashboard_snapshot(ROOT, ROOT.parent / "data")

    assert snapshot["ui_status"]["backtest_button"] == {
        "visible": True,
        "enabled": False,
        "hint": "Backtest engine not implemented yet. Next step after data audit.",
    }


def test_dashboard_state_does_not_create_repository_data_raw_or_market_data(tmp_path):
    dashboard_state.build_dashboard_snapshot(ROOT, tmp_path)

    assert [path for path in FORBIDDEN_REPOSITORY_PATHS if (ROOT / path).exists()] == []


def test_dashboard_state_does_not_create_reports(tmp_path):
    before = {
        report_dir: sorted(path.name for path in (ROOT / report_dir).glob("*"))
        for report_dir in FORBIDDEN_REPORT_DIRS
    }

    dashboard_state.build_dashboard_snapshot(ROOT, tmp_path)

    after = {
        report_dir: sorted(path.name for path in (ROOT / report_dir).glob("*"))
        for report_dir in FORBIDDEN_REPORT_DIRS
    }
    assert after == before


def test_dashboard_state_does_not_create_api_key_or_env_files(tmp_path):
    dashboard_state.build_dashboard_snapshot(ROOT, tmp_path)

    assert [path for path in FORBIDDEN_SECRET_PATHS if (ROOT / path).exists()] == []
