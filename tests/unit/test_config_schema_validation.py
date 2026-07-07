"""Strict schema validation tests for config templates."""

from copy import deepcopy
from pathlib import Path
import tomllib

import pytest

from ethusdc_bot.config.schema import validate_config
from ethusdc_bot.validation import SchemaValidationError


ROOT = Path(__file__).resolve().parents[2]


def load_default_config():
    return tomllib.loads((ROOT / "config" / "default.toml").read_text(encoding="utf-8"))


def assert_rejected(config):
    with pytest.raises(SchemaValidationError):
        validate_config(config)


def test_default_config_passes_strict_schema_validation():
    validate_config(load_default_config())


@pytest.mark.parametrize(
    ("section", "key", "bad_value"),
    [
        ("project", "symbol", "BTCUSDC"),
        ("project", "quote_asset", "USDT"),
        ("project", "exchange", "coinbase"),
        ("project", "market_type", "futures"),
        ("project", "position_mode", "long_short"),
        ("project", "start_capital_usdc", 101),
        ("project", "start_capital_usdc", "100"),
        ("data_requirements", "training_days", 729),
        ("data_requirements", "blindtest_days", 364),
        ("data_requirements", "required_ethusdc_utc_days", 1094),
        ("data_requirements", "raw_data_location", "inside_repository"),
        ("safety", "live_enabled", True),
        ("safety", "paper_enabled", True),
        ("safety", "testtrade_enabled", True),
        ("safety", "shorts_enabled", True),
        ("safety", "margin_enabled", True),
        ("safety", "futures_enabled", True),
        ("safety", "leverage_enabled", True),
    ],
)
def test_config_rejects_forbidden_values_and_wrong_types(section, key, bad_value):
    config = load_default_config()
    config[section][key] = bad_value

    assert_rejected(config)


@pytest.mark.parametrize(
    "bad_context_symbols",
    [
        [],
        ["BTCUSDC"],
        ["ETHBTC", "BTCUSDC"],
        ["BTCUSDC", "ETHBTC", "BNBUSDC"],
        ("BTCUSDC", "ETHBTC"),
    ],
)
def test_config_rejects_wrong_context_symbols(bad_context_symbols):
    config = load_default_config()
    config["data_requirements"]["context_symbols"] = bad_context_symbols

    assert_rejected(config)


@pytest.mark.parametrize(
    ("section", "key"),
    [
        ("project", "symbol"),
        ("data_requirements", "training_days"),
        ("safety", "live_enabled"),
        ("phase", "current"),
    ],
)
def test_config_rejects_missing_required_fields(section, key):
    config = load_default_config()
    del config[section][key]

    assert_rejected(config)


def test_config_rejects_unknown_top_level_sections():
    config = load_default_config()
    config["engine"] = {"enabled": True}

    assert_rejected(config)


def test_config_rejects_unknown_nested_keys():
    config = load_default_config()
    config["project"]["secret_mode"] = "enabled"

    assert_rejected(config)
