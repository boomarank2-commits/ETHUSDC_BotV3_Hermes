"""Strict validation for the immutable local product configuration."""

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
PORTFOLIO_KEYS = {
    "model_version",
    "lot_notional_usdc",
    "default_deployment_budget_usdc",
    "allowed_deployment_budgets_usdc",
    "compounding_enabled",
    "baseline_fee_bps_per_side",
    "baseline_slippage_bps_per_side",
    "soft_drawdown_fraction",
}
TARGET_GUIDANCE_KEYS = {
    "measurement",
    "includes_zero_trade_days",
    "acceptable_by_budget_usdc",
    "desired_by_budget_usdc",
    "used_for_candidate_search",
}
SHADOW_KEYS = {
    "mode",
    "runtime_location",
    "orders_enabled",
    "trading_api_enabled",
    "api_keys_used",
    "automatic_live_transition_enabled",
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
CONFIG_KEYS = {
    "project",
    "portfolio",
    "target_guidance",
    "shadow",
    "data_requirements",
    "safety",
    "phase",
}


def validate_config(config: Mapping[str, Any]) -> None:
    """Validate the strict default product config.

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

    portfolio = require_mapping(root["portfolio"], "config.portfolio")
    require_exact_keys(portfolio, PORTFOLIO_KEYS, "config.portfolio")
    require_literal(
        portfolio, "model_version", "fixed_lot_portfolio_v1", "config.portfolio"
    )
    require_literal(portfolio, "lot_notional_usdc", 100, "config.portfolio")
    require_literal(
        portfolio, "default_deployment_budget_usdc", 100, "config.portfolio"
    )
    require_literal(
        portfolio,
        "allowed_deployment_budgets_usdc",
        [100, 200, 500, 1000],
        "config.portfolio",
    )
    require_false(portfolio, "compounding_enabled", "config.portfolio")
    require_literal(
        portfolio, "baseline_fee_bps_per_side", 10, "config.portfolio"
    )
    require_literal(
        portfolio, "baseline_slippage_bps_per_side", 5, "config.portfolio"
    )
    require_literal(portfolio, "soft_drawdown_fraction", 0.15, "config.portfolio")

    target_guidance = require_mapping(
        root["target_guidance"], "config.target_guidance"
    )
    require_exact_keys(
        target_guidance, TARGET_GUIDANCE_KEYS, "config.target_guidance"
    )
    require_literal(
        target_guidance,
        "measurement",
        "net_usdc_per_calendar_day_after_costs",
        "config.target_guidance",
    )
    require_literal(
        target_guidance,
        "includes_zero_trade_days",
        True,
        "config.target_guidance",
    )
    require_literal(
        target_guidance,
        "acceptable_by_budget_usdc",
        {"100": 3, "200": 5, "500": 12, "1000": 25},
        "config.target_guidance",
    )
    require_literal(
        target_guidance,
        "desired_by_budget_usdc",
        {"100": 3, "200": 6, "500": 13, "1000": 30},
        "config.target_guidance",
    )
    require_false(
        target_guidance, "used_for_candidate_search", "config.target_guidance"
    )

    shadow = require_mapping(root["shadow"], "config.shadow")
    require_exact_keys(shadow, SHADOW_KEYS, "config.shadow")
    require_literal(shadow, "mode", "public_data_shadow", "config.shadow")
    require_literal(
        shadow, "runtime_location", "outside_repository", "config.shadow"
    )
    for key in (
        "orders_enabled",
        "trading_api_enabled",
        "api_keys_used",
        "automatic_live_transition_enabled",
    ):
        require_false(shadow, key, "config.shadow")

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
    require_literal(
        phase, "current", "portfolio_shadow_foundation", "config.phase"
    )
    require_literal(
        phase,
        "implementation_scope",
        "offline_backtest_and_order_free_shadow_only",
        "config.phase",
    )
