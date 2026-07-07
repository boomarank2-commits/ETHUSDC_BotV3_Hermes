"""Strict schema validation for Phase 1 config templates."""

from collections.abc import Mapping
from typing import Any

from ethusdc_bot.validation import (
    require_exact_keys,
    require_exact_string_list,
    require_false,
    require_literal,
    require_mapping,
)


PROJECT_KEYS = {
    "symbol",
    "quote_asset",
    "base_asset",
    "exchange",
    "market_type",
    "position_mode",
    "start_capital_usdc",
    "risk_profile",
}
DATA_REQUIREMENT_KEYS = {
    "training_days",
    "blindtest_days",
    "required_ethusdc_utc_days",
    "context_symbols",
    "raw_data_location",
}
SAFETY_KEYS = {
    "live_enabled",
    "paper_enabled",
    "testtrade_enabled",
    "shorts_enabled",
    "margin_enabled",
    "futures_enabled",
    "leverage_enabled",
}
PHASE_KEYS = {"current", "implementation_scope"}
CONFIG_KEYS = {"project", "data_requirements", "safety", "phase"}


def validate_config(config: Mapping[str, Any]) -> None:
    """Validate the strict Phase 1 default config schema.

    The schema encodes immutable project safety constraints only. It does not
    create runtime truth, connect to Binance, or implement trading behavior.
    """

    root = require_mapping(config, "config")
    require_exact_keys(root, CONFIG_KEYS, "config")

    project = require_mapping(root["project"], "config.project")
    require_exact_keys(project, PROJECT_KEYS, "config.project")
    require_literal(project, "symbol", "ETHUSDC", "config.project")
    require_literal(project, "quote_asset", "USDC", "config.project")
    require_literal(project, "base_asset", "ETH", "config.project")
    require_literal(project, "exchange", "binance", "config.project")
    require_literal(project, "market_type", "spot", "config.project")
    require_literal(project, "position_mode", "long_only", "config.project")
    require_literal(project, "start_capital_usdc", 100, "config.project")
    require_literal(project, "risk_profile", "medium", "config.project")

    data_requirements = require_mapping(
        root["data_requirements"], "config.data_requirements"
    )
    require_exact_keys(
        data_requirements, DATA_REQUIREMENT_KEYS, "config.data_requirements"
    )
    require_literal(data_requirements, "training_days", 730, "config.data_requirements")
    require_literal(data_requirements, "blindtest_days", 365, "config.data_requirements")
    require_literal(
        data_requirements,
        "required_ethusdc_utc_days",
        1095,
        "config.data_requirements",
    )
    require_exact_string_list(
        data_requirements,
        "context_symbols",
        ["BTCUSDC", "ETHBTC"],
        "config.data_requirements",
    )
    require_literal(
        data_requirements,
        "raw_data_location",
        "outside_repository",
        "config.data_requirements",
    )

    safety = require_mapping(root["safety"], "config.safety")
    require_exact_keys(safety, SAFETY_KEYS, "config.safety")
    for key in sorted(SAFETY_KEYS):
        require_false(safety, key, "config.safety")

    phase = require_mapping(root["phase"], "config.phase")
    require_exact_keys(phase, PHASE_KEYS, "config.phase")
    require_literal(phase, "current", "phase_1_skeleton", "config.phase")
    require_literal(
        phase,
        "implementation_scope",
        "structure_templates_tests_only",
        "config.phase",
    )
