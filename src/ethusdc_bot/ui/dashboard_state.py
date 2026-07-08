"""Pure dashboard state helpers for the local control UI.

These helpers inspect paths and constants only. They do not create data folders,
read market data contents, download files, start UI processes, execute backtests,
create reports, or unlock live/paper/testtrade.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ethusdc_bot.data_pipeline.data_readiness import build_backtest_start_data_gate
from ethusdc_bot.data_pipeline.kline_zip_audit import build_kline_audit_summary
from ethusdc_bot.data_pipeline.inventory_status import build_inventory_status
from ethusdc_bot.data_pipeline.public_kline_downloader import DEFAULT_RAW_ROOT
from ethusdc_bot.ui.data_update_controller import (
    build_data_update_plan,
    build_initial_data_prep_last_run_status,
    build_initial_data_prep_status,
)

BACKTEST_DISABLED_HINT = "Backtest waits for data readiness and real engine implementation. No fake result."
BACKTEST_START_HINT = "Backtest start currently prepares data only. Real engine is not implemented yet."
EXPECTED_UTC_DAYS = 1095


def collect_project_status() -> dict[str, Any]:
    """Return the static project contract values shown by the dashboard."""

    return {
        "symbol": "ETHUSDC",
        "quote_asset": "USDC",
        "exchange": "Binance",
        "market_type": "Spot",
        "position_mode": "LONG-only",
        "start_capital_usdc": 100,
        "risk_profile": "mittel",
        "training_days": 730,
        "blindtest_days": 365,
        "required_utc_days": EXPECTED_UTC_DAYS,
        "context_symbols": ["BTCUSDC", "ETHBTC"],
        "future_goal": ">= 3 USDC/day after realistic blindtest",
    }


def collect_safety_status() -> dict[str, str]:
    """Return current safety locks. This UI cannot unlock them."""

    return {
        "live": "locked",
        "paper": "locked",
        "testtrade": "locked",
        "shorts_margin_futures_leverage": "forbidden",
        "binance_trading_api": "forbidden",
        "api_keys": "not_used",
    }


def collect_inventory_status(repository_root: str | Path, local_root: str | Path) -> dict[str, Any]:
    """Collect path-only inventory status without creating or reading data files."""

    status = build_inventory_status(local_root=local_root, repository_root=repository_root)
    sources_by_id = {source["source_id"]: source for source in status["inventory"]["sources"]}
    return {
        "local_root": status["local_root"],
        "repository_root": status["repository_root"],
        "inventory_status": status["overall_status"],
        "quality_status": status["quality_status"],
        "counts": status["counts"],
        "ethusdc_1m_klines": _source_summary(sources_by_id, "ethusdc_1m_klines"),
        "btcusdc_1m_context": _source_summary(sources_by_id, "btcusdc_1m_klines"),
        "ethbtc_1m_context": _source_summary(sources_by_id, "ethbtc_1m_klines"),
        "safety_notice": status["safety_notice"],
    }


def collect_download_folder_status(local_root: str | Path) -> dict[str, Any]:
    """Collect count-only status for the ETHUSDC 1m kline download directory."""

    download_dir = _ethusdc_1m_download_dir(local_root)
    counts = count_download_files(download_dir)
    return {
        "target_dir": str(download_dir),
        "exists": download_dir.exists(),
        **counts,
    }


def collect_kline_audit_status(local_root: str | Path, required_utc_days: int = EXPECTED_UTC_DAYS) -> dict[str, Any]:
    """Collect real local ETHUSDC 1m kline ZIP audit status when data exists."""

    download_dir = _ethusdc_1m_download_dir(local_root)
    if not download_dir.exists():
        return {
            "schema_version": 1,
            "symbol": "ETHUSDC",
            "interval": "1m",
            "download_dir": str(download_dir),
            "zip_count": 0,
            "checksum_count": 0,
            "audit_status": "not_audited",
            "observed_start_utc": None,
            "observed_end_utc": None,
            "observed_rows": 0,
            "complete_utc_days": 0,
            "missing_utc_days": [],
            "missing_utc_days_count": 0,
            "duplicate_rows": 0,
            "gap_count": 0,
            "max_gap_seconds": 0,
            "unsorted_rows": 0,
            "blocked_files": 0,
            "backtest_ready": False,
            "files": [],
            "safety_note": "Local audit only; no download; no Binance API; no backtest; live/paper/testtrade locked.",
        }
    return build_kline_audit_summary(download_dir, required_utc_days=required_utc_days)


def count_download_files(download_dir: str | Path) -> dict[str, Any]:
    """Count ZIP and CHECKSUM files and list up to the last 10 names.

    Missing folders are reported honestly and are not created.
    """

    directory = Path(download_dir)
    files = sorted([path for path in directory.iterdir() if path.is_file()]) if directory.exists() else []
    zip_files = [path for path in files if path.name.endswith(".zip")]
    checksum_files = [path for path in files if path.name.endswith(".CHECKSUM")]
    return {
        "zip_count": len(zip_files),
        "checksum_count": len(checksum_files),
        "last_10_files": [path.name for path in files[-10:]],
        "expected_zip_count_for_1095_days": EXPECTED_UTC_DAYS,
        "expected_checksum_count_for_1095_days": EXPECTED_UTC_DAYS,
        "quality_claim": "not_audited",
        "progress_note": (
            "Counts are rough file presence only; no completeness or quality claim "
            "exists until a separate audit is implemented."
        ),
    }


def build_dashboard_snapshot(
    repository_root: str | Path,
    local_root: str | Path = DEFAULT_RAW_ROOT,
    data_prep_last_run_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the complete status-only dashboard snapshot."""

    data_update_plan = build_data_update_plan(local_root)
    data_readiness_report = build_backtest_start_data_gate(local_root)
    runtime_status = build_initial_data_prep_status()
    runtime_status.update(
        {
            "supported_download_task_count": data_update_plan["supported_download_task_count"],
            "unsupported_task_count": data_update_plan["unsupported_task_count"],
            "live_collector_task_count": data_update_plan["live_collector_task_count"],
            "total_tasks": data_update_plan["supported_download_task_count"],
        }
    )
    backtest_blocker_summary = _build_backtest_blocker_summary(data_readiness_report)
    last_run_status = dict(data_prep_last_run_status or build_initial_data_prep_last_run_status())
    return {
        "schema_version": 1,
        "project_status": collect_project_status(),
        "safety_status": collect_safety_status(),
        "inventory_status": collect_inventory_status(repository_root, local_root),
        "download_folder_status": collect_download_folder_status(local_root),
        "kline_audit_status": collect_kline_audit_status(local_root),
        "data_readiness_report": data_readiness_report,
        "data_prep_runtime_status": runtime_status,
        "data_prep_last_run_status": last_run_status,
        "operator_data_status_rows": build_operator_data_status_rows(data_readiness_report),
        "data_prep_progress_pct": runtime_status["progress_pct"],
        "data_prep_current_task": runtime_status["current_task_id"],
        "data_prep_mode": runtime_status["mode"],
        "bot_current_status_text": _build_bot_status_text(data_readiness_report, runtime_status),
        "can_start_data_prep": True,
        "can_start_backtest_engine": False,
        "backtest_blocker_summary": backtest_blocker_summary,
        "data_prep_status": {
            "status": "idle",
            "engine_start_locked": True,
            "last_data_update_plan_summary": data_update_plan["summary"],
            "supported_download_task_count": data_update_plan["supported_download_task_count"],
            "unsupported_task_count": data_update_plan["unsupported_task_count"],
            "live_collector_task_count": data_update_plan["live_collector_task_count"],
        },
        "ui_status": {
            "data_prep_button": {
                "visible": True,
                "enabled": True,
                "action": "data_preparation_only",
                "hint": BACKTEST_DISABLED_HINT,
            },
            "backtest_start_button": {
                "visible": True,
                "enabled": True,
                "action": "data_preparation_only",
                "engine_locked": True,
                "hint": BACKTEST_START_HINT,
            },
            "live_paper_testtrade": "locked",
        },
    }


