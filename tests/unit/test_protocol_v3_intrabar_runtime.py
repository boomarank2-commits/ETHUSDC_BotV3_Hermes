"""Golden-trade parity for the incremental Task-8 runtime adapter."""
from __future__ import annotations

from dataclasses import asdict
import importlib.util
from pathlib import Path

from ethusdc_bot.backtest.context_features import CONTEXT_POLICY_VERSION, ContextDecision
from ethusdc_bot.protocol_v3 import intrabar_runtime
from ethusdc_bot.protocol_v3.intrabar_execution import (
    simulate_protocol_v3_intrabar_portfolio_strategy,
)
from ethusdc_bot.portfolio import PortfolioPolicy

_TASK8_PATH = Path(__file__).with_name("test_protocol_v3_intrabar_execution.py")
_SPEC8 = importlib.util.spec_from_file_location(
    "protocol_v3_task29_task8_support", _TASK8_PATH
)
assert _SPEC8 is not None and _SPEC8.loader is not None
task8 = importlib.util.module_from_spec(_SPEC8)
_SPEC8.loader.exec_module(task8)


def _allowed(index: int, candle) -> ContextDecision:
    return ContextDecision(
        allowed=True,
        reason="context_confirmed",
        index=index,
        open_time=candle.open_time,
        policy_version=CONTEXT_POLICY_VERSION,
        btc_trend_bps=1.0,
        btc_volatility_bps=1.0,
        ethbtc_trend_bps=1.0,
    )


def test_incremental_runtime_trade_is_bit_identical_to_task8_golden_trade() -> None:
    candles = [
        task8._candle(0, open_=100, high=100.1, low=99.9, close=100),
        task8._candle(1, open_=100, high=102, low=98, close=100),
    ]
    strategy = task8._strategy()
    snapshot = task8._snapshot()
    finite = simulate_protocol_v3_intrabar_portfolio_strategy(
        candles,
        strategy,
        days=1,
        policy=PortfolioPolicy(100),
        exchange_info_snapshot=snapshot,
        horizon_policy=task8.HORIZON_POLICY,
    )

    state = intrabar_runtime.new_intrabar_runtime_state()
    for index, candle in enumerate(candles):
        state, _ = intrabar_runtime.advance_intrabar_runtime(
            state,
            candle,
            strategy,
            exchange_info_snapshot=snapshot,
            horizon_policy=task8.HORIZON_POLICY,
            context_decision=_allowed(index, candle),
            entry_allowed=True,
        )

    assert len(state.trades) == 1
    assert asdict(state.trades[0]) == asdict(finite.trades[0])
    assert state.closing_equity_usdc == finite.equity_curve[-1].equity_usdc
    assert state.position is None
    assert state.pending_signal_time is None


def test_incremental_runtime_roundtrips_open_position_without_liquidation() -> None:
    candles = [
        task8._candle(0, open_=100, high=100.1, low=99.9, close=100),
        task8._candle(1, open_=100, high=100.2, low=99.5, close=100),
    ]
    strategy = task8._strategy(stop_loss_bps=500, take_profit_bps=500)
    snapshot = task8._snapshot()
    state = intrabar_runtime.new_intrabar_runtime_state()
    for index, candle in enumerate(candles):
        state, _ = intrabar_runtime.advance_intrabar_runtime(
            state,
            candle,
            strategy,
            exchange_info_snapshot=snapshot,
            horizon_policy=task8.HORIZON_POLICY,
            context_decision=_allowed(index, candle),
            entry_allowed=True,
        )

    assert state.position is not None
    assert state.trades == ()
    restored = intrabar_runtime.restore_intrabar_runtime_state(
        intrabar_runtime.intrabar_runtime_state_payload(state)
    )
    assert intrabar_runtime.intrabar_runtime_state_payload(restored) == (
        intrabar_runtime.intrabar_runtime_state_payload(state)
    )
    assert restored.position is not None
    assert restored.position.entry.executed_entry_notional <= 100


def test_context_veto_and_entry_window_cannot_create_a_pending_fill() -> None:
    candle = task8._candle(0, open_=100, high=100.1, low=99.9, close=100)
    strategy = task8._strategy()
    snapshot = task8._snapshot()
    veto = ContextDecision(
        allowed=False,
        reason="btc_context_veto",
        index=0,
        open_time=candle.open_time,
        policy_version=CONTEXT_POLICY_VERSION,
        btc_trend_bps=-100.0,
        btc_volatility_bps=1.0,
        ethbtc_trend_bps=1.0,
    )

    state, events = intrabar_runtime.advance_intrabar_runtime(
        intrabar_runtime.new_intrabar_runtime_state(),
        candle,
        strategy,
        exchange_info_snapshot=snapshot,
        horizon_policy=task8.HORIZON_POLICY,
        context_decision=veto,
        entry_allowed=True,
    )
    assert state.pending_signal_time is None
    assert all(event.event_type != "entry_scheduled" for event in events)

    state, events = intrabar_runtime.advance_intrabar_runtime(
        intrabar_runtime.new_intrabar_runtime_state(),
        candle,
        strategy,
        exchange_info_snapshot=snapshot,
        horizon_policy=task8.HORIZON_POLICY,
        context_decision=_allowed(0, candle),
        entry_allowed=False,
    )
    assert state.pending_signal_time is None
    assert events == ()
