"""Local ETHUSDC 1m kline ZIP audit helpers.

This module audits already-downloaded Binance public data ZIP files only. It does
not download data, call Binance APIs, create raw-data folders, run backtests,
produce reports, emit profit/trade/candidate fields, or unlock live/paper/testtrade.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import zipfile

from ethusdc_bot.validation import SchemaValidationError

SYMBOL = "ETHUSDC"
INTERVAL = "1m"
EXPECTED_INTERVAL_SECONDS = 60
ROWS_PER_COMPLETE_UTC_DAY = 1440
DEFAULT_ALLOWED_RAW_ROOT = Path("C:/TradingBot/data/ETHUSDC_BotV3_Hermes")
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


def find_kline_zip_files(download_dir: str | Path) -> list[Path]:
    """Return local ETHUSDC 1m ZIP files from an approved raw-data directory."""

    directory = _validate_allowed_path(download_dir)
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.name.endswith(".zip") and _looks_like_ethusdc_1m_zip(path)
    )


def find_checksum_files(download_dir: str | Path) -> list[Path]:
    """Return local CHECKSUM files from an approved raw-data directory."""

    directory = _validate_allowed_path(download_dir)
    if not directory.exists():
        return []
    return sorted(path for path in directory.iterdir() if path.is_file() and path.name.endswith(".CHECKSUM"))


def parse_kline_open_time_from_row(row: Sequence[str]) -> int:
    """Parse the Binance kline open_time milliseconds from a CSV row."""

    if not row:
        raise SchemaValidationError("kline row is empty")
    try:
        value = int(row[0])
    except (TypeError, ValueError) as exc:
        raise SchemaValidationError("kline open_time must be integer milliseconds") from exc
    if value > 9_999_999_999_999:
        value //= 1000
    return value


def audit_ethusdc_1m_zip_file(zip_path: str | Path) -> dict[str, object]:
    """Audit one ETHUSDC 1m kline ZIP file without creating side effects."""

    path = _validate_allowed_path(zip_path)
    result = _empty_file_result(path)
    if not _looks_like_ethusdc_1m_zip(path):
        result.update({"audit_status": "blocked", "error": "zip filename must match ETHUSDC-1m-*.zip"})
        return _assert_no_forbidden_fields(result)
    if not path.exists():
        result.update({"audit_status": "blocked", "error": "zip file missing"})
        return _assert_no_forbidden_fields(result)

    open_times: list[int] = []
    try:
        with zipfile.ZipFile(path) as archive:
            csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
            if len(csv_names) != 1:
                result.update({"audit_status": "blocked", "error": "zip must contain exactly one CSV file"})
                return _assert_no_forbidden_fields(result)
            inner_name = csv_names[0]
            if SYMBOL not in Path(inner_name).name or INTERVAL not in Path(inner_name).name:
                result.update({"audit_status": "blocked", "error": "CSV path must identify ETHUSDC 1m klines"})
                return _assert_no_forbidden_fields(result)
            with archive.open(inner_name) as raw_file:
                text_file = (line.decode("utf-8") for line in raw_file)
                reader = csv.reader(text_file)
                for row in reader:
                    if not row:
                        continue
                    open_times.append(parse_kline_open_time_from_row(row))
    except zipfile.BadZipFile as exc:
        result.update({"audit_status": "blocked", "error": f"bad zip file: {exc}"})
        return _assert_no_forbidden_fields(result)
    except (UnicodeDecodeError, SchemaValidationError) as exc:
        result.update({"audit_status": "blocked", "error": str(exc)})
        return _assert_no_forbidden_fields(result)

    metrics = _build_time_metrics(open_times)
    result.update(metrics)
    result["audit_status"] = "not_audited" if not open_times else _status_from_metrics(metrics)
    result["backtest_ready"] = False
    return _assert_no_forbidden_fields(result)


def audit_ethusdc_1m_zip_directory(download_dir: str | Path) -> dict[str, object]:
    """Audit all local ETHUSDC 1m ZIP files in one download directory."""

    directory = _validate_allowed_path(download_dir)
    zip_files = find_kline_zip_files(directory)
    checksum_files = find_checksum_files(directory)
    file_results = [audit_ethusdc_1m_zip_file(path) for path in zip_files]
    return _build_directory_summary(directory, zip_files, checksum_files, file_results, required_utc_days=None)


def build_kline_audit_summary(download_dir: str | Path, required_utc_days: int = 1095) -> dict[str, object]:
    """Build the UI-facing data audit summary for the ETHUSDC 1m ZIP directory."""

    if not isinstance(required_utc_days, int) or required_utc_days <= 0:
        raise SchemaValidationError("required_utc_days must be a positive integer")
    directory = _validate_allowed_path(download_dir)
    zip_files = find_kline_zip_files(directory)
    checksum_files = find_checksum_files(directory)
    file_results = [audit_ethusdc_1m_zip_file(path) for path in zip_files]
    return _build_directory_summary(directory, zip_files, checksum_files, file_results, required_utc_days)


def _build_directory_summary(
    directory: Path,
    zip_files: Sequence[Path],
    checksum_files: Sequence[Path],
    file_results: Sequence[dict[str, object]],
    required_utc_days: int | None,
) -> dict[str, object]:
    open_times: list[int] = []
    blocked_files = 0
    for file_result in file_results:
        if file_result["audit_status"] == "blocked":
            blocked_files += 1
        open_times.extend(int(value) for value in file_result.get("open_times", []))

    metrics = _build_time_metrics(open_times)
    complete_days = list(metrics["complete_utc_day_values"])
    missing_days = _missing_days_from_observation(complete_days, required_utc_days)
    has_required_days = required_utc_days is None or len(complete_days) >= required_utc_days
    clean = (
        blocked_files == 0
        and metrics["observed_rows"] > 0
        and metrics["duplicate_rows"] == 0
        and metrics["gap_count"] == 0
        and metrics["unsorted_rows"] == 0
        and has_required_days
        and not missing_days
    )
    audit_status = "usable_for_backtest_candidate" if clean else "incomplete"
    if blocked_files:
        audit_status = "blocked"
    elif not zip_files:
        audit_status = "not_audited"

    summary = {
        "schema_version": 1,
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "download_dir": str(directory),
        "zip_count": len(zip_files),
        "checksum_count": len(checksum_files),
        "audit_status": audit_status,
        "observed_start_utc": metrics["observed_start_utc"],
        "observed_end_utc": metrics["observed_end_utc"],
        "observed_rows": metrics["observed_rows"],
        "complete_utc_days": len(complete_days),
        "missing_utc_days": missing_days,
        "missing_utc_days_count": len(missing_days),
        "duplicate_rows": metrics["duplicate_rows"],
        "gap_count": metrics["gap_count"],
        "max_gap_seconds": metrics["max_gap_seconds"],
        "unsorted_rows": metrics["unsorted_rows"],
        "blocked_files": blocked_files,
        "backtest_ready": clean,
        "files": [_public_file_result(file_result) for file_result in file_results],
        "safety_note": "Local audit only; no download; no Binance API; no backtest; live/paper/testtrade locked.",
    }
    return _assert_no_forbidden_fields(summary)


def _empty_file_result(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "audit_status": "not_audited",
        "observed_start_utc": None,
        "observed_end_utc": None,
        "observed_rows": 0,
        "complete_utc_days": 0,
        "duplicate_rows": 0,
        "gap_count": 0,
        "max_gap_seconds": 0,
        "unsorted_rows": 0,
        "backtest_ready": False,
        "error": "",
        "open_times": [],
    }


def _build_time_metrics(open_times: Sequence[int]) -> dict[str, object]:
    if not open_times:
        return {
            "observed_start_utc": None,
            "observed_end_utc": None,
            "observed_rows": 0,
            "complete_utc_days": 0,
            "complete_utc_day_values": [],
            "duplicate_rows": 0,
            "gap_count": 0,
            "max_gap_seconds": 0,
            "unsorted_rows": 0,
            "open_times": [],
        }

    duplicates = sum(count - 1 for count in Counter(open_times).values() if count > 1)
    unsorted_rows = sum(1 for previous, current in zip(open_times, open_times[1:]) if current <= previous)
    unique_sorted = sorted(set(open_times))
    gap_seconds = [
        int((current - previous) / 1000)
        for previous, current in zip(unique_sorted, unique_sorted[1:])
        if current - previous != EXPECTED_INTERVAL_SECONDS * 1000
    ]
    complete_days = _complete_days(unique_sorted)
    return {
        "observed_start_utc": _format_utc_ms(unique_sorted[0]),
        "observed_end_utc": _format_utc_ms(unique_sorted[-1]),
        "observed_rows": len(open_times),
        "complete_utc_days": len(complete_days),
        "complete_utc_day_values": complete_days,
        "duplicate_rows": duplicates,
        "gap_count": len(gap_seconds),
        "max_gap_seconds": max(gap_seconds) if gap_seconds else 0,
        "unsorted_rows": unsorted_rows,
        "open_times": list(open_times),
    }


def _complete_days(unique_sorted_open_times: Iterable[int]) -> list[date]:
    by_day: dict[date, list[int]] = defaultdict(list)
    for open_time_ms in unique_sorted_open_times:
        dt = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
        by_day[dt.date()].append(open_time_ms)

    complete = []
    for day, values in sorted(by_day.items()):
        day_start = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp() * 1000)
        expected = [day_start + minute * 60_000 for minute in range(ROWS_PER_COMPLETE_UTC_DAY)]
        if values == expected:
            complete.append(day)
    return complete


def _missing_days_from_observation(complete_days: Sequence[date], required_utc_days: int | None) -> list[str]:
    if required_utc_days is None or not complete_days:
        return []
    first_day = min(complete_days)
    required = [first_day + timedelta(days=offset) for offset in range(required_utc_days)]
    complete_set = set(complete_days)
    return [day.isoformat() for day in required if day not in complete_set]


def _status_from_metrics(metrics: dict[str, object]) -> str:
    if (
        metrics["duplicate_rows"] == 0
        and metrics["gap_count"] == 0
        and metrics["unsorted_rows"] == 0
        and metrics["complete_utc_days"]
    ):
        return "usable_for_backtest_candidate"
    return "incomplete"


def _public_file_result(file_result: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in file_result.items() if key != "open_times"}


def _looks_like_ethusdc_1m_zip(path: Path) -> bool:
    return path.name.startswith(f"{SYMBOL}-{INTERVAL}-") and path.name.endswith(".zip")


def _validate_allowed_path(path: str | Path) -> Path:
    candidate = Path(path)
    allowed = DEFAULT_ALLOWED_RAW_ROOT
    try:
        candidate.resolve().relative_to(allowed.resolve())
    except ValueError as exc:
        raise SchemaValidationError(
            f"audit path must be under approved local raw-data root: {allowed}"
        ) from exc
    except (OSError, RuntimeError):
        candidate_text = str(candidate).replace("\\", "/").lower()
        allowed_text = str(allowed).replace("\\", "/").rstrip("/").lower()
        if not (candidate_text == allowed_text or candidate_text.startswith(allowed_text + "/")):
            raise SchemaValidationError(
                f"audit path must be under approved local raw-data root: {allowed}"
            )
    return candidate


def _format_utc_ms(open_time_ms: int) -> str:
    return datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _assert_no_forbidden_fields(result: dict[str, object]) -> dict[str, object]:
    if FORBIDDEN_RESULT_FIELDS & set(result):
        raise SchemaValidationError("audit result contains forbidden result fields")
    return result