def build_operator_data_status_rows(readiness: Mapping[str, Any]) -> list[dict[str, str]]:
    """Return five concise user-facing data status rows for the dashboard."""

    requirements = readiness.get("requirements_by_id", {})
    specs = [
        ("ETHUSDC 1m", "ethusdc_klines_1m"),
        ("BTCUSDC 1m", "btcusdc_klines_1m"),
        ("ETHBTC 1m", "ethbtc_klines_1m"),
        ("ETHUSDC aggTrades", "ethusdc_aggtrades"),
        ("ETHUSDC trades", "ethusdc_trades"),
    ]
    rows = []
    for label, requirement_id in specs:
        requirement = requirements.get(requirement_id, {}) if isinstance(requirements, Mapping) else {}
        available = int(requirement.get("available_days", 0) or 0)
        required = int(requirement.get("required_days", 0) or requirement.get("minimum_days", 0) or 0)
        rows.append(
            {
                "label": label,
                "status": _operator_status_word(str(requirement.get("status", "missing")), available, required),
                "files_text": f"{available}/{required}" if required else "wird ermittelt",
                "reason": str(requirement.get("reason") or ""),
            }
        )
    return rows


def format_operator_summary_for_display(snapshot: Mapping[str, Any]) -> str:
    """Format only the concise operator summary, not the raw diagnostic snapshot."""

    last_run = snapshot["data_prep_last_run_status"]
    runtime = snapshot["data_prep_runtime_status"]
    progress = runtime.get("progress_pct", 0)
    data_rows = snapshot.get("operator_data_status_rows", [])
    lines = [
        "ETHUSDC Bot V3 Hermes",
        "",
        f"Bot-Status: {_operator_bot_status(runtime, last_run)}",
        f"Datenstatus: {snapshot['data_readiness_report']['overall_status']}",
        f"Gesamtfortschritt: {progress}%",
        f"Aktueller Download: {runtime.get('current_file_name') or runtime.get('current_task_id') or 'keiner'}",
        (
            "Dateien: "
            f"{runtime.get('completed_file_count', 0)}/{runtime.get('planned_file_count', 0)} "
            f"(geladen {runtime.get('downloaded_file_count', 0)}, "
            f"übersprungen {runtime.get('skipped_file_count', 0)}, "
            f"Fehler {runtime.get('failed_file_count', 0)})"
        ),
        f"Letzter Lauf: {last_run['last_run_status']} / {last_run['last_run_mode']} - {last_run['last_run_summary_text']}",
        f"Nächster Blocker: {last_run['last_run_next_blocker'] or snapshot['backtest_blocker_summary']}",
        f"Backtest: Gesperrt, weil Daten/Engine fehlen. Keine Fake-Ergebnisse.",
        "",
        "Datenstatus:",
    ]
    for row in data_rows:
        lines.append(f"- {row['label']}: {row['files_text']} Dateien, {row['status']}")
    return "\n".join(lines) + "\n"


