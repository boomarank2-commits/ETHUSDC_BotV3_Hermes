"""UI data update controller tests.

The controller may prepare local public-data downloads, but it must not start a
backtest engine, create reports, create repo-local raw data, or unlock trading.
"""

from __future__ import annotations

from pathlib import Path

from ethusdc_bot.ui import data_update_controller as controller


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_RESULT_FIELDS = {
    "profit_usdc",
    "net_usdc_per_day",
    "winrate",
    "profit_factor",
    "trade_count",
    "trades",
    "real_trades",
    "backtest_run_id",
    "candidate_adoptable",
    "adopted_candidate",
    "best_candidate",
    "candidate",
}
FORBIDDEN_REPOSITORY_PATHS = [
    "src/ethusdc_bot/data_pipeline/binance_client.py",
    "src/ethusdc_bot/exchange",
    "src/ethusdc_bot/engine",
    "src/ethusdc_bot/strategy",
    "src/ethusdc_bot/backtest",
    "src/ethusdc_bot/live",
    "src/ethusdc_bot/paper",
    "data",
    "raw",
    "market_data",
]


def test_build_data_update_plan_contains_supported_public_tasks(tmp_path):
    plan = controller.build_data_update_plan(tmp_path)
    task_ids = {task["task_id"] for task in plan["supported_public_tasks"]}

    assert "download_ethusdc_klines_1m" in task_ids
    assert "download_btcusdc_klines_1m" in task_ids
    assert "download_ethbtc_klines_1m" in task_ids
    assert "download_ethusdc_aggtrades" in task_ids
    assert "download_ethusdc_trades" in task_ids
    for task in plan["supported_public_tasks"]:
        assert task["source_kind"] == "public_binance_data"
        assert task["execute_allowed"] is True


def test_initial_last_run_status_is_never_run():
    status = controller.build_initial_data_prep_last_run_status()

    assert status["last_run_status"] == "never_run"
    assert status["last_run_mode"] == "dry_run"
    assert status["last_run_backtest_engine_locked"] is True
    assert status["last_run_summary_text"] == "Noch kein Datenvorbereitungs-Lauf in dieser UI-Sitzung."


def test_initial_data_prep_status_is_idle_with_zero_progress():
    status = controller.build_initial_data_prep_status()

    assert status["phase"] == "idle"
    assert status["mode"] == "dry_run"
    assert status["progress_pct"] == 0
    assert status["current_step"] == "Idle"
    assert status["backtest_started"] is False
    assert status["backtest_allowed"] is False
    assert status["engine_start_locked"] is True


def test_run_data_update_plan_dry_run_emits_structured_status_sequence(monkeypatch, tmp_path):
    def fail_if_called(task, execute=False):
        raise AssertionError("public downloader must not be called in dry-run")

    monkeypatch.setattr(controller.public_data_downloader, "execute_public_download_task", fail_if_called)
    updates = []

    result = controller.run_data_update_plan(tmp_path, execute=False, progress_callback=updates.append)

    phases = [status["phase"] for status in updates]
    assert phases[0] == "checking_readiness"
    assert "planning" in phases
    assert "dry_run" in phases
    assert "refreshing_readiness" in phases
    assert phases[-1] == "finished"
    assert result["runtime_status"]["phase"] == "finished"
    assert result["runtime_status"]["progress_pct"] == 100


def test_run_data_update_plan_execute_emits_downloading_status_for_supported_tasks(monkeypatch, tmp_path):
    calls = []
    updates = []

    def fake_execute(task, execute=False):
        calls.append(task["task_id"])
        return {"task_id": task["task_id"], "file_results": [], "checksum_results": []}

    monkeypatch.setattr(controller.public_data_downloader, "execute_public_download_task", fake_execute)

    controller.run_data_update_plan(tmp_path, execute=True, progress_callback=updates.append)

    download_updates = [status for status in updates if status["phase"] == "downloading"]
    assert download_updates
    assert {status["current_task_id"] for status in download_updates} == set(calls)
    assert all(status["mode"] == "execute" for status in download_updates)
    assert all(status["total_tasks"] >= len(calls) for status in download_updates)


