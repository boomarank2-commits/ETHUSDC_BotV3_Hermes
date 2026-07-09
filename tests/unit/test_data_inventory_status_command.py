"""Local data inventory status command tests.

These tests exercise only catalog loading, path inventory metadata, and command
formatting. They do not download data, call Binance, read market data contents,
run a backtest, or create reports.
"""

from pathlib import Path
import json

from ethusdc_bot.data_pipeline.inventory import build_expected_inventory
from ethusdc_bot.data_pipeline.inventory_status import (
    DEFAULT_LOCAL_ROOT,
    build_inventory_status,
    format_inventory_status_text,
    load_data_catalog,
    main,
)


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


def test_status_command_loads_data_catalog_template():
    catalog = load_data_catalog(CATALOG_PATH)

    assert catalog["schema_version"] == 1
    assert catalog["project"]["symbol"] == "ETHUSDC"
    assert {source["source_id"] for source in catalog["sources"]}


def test_default_local_root_is_project_data_directory():
    assert DEFAULT_LOCAL_ROOT == "C:/TradingBot/data/ETHUSDC_BotV3_Hermes"


def test_text_output_contains_required_symbols(tmp_path):
    status = build_inventory_status(CATALOG_PATH, tmp_path, ROOT)
    text = format_inventory_status_text(status)

    assert "ETHUSDC" in text
    assert "BTCUSDC" in text
    assert "ETHBTC" in text


def test_text_output_contains_missing_present_and_blocked_words(tmp_path):
    catalog = load_data_catalog(CATALOG_PATH)
    expected = build_expected_inventory(catalog, tmp_path, ROOT)
    Path(expected["sources"][0]["expected_path"]).mkdir(parents=True)
    status = build_inventory_status(CATALOG_PATH, tmp_path, ROOT)
    blocked_status = build_inventory_status(CATALOG_PATH, ROOT / "data", ROOT)

    text = format_inventory_status_text(status)
    blocked_text = format_inventory_status_text(blocked_status)

    assert "missing" in text
    assert "present" in text
    assert "blocked" in blocked_text


def test_json_output_contains_no_profit_backtest_trade_or_candidate_fields(tmp_path, capsys):
    exit_code = main(["--catalog", str(CATALOG_PATH), "--local-root", str(tmp_path), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(payload)
    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(payload["inventory"])
    for entry in payload["inventory"]["sources"]:
        assert FORBIDDEN_RESULT_FIELDS.isdisjoint(entry)


def test_local_root_inside_repository_produces_blocked_status():
    status = build_inventory_status(CATALOG_PATH, ROOT / "data", ROOT)

    assert status["inventory"]["status"] == "blocked"
    assert status["counts"]["blocked"] == status["counts"]["total"]


def test_outside_repository_with_missing_paths_produces_missing_status(tmp_path):
    status = build_inventory_status(CATALOG_PATH, tmp_path, ROOT)

    assert status["inventory"]["status"] == "missing"
    assert status["counts"]["missing"] == status["counts"]["total"]


def test_existing_temporary_paths_produce_present_status(tmp_path):
    catalog = load_data_catalog(CATALOG_PATH)
    expected = build_expected_inventory(catalog, tmp_path, ROOT)
    Path(expected["sources"][0]["expected_path"]).mkdir(parents=True)

    status = build_inventory_status(CATALOG_PATH, tmp_path, ROOT)

    assert status["counts"]["present"] == 1
    assert status["counts"]["missing"] == status["counts"]["total"] - 1
    assert any(entry["status"] == "present" for entry in status["inventory"]["sources"])


def test_cli_output_states_no_download_no_binance_and_locked_modes(tmp_path, capsys):
    exit_code = main(["--catalog", str(CATALOG_PATH), "--local-root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "no download" in captured.out
    assert "no Binance API" in captured.out
    assert "no market data read" in captured.out
    assert "no backtest" in captured.out
    assert "live/paper/testtrade locked" in captured.out


def test_context_and_primary_symbol_rules_are_preserved(tmp_path):
    status = build_inventory_status(CATALOG_PATH, tmp_path, ROOT)
    entries = {entry["source_id"]: entry for entry in status["inventory"]["sources"]}
    primary_symbols = {
        entry["symbol"]
        for entry in status["inventory"]["sources"]
        if entry["role"] == "primary_trading_symbol"
    }

    assert primary_symbols == {"ETHUSDC"}
    assert entries["btcusdc_1m_klines"]["role"] == "context_only"
    assert entries["ethbtc_1m_klines"]["role"] == "context_only"
    assert entries["btcusdc_1m_klines"]["may_trigger_orders"] is False
    assert entries["ethbtc_1m_klines"]["may_trigger_orders"] is False


def test_status_command_never_claims_usable_quality(tmp_path):
    status = build_inventory_status(CATALOG_PATH, tmp_path, ROOT)

    assert status["inventory"]["quality_status"] != "usable"
    assert all(
        entry["quality_status"] != "usable"
        for entry in status["inventory"]["sources"]
    )


def test_forbidden_files_and_directories_do_not_exist():
    forbidden_paths = [
        "src/ethusdc_bot/data_pipeline/downloader.py",
        "src/ethusdc_bot/data_pipeline/binance_client.py",
        "src/ethusdc_bot/exchange",
        "src/ethusdc_bot/engine",
        "src/ethusdc_bot/strategy",

        "data",
        "raw",
        "market_data",
    ]

    assert [path for path in forbidden_paths if (ROOT / path).exists()] == []
