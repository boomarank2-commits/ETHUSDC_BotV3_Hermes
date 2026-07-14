"""Protocol v3 task-7 tests for quantity, notional, fee and rounding parity."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.portfolio import PortfolioPolicy
from ethusdc_bot.protocol_v3.execution_parity import (
    ExecutionParityError,
    build_market_execution_rules,
    load_execution_parity_contract,
    prepare_market_entry,
    prepare_market_exit,
    simulate_protocol_v3_portfolio_strategy,
    simulate_protocol_v3_strategy,
    validate_execution_parity_contract,
)
from ethusdc_bot.protocol_v3.run_identity import build_exchange_info_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]


def _exchange_info(
    *,
    lot_step: str = "0.0001",
    market_step: str = "0.0001",
    min_notional: str = "5",
    max_notional: str = "10000000",
    apply_min: bool = True,
    apply_max: bool = False,
) -> dict:
    return {
        "symbols": [
            {
                "symbol": "ETHUSDC",
                "status": "TRADING",
                "baseAsset": "ETH",
                "quoteAsset": "USDC",
                "isSpotTradingAllowed": True,
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "minPrice": "0.01",
                        "maxPrice": "1000000",
                        "tickSize": "0.01",
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.0001",
                        "maxQty": "9000",
                        "stepSize": lot_step,
                    },
                    {
                        "filterType": "MARKET_LOT_SIZE",
                        "minQty": "0",
                        "maxQty": "1200",
                        "stepSize": market_step,
                    },
                    {
                        "filterType": "MIN_NOTIONAL",
                        "minNotional": min_notional,
                        "applyToMarket": apply_min,
                        "avgPriceMins": 5,
                    },
                    {
                        "filterType": "NOTIONAL",
                        "minNotional": min_notional,
                        "maxNotional": max_notional,
                        "applyMinToMarket": apply_min,
                        "applyMaxToMarket": apply_max,
                        "avgPriceMins": 5,
                    },
                ],
            }
        ]
    }


def _snapshot(**kwargs: object):
    return build_exchange_info_snapshot(
        _exchange_info(**kwargs),
        snapshot_as_of_utc="2026-07-07T23:59:59Z",
    )


def _candles(prices: list[float]) -> list[Candle]:
    return [
        Candle(
            open_time=index * 60_000,
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=10.0,
        )
        for index, price in enumerate(prices)
    ]


def _strategy() -> StrategyCandidate:
    return StrategyCandidate(
        "always_long",
        {
            "side": "LONG",
            "symbol": "ETHUSDC",
            "max_hold_minutes": 1,
            "cooldown_minutes": 0,
        },
    )


def test_task6_exchange_snapshot_and_task7_contract_remain_fail_closed() -> None:
    snapshot = _snapshot()
    rules = build_market_execution_rules(snapshot)
    assert len(snapshot.snapshot_sha256) == 64
    assert rules.exchange_info_snapshot_sha256 == snapshot.snapshot_sha256

    contract = load_execution_parity_contract(REPO_ROOT)
    assert contract["lot_policy"]["requested_entry_notional_usdc"] == "100"
    assert contract["lot_policy"]["fees_are_additional"] is True
    assert contract["price_policy"]["tick_rounding_deferred_to_task_8"] is True

    changed = json.loads(json.dumps(contract))
    changed["quantity_policy"]["rounding"] = "ROUND_HALF_UP"
    with pytest.raises(ExecutionParityError, match="not canonical"):
        validate_execution_parity_contract(changed)


def test_quantity_uses_positive_step_intersection_and_zero_market_fallback() -> None:
    intersection = build_market_execution_rules(
        _snapshot(lot_step="0.0001", market_step="0.001")
    )
    assert str(intersection.effective_quantity_step) == "0.001"
    assert intersection.quantity_step_sources == ("LOT_SIZE", "MARKET_LOT_SIZE")

    fallback = build_market_execution_rules(
        _snapshot(lot_step="0.0001", market_step="0")
    )
    assert str(fallback.effective_quantity_step) == "0.0001"
    assert fallback.quantity_step_sources == ("LOT_SIZE",)


def test_requested_reserved_and_executed_notional_are_separate_and_fees_additional() -> None:
    rules = build_market_execution_rules(
        _snapshot(lot_step="0.001", market_step="0")
    )
    entry = prepare_market_entry("1000", "0.001", rules)

    assert str(entry.requested_entry_notional) == "100"
    assert str(entry.reserved_entry_notional) == "100"
    assert str(entry.raw_quantity) == "0.1"
    assert str(entry.executed_quantity) == "0.1"
    assert str(entry.executed_entry_notional) == "100.0"
    assert str(entry.entry_fee) == "0.1000"
    assert str(entry.entry_cash_cost_including_fee) == "100.1000"
    assert entry.entry_cash_cost_including_fee > entry.reserved_entry_notional


def test_rounding_is_down_and_executed_notional_never_exceeds_100() -> None:
    rules = build_market_execution_rules(_snapshot())
    entry = prepare_market_entry("2001", "0.001", rules)

    assert str(entry.executed_quantity) == "0.0499"
    assert str(entry.executed_entry_notional) == "99.8499"
    assert entry.executed_entry_notional <= entry.requested_entry_notional
    assert str(entry.unspent_reserved_notional) == "0.1501"


def test_entry_and_exit_notional_filters_are_enforced() -> None:
    too_high_minimum = build_market_execution_rules(
        _snapshot(min_notional="101")
    )
    with pytest.raises(ExecutionParityError, match="entry notional is below"):
        prepare_market_entry("2000", "0.001", too_high_minimum)

    maximum = build_market_execution_rules(
        _snapshot(max_notional="90", apply_max=True)
    )
    with pytest.raises(ExecutionParityError, match="entry notional is above"):
        prepare_market_entry("2000", "0.001", maximum)

    rules = build_market_execution_rules(_snapshot(min_notional="99"))
    entry = prepare_market_entry("1000", "0.001", rules)
    with pytest.raises(ExecutionParityError, match="exit notional is below"):
        prepare_market_exit("900", entry.executed_quantity, "0.001", rules)


def test_golden_single_trade_is_exact_after_step_size_and_actual_fees() -> None:
    result = simulate_protocol_v3_strategy(
        _candles([1900.0, 2000.0, 2100.0]),
        _strategy(),
        days=1,
        exchange_info_snapshot=_snapshot(),
    )
    assert result.trade_count == 1
    trade = result.trades[0]

    expected = {
        "entry_price": 2001.0,
        "exit_price": 2098.95,
        "quantity": 0.0499,
        "exit_quantity": 0.0499,
        "requested_entry_notional_usdc": 100.0,
        "reserved_entry_notional_usdc": 100.0,
        "executed_entry_notional_usdc": 99.8499,
        "entry_fee_usdc": 0.0998499,
        "executed_exit_notional_usdc": 104.737605,
        "exit_fee_usdc": 0.104737605,
        "gross_profit_usdc": 4.887705,
        "fees_usdc": 0.204587505,
        "net_profit_usdc": 4.683117495,
    }
    actual = asdict(trade)
    for key, value in expected.items():
        assert actual[key] == value
    assert trade.quantity_rounding_mode == "ROUND_DOWN"
    assert trade.compounding_enabled is False
    assert result.equity_curve[-1].equity_usdc == trade.net_profit_usdc


def test_single_and_portfolio_golden_trade_core_are_bit_identical() -> None:
    candles = _candles([1900.0, 2000.0, 2100.0])
    snapshot = _snapshot()
    single = simulate_protocol_v3_strategy(
        candles,
        _strategy(),
        days=1,
        exchange_info_snapshot=snapshot,
    )
    portfolio = simulate_protocol_v3_portfolio_strategy(
        candles,
        _strategy(),
        days=1,
        policy=PortfolioPolicy(deployment_budget_usdc=100),
        exchange_info_snapshot=snapshot,
    )
    assert len(single.trades) == len(portfolio.trades) == 1
    single_row = asdict(single.trades[0])
    portfolio_row = asdict(portfolio.trades[0])
    for key, value in single_row.items():
        assert portfolio_row[key] == value
    assert portfolio.max_reserved_notional_usdc == 100.0
    assert portfolio.max_open_entry_exposure_usdc == 99.8499


def test_two_sequential_trades_keep_fixed_100_usdc_without_compounding() -> None:
    result = simulate_protocol_v3_strategy(
        _candles([1900.0, 2000.0, 2100.0, 2000.0, 2100.0]),
        _strategy(),
        days=1,
        exchange_info_snapshot=_snapshot(),
    )
    assert result.trade_count == 2
    assert all(
        trade.requested_entry_notional_usdc == 100.0
        and trade.reserved_entry_notional_usdc == 100.0
        and trade.compounding_enabled is False
        for trade in result.trades
    )
    assert all(trade.exit_quantity == trade.quantity for trade in result.trades)


def test_invalid_requested_lot_or_off_grid_exit_quantity_blocks() -> None:
    rules = build_market_execution_rules(_snapshot())
    with pytest.raises(ExecutionParityError, match="must remain exactly 100"):
        prepare_market_entry(
            "2000",
            "0.001",
            rules,
            requested_entry_notional="99",
        )
    with pytest.raises(ExecutionParityError, match="step grid"):
        prepare_market_exit("2100", "0.04995", "0.001", rules)