def _operator_status_word(status: str, available: int, required: int) -> str:
    if status in {"ready", "present"} or (required and available >= required):
        return "vollständig"
    if available > 0:
        return "teilweise"
    return "fehlt"


def _operator_bot_status(runtime: Mapping[str, Any], last_run: Mapping[str, Any]) -> str:
    phase = runtime.get("phase")
    if phase in {"checking_readiness", "planning", "dry_run", "refreshing_readiness"}:
        return "Prüft Daten"
    if phase == "downloading":
        return "Lädt Daten"
    if phase == "failed" or last_run.get("last_run_status") == "failed":
        return "Fehler"
    if phase == "finished" or last_run.get("last_run_status") == "finished":
        return "Fertig"
    return "Bereit"


def format_snapshot_for_display(snapshot: Mapping[str, Any]) -> str:
    """Format a dashboard snapshot for the Tk text area or terminal diagnostics."""

    project = snapshot["project_status"]
    safety = snapshot["safety_status"]
    inventory = snapshot["inventory_status"]
    counts = inventory["counts"]
    download = snapshot["download_folder_status"]
    audit = snapshot["kline_audit_status"]
    readiness = snapshot["data_readiness_report"]
    prep = snapshot["data_prep_status"]
    runtime = snapshot["data_prep_runtime_status"]
    last_run = snapshot["data_prep_last_run_status"]
    window = readiness["backtest_window"]
    backtest = snapshot["ui_status"]["backtest_start_button"]
    lines = [
        "ETHUSDC Bot V3 Hermes - Local Control Dashboard",
        "",
        "Last Data Prep Run:",
        f"- Last status: {last_run['last_run_status']}",
        f"- Last mode: {last_run['last_run_mode']}",
        f"- Last started_at: {last_run['last_run_started_at']}",
        f"- Last finished_at: {last_run['last_run_finished_at']}",
        f"- Last duration seconds: {last_run['last_run_duration_seconds']}",
        f"- Last supported/completed/skipped/failed: {last_run['last_run_supported_tasks']}/{last_run['last_run_completed_tasks']}/{last_run['last_run_skipped_tasks']}/{last_run['last_run_failed_tasks']}",
        f"- Last download results count: {last_run['last_run_download_results_count']}",
        f"- Last files planned/completed/skipped/downloaded/failed: {last_run.get('last_run_planned_file_count', 0)}/{last_run.get('last_run_completed_file_count', 0)}/{last_run.get('last_run_skipped_file_count', 0)}/{last_run.get('last_run_downloaded_file_count', 0)}/{last_run.get('last_run_failed_file_count', 0)}",
        f"- Last readiness before/after: {last_run['last_run_readiness_before']} -> {last_run['last_run_readiness_after']}",
        f"- Last engine locked: {last_run['last_run_backtest_engine_locked']}",
        f"- Last next blocker: {last_run['last_run_next_blocker']}",
        f"- Last summary: {last_run['last_run_summary_text']}",
        "",
        "Project Status:",
        f"- Symbol: {project['symbol']}",
        f"- Quote: {project['quote_asset']}",
        f"- Exchange/Market: {project['exchange']} {project['market_type']}",
        f"- Position mode: {project['position_mode']}",
        f"- Start capital: {project['start_capital_usdc']} USDC",
        f"- Training: {project['training_days']} days",
        f"- Blindtest: {project['blindtest_days']} days",
        f"- Required UTC Days: {project['required_utc_days']}",
        f"- Future target: {project['future_goal']}",
        f"- Context symbols: {', '.join(project['context_symbols'])} (context only)",
        "",
        "Safety:",
        f"- Live: {safety['live']}",
        f"- Paper: {safety['paper']}",
        f"- Testtrade: {safety['testtrade']}",
        f"- Shorts/Margin/Futures/Leverage: {safety['shorts_margin_futures_leverage']}",
        "",
        "Data Inventory Status:",
        f"- local_root: {inventory['local_root']}",
        f"- repository_root: {inventory['repository_root']}",
        f"- inventory status: {inventory['inventory_status']}",
        (
            "- total/missing/present/blocked: "
            f"{counts['total']}/{counts['missing']}/{counts['present']}/{counts['blocked']}"
        ),
        _format_source_line("ETHUSDC 1m Klines", inventory["ethusdc_1m_klines"]),
        _format_source_line("BTCUSDC 1m context", inventory["btcusdc_1m_context"]),
        _format_source_line("ETHBTC 1m context", inventory["ethbtc_1m_context"]),
        "",
        "Download Folder Status:",
        f"- Target ETHUSDC 1m Klines: {download['target_dir']}",
        f"- Folder exists: {download['exists']}",
        f"- ZIP count: {download['zip_count']}",
        f"- CHECKSUM count: {download['checksum_count']}",
        (
            "- Rough target for 1095 days: "
            f"ca. {download['expected_zip_count_for_1095_days']} ZIP + "
            f"{download['expected_checksum_count_for_1095_days']} CHECKSUM"
        ),
        f"- Quality claim: {download['quality_claim']}",
        f"- Note: {download['progress_note']}",
        "- Last 10 files:",
        *_format_last_files(download["last_10_files"]),
        "",
        "Data Audit Status:",
        f"- ZIP count: {audit['zip_count']}",
        f"- CHECKSUM count: {audit['checksum_count']}",
        f"- Audit status: {audit['audit_status']}",
        f"- observed_start_utc: {audit['observed_start_utc']}",
        f"- observed_end_utc: {audit['observed_end_utc']}",
        f"- observed_rows: {audit['observed_rows']}",
        f"- complete_utc_days: {audit['complete_utc_days']}",
        f"- missing_utc_days count: {audit['missing_utc_days_count']}",
        f"- duplicate_rows: {audit['duplicate_rows']}",
        f"- gap_count: {audit['gap_count']}",
        f"- max_gap_seconds: {audit['max_gap_seconds']}",
        f"- backtest_ready: {audit['backtest_ready']}",
        f"- Note: {audit['safety_note']}",
        "",
        "Backtest Data Readiness:",
        f"- Overall status: {readiness['overall_status']}",
        f"- data_gate_ready: {readiness['data_gate_ready']}",
        f"- data_start: {window['data_start']}",
        f"- data_end: {window['data_end']}",
        f"- training_start: {window['training_start']}",
        f"- training_end: {window['training_end']}",
        f"- blind_start: {window['blind_start']}",
        f"- blind_end: {window['blind_end']}",
        "- Sources:",
        *_format_readiness_sources(readiness["requirements"]),
        f"- Hint: {readiness['backtest_button_reason']}",
        "",
        "Data Preparation Workflow:",
        f"- Bot state: {snapshot['bot_current_status_text']}",
        f"- Runtime phase: {runtime['phase']}",
        f"- Mode: {runtime['mode']}",
        f"- Progress: {runtime['progress_pct']}%",
        f"- Current step: {runtime['current_step']}",
        f"- Current task: {runtime['current_task_id'] or 'none'}",
        f"- Tasks completed/total: {runtime['completed_tasks']}/{runtime['total_tasks']}",
        f"- Backtest blocker: {snapshot['backtest_blocker_summary']}",
        "- Backtest start currently runs data preparation only. Real engine start is still locked.",
        f"- data_prep_status: {prep['status']}",
        f"- engine_start_locked: {prep['engine_start_locked']}",
        f"- last_data_update_plan_summary: {prep['last_data_update_plan_summary']}",
        f"- supported_download_task_count: {prep['supported_download_task_count']}",
        f"- unsupported_task_count: {prep['unsupported_task_count']}",
        f"- live_collector_task_count: {prep['live_collector_task_count']}",
        "",
        "Backtest:",
        f"- Button visible: {backtest['visible']}",
        f"- Button enabled: {backtest['enabled']}",
        f"- Button action: {backtest['action']}",
        f"- Engine locked: {backtest['engine_locked']}",
        f"- Hint: {backtest['hint']}",
    ]
    return "\n".join(lines) + "\n"


