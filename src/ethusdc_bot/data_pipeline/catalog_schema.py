"""Strict schema validation for data catalog templates.

This module validates metadata only. It performs no downloads, no Binance API
calls, no trading, no backtesting, and no report-result generation.
"""

from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Any

from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.validation import (
    SchemaValidationError,
    require_exact_keys,
    require_exact_string_list,
    require_false,
    require_literal,
    require_mapping,
    require_non_empty_string,
)


CATALOG_KEYS = {"schema_version", "template", "project", "raw_data_policy", "sources"}
PROJECT_KEYS = {
    "symbol",
    "quote_asset",
    "base_asset",
    "exchange",
    "market_type",
    "position_mode",
    "training_days",
    "blindtest_days",
    "required_ethusdc_utc_days",
    "context_symbols",
}
RAW_DATA_POLICY_KEYS = {
    "raw_data_location",
    "repository_raw_data_allowed",
    "example_local_root",
}
SOURCE_KEYS = {
    "source_id",
    "symbol",
    "role",
    "data_type",
    "interval_seconds",
    "exchange",
    "market_type",
    "expected_quote_asset",
    "may_trigger_orders",
    "required_for_phase",
    "required_for_backtest_candidate",
    "local_path_hint",
    "file_format",
    "timezone",
    "quality_status",
    "notes",
}
EXPECTED_SOURCE_IDS = {
    "ethusdc_1m_klines",
    "ethusdc_agg_trades",
    "ethusdc_trades",
    "ethusdc_exchange_info",
    "ethusdc_fees",
    "ethusdc_slippage",
    "ethusdc_book_ticker",
    "ethusdc_orderbook",
    "btcusdc_1m_klines",
    "ethbtc_1m_klines",
}
DATA_TYPES = {
    "klines",
    "agg_trades",
    "trades",
    "exchange_info",
    "fees",
    "slippage",
    "book_ticker",
    "orderbook",
}
ROLES = {"primary_trading_symbol", "context_only", "rules_or_costs"}
QUALITY_STATUSES = {"unknown", "missing", "incomplete", "blocked", "usable"}
CONTEXT_SYMBOLS = {"BTCUSDC", "ETHBTC"}


def validate_data_catalog(
    catalog: Mapping[str, Any], repository_root: str | Path | None = None
) -> None:
    """Validate the strict data catalog template schema."""

    root = require_mapping(catalog, "data_catalog")
    require_exact_keys(root, CATALOG_KEYS, "data_catalog")
    require_literal(root, "schema_version", 1, "data_catalog")
    require_literal(root, "template", True, "data_catalog")

    project = require_mapping(root["project"], "data_catalog.project")
    _validate_project(project)

    raw_data_policy = require_mapping(
        root["raw_data_policy"], "data_catalog.raw_data_policy"
    )
    _validate_raw_data_policy(raw_data_policy, repository_root)

    sources = root["sources"]
    if not isinstance(sources, list):
        raise SchemaValidationError("data_catalog.sources must be a list")
    source_ids = [
        _validate_source(source, root["template"], repository_root)
        for source in sources
    ]
    if set(source_ids) != EXPECTED_SOURCE_IDS or len(source_ids) != len(EXPECTED_SOURCE_IDS):
        raise SchemaValidationError("data_catalog.sources must contain exactly the required source_ids")


def _validate_project(project: Mapping[str, Any]) -> None:
    require_exact_keys(project, PROJECT_KEYS, "data_catalog.project")
    require_literal(project, "symbol", "ETHUSDC", "data_catalog.project")
    require_literal(project, "quote_asset", "USDC", "data_catalog.project")
    require_literal(project, "base_asset", "ETH", "data_catalog.project")
    require_literal(project, "exchange", "binance", "data_catalog.project")
    require_literal(project, "market_type", "spot", "data_catalog.project")
    require_literal(project, "position_mode", "long_only", "data_catalog.project")
    require_literal(project, "training_days", 730, "data_catalog.project")
    require_literal(project, "blindtest_days", 365, "data_catalog.project")
    require_literal(project, "required_ethusdc_utc_days", 1095, "data_catalog.project")
    require_exact_string_list(
        project,
        "context_symbols",
        ["BTCUSDC", "ETHBTC"],
        "data_catalog.project",
    )


def _validate_raw_data_policy(
    raw_data_policy: Mapping[str, Any], repository_root: str | Path | None
) -> None:
    require_exact_keys(
        raw_data_policy, RAW_DATA_POLICY_KEYS, "data_catalog.raw_data_policy"
    )
    require_literal(
        raw_data_policy,
        "raw_data_location",
        "outside_repository",
        "data_catalog.raw_data_policy",
    )
    require_false(
        raw_data_policy,
        "repository_raw_data_allowed",
        "data_catalog.raw_data_policy",
    )
    require_non_empty_string(
        raw_data_policy, "example_local_root", "data_catalog.raw_data_policy"
    )
    _reject_repository_path(
        raw_data_policy["example_local_root"], repository_root, "data_catalog.raw_data_policy.example_local_root"
    )


