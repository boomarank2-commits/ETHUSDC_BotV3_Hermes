"""UI data preparation controller.

This controller coordinates the data-preparation phase that the UI can run before
any real backtest engine exists. It checks readiness, plans supported public data
updates, optionally executes those public downloads, then rebuilds readiness. It
never starts a backtest engine, creates result reports, places orders, or unlocks
live/paper/testtrade.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import threading
from typing import Any

from ethusdc_bot.data_pipeline.data_readiness import build_backtest_start_data_gate
from ethusdc_bot.data_pipeline import public_data_downloader

LogCallback = Callable[[str], None]
SUPPORTED_PUBLIC_DATA_TYPES = {"klines_1m", "klines", "aggTrades", "trades"}
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


def build_data_update_plan(local_root: str | Path) -> dict[str, Any]:
    """Build a UI-facing data update plan from the current readiness report."""

    readiness_before = build_backtest_start_data_gate(local_root)
    all_tasks = list(readiness_before.get("missing_download_tasks", [])) + list(
        readiness_before.get("outdated_download_tasks", [])
    )
    supported_public_tasks = []
    unsupported_tasks = []
    live_collector_tasks = []
    for task in all_tasks:
        if not isinstance(task, Mapping):
            continue
        if task.get("source_kind") == "live_collection":
            live_collector_tasks.append(dict(task))
        elif _is_supported_public_task(task):
            supported_public_tasks.append(_with_safety_metadata(task))
        else:
            unsupported_tasks.append(dict(task))

    plan = {
        "schema_version": 1,
        "local_root": str(Path(local_root)),
        "readiness_before": readiness_before,
        "supported_public_tasks": supported_public_tasks,
        "unsupported_tasks": unsupported_tasks,
        "live_collector_tasks": live_collector_tasks,
        "supported_download_task_count": len(supported_public_tasks),
        "unsupported_task_count": len(unsupported_tasks),
        "live_collector_task_count": len(live_collector_tasks),
        "engine_start_locked": True,
        "backtest_started": False,
        "status": "planned",
        "summary": "",
    }
    plan["summary"] = summarize_data_update_plan(plan)
    return _assert_no_forbidden_fields(plan)


def summarize_data_update_plan(plan: Mapping[str, Any]) -> str:
    """Return a concise human-readable summary for UI logs/status."""

    readiness = plan.get("readiness_before", {})
    return (
        "Data update plan: "
        f"readiness={readiness.get('overall_status', 'unknown')}; "
        f"supported_public={plan.get('supported_download_task_count', 0)}; "
        f"unsupported={plan.get('unsupported_task_count', 0)}; "
        f"live_collectors={plan.get('live_collector_task_count', 0)}; "
        "engine_start_locked=true; backtest_started=false"
    )


def run_data_update_plan(
    local_root: str | Path,
    execute: bool = False,
    log_callback: LogCallback | None = None,
) -> dict[str, Any]:
    """Run the data-preparation workflow.

    Dry-run (`execute=False`) only logs/plans and deliberately does not call the
    public downloader. Execute mode calls the public downloader only for supported
    public tasks. Unsupported and live-collector tasks are reported only.
    """

    _log(log_callback, "Readiness wird geprüft.")
    plan = build_data_update_plan(local_root)
    _log(log_callback, plan["summary"])
    _log(log_callback, f"Unterstützte Download-Tasks: {plan['supported_download_task_count']}")
    _log(log_callback, f"Nicht unterstützte Tasks: {plan['unsupported_task_count']}")
    _log(log_callback, f"Live-Collector-Tasks: {plan['live_collector_task_count']}")

    download_results = []
    if execute:
        for task in plan["supported_public_tasks"]:
            _log(log_callback, f"Starte öffentlichen Download: {task['task_id']} ({task['symbol']} {task['data_type']})")
            result = public_data_downloader.execute_public_download_task(task, execute=True)
            download_results.append(result)
            _log(log_callback, f"Download-Task abgeschlossen: {task['task_id']}")
    else:
        for task in plan["supported_public_tasks"]:
            _log(log_callback, f"Dry-run: würde planen/laden: {task['task_id']} ({task['symbol']} {task['data_type']})")

    for task in plan["unsupported_tasks"]:
        _log(log_callback, f"Nicht unterstützt: {task['task_id']} ({task.get('data_type')})")
    for task in plan["live_collector_tasks"]:
        _log(log_callback, f"Live-Collector noch nicht implementiert: {task['task_id']}")

    _log(log_callback, "Audit/Readiness wird erneut aufgebaut.")
    readiness_after = build_backtest_start_data_gate(local_root)
    _log(log_callback, f"Neuer Readiness-Status: {readiness_after['overall_status']}")
    _log(log_callback, "Data preparation finished. Backtest engine not implemented yet.")
    result = {
        "schema_version": 1,
        "execute": execute,
        "plan": plan,
        "download_results": download_results,
        "readiness_after": readiness_after,
        "engine_start_locked": True,
        "backtest_started": False,
        "result_report_created": False,
        "status": "finished",
        "message": "Data preparation finished. Backtest engine not implemented yet.",
    }
    return _assert_no_forbidden_fields(result)


def run_data_update_plan_async(
    local_root: str | Path,
    execute: bool = False,
    log_callback: LogCallback | None = None,
) -> tuple[threading.Thread, dict[str, Any]]:
    """Run data preparation on a daemon thread and return thread/result holder."""

    result_container: dict[str, Any] = {"result": None, "error": None}

    def _target() -> None:
        try:
            result_container["result"] = run_data_update_plan(local_root, execute=execute, log_callback=log_callback)
        except Exception as exc:  # pragma: no cover - defensive thread bridge
            result_container["error"] = exc
            _log(log_callback, f"Data preparation failed: {exc}")

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    return thread, result_container


def _is_supported_public_task(task: Mapping[str, Any]) -> bool:
    return (
        task.get("source_kind") == "public_binance_data"
        and bool(task.get("execute_allowed"))
        and str(task.get("data_type")) in SUPPORTED_PUBLIC_DATA_TYPES
    )


def _with_safety_metadata(task: Mapping[str, Any]) -> dict[str, Any]:
    enriched = dict(task)
    symbol = str(enriched.get("symbol"))
    data_type = str(enriched.get("data_type"))
    enriched["context_only"] = symbol in {"BTCUSDC", "ETHBTC"}
    enriched["may_trigger_orders"] = symbol == "ETHUSDC" and data_type == "klines_1m"
    enriched["trade_market"] = symbol == "ETHUSDC" and data_type == "klines_1m"
    return enriched


def _log(callback: LogCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _assert_no_forbidden_fields(result: dict[str, Any]) -> dict[str, Any]:
    if FORBIDDEN_RESULT_FIELDS & set(result):
        raise ValueError("data update result contains forbidden result fields")
    return result
