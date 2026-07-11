"""Pure order-free Shadow reducer for closed public ETHUSDC 1m candles.

This module performs no networking, account access, credential loading, or
order submission.  It validates adopted deployment/state receipts and reuses
the exact portfolio backtest reducer for hypothetical entries and exits.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import isfinite
from typing import Any

from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS
from ethusdc_bot.backtest.portfolio_simulator import (
    CapacityRejection,
    PortfolioEngineState,
    PortfolioLot,
    PortfolioStepEvent,
    PortfolioTrade,
    advance_portfolio_engine,
    new_portfolio_engine_state,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.portfolio import PortfolioPolicy
from ethusdc_bot.shadow.schema import (
    ShadowSchemaError,
    validate_shadow_deployment,
    validate_shadow_state,
)


class ShadowReplayError(ValueError):
    """Raised when a deployment or state cannot safely seed replay."""


@dataclass(frozen=True)
class ShadowReplayEvent:
    """Deterministic hypothetical event; it can never represent an order."""

    sequence: int
    event_type: str
    candle_open_time_ms: int | None
    lot_id: str | None = None
    trade: PortfolioTrade | None = None
    rejection: CapacityRejection | None = None
    reason: str | None = None
    hypothetical: bool = True
    orders_enabled: bool = False
    trading_api_enabled: bool = False


@dataclass(frozen=True)
class ShadowReplayState:
    """Complete in-memory state required for exact incremental replay."""

    deployment_id: str
    phase: str
    strategy: StrategyCandidate
    policy: PortfolioPolicy
    engine_state: PortfolioEngineState
    next_event_sequence: int
    paused_reason: str | None = None

    @property
    def last_processed_candle_open_time_ms(self) -> int | None:
        if not self.engine_state.candles:
            return None
        return self.engine_state.candles[-1].open_time

    @property
    def open_lots(self) -> tuple[PortfolioLot, ...]:
        return self.engine_state.open_lots

    @property
    def trades(self) -> tuple[PortfolioTrade, ...]:
        return self.engine_state.trades

    @property
    def realized_net_usdc(self) -> float:
        return self.engine_state.realized_net_usdc

    @property
    def reserved_notional_usdc(self) -> float:
        return round(
            self.engine_state.reserved_lots * self.policy.lot_notional_usdc, 10
        )


@dataclass(frozen=True)
class ShadowReplayResult:
    """Result of reducing one ordered batch of closed candles."""

    state: ShadowReplayState
    events: tuple[ShadowReplayEvent, ...]
    processed_candles: int
    ignored_idempotent_candles: int
    trades_emitted: tuple[PortfolioTrade, ...]


def initialize_shadow_replay(
    deployment: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    start: bool = False,
) -> ShadowReplayState:
    """Validate immutable receipts and create a complete pure replay state.

    Only a fresh persisted state can seed this in-memory reducer.  The current
    persistence schema intentionally lacks signal history and pending/cooldown
    fields; accepting a partially processed receipt would therefore risk a
    divergent replay and is rejected fail-closed.
    """

    try:
        validate_shadow_deployment(deployment)
        validate_shadow_state(state)
    except ShadowSchemaError as exc:
        raise ShadowReplayError(str(exc)) from exc

    strategy, policy = _deployment_context(deployment)
    deployment_id = str(deployment["deployment_id"])
    if state.get("deployment_id") != deployment_id:
        raise ShadowReplayError("Shadow deployment and state IDs do not match")
    if state.get("deployment_budget_usdc") != policy.deployment_budget_usdc:
        raise ShadowReplayError("Shadow state budget does not match deployment policy")
    if state.get("max_open_lots") != policy.max_concurrent_lots:
        raise ShadowReplayError("Shadow state lot capacity does not match deployment policy")

    fresh = (
        state.get("last_processed_candle_open_time_ms") is None
        and state.get("open_lots") == []
        and float(state.get("realized_net_usdc", 0.0)) == 0.0
        and float(state.get("unrealized_net_usdc", 0.0)) == 0.0
    )
    if not fresh:
        raise ShadowReplayError(
            "partially processed persisted state cannot safely seed exact replay"
        )
    phase = str(state["phase"])
    if start:
        if phase not in {"adopted_stopped", "stopped", "running"}:
            raise ShadowReplayError(f"cannot start Shadow replay from phase {phase!r}")
        phase = "running"
    return ShadowReplayState(
        deployment_id=deployment_id,
        phase=phase,
        strategy=strategy,
        policy=policy,
        engine_state=new_portfolio_engine_state(),
        next_event_sequence=int(state["event_count"]) + 1,
        paused_reason=str(state["error"]) if state.get("error") is not None else None,
    )


def start_shadow_replay(
    deployment: Mapping[str, Any],
    state: Mapping[str, Any] | ShadowReplayState,
) -> ShadowReplayState:
    """Start a fresh or stopped pure replay without enabling any order path."""

    if isinstance(state, Mapping):
        return initialize_shadow_replay(deployment, state, start=True)
    current = _validated_runtime_state(deployment, state)
    if current.phase not in {"adopted_stopped", "stopped", "running"}:
        raise ShadowReplayError(f"cannot start Shadow replay from phase {current.phase!r}")
    return replace(current, phase="running", paused_reason=None)


def stop_shadow_replay(state: ShadowReplayState) -> ShadowReplayState:
    """Stop consumption without closing or otherwise changing any open lot."""

    if not isinstance(state, ShadowReplayState):
        raise TypeError("state must be a ShadowReplayState")
    if state.phase == "error":
        return state
    return replace(state, phase="stopped")


def replay_closed_candles(
    deployment: Mapping[str, Any],
    state: Mapping[str, Any] | ShadowReplayState,
    candles: Sequence[Candle],
) -> ShadowReplayResult:
    """Reduce strictly chronological closed 1m candles into hypothetical state.

    Exact candles already processed in a previous call are ignored
    idempotently.  A duplicate within the same incoming batch, conflicting
    replay data, an out-of-order timestamp, or a 1m gap pauses the reducer and
    emits one fail-closed event.  No end-of-batch liquidation occurs.
    """

    current = (
        initialize_shadow_replay(deployment, state)
        if isinstance(state, Mapping)
        else _validated_runtime_state(deployment, state)
    )
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise TypeError("candles must be a sequence of Candle values")
    if current.phase != "running":
        return ShadowReplayResult(current, (), 0, 0, ())

    events: list[ShadowReplayEvent] = []
    processed = 0
    ignored = 0
    trades_before = len(current.trades)
    seen_in_batch: set[int] = set()
    known = {candle.open_time: candle for candle in current.engine_state.candles}
    known_at_batch_start = frozenset(known)

    for candle in candles:
        invalid_reason = _invalid_candle_reason(candle)
        if invalid_reason is not None:
            current, pause_event = _pause(
                current,
                f"invalid_candle:{invalid_reason}",
                candle.open_time if isinstance(candle, Candle) else None,
            )
            events.append(pause_event)
            break
        timestamp = candle.open_time
        if timestamp in known_at_batch_start:
            if known[timestamp] == candle:
                ignored += 1
                continue
            current, pause_event = _pause(
                current, "conflicting_replayed_candle", timestamp
            )
            events.append(pause_event)
            break
        if timestamp in seen_in_batch:
            current, pause_event = _pause(
                current, "duplicate_candle_in_batch", timestamp
            )
            events.append(pause_event)
            break
        seen_in_batch.add(timestamp)

        previous = known.get(timestamp)
        if previous is not None:
            if previous == candle:
                ignored += 1
                continue
            current, pause_event = _pause(
                current, "conflicting_replayed_candle", timestamp
            )
            events.append(pause_event)
            break

        last_timestamp = current.last_processed_candle_open_time_ms
        if last_timestamp is not None:
            if timestamp < last_timestamp:
                current, pause_event = _pause(
                    current, "out_of_order_candle", timestamp
                )
                events.append(pause_event)
                break
            if timestamp != last_timestamp + EXPECTED_STEP_MS:
                current, pause_event = _pause(current, "one_minute_gap", timestamp)
                events.append(pause_event)
                break

        next_engine, step_events = advance_portfolio_engine(
            current.engine_state,
            candle,
            current.strategy,
            current.policy,
            end_of_data=False,
        )
        current = replace(current, engine_state=next_engine)
        known[timestamp] = candle
        processed += 1
        for step_event in step_events:
            shadow_event = _shadow_event(current, step_event)
            events.append(shadow_event)
            current = replace(
                current, next_event_sequence=current.next_event_sequence + 1
            )

    emitted = current.trades[trades_before:]
    return ShadowReplayResult(
        state=current,
        events=tuple(events),
        processed_candles=processed,
        ignored_idempotent_candles=ignored,
        trades_emitted=emitted,
    )


def _validated_runtime_state(
    deployment: Mapping[str, Any], state: ShadowReplayState
) -> ShadowReplayState:
    try:
        validate_shadow_deployment(deployment)
    except ShadowSchemaError as exc:
        raise ShadowReplayError(str(exc)) from exc
    if not isinstance(state, ShadowReplayState):
        raise TypeError("state must be a ShadowReplayState")
    strategy, policy = _deployment_context(deployment)
    if state.deployment_id != deployment.get("deployment_id"):
        raise ShadowReplayError("Shadow deployment and runtime state IDs do not match")
    if state.strategy != strategy or state.policy != policy:
        raise ShadowReplayError("Shadow runtime state context does not match deployment")
    if state.phase not in {
        "adopted_stopped",
        "running",
        "paused",
        "stopped",
        "error",
    }:
        raise ShadowReplayError("Shadow runtime state phase is invalid")
    if state.engine_state.reserved_lots > policy.max_concurrent_lots:
        raise ShadowReplayError("Shadow runtime state exceeds deployment capacity")
    if state.next_event_sequence < 1:
        raise ShadowReplayError("Shadow event sequence is invalid")
    return state


def _deployment_context(
    deployment: Mapping[str, Any],
) -> tuple[StrategyCandidate, PortfolioPolicy]:
    candidate = deployment["candidate"]
    policy_payload = deployment["portfolio_policy"]["policy"]
    strategy = StrategyCandidate(
        family=str(candidate["family"]), params=dict(candidate["params"])
    )
    policy = PortfolioPolicy(
        deployment_budget_usdc=policy_payload["deployment_budget_usdc"],
        lot_notional_usdc=policy_payload["lot_notional_usdc"],
        compounding_enabled=policy_payload["compounding_enabled"],
        baseline_fee_bps_per_side=policy_payload["baseline_fee_bps_per_side"],
        baseline_slippage_bps_per_side=policy_payload[
            "baseline_slippage_bps_per_side"
        ],
        soft_drawdown_fraction=policy_payload["soft_drawdown_fraction"],
    )
    return strategy, policy


def _shadow_event(
    state: ShadowReplayState, event: PortfolioStepEvent
) -> ShadowReplayEvent:
    return ShadowReplayEvent(
        sequence=state.next_event_sequence,
        event_type=event.event_type,
        candle_open_time_ms=event.candle_open_time_ms,
        lot_id=event.lot_id,
        trade=event.trade,
        rejection=event.rejection,
    )


def _pause(
    state: ShadowReplayState, reason: str, timestamp: int | None
) -> tuple[ShadowReplayState, ShadowReplayEvent]:
    event = ShadowReplayEvent(
        sequence=state.next_event_sequence,
        event_type="replay_paused",
        candle_open_time_ms=timestamp,
        reason=reason,
    )
    return (
        replace(
            state,
            phase="paused",
            paused_reason=reason,
            next_event_sequence=state.next_event_sequence + 1,
        ),
        event,
    )


def _invalid_candle_reason(value: object) -> str | None:
    if not isinstance(value, Candle):
        return "not_a_candle"
    if type(value.open_time) is not int or value.open_time < 0:
        return "open_time"
    if value.open_time % EXPECTED_STEP_MS != 0:
        return "open_time_grid"
    numbers = (value.open, value.high, value.low, value.close, value.volume)
    if any(isinstance(number, bool) or not isinstance(number, (int, float)) for number in numbers):
        return "non_numeric_ohlcv"
    if any(not isfinite(float(number)) for number in numbers):
        return "non_finite_ohlcv"
    if min(value.open, value.high, value.low, value.close) <= 0:
        return "non_positive_price"
    if value.volume < 0:
        return "negative_volume"
    if value.high < max(value.open, value.close) or value.low > min(
        value.open, value.close
    ):
        return "invalid_ohlc_range"
    if value.low > value.high:
        return "low_above_high"
    return None


__all__ = [
    "ShadowReplayError",
    "ShadowReplayEvent",
    "ShadowReplayResult",
    "ShadowReplayState",
    "initialize_shadow_replay",
    "replay_closed_candles",
    "start_shadow_replay",
    "stop_shadow_replay",
]
