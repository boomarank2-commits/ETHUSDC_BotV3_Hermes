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
