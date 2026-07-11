"""Pure dashboard state helpers for the local control UI.

These helpers inspect paths and validated local status artifacts only. They do
not create folders, download data, execute research, adopt candidates, append
Shadow events, or unlock live/paper/testtrade.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ethusdc_bot.data_pipeline.data_readiness import build_backtest_start_data_gate
from ethusdc_bot.data_pipeline.kline_zip_audit import build_kline_audit_summary
from ethusdc_bot.data_pipeline.inventory_status import build_inventory_status
from ethusdc_bot.data_pipeline.public_kline_downloader import DEFAULT_RAW_ROOT
from ethusdc_bot.portfolio import PortfolioPolicy
from ethusdc_bot.shadow.adoption import assess_final_report
from ethusdc_bot.shadow.store import (
    load_deployment,
    load_shadow_state,
    verify_event_log,
)
from ethusdc_bot.ui.backtest_controller import build_initial_training_research_status
from ethusdc_bot.ui.final_evaluation_controller import (
    build_initial_final_evaluation_status,
    discover_latest_frozen_research_report,
)
from ethusdc_bot.ui.data_update_controller import (
    build_data_update_plan,
    build_initial_data_prep_last_run_status,
    build_initial_data_prep_status,
)

BACKTEST_DISABLED_HINT = "Training/WFV research waits for the complete data gate. No fake result."
BACKTEST_START_HINT = (
    "Starts Protocol-v2 training/validation/WFV only. The sealed final holdout "
    "is a separate one-shot step and is never opened by this button."
)
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
        "fixed_lot_notional_usdc": 100,
        "risk_profile": "mittel",
        "training_days": 730,
        "blindtest_days": 365,
        "required_utc_days": EXPECTED_UTC_DAYS,
        "context_symbols": ["BTCUSDC", "ETHBTC"],
        "future_goal": "about 3 USDC/day after costs as a guideline, not a guarantee",
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


def collect_portfolio_status(deployment_budget_usdc: int = 100) -> dict[str, Any]:
    """Return the validated fixed-lot policy selected by the operator."""

    policy = PortfolioPolicy(deployment_budget_usdc=deployment_budget_usdc)
    return policy.to_dict()


def collect_final_evaluation_status(final_reports_root: str | Path) -> dict[str, Any]:
    """Inspect the newest final report without changing it or adopting it."""

    root = Path(final_reports_root)
    reports = sorted(path for path in root.glob("*.json") if path.is_file()) if root.exists() else []
    if not reports:
        return {
            "status": "not_found",
            "report_path": None,
            "color": "none",
            "shadow_eligible": False,
            "target_reached": False,
            "live_eligible": False,
            "final_net_usdc_per_day": None,
            "reason_codes": ["no_final_evaluation_report"],
        }
    report_path = reports[-1]
    assessment = assess_final_report(report_path)
    return {
        "status": "verified" if assessment.color in {"green", "yellow"} else "blocked",
        "report_path": str(report_path),
        "color": assessment.color,
        "shadow_eligible": assessment.shadow_eligible,
        "target_reached": assessment.target_reached,
        "live_eligible": False,
        "final_net_usdc_per_day": assessment.final_net_usdc_per_day,
        "reason_codes": list(assessment.reason_codes),
        "final_evaluation_id": assessment.final_evaluation_id,
        "candidate_id": assessment.candidate_id,
    }


def collect_shadow_runtime_status(shadow_root: str | Path) -> dict[str, Any]:
    """Read and cross-check the newest persisted order-free Shadow state."""

    root = Path(shadow_root)
    deployments = (
        sorted(path for path in root.iterdir() if path.is_dir() and not path.name.startswith("."))
        if root.exists()
        else []
    )
    if not deployments:
        return {
            "status": "not_adopted",
            "deployment_id": None,
            "phase": "not_started",
            "deployment_budget_usdc": None,
            "lot_notional_usdc": 100.0,
            "open_lots": 0,
            "max_open_lots": 0,
            "realized_net_usdc": 0.0,
            "unrealized_net_usdc": 0.0,
            "event_count": 0,
            "error": None,
            "orders_enabled": False,
            "trading_api_enabled": False,
            "api_keys_used": False,
        }
    deployment_dir = deployments[-1]
    try:
        deployment = load_deployment(deployment_dir / "deployment.json")
        state = load_shadow_state(deployment_dir / "state.json")
        event_status = verify_event_log(deployment_dir / "events.jsonl")
        if deployment["deployment_id"] != state["deployment_id"]:
            raise ValueError("deployment/state id mismatch")
        if state["event_count"] != event_status["event_count"]:
            raise ValueError("state/event count mismatch")
        if state["last_event_hash"] != event_status["last_event_hash"]:
            raise ValueError("state/event hash mismatch")
    except (OSError, ValueError) as exc:
        return {
            "status": "integrity_error",
            "deployment_id": deployment_dir.name,
            "phase": "error",
            "deployment_budget_usdc": None,
            "lot_notional_usdc": 100.0,
            "open_lots": 0,
            "max_open_lots": 0,
            "realized_net_usdc": 0.0,
            "unrealized_net_usdc": 0.0,
            "event_count": 0,
            "error": str(exc),
            "orders_enabled": False,
            "trading_api_enabled": False,
            "api_keys_used": False,
        }
    return {
        "status": "valid",
        "deployment_id": state["deployment_id"],
        "phase": state["phase"],
        "deployment_budget_usdc": state["deployment_budget_usdc"],
        "lot_notional_usdc": state["lot_notional_usdc"],
        "open_lots": len(state["open_lots"]),
        "max_open_lots": state["max_open_lots"],
        "realized_net_usdc": state["realized_net_usdc"],
        "unrealized_net_usdc": state["unrealized_net_usdc"],
        "event_count": state["event_count"],
        "error": state["error"],
        "orders_enabled": False,
        "trading_api_enabled": False,
        "api_keys_used": False,
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
    *,
    deployment_budget_usdc: int = 100,
    training_research_status: Mapping[str, Any] | None = None,
    final_evaluation_runtime_status: Mapping[str, Any] | None = None,
    training_reports_root: str | Path | None = None,
    final_reports_root: str | Path | None = None,
    shadow_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build the complete status-only dashboard snapshot."""

    data_update_plan = build_data_update_plan(local_root)
    data_readiness_report = build_backtest_start_data_gate(local_root)
    runtime_status = build_initial_data_prep_status()
    overall_progress = build_overall_data_progress(data_readiness_report)
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
    training_status = dict(
        training_research_status or build_initial_training_research_status()
    )
    final_runtime_status = dict(
        final_evaluation_runtime_status or build_initial_final_evaluation_status()
    )
    local_path = Path(local_root)
    research_root = (
        Path(training_reports_root)
        if training_reports_root is not None
        else local_path / "runtime" / "reports" / "research_loop"
    )
    final_root = (
        Path(final_reports_root)
        if final_reports_root is not None
        else local_path / "runtime" / "reports" / "sealed_holdout_final"
    )
    shadow_state_root = Path(shadow_root) if shadow_root is not None else local_path / "runtime" / "shadow"
    portfolio_status = collect_portfolio_status(deployment_budget_usdc)
    final_status = collect_final_evaluation_status(final_root)
    frozen_research_status = discover_latest_frozen_research_report(research_root)
    shadow_status = collect_shadow_runtime_status(shadow_state_root)
    data_ready = bool(data_readiness_report.get("data_gate_ready"))
    research_running = bool(training_status.get("running"))
    final_running = bool(final_runtime_status.get("running"))
    can_start_training = data_ready and not research_running and not final_running
    can_adopt_shadow = bool(final_status["shadow_eligible"])
    can_run_final = bool(
        frozen_research_status["status"] == "ready_for_explicit_one_shot"
        and not research_running
        and not final_running
        and final_status["status"] == "not_found"
    )
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
        "portfolio_status": portfolio_status,
        "training_research_status": training_status,
        "final_evaluation_runtime_status": final_runtime_status,
        "frozen_research_status": frozen_research_status,
        "final_evaluation_status": final_status,
        "shadow_runtime_status": shadow_status,
        "final_reports_root": str(final_root),
        "training_reports_root": str(research_root),
        "shadow_root": str(shadow_state_root),
        "operator_data_status_rows": build_operator_data_status_rows(data_readiness_report),
        "overall_data_progress_pct": overall_progress["overall_data_progress_pct"],
        "overall_data_progress": overall_progress,
        "current_run_progress_pct": runtime_status["progress_pct"],
        "data_prep_progress_pct": overall_progress["overall_data_progress_pct"],
        "data_prep_current_task": runtime_status["current_task_id"],
        "data_prep_mode": runtime_status["mode"],
        "bot_current_status_text": _build_bot_status_text(data_readiness_report, runtime_status),
        "can_start_data_prep": True,
        "can_start_backtest_engine": can_start_training,
        "backtest_status": build_initial_backtest_status(
            data_readiness_report, training_status
        ),
        "backtest_blocker_summary": backtest_blocker_summary,
        "data_prep_status": {
            "status": "idle",
            "engine_start_locked": not data_ready,
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
                "enabled": can_start_training,
                "action": "training_validation_wfv_protocol_v2",
                "engine_locked": not data_ready,
                "final_holdout_evaluated": False,
                "uses_trading_api": False,
                "live_paper_testtrade_locked": True,
                "hint": BACKTEST_START_HINT,
            },
            "shadow_adopt_button": {
                "visible": True,
                "enabled": can_adopt_shadow,
                "action": "adopt_verified_final_report_to_order_free_shadow",
                "report_path": final_status["report_path"],
                "assessment_color": final_status["color"],
                "orders_enabled": False,
                "trading_api_enabled": False,
                "live_enabled": False,
                "hint": (
                    "Only a freshly re-verified green/yellow final evaluation can be adopted. "
                    "Adoption creates no real order."
                ),
            },
            "sealed_final_button": {
                "visible": True,
                "enabled": can_run_final,
                "action": "run_irreversible_sealed_holdout_once",
                "source_report_path": frozen_research_status["report_path"],
                "orders_enabled": False,
                "trading_api_enabled": False,
                "live_enabled": False,
                "hint": (
                    "Irreversible one-shot final evaluation. A persistent claim is created "
                    "before the sealed candles are loaded; failures must not be retried."
                ),
            },
            "live_paper_testtrade": "locked",
        },
    }


