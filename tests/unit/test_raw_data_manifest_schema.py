"""Raw data manifest template schema tests.

These tests validate manifest metadata only. They do not download data, call
Binance, read market data contents, create raw data directories, run backtests,
or unlock live/paper/testtrade.
"""

from copy import deepcopy
from pathlib import Path
import json

import pytest

from ethusdc_bot.data_pipeline.manifest_schema import validate_raw_data_manifest
from ethusdc_bot.validation import SchemaValidationError


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "config" / "raw_data_manifest.example.json"
FORBIDDEN_RESULT_FIELDS = [
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
]
FORBIDDEN_SECRET_FIELDS = ["api_key", "api_secret", "secret", "token"]
FORBIDDEN_UNLOCK_FIELDS = ["live_enabled", "paper_enabled", "testtrade_enabled"]


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def assert_rejected(manifest):
    with pytest.raises(SchemaValidationError):
        validate_raw_data_manifest(manifest)


def test_example_raw_data_manifest_template_is_valid():
    validate_raw_data_manifest(load_manifest())


def test_manifest_rejects_wrong_symbol():
    manifest = load_manifest()
    manifest["symbol"] = "BNBUSDC"

    assert_rejected(manifest)


def test_manifest_rejects_wrong_market():
    manifest = load_manifest()
    manifest["market_type"] = "futures"

    assert_rejected(manifest)


def test_manifest_rejects_wrong_role():
    manifest = load_manifest()
    manifest["role"] = "trading_context"

    assert_rejected(manifest)


def test_manifest_rejects_context_only_may_trigger_orders_true():
    manifest = load_manifest()
    manifest["symbol"] = "BTCUSDC"
    manifest["role"] = "context_only"
    manifest["may_trigger_orders"] = True

    assert_rejected(manifest)


def test_manifest_rejects_quality_status_usable_in_template():
    manifest = load_manifest()
    manifest["quality_status"] = "usable"

    assert_rejected(manifest)


@pytest.mark.parametrize("bad_status", ["complete", "success", "usable"])
def test_manifest_rejects_download_status_success_complete_or_usable_in_template(bad_status):
    manifest = load_manifest()
    manifest["download_status"] = bad_status

    assert_rejected(manifest)


@pytest.mark.parametrize("bad_status", ["audited", "complete"])
def test_manifest_rejects_audit_status_audited_or_complete_in_template(bad_status):
    manifest = load_manifest()
    manifest["audit_status"] = bad_status

    assert_rejected(manifest)


@pytest.mark.parametrize("field_name", FORBIDDEN_RESULT_FIELDS)
def test_manifest_rejects_profit_backtest_trade_and_candidate_fields(field_name):
    manifest = load_manifest()
    manifest[field_name] = 0

    assert_rejected(manifest)


@pytest.mark.parametrize("field_name", FORBIDDEN_SECRET_FIELDS)
def test_manifest_rejects_api_key_secret_and_token_fields(field_name):
    manifest = load_manifest()
    manifest[field_name] = "secret-value"

    assert_rejected(manifest)


@pytest.mark.parametrize("field_name", FORBIDDEN_UNLOCK_FIELDS)
def test_manifest_rejects_live_paper_and_testtrade_unlock_fields(field_name):
    manifest = load_manifest()
    manifest[field_name] = True

    assert_rejected(manifest)


def test_manifest_rejects_unknown_fields():
    manifest = load_manifest()
    manifest["downloaded_files_count"] = 99

    assert_rejected(manifest)


def test_manifest_rejects_missing_required_fields():
    manifest = load_manifest()
    del manifest["source_id"]

    assert_rejected(manifest)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("schema_version", "1"),
        ("template", "true"),
        ("interval_seconds", "60"),
        ("files", ()),
        ("observed_rows", "0"),
        ("missing_utc_days", ()),
        ("duplicate_rows", "0"),
        ("gap_count", "0"),
        ("max_gap_seconds", "0"),
    ],
)
def test_manifest_rejects_wrong_types(field_name, bad_value):
    manifest = load_manifest()
    manifest[field_name] = bad_value

    assert_rejected(manifest)


def test_manifest_files_must_be_empty_in_template():
    manifest = load_manifest()
    manifest["files"] = ["ETHUSDC-1m.csv"]

    assert_rejected(manifest)


def test_manifest_observed_rows_must_be_zero_in_template():
    manifest = load_manifest()
    manifest["observed_rows"] = 1

    assert_rejected(manifest)


def test_manifest_observed_start_and_end_must_be_null_in_template():
    for field_name in ["observed_start_utc", "observed_end_utc"]:
        manifest = load_manifest()
        manifest[field_name] = "2024-01-01T00:00:00Z"

        assert_rejected(manifest)


def test_forbidden_files_and_directories_do_not_exist():
    forbidden_paths = [
        "src/ethusdc_bot/data_pipeline/downloader.py",
        "src/ethusdc_bot/data_pipeline/binance_client.py",
        "src/ethusdc_bot/exchange",
        "src/ethusdc_bot/engine",
        "src/ethusdc_bot/strategy",
        "src/ethusdc_bot/backtest",
        "data",
        "raw",
        "market_data",
    ]

    assert [path for path in forbidden_paths if (ROOT / path).exists()] == []
