"""UI data preparation controller.

This controller coordinates the data-preparation phase that the UI can run before
any real backtest engine exists. It checks readiness, plans supported public data
updates, optionally executes those public downloads, then rebuilds readiness. It
never starts a backtest engine, creates result reports, places orders, or unlocks
live/paper/testtrade.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
import threading
from typing import Any

from ethusdc_bot.data_pipeline.data_readiness import build_backtest_start_data_gate
from ethusdc_bot.data_pipeline import public_data_downloader

LogCallback = Callable[[str], None]
ProgressCallback = Callable[[dict[str, Any]], None]
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


def build_initial_data_prep_status(mode: str = "dry_run") -> dict[str, Any]:
    """Return the safe initial structured data-preparation runtime status."""

    return {
        "phase": "idle",
        "mode": mode,
        "progress_pct": 0,
        "current_step": "Idle",
        "current_task_id": None,
        "current_symbol": None,
        "current_data_type": None,
        "total_tasks": 0,
        "completed_tasks": 0,
        "skipped_tasks": 0,
        "failed_tasks": 0,
        "supported_download_task_count": 0,
        "unsupported_task_count": 0,
        "live_collector_task_count": 0,
        "engine_start_locked": True,
        "backtest_started": False,
        "backtest_allowed": False,
        "last_message": "Idle. No data preparation is running.",
        "started_at": None,
        "finished_at": None,
        "error": None,
    }


def update_progress_status(
    status: Mapping[str, Any],
    progress_callback: ProgressCallback | None = None,
    **updates: Any,
) -> dict[str, Any]:
    """Merge and publish one structured progress status update."""

    updated = dict(status)
    updated.update(updates)
    updated["progress_pct"] = max(0, min(100, int(updated.get("progress_pct", 0))))
    updated["engine_start_locked"] = True
    updated["backtest_started"] = False
    updated["backtest_allowed"] = False
    if updated.get("phase") in {"finished", "failed"} and updated.get("finished_at") is None:
        updated["finished_at"] = _utc_now()
    if progress_callback is not None:
        progress_callback(dict(updated))
    return updated


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
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Run the data-preparation workflow with structured progress updates.

    Dry-run (`execute=False`) only logs/plans and deliberately does not call the
    public downloader. Execute mode calls the public downloader only for supported
    public tasks. Unsupported and live-collector tasks are reported only.
    """

    mode = "execute" if execute else "dry_run"
    status = build_initial_data_prep_status(mode=mode)
    status = update_progress_status(
        status,
        progress_callback,
        phase="checking_readiness",
        progress_pct=5,
        current_step="Checking data readiness",
        started_at=_utc_now(),
        last_message="Readiness wird geprüft.",
    )
    try:
        _log(log_callback, "Readiness wird geprüft.")
        status = update_progress_status(
            status,
            progress_callback,
            phase="planning",
            progress_pct=10,
            current_step="Building data update plan",
            last_message="Download-Plan wird gebaut.",
        )
        plan = build_data_update_plan(local_root)
        total_tasks = len(plan["supported_public_tasks"])
        status = update_progress_status(
            status,
            progress_callback,
            phase="planning",
            progress_pct=15,
            current_step="Data update plan built",
            total_tasks=total_tasks,
            supported_download_task_count=plan["supported_download_task_count"],
            unsupported_task_count=plan["unsupported_task_count"],
            live_collector_task_count=plan["live_collector_task_count"],
            last_message=plan["summary"],
        )
        _log(log_callback, plan["summary"])
        _log(log_callback, f"Unterstützte Download-Tasks: {plan['supported_download_task_count']}")
        _log(log_callback, f"Nicht unterstützte Tasks: {plan['unsupported_task_count']}")
        _log(log_callback, f"Live-Collector-Tasks: {plan['live_collector_task_count']}")

        download_results = []
        completed_tasks = 0
        if execute:
            for task in plan["supported_public_tasks"]:
                status = _task_status(
                    status,
                    progress_callback,
                    task=task,
                    phase="downloading",
                    mode=mode,
                    current_step="Downloading supported public task",
                    completed_tasks=completed_tasks,
                    total_tasks=total_tasks,
                )
                _log(log_callback, f"Starte öffentlichen Download: {task['task_id']} ({task['symbol']} {task['data_type']})")
                result = public_data_downloader.execute_public_download_task(task, execute=True)
                download_results.append(result)
                completed_tasks += 1
                status = update_progress_status(
                    status,
                    progress_callback,
                    progress_pct=_task_progress(completed_tasks, total_tasks),
                    completed_tasks=completed_tasks,
                    last_message=f"Download-Task abgeschlossen: {task['task_id']}",
                )
                _log(log_callback, f"Download-Task abgeschlossen: {task['task_id']}")
        else:
            for task in plan["supported_public_tasks"]:
                status = _task_status(
                    status,
                    progress_callback,
                    task=task,
                    phase="dry_run",
                    mode=mode,
                    current_step="Dry-run supported public task",
                    completed_tasks=completed_tasks,
                    total_tasks=total_tasks,
                )
                completed_tasks += 1
                status = update_progress_status(
                    status,
                    progress_callback,
                    progress_pct=_task_progress(completed_tasks, total_tasks),
                    completed_tasks=completed_tasks,
                    skipped_tasks=completed_tasks,
                    last_message=f"Dry-run geplant: {task['task_id']}",
                )
                _log(log_callback, f"Dry-run: würde planen/laden: {task['task_id']} ({task['symbol']} {task['data_type']})")

        for task in plan["unsupported_tasks"]:
            _log(log_callback, f"Nicht unterstützt: {task['task_id']} ({task.get('data_type')})")
        for task in plan["live_collector_tasks"]:
            _log(log_callback, f"Live-Collector noch nicht implementiert: {task['task_id']}")

        status = update_progress_status(
            status,
            progress_callback,
            phase="refreshing_readiness",
            progress_pct=90,
            current_step="Audit/Readiness neu prüfen",
            current_task_id=None,
            current_symbol=None,
            current_data_type=None,
            last_message="Audit/Readiness wird erneut aufgebaut.",
        )
        _log(log_callback, "Audit/Readiness wird erneut aufgebaut.")
        readiness_after = build_backtest_start_data_gate(local_root)
        _log(log_callback, f"Neuer Readiness-Status: {readiness_after['overall_status']}")
        _log(log_callback, "Data preparation finished. Backtest engine not implemented yet.")
        status = update_progress_status(
            status,
            progress_callback,
            phase="finished",
            progress_pct=100,
            current_step="Finished",
            last_message="Data preparation finished. Backtest engine not implemented yet.",
        )
        result = {
            "schema_version": 1,
            "execute": execute,
            "plan": plan,
            "download_results": download_results,
            "readiness_after": readiness_after,
            "runtime_status": status,
            "engine_start_locked": True,
            "backtest_started": False,
            "result_report_created": False,
            "status": "finished",
            "message": "Data preparation finished. Backtest engine not implemented yet.",
        }
        return _assert_no_forbidden_fields(result)
    except Exception as exc:
        update_progress_status(
            status,
            progress_callback,
            phase="failed",
            current_step="Failed",
            last_message=f"Data preparation failed: {exc}",
            error=str(exc),
        )
        raise


