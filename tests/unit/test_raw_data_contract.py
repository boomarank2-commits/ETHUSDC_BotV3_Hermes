"""Raw data directory contract tests.

These tests define downloader input/path contracts only. They do not download,
call Binance, read market data, create raw data directories, run backtests, or
start trading/UI code.
"""

from pathlib import Path
import tomllib

import pytest

from ethusdc_bot.data_pipeline.raw_data_contract import (
    assert_raw_root_outside_repository,
    build_expected_raw_paths,
    build_source_raw_path,
    expected_raw_root,
    validate_download_target_contract,
)
from ethusdc_bot.validation import SchemaValidationError


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "config" / "data_catalog.example.toml"
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


def load_catalog():
    return tomllib.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def source_by_id(catalog, source_id):
    return next(source for source in catalog["sources"] if source["source_id"] == source_id)


def test_raw_root_inside_repository_is_rejected():
    with pytest.raises(SchemaValidationError):
        assert_raw_root_outside_repository(ROOT / "data", ROOT)


def test_expected_raw_root_is_allowed_outside_repository():
    raw_root = expected_raw_root()

    assert raw_root == Path("C:/TradingBot/data/ETHUSDC_BotV3_Hermes")
    assert_raw_root_outside_repository(raw_root, ROOT)


def test_ethusdc_1m_klines_path_is_correct():
    catalog = load_catalog()
    path = build_source_raw_path(
        source_by_id(catalog, "ethusdc_1m_klines"), expected_raw_root()
    )

    assert path == Path(
        "C:/TradingBot/data/ETHUSDC_BotV3_Hermes/raw/binance/spot/ETHUSDC/klines/1m"
    )


def test_btcusdc_and_ethbtc_remain_context_only():
    contract = validate_download_target_contract(load_catalog(), expected_raw_root(), ROOT)
    entries = {entry["source_id"]: entry for entry in contract["sources"]}

    assert entries["btcusdc_1m_klines"]["role"] == "context_only"
    assert entries["ethbtc_1m_klines"]["role"] == "context_only"
    assert entries["btcusdc_1m_klines"]["may_trigger_orders"] is False
    assert entries["ethbtc_1m_klines"]["may_trigger_orders"] is False


def test_all_catalog_sources_get_expected_paths():
    catalog = load_catalog()
    contract = build_expected_raw_paths(catalog, expected_raw_root(), ROOT)

    assert {entry["source_id"] for entry in contract["sources"]} == {
        source["source_id"] for source in catalog["sources"]
    }
    assert len(contract["sources"]) == len(catalog["sources"])


def test_no_expected_paths_point_into_repository():
    contract = validate_download_target_contract(load_catalog(), expected_raw_root(), ROOT)
    repo_text = str(ROOT).replace("\\", "/").rstrip("/").lower()

    for entry in contract["sources"]:
        target_text = entry["target_path"].replace("\\", "/").rstrip("/").lower()
        assert target_text != repo_text
        assert not target_text.startswith(repo_text + "/")


def test_contract_emits_no_profit_backtest_trade_or_candidate_fields():
    contract = validate_download_target_contract(load_catalog(), expected_raw_root(), ROOT)

    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(contract)
    for entry in contract["sources"]:
        assert FORBIDDEN_RESULT_FIELDS.isdisjoint(entry)


def test_contract_preserves_locked_execution_modes():
    contract = validate_download_target_contract(load_catalog(), expected_raw_root(), ROOT)

    assert contract["live_status"] == "locked"
    assert contract["paper_status"] == "locked"
    assert contract["testtrade_status"] == "locked"
    for entry in contract["sources"]:
        assert "live_enabled" not in entry
        assert "paper_enabled" not in entry
        assert "testtrade_enabled" not in entry


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
