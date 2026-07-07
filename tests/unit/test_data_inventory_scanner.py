"""Local data inventory scanner tests.

These tests use only catalog metadata and temporary directories. They do not
read market data, download anything, call Binance, or create runtime reports.
"""

from pathlib import Path
import tomllib

from ethusdc_bot.data_pipeline.inventory import (
    build_expected_inventory,
    scan_local_inventory,
)


ROOT = Path(__file__).resolve().parents[2]
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
    return tomllib.loads((ROOT / "config" / "data_catalog.example.toml").read_text(encoding="utf-8"))


def by_source_id(inventory):
    return {entry["source_id"]: entry for entry in inventory["sources"]}


def test_inventory_blocks_local_root_inside_repository():
    inventory = scan_local_inventory(load_catalog(), ROOT / "data", ROOT)

    assert inventory["status"] == "blocked"
    assert inventory["quality_status"] == "blocked"
    assert all(entry["status"] == "blocked" for entry in inventory["sources"])


def test_inventory_accepts_local_root_outside_repository(tmp_path):
    inventory = build_expected_inventory(load_catalog(), tmp_path, ROOT)

    assert inventory["status"] == "planned"
    assert inventory["local_root"] == str(tmp_path)
    assert inventory["repository_root"] == str(ROOT)
    assert inventory["quality_status"] == "unknown"


def test_inventory_generates_entries_for_all_catalog_sources(tmp_path):
    catalog = load_catalog()
    inventory = build_expected_inventory(catalog, tmp_path, ROOT)

    assert {entry["source_id"] for entry in inventory["sources"]} == {
        source["source_id"] for source in catalog["sources"]
    }
    assert len(inventory["sources"]) == len(catalog["sources"])


def test_inventory_marks_missing_paths_as_missing(tmp_path):
    inventory = scan_local_inventory(load_catalog(), tmp_path, ROOT)

    assert inventory["status"] == "missing"
    assert {entry["status"] for entry in inventory["sources"]} == {"missing"}


def test_inventory_marks_existing_temporary_paths_as_present(tmp_path):
    catalog = load_catalog()
    expected = build_expected_inventory(catalog, tmp_path, ROOT)
    first_expected_path = Path(expected["sources"][0]["expected_path"])
    first_expected_path.mkdir(parents=True)

    inventory = scan_local_inventory(catalog, tmp_path, ROOT)
    entries = by_source_id(inventory)

    assert entries[expected["sources"][0]["source_id"]]["status"] == "present"
    assert "present" in {entry["status"] for entry in inventory["sources"]}
    assert "missing" in {entry["status"] for entry in inventory["sources"]}


def test_inventory_never_claims_usable_quality(tmp_path):
    catalog = load_catalog()
    expected = build_expected_inventory(catalog, tmp_path, ROOT)
    Path(expected["sources"][0]["expected_path"]).mkdir(parents=True)

    inventory = scan_local_inventory(catalog, tmp_path, ROOT)

    assert inventory["quality_status"] != "usable"
    assert {entry["quality_status"] for entry in inventory["sources"]} <= {
        "unknown",
        "missing",
        "blocked",
    }
    assert all(entry["quality_status"] != "usable" for entry in inventory["sources"])


def test_inventory_does_not_emit_backtest_profit_or_trade_fields(tmp_path):
    inventory = scan_local_inventory(load_catalog(), tmp_path, ROOT)

    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(inventory)
    for entry in inventory["sources"]:
        assert FORBIDDEN_RESULT_FIELDS.isdisjoint(entry)


def test_inventory_keeps_context_only_sources_from_triggering_orders(tmp_path):
    inventory = build_expected_inventory(load_catalog(), tmp_path, ROOT)
    entries = by_source_id(inventory)

    assert entries["btcusdc_1m_klines"]["role"] == "context_only"
    assert entries["ethbtc_1m_klines"]["role"] == "context_only"
    assert entries["btcusdc_1m_klines"]["may_trigger_orders"] is False
    assert entries["ethbtc_1m_klines"]["may_trigger_orders"] is False


def test_inventory_keeps_ethusdc_as_only_primary_trading_symbol(tmp_path):
    inventory = build_expected_inventory(load_catalog(), tmp_path, ROOT)
    primary_symbols = {
        entry["symbol"]
        for entry in inventory["sources"]
        if entry["role"] == "primary_trading_symbol"
    }

    assert primary_symbols == {"ETHUSDC"}


def test_forbidden_files_and_directories_do_not_exist():
    forbidden_paths = [
        "src/ethusdc_bot/data_pipeline/downloader.py",
        "src/ethusdc_bot/data_pipeline/binance_client.py",
        "src/ethusdc_bot/exchange",
        "src/ethusdc_bot/engine",
        "src/ethusdc_bot/strategy",
        "src/ethusdc_bot/backtest",
        "src/ethusdc_bot/ui",
        "data",
        "raw",
        "market_data",
    ]

    assert [path for path in forbidden_paths if (ROOT / path).exists()] == []
