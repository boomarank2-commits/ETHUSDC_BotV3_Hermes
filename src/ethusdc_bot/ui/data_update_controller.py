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
import inspect
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


def build_initial_data_prep_last_run_status() -> dict[str, Any]:
    """Return the per-UI-session last-run status before any data prep was run."""

    return {
        "last_run_status": "never_run",
        "last_run_mode": "dry_run",
        "last_run_started_at": None,
        "last_run_finished_at": None,
        "last_run_duration_seconds": None,
        "last_run_supported_tasks": 0,
        "last_run_completed_tasks": 0,
        "last_run_skipped_tasks": 0,
        "last_run_failed_tasks": 0,
        "last_run_planned_file_count": 0,
        "last_run_completed_file_count": 0,
        "last_run_skipped_file_count": 0,
        "last_run_downloaded_file_count": 0,
        "last_run_failed_file_count": 0,
        "last_run_download_results_count": 0,
        "last_run_readiness_before": None,
        "last_run_readiness_after": None,
        "last_run_backtest_engine_locked": True,
        "last_run_summary_text": "Noch kein Datenvorbereitungs-Lauf in dieser UI-Sitzung.",
        "last_run_next_blocker": "Noch kein Datenlauf gestartet.",
        "error": None,
    }


def build_running_data_prep_last_run_status(runtime_status: Mapping[str, Any]) -> dict[str, Any]:
    """Build a persistent session last-run model from an in-flight runtime update."""

    task_id = runtime_status.get("current_task_id") or "unknown"
    symbol = runtime_status.get("current_symbol") or "unknown"
    data_type = runtime_status.get("current_data_type") or "unknown"
    summary = (
        "Datenlauf läuft gerade. "
        f"Aktueller Task: {task_id} ({symbol} {data_type}). "
        "Dieser Task kann lange dauern, Fortschritt ist task-basiert, nicht byte-basiert."
    )
    status = build_initial_data_prep_last_run_status()
    status.update(
        {
            "last_run_status": "running",
            "last_run_mode": runtime_status.get("mode", "dry_run"),
            "last_run_started_at": runtime_status.get("started_at"),
            "last_run_finished_at": None,
            "last_run_duration_seconds": None,
            "last_run_supported_tasks": runtime_status.get("supported_download_task_count", runtime_status.get("total_tasks", 0)),
            "last_run_completed_tasks": runtime_status.get("completed_tasks", 0),
            "last_run_skipped_tasks": runtime_status.get("skipped_tasks", 0),
            "last_run_failed_tasks": runtime_status.get("failed_tasks", 0),
            "last_run_summary_text": summary,
            "last_run_next_blocker": str(runtime_status.get("last_message") or summary),
        }
    )
    return status


