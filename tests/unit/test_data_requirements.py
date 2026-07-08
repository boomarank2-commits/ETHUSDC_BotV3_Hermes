"""Backtest data requirement catalog tests."""

from ethusdc_bot.data_pipeline.data_requirements import (
    build_backtest_data_requirements,
    classify_requirement_role,
    get_requirement_by_id,
    requirement_blocks_backtest,
    requirement_can_be_downloaded_publicly,
    requirement_is_live_collected,
)


def test_requirements_contain_ethusdc_klines_as_blocking_trade_market():
    requirements = build_backtest_data_requirements()
    requirement = get_requirement_by_id(requirements, "ethusdc_klines_1m")

    assert requirement["symbol"] == "ETHUSDC"
    assert requirement["data_type"] == "klines_1m"
    assert requirement["role"] == "trade_market"
    assert requirement["required"] is True
    assert requirement["trade_market"] is True
    assert requirement["context_only"] is False
    assert requirement["required_days"] == 1095
    assert requirement_blocks_backtest(requirement) is True
    assert requirement_can_be_downloaded_publicly(requirement) is True


def test_requirements_contain_btcusdc_and_ethbtc_as_context_only_never_trade_market():
    requirements = build_backtest_data_requirements()
    btc = get_requirement_by_id(requirements, "btcusdc_klines_1m")
    ethbtc = get_requirement_by_id(requirements, "ethbtc_klines_1m")

    for requirement in [btc, ethbtc]:
        assert requirement["role"] == "market_context"
        assert requirement["context_only"] is True
        assert requirement["trade_market"] is False
        assert requirement["may_trigger_orders"] is False
        assert requirement["required_days"] == 1095
        assert classify_requirement_role(requirement) == "market_context"


def test_aggtrades_and_trades_are_microstructure_tradeflow():
    requirements = build_backtest_data_requirements()
    agg = get_requirement_by_id(requirements, "ethusdc_aggtrades")
    trades = get_requirement_by_id(requirements, "ethusdc_trades")

    assert agg["role"] == "microstructure_tradeflow"
    assert trades["role"] == "microstructure_tradeflow"
    assert agg["minimum_days"] == 7
    assert trades["minimum_days"] == 1
    assert requirement_can_be_downloaded_publicly(agg) is True
    assert requirement_can_be_downloaded_publicly(trades) is True


def test_bookticker_and_orderbook_are_live_collected_and_not_initially_included():
    requirements = build_backtest_data_requirements()
    bookticker = get_requirement_by_id(requirements, "ethusdc_bookticker_live")
    orderbook = get_requirement_by_id(requirements, "ethusdc_orderbook_snapshots_live")

    for requirement in [bookticker, orderbook]:
        assert requirement_is_live_collected(requirement) is True
        assert requirement["publicly_downloadable"] is False
        assert requirement["live_collected"] is True
        assert requirement["minimum_days"] == 30
        assert requirement["included_by_default"] is False
        assert requirement["diagnostic_until_minimum_history"] is True
