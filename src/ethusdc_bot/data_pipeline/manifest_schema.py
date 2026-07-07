"""Strict validation for raw data manifest templates.

The manifest describes future local raw data directories only. This module does
not create folders, download files, read market data, call Binance, run
strategies, execute backtests, start UI code, or unlock live/paper/testtrade.
"""

from collections.abc import Mapping
from typing import Any

from ethusdc_bot.validation import SchemaValidationError


REQUIRED_KEYS = {
    "schema_version",
    "template",
    "source_id",
    "symbol",
    "role",
    "data_type",
    "interval_seconds",
    "exchange",
    "market_type",
    "quote_asset",
    "raw_root",
    "expected_path",
    "files",
    "download_status",
    "audit_status",
    "quality_status",
    "observed_start_utc",
    "observed_end_utc",
    "observed_rows",
    "complete_utc_days",
    "missing_utc_days",
    "duplicate_rows",
    "gap_count",
    "max_gap_seconds",
    "checksum_status",
    "notes",
}
OPTIONAL_KEYS = {"may_trigger_orders"}
FORBIDDEN_FIELDS = {
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
    "api_key",
    "api_secret",
    "secret",
    "token",
    "live_enabled",
    "paper_enabled",
    "testtrade_enabled",
}
ALLOWED_SYMBOLS = {"ETHUSDC", "BTCUSDC", "ETHBTC"}
CONTEXT_SYMBOLS = {"BTCUSDC", "ETHBTC"}
ALLOWED_ROLES = {"primary_trading_symbol", "context_only", "rules_or_costs"}
ALLOWED_DATA_TYPES = {
    "klines",
    "agg_trades",
    "trades",
    "exchange_info",
    "fees",
    "slippage",
    "book_ticker",
    "orderbook",
}
FORBIDDEN_TEMPLATE_DOWNLOAD_STATUSES = {"success", "complete", "usable"}
FORBIDDEN_TEMPLATE_AUDIT_STATUSES = {"audited", "complete"}


def validate_raw_data_manifest(manifest: Mapping[str, Any]) -> None:
    """Validate a raw data manifest template without accepting success claims."""

    if not isinstance(manifest, Mapping):
        raise SchemaValidationError("raw_data_manifest must be a mapping")

    keys = set(manifest.keys())
    forbidden_present = sorted(FORBIDDEN_FIELDS & keys)
    if forbidden_present:
        raise SchemaValidationError(
            f"raw_data_manifest contains forbidden fields: {forbidden_present}"
        )

    missing = REQUIRED_KEYS - keys
    if missing:
        raise SchemaValidationError(
            f"raw_data_manifest missing required keys: {sorted(missing)}"
        )
    extra = keys - REQUIRED_KEYS - OPTIONAL_KEYS
    if extra:
        raise SchemaValidationError(
            f"raw_data_manifest contains unknown keys: {sorted(extra)}"
        )

    _require_literal(manifest, "schema_version", 1)
    _require_literal(manifest, "template", True)
    _require_non_empty_string(manifest, "source_id")
    symbol = _require_non_empty_string(manifest, "symbol")
    role = _require_non_empty_string(manifest, "role")
    data_type = _require_non_empty_string(manifest, "data_type")
    _require_literal(manifest, "exchange", "binance")
    _require_literal(manifest, "market_type", "spot")
    _require_non_empty_string(manifest, "quote_asset")
    _require_non_empty_string(manifest, "raw_root")
    _require_non_empty_string(manifest, "expected_path")
    _require_literal(manifest, "download_status", "not_downloaded")
    _require_literal(manifest, "audit_status", "not_audited")
    _require_literal(manifest, "quality_status", "unknown")
    _require_literal(manifest, "observed_start_utc", None)
    _require_literal(manifest, "observed_end_utc", None)
    _require_literal(manifest, "observed_rows", 0)
    _require_literal(manifest, "complete_utc_days", 0)
    _require_literal(manifest, "duplicate_rows", 0)
    _require_literal(manifest, "gap_count", 0)
    _require_literal(manifest, "max_gap_seconds", 0)
    _require_literal(manifest, "checksum_status", "not_checked")
    _require_non_empty_string(manifest, "notes")
    _require_empty_list(manifest, "files")
    _require_empty_list(manifest, "missing_utc_days")

    interval_seconds = manifest["interval_seconds"]
    if not isinstance(interval_seconds, int) or interval_seconds < 0:
        raise SchemaValidationError(
            "raw_data_manifest.interval_seconds must be a non-negative integer"
        )
    if data_type == "klines" and interval_seconds <= 0:
        raise SchemaValidationError(
            "raw_data_manifest.interval_seconds must be positive for klines"
        )

    if symbol not in ALLOWED_SYMBOLS:
        raise SchemaValidationError("raw_data_manifest.symbol is not allowed")
    if role not in ALLOWED_ROLES:
        raise SchemaValidationError("raw_data_manifest.role is not allowed")
    if data_type not in ALLOWED_DATA_TYPES:
        raise SchemaValidationError("raw_data_manifest.data_type is not allowed")

    if role == "context_only" and symbol not in CONTEXT_SYMBOLS:
        raise SchemaValidationError(
            "raw_data_manifest.context_only symbol must be BTCUSDC or ETHBTC"
        )
    if role == "primary_trading_symbol" and symbol != "ETHUSDC":
        raise SchemaValidationError(
            "raw_data_manifest.primary_trading_symbol must be ETHUSDC"
        )
    if role == "rules_or_costs" and symbol != "ETHUSDC":
        raise SchemaValidationError("raw_data_manifest.rules_or_costs must be ETHUSDC")

    if "may_trigger_orders" in manifest:
        if type(manifest["may_trigger_orders"]) is not bool:
            raise SchemaValidationError(
                "raw_data_manifest.may_trigger_orders must be boolean"
            )
        if role == "context_only" and manifest["may_trigger_orders"] is not False:
            raise SchemaValidationError(
                "raw_data_manifest.context_only may_trigger_orders must be false"
            )

    if manifest["download_status"] in FORBIDDEN_TEMPLATE_DOWNLOAD_STATUSES:
        raise SchemaValidationError(
            "raw_data_manifest.download_status must not claim success in template"
        )
    if manifest["audit_status"] in FORBIDDEN_TEMPLATE_AUDIT_STATUSES:
        raise SchemaValidationError(
            "raw_data_manifest.audit_status must not claim audit completion in template"
        )
    if manifest["quality_status"] == "usable":
        raise SchemaValidationError(
            "raw_data_manifest.quality_status must not be usable in template"
        )


def _require_literal(data: Mapping[str, Any], key: str, expected: Any) -> None:
    value = data[key]
    if value != expected or type(value) is not type(expected):
        raise SchemaValidationError(f"raw_data_manifest.{key} must be {expected!r}")


def _require_non_empty_string(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(
            f"raw_data_manifest.{key} must be a non-empty string"
        )
    return value


def _require_empty_list(data: Mapping[str, Any], key: str) -> None:
    value = data[key]
    if not isinstance(value, list) or value:
        raise SchemaValidationError(f"raw_data_manifest.{key} must be an empty list")
