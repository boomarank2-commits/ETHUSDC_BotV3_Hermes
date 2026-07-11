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

    "data",
    "raw",
    "market_data",
]
FORBIDDEN_SECRET_PATHS = [".env", "api_key.txt", "binance_key.txt", "secrets.json"]
FORBIDDEN_REPORT_DIRS = ["reports/backtests", "reports/summary"]


def test_dashboard_module_is_importable():
    module = importlib.import_module("ethusdc_bot.ui.dashboard")

    assert module.BACKTEST_DISABLED_HINT == (
        "Backtest waits for data readiness and real engine implementation. No fake result."
    )


def test_primary_data_button_starts_execute_mode():
    module = importlib.import_module("ethusdc_bot.ui.dashboard")
    app = module.DashboardApp.__new__(module.DashboardApp)
    calls = []
    app._start_data_preparation = lambda execute: calls.append(execute)

    app.start_data_check_and_load()

    assert calls == [True]


def test_secondary_check_button_starts_dry_run_mode():
    module = importlib.import_module("ethusdc_bot.ui.dashboard")
    app = module.DashboardApp.__new__(module.DashboardApp)
    calls = []
    app._start_data_preparation = lambda execute: calls.append(execute)

    app.start_check_without_download()

    assert calls == [False]


def test_operator_runtime_text_shows_running_file_progress():
    module = importlib.import_module("ethusdc_bot.ui.dashboard")

    text = module.build_operator_runtime_text(
        {
            "phase": "downloading",
            "mode": "execute",
            "progress_pct": 35,
            "current_task_id": "download_btcusdc_klines_1m",
            "current_symbol": "BTCUSDC",
            "current_data_type": "klines_1m",
            "current_file_name": "BTCUSDC-1m-2024-01-01.zip",
            "current_file_index": 3,
            "planned_file_count": 2190,
            "completed_file_count": 2,
            "downloaded_file_count": 1,
            "skipped_file_count": 1,
            "failed_file_count": 0,
            "elapsed_seconds": 12,
            "last_message": "Downloading file",
        },
        seconds_since_file_event=12,
    )

    assert "Lädt Daten" in text["bot_status"]
    assert "BTCUSDC" in text["current_download"]
    assert "BTCUSDC-1m-2024-01-01.zip" in text["current_download"]
    assert "2/2190" in text["files"]
    assert "läuft noch, warte auf nächsten Datei-Fortschritt" in text["activity_note"]


def test_operator_runtime_text_shows_slow_network_after_sixty_seconds():
    module = importlib.import_module("ethusdc_bot.ui.dashboard")

    text = module.build_operator_runtime_text(
        {"phase": "downloading", "mode": "execute", "elapsed_seconds": 61},
        seconds_since_file_event=61,
    )

    assert "möglicherweise großer Download oder Netzwerk langsam" in text["activity_note"]


def test_operator_runtime_text_shows_failed_error():
    module = importlib.import_module("ethusdc_bot.ui.dashboard")

    text = module.build_operator_runtime_text({"phase": "failed", "error": "boom"})

    assert text["bot_status"] == "Fehler"
    assert text["activity_note"] == "Fehler: boom"


def test_backtest_start_button_model_runs_data_preparation_only():
    snapshot = dashboard_state.build_dashboard_snapshot(ROOT, ROOT.parent / "data")

    button = snapshot["ui_status"]["backtest_start_button"]
    assert button["visible"] is True
    assert button["action"] == "research_protocol_v2_not_wired"
    assert button["enabled"] is False
    assert button["engine_locked"] is True
    assert button["uses_trading_api"] is False
    assert button["live_paper_testtrade_locked"] is True
    assert snapshot["data_prep_status"]["engine_start_locked"] is True


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
