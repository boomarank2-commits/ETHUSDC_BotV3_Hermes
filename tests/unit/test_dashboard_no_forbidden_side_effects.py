"""Dashboard import and forbidden-side-effect tests."""

from pathlib import Path
import importlib
from types import SimpleNamespace

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
        "Training/WFV research waits for the complete data gate. No fake result."
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


def test_training_button_starts_only_the_injected_training_wfv_controller(monkeypatch, tmp_path):
    module = importlib.import_module("ethusdc_bot.ui.dashboard")
    app = module.DashboardApp.__new__(module.DashboardApp)
    calls = []

    class Controller:
        is_running = False

        def start(self, raw_root, reports_root, status_callback=None):
            calls.append((raw_root, reports_root, status_callback))
            return object(), {"status": {"phase": "running", "running": True}}

    app.active_data_thread = None
    app.training_research_controller = Controller()
    app.repository_root = ROOT
    app.local_root = tmp_path
    app.last_run_status = {}
    app.training_research_status = {"phase": "initial", "running": False}
    app.training_reports_root = tmp_path / "runtime/reports/research_loop"
    app.final_reports_root = tmp_path / "runtime/reports/sealed_holdout_final"
    app.shadow_root = tmp_path / "runtime/shadow"
    app.log_queue = SimpleNamespace(put=lambda value: None)
    app._log = lambda value: None
    app._apply_training_research_status = lambda value: None
    app._set_data_buttons_enabled = lambda value: None
    app._selected_deployment_budget = lambda: 100
    monkeypatch.setattr(
        module,
        "build_dashboard_snapshot",
        lambda *args, **kwargs: {
            "ui_status": {"backtest_start_button": {"enabled": True}},
            "backtest_blocker_summary": "",
        },
    )

    app.start_training_research()

    assert len(calls) == 1
    assert calls[0][0] == tmp_path
    assert calls[0][1] == app.training_reports_root


def test_shadow_adoption_button_requires_confirmation_and_stays_order_free(monkeypatch, tmp_path):
    module = importlib.import_module("ethusdc_bot.ui.dashboard")
    app = module.DashboardApp.__new__(module.DashboardApp)
    report_path = tmp_path / "final.json"
    calls = []
    app.repository_root = ROOT
    app.local_root = tmp_path
    app.last_run_status = {}
    app.training_research_status = {"phase": "completed", "running": False}
    app.final_reports_root = tmp_path
    app.shadow_root = tmp_path / "runtime/shadow"
    app._selected_deployment_budget = lambda: 500
    app._log = lambda value: None
    app.refresh_status = lambda: calls.append("refresh")
    monkeypatch.setattr(
        module,
        "build_dashboard_snapshot",
        lambda *args, **kwargs: {
            "ui_status": {
                "shadow_adopt_button": {
                    "enabled": True,
                    "report_path": str(report_path),
                }
            }
        },
    )
    monkeypatch.setattr(module.messagebox, "askyesno", lambda *args: True)
    monkeypatch.setattr(module.messagebox, "showinfo", lambda *args: None)
    monkeypatch.setattr(
        module,
        "adopt_for_shadow",
        lambda report, budget, root: (
            calls.append((report, budget, root))
            or SimpleNamespace(deployment={"deployment_id": "shadow_test"})
        ),
    )

    app.adopt_verified_final_to_shadow()

    assert calls[0] == (str(report_path), 500, app.shadow_root)
    assert calls[1] == "refresh"


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


def test_backtest_start_button_model_is_training_wfv_only_and_missing_data_blocks():
    snapshot = dashboard_state.build_dashboard_snapshot(ROOT, ROOT.parent / "data")

    button = snapshot["ui_status"]["backtest_start_button"]
    assert button["visible"] is True
    assert button["action"] == "training_validation_wfv_protocol_v2"
    assert button["enabled"] is False
    assert button["engine_locked"] is True
    assert button["uses_trading_api"] is False
    assert button["live_paper_testtrade_locked"] is True
    assert button["final_holdout_evaluated"] is False
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
