"""Backtest data readiness gate.

This module plans and evaluates local data readiness only. It does not download
data, call Binance APIs, run backtests, create reports, create trades, or unlock
live/paper/testtrade.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ethusdc_bot.data_pipeline.data_requirements import build_backtest_data_requirements

TRAINING_DAYS = 730
BLIND_DAYS = 365
DEFAULT_REQUIRED_DAYS = TRAINING_DAYS + BLIND_DAYS
SUPPORTED_PUBLIC_DOWNLOADER_REQUIREMENTS = {
    "ethusdc_klines_1m",
    "btcusdc_klines_1m",
    "ethbtc_klines_1m",
    "ethusdc_aggtrades",
    "ethusdc_trades",
}
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


def compute_rolling_utc_window(
    reference_date: date | str | None = None,
    available_data_end: date | str | None = None,
    required_days: int = DEFAULT_REQUIRED_DAYS,
) -> dict[str, object]:
    """Return a rolling UTC data window ending at latest complete available day."""

    if required_days <= 0:
        raise ValueError("required_days must be positive")
    end = _parse_date(available_data_end) if available_data_end is not None else _parse_date(reference_date) - timedelta(days=1)
    start = end - timedelta(days=required_days - 1)
    return {"data_start": start.isoformat(), "data_end": end.isoformat(), "days": required_days}


def build_expected_backtest_window(latest_complete_day: date | str, required_days: int = DEFAULT_REQUIRED_DAYS) -> dict[str, object]:
    """Build data, training, and blindtest date boundaries without leakage."""

    base = compute_rolling_utc_window(available_data_end=latest_complete_day, required_days=required_days)
    data_start = date.fromisoformat(str(base["data_start"]))
    data_end = date.fromisoformat(str(base["data_end"]))
    training_start = data_start
    training_end = training_start + timedelta(days=TRAINING_DAYS - 1)
    blind_start = training_end + timedelta(days=1)
    blind_end = data_end
    return {
        **base,
        "training_start": training_start.isoformat(),
        "training_end": training_end.isoformat(),
        "training_days": TRAINING_DAYS,
        "blind_start": blind_start.isoformat(),
        "blind_end": blind_end.isoformat(),
        "blind_days": (blind_end - blind_start).days + 1,
    }


def evaluate_requirement_status(
    requirement: Mapping[str, object],
    local_root: str | Path,
    reference_date: date | str | None = None,
) -> dict[str, object]:
    """Evaluate one requirement from local files and configuration defaults."""

    ref = _reference_day(reference_date)
    root = Path(local_root)
    expected_path = _expected_path(root, requirement)
    available_days, latest_day = _available_days(requirement, expected_path)
    required_days = requirement.get("required_days")
    minimum_days = int(requirement.get("minimum_days") or 0)
    required_count = int(required_days or minimum_days or 0)
    coverage_pct = round((available_days / required_count) * 100, 2) if required_count else 100.0
    stale = latest_day is not None and (ref - latest_day).days > 7

    status = _status_for(requirement, available_days, stale)
    included = _included_in_backtest(requirement, available_days, status)
    diagnostic_only = _diagnostic_only(requirement, available_days, status)
    positive_allowed = bool(included and not requirement.get("context_only") and status == "current")
    if requirement.get("context_only"):
        positive_allowed = False
    blocking = bool(requirement.get("blocks_backtest") and status in {"missing", "partial", "outdated", "blocked"})
    update_required = status in {"missing", "partial", "outdated", "optional_missing", "diagnostic_only"} and (
        bool(requirement.get("publicly_downloadable")) or bool(requirement.get("live_collected"))
    )
    reason = _reason_for(requirement, status, available_days, latest_day)

    result = {
        "requirement_id": requirement["requirement_id"],
        "symbol": requirement["symbol"],
        "data_type": requirement["data_type"],
        "interval": requirement.get("interval"),
        "role": requirement["role"],
        "required": requirement["required"],
        "context_only": requirement["context_only"],
        "trade_market": requirement["trade_market"],
        "publicly_downloadable": requirement["publicly_downloadable"],
        "live_collected": requirement["live_collected"],
        "required_days": required_days,
        "minimum_days": requirement["minimum_days"],
        "available_days": available_days,
        "coverage_pct": coverage_pct,
        "latest_available_day": latest_day.isoformat() if latest_day else None,
        "status": status,
        "included_in_backtest": included,
        "diagnostic_only": diagnostic_only,
        "positive_candidate_influence_allowed": positive_allowed,
        "blocking_backtest": blocking,
        "update_required": update_required,
        "reason": reason,
        "expected_path": str(expected_path),
        "source_kind": requirement["source_kind"],
        "implemented_downloader": requirement["implemented_downloader"],
    }
    return _assert_no_forbidden_fields(result)


def build_data_readiness_report(local_root: str | Path, reference_date: date | str | None = None) -> dict[str, object]:
    """Build the full local data readiness report for the UI gate."""

    requirements = build_backtest_data_requirements()
    statuses = [evaluate_requirement_status(requirement, local_root, reference_date) for requirement in requirements]
    by_id = {str(status["requirement_id"]): status for status in statuses}
    eth = by_id["ethusdc_klines_1m"]
    latest = eth["latest_available_day"] or _reference_day(reference_date).isoformat()
    window = build_expected_backtest_window(str(latest), DEFAULT_REQUIRED_DAYS)
    data_gate_ready = not any(bool(status["blocking_backtest"]) for status in statuses)
    report = {
        "schema_version": 1,
        "status_type": "backtest_data_readiness",
        "overall_status": "ready" if data_gate_ready else "blocked",
        "data_gate_ready": data_gate_ready,
        "backtest_engine_implemented": False,
        "backtest_button_enabled": False,
        "backtest_button_reason": "Backtest waits for data readiness and real engine implementation. No fake result.",
        "local_root": str(Path(local_root)),
        "backtest_window": window,
        "requirements": statuses,
        "requirements_by_id": by_id,
        "missing_download_tasks": [],
        "outdated_download_tasks": [],
        "safety_note": "No download; no Binance trading API; no orders; no backtest result; live/paper/testtrade locked.",
    }
    report["missing_download_tasks"] = list_missing_download_tasks(report)
    report["outdated_download_tasks"] = list_outdated_download_tasks(report)
    return _assert_no_forbidden_fields(report)


def list_missing_download_tasks(readiness_report: Mapping[str, object]) -> list[dict[str, object]]:
    """List concrete missing public-download or live-collector tasks without executing them."""

    tasks = []
    for status in readiness_report["requirements"]:  # type: ignore[index]
        if not isinstance(status, Mapping):
            continue
        if status["status"] not in {"missing", "partial", "optional_missing", "diagnostic_only"}:
            continue
        if status["source_kind"] not in {"public_binance_data", "live_collection"}:
            continue
        tasks.append(_task_for_status(status, outdated=False))
    return tasks


def list_outdated_download_tasks(readiness_report: Mapping[str, object], max_age_days: int = 7) -> list[dict[str, object]]:
    """List concrete update tasks for sources older than the allowed age."""

    tasks = []
    for status in readiness_report["requirements"]:  # type: ignore[index]
        if not isinstance(status, Mapping):
            continue
        if status["status"] != "outdated":
            continue
        if status["source_kind"] in {"public_binance_data", "live_collection"}:
            task = _task_for_status(status, outdated=True)
            task["reason"] = f"older_than_{max_age_days}_days"
            tasks.append(task)
    return tasks


def build_backtest_start_data_gate(local_root: str | Path, reference_date: date | str | None = None) -> dict[str, object]:
    """Return the data gate model used by a future UI backtest-start button."""

    return build_data_readiness_report(local_root, reference_date)


def _status_for(requirement: Mapping[str, object], available_days: int, stale: bool) -> str:
    if requirement["source_kind"] == "config_model":
        return "current"
    if available_days == 0:
        if requirement.get("live_collected") or requirement.get("diagnostic_until_minimum_history"):
            return "diagnostic_only"
        return "missing" if requirement.get("publicly_downloadable") else "optional_missing"
    minimum = int(requirement.get("minimum_days") or 0)
    required_days = requirement.get("required_days")
    required_count = int(required_days or minimum or 0)
    if stale and requirement.get("publicly_downloadable"):
        return "outdated"
    if requirement.get("live_collected") and available_days < minimum:
        return "diagnostic_only"
    if requirement.get("diagnostic_until_minimum_history") and available_days < minimum:
        return "diagnostic_only"
    if required_count and available_days < required_count:
        return "partial"
    return "current"


def _included_in_backtest(requirement: Mapping[str, object], available_days: int, status: str) -> bool:
    if status != "current":
        return False
    if requirement.get("live_collected") and available_days < int(requirement.get("minimum_days") or 0):
        return False
    if requirement.get("diagnostic_until_minimum_history") and available_days < int(requirement.get("minimum_days") or 0):
        return False
    return bool(requirement.get("included_by_default"))


def _diagnostic_only(requirement: Mapping[str, object], available_days: int, status: str) -> bool:
    if status == "diagnostic_only":
        return True
    return bool(requirement.get("live_collected") and available_days < int(requirement.get("minimum_days") or 0))


def _reason_for(requirement: Mapping[str, object], status: str, available_days: int, latest_day: date | None) -> str:
    if status == "current":
        return "ready for its allowed role"
    if status == "outdated":
        return f"latest local day {latest_day.isoformat() if latest_day else 'unknown'} is older than 7 days"
    if status == "partial":
        return "insufficient complete local days for this source"
    if status == "diagnostic_only":
        return "minimum validated history not reached; diagnostic only"
    if status == "optional_missing":
        return "optional or future-enhancement source missing"
    if status == "missing":
        return "required local source missing"
    return "blocked"


def _available_days(requirement: Mapping[str, object], expected_path: Path) -> tuple[int, date | None]:
    if requirement["source_kind"] == "config_model":
        return 0, None
    if not expected_path.exists():
        return 0, None
    if requirement["source_kind"] == "public_binance_data":
        dates = sorted(_dates_from_complete_public_file_pairs(expected_path, str(requirement["symbol"])))
    else:
        dates = sorted(_dates_from_files(expected_path, str(requirement["symbol"])))
    return len(dates), dates[-1] if dates else None


def _dates_from_complete_public_file_pairs(path: Path, symbol: str) -> set[date]:
    """Return days that have a non-empty ZIP and matching non-empty CHECKSUM."""

    zip_days: dict[str, date] = {}
    checksum_bases = set()
    for file_path in path.iterdir() if path.exists() else []:
        if not _is_non_empty_final_file(file_path):
            continue
        name = file_path.name
        if name.endswith(".zip") and symbol in name:
            maybe_day = _extract_iso_day(name)
            if maybe_day is not None:
                zip_days[name] = maybe_day
        elif name.endswith(".zip.CHECKSUM") and symbol in name:
            checksum_bases.add(name[: -len(".CHECKSUM")])
    return {day for name, day in zip_days.items() if name in checksum_bases}


def _dates_from_files(path: Path, symbol: str) -> set[date]:
    dates = set()
    for file_path in path.iterdir() if path.exists() else []:
        if not _is_non_empty_final_file(file_path):
            continue
        maybe_day = _extract_iso_day(file_path.name)
        if maybe_day is not None and symbol in file_path.name:
            dates.add(maybe_day)
    return dates


def _is_non_empty_final_file(file_path: Path) -> bool:
    if not file_path.is_file():
        return False
    if file_path.name.endswith((".tmp", ".part")):
        return False
    return file_path.stat().st_size > 0


def _extract_iso_day(name: str) -> date | None:
    parts = name.replace("_", "-").split("-")
    for index in range(len(parts) - 2):
        token = "-".join(parts[index : index + 3])[:10]
        try:
            return date.fromisoformat(token)
        except ValueError:
            continue
    return None


def _expected_path(local_root: Path, requirement: Mapping[str, object]) -> Path:
    symbol = str(requirement["symbol"])
    data_type = str(requirement["data_type"])
    if data_type == "klines_1m":
        return local_root / "raw" / "binance" / "spot" / symbol / "klines" / "1m"
    if data_type == "aggTrades":
        return local_root / "raw" / "binance" / "spot" / symbol / "aggTrades"
    if data_type == "trades":
        return local_root / "raw" / "binance" / "spot" / symbol / "trades"
    if data_type == "bookTicker":
        return local_root / "raw" / "binance" / "spot" / symbol / "bookTicker"
    if data_type == "orderbook_snapshots":
        return local_root / "raw" / "binance" / "spot" / symbol / "orderbook_snapshots"
    if data_type == "exchange_info":
        return local_root / "raw" / "binance" / "spot" / symbol / "exchange_info"
    return local_root / "config" / data_type


def _task_for_status(status: Mapping[str, object], outdated: bool) -> dict[str, object]:
    prefix = "collect" if status["source_kind"] == "live_collection" else "download"
    requirement_id = str(status["requirement_id"])
    latest = status.get("latest_available_day")
    end_day = date.today() - timedelta(days=1)
    if latest is None:
        target_days = int(status.get("required_days") or status.get("minimum_days") or 1)
        start_date = (end_day - timedelta(days=target_days - 1)).isoformat()
    else:
        start_date = (date.fromisoformat(str(latest)) + timedelta(days=1)).isoformat()
    end_date = end_day.isoformat()
    reason = "update_required" if outdated else "missing_or_incomplete"
    if status["source_kind"] == "public_binance_data" and not status.get("implemented_downloader"):
        reason = "next_required_downloader"
    public_downloader_supported = requirement_id in SUPPORTED_PUBLIC_DOWNLOADER_REQUIREMENTS
    if public_downloader_supported:
        reason = "missing_or_incomplete" if not outdated else "update_required"
    return {
        "task_id": f"{prefix}_{requirement_id}",
        "requirement_id": requirement_id,
        "symbol": status["symbol"],
        "data_type": status["data_type"],
        "interval": status.get("interval"),
        "start_date": start_date,
        "end_date": end_date,
        "target_path": status["expected_path"],
        "source_kind": status["source_kind"],
        "execute_allowed": bool(status["source_kind"] == "public_binance_data" and public_downloader_supported),
        "reason": reason,
    }


def _reference_day(reference_date: date | str | None) -> date:
    if reference_date is None:
        return date.today()
    return _parse_date(reference_date)


def _parse_date(value: date | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _assert_no_forbidden_fields(result: dict[str, object]) -> dict[str, object]:
    if FORBIDDEN_RESULT_FIELDS & set(result):
        raise ValueError("readiness result contains forbidden result fields")
    return result
