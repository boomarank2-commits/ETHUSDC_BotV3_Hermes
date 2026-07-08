"""Pure dashboard state helpers for the local control UI.

These helpers inspect paths and constants only. They do not create data folders,
read market data contents, download files, start UI processes, execute backtests,
create reports, or unlock live/paper/testtrade.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ethusdc_bot.data_pipeline.inventory_status import build_inventory_status
from ethusdc_bot.data_pipeline.public_kline_downloader import DEFAULT_RAW_ROOT

BACKTEST_DISABLED_HINT = "Backtest engine not implemented yet. Next step after data audit."
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
) -> dict[str, Any]:
    """Build the complete status-only dashboard snapshot."""

    return {
        "schema_version": 1,
        "project_status": collect_project_status(),
        "safety_status": collect_safety_status(),
        "inventory_status": collect_inventory_status(repository_root, local_root),
        "download_folder_status": collect_download_folder_status(local_root),
        "ui_status": {
            "backtest_button": {
                "visible": True,
                "enabled": False,
                "hint": BACKTEST_DISABLED_HINT,
            },
            "live_paper_testtrade": "locked",
        },
    }


def format_snapshot_for_display(snapshot: Mapping[str, Any]) -> str:
    """Format a dashboard snapshot for the Tk text area or terminal diagnostics."""

    project = snapshot["project_status"]
    safety = snapshot["safety_status"]
    inventory = snapshot["inventory_status"]
    counts = inventory["counts"]
    download = snapshot["download_folder_status"]
    backtest = snapshot["ui_status"]["backtest_button"]
    lines = [
        "ETHUSDC Bot V3 Hermes - Local Control Dashboard",
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
        "Backtest:",
        f"- Button visible: {backtest['visible']}",
        f"- Button enabled: {backtest['enabled']}",
        f"- Hint: {backtest['hint']}",
    ]
    return "\n".join(lines) + "\n"


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