def _validate_source(
    source_value: Any, is_template: bool, repository_root: str | Path | None
) -> str:
    source = require_mapping(source_value, "data_catalog.sources[]")
    require_exact_keys(source, SOURCE_KEYS, "data_catalog.sources[]")

    source_id = _require_string(source, "source_id", "data_catalog.sources[]")
    symbol = _require_string(source, "symbol", f"data_catalog.sources.{source_id}")
    role = _require_string(source, "role", f"data_catalog.sources.{source_id}")
    data_type = _require_string(source, "data_type", f"data_catalog.sources.{source_id}")
    exchange = _require_string(source, "exchange", f"data_catalog.sources.{source_id}")
    market_type = _require_string(source, "market_type", f"data_catalog.sources.{source_id}")
    _require_string(source, "expected_quote_asset", f"data_catalog.sources.{source_id}")
    required_for_phase = _require_string(
        source, "required_for_phase", f"data_catalog.sources.{source_id}"
    )
    local_path_hint = _require_string(
        source, "local_path_hint", f"data_catalog.sources.{source_id}"
    )
    _require_string(source, "file_format", f"data_catalog.sources.{source_id}")
    timezone = _require_string(source, "timezone", f"data_catalog.sources.{source_id}")
    quality_status = _require_string(
        source, "quality_status", f"data_catalog.sources.{source_id}"
    )
    _require_string(source, "notes", f"data_catalog.sources.{source_id}")
    interval_seconds = source["interval_seconds"]
    may_trigger_orders = source["may_trigger_orders"]
    required_for_backtest_candidate = source["required_for_backtest_candidate"]

    if source_id not in EXPECTED_SOURCE_IDS:
        raise SchemaValidationError(f"data_catalog.sources.{source_id} is not an expected source")
    if role not in ROLES:
        raise SchemaValidationError(f"data_catalog.sources.{source_id}.role is invalid")
    if data_type not in DATA_TYPES:
        raise SchemaValidationError(f"data_catalog.sources.{source_id}.data_type is invalid")
    if exchange != "binance" or market_type != "spot":
        raise SchemaValidationError(f"data_catalog.sources.{source_id} must be binance spot")
    if timezone != "UTC":
        raise SchemaValidationError(f"data_catalog.sources.{source_id}.timezone must be UTC")
    if not isinstance(interval_seconds, int) or interval_seconds < 0:
        raise SchemaValidationError(
            f"data_catalog.sources.{source_id}.interval_seconds must be a non-negative integer"
        )
    if data_type == "klines" and interval_seconds <= 0:
        raise SchemaValidationError(
            f"data_catalog.sources.{source_id}.interval_seconds is required for klines"
        )
    if type(may_trigger_orders) is not bool:
        raise SchemaValidationError(
            f"data_catalog.sources.{source_id}.may_trigger_orders must be boolean"
        )
    if type(required_for_backtest_candidate) is not bool:
        raise SchemaValidationError(
            f"data_catalog.sources.{source_id}.required_for_backtest_candidate must be boolean"
        )
    if quality_status not in QUALITY_STATUSES:
        raise SchemaValidationError(f"data_catalog.sources.{source_id}.quality_status is invalid")
    if is_template and quality_status == "usable":
        raise SchemaValidationError(
            f"data_catalog.sources.{source_id}.quality_status must not be usable in templates"
        )

    _validate_symbol_role(source_id, symbol, role, may_trigger_orders)
    _reject_repository_path(local_path_hint, repository_root, f"data_catalog.sources.{source_id}.local_path_hint")
    if not required_for_phase.strip():
        raise SchemaValidationError(f"data_catalog.sources.{source_id}.required_for_phase must be non-empty")

    return source_id


def _validate_symbol_role(
    source_id: str, symbol: str, role: str, may_trigger_orders: bool
) -> None:
    if role == "primary_trading_symbol":
        if symbol != "ETHUSDC":
            raise SchemaValidationError(
                f"data_catalog.sources.{source_id}.symbol must be ETHUSDC for primary trading"
            )
        return

    if role == "context_only":
        if symbol not in CONTEXT_SYMBOLS:
            raise SchemaValidationError(
                f"data_catalog.sources.{source_id}.symbol must be a permitted context symbol"
            )
        if may_trigger_orders is not False:
            raise SchemaValidationError(
                f"data_catalog.sources.{source_id}.may_trigger_orders must be false for context_only"
            )
        return

    if symbol != "ETHUSDC":
        raise SchemaValidationError(
            f"data_catalog.sources.{source_id}.symbol must be ETHUSDC for rules_or_costs"
        )
    if may_trigger_orders is not False:
        raise SchemaValidationError(
            f"data_catalog.sources.{source_id}.may_trigger_orders must be false for rules_or_costs"
        )


def _require_string(data: Mapping[str, Any], key: str, path: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{path}.{key} must be a non-empty string")
    return value


def _reject_repository_path(
    path_value: str, repository_root: str | Path | None, path_name: str
) -> None:
    if repository_root is None:
        return
    if is_path_within(path_value, repository_root):
        raise SchemaValidationError(f"{path_name} must be outside the repository")