def test_data_prep_progress_stays_between_zero_and_one_hundred(monkeypatch, tmp_path):
    updates = []

    def fake_execute(task, execute=False):
        return {"task_id": task["task_id"], "file_results": [], "checksum_results": []}

    monkeypatch.setattr(controller.public_data_downloader, "execute_public_download_task", fake_execute)

    controller.run_data_update_plan(tmp_path, execute=True, progress_callback=updates.append)

    assert updates
    assert all(0 <= status["progress_pct"] <= 100 for status in updates)
    assert updates[-1]["phase"] == "finished"
    assert updates[-1]["progress_pct"] == 100


def test_failed_data_prep_status_contains_error(monkeypatch, tmp_path):
    updates = []

    def fail_readiness(local_root):
        raise RuntimeError("readiness exploded")

    monkeypatch.setattr(controller, "build_backtest_start_data_gate", fail_readiness)
    try:
        controller.run_data_update_plan(tmp_path, execute=False, progress_callback=updates.append)
    except RuntimeError:
        pass
    else:  # pragma: no cover - explicit failure branch
        raise AssertionError("expected readiness failure")

    assert updates[-1]["phase"] == "failed"
    assert updates[-1]["error"] == "readiness exploded"
    assert updates[-1]["backtest_started"] is False
    assert updates[-1]["engine_start_locked"] is True


def test_build_running_last_run_status_from_runtime_update():
    runtime = controller.build_initial_data_prep_status(mode="execute")
    runtime.update(
        {
            "phase": "downloading",
            "started_at": "2026-07-08T10:00:00+00:00",
            "current_task_id": "download_btcusdc_klines_1m",
            "current_symbol": "BTCUSDC",
            "current_data_type": "klines_1m",
            "total_tasks": 5,
            "completed_tasks": 1,
            "skipped_tasks": 0,
            "failed_tasks": 0,
            "supported_download_task_count": 5,
            "last_message": "Downloading supported public task: download_btcusdc_klines_1m",
        }
    )

    last_run = controller.build_running_data_prep_last_run_status(runtime)

    assert last_run["last_run_status"] == "running"
    assert last_run["last_run_mode"] == "execute"
    assert last_run["last_run_started_at"] == "2026-07-08T10:00:00+00:00"
    assert last_run["last_run_supported_tasks"] == 5
    assert last_run["last_run_completed_tasks"] == 1
    assert "Datenlauf läuft gerade" in last_run["last_run_summary_text"]
    assert "task-basiert" in last_run["last_run_summary_text"]


def test_build_finished_last_run_status_after_dry_run(tmp_path):
    result = controller.run_data_update_plan(tmp_path, execute=False)

    last_run = controller.build_finished_data_prep_last_run_status(result)

    assert last_run["last_run_status"] == "finished"
    assert last_run["last_run_mode"] == "dry_run"
    assert last_run["last_run_supported_tasks"] >= 5
    assert last_run["last_run_completed_tasks"] == last_run["last_run_supported_tasks"]
    assert last_run["last_run_skipped_tasks"] == last_run["last_run_supported_tasks"]
    assert last_run["last_run_download_results_count"] == 0
    assert last_run["last_run_readiness_before"] == "blocked"
    assert last_run["last_run_readiness_after"] == "blocked"
    assert last_run["last_run_backtest_engine_locked"] is True
    assert "Letzter Datenlauf fertig" in last_run["last_run_summary_text"]
    assert last_run["last_run_next_blocker"]


def test_build_finished_last_run_status_after_execute_shows_readiness_after(monkeypatch, tmp_path):
    def fake_execute(task, execute=False):
        return {"task_id": task["task_id"], "planned_files": 2, "file_results": [], "checksum_results": []}

    monkeypatch.setattr(controller.public_data_downloader, "execute_public_download_task", fake_execute)

    result = controller.run_data_update_plan(tmp_path, execute=True)
    last_run = controller.build_finished_data_prep_last_run_status(result)

    assert last_run["last_run_status"] == "finished"
    assert last_run["last_run_mode"] == "execute"
    assert last_run["last_run_download_results_count"] == len(result["download_results"])
    assert last_run["last_run_readiness_after"] == result["readiness_after"]["overall_status"]
    assert last_run["last_run_backtest_engine_locked"] is True


def test_build_failed_last_run_status_exposes_error():
    runtime = controller.build_initial_data_prep_status(mode="dry_run")
    runtime.update({"started_at": "2026-07-08T10:00:00+00:00", "finished_at": "2026-07-08T10:00:05+00:00"})

    last_run = controller.build_failed_data_prep_last_run_status(runtime, RuntimeError("boom"))

    assert last_run["last_run_status"] == "failed"
    assert last_run["last_run_mode"] == "dry_run"
    assert last_run["last_run_backtest_engine_locked"] is True
    assert last_run["error"] == "boom"
    assert "Datenlauf fehlgeschlagen: boom" == last_run["last_run_summary_text"]


