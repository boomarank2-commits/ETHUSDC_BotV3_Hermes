"""Public Binance ETHUSDC 1m kline downloader.

This module uses Binance public data URLs only. It does not use API keys, call
private/trading APIs, place orders, run strategies, execute backtests, start UI
code, or unlock live/paper/testtrade.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

from ethusdc_bot.validation import SchemaValidationError


PUBLIC_DATA_BASE = "https://data.binance.vision/data/spot"
SYMBOL = "ETHUSDC"
INTERVAL = "1m"
QUOTE_ASSET = "USDC"
DEFAULT_RAW_ROOT = Path("C:/TradingBot/data/ETHUSDC_BotV3_Hermes")
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


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
}


def build_monthly_kline_url(symbol: str, interval: str, year: int, month: int) -> str:
    """Build a Binance public monthly kline ZIP URL."""

    _validate_symbol_interval(symbol, interval)
    if not isinstance(year, int) or not isinstance(month, int) or not 1 <= month <= 12:
        raise SchemaValidationError("year/month must be valid integers")
    return (
        f"{PUBLIC_DATA_BASE}/monthly/klines/{symbol}/{interval}/"
        f"{symbol}-{interval}-{year:04d}-{month:02d}.zip"
    )


def build_daily_kline_url(symbol: str, interval: str, day: str | date) -> str:
    """Build a Binance public daily kline ZIP URL."""

    _validate_symbol_interval(symbol, interval)
    parsed_day = _parse_date(day)
    return (
        f"{PUBLIC_DATA_BASE}/daily/klines/{symbol}/{interval}/"
        f"{symbol}-{interval}-{parsed_day.isoformat()}.zip"
    )


def build_checksum_url(zip_url: str) -> str:
    """Build the public CHECKSUM URL for a Binance public data ZIP URL."""

    return f"{zip_url}.CHECKSUM"


def planned_months_for_range(start_date: str | date, end_date: str | date) -> list[tuple[int, int]]:
    """Return inclusive (year, month) tuples touched by a date range."""

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    _validate_date_range(start, end)
    months: list[tuple[int, int]] = []
    current = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while current <= last:
        months.append((current.year, current.month))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def planned_days_for_range(start_date: str | date, end_date: str | date) -> list[date]:
    """Return inclusive UTC days in a date range."""

    start = _parse_date(start_date)
    end = _parse_date(end_date)
    _validate_date_range(start, end)
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def download_file(url: str, target_path: str | Path, execute: bool) -> dict[str, str]:
    """Download a public file only when execute is true.

    Existing files are never overwritten.
    """

    target = Path(target_path)
    if target.exists():
        return {"url": url, "target_path": str(target), "status": "skipped_existing"}
    if not execute:
        return {"url": url, "target_path": str(target), "status": "planned"}

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, str(target))
    except Exception as exc:  # pragma: no cover - exact network errors vary
        if target.exists():
            target.unlink()
        return {
            "url": url,
            "target_path": str(target),
            "status": "error",
            "error": str(exc),
        }
    return {"url": url, "target_path": str(target), "status": "downloaded"}


def download_checksum_if_available(
    url: str, target_path: str | Path, execute: bool
) -> dict[str, str]:
    """Download the optional public CHECKSUM file when available."""

    checksum_url = build_checksum_url(url)
    checksum_path = Path(f"{target_path}.CHECKSUM")
    if checksum_path.exists():
        return {
            "url": checksum_url,
            "target_path": str(checksum_path),
            "status": "skipped_existing",
        }
    if not execute:
        return {
            "url": checksum_url,
            "target_path": str(checksum_path),
            "status": "planned",
        }

    checksum_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(checksum_url, str(checksum_path))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "url": checksum_url,
                "target_path": str(checksum_path),
                "status": "not_available",
            }
        return {
            "url": checksum_url,
            "target_path": str(checksum_path),
            "status": "error",
            "error": str(exc),
        }
    except urllib.error.URLError as exc:
        return {
            "url": checksum_url,
            "target_path": str(checksum_path),
            "status": "error",
            "error": str(exc),
        }
    return {
        "url": checksum_url,
        "target_path": str(checksum_path),
        "status": "downloaded",
    }


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def verify_checksum_file(zip_path: str | Path, checksum_path: str | Path) -> dict[str, str | bool]:
    """Verify a ZIP file against a Binance SHA256 CHECKSUM file."""

    zip_file = Path(zip_path)
    checksum_file = Path(checksum_path)
    if not zip_file.is_file() or not checksum_file.is_file():
        return {"status": "missing", "verified": False}
    try:
        tokens = checksum_file.read_text(encoding="utf-8").strip().split()
    except (OSError, UnicodeError):
        return {"status": "malformed", "verified": False}
    if not tokens or len(tokens) > 2 or not _SHA256_RE.fullmatch(tokens[0]):
        return {"status": "malformed", "verified": False}
    if len(tokens) == 2 and Path(tokens[1].lstrip("*")).name != zip_file.name:
        return {"status": "malformed", "verified": False}
    expected = tokens[0].lower()
    hasher = hashlib.sha256()
    try:
        with zip_file.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError:
        return {"status": "unreadable", "verified": False}
    digest = hasher.hexdigest()
    return {
        "status": "verified" if digest == expected else "mismatch",
        "verified": digest == expected,
        "expected_sha256": expected,
        "actual_sha256": digest,
    }


def plan_ethusdc_1m_download(
    start_date: str | date, end_date: str | date, raw_root: str | Path
) -> dict[str, object]:
    """Plan public daily ETHUSDC 1m spot kline ZIP downloads."""

    target_dir = _target_dir(raw_root)
    _reject_repository_path(target_dir)
    downloads = []
    for day in planned_days_for_range(start_date, end_date):
        url = build_daily_kline_url(SYMBOL, INTERVAL, day)
        filename = f"{SYMBOL}-{INTERVAL}-{day.isoformat()}.zip"
        downloads.append(
            {
                "symbol": SYMBOL,
                "interval": INTERVAL,
                "market_type": "spot",
                "quote_asset": QUOTE_ASSET,
                "date": day.isoformat(),
                "url": url,
                "checksum_url": build_checksum_url(url),
                "target_path": str(target_dir / filename),
            }
        )
    return {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "market_type": "spot",
        "quote_asset": QUOTE_ASSET,
        "raw_root": str(Path(raw_root)),
        "target_dir": str(target_dir),
        "start_date": _parse_date(start_date).isoformat(),
        "end_date": _parse_date(end_date).isoformat(),
        "downloads": downloads,
    }


def plan_ethusdc_1m_download_for_last_days(
    last_days: int, raw_root: str | Path, today: date | None = None
) -> dict[str, object]:
    """Plan the last N UTC days of public ETHUSDC 1m spot kline downloads."""

    if not isinstance(last_days, int) or last_days <= 0:
        raise SchemaValidationError("last_days must be a positive integer")
    anchor = today or date.today()
    start = anchor - timedelta(days=last_days - 1)
    return plan_ethusdc_1m_download(start, anchor, raw_root)


def build_download_manifest(
    plan: dict[str, object], file_results: Sequence[dict[str, str]]
) -> dict[str, object]:
    """Build an honest manifest for a download target without audit claims."""

    files = [
        {
            "path": result["target_path"],
            "url": result["url"],
            "status": result["status"],
        }
        for result in file_results
        if result.get("target_path", "").endswith(".zip")
    ]
    downloaded_any = any(entry["status"] in {"downloaded", "skipped_existing"} for entry in files)
    manifest = {
        "schema_version": 1,
        "template": False,
        "source_id": "ethusdc_1m_klines",
        "symbol": SYMBOL,
        "role": "primary_trading_symbol",
        "data_type": "klines",
        "interval_seconds": 60,
        "exchange": "binance",
        "market_type": "spot",
        "quote_asset": QUOTE_ASSET,
        "raw_root": str(plan["raw_root"]),
        "expected_path": str(plan["target_dir"]),
        "files": files,
        "download_status": "downloaded" if downloaded_any else "not_downloaded",
        "audit_status": "not_audited",
        "quality_status": "unknown",
        "observed_start_utc": None,
        "observed_end_utc": None,
        "observed_rows": 0,
        "complete_utc_days": 0,
        "missing_utc_days": [],
        "duplicate_rows": 0,
        "gap_count": 0,
        "max_gap_seconds": 0,
        "checksum_status": "not_checked",
        "notes": "Public ZIP download manifest only; no kline contents audited.",
    }
    if FORBIDDEN_RESULT_FIELDS & set(manifest.keys()):
        raise SchemaValidationError("manifest contains forbidden result fields")
    return manifest


def run_downloader(argv: Sequence[str] | None = None) -> int:
    """Run the public ETHUSDC 1m downloader CLI."""

    parser = argparse.ArgumentParser(description="Download public ETHUSDC 1m kline ZIP files.")
    parser.add_argument("--symbol", default=SYMBOL)
    parser.add_argument("--interval", default=INTERVAL)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--last-days", type=int)
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    _validate_symbol_interval(args.symbol, args.interval)
    if args.last_days is not None:
        plan = plan_ethusdc_1m_download_for_last_days(args.last_days, args.raw_root)
    else:
        if not args.start or not args.end:
            raise SchemaValidationError("--start and --end are required unless --last-days is used")
        plan = plan_ethusdc_1m_download(args.start, args.end, args.raw_root)

    results: list[dict[str, str]] = []
    checksum_results: list[dict[str, str]] = []
    for item in plan["downloads"]:  # type: ignore[index]
        result = download_file(str(item["url"]), item["target_path"], args.execute)  # type: ignore[index]
        results.append(result)
        checksum_results.append(
            download_checksum_if_available(str(item["url"]), item["target_path"], args.execute)  # type: ignore[index]
        )

    if args.execute:
        manifest = build_download_manifest(plan, results)
        manifest_path = Path(str(plan["target_dir"])) / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    summary = {
        "execute": args.execute,
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "market_type": "spot",
        "target_dir": plan["target_dir"],
        "planned_files": len(plan["downloads"]),
        "results": results,
        "checksum_results": checksum_results,
        "safety": "public data only; no API key; no orders; no backtest; no UI; live/paper/testtrade locked",
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _validate_symbol_interval(symbol: str, interval: str) -> None:
    if symbol != SYMBOL:
        raise SchemaValidationError("only ETHUSDC public kline downloads are allowed")
    if interval != INTERVAL:
        raise SchemaValidationError("only 1m public kline downloads are allowed")


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise SchemaValidationError("date must be ISO yyyy-mm-dd")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SchemaValidationError("date must be ISO yyyy-mm-dd") from exc


def _validate_date_range(start: date, end: date) -> None:
    if end < start:
        raise SchemaValidationError("end date must be on or after start date")


def _target_dir(raw_root: str | Path) -> Path:
    return Path(raw_root) / "raw" / "binance" / "spot" / SYMBOL / "klines" / INTERVAL


def _reject_repository_path(path: str | Path) -> None:
    repo_text = str(REPOSITORY_ROOT).replace("\\", "/").rstrip("/").lower()
    path_text = str(path).replace("\\", "/").rstrip("/").lower()
    if path_text == repo_text or path_text.startswith(repo_text + "/"):
        raise SchemaValidationError("download target must be outside the repository")

    try:
        Path(path).resolve().relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        return
    except (OSError, RuntimeError):
        return
    raise SchemaValidationError("download target must be outside the repository")


if __name__ == "__main__":
    raise SystemExit(run_downloader())
