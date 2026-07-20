"""Incremental order-free runtime adapter over the exact Task-8 execution core.

This module does not implement a second fill model.  It persists the minimum
state around the existing Task-8 private primitives so a forward-only controller
can stop and resume without terminal liquidation while retaining identical
entry, exit, rounding, fee, slippage, and mark-to-market calculations.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from ethusdc_bot.backtest.context_features import ContextDecision
from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS
from ethusdc_bot.backtest.equity import EquityPoint
from ethusdc_bot.backtest.simulator import EntryDecision, StrategyCandidate, _entry_decision
from ethusdc_bot.protocol_v3.execution_parity import (
    MarketEntryExecution,
    build_market_execution_rules,
    load_execution_parity_contract,
)
from ethusdc_bot.protocol_v3.intrabar_execution import (
    BASELINE_COST_PROFILE,
    ExecutionCostProfile,
    IntrabarExecutionError,
    ProtocolV3IntrabarPortfolioTrade,
    _OpenPosition,
    _advance_completed_bar_state,
    _close_position,
    _decimal,
    _exit_decision,
    _float10,
    _open_liquidation_pnl,
    _open_position,
    _validate_cost_profile,
    _validate_horizon_policy,
    _validate_inputs,
    load_intrabar_execution_contract,
)
from ethusdc_bot.protocol_v3.run_identity import FrozenExchangeInfoSnapshot
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy


class IntrabarRuntimeError(ValueError):
    """Raised when incremental Task-8 state cannot remain exact and causal."""


@dataclass(frozen=True)
class IntrabarRuntimeEvent:
    event_type: str
    candle_open_time_ms: int
    trade: ProtocolV3IntrabarPortfolioTrade | None = None
    reason: str | None = None


@dataclass(frozen=True)
class IntrabarRuntimeState:
    candles: tuple[Candle, ...] = ()
    position: _OpenPosition | None = None
    pending_signal_time: int | None = None
    pending_signal_index: int | None = None
    cooldown_until_index: int = -1
    realized_net_usdc: Decimal = Decimal("0")
    trades: tuple[ProtocolV3IntrabarPortfolioTrade, ...] = ()
    equity_curve: tuple[EquityPoint, ...] = ()
    rejection_reasons: tuple[tuple[str, int], ...] = ()
    signal_funnel: tuple[tuple[str, int], ...] = ()
    max_executed_entry_exposure_usdc: Decimal = Decimal("0")
    max_reserved_notional_usdc: Decimal = Decimal("0")
    max_concurrent_lots: int = 0
    next_lot_sequence: int = 1

    @property
    def open_lot_count(self) -> int:
        return 1 if self.position is not None else 0

    @property
    def pending_entry(self) -> bool:
        return self.pending_signal_time is not None

    @property
    def closing_equity_usdc(self) -> float:
        return self.equity_curve[-1].equity_usdc if self.equity_curve else 0.0


def new_intrabar_runtime_state() -> IntrabarRuntimeState:
    return IntrabarRuntimeState()


def discard_pending_entry(state: IntrabarRuntimeState) -> IntrabarRuntimeState:
    validated = validate_intrabar_runtime_state(state)
    if validated.pending_signal_time is None:
        return validated
    funnel = Counter(dict(validated.signal_funnel))
    funnel["discarded.entry_window_closed"] += 1
    return IntrabarRuntimeState(
        **{
            **vars(validated),
            "pending_signal_time": None,
            "pending_signal_index": None,
            "signal_funnel": _counter_items(funnel),
        }
    )


def advance_intrabar_runtime(
    state: IntrabarRuntimeState,
    candle: Candle,
    strategy: StrategyCandidate,
    *,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    horizon_policy: HorizonPolicy,
    context_decision: ContextDecision,
    entry_allowed: bool,
    cost_profile: ExecutionCostProfile = BASELINE_COST_PROFILE,
) -> tuple[IntrabarRuntimeState, tuple[IntrabarRuntimeEvent, ...]]:
    """Reduce exactly one closed 1m bar without any end-of-feed liquidation."""

    current = validate_intrabar_runtime_state(state)
    if not isinstance(entry_allowed, bool):
        raise IntrabarRuntimeError("entry_allowed must be boolean")
    if not isinstance(context_decision, ContextDecision):
        raise IntrabarRuntimeError("a canonical closed context decision is required")
    load_execution_parity_contract()
    load_intrabar_execution_contract()
    profile = _validate_cost_profile(cost_profile)
    _validate_inputs([candle], strategy, None)
    horizons = _validate_horizon_policy(horizon_policy, strategy)
    rules = build_market_execution_rules(exchange_info_snapshot)
    if current.candles:
        expected = current.candles[-1].open_time + EXPECTED_STEP_MS
        if candle.open_time != expected:
            raise IntrabarRuntimeError(
                "incremental Task-8 candles must be contiguous and unique"
            )
    if context_decision.open_time != candle.open_time:
        raise IntrabarRuntimeError("context decision does not match the trade bar")
    if context_decision.may_create_signal or context_decision.may_submit_order:
        raise IntrabarRuntimeError("context may only confirm or veto an ETHUSDC signal")

    candles = (*current.candles, candle)
    index = len(candles) - 1
    position = current.position
    pending_time = current.pending_signal_time
    pending_index = current.pending_signal_index
    cooldown = current.cooldown_until_index
    realized = current.realized_net_usdc
    trades = list(current.trades)
    rejections = Counter(dict(current.rejection_reasons))
    funnel = Counter(dict(current.signal_funnel))
    max_exposure = current.max_executed_entry_exposure_usdc
    max_reserved = current.max_reserved_notional_usdc
    max_concurrent = current.max_concurrent_lots
    next_lot = current.next_lot_sequence
    events: list[IntrabarRuntimeEvent] = []
    funnel["observations_total"] += 1

    if not entry_allowed and pending_time is not None:
        pending_time = None
        pending_index = None
        funnel["discarded.entry_window_closed"] += 1
        events.append(
            IntrabarRuntimeEvent(
                "pending_entry_discarded",
                candle.open_time,
                reason="entry_window_closed_or_context_vetoed",
            )
        )

    if pending_time is not None and position is None:
        if pending_index is None:
            raise IntrabarRuntimeError("pending entry lacks its signal index")
        max_reserved = max(max_reserved, Decimal("100"))
        latency = index - pending_index
        if latency > horizons.pending_entry_latency_minutes:
            pending_time = None
            pending_index = None
            rejections["pending_entry_latency_expired"] += 1
            funnel["discarded.pending_entry_latency_expired"] += 1
            events.append(
                IntrabarRuntimeEvent(
                    "pending_entry_discarded",
                    candle.open_time,
                    reason="pending_entry_latency_expired",
                )
            )
        elif candle.volume > 0:
            position = _open_position(
                candle,
                index,
                pending_time,
                strategy,
                rules,
                profile,
            )
            pending_time = None
            pending_index = None
            max_exposure = max(
                max_exposure,
                position.entry.executed_entry_notional,
            )
            max_concurrent = 1
            funnel["executed_entries"] += 1
            events.append(IntrabarRuntimeEvent("hypothetical_entry", candle.open_time))
        else:
            funnel["blocked.zero_volume_pending_entry"] += 1

    exited = False
    if position is not None and candle.volume > 0:
        exit_decision = _exit_decision(
            candle,
            index,
            position,
            strategy,
            rules,
            profile,
        )
        if exit_decision is not None:
            base_trade = _close_position(position, exit_decision, rules, profile)
            trade = ProtocolV3IntrabarPortfolioTrade(
                **vars(base_trade),
                lot_id=f"lot-{next_lot:08d}",
                entry_notional_usdc=100.0,
            )
            next_lot += 1
            trades.append(trade)
            realized += _decimal(
                trade.net_profit_usdc,
                "trade.net_profit_usdc",
                allow_negative=True,
                allow_zero=True,
            )
            position = None
            exited = True
            cooldown = index + int(strategy.params.get("cooldown_minutes", 0) or 0)
            funnel[f"exits.{trade.exit_reason}"] += 1
            events.append(
                IntrabarRuntimeEvent(
                    "hypothetical_exit",
                    candle.open_time,
                    trade=trade,
                )
            )

    if position is not None and not exited and candle.volume > 0:
        _advance_completed_bar_state(position, candle, rules)

    if position is not None:
        funnel["blocked.position_open"] += 1
    elif pending_time is not None:
        funnel["blocked.pending_entry"] += 1
    elif not entry_allowed:
        funnel["blocked.entry_not_allowed"] += 1
    elif index < cooldown:
        funnel["blocked.cooldown"] += 1
    else:
        funnel["entry_evaluations"] += 1
        entry_decision = _contextual_entry_decision(
            candles,
            index,
            strategy,
            context_decision,
        )
        if entry_decision.raw_signal:
            funnel["raw_entry_signals"] += 1
        if entry_decision.allowed:
            funnel["accepted_entry_signals"] += 1
            pending_time = candle.open_time + EXPECTED_STEP_MS - 1
            pending_index = index
            max_reserved = max(max_reserved, Decimal("100"))
            events.append(IntrabarRuntimeEvent("entry_scheduled", candle.open_time))
        else:
            reason = entry_decision.reason or "entry_signal_absent"
            rejections[reason] += 1
            funnel["rejected_signals"] += 1
            funnel[f"rejected.{reason}"] += 1

    equity = realized
    if position is not None:
        equity += _open_liquidation_pnl(position, candle.close, rules, profile)
    curve = current.equity_curve
    if not curve:
        curve = (EquityPoint(candle.open_time, 0.0),)
    curve = (
        *curve,
        EquityPoint(candle.open_time + EXPECTED_STEP_MS - 1, _float10(equity)),
    )
    next_state = IntrabarRuntimeState(
        candles=candles,
        position=position,
        pending_signal_time=pending_time,
        pending_signal_index=pending_index,
        cooldown_until_index=cooldown,
        realized_net_usdc=realized,
        trades=tuple(trades),
        equity_curve=curve,
        rejection_reasons=_counter_items(rejections),
        signal_funnel=_counter_items(funnel),
        max_executed_entry_exposure_usdc=max_exposure,
        max_reserved_notional_usdc=max_reserved,
        max_concurrent_lots=max_concurrent,
        next_lot_sequence=next_lot,
    )
    return validate_intrabar_runtime_state(next_state), tuple(events)


def validate_intrabar_runtime_state(state: IntrabarRuntimeState) -> IntrabarRuntimeState:
    if not isinstance(state, IntrabarRuntimeState):
        raise IntrabarRuntimeError("IntrabarRuntimeState is required")
    if state.pending_signal_time is None and state.pending_signal_index is not None:
        raise IntrabarRuntimeError("pending signal index exists without a signal")
    if state.pending_signal_time is not None and state.pending_signal_index is None:
        raise IntrabarRuntimeError("pending signal lacks its index")
    if state.position is not None and state.pending_signal_time is not None:
        raise IntrabarRuntimeError("one-lot runtime cannot be open and pending together")
    previous: int | None = None
    for candle in state.candles:
        if not isinstance(candle, Candle):
            raise IntrabarRuntimeError("runtime candle history is invalid")
        if previous is not None and candle.open_time != previous + EXPECTED_STEP_MS:
            raise IntrabarRuntimeError("runtime candle history contains a gap")
        previous = candle.open_time
    if state.position is not None:
        if not state.candles or state.position.entry_index >= len(state.candles):
            raise IntrabarRuntimeError("runtime open position index is invalid")
    if state.next_lot_sequence != len(state.trades) + 1:
        raise IntrabarRuntimeError("runtime lot sequence differs from completed trades")
    for rows, label in (
        (state.rejection_reasons, "rejection_reasons"),
        (state.signal_funnel, "signal_funnel"),
    ):
        if tuple(sorted(rows)) != rows or len({key for key, _ in rows}) != len(rows):
            raise IntrabarRuntimeError(f"runtime {label} is not canonical")
        if any(not isinstance(key, str) or type(value) is not int or value < 0 for key, value in rows):
            raise IntrabarRuntimeError(f"runtime {label} contains invalid values")
    if state.max_concurrent_lots not in (0, 1):
        raise IntrabarRuntimeError("runtime exceeded one concurrent lot")
    if any(
        value < 0
        for value in (
            state.max_executed_entry_exposure_usdc,
            state.max_reserved_notional_usdc,
        )
    ):
        raise IntrabarRuntimeError("runtime exposure metrics must be non-negative")
    return state


def intrabar_runtime_state_payload(state: IntrabarRuntimeState) -> dict[str, Any]:
    current = validate_intrabar_runtime_state(state)
    return {
        "candles": [asdict(candle) for candle in current.candles],
        "position": _position_payload(current.position),
        "pending_signal_time": current.pending_signal_time,
        "pending_signal_index": current.pending_signal_index,
        "cooldown_until_index": current.cooldown_until_index,
        "realized_net_usdc": str(current.realized_net_usdc),
        "trades": [asdict(trade) for trade in current.trades],
        "equity_curve": [asdict(point) for point in current.equity_curve],
        "rejection_reasons": dict(current.rejection_reasons),
        "signal_funnel": dict(current.signal_funnel),
        "max_executed_entry_exposure_usdc": str(
            current.max_executed_entry_exposure_usdc
        ),
        "max_reserved_notional_usdc": str(current.max_reserved_notional_usdc),
        "max_concurrent_lots": current.max_concurrent_lots,
        "next_lot_sequence": current.next_lot_sequence,
    }


def restore_intrabar_runtime_state(value: Mapping[str, Any]) -> IntrabarRuntimeState:
    if not isinstance(value, Mapping):
        raise IntrabarRuntimeError("runtime payload must be an object")
    required = {
        "candles",
        "position",
        "pending_signal_time",
        "pending_signal_index",
        "cooldown_until_index",
        "realized_net_usdc",
        "trades",
        "equity_curve",
        "rejection_reasons",
        "signal_funnel",
        "max_executed_entry_exposure_usdc",
        "max_reserved_notional_usdc",
        "max_concurrent_lots",
        "next_lot_sequence",
    }
    if set(value) != required:
        raise IntrabarRuntimeError("runtime payload fields are invalid")
    try:
        state = IntrabarRuntimeState(
            candles=tuple(Candle(**row) for row in value["candles"]),
            position=_restore_position(value["position"]),
            pending_signal_time=value["pending_signal_time"],
            pending_signal_index=value["pending_signal_index"],
            cooldown_until_index=value["cooldown_until_index"],
            realized_net_usdc=Decimal(str(value["realized_net_usdc"])),
            trades=tuple(
                ProtocolV3IntrabarPortfolioTrade(**row) for row in value["trades"]
            ),
            equity_curve=tuple(EquityPoint(**row) for row in value["equity_curve"]),
            rejection_reasons=_mapping_counter(value["rejection_reasons"]),
            signal_funnel=_mapping_counter(value["signal_funnel"]),
            max_executed_entry_exposure_usdc=Decimal(
                str(value["max_executed_entry_exposure_usdc"])
            ),
            max_reserved_notional_usdc=Decimal(
                str(value["max_reserved_notional_usdc"])
            ),
            max_concurrent_lots=value["max_concurrent_lots"],
            next_lot_sequence=value["next_lot_sequence"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise IntrabarRuntimeError("runtime payload is invalid") from exc
    return validate_intrabar_runtime_state(state)


def _contextual_entry_decision(
    candles: tuple[Candle, ...],
    index: int,
    strategy: StrategyCandidate,
    context: ContextDecision,
) -> EntryDecision:
    base = _entry_decision(
        list(candles),
        index,
        strategy,
        market_context=None,
        context_policy=None,
    )
    if not base.raw_signal:
        return base
    if not base.allowed and base.reason != "context_data_missing":
        return base
    return EntryDecision(
        allowed=context.allowed,
        raw_signal=True,
        reason=None if context.allowed else context.reason,
    )


def _counter_items(counter: Counter[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((str(key), int(value)) for key, value in counter.items()))


def _mapping_counter(value: Any) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, Mapping):
        raise IntrabarRuntimeError("runtime counter must be an object")
    rows = []
    for key, count in value.items():
        if not isinstance(key, str) or type(count) is not int or count < 0:
            raise IntrabarRuntimeError("runtime counter contains invalid values")
        rows.append((key, count))
    return tuple(sorted(rows))


def _position_payload(position: _OpenPosition | None) -> dict[str, Any] | None:
    if position is None:
        return None
    return {
        "signal_time": position.signal_time,
        "entry_time": position.entry_time,
        "entry_index": position.entry_index,
        "entry_reference_price": str(position.entry_reference_price),
        "entry_fill_price": str(position.entry_fill_price),
        "entry": {key: str(value) for key, value in asdict(position.entry).items()},
        "initial_stop_price": str(position.initial_stop_price),
        "target_price": str(position.target_price),
        "break_even_trigger_price": (
            None
            if position.break_even_trigger_price is None
            else str(position.break_even_trigger_price)
        ),
        "trailing_stop_bps": str(position.trailing_stop_bps),
        "high_watermark_price": str(position.high_watermark_price),
        "active_stop_price": str(position.active_stop_price),
        "active_stop_source": position.active_stop_source,
    }


def _restore_position(value: Any) -> _OpenPosition | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise IntrabarRuntimeError("runtime position must be an object or null")
    required = {
        "signal_time",
        "entry_time",
        "entry_index",
        "entry_reference_price",
        "entry_fill_price",
        "entry",
        "initial_stop_price",
        "target_price",
        "break_even_trigger_price",
        "trailing_stop_bps",
        "high_watermark_price",
        "active_stop_price",
        "active_stop_source",
    }
    if set(value) != required or not isinstance(value["entry"], Mapping):
        raise IntrabarRuntimeError("runtime position fields are invalid")
    entry_required = set(MarketEntryExecution.__dataclass_fields__)
    if set(value["entry"]) != entry_required:
        raise IntrabarRuntimeError("runtime entry execution fields are invalid")
    return _OpenPosition(
        signal_time=int(value["signal_time"]),
        entry_time=int(value["entry_time"]),
        entry_index=int(value["entry_index"]),
        entry_reference_price=Decimal(str(value["entry_reference_price"])),
        entry_fill_price=Decimal(str(value["entry_fill_price"])),
        entry=MarketEntryExecution(
            **{key: Decimal(str(raw)) for key, raw in value["entry"].items()}
        ),
        initial_stop_price=Decimal(str(value["initial_stop_price"])),
        target_price=Decimal(str(value["target_price"])),
        break_even_trigger_price=(
            None
            if value["break_even_trigger_price"] is None
            else Decimal(str(value["break_even_trigger_price"]))
        ),
        trailing_stop_bps=Decimal(str(value["trailing_stop_bps"])),
        high_watermark_price=Decimal(str(value["high_watermark_price"])),
        active_stop_price=Decimal(str(value["active_stop_price"])),
        active_stop_source=str(value["active_stop_source"]),
    )


__all__ = [
    "IntrabarRuntimeError",
    "IntrabarRuntimeEvent",
    "IntrabarRuntimeState",
    "advance_intrabar_runtime",
    "discard_pending_entry",
    "intrabar_runtime_state_payload",
    "new_intrabar_runtime_state",
    "restore_intrabar_runtime_state",
    "validate_intrabar_runtime_state",
]