def test_build_data_update_plan_separates_unsupported_exchange_info_and_live_collectors(tmp_path):
    plan = controller.build_data_update_plan(tmp_path)
    unsupported_ids = {task["task_id"] for task in plan["unsupported_tasks"]}
    live_ids = {task["task_id"] for task in plan["live_collector_tasks"]}

    assert "download_exchange_info" in unsupported_ids
    assert "collect_ethusdc_bookticker_live" in live_ids
    assert "collect_ethusdc_orderbook_snapshots_live" in live_ids


def test_run_data_update_plan_dry_run_downloads_nothing(monkeypatch, tmp_path):
    def fail_if_called(task, execute=False):
        raise AssertionError("public downloader must not be called in dry-run")

    monkeypatch.setattr(controller.public_data_downloader, "execute_public_download_task", fail_if_called)
    result = controller.run_data_update_plan(tmp_path, execute=False)

    assert result["execute"] is False
    assert result["download_results"] == []
    assert list(tmp_path.rglob("*.zip")) == []


def test_run_data_update_plan_execute_calls_public_downloader_only_for_supported_tasks(monkeypatch, tmp_path):
    calls = []

    def fake_execute(task, execute=False):
        calls.append((task["task_id"], task["source_kind"], execute))
        return {
            "task_id": task["task_id"],
            "symbol": task["symbol"],
            "data_type": task["data_type"],
            "context_only": task.get("symbol") in {"BTCUSDC", "ETHBTC"},
            "may_trigger_orders": task.get("symbol") == "ETHUSDC" and task.get("data_type") == "klines_1m",
            "file_results": [],
            "checksum_results": [],
        }

    monkeypatch.setattr(controller.public_data_downloader, "execute_public_download_task", fake_execute)
    result = controller.run_data_update_plan(tmp_path, execute=True)

    called_ids = {call[0] for call in calls}
    assert "download_ethusdc_klines_1m" in called_ids
    assert "download_btcusdc_klines_1m" in called_ids
    assert "download_ethbtc_klines_1m" in called_ids
    assert "download_ethusdc_aggtrades" in called_ids
    assert "download_ethusdc_trades" in called_ids
    assert "download_exchange_info" not in called_ids
    assert "collect_ethusdc_bookticker_live" not in called_ids
    assert all(call[2] is True for call in calls)
    assert result["engine_start_locked"] is True
    assert result["backtest_started"] is False


def test_controller_preserves_context_only_order_safety(monkeypatch, tmp_path):
    seen = {}

    def fake_execute(task, execute=False):
        if task["symbol"] in {"BTCUSDC", "ETHBTC"}:
            seen[task["symbol"]] = task
        return {"task_id": task["task_id"], "file_results": [], "checksum_results": []}

    monkeypatch.setattr(controller.public_data_downloader, "execute_public_download_task", fake_execute)
    controller.run_data_update_plan(tmp_path, execute=True)

    assert seen["BTCUSDC"]["context_only"] is True
    assert seen["BTCUSDC"]["may_trigger_orders"] is False
    assert seen["ETHBTC"]["context_only"] is True
    assert seen["ETHBTC"]["may_trigger_orders"] is False


def test_run_data_update_plan_has_no_forbidden_result_fields_and_no_reports(tmp_path):
    before = {
        report_dir: sorted(path.name for path in (ROOT / report_dir).glob("*"))
        for report_dir in ["reports/backtests", "reports/summary"]
    }

    result = controller.run_data_update_plan(tmp_path, execute=False)

    after = {
        report_dir: sorted(path.name for path in (ROOT / report_dir).glob("*"))
        for report_dir in ["reports/backtests", "reports/summary"]
    }
    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(result)
    assert after == before


def test_data_prep_does_not_create_forbidden_repository_paths(tmp_path):
    controller.run_data_update_plan(tmp_path, execute=False)

    assert [path for path in FORBIDDEN_REPOSITORY_PATHS if (ROOT / path).exists()] == []


def test_run_data_update_plan_async_returns_thread_and_result_container(tmp_path):
    thread, result_container = controller.run_data_update_plan_async(tmp_path, execute=False)
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert result_container["result"]["execute"] is False
    assert result_container["result"]["backtest_started"] is False
