"""Protocol v3 task-8 tests for next-tradable and pessimistic fills."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.portfolio import PortfolioPolicy
from ethusdc_bot.protocol_v3.execution_parity import prepare_market_entry
from ethusdc_bot.protocol_v3.intrabar_execution import (
    BASELINE_COST_PROFILE,
    JOINT_STRESS_COST_PROFILE,
    IntrabarExecutionError,
    load_intrabar_execution_contract,
    simulate_protocol_v3_intrabar_portfolio_strategy,
    simulate_protocol_v3_intrabar_strategy,
    validate_intrabar_execution_contract,
)
from ethusdc_bot.protocol_v3.run_identity import build_exchange_info_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]


def _snapshot(*, tick: str = "0.01"):
    payload = {
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
                        "tickSize": tick,
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.0001",
                        "maxQty": "9000",
                        "stepSize": "0.0001",
                    },
                    {
                        "filterType": "MARKET_LOT_SIZE",
                        "minQty": "0.0001",
                        "maxQty": "1200",
                        "stepSize": "0.0001",
                    },
                    {
                        "filterType": "MIN_NOTIONAL",
                        "minNotional": "5",
                        "applyToMarket": True,
                        "avgPriceMins": 5,
                    },
                    {
                        "filterType": "NOTIONAL",
                        "minNotional": "5",
                        "maxNotional": "10000000",
                        "applyMinToMarket": True,
                        "applyMaxToMarket": False,
                        "avgPriceMins": 5,
                    },
                ],
            }
        ]
    }
    return build_exchange_info_snapshot(
        payload,
        snapshot_as_of_utc="2026-07-07T23:59:59Z",
    )


def _candle(
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 10.0,
) -> Candle:
    return Candle(index * 60_000, open_, high, low, close, volume)


def _strategy(**changes: float | int | str) -> StrategyCandidate:
    params: dict[str, float | int | str] = {
        "side": "LONG",
        "symbol": "ETHUSDC",
        "stop_loss_bps": 100,
        "take_profit_bps": 100,
        "trailing_stop_bps": 0,
        "break_even_after_bps": 0,
        "max_hold_minutes": 10,
        "cooldown_minutes": 10,
    }
    params.update(changes)
    return StrategyCandidate("always_long", params)


def test_task7_remains_exact_and_task8_contract_is_fail_closed() -> None:
    contract = load_intrabar_execution_contract(REPO_ROOT)
    assert contract["entry_policy"]["signal_bar_must_be_closed"] is True
    assert contract["exit_policy"]["simultaneous_stop_target_priority"] == "stop_first"
    assert contract["task7_dependency"]["requested_entry_notional_usdc"] == "100"
    changed = json.loads(json.dumps(contract))
    changed["exit_policy"]["simultaneous_stop_target_priority"] = "target_first"
    with pytest.raises(IntrabarExecutionError, match="not canonical"):
        validate_intrabar_execution_contract(changed)

    rules_snapshot = _snapshot()
    from ethusdc_bot.protocol_v3.execution_parity import build_market_execution_rules

    entry = prepare_market_entry(
        "2001",
        "0.001",
        build_market_execution_rules(rules_snapshot),
    )
    assert str(entry.requested_entry_notional) == "100"
    assert str(entry.reserved_entry_notional) == "100"
    assert str(entry.executed_quantity) == "0.0499"
    assert str(entry.executed_entry_notional) == "99.8499"


def test_entry_waits_for_next_positive_volume_open_and_rounds_buy_up() -> None:
    candles = [
        _candle(0, open_=100, high=100.2, low=99.8, close=100),
        _candle(1, open_=101, high=101, low=101, close=101, volume=0),
        _candle(2, open_=100.003, high=100.2, low=99.9, close=100.1),
        _candle(3, open_=100.1, high=100.2, low=100.0, close=100.1),
    ]
    result = simulate_protocol_v3_intrabar_strategy(
        candles,
        _strategy(stop_loss_bps=500, take_profit_bps=500),
        days=1,
        exchange_info_snapshot=_snapshot(),
    )
    assert result.trade_count == 1
    trade = result.trades[0]
    assert trade.signal_time == 59_999
    assert trade.entry_time == 120_000
    assert trade.entry_reference_price == 100.003
    assert trade.entry_price == 100.06
    assert trade.entry_tick_rounding == "ROUND_CEILING"
    assert result.signal_funnel["blocked.zero_volume_pending_entry"] == 1
    assert trade.terminal_liquidation is True
    assert trade.exit_time == 239_999


def test_same_entry_bar_stop_and_target_touch_always_uses_stop() -> None:
    candles = [
        _candle(0, open_=100, high=100.1, low=99.9, close=100),
        _candle(1, open_=100, high=102, low=98, close=100),
    ]
    result = simulate_protocol_v3_intrabar_strategy(
        candles,
        _strategy(),
        days=1,
        exchange_info_snapshot=_snapshot(),
    )
    trade = result.trades[0]
    assert trade.entry_time == trade.exit_time == 60_000
    assert trade.exit_reason == "stop_loss"
    assert trade.simultaneous_stop_target_touch is True
    assert trade.active_stop_price == 99.04
    assert trade.exit_reference_price == 99.04
    assert trade.exit_price == 98.99
    assert trade.exit_price not in {candles[1].high, candles[1].low}


def test_stop_gap_fills_from_worse_open_not_stop_level() -> None:
    candles = [
        _candle(0, open_=100, high=100.1, low=99.9, close=100),
        _candle(1, open_=100, high=100.2, low=99.5, close=100),
        _candle(2, open_=98, high=99, low=97, close=98.5),
    ]
    result = simulate_protocol_v3_intrabar_strategy(
        candles,
        _strategy(take_profit_bps=500),
        days=1,
        exchange_info_snapshot=_snapshot(),
    )
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.gap_fill is True
    assert trade.active_stop_price == 99.04
    assert trade.exit_reference_price == 98.0
    assert trade.exit_price == 97.95
    assert trade.exit_price < trade.active_stop_price


def test_favorable_target_gap_is_capped_at_target_before_slippage() -> None:
    candles = [
        _candle(0, open_=100, high=100.1, low=99.9, close=100),
        _candle(1, open_=100, high=100.2, low=99.5, close=100),
        _candle(2, open_=102.5, high=103, low=102, close=102.5),
    ]
    result = simulate_protocol_v3_intrabar_strategy(
        candles,
        _strategy(stop_loss_bps=500),
        days=1,
        exchange_info_snapshot=_snapshot(),
    )
    trade = result.trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.gap_fill is True
    assert trade.target_price == 101.06
    assert trade.exit_reference_price == 101.06
    assert trade.exit_price == 101.0
    assert trade.exit_reference_price < candles[2].open


def test_break_even_activates_only_after_survived_completed_bar() -> None:
    candles = [
        _candle(0, open_=100, high=100.1, low=99.9, close=100),
        _candle(1, open_=100, high=100.8, low=99.2, close=100.2),
        _candle(2, open_=100.2, high=100.3, low=99.9, close=100),
    ]
    result = simulate_protocol_v3_intrabar_strategy(
        candles,
        _strategy(
            stop_loss_bps=200,
            take_profit_bps=500,
            break_even_after_bps=50,
        ),
        days=1,
        exchange_info_snapshot=_snapshot(),
    )
    trade = result.trades[0]
    assert trade.entry_time == 60_000
    assert trade.exit_time == 120_000
    assert trade.exit_reason == "break_even"
    assert trade.active_stop_source == "break_even"
    assert trade.active_stop_price == trade.entry_price
    assert trade.exit_price == 99.99


def test_time_exit_uses_bar_open_before_intrabar_levels() -> None:
    candles = [
        _candle(0, open_=100, high=100.1, low=99.9, close=100),
        _candle(1, open_=100, high=100.2, low=99.5, close=100),
        _candle(2, open_=100.4, high=103, low=97, close=100),
    ]
    result = simulate_protocol_v3_intrabar_strategy(
        candles,
        _strategy(max_hold_minutes=1),
        days=1,
        exchange_info_snapshot=_snapshot(),
    )
    trade = result.trades[0]
    assert trade.exit_reason == "time_exit"
    assert trade.simultaneous_stop_target_touch is False
    assert trade.exit_reference_price == 100.4
    assert trade.exit_price == 100.34


def test_baseline_and_joint_stress_use_same_engine_and_timing() -> None:
    candles = [
        _candle(0, open_=100, high=100.1, low=99.9, close=100),
        _candle(1, open_=100, high=100.2, low=99.5, close=100),
        _candle(2, open_=102, high=103, low=101.5, close=102),
    ]
    baseline = simulate_protocol_v3_intrabar_strategy(
        candles,
        _strategy(stop_loss_bps=500),
        days=1,
        exchange_info_snapshot=_snapshot(),
        cost_profile=BASELINE_COST_PROFILE,
    )
    stress = simulate_protocol_v3_intrabar_strategy(
        candles,
        _strategy(stop_loss_bps=500),
        days=1,
        exchange_info_snapshot=_snapshot(),
        cost_profile=JOINT_STRESS_COST_PROFILE,
    )
    left = baseline.trades[0]
    right = stress.trades[0]
    assert (left.signal_time, left.entry_time, left.exit_time, left.exit_reason) == (
        right.signal_time,
        right.entry_time,
        right.exit_time,
        right.exit_reason,
    )
    assert left.execution_contract_version == right.execution_contract_version
    assert left.cost_profile == "baseline"
    assert right.cost_profile == "joint_stress"
    assert right.net_profit_usdc < left.net_profit_usdc


def test_single_and_portfolio_use_identical_task8_trade_core() -> None:
    candles = [
        _candle(0, open_=100, high=100.1, low=99.9, close=100),
        _candle(1, open_=100, high=102, low=98, close=100),
    ]
    snapshot = _snapshot()
    single = simulate_protocol_v3_intrabar_strategy(
        candles,
        _strategy(),
        days=1,
        exchange_info_snapshot=snapshot,
    )
    portfolio = simulate_protocol_v3_intrabar_portfolio_strategy(
        candles,
        _strategy(),
        days=1,
        policy=PortfolioPolicy(deployment_budget_usdc=100),
        exchange_info_snapshot=snapshot,
    )
    single_row = asdict(single.trades[0])
    portfolio_row = asdict(portfolio.trades[0])
    for key, value in single_row.items():
        assert portfolio_row[key] == value
    assert portfolio.max_concurrent_lots == 1
    assert portfolio.max_reserved_notional_usdc == 100.0
    assert portfolio.max_open_entry_exposure_usdc <= 100.0
    assert portfolio.equity_curve[-1].equity_usdc == portfolio.net_profit_usdc


def test_noncanonical_portfolio_size_and_untradable_terminal_bar_block() -> None:
    candles = [
        _candle(0, open_=100, high=100.1, low=99.9, close=100),
        _candle(1, open_=100, high=100.2, low=99.5, close=100),
    ]
    with pytest.raises(IntrabarExecutionError, match="one open lot"):
        simulate_protocol_v3_intrabar_portfolio_strategy(
            candles,
            _strategy(stop_loss_bps=500, take_profit_bps=500),
            days=1,
            policy=PortfolioPolicy(deployment_budget_usdc=200),
            exchange_info_snapshot=_snapshot(),
        )

    zero_terminal = [
        _candle(0, open_=100, high=100.1, low=99.9, close=100),
        _candle(1, open_=100, high=100.2, low=99.5, close=100),
        _candle(2, open_=100, high=100, low=100, close=100, volume=0),
    ]
    with pytest.raises(IntrabarExecutionError, match="positive-volume terminal"):
        simulate_protocol_v3_intrabar_strategy(
            zero_terminal,
            _strategy(stop_loss_bps=500, take_profit_bps=500),
            days=1,
            exchange_info_snapshot=_snapshot(),
        )