def build_finished_data_prep_last_run_status(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build the durable visible last-run status from a completed controller result."""

    runtime = result.get("runtime_status", {}) if isinstance(result.get("runtime_status"), Mapping) else {}
    plan = result.get("plan", {}) if isinstance(result.get("plan"), Mapping) else {}
    readiness_before = plan.get("readiness_before", {}) if isinstance(plan.get("readiness_before"), Mapping) else {}
    readiness_after = result.get("readiness_after", {}) if isinstance(result.get("readiness_after"), Mapping) else {}
    download_results = list(result.get("download_results", [])) if isinstance(result.get("download_results", []), list) else []
    before_status = readiness_before.get("overall_status")
    after_status = readiness_after.get("overall_status")
    next_blocker = _next_blocker(readiness_after)
    if after_status == "ready":
        summary = "Letzter Datenlauf fertig. Data gate ready, aber Engine fehlt."
    elif not result.get("execute"):
        summary = f"Dry-run finished. No downloads executed. Readiness bleibt blocked wegen: {next_blocker}"
    else:
        summary = f"Download/data preparation finished. Readiness bleibt blocked wegen: {next_blocker}"
    status = build_initial_data_prep_last_run_status()
    status.update(
        {
            "last_run_status": "finished",
            "last_run_mode": runtime.get("mode", "execute" if result.get("execute") else "dry_run"),
            "last_run_started_at": runtime.get("started_at"),
            "last_run_finished_at": runtime.get("finished_at"),
            "last_run_duration_seconds": _duration_seconds(runtime.get("started_at"), runtime.get("finished_at")),
            "last_run_supported_tasks": plan.get("supported_download_task_count", runtime.get("supported_download_task_count", 0)),
            "last_run_completed_tasks": runtime.get("completed_tasks", 0),
            "last_run_skipped_tasks": runtime.get("skipped_tasks", 0),
            "last_run_failed_tasks": runtime.get("failed_tasks", 0),
            "last_run_planned_file_count": runtime.get("planned_file_count", 0),
            "last_run_completed_file_count": runtime.get("completed_file_count", 0),
            "last_run_skipped_file_count": runtime.get("skipped_file_count", 0),
            "last_run_downloaded_file_count": runtime.get("downloaded_file_count", 0),
            "last_run_failed_file_count": runtime.get("failed_file_count", 0),
            "last_run_download_results_count": len(download_results),
            "last_run_readiness_before": before_status,
            "last_run_readiness_after": after_status,
            "last_run_backtest_engine_locked": True,
            "last_run_summary_text": summary,
            "last_run_next_blocker": next_blocker,
            "error": None,
        }
    )
    return status


def build_failed_data_prep_last_run_status(
    runtime_status: Mapping[str, Any],
    error: BaseException | str,
) -> dict[str, Any]:
    """Build the durable visible last-run status for a failed controller run."""

    error_text = str(error)
    status = build_initial_data_prep_last_run_status()
    status.update(
        {
            "last_run_status": "failed",
            "last_run_mode": runtime_status.get("mode", "dry_run"),
            "last_run_started_at": runtime_status.get("started_at"),
            "last_run_finished_at": runtime_status.get("finished_at") or _utc_now(),
            "last_run_duration_seconds": _duration_seconds(
                runtime_status.get("started_at"), runtime_status.get("finished_at") or _utc_now()
            ),
            "last_run_supported_tasks": runtime_status.get("supported_download_task_count", runtime_status.get("total_tasks", 0)),
            "last_run_completed_tasks": runtime_status.get("completed_tasks", 0),
            "last_run_skipped_tasks": runtime_status.get("skipped_tasks", 0),
            "last_run_failed_tasks": max(1, int(runtime_status.get("failed_tasks", 0) or 0)),
            "last_run_backtest_engine_locked": True,
            "last_run_summary_text": f"Datenlauf fehlgeschlagen: {error_text}",
            "last_run_next_blocker": f"Fehler beheben: {error_text}",
            "error": error_text,
        }
    )
    return status


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
        "planned_file_count": 0,
        "current_file_index": 0,
        "current_file_name": None,
        "completed_file_count": 0,
        "skipped_file_count": 0,
        "downloaded_file_count": 0,
        "failed_file_count": 0,
        "elapsed_seconds": 0,
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


def build_data_prep_heartbeat_status(runtime_status: Mapping[str, Any], now: str | None = None) -> dict[str, Any]:
    """Return a heartbeat update so the UI changes even during long file downloads."""

    heartbeat = dict(runtime_status)
    heartbeat["elapsed_seconds"] = _duration_seconds(heartbeat.get("started_at"), now or _utc_now()) or 0
    heartbeat["last_message"] = "Still running. Progress is task/file based, not byte based."
    heartbeat["engine_start_locked"] = True
    heartbeat["backtest_started"] = False
    heartbeat["backtest_allowed"] = False
    return heartbeat


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
    updated["elapsed_seconds"] = _duration_seconds(updated.get("started_at"), _utc_now()) or 0
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

        def _file_progress_callback(event: dict[str, Any]) -> None:
            nonlocal status
            status = update_progress_status(
                status,
                progress_callback,
                phase="downloading",
                current_step="Downloading public file",
                current_task_id=event.get("task_id"),
                current_symbol=event.get("symbol"),
                current_data_type=event.get("data_type"),
                planned_file_count=event.get("planned_file_count", status.get("planned_file_count", 0)),
                current_file_index=event.get("current_file_index", status.get("current_file_index", 0)),
                current_file_name=event.get("current_file_name", status.get("current_file_name")),
                completed_file_count=event.get("completed_file_count", status.get("completed_file_count", 0)),
                skipped_file_count=event.get("skipped_file_count", status.get("skipped_file_count", 0)),
                downloaded_file_count=event.get("downloaded_file_count", status.get("downloaded_file_count", 0)),
                failed_file_count=event.get("failed_file_count", status.get("failed_file_count", 0)),
                last_message=event.get("message", "Still running. Progress is task/file based, not byte based."),
                error=event.get("error", status.get("error")),
            )
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
                result = _execute_public_download_task_with_optional_progress(task, _file_progress_callback)
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


def _execute_public_download_task_with_optional_progress(
    task: Mapping[str, Any],
    progress_callback: ProgressCallback,
) -> dict[str, Any]:
    downloader = public_data_downloader.execute_public_download_task
    if "progress_callback" in inspect.signature(downloader).parameters:
        return downloader(task, execute=True, progress_callback=progress_callback)
    return downloader(task, execute=True)


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


def _duration_seconds(started_at: Any, finished_at: Any) -> int | None:
    if not started_at or not finished_at:
        return None
    try:
        started = datetime.fromisoformat(str(started_at))
        finished = datetime.fromisoformat(str(finished_at))
    except ValueError:
        return None
    return max(0, round((finished - started).total_seconds()))


def _next_blocker(readiness: Mapping[str, Any]) -> str:
    for requirement in readiness.get("requirements", []):
        if isinstance(requirement, Mapping) and requirement.get("blocking_backtest"):
            return (
                f"{requirement.get('requirement_id')}: "
                f"status={requirement.get('status')}; reason={requirement.get('reason')}"
            )
    if not readiness.get("backtest_engine_implemented"):
        return "Backtest engine is not implemented; UI starts data preparation only."
    return str(readiness.get("backtest_button_reason") or "No blocker reported.")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _log(callback: LogCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _assert_no_forbidden_fields(result: dict[str, Any]) -> dict[str, Any]:
    if FORBIDDEN_RESULT_FIELDS & set(result):
        raise ValueError("data update result contains forbidden result fields")
    return result