def build_initial_backtest_status(
    readiness: Mapping[str, Any],
    training_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the UI model for backtest mode without fake results."""

    data_ready = bool(readiness.get("data_gate_ready"))
    run = dict(training_status or build_initial_training_research_status())
    running = bool(run.get("running"))
    phase = str(run.get("phase", "initial"))
    return {
        "mode": "backtest",
        "phase": "running" if running else "idle" if phase == "initial" else phase,
        "enabled": data_ready and not running,
        "stages": [
            "data_gate",
            "training_validation",
            "walk_forward",
            "quality_gates",
            "sealed_holdout_separate",
        ],
        "status_text": (
            "Training/WFV-Forschung laeuft; der versiegelte Final-Holdout bleibt geschlossen."
            if running
            else "Data Gate bereit; Training/Validation/WFV kann gestartet werden. Final-Holdout separat."
            if data_ready
            else "Training/WFV wartet auf das Data Gate. Keine Ergebnisse erfunden."
        ),
        "target_usdc_per_day": 3.0,
        "result_status": str(run.get("freeze_status", "not_run")),
        "final_holdout_evaluated": False,
        "shadow_eligible": False,
        "live_paper_testtrade": "locked",
    }


def build_overall_data_progress(readiness: Mapping[str, Any]) -> dict[str, Any]:
    """Compute persistent local-data progress from valid local files and requirements."""

    requirements = readiness.get("requirements_by_id", {})
    source_ids = [
        "ethusdc_klines_1m",
        "btcusdc_klines_1m",
        "ethbtc_klines_1m",
        "ethusdc_aggtrades",
        "ethusdc_trades",
    ]
    available_total = 0
    required_total = 0
    sources = []
    for requirement_id in source_ids:
        requirement = requirements.get(requirement_id, {}) if isinstance(requirements, Mapping) else {}
        required = int(requirement.get("required_days", 0) or requirement.get("minimum_days", 0) or 0)
        available = int(requirement.get("available_days", 0) or 0)
        counted_available = min(available, required) if required else available
        available_total += counted_available
        required_total += required
        sources.append(
            {
                "requirement_id": requirement_id,
                "available_days": available,
                "counted_available_days": counted_available,
                "required_days": required,
                "status": str(requirement.get("status", "missing")),
                "latest_available_day": requirement.get("latest_available_day"),
            }
        )
    pct = round((available_total / required_total) * 100, 2) if required_total else 100.0
    return {
        "overall_data_progress_pct": pct,
        "available_days": available_total,
        "required_days": required_total,
        "sources": sources,
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
    overall_progress = snapshot.get("overall_data_progress_pct", 0)
    data_rows = snapshot.get("operator_data_status_rows", [])
    portfolio = snapshot["portfolio_status"]
    final = snapshot["final_evaluation_status"]
    shadow = snapshot["shadow_runtime_status"]
    research = snapshot["training_research_status"]
    frozen = snapshot["frozen_research_status"]
    final_runtime = snapshot["final_evaluation_runtime_status"]
    lines = [
        "ETHUSDC Bot V3 Hermes",
        "",
        f"Bot-Status: {_operator_bot_status(runtime, last_run)}",
        f"Datenstatus: {snapshot['data_readiness_report']['overall_status']}",
        f"Gesamtdatenstand: {overall_progress}%",
        f"Gesamtfortschritt: {overall_progress}%",
        f"Aktueller Lauf: {progress}% seit Start / {runtime.get('current_step', 'Idle')}",
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
        f"Backtest: {snapshot['backtest_status']['status_text']}",
        (
            "Research-Status: "
            f"{research.get('phase')} / {research.get('freeze_status')}"
        ),
        (
            "Frozen Candidate: "
            f"{frozen.get('status')} / {frozen.get('candidate_id')}"
        ),
        (
            "Finaltest-Lauf: "
            f"{final_runtime.get('phase')} / "
            f"{final_runtime.get('final_holdout_outcome')} / "
            f"wiederholbar={final_runtime.get('retry_allowed')}"
        ),
        (
            "Portfolio: "
            f"{portfolio['deployment_budget_usdc']} USDC Budget, "
            f"{portfolio['lot_notional_usdc']} USDC/Lot, "
            f"max. {portfolio['max_concurrent_lots']} Lots, kein Compounding"
        ),
        (
            "Final-Ampel: "
            f"{final['color']} / Shadow-uebernehmbar={final['shadow_eligible']} / "
            f"Netto pro Tag={final['final_net_usdc_per_day']}"
        ),
        (
            "Shadow: "
            f"{shadow['status']} / {shadow['phase']} / "
            f"Lots {shadow['open_lots']}/{shadow['max_open_lots']} / "
            "Orders=false, Trading-API=false"
        ),
        "",
        "Datenstatus:",
    ]
    for row in data_rows:
        lines.append(f"- {row['label']}: {row['files_text']} Dateien, {row['status']}")
    if overall_progress:
        lines.append("Hinweis: Fortsetzen möglich. Vorhandene Dateien werden übersprungen.")
    if snapshot["data_readiness_report"]["overall_status"] != "ready":
        lines.append("Hinweis: Fehlende Daten vorhanden. Klicke Daten prüfen & fehlende Daten laden.")
    if any(row.get("reason", "").startswith("latest local day") for row in data_rows):
        lines.append("Hinweis: Daten älter als 7 Tage. Bitte Daten aktualisieren.")
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
        "- Protocol-v2 training/validation/WFV is wired; sealed final evaluation remains separate.",
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
        "",
        "Portfolio / Final / Shadow:",
        f"- Portfolio: {snapshot['portfolio_status']}",
        f"- Training research: {snapshot['training_research_status']}",
        f"- Final evaluation: {snapshot['final_evaluation_status']}",
        f"- Shadow runtime: {snapshot['shadow_runtime_status']}",
    ]
    return "\n".join(lines) + "\n"


def _build_backtest_blocker_summary(readiness: Mapping[str, Any]) -> str:
    blockers = []
    if not readiness.get("data_gate_ready"):
        blockers.append(str(readiness.get("backtest_button_reason", "Data readiness is blocked.")))
    if readiness.get("data_gate_ready"):
        blockers.append(
            "Training/validation/WFV is available; final holdout remains a separate sealed one-shot step."
        )
    return " ".join(blockers)


def _build_bot_status_text(readiness: Mapping[str, Any], runtime_status: Mapping[str, Any]) -> str:
    if runtime_status.get("phase") not in {"idle", "finished"}:
        return f"Data preparation running: {runtime_status.get('phase')}"
    if readiness.get("data_gate_ready"):
        return "Data readiness is complete; Protocol-v2 training/validation/WFV can be started. Final holdout remains sealed."
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
