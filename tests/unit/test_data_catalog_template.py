"""Data catalog template content tests."""

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def load_catalog():
    return tomllib.loads((ROOT / "config" / "data_catalog.example.toml").read_text(encoding="utf-8"))


def test_data_catalog_template_contains_required_project_limits():
    catalog = load_catalog()

    assert catalog["schema_version"] == 1
    assert catalog["template"] is True
    assert catalog["project"]["symbol"] == "ETHUSDC"
    assert catalog["project"]["quote_asset"] == "USDC"
    assert catalog["project"]["base_asset"] == "ETH"
    assert catalog["project"]["exchange"] == "binance"
    assert catalog["project"]["market_type"] == "spot"
    assert catalog["project"]["position_mode"] == "long_only"
    assert catalog["project"]["training_days"] == 730
    assert catalog["project"]["blindtest_days"] == 365
    assert catalog["project"]["required_ethusdc_utc_days"] == 1095
    assert catalog["project"]["context_symbols"] == ["BTCUSDC", "ETHBTC"]


def test_data_catalog_template_keeps_raw_data_outside_repository():
    catalog = load_catalog()

    assert catalog["raw_data_policy"]["raw_data_location"] == "outside_repository"
    assert catalog["raw_data_policy"]["repository_raw_data_allowed"] is False
    assert (
        catalog["raw_data_policy"]["example_local_root"]
        == "C:/TradingBot/data/ETHUSDC_BotV3_Hermes"
    )


def test_data_catalog_template_lists_required_sources_without_claiming_success():
    catalog = load_catalog()
    sources = {source["source_id"]: source for source in catalog["sources"]}

    assert set(sources) == {
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
    assert sources["ethusdc_1m_klines"]["role"] == "primary_trading_symbol"
    assert sources["ethusdc_1m_klines"]["may_trigger_orders"] is True
    assert sources["btcusdc_1m_klines"]["role"] == "context_only"
    assert sources["ethbtc_1m_klines"]["role"] == "context_only"
    assert sources["btcusdc_1m_klines"]["may_trigger_orders"] is False
    assert sources["ethbtc_1m_klines"]["may_trigger_orders"] is False
    assert {source["quality_status"] for source in sources.values()} <= {"unknown", "missing"}
