"""Strict schema validation tests for data catalog templates."""

from copy import deepcopy
from pathlib import Path
import tomllib

import pytest

from ethusdc_bot.data_pipeline.catalog_schema import validate_data_catalog
from ethusdc_bot.validation import SchemaValidationError


ROOT = Path(__file__).resolve().parents[2]


def load_catalog():
    return tomllib.loads((ROOT / "config" / "data_catalog.example.toml").read_text(encoding="utf-8"))


def assert_rejected(catalog):
    with pytest.raises(SchemaValidationError):
        validate_data_catalog(catalog, repository_root=ROOT)


def source_by_id(catalog, source_id):
    return next(source for source in catalog["sources"] if source["source_id"] == source_id)


def test_data_catalog_template_passes_strict_schema_validation():
    validate_data_catalog(load_catalog(), repository_root=ROOT)


def test_data_catalog_rejects_wrong_primary_trading_symbol():
    catalog = load_catalog()
    source_by_id(catalog, "ethusdc_1m_klines")["symbol"] = "BTCUSDC"

    assert_rejected(catalog)


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
def test_data_catalog_rejects_wrong_context_symbols(bad_context_symbols):
    catalog = load_catalog()
    catalog["project"]["context_symbols"] = bad_context_symbols

    assert_rejected(catalog)


def test_data_catalog_rejects_context_only_source_that_may_trigger_orders():
    catalog = load_catalog()
    source_by_id(catalog, "btcusdc_1m_klines")["may_trigger_orders"] = True

    assert_rejected(catalog)


def test_data_catalog_rejects_raw_data_path_inside_repository():
    catalog = load_catalog()
    source_by_id(catalog, "ethusdc_1m_klines")["local_path_hint"] = str(
        ROOT / "data" / "ETHUSDC" / "klines.csv"
    )

    assert_rejected(catalog)


def test_data_catalog_template_sources_must_not_claim_usable_quality():
    catalog = load_catalog()
    source_by_id(catalog, "ethusdc_1m_klines")["quality_status"] = "usable"

    assert_rejected(catalog)


@pytest.mark.parametrize(
    ("section", "key", "bad_value"),
    [
        ("project", "quote_asset", "USDT"),
        ("project", "exchange", "coinbase"),
        ("project", "market_type", "futures"),
        ("project", "position_mode", "long_short"),
        ("project", "training_days", 729),
        ("project", "blindtest_days", 364),
        ("project", "required_ethusdc_utc_days", 1094),
        ("raw_data_policy", "repository_raw_data_allowed", True),
        ("raw_data_policy", "raw_data_location", "inside_repository"),
    ],
)
def test_data_catalog_rejects_forbidden_project_and_raw_policy_values(section, key, bad_value):
    catalog = load_catalog()
    catalog[section][key] = bad_value

    assert_rejected(catalog)


def test_data_catalog_rejects_unknown_fields():
    catalog = load_catalog()
    source_by_id(catalog, "ethusdc_1m_klines")["backtest_profit"] = 999

    assert_rejected(catalog)


def test_data_catalog_rejects_missing_required_fields():
    catalog = load_catalog()
    del source_by_id(catalog, "ethusdc_1m_klines")["quality_status"]

    assert_rejected(catalog)


@pytest.mark.parametrize(
    ("section", "key", "bad_value"),
    [
        ("project", "training_days", "730"),
        ("raw_data_policy", "repository_raw_data_allowed", "false"),
    ],
)
def test_data_catalog_rejects_wrong_types(section, key, bad_value):
    catalog = load_catalog()
    catalog[section][key] = bad_value

    assert_rejected(catalog)
