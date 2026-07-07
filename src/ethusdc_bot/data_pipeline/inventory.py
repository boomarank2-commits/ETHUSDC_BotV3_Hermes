"""Pure local data inventory helpers without downloads.

This module only maps catalog source metadata to expected local paths and checks
whether those paths exist. It does not read market data files, download data,
call Binance, run a strategy, execute a backtest, or create reports.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any


BLOCKED = "blocked"
MISSING = "missing"
PRESENT = "present"
PLANNED = "planned"
UNKNOWN = "unknown"


def build_expected_inventory(
    catalog: Mapping[str, Any], local_root: str | Path, repository_root: str | Path
) -> dict[str, Any]:
    """Build expected inventory entries from catalog metadata only."""

    local_root_path = Path(local_root)
    repository_root_path = Path(repository_root)
    local_root_blocked = _is_inside_repository(local_root_path, repository_root_path)

    entries = [
        _build_source_entry(source, local_root_path, repository_root_path, local_root_blocked)
        for source in catalog["sources"]
    ]

    status = BLOCKED if local_root_blocked else PLANNED
    quality_status = BLOCKED if local_root_blocked else UNKNOWN
    return {
        "schema_version": 1,
        "template": False,
        "status": status,
        "quality_status": quality_status,
        "local_root": str(local_root_path),
        "repository_root": str(repository_root_path),
        "sources": entries,
        "notes": "Path inventory only; no market data read and no data quality claimed.",
    }


def scan_local_inventory(
    catalog: Mapping[str, Any], local_root: str | Path, repository_root: str | Path
) -> dict[str, Any]:
    """Scan expected source paths for presence only, without reading files."""

    inventory = build_expected_inventory(catalog, local_root, repository_root)
    if inventory["status"] == BLOCKED:
        return inventory

    source_statuses: list[str] = []
    for entry in inventory["sources"]:
        expected_path = Path(entry["expected_path"])
        if _is_inside_repository(expected_path, repository_root):
            entry["status"] = BLOCKED
            entry["quality_status"] = BLOCKED
        elif expected_path.exists():
            entry["status"] = PRESENT
            entry["quality_status"] = UNKNOWN
        else:
            entry["status"] = MISSING
            entry["quality_status"] = MISSING
        source_statuses.append(entry["status"])

    if BLOCKED in source_statuses:
        inventory["status"] = BLOCKED
        inventory["quality_status"] = BLOCKED
    elif PRESENT in source_statuses and MISSING in source_statuses:
        inventory["status"] = "partial"
        inventory["quality_status"] = UNKNOWN
    elif source_statuses and all(status == PRESENT for status in source_statuses):
        inventory["status"] = PRESENT
        inventory["quality_status"] = UNKNOWN
    elif source_statuses and all(status == MISSING for status in source_statuses):
        inventory["status"] = MISSING
        inventory["quality_status"] = MISSING
    else:
        inventory["status"] = UNKNOWN
        inventory["quality_status"] = UNKNOWN

    return inventory


def _build_source_entry(
    source: Mapping[str, Any],
    local_root: Path,
    repository_root: Path,
    local_root_blocked: bool,
) -> dict[str, Any]:
    expected_path = _expected_path_for_source(source, local_root)
    blocked = local_root_blocked or _is_inside_repository(expected_path, repository_root)
    status = BLOCKED if blocked else UNKNOWN
    quality_status = BLOCKED if blocked else UNKNOWN

    return {
        "source_id": source["source_id"],
        "symbol": source["symbol"],
        "role": source["role"],
        "data_type": source["data_type"],
        "interval_seconds": source["interval_seconds"],
        "may_trigger_orders": source["may_trigger_orders"],
        "required_for_backtest_candidate": source["required_for_backtest_candidate"],
        "expected_path": str(expected_path),
        "status": status,
        "quality_status": quality_status,
        "notes": "Inventory metadata only; no data file content inspected.",
    }


def _expected_path_for_source(source: Mapping[str, Any], local_root: Path) -> Path:
    symbol = str(source["symbol"])
    data_type = str(source["data_type"])
    interval_seconds = source["interval_seconds"]

    parts = ["raw", "binance", "spot", symbol]
    if data_type == "klines":
        return local_root.joinpath(*parts, "klines", _interval_label(interval_seconds))
    return local_root.joinpath(*parts, data_type)


def _interval_label(interval_seconds: Any) -> str:
    if interval_seconds == 60:
        return "1m"
    return f"{interval_seconds}s"


def _is_inside_repository(path: str | Path, repository_root: str | Path) -> bool:
    repo_text = str(repository_root).replace("\\", "/").rstrip("/").lower()
    path_text = str(path).replace("\\", "/").rstrip("/").lower()
    if path_text == repo_text or path_text.startswith(repo_text + "/"):
        return True

    try:
        path_resolved = Path(path).resolve()
        repo_resolved = Path(repository_root).resolve()
    except (OSError, RuntimeError):
        return False

    try:
        path_resolved.relative_to(repo_resolved)
    except ValueError:
        return False
    return True