def run_data_update_plan_async(
    local_root: str | Path,
    execute: bool = False,
    log_callback: LogCallback | None = None,
    progress_callback: ProgressCallback | None = None,
) -> tuple[threading.Thread, dict[str, Any]]:
    """Run data preparation on a daemon thread and return thread/result holder."""

    result_container: dict[str, Any] = {"result": None, "error": None}

    def _target() -> None:
        try:
            result_container["result"] = run_data_update_plan(
                local_root,
                execute=execute,
                log_callback=log_callback,
                progress_callback=progress_callback,
            )
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


def _task_status(
    status: Mapping[str, Any],
    progress_callback: ProgressCallback | None,
    *,
    task: Mapping[str, Any],
    phase: str,
    mode: str,
    current_step: str,
    completed_tasks: int,
    total_tasks: int,
) -> dict[str, Any]:
    return update_progress_status(
        status,
        progress_callback,
        phase=phase,
        mode=mode,
        progress_pct=_task_progress(completed_tasks, total_tasks),
        current_step=current_step,
        current_task_id=task.get("task_id"),
        current_symbol=task.get("symbol"),
        current_data_type=task.get("data_type"),
        completed_tasks=completed_tasks,
        total_tasks=total_tasks,
        last_message=f"{current_step}: {task.get('task_id')}",
    )


def _task_progress(completed_tasks: int, total_tasks: int) -> int:
    if total_tasks <= 0:
        return 80
    return 20 + round((completed_tasks / total_tasks) * 60)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _log(callback: LogCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _assert_no_forbidden_fields(result: dict[str, Any]) -> dict[str, Any]:
    if FORBIDDEN_RESULT_FIELDS & set(result):
        raise ValueError("data update result contains forbidden result fields")
    return result
