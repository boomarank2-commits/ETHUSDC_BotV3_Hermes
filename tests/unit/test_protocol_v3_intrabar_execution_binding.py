"""Additional Task-8 state and pipeline-binding regression tests."""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3.intrabar_execution import (
    ExecutionCostProfile,
    IntrabarExecutionError,
    simulate_protocol_v3_intrabar_strategy,
)
from ethusdc_bot.protocol_v3.pipeline import (
    PIPELINE_CONTRACT_PATH,
    build_pipeline_generation,
)
from ethusdc_bot.protocol_v3.run_identity import build_exchange_info_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]


def _snapshot():
    return build_exchange_info_snapshot(
        {
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
                    ],
                }
            ]
        },
        snapshot_as_of_utc="2026-07-07T23:59:59Z",
    )


def _candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(index * 60_000, open_, high, low, close, 10.0)


def _strategy() -> StrategyCandidate:
    return StrategyCandidate(
        "always_long",
        {
            "side": "LONG",
            "symbol": "ETHUSDC",
            "stop_loss_bps": 500,
            "take_profit_bps": 1000,
            "trailing_stop_bps": 100,
            "break_even_after_bps": 0,
            "max_hold_minutes": 10,
            "cooldown_minutes": 10,
        },
    )


def test_trailing_stop_uses_only_the_previous_survived_bar_high() -> None:
    result = simulate_protocol_v3_intrabar_strategy(
        [
            _candle(0, 100, 100.1, 99.9, 100),
            _candle(1, 100, 102, 99.5, 101.5),
            _candle(2, 101.2, 101.3, 100.9, 101),
        ],
        _strategy(),
        days=1,
        exchange_info_snapshot=_snapshot(),
    )
    trade = result.trades[0]
    assert trade.entry_time == 60_000
    assert trade.exit_time == 120_000
    assert trade.exit_reason == "trailing_stop"
    assert trade.active_stop_source == "trailing_stop"
    assert trade.active_stop_price == 100.98
    assert trade.exit_reference_price == 100.98
    assert trade.exit_price == 100.92


def test_task8_sources_remain_bound_inside_the_task9_pipeline_identity() -> None:
    basis = build_pipeline_generation(REPO_ROOT).basis()
    assert (
        basis["component_contracts"]["simulator"]
        == "next_tradable_price_pessimistic_intrabar_with_fold_outer_state_v1"
    )
    assert (
        basis["component_contracts"]["cost_model"]
        == "protocol_v3_actual_notional_baseline_and_stress_costs_v1"
    )
    contract = json.loads(
        (REPO_ROOT / PIPELINE_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    assert (
        "configs/protocol_v3_intrabar_execution_contract.json"
        in contract["source_bindings"]["simulator"]
    )
    assert (
        "src/ethusdc_bot/protocol_v3/intrabar_execution.py"
        in contract["source_bindings"]["simulator"]
    )
    assert (
        "src/ethusdc_bot/protocol_v3/runtime_state.py"
        in contract["source_bindings"]["simulator"]
    )
    assert len(basis["component_source_sha256"]["simulator"]) == 64
    assert len(basis["component_source_sha256"]["cost_model"]) == 64


def test_noncanonical_cost_profile_cannot_enter_the_shared_engine() -> None:
    with pytest.raises(IntrabarExecutionError, match="not canonical"):
        simulate_protocol_v3_intrabar_strategy(
            [
                _candle(0, 100, 100.1, 99.9, 100),
                _candle(1, 100, 101, 99, 100),
            ],
            _strategy(),
            days=1,
            exchange_info_snapshot=_snapshot(),
            cost_profile=ExecutionCostProfile(
                "baseline", Decimal("9"), Decimal("5")
            ),
        )
