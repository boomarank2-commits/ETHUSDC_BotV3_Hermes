"""Deterministic fixed-lot ETHUSDC portfolio simulation core.

The reducer in this module is shared by offline portfolio backtests and the
order-free Shadow replay engine.  It deliberately reuses the single-position
simulator's signal, exit, and execution functions so both paths have one cost
and timing model.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from math import isclose

from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS, SYMBOL
from ethusdc_bot.backtest.equity import (
    EquityPoint,
    max_drawdown_usdc,
    max_underwater_calendar_days,
)
from ethusdc_bot.backtest.metrics import BacktestMetrics, compute_metrics
from ethusdc_bot.backtest.simulator import (
    StrategyCandidate,
    Trade,
    _exit_reason,
    _exit_trade,
    _signal,
)
from ethusdc_bot.portfolio import PortfolioPolicy


FULL_RETENTION_PROFILE = "full"
BOUNDED_SHADOW_RETENTION_PROFILE = "bounded_shadow_v1"
MAX_BOUNDED_HISTORY_CANDLES = 10_081
STRATEGY_HISTORY_MARGIN_CANDLES = 1


@dataclass(frozen=True)
class PortfolioTrade(Trade):
    """A normal simulator trade with its fixed-lot portfolio identity."""

    lot_id: str = ""
    entry_notional_usdc: float = 100.0


@dataclass(frozen=True)
class PortfolioLot:
    """Internal immutable representation of one open 100-USDC LONG lot."""

    lot_id: str
    signal_time_ms: int
    entry_time_ms: int
    entry_mid_price: float
    entry_price: float
    quantity: float
    entry_index: int
    entry_fee_usdc: float
    entry_notional_usdc: float

    def as_simulator_position(self) -> dict[str, float | int]:
        return {
            "entry_mid_price": self.entry_mid_price,
            "entry_price": self.entry_price,
            "quantity": self.quantity,
            "entry_time": self.entry_time_ms,
            "entry_index": self.entry_index,
            "entry_fee_usdc": self.entry_fee_usdc,
        }


@dataclass(frozen=True)
class PendingPortfolioEntry:
    """A signal whose entry is reserved for the next candle open."""

    signal_time_ms: int


@dataclass(frozen=True)
class CapacityRejection:
    """Audit record for a signal rejected by the manual deployment budget."""

    signal_time_ms: int
    open_lots: int
    pending_entries: int
    reserved_notional_usdc: float
    deployment_budget_usdc: int
    reason: str = "deployment_budget_capacity"


@dataclass(frozen=True)
class PortfolioStepEvent:
    """Pure event emitted by one portfolio reducer step."""

    event_type: str
    candle_open_time_ms: int
    lot_id: str | None = None
    trade: PortfolioTrade | None = None
    rejection: CapacityRejection | None = None


@dataclass(frozen=True)
class PortfolioEngineState:
    """Complete deterministic reducer state; contains no external handles."""

    candles: tuple[Candle, ...] = ()
    open_lots: tuple[PortfolioLot, ...] = ()
    pending_entry: PendingPortfolioEntry | None = None
    cooldown_until_index: int = -1
    realized_net_usdc: float = 0.0
    trades: tuple[PortfolioTrade, ...] = ()
    capacity_rejections: tuple[CapacityRejection, ...] = ()
    equity_curve: tuple[EquityPoint, ...] = ()
    next_lot_sequence: int = 1
    max_concurrent_lots: int = 0
    max_open_entry_exposure_usdc: float = 0.0
    max_reserved_notional_usdc: float = 0.0
    retention_profile: str = FULL_RETENTION_PROFILE
    retained_history_limit: int | None = None
    history_start_index: int = 0
    total_processed_candles: int = 0

    @property
    def reserved_lots(self) -> int:
        return len(self.open_lots) + (1 if self.pending_entry is not None else 0)


@dataclass(frozen=True)
class PortfolioSimulationResult:
    """Auditable result of a fixed-lot portfolio simulation."""

    strategy: StrategyCandidate
    policy: PortfolioPolicy
    metrics: BacktestMetrics
    trades: list[PortfolioTrade]
    rejection_reasons: Counter[str] = field(default_factory=Counter)
    capacity_rejections: tuple[CapacityRejection, ...] = ()
    equity_curve: tuple[EquityPoint, ...] = ()
    max_underwater_days: int = 0
    max_concurrent_lots: int = 0
    max_open_entry_exposure_usdc: float = 0.0
    max_reserved_notional_usdc: float = 0.0
    drawdown_method: str = "mark_to_market_portfolio_liquidation"

    @property
    def net_profit_usdc(self) -> float:
        return self.metrics.net_profit_usdc

    @property
    def net_usdc_per_day(self) -> float:
        return self.metrics.net_usdc_per_day

    @property
    def trade_count(self) -> int:
        return self.metrics.trade_count

    @property
    def fees_usdc(self) -> float:
        return self.metrics.fees_usdc

    @property
    def slippage_usdc(self) -> float:
        return self.metrics.slippage_usdc

    @property
    def max_drawdown_usdc(self) -> float:
        return self.metrics.max_drawdown_usdc

    @property
    def equity_curve_usdc(self) -> list[float]:
        return [point.equity_usdc for point in self.equity_curve]

    @property
    def equity_curve_timestamps_ms(self) -> list[int]:
        return [point.timestamp_ms for point in self.equity_curve]


def new_portfolio_engine_state() -> PortfolioEngineState:
    """Return an empty reducer state for backtest or Shadow replay."""

    return PortfolioEngineState()


def required_strategy_history_candles(strategy: StrategyCandidate) -> int:
    """Return the exact bounded history required by the shared strategy rules.

    Signals need the current candle plus their longest configured lookback.
    Open-lot exit rules additionally need every close since entry until the
    configured time exit.  The single-candle margin accounts for the current
    candle in both cases.
    """

    if not isinstance(strategy, StrategyCandidate):
        raise TypeError("strategy must be a StrategyCandidate")
    params = strategy.params
    lookback = _positive_history_parameter(params, "lookback", 5)
    trend_lookback = _positive_history_parameter(
        params, "trend_lookback", lookback
    )
    volatility_lookback = _positive_history_parameter(
        params, "volatility_lookback", lookback
    )
    max_hold = _positive_history_parameter(params, "max_hold_minutes", 30)
    required = (
        max(lookback, trend_lookback, volatility_lookback, max_hold)
        + STRATEGY_HISTORY_MARGIN_CANDLES
    )
    if required > MAX_BOUNDED_HISTORY_CANDLES:
        raise ValueError(
            "bounded Shadow strategy history exceeds the hard 10081-candle limit"
        )
    return required


def compact_portfolio_engine_for_bounded_shadow(
    state: PortfolioEngineState,
    strategy: StrategyCandidate,
) -> PortfolioEngineState:
    """Select bounded Shadow retention and compact a full reducer state.

    This operation is explicit so pre-existing event logs continue to replay
    with the legacy full-retention digest until the runtime records a profile
    selection marker.  Forward-relevant state is preserved; historical trades,
    capacity rejections, and equity samples remain available in the event log.
    """

    if not isinstance(state, PortfolioEngineState):
        raise TypeError("state must be a PortfolioEngineState")
    limit = required_strategy_history_candles(strategy)
    _validate_retention_state(state, strategy=None)
    if state.retention_profile == BOUNDED_SHADOW_RETENTION_PROFILE:
        if state.retained_history_limit != limit:
            raise ValueError(
                "bounded Shadow retention does not match the active strategy"
            )
        return state

    trim_count = max(0, len(state.candles) - limit)
    history_start_index = state.history_start_index + trim_count
    _ensure_open_lot_history_is_retained(state.open_lots, history_start_index)
    curve = state.equity_curve[-1:] if state.equity_curve else ()
    return replace(
        state,
        candles=state.candles[trim_count:],
        trades=(),
        capacity_rejections=(),
        equity_curve=curve,
        retention_profile=BOUNDED_SHADOW_RETENTION_PROFILE,
        retained_history_limit=limit,
        history_start_index=history_start_index,
    )


def advance_portfolio_engine(
    state: PortfolioEngineState,
    candle: Candle,
    strategy: StrategyCandidate,
    policy: PortfolioPolicy,
    *,
    end_of_data: bool = False,
) -> tuple[PortfolioEngineState, tuple[PortfolioStepEvent, ...]]:
    """Advance the common portfolio reducer by exactly one closed candle.

    Signals are evaluated on the candle close and reserve at most one entry.
    That reservation is executed on the next candle open.  ``end_of_data`` is
    reserved for finite offline backtests; Shadow replay never sets it merely
    because a feed is stopped.
    """

    _validate_context(strategy, policy)
    if not isinstance(state, PortfolioEngineState):
        raise TypeError("state must be a PortfolioEngineState")
    if not isinstance(candle, Candle):
        raise TypeError("candle must be a Candle")
    _validate_retention_state(state, strategy=strategy)
    _validate_next_candle_timestamp(state, candle)

    candles = (*state.candles, candle)
    local_index = len(candles) - 1
    global_index = state.total_processed_candles
    fee_rate = policy.baseline_fee_bps_per_side / 10_000
    slippage_bps = policy.baseline_slippage_bps_per_side
    lots = list(state.open_lots)
    pending = state.pending_entry
    realized = state.realized_net_usdc
    trades = list(state.trades)
    rejections = list(state.capacity_rejections)
    events: list[PortfolioStepEvent] = []
    next_lot_sequence = state.next_lot_sequence
    cooldown_until_index = state.cooldown_until_index
    max_concurrent = state.max_concurrent_lots
    max_open_exposure = state.max_open_entry_exposure_usdc
    max_reserved = state.max_reserved_notional_usdc

    if pending is not None:
        if len(lots) >= policy.max_concurrent_lots:
            raise RuntimeError("reserved portfolio entry exceeds deployment capacity")
        entry_mid_price = candle.open
        entry_price = entry_mid_price * (1 + slippage_bps / 10_000)
        quantity = policy.lot_notional_usdc / entry_price
        lot = PortfolioLot(
            lot_id=f"lot-{next_lot_sequence:08d}",
            signal_time_ms=pending.signal_time_ms,
            entry_time_ms=candle.open_time,
            entry_mid_price=entry_mid_price,
            entry_price=entry_price,
            quantity=quantity,
            entry_index=global_index,
            entry_fee_usdc=entry_price * quantity * fee_rate,
            entry_notional_usdc=policy.lot_notional_usdc,
        )
        lots.append(lot)
        # Record the fill before exits are evaluated.  A lot can legitimately
        # fill and exit on the final reducer step, but it still consumed the
        # deployment budget at that open.
        max_concurrent = max(max_concurrent, len(lots))
        max_open_exposure = max(
            max_open_exposure, len(lots) * policy.lot_notional_usdc
        )
        next_lot_sequence += 1
        pending = None
        events.append(
            PortfolioStepEvent("hypothetical_entry", candle.open_time, lot_id=lot.lot_id)
        )

    remaining: list[PortfolioLot] = []
    exited_normally = False
    for lot in lots:
        position = lot.as_simulator_position()
        position["entry_index"] = lot.entry_index - state.history_start_index
        reason = _exit_reason(candles, local_index, position, strategy)
        if reason is None:
            remaining.append(lot)
            continue
        trade = _portfolio_exit_trade(
            candle, lot, fee_rate, slippage_bps, exit_reason=reason
        )
        trades.append(trade)
        realized = round(realized + trade.net_profit_usdc, 10)
        exited_normally = True
        events.append(
            PortfolioStepEvent(
                "hypothetical_exit",
                candle.open_time,
                lot_id=lot.lot_id,
                trade=trade,
            )
        )
    lots = remaining
    if exited_normally:
        cooldown_until_index = global_index + int(
            strategy.params.get("cooldown_minutes", 0) or 0
        )

    if end_of_data and lots:
        for lot in lots:
            trade = _portfolio_exit_trade(
                candle,
                lot,
                fee_rate,
                slippage_bps,
                exit_reason="end_of_data",
            )
            trades.append(trade)
            realized = round(realized + trade.net_profit_usdc, 10)
            events.append(
                PortfolioStepEvent(
                    "hypothetical_exit",
                    candle.open_time,
                    lot_id=lot.lot_id,
                    trade=trade,
                )
            )
        lots = []

    if (
        not end_of_data
        and global_index >= cooldown_until_index
        and _signal(candles, local_index, strategy)
    ):
        reserved_lots = len(lots) + (1 if pending is not None else 0)
        if reserved_lots < policy.max_concurrent_lots:
            pending = PendingPortfolioEntry(signal_time_ms=candle.open_time)
            events.append(PortfolioStepEvent("entry_scheduled", candle.open_time))
        else:
            rejection = CapacityRejection(
                signal_time_ms=candle.open_time,
                open_lots=len(lots),
                pending_entries=1 if pending is not None else 0,
                reserved_notional_usdc=round(
                    reserved_lots * policy.lot_notional_usdc, 10
                ),
                deployment_budget_usdc=policy.deployment_budget_usdc,
            )
            rejections.append(rejection)
            events.append(
                PortfolioStepEvent(
                    "capacity_rejection",
                    candle.open_time,
                    rejection=rejection,
                )
            )

    open_exposure = len(lots) * policy.lot_notional_usdc
    reserved_notional = (
        len(lots) + (1 if pending is not None else 0)
    ) * policy.lot_notional_usdc
    if reserved_notional > policy.deployment_budget_usdc:
        raise RuntimeError("reserved notional exceeds deployment budget")
    max_concurrent = max(max_concurrent, len(lots))
    max_open_exposure = max(max_open_exposure, open_exposure)
    max_reserved = max(max_reserved, reserved_notional)

    curve = state.equity_curve
    if not curve:
        curve = (EquityPoint(candle.open_time, 0.0),)
    curve = (
        *curve,
        EquityPoint(
            timestamp_ms=candle.open_time + EXPECTED_STEP_MS - 1,
            equity_usdc=_portfolio_liquidation_equity_usdc(
                realized, lots, candle.close, fee_rate, slippage_bps
            ),
        ),
    )
    history_start_index = state.history_start_index
    if state.retention_profile == BOUNDED_SHADOW_RETENTION_PROFILE:
        limit = state.retained_history_limit
        if limit is None:  # pragma: no cover - guarded by retention validation
            raise RuntimeError("bounded Shadow history limit is missing")
        trim_count = max(0, len(candles) - limit)
        history_start_index += trim_count
        candles = candles[trim_count:]
        _ensure_open_lot_history_is_retained(lots, history_start_index)
        # The append-only Shadow event log is the cumulative audit source.
        # Keep only forward-relevant reducer state in memory.
        trades = []
        rejections = []
        curve = curve[-1:]
    next_state = PortfolioEngineState(
        candles=candles,
        open_lots=tuple(lots),
        pending_entry=pending,
        cooldown_until_index=cooldown_until_index,
        realized_net_usdc=round(realized, 10),
        trades=tuple(trades),
        capacity_rejections=tuple(rejections),
        equity_curve=curve,
        next_lot_sequence=next_lot_sequence,
        max_concurrent_lots=max_concurrent,
        max_open_entry_exposure_usdc=round(max_open_exposure, 10),
        max_reserved_notional_usdc=round(max_reserved, 10),
        retention_profile=state.retention_profile,
        retained_history_limit=state.retained_history_limit,
        history_start_index=history_start_index,
        total_processed_candles=global_index + 1,
    )
    return next_state, tuple(events)


def simulate_portfolio_strategy(
    candles: list[Candle],
    strategy: StrategyCandidate,
    *,
    days: int,
    policy: PortfolioPolicy,
    training_days: int = 0,
    blindtest_days: int = 0,
) -> PortfolioSimulationResult:
    """Simulate fixed 100-USDC lots within a manual deployment budget."""

    _validate_context(strategy, policy)
    _validate_candle_timestamps(candles)
    symbol = str(strategy.params.get("symbol", SYMBOL))
    if symbol != SYMBOL:
        return _empty_result(
            candles,
            strategy,
            policy,
            Counter({"context_symbol_not_tradeable": 1}),
            days=days,
            training_days=training_days,
            blindtest_days=blindtest_days,
        )

    state = new_portfolio_engine_state()
    for index, candle in enumerate(candles):
        state, _ = advance_portfolio_engine(
            state,
            candle,
            strategy,
            policy,
            end_of_data=index == len(candles) - 1,
        )
    if not candles:
        return _empty_result(
            candles,
            strategy,
            policy,
            Counter(),
            days=days,
            training_days=training_days,
            blindtest_days=blindtest_days,
        )
    return _result_from_state(
        state,
        strategy,
        policy,
        days=days,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )


def _result_from_state(
    state: PortfolioEngineState,
    strategy: StrategyCandidate,
    policy: PortfolioPolicy,
    *,
    days: int,
    training_days: int,
    blindtest_days: int,
) -> PortfolioSimulationResult:
    trades = list(state.trades)
    metrics = compute_metrics(
        trades,
        days=days,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
    curve = state.equity_curve or (EquityPoint(0, 0.0),)
    endpoint = metrics.net_profit_usdc
    if not isclose(curve[-1].equity_usdc, endpoint, rel_tol=1e-10, abs_tol=1e-8):
        raise RuntimeError(
            "portfolio mark-to-market endpoint does not match realized net profit"
        )
    if curve[-1].equity_usdc != endpoint:
        curve = (*curve[:-1], replace(curve[-1], equity_usdc=endpoint))
    metrics = replace(metrics, max_drawdown_usdc=max_drawdown_usdc(curve))
    rejection_reasons: Counter[str] = Counter(
        rejection.reason for rejection in state.capacity_rejections
    )
    return PortfolioSimulationResult(
        strategy=strategy,
        policy=policy,
        metrics=metrics,
        trades=trades,
        rejection_reasons=rejection_reasons,
        capacity_rejections=state.capacity_rejections,
        equity_curve=curve,
        max_underwater_days=max_underwater_calendar_days(curve),
        max_concurrent_lots=state.max_concurrent_lots,
        max_open_entry_exposure_usdc=state.max_open_entry_exposure_usdc,
        max_reserved_notional_usdc=state.max_reserved_notional_usdc,
    )


def _empty_result(
    candles: list[Candle],
    strategy: StrategyCandidate,
    policy: PortfolioPolicy,
    rejections: Counter[str],
    *,
    days: int,
    training_days: int,
    blindtest_days: int,
) -> PortfolioSimulationResult:
    if candles:
        curve = (
            EquityPoint(candles[0].open_time, 0.0),
            *(
                EquityPoint(candle.open_time + EXPECTED_STEP_MS - 1, 0.0)
                for candle in candles
            ),
        )
    else:
        curve = (EquityPoint(0, 0.0),)
    metrics = compute_metrics(
        [],
        days=days,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
    return PortfolioSimulationResult(
        strategy=strategy,
        policy=policy,
        metrics=metrics,
        trades=[],
        rejection_reasons=rejections,
        equity_curve=curve,
    )


def _portfolio_exit_trade(
    candle: Candle,
    lot: PortfolioLot,
    fee_rate: float,
    slippage_bps: float,
    *,
    exit_reason: str,
) -> PortfolioTrade:
    base = _exit_trade(
        candle,
        lot.as_simulator_position(),
        fee_rate,
        slippage_bps,
        lot.entry_notional_usdc,
        exit_reason=exit_reason,
    )
    return PortfolioTrade(
        **vars(base),
        lot_id=lot.lot_id,
        entry_notional_usdc=lot.entry_notional_usdc,
    )


def _portfolio_liquidation_equity_usdc(
    realized_net_usdc: float,
    lots: list[PortfolioLot],
    mark_mid_price: float,
    fee_rate: float,
    slippage_bps: float,
) -> float:
    equity = realized_net_usdc
    exit_price = mark_mid_price * (1 - slippage_bps / 10_000)
    for lot in lots:
        gross = (exit_price - lot.entry_price) * lot.quantity
        exit_fee = exit_price * lot.quantity * fee_rate
        equity += gross - lot.entry_fee_usdc - exit_fee
    return round(equity, 10)


def _validate_context(strategy: StrategyCandidate, policy: PortfolioPolicy) -> None:
    if not isinstance(strategy, StrategyCandidate):
        raise TypeError("strategy must be a StrategyCandidate")
    if not isinstance(policy, PortfolioPolicy):
        raise TypeError("policy must be a PortfolioPolicy")
    if str(strategy.params.get("side", "LONG")) != "LONG":
        raise ValueError("Portfolio simulator is LONG-only; shorts are forbidden")


def _positive_history_parameter(
    params: dict[str, object], name: str, default: int
) -> int:
    raw = params.get(name, default) or default
    if isinstance(raw, bool):
        raise ValueError(f"strategy {name} must be a positive integer")
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"strategy {name} must be a positive integer") from exc
    if value < 1 or value != raw:
        raise ValueError(f"strategy {name} must be a positive integer")
    return value


def _validate_retention_state(
    state: PortfolioEngineState, strategy: StrategyCandidate | None
) -> None:
    if state.retention_profile not in {
        FULL_RETENTION_PROFILE,
        BOUNDED_SHADOW_RETENTION_PROFILE,
    }:
        raise ValueError("portfolio retention profile is invalid")
    if type(state.history_start_index) is not int or state.history_start_index < 0:
        raise ValueError("portfolio history start index is invalid")
    if (
        type(state.total_processed_candles) is not int
        or state.total_processed_candles < 0
    ):
        raise ValueError("portfolio processed-candle count is invalid")
    if (
        state.history_start_index + len(state.candles)
        != state.total_processed_candles
    ):
        raise ValueError("portfolio retained history indexes are inconsistent")
    if state.retention_profile == FULL_RETENTION_PROFILE:
        if state.retained_history_limit is not None or state.history_start_index != 0:
            raise ValueError("full-retention portfolio state is inconsistent")
        return
    if (
        type(state.retained_history_limit) is not int
        or state.retained_history_limit < 1
        or state.retained_history_limit > MAX_BOUNDED_HISTORY_CANDLES
    ):
        raise ValueError("bounded Shadow retained history limit is invalid")
    if len(state.candles) > state.retained_history_limit:
        raise ValueError("bounded Shadow retained candle history exceeds its limit")
    if len(state.equity_curve) > 1:
        raise ValueError("bounded Shadow retained equity history exceeds one point")
    if state.trades or state.capacity_rejections:
        raise ValueError("bounded Shadow state retained cumulative audit records")
    if strategy is not None:
        required = required_strategy_history_candles(strategy)
        if state.retained_history_limit != required:
            raise ValueError(
                "bounded Shadow retention does not match the active strategy"
            )
    _ensure_open_lot_history_is_retained(
        state.open_lots, state.history_start_index
    )


def _ensure_open_lot_history_is_retained(
    lots: tuple[PortfolioLot, ...] | list[PortfolioLot], history_start_index: int
) -> None:
    if any(lot.entry_index < history_start_index for lot in lots):
        raise RuntimeError("bounded Shadow compaction would discard open-lot history")


def _validate_next_candle_timestamp(
    state: PortfolioEngineState, candle: Candle
) -> None:
    if type(candle.open_time) is not int or candle.open_time < 0:
        raise ValueError("portfolio candle open_time must be a non-negative integer")
    if candle.open_time % EXPECTED_STEP_MS != 0:
        raise ValueError("portfolio candle open_time must align to the UTC 1m grid")
    if state.candles:
        previous = state.candles[-1].open_time
        if candle.open_time - previous != EXPECTED_STEP_MS:
            raise ValueError(
                "portfolio candles must be strict chronological 1m data without duplicates or gaps"
            )


def _validate_candle_timestamps(candles: list[Candle]) -> None:
    previous: int | None = None
    for candle in candles:
        if not isinstance(candle, Candle):
            raise TypeError("portfolio candles must contain only Candle values")
        if type(candle.open_time) is not int or candle.open_time < 0:
            raise ValueError("portfolio candle open_time must be a non-negative integer")
        if candle.open_time % EXPECTED_STEP_MS != 0:
            raise ValueError("portfolio candle open_time must align to the UTC 1m grid")
        if previous is not None and candle.open_time - previous != EXPECTED_STEP_MS:
            raise ValueError(
                "portfolio candles must be strict chronological 1m data without duplicates or gaps"
            )
        previous = candle.open_time


__all__ = [
    "BOUNDED_SHADOW_RETENTION_PROFILE",
    "CapacityRejection",
    "FULL_RETENTION_PROFILE",
    "MAX_BOUNDED_HISTORY_CANDLES",
    "PendingPortfolioEntry",
    "PortfolioEngineState",
    "PortfolioLot",
    "PortfolioSimulationResult",
    "PortfolioStepEvent",
    "PortfolioTrade",
    "STRATEGY_HISTORY_MARGIN_CANDLES",
    "advance_portfolio_engine",
    "compact_portfolio_engine_for_bounded_shadow",
    "new_portfolio_engine_state",
    "required_strategy_history_candles",
    "simulate_portfolio_strategy",
]
