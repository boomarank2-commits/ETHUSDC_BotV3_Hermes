"""Public Binance data downloader for readiness tasks.

Supports only public Binance data endpoints needed by the readiness gate. It does
not use API keys, call private/trading APIs, place orders, run strategies,
execute backtests, create reports, create profit/trade/candidate fields, or
unlock live/paper/testtrade.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
import json
from pathlib import Path
import urllib.error
import urllib.request

from ethusdc_bot.data_pipeline.data_readiness import build_data_readiness_report
from ethusdc_bot.data_pipeline.public_kline_downloader import DEFAULT_RAW_ROOT
from ethusdc_bot.validation import SchemaValidationError

PUBLIC_DATA_BASE = "https://data.binance.vision/data/spot"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SUPPORTED_SYMBOLS = {"ETHUSDC", "BTCUSDC", "ETHBTC"}
SUPPORTED_PUBLIC_TYPES = {"klines", "klines_1m", "aggTrades", "trades"}
CONTEXT_SYMBOLS = {"BTCUSDC", "ETHBTC"}
TRADE_SYMBOL = "ETHUSDC"
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


ProgressCallback = Callable[[dict[str, object]], None]


def build_public_data_url(
    symbol: str,
    data_type: str,
    interval: str | None,
    day_or_month: str | date,
    frequency: str,
) -> str:
    """Build a Binance public data ZIP URL for supported spot data."""

    normalized_type = _normalize_data_type(data_type)
    _validate_symbol_data_type(symbol, normalized_type, interval)
    if frequency not in {"daily", "monthly"}:
        raise SchemaValidationError("frequency must be daily or monthly")
    token = _format_day_or_month(day_or_month, frequency)
    if normalized_type == "klines":
        if interval != "1m":
            raise SchemaValidationError("only 1m klines are supported")
        return (
            f"{PUBLIC_DATA_BASE}/{frequency}/klines/{symbol}/{interval}/"
            f"{symbol}-{interval}-{token}.zip"
        )
    return f"{PUBLIC_DATA_BASE}/{frequency}/{normalized_type}/{symbol}/{symbol}-{normalized_type}-{token}.zip"


def build_public_checksum_url(zip_url: str) -> str:
    """Build CHECKSUM URL for a Binance public data ZIP URL."""

    return f"{zip_url}.CHECKSUM"


def plan_public_download_task(task: Mapping[str, object]) -> dict[str, object]:
    """Plan one readiness/public download task without network or file writes."""

    symbol = str(task["symbol"])
    data_type = _normalize_data_type(str(task["data_type"]))
    interval = task.get("interval")
    interval_text = str(interval) if interval is not None else None
    _validate_symbol_data_type(symbol, data_type, interval_text)
    target_dir = Path(str(task["target_path"]))
    _reject_repository_path(target_dir)
    start = _parse_date(task.get("start_date") or task.get("end_date") or date.today().isoformat())
    end = _parse_date(task.get("end_date") or start.isoformat())
    if end < start:
        raise SchemaValidationError("end_date must be on or after start_date")

    downloads = []
    current = start
    while current <= end:
        url = build_public_data_url(symbol, data_type, interval_text, current, "daily")
        filename = url.rsplit("/", 1)[1]
        downloads.append(
            {
                "symbol": symbol,
                "data_type": data_type,
                "interval": interval_text,
                "date": current.isoformat(),
                "url": url,
                "checksum_url": build_public_checksum_url(url),
                "target_path": str(target_dir / filename),
            }
        )
        current += timedelta(days=1)

    plan = {
        "task_id": task.get("task_id", f"download_{symbol.lower()}_{data_type}"),
        "requirement_id": task.get("requirement_id"),
        "symbol": symbol,
        "data_type": data_type,
        "interval": interval_text,
        "role": _role_for(symbol, data_type),
        "context_only": symbol in CONTEXT_SYMBOLS,
        "trade_market": symbol == TRADE_SYMBOL and data_type == "klines",
        "may_trigger_orders": symbol == TRADE_SYMBOL and data_type == "klines",
        "source_kind": "public_binance_data",
        "target_dir": str(target_dir),
        "downloads": downloads,
        "safety": "public data only; no API key; no orders; no strategy; no backtest; live/paper/testtrade locked",
    }
    return _assert_no_forbidden_fields(plan)


def execute_public_download_task(
    task: Mapping[str, object],
    execute: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, object]:
    """Execute or dry-run one public download task."""

    plan = plan_public_download_task(task)
    file_results = []
    checksum_results = []
    counters = {"completed": 0, "skipped": 0, "downloaded": 0, "failed": 0}
    planned_file_count = len(plan["downloads"]) * 2  # type: ignore[arg-type]
    current_file_index = 0
    for item in plan["downloads"]:  # type: ignore[index]
        current_file_index += 1
        file_results.append(
            _download_file_with_progress(
                str(item["url"]),
                item["target_path"],
                execute,
                plan=plan,
                progress_callback=progress_callback,
                planned_file_count=planned_file_count,
                current_file_index=current_file_index,
                counters=counters,
            )
        )  # type: ignore[index]
        current_file_index += 1
        checksum_results.append(
            _download_file_with_progress(
                str(item["checksum_url"]),
                f"{item['target_path']}.CHECKSUM",
                execute,
                plan=plan,
                progress_callback=progress_callback,
                planned_file_count=planned_file_count,
                current_file_index=current_file_index,
                counters=counters,
            )
        )  # type: ignore[index]
    result = {
        "task_id": plan["task_id"],
        "requirement_id": plan["requirement_id"],
        "symbol": plan["symbol"],
        "data_type": plan["data_type"],
        "interval": plan["interval"],
        "role": plan["role"],
        "context_only": plan["context_only"],
        "trade_market": plan["trade_market"],
        "may_trigger_orders": plan["may_trigger_orders"],
        "execute": execute,
        "planned_files": len(plan["downloads"]),
        "planned_file_count": planned_file_count,
        "completed_file_count": counters["completed"],
        "skipped_file_count": counters["skipped"],
        "downloaded_file_count": counters["downloaded"],
        "failed_file_count": counters["failed"],
        "file_results": file_results,
        "checksum_results": checksum_results,
        "safety": plan["safety"],
    }
    return _assert_no_forbidden_fields(result)


def execute_readiness_download_tasks(readiness_report: Mapping[str, object], execute: bool = False) -> dict[str, object]:
    """Execute/dry-run supported public download tasks from a readiness report."""

    source_tasks = list(readiness_report.get("missing_download_tasks", [])) + list(
        readiness_report.get("outdated_download_tasks", [])
    )
    task_results = []
    skipped_tasks = []
    for task in source_tasks:
        if not isinstance(task, Mapping):
            continue
        if task.get("source_kind") != "public_binance_data":
            skipped_tasks.append({"task_id": task.get("task_id"), "reason": "not_public_download"})
            continue
        if _normalize_data_type(str(task.get("data_type"))) not in SUPPORTED_PUBLIC_TYPES:
            skipped_tasks.append({"task_id": task.get("task_id"), "reason": "unsupported_public_data_type"})
            continue
        task_results.append(execute_public_download_task(task, execute=execute))
    result = {
        "execute": execute,
        "task_results": task_results,
        "skipped_tasks": skipped_tasks,
        "safety": "public data readiness downloads only; no API key; no orders; no backtest",
    }
    return _assert_no_forbidden_fields(result)


def run_public_data_downloader(argv: Sequence[str] | None = None) -> int:
    """Run the public data downloader CLI."""

    parser = argparse.ArgumentParser(description="Plan or execute Binance public data downloads for readiness.")
    parser.add_argument("--from-readiness", action="store_true")
    parser.add_argument("--symbol")
    parser.add_argument("--data-type")
    parser.add_argument("--interval")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--last-days", type=int)
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    if args.from_readiness:
        report = build_data_readiness_report(args.raw_root)
        result = execute_readiness_download_tasks(report, execute=args.execute)
    else:
        if not args.symbol or not args.data_type:
            raise SchemaValidationError("--symbol and --data-type are required unless --from-readiness is used")
        end = _parse_date(args.end) if args.end else date.today()
        if args.last_days is not None:
            if args.last_days <= 0:
                raise SchemaValidationError("--last-days must be positive")
            start = end - timedelta(days=args.last_days - 1)
        else:
            if not args.start:
                raise SchemaValidationError("--start or --last-days is required")
            start = _parse_date(args.start)
        task = {
            "task_id": f"download_{args.symbol.lower()}_{_normalize_data_type(args.data_type)}",
            "requirement_id": f"{args.symbol.lower()}_{_normalize_data_type(args.data_type)}",
            "symbol": args.symbol,
            "data_type": args.data_type,
            "interval": args.interval,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "target_path": str(_target_dir(args.raw_root, args.symbol, _normalize_data_type(args.data_type), args.interval)),
            "source_kind": "public_binance_data",
            "execute_allowed": True,
        }
        result = {
            "execute": args.execute,
            "task_results": [execute_public_download_task(task, execute=args.execute)],
            "skipped_tasks": [],
            "safety": "public data only; no API key; no orders; no backtest; live/paper/testtrade locked",
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _download_file_with_progress(
    url: str,
    target_path: str | Path,
    execute: bool,
    *,
    plan: Mapping[str, object],
    progress_callback: ProgressCallback | None,
    planned_file_count: int,
    current_file_index: int,
    counters: dict[str, int],
) -> dict[str, str]:
    target = Path(target_path)
    base = {
        "task_id": plan["task_id"],
        "symbol": plan["symbol"],
        "data_type": plan["data_type"],
        "phase": "file_progress",
        "planned_file_count": planned_file_count,
        "current_file_index": current_file_index,
        "current_file_name": target.name,
        "target_path": str(target),
    }
    if target.exists():
        counters["completed"] += 1
        counters["skipped"] += 1
        _emit_progress(progress_callback, base, counters, "skipped_existing", f"Skipped existing file: {target.name}")
        return {"url": url, "target_path": str(target), "status": "skipped_existing"}
    if not execute:
        counters["completed"] += 1
        _emit_progress(progress_callback, base, counters, "planned", f"Planned file only (dry-run): {target.name}")
        return {"url": url, "target_path": str(target), "status": "planned"}
    _emit_progress(progress_callback, base, counters, "downloading", f"Downloading file: {target.name}")
    result = _download_file(url, target, execute=True)
    counters["completed"] += 1
    if result["status"] == "downloaded":
        counters["downloaded"] += 1
        event_status = "downloaded"
    elif result["status"] == "skipped_existing":
        counters["skipped"] += 1
        event_status = "skipped_existing"
    else:
        counters["failed"] += 1
        event_status = "failed"
    _emit_progress(
        progress_callback,
        base,
        counters,
        event_status,
        f"{event_status}: {target.name}",
        error=result.get("error"),
    )
    return result


def _emit_progress(
    progress_callback: ProgressCallback | None,
    base: Mapping[str, object],
    counters: Mapping[str, int],
    status: str,
    message: str,
    error: str | None = None,
) -> None:
    if progress_callback is None:
        return
    event = {
        **dict(base),
        "status": status,
        "completed_file_count": counters["completed"],
        "skipped_file_count": counters["skipped"],
        "downloaded_file_count": counters["downloaded"],
        "failed_file_count": counters["failed"],
        "message": message,
    }
    if error:
        event["error"] = error
    progress_callback(event)


def _download_file(url: str, target_path: str | Path, execute: bool) -> dict[str, str]:
    target = Path(target_path)
    if target.exists():
        return {"url": url, "target_path": str(target), "status": "skipped_existing"}
    if not execute:
        return {"url": url, "target_path": str(target), "status": "planned"}
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(url, str(target))
    except urllib.error.HTTPError as exc:
        if target.exists():
            target.unlink()
        if exc.code == 404:
            return {"url": url, "target_path": str(target), "status": "not_available"}
        return {"url": url, "target_path": str(target), "status": "error", "error": str(exc)}
    except Exception as exc:  # pragma: no cover - exact network errors vary
        if target.exists():
            target.unlink()
        return {"url": url, "target_path": str(target), "status": "error", "error": str(exc)}
    return {"url": url, "target_path": str(target), "status": "downloaded"}


def _target_dir(raw_root: str | Path, symbol: str, data_type: str, interval: str | None) -> Path:
    normalized_type = _normalize_data_type(data_type)
    if normalized_type == "klines":
        return Path(raw_root) / "raw" / "binance" / "spot" / symbol / "klines" / str(interval)
    return Path(raw_root) / "raw" / "binance" / "spot" / symbol / normalized_type


def _validate_symbol_data_type(symbol: str, data_type: str, interval: str | None) -> None:
    if symbol not in SUPPORTED_SYMBOLS:
        raise SchemaValidationError("only ETHUSDC, BTCUSDC, and ETHBTC public data are supported")
    if data_type not in SUPPORTED_PUBLIC_TYPES:
        raise SchemaValidationError("unsupported public data type")
    if data_type in {"aggTrades", "trades"} and symbol != "ETHUSDC":
        raise SchemaValidationError("aggTrades/trades are only supported for ETHUSDC")
    if data_type == "klines" and interval != "1m":
        raise SchemaValidationError("only 1m klines are supported")


def _normalize_data_type(data_type: str) -> str:
    if data_type == "klines_1m":
        return "klines"
    return data_type


def _role_for(symbol: str, data_type: str) -> str:
    if symbol in CONTEXT_SYMBOLS:
        return "market_context"
    if symbol == TRADE_SYMBOL and data_type == "klines":
        return "trade_market"
    return "microstructure_tradeflow"


def _format_day_or_month(day_or_month: str | date, frequency: str) -> str:
    if isinstance(day_or_month, date):
        parsed = day_or_month
    else:
        text = str(day_or_month)
        parsed = date.fromisoformat(text + "-01") if frequency == "monthly" and len(text) == 7 else date.fromisoformat(text)
    return parsed.strftime("%Y-%m") if frequency == "monthly" else parsed.isoformat()


def _parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


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


def _assert_no_forbidden_fields(result: dict[str, object]) -> dict[str, object]:
    if FORBIDDEN_RESULT_FIELDS & set(result):
        raise SchemaValidationError("public downloader result contains forbidden result fields")
    return result


if __name__ == "__main__":
    raise SystemExit(run_public_data_downloader())
