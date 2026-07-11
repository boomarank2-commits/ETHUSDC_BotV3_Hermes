"""Raw data target path contract for future download work.

This module defines where future raw data may be placed. It does not create
folders, download files, read market data, call Binance, run strategies, execute
backtests, start UI code, or unlock live/paper/testtrade paths.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.validation import SchemaValidationError


RAW_ROOT = Path("C:/TradingBot/data/ETHUSDC_BotV3_Hermes")
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
CONTEXT_SYMBOLS = {"BTCUSDC", "ETHBTC"}


def expected_raw_root() -> Path:
    """Return the only allowed local raw-data root for this project."""

    return RAW_ROOT


def assert_raw_root_outside_repository(
    raw_root: str | Path, repository_root: str | Path
) -> None:
    """Reject raw roots inside the repository.

    The function only validates paths; it does not create directories.
    """

    if _is_inside_repository(raw_root, repository_root):
        raise SchemaValidationError("raw_root must be outside the repository")


def build_source_raw_path(source: Mapping[str, Any], raw_root: str | Path) -> Path:
    """Build the future raw-data target directory for a catalog source."""

    symbol = str(source["symbol"])
    data_type = str(source["data_type"])
    interval_seconds = source["interval_seconds"]
    root = Path(raw_root)
    base = root / "raw" / "binance" / "spot" / symbol

    if data_type == "klines":
        return base / "klines" / _interval_label(interval_seconds)
    return base / data_type


def build_expected_raw_paths(
    catalog: Mapping[str, Any], raw_root: str | Path, repository_root: str | Path
) -> dict[str, Any]:
    """Build the raw-data path contract without validating downloader readiness."""

    raw_root_path = Path(raw_root)
    sources = [
        _source_contract_entry(source, raw_root_path, repository_root)
        for source in catalog["sources"]
    ]
    return {
        "schema_version": 1,
        "contract_type": "raw_data_directory_contract",
        "raw_root": str(raw_root_path),
        "repository_root": str(Path(repository_root)),
        "live_status": "locked",
        "paper_status": "locked",
        "testtrade_status": "locked",
        "creates_directories": False,
        "downloads_data": False,
        "reads_market_data": False,
        "uses_binance_api": False,
        "runs_backtest": False,
        "sources": sources,
    }


def validate_download_target_contract(
    catalog: Mapping[str, Any], raw_root: str | Path, repository_root: str | Path
) -> dict[str, Any]:
    """Validate and return the future downloader target path contract."""

    assert_raw_root_outside_repository(raw_root, repository_root)
    contract = build_expected_raw_paths(catalog, raw_root, repository_root)
    _reject_forbidden_result_fields(contract, "raw_data_contract")

    primary_symbols = set()
    for entry in contract["sources"]:
        _reject_forbidden_result_fields(entry, f"raw_data_contract.sources.{entry['source_id']}")
        if _is_inside_repository(entry["target_path"], repository_root):
            raise SchemaValidationError(
                f"raw_data_contract.sources.{entry['source_id']}.target_path must be outside the repository"
            )
        if entry["role"] == "context_only":
            if entry["symbol"] not in CONTEXT_SYMBOLS:
                raise SchemaValidationError(
                    f"raw_data_contract.sources.{entry['source_id']}.symbol is not an allowed context symbol"
                )
            if entry["may_trigger_orders"] is not False:
                raise SchemaValidationError(
                    f"raw_data_contract.sources.{entry['source_id']}.may_trigger_orders must stay false"
                )
        if entry["role"] == "primary_trading_symbol":
            primary_symbols.add(entry["symbol"])

    if primary_symbols != {"ETHUSDC"}:
        raise SchemaValidationError("ETHUSDC must be the only primary trading symbol")

    return contract


def _source_contract_entry(
    source: Mapping[str, Any], raw_root: Path, repository_root: str | Path
) -> dict[str, Any]:
    target_path = build_source_raw_path(source, raw_root)
    blocked = _is_inside_repository(target_path, repository_root)
    status = "blocked" if blocked else "planned"
    return {
        "source_id": source["source_id"],
        "symbol": source["symbol"],
        "role": source["role"],
        "data_type": source["data_type"],
        "interval_seconds": source["interval_seconds"],
        "may_trigger_orders": source["may_trigger_orders"],
        "target_path": str(target_path),
        "manifest_path": str(target_path / "manifest.json"),
        "expected_payload": "raw_files_plus_manifest",
        "status": status,
        "notes": "Contract only; no directory is created and no data is downloaded.",
    }


def _interval_label(interval_seconds: Any) -> str:
    if interval_seconds == 60:
        return "1m"
    return f"{interval_seconds}s"


def _is_inside_repository(path: str | Path, repository_root: str | Path) -> bool:
    return is_path_within(path, repository_root)


def _reject_forbidden_result_fields(data: Mapping[str, Any], path: str) -> None:
    forbidden_present = sorted(FORBIDDEN_RESULT_FIELDS & set(data.keys()))
    if forbidden_present:
        raise SchemaValidationError(
            f"{path} contains forbidden result fields: {forbidden_present}"
        )