def _build_backtest_blocker_summary(readiness: Mapping[str, Any]) -> str:
    blockers = []
    if not readiness.get("data_gate_ready"):
        blockers.append(str(readiness.get("backtest_button_reason", "Data readiness is blocked.")))
    if not readiness.get("backtest_engine_implemented"):
        blockers.append("Backtest engine is not implemented; UI starts data preparation only.")
    return " ".join(blockers) or "Backtest engine is locked by policy."


def _build_bot_status_text(readiness: Mapping[str, Any], runtime_status: Mapping[str, Any]) -> str:
    if runtime_status.get("phase") not in {"idle", "finished"}:
        return f"Data preparation running: {runtime_status.get('phase')}"
    if readiness.get("data_gate_ready"):
        return "Data readiness is complete, but real backtest engine remains locked/not implemented."
    return "Data readiness is blocked; run dry-run or data loading to inspect missing tasks."


def default_repository_root() -> Path:
    """Return repository root from the src package location."""

    return Path(__file__).resolve().parents[3]


def default_local_root() -> Path:
    """Return the default external local data root."""

    return DEFAULT_RAW_ROOT


def _source_summary(sources_by_id: Mapping[str, Mapping[str, Any]], source_id: str) -> dict[str, Any]:
    source = sources_by_id.get(source_id)
    if source is None:
        return {"source_id": source_id, "status": "missing_catalog_entry", "expected_path": ""}
    return {
        "source_id": source_id,
        "symbol": source["symbol"],
        "status": source["status"],
        "expected_path": source["expected_path"],
        "quality_status": source["quality_status"],
        "may_trigger_orders": source["may_trigger_orders"],
    }


def _ethusdc_1m_download_dir(local_root: str | Path) -> Path:
    return Path(local_root) / "raw" / "binance" / "spot" / "ETHUSDC" / "klines" / "1m"


def _format_source_line(label: str, source: Mapping[str, Any]) -> str:
    return f"- {label}: {source['status']} ({source['expected_path']})"


def _format_last_files(files: Sequence[str]) -> list[str]:
    if not files:
        return ["  - none"]
    return [f"  - {name}" for name in files]


def _format_readiness_sources(requirements: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = []
    for requirement in requirements:
        lines.append(
            "  - "
            f"{requirement['requirement_id']}: status={requirement['status']}, "
            f"available_days={requirement['available_days']}, "
            f"required_days={requirement['required_days']}, "
            f"minimum_days={requirement['minimum_days']}, "
            f"included_in_backtest={requirement['included_in_backtest']}, "
            f"update_required={requirement['update_required']}, "
            f"blocking_backtest={requirement['blocking_backtest']}, "
            f"reason={requirement['reason']}"
        )
    return lines or ["  - none"]
