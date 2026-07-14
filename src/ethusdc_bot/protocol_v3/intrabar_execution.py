"""Protocol v3 next-tradable-price and pessimistic intrabar execution.

This module reuses the existing strategy signal decision and Task-7 quantity,
notional and fee rules.  It adds exactly one Protocol-v3 execution path for
baseline and stress profiles.  It creates no orders and never accesses private
or account data.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
import json
from math import isclose, isfinite
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from ethusdc_bot.backtest.context_features import (
    ContextVetoPolicy,
    validate_context_against_trade_candles,
)
from ethusdc_bot.backtest.data_loader import (
    AlignedMarketCandles,
    Candle,
    EXPECTED_STEP_MS,
    SYMBOL,
)
from ethusdc_bot.backtest.equity import (
    EquityPoint,
    max_drawdown_usdc,
    max_underwater_calendar_days,
)
from ethusdc_bot.backtest.metrics import compute_metrics
from ethusdc_bot.backtest.portfolio_simulator import PortfolioSimulationResult
from ethusdc_bot.backtest.simulator import (
    SimulationResult,
    StrategyCandidate,
    _entry_decision,
)
from ethusdc_bot.portfolio import FIXED_LOT_NOTIONAL_USDC, PortfolioPolicy
from ethusdc_bot.protocol_v3.execution_parity import (
    EXECUTION_PARITY_CONTRACT_VERSION,
    MarketEntryExecution,
    MarketExecutionRules,
    ProtocolV3PortfolioTrade,
    ProtocolV3Trade,
    build_market_execution_rules,
    load_execution_parity_contract,
    prepare_market_entry,
    prepare_market_exit,
)
from ethusdc_bot.protocol_v3.run_identity import FrozenExchangeInfoSnapshot


INTRABAR_EXECUTION_CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_intrabar_execution_contract.json"
)
INTRABAR_EXECUTION_CONTRACT_SCHEMA: Final = (
    "protocol_v3_intrabar_execution_contract_v1"
)
INTRABAR_EXECUTION_CONTRACT_VERSION: Final = (
    "next_tradable_price_pessimistic_intrabar_v1"
)

_CANONICAL_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: dict[str, Any] = {
    "schema_version": INTRABAR_EXECUTION_CONTRACT_SCHEMA,
    "protocol_version": "3.0.0",
    "contract_version": INTRABAR_EXECUTION_CONTRACT_VERSION,
    "market": {
        "exchange": "binance",
        "market_type": "spot",
        "symbol": "ETHUSDC",
        "side": "LONG",
        "source_bar": "1m",
    },
    "entry_policy": {
        "signal_bar_must_be_closed": True,
        "earliest_fill": "next_positive_volume_1m_open",
        "entry_reference": "next_tradable_open",
        "adverse_slippage_direction": "up_for_buy",
        "price_tick_rounding": "ROUND_CEILING",
        "same_entry_bar_exit_checks_enabled": True,
        "pending_entry_does_not_fill_on_zero_volume": True,
    },
    "exit_policy": {
        "stop_and_target_resolved_on": "positive_volume_1m_ohlc",
        "simultaneous_stop_target_priority": "stop_first",
        "time_exit_priority": "bar_open_before_intrabar",
        "stop_gap_reference": "worse_next_tradable_open",
        "target_gap_reference": "target_level_not_better_gap_open",
        "intrabar_stop_reference": "active_stop_level",
        "intrabar_target_reference": "target_level",
        "adverse_slippage_direction": "down_for_sell",
        "price_tick_rounding": "ROUND_FLOOR",
        "perfect_high_low_fills_forbidden": True,
        "exit_quantity_equals_task7_entry_quantity": True,
        "zero_volume_bar_cannot_fill_or_advance_trailing_state": True,
    },
    "level_policy": {
        "initial_stop_tick_rounding": "ROUND_FLOOR",
        "target_tick_rounding": "ROUND_CEILING",
        "break_even_and_trailing_use_completed_prior_bars_only": True,
        "break_even_becomes_active_next_tradable_bar": True,
        "trailing_high_watermark_updates_after_survived_bar": True,
        "trailing_stop_tick_rounding": "ROUND_FLOOR",
    },
    "terminal_policy": {
        "finite_run_liquidation_reference": "last_positive_volume_bar_close",
        "terminal_liquidation_is_explicit": True,
        "missing_tradable_terminal_price_blocks": True,
    },
    "cost_profiles": {
        "baseline": {"fee_bps_per_side": "10", "slippage_bps_per_side": "5"},
        "slippage_stress": {
            "fee_bps_per_side": "10",
            "slippage_bps_per_side": "15",
        },
        "joint_stress": {
            "fee_bps_per_side": "15",
            "slippage_bps_per_side": "10",
        },
        "all_profiles_use_same_engine": True,
    },
    "task7_dependency": {
        "contract_version": EXECUTION_PARITY_CONTRACT_VERSION,
        "requested_entry_notional_usdc": "100",
        "reserved_entry_notional_usdc": "100",
        "quantity_rounding": "ROUND_DOWN",
        "fees_use_actual_notional": True,
    },
    "scope": {
        "fold_state_machine_deferred_to_task_9": True,
        "context_parity_deferred_to_task_10": True,
        "partial_fills_forbidden": True,
        "order_book_execution_not_implemented": True,
    },
    "safety": _CANONICAL_SAFETY,
}


class IntrabarExecutionError(RuntimeError):
    """Raised when Task-8 execution cannot remain deterministic and conservative."""


@dataclass(frozen=True)
class ExecutionCostProfile:
    name: str
    fee_bps_per_side: Decimal
    slippage_bps_per_side: Decimal

    @property
    def fee_rate(self) -> Decimal:
        return self.fee_bps_per_side / Decimal("10000")


BASELINE_COST_PROFILE: Final = ExecutionCostProfile(
    "baseline", Decimal("10"), Decimal("5")
)
SLIPPAGE_STRESS_COST_PROFILE: Final = ExecutionCostProfile(
    "slippage_stress", Decimal("10"), Decimal("15")
)
JOINT_STRESS_COST_PROFILE: Final = ExecutionCostProfile(
    "joint_stress", Decimal("15"), Decimal("10")
)
_ALLOWED_COST_PROFILES: Final = {
    profile.name: profile
    for profile in (
        BASELINE_COST_PROFILE,
        SLIPPAGE_STRESS_COST_PROFILE,
        JOINT_STRESS_COST_PROFILE,
    )
}


@dataclass(frozen=True)
class IntrabarExitDecision:
    reason: str
    reference_price: Decimal
    fill_price: Decimal
    active_stop_price: Decimal
    target_price: Decimal
    active_stop_source: str
    gap_fill: bool
    simultaneous_stop_target_touch: bool
    terminal_liquidation: bool = False


@dataclass(frozen=True)
class ProtocolV3IntrabarTrade(ProtocolV3Trade):
    signal_time: int = 0
    entry_reference_price: float = 0.0
    exit_reference_price: float = 0.0
    active_stop_price: float = 0.0
    target_price: float = 0.0
    high_watermark_price: float = 0.0
    active_stop_source: str = "initial_stop"
    entry_tick_rounding: str = "ROUND_CEILING"
    exit_tick_rounding: str = "ROUND_FLOOR"
    gap_fill: bool = False
    simultaneous_stop_target_touch: bool = False
    terminal_liquidation: bool = False
    execution_contract_version: str = INTRABAR_EXECUTION_CONTRACT_VERSION
    cost_profile: str = "baseline"


@dataclass(frozen=True)
class ProtocolV3IntrabarPortfolioTrade(ProtocolV3IntrabarTrade):
    lot_id: str = ""
    entry_notional_usdc: float = 100.0


@dataclass
class _OpenPosition:
    signal_time: int
    entry_time: int
    entry_index: int
    entry_reference_price: Decimal
    entry_fill_price: Decimal
    entry: MarketEntryExecution
    initial_stop_price: Decimal
    target_price: Decimal
    break_even_trigger_price: Decimal | None
    trailing_stop_bps: Decimal
    high_watermark_price: Decimal
    active_stop_price: Decimal
    active_stop_source: str


@dataclass(frozen=True)
class _CoreResult:
    trades: tuple[ProtocolV3IntrabarTrade, ...]
    rejection_reasons: Counter[str]
    signal_funnel: Counter[str]
    equity_curve: tuple[EquityPoint, ...]
    max_executed_entry_exposure_usdc: float
    max_reserved_notional_usdc: float
    max_concurrent_lots: int


def load_intrabar_execution_contract(
    repo_root: str | Path | None = None,
    *,
    contract_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    path = Path(contract_path) if contract_path is not None else root / INTRABAR_EXECUTION_CONTRACT_PATH
    if not path.is_absolute():
        path = root / path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntrabarExecutionError(
            f"intrabar execution contract is missing or invalid: {path}"
        ) from exc
    validate_intrabar_execution_contract(value)
    return value


def validate_intrabar_execution_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize_json(value) != _CANONICAL_CONTRACT:
        raise IntrabarExecutionError(
            "Protocol v3 intrabar execution contract is not canonical"
        )


def simulate_protocol_v3_intrabar_strategy(
    candles: list[Candle],
    strategy: StrategyCandidate,
    *,
    days: int,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    cost_profile: ExecutionCostProfile = BASELINE_COST_PROFILE,
    training_days: int = 0,
    blindtest_days: int = 0,
    market_context: AlignedMarketCandles | None = None,
) -> SimulationResult:
    """Simulate one fixed 100-USDC LONG lot with the canonical Task-8 engine."""

    core = _simulate_core(
        candles,
        strategy,
        exchange_info_snapshot=exchange_info_snapshot,
        cost_profile=cost_profile,
        market_context=market_context,
    )
    metrics = compute_metrics(
        list(core.trades),
        days=days,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
    metrics = metrics.__class__(
        **{
            **vars(metrics),
            "max_drawdown_usdc": max_drawdown_usdc(core.equity_curve),
        }
    )
    _assert_equity_endpoint(core.equity_curve, metrics.net_profit_usdc)
    return SimulationResult(
        strategy=strategy,
        metrics=metrics,
        trades=list(core.trades),
        rejection_reasons=core.rejection_reasons,
        signal_funnel=core.signal_funnel,
        equity_curve=core.equity_curve,
        max_underwater_days=max_underwater_calendar_days(core.equity_curve),
        drawdown_method="mark_to_market_protocol_v3_pessimistic_intrabar",
    )


def simulate_protocol_v3_intrabar_portfolio_strategy(
    candles: list[Candle],
    strategy: StrategyCandidate,
    *,
    days: int,
    policy: PortfolioPolicy,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    cost_profile: ExecutionCostProfile = BASELINE_COST_PROFILE,
    training_days: int = 0,
    blindtest_days: int = 0,
    market_context: AlignedMarketCandles | None = None,
) -> PortfolioSimulationResult:
    """Return the same Task-8 trades through the order-free portfolio result type."""

    if not isinstance(policy, PortfolioPolicy):
        raise TypeError("policy must be a PortfolioPolicy")
    if policy.max_concurrent_lots != 1 or policy.lot_notional_usdc != FIXED_LOT_NOTIONAL_USDC:
        raise IntrabarExecutionError(
            "Task-8 canonical Protocol v3 profile must remain 100 USDC with one open lot"
        )
    core = _simulate_core(
        candles,
        strategy,
        exchange_info_snapshot=exchange_info_snapshot,
        cost_profile=cost_profile,
        market_context=market_context,
    )
    trades = [
        ProtocolV3IntrabarPortfolioTrade(
            **vars(trade),
            lot_id=f"lot-{index:08d}",
            entry_notional_usdc=100.0,
        )
        for index, trade in enumerate(core.trades, start=1)
    ]
    metrics = compute_metrics(
        trades,
        days=days,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
    metrics = metrics.__class__(
        **{
            **vars(metrics),
            "max_drawdown_usdc": max_drawdown_usdc(core.equity_curve),
        }
    )
    _assert_equity_endpoint(core.equity_curve, metrics.net_profit_usdc)
    return PortfolioSimulationResult(
        strategy=strategy,
        policy=policy,
        metrics=metrics,
        trades=trades,
        rejection_reasons=core.rejection_reasons,
        capacity_rejections=(),
        equity_curve=core.equity_curve,
        max_underwater_days=max_underwater_calendar_days(core.equity_curve),
        max_concurrent_lots=core.max_concurrent_lots,
        max_open_entry_exposure_usdc=core.max_executed_entry_exposure_usdc,
        max_reserved_notional_usdc=core.max_reserved_notional_usdc,
        drawdown_method="mark_to_market_portfolio_protocol_v3_pessimistic_intrabar",
    )


def _simulate_core(
    candles: list[Candle],
    strategy: StrategyCandidate,
    *,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    cost_profile: ExecutionCostProfile,
    market_context: AlignedMarketCandles | None,
) -> _CoreResult:
    load_execution_parity_contract()
    load_intrabar_execution_contract()
    profile = _validate_cost_profile(cost_profile)
    _validate_inputs(candles, strategy, market_context)
    rules = build_market_execution_rules(exchange_info_snapshot)
    rejections: Counter[str] = Counter()
    funnel: Counter[str] = Counter()
    if str(strategy.params.get("symbol", SYMBOL)) != SYMBOL:
        rejections["context_symbol_not_tradeable"] += 1
        funnel.update(
            {
                "observations_total": len(candles),
                "entry_evaluations": 1,
                "rejected_signals": 1,
                "rejected.context_symbol_not_tradeable": 1,
            }
        )
        return _CoreResult(
            (),
            rejections,
            funnel,
            _zero_equity_curve(candles),
            0.0,
            0.0,
            0,
        )

    context_policy: ContextVetoPolicy | None = None
    if strategy.family == "context_filter":
        context_policy = ContextVetoPolicy.from_candidate_params(strategy.params)
        if market_context is not None:
            validate_context_against_trade_candles(candles, market_context)

    position: _OpenPosition | None = None
    pending_signal_time: int | None = None
    cooldown_until_index = -1
    realized = Decimal("0")
    trades: list[ProtocolV3IntrabarTrade] = []
    curve: list[EquityPoint] = [
        EquityPoint(candles[0].open_time if candles else 0, 0.0)
    ]
    max_exposure = Decimal("0")
    max_reserved = Decimal("0")
    max_concurrent = 0

    for index, candle in enumerate(candles):
        funnel["observations_total"] += 1
        exited = False
        if pending_signal_time is not None and position is None:
            max_reserved = max(max_reserved, Decimal("100"))
            if candle.volume > 0:
                position = _open_position(
                    candle,
                    index,
                    pending_signal_time,
                    strategy,
                    rules,
                    profile,
                )
                pending_signal_time = None
                max_exposure = max(
                    max_exposure, position.entry.executed_entry_notional
                )
                max_concurrent = 1
                funnel["executed_entries"] += 1
            else:
                funnel["blocked.zero_volume_pending_entry"] += 1

        if position is not None and candle.volume > 0:
            decision = _exit_decision(
                candle,
                index,
                position,
                strategy,
                rules,
                profile,
            )
            if decision is not None:
                trade = _close_position(position, decision, rules, profile)
                trades.append(trade)
                realized += _decimal(
                    trade.net_profit_usdc,
                    "trade.net_profit_usdc",
                    allow_negative=True,
                    allow_zero=True,
                )
                position = None
                exited = True
                cooldown_until_index = index + int(
                    strategy.params.get("cooldown_minutes", 0) or 0
                )
                funnel[f"exits.{trade.exit_reason}"] += 1

        if position is not None and index == len(candles) - 1:
            if candle.volume <= 0:
                raise IntrabarExecutionError(
                    "finite run cannot liquidate an open lot without a positive-volume terminal bar"
                )
            decision = _terminal_decision(candle, position, rules, profile)
            trade = _close_position(position, decision, rules, profile)
            trades.append(trade)
            realized += _decimal(
                trade.net_profit_usdc,
                "trade.net_profit_usdc",
                allow_negative=True,
                allow_zero=True,
            )
            position = None
            exited = True
            funnel["exits.end_of_data"] += 1

        if position is not None and not exited and candle.volume > 0:
            _advance_completed_bar_state(position, candle, strategy, rules)

        if position is not None:
            funnel["blocked.position_open"] += 1
        elif pending_signal_time is not None:
            funnel["blocked.pending_entry"] += 1
        elif index >= len(candles) - 1:
            funnel["blocked.end_of_data"] += 1
        elif index < cooldown_until_index:
            funnel["blocked.cooldown"] += 1
        else:
            funnel["entry_evaluations"] += 1
            decision = _entry_decision(
                candles,
                index,
                strategy,
                market_context=market_context,
                context_policy=context_policy,
            )
            if decision.raw_signal:
                funnel["raw_entry_signals"] += 1
            if decision.allowed:
                funnel["accepted_entry_signals"] += 1
                pending_signal_time = candle.open_time + EXPECTED_STEP_MS - 1
                max_reserved = max(max_reserved, Decimal("100"))
            else:
                reason = decision.reason or "entry_signal_absent"
                rejections[reason] += 1
                funnel["rejected_signals"] += 1
                funnel[f"rejected.{reason}"] += 1

        equity = realized
        if position is not None:
            equity += _open_liquidation_pnl(
                position,
                candle.close,
                rules,
                profile,
            )
        curve.append(
            EquityPoint(
                candle.open_time + EXPECTED_STEP_MS - 1,
                _float10(equity),
            )
        )

    if position is not None:
        raise IntrabarExecutionError("Protocol v3 simulation ended with an open lot")
    for key in (
        "observations_total",
        "entry_evaluations",
        "raw_entry_signals",
        "accepted_entry_signals",
        "executed_entries",
        "rejected_signals",
        "blocked.position_open",
        "blocked.pending_entry",
        "blocked.cooldown",
        "blocked.end_of_data",
        "blocked.zero_volume_pending_entry",
    ):
        funnel.setdefault(key, 0)
    return _CoreResult(
        tuple(trades),
        rejections,
        funnel,
        tuple(curve),
        _float10(max_exposure),
        _float10(max_reserved),
        max_concurrent,
    )


def _open_position(
    candle: Candle,
    index: int,
    signal_time: int,
    strategy: StrategyCandidate,
    rules: MarketExecutionRules,
    profile: ExecutionCostProfile,
) -> _OpenPosition:
    entry_reference = _decimal(candle.open, "entry_reference_price")
    entry_fill = _buy_fill(entry_reference, profile.slippage_bps_per_side, rules)
    entry = prepare_market_entry(entry_fill, profile.fee_rate, rules)
    stop_bps = _positive_bps(strategy.params.get("stop_loss_bps", 60), "stop_loss_bps")
    target_bps = _positive_bps(
        strategy.params.get("take_profit_bps", 80), "take_profit_bps"
    )
    initial_stop = _floor_tick(
        entry_fill * (Decimal("1") - stop_bps / Decimal("10000")),
        rules.tick_size,
    )
    target = _ceil_tick(
        entry_fill * (Decimal("1") + target_bps / Decimal("10000")),
        rules.tick_size,
    )
    if initial_stop <= 0 or initial_stop >= entry_fill:
        raise IntrabarExecutionError("initial stop is not below the entry fill")
    if target <= entry_fill:
        raise IntrabarExecutionError("target is not above the entry fill")
    break_even_bps = _nonnegative_bps(
        strategy.params.get("break_even_after_bps", 0),
        "break_even_after_bps",
    )
    break_even_trigger = (
        _ceil_tick(
            entry_fill * (Decimal("1") + break_even_bps / Decimal("10000")),
            rules.tick_size,
        )
        if break_even_bps > 0
        else None
    )
    trailing_bps = _nonnegative_bps(
        strategy.params.get("trailing_stop_bps", 0), "trailing_stop_bps"
    )
    return _OpenPosition(
        signal_time=signal_time,
        entry_time=candle.open_time,
        entry_index=index,
        entry_reference_price=entry_reference,
        entry_fill_price=entry_fill,
        entry=entry,
        initial_stop_price=initial_stop,
        target_price=target,
        break_even_trigger_price=break_even_trigger,
        trailing_stop_bps=trailing_bps,
        high_watermark_price=entry_fill,
        active_stop_price=initial_stop,
        active_stop_source="stop_loss",
    )


def _exit_decision(
    candle: Candle,
    index: int,
    position: _OpenPosition,
    strategy: StrategyCandidate,
    rules: MarketExecutionRules,
    profile: ExecutionCostProfile,
) -> IntrabarExitDecision | None:
    max_hold = int(strategy.params.get("max_hold_minutes", 30) or 30)
    if max_hold <= 0:
        raise IntrabarExecutionError("max_hold_minutes must be positive")
    open_price = _decimal(candle.open, "candle.open")
    if index - position.entry_index >= max_hold:
        return _decision(
            "time_exit",
            open_price,
            position,
            rules,
            profile,
            gap=False,
            simultaneous=False,
        )
    if open_price <= position.active_stop_price:
        return _decision(
            position.active_stop_source,
            open_price,
            position,
            rules,
            profile,
            gap=True,
            simultaneous=False,
        )
    if open_price >= position.target_price:
        return _decision(
            "take_profit",
            position.target_price,
            position,
            rules,
            profile,
            gap=True,
            simultaneous=False,
        )
    low = _decimal(candle.low, "candle.low")
    high = _decimal(candle.high, "candle.high")
    stop_touch = low <= position.active_stop_price
    target_touch = high >= position.target_price
    if stop_touch:
        return _decision(
            position.active_stop_source,
            position.active_stop_price,
            position,
            rules,
            profile,
            gap=False,
            simultaneous=target_touch,
        )
    if target_touch:
        return _decision(
            "take_profit",
            position.target_price,
            position,
            rules,
            profile,
            gap=False,
            simultaneous=False,
        )
    return None


def _decision(
    reason: str,
    reference: Decimal,
    position: _OpenPosition,
    rules: MarketExecutionRules,
    profile: ExecutionCostProfile,
    *,
    gap: bool,
    simultaneous: bool,
) -> IntrabarExitDecision:
    return IntrabarExitDecision(
        reason=reason,
        reference_price=reference,
        fill_price=_sell_fill(reference, profile.slippage_bps_per_side, rules),
        active_stop_price=position.active_stop_price,
        target_price=position.target_price,
        active_stop_source=position.active_stop_source,
        gap_fill=gap,
        simultaneous_stop_target_touch=simultaneous,
    )


def _terminal_decision(
    candle: Candle,
    position: _OpenPosition,
    rules: MarketExecutionRules,
    profile: ExecutionCostProfile,
) -> IntrabarExitDecision:
    reference = _decimal(candle.close, "terminal_close")
    return IntrabarExitDecision(
        reason="end_of_data",
        reference_price=reference,
        fill_price=_sell_fill(reference, profile.slippage_bps_per_side, rules),
        active_stop_price=position.active_stop_price,
        target_price=position.target_price,
        active_stop_source=position.active_stop_source,
        gap_fill=False,
        simultaneous_stop_target_touch=False,
        terminal_liquidation=True,
    )


def _advance_completed_bar_state(
    position: _OpenPosition,
    candle: Candle,
    strategy: StrategyCandidate,
    rules: MarketExecutionRules,
) -> None:
    high = _decimal(candle.high, "candle.high")
    position.high_watermark_price = max(position.high_watermark_price, high)
    candidates: list[tuple[Decimal, str]] = [
        (position.initial_stop_price, "stop_loss")
    ]
    if (
        position.break_even_trigger_price is not None
        and position.high_watermark_price >= position.break_even_trigger_price
    ):
        candidates.append((position.entry_fill_price, "break_even"))
    if position.trailing_stop_bps > 0:
        trailing = _floor_tick(
            position.high_watermark_price
            * (Decimal("1") - position.trailing_stop_bps / Decimal("10000")),
            rules.tick_size,
        )
        candidates.append((trailing, "trailing_stop"))
    active_price, source = max(candidates, key=lambda row: (row[0], row[1]))
    if active_price >= position.target_price:
        raise IntrabarExecutionError("completed-bar stop state reached or exceeded target")
    position.active_stop_price = active_price
    position.active_stop_source = source


def _close_position(
    position: _OpenPosition,
    decision: IntrabarExitDecision,
    rules: MarketExecutionRules,
    profile: ExecutionCostProfile,
) -> ProtocolV3IntrabarTrade:
    exit_fill = prepare_market_exit(
        decision.fill_price,
        position.entry.executed_quantity,
        profile.fee_rate,
        rules,
    )
    quantity = position.entry.executed_quantity
    gross = (decision.fill_price - position.entry_fill_price) * quantity
    entry_slippage = (
        position.entry_fill_price - position.entry_reference_price
    ) * quantity
    exit_slippage = (decision.reference_price - decision.fill_price) * quantity
    fees = position.entry.entry_fee + exit_fill.exit_fee
    net = gross - fees
    return ProtocolV3IntrabarTrade(
        symbol=SYMBOL,
        side="LONG",
        entry_time=position.entry_time,
        exit_time=(
            position.entry_time
            if decision.terminal_liquidation and position.entry_time < 0
            else 0
        ),
        entry_price=_float10(position.entry_fill_price),
        exit_price=_float10(decision.fill_price),
        quantity=_float10(quantity),
        gross_profit_usdc=_float10(gross),
        fees_usdc=_float10(fees),
        slippage_usdc=_float10(entry_slippage + exit_slippage),
        net_profit_usdc=_float10(net),
        exit_reason=decision.reason,
        entry_mid_price=_float10(position.entry_reference_price),
        exit_mid_price=_float10(decision.reference_price),
        entry_slippage_usdc=_float10(entry_slippage),
        exit_slippage_usdc=_float10(exit_slippage),
        entry_fee_usdc=_float10(position.entry.entry_fee),
        exit_fee_usdc=_float10(exit_fill.exit_fee),
        requested_entry_notional_usdc=100.0,
        reserved_entry_notional_usdc=100.0,
        executed_entry_notional_usdc=_float10(
            position.entry.executed_entry_notional
        ),
        unspent_reserved_notional_usdc=_float10(
            position.entry.unspent_reserved_notional
        ),
        entry_cash_cost_including_fee_usdc=_float10(
            position.entry.entry_cash_cost_including_fee
        ),
        executed_exit_notional_usdc=_float10(
            exit_fill.executed_exit_notional
        ),
        exit_proceeds_after_fee_usdc=_float10(
            exit_fill.exit_proceeds_after_fee
        ),
        exit_quantity=_float10(exit_fill.executed_quantity),
        quantity_step_size=_float10(rules.effective_quantity_step),
        quantity_rounding_mode="ROUND_DOWN",
        execution_rules_sha256=rules.rules_sha256,
        exchange_info_snapshot_sha256=rules.exchange_info_snapshot_sha256,
        compounding_enabled=False,
        signal_time=position.signal_time,
        entry_reference_price=_float10(position.entry_reference_price),
        exit_reference_price=_float10(decision.reference_price),
        active_stop_price=_float10(decision.active_stop_price),
        target_price=_float10(decision.target_price),
        high_watermark_price=_float10(position.high_watermark_price),
        active_stop_source=decision.active_stop_source,
        gap_fill=decision.gap_fill,
        simultaneous_stop_target_touch=decision.simultaneous_stop_target_touch,
        terminal_liquidation=decision.terminal_liquidation,
        cost_profile=profile.name,
    )


def _open_liquidation_pnl(
    position: _OpenPosition,
    mark_mid_price: float,
    rules: MarketExecutionRules,
    profile: ExecutionCostProfile,
) -> Decimal:
    reference = _decimal(mark_mid_price, "mark_mid_price")
    fill = _sell_fill(reference, profile.slippage_bps_per_side, rules)
    exit_fill = prepare_market_exit(
        fill,
        position.entry.executed_quantity,
        profile.fee_rate,
        rules,
    )
    gross = (
        fill - position.entry_fill_price
    ) * position.entry.executed_quantity
    return gross - position.entry.entry_fee - exit_fill.exit_fee


def _buy_fill(
    reference: Decimal,
    slippage_bps: Decimal,
    rules: MarketExecutionRules,
) -> Decimal:
    raw = reference * (Decimal("1") + slippage_bps / Decimal("10000"))
    return _ceil_tick(raw, rules.tick_size)


def _sell_fill(
    reference: Decimal,
    slippage_bps: Decimal,
    rules: MarketExecutionRules,
) -> Decimal:
    raw = reference * (Decimal("1") - slippage_bps / Decimal("10000"))
    fill = _floor_tick(raw, rules.tick_size)
    if fill <= 0:
        raise IntrabarExecutionError("adverse sell fill is not positive")
    return fill


def _ceil_tick(value: Decimal, tick: Decimal) -> Decimal:
    if tick <= 0:
        raise IntrabarExecutionError("tick size must be positive")
    return (value / tick).to_integral_value(rounding=ROUND_CEILING) * tick


def _floor_tick(value: Decimal, tick: Decimal) -> Decimal:
    if tick <= 0:
        raise IntrabarExecutionError("tick size must be positive")
    return (value / tick).to_integral_value(rounding=ROUND_FLOOR) * tick


def _validate_inputs(
    candles: Sequence[Candle],
    strategy: StrategyCandidate,
    market_context: AlignedMarketCandles | None,
) -> None:
    if not isinstance(strategy, StrategyCandidate):
        raise TypeError("strategy must be a StrategyCandidate")
    if str(strategy.params.get("side", "LONG")) != "LONG":
        raise IntrabarExecutionError("Protocol v3 intrabar execution is LONG-only")
    previous: int | None = None
    for candle in candles:
        if not isinstance(candle, Candle):
            raise TypeError("candles must contain only Candle values")
        if type(candle.open_time) is not int or candle.open_time < 0:
            raise IntrabarExecutionError("candle open_time must be a non-negative integer")
        if candle.open_time % EXPECTED_STEP_MS != 0:
            raise IntrabarExecutionError("candles must align to the UTC 1m grid")
        if previous is not None and candle.open_time - previous != EXPECTED_STEP_MS:
            raise IntrabarExecutionError(
                "candles must be strict chronological 1m data without gaps or duplicates"
            )
        values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
        if any(not isfinite(float(value)) for value in values):
            raise IntrabarExecutionError("candle OHLCV values must be finite")
        if min(candle.open, candle.high, candle.low, candle.close) <= 0:
            raise IntrabarExecutionError("candle prices must be positive")
        if candle.volume < 0:
            raise IntrabarExecutionError("candle volume must be non-negative")
        if candle.high < max(candle.open, candle.low, candle.close):
            raise IntrabarExecutionError("candle high is inconsistent")
        if candle.low > min(candle.open, candle.high, candle.close):
            raise IntrabarExecutionError("candle low is inconsistent")
        previous = candle.open_time
    if market_context is not None and len(candles) != market_context.candle_count:
        raise IntrabarExecutionError("market context length does not match trade candles")


def _validate_cost_profile(profile: ExecutionCostProfile) -> ExecutionCostProfile:
    if not isinstance(profile, ExecutionCostProfile):
        raise TypeError("cost_profile must be an ExecutionCostProfile")
    canonical = _ALLOWED_COST_PROFILES.get(profile.name)
    if canonical != profile:
        raise IntrabarExecutionError("cost profile is not canonical")
    return profile


def _positive_bps(value: Any, label: str) -> Decimal:
    parsed = _decimal(value, label)
    if parsed <= 0:
        raise IntrabarExecutionError(f"{label} must be positive")
    return parsed


def _nonnegative_bps(value: Any, label: str) -> Decimal:
    return _decimal(value, label, allow_zero=True)


def _decimal(
    value: Any,
    label: str,
    *,
    allow_zero: bool = False,
    allow_negative: bool = False,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int, float)):
        raise IntrabarExecutionError(f"{label} must be a finite decimal value")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise IntrabarExecutionError(f"{label} is not a valid decimal") from exc
    if not parsed.is_finite():
        raise IntrabarExecutionError(f"{label} must be finite")
    if allow_negative:
        return parsed
    if parsed < 0 or (parsed == 0 and not allow_zero):
        requirement = "non-negative" if allow_zero else "positive"
        raise IntrabarExecutionError(f"{label} must be {requirement}")
    return parsed


def _float10(value: Decimal) -> float:
    return round(float(value), 10)


def _zero_equity_curve(candles: Sequence[Candle]) -> tuple[EquityPoint, ...]:
    if not candles:
        return (EquityPoint(0, 0.0),)
    return (
        EquityPoint(candles[0].open_time, 0.0),
        *(
            EquityPoint(candle.open_time + EXPECTED_STEP_MS - 1, 0.0)
            for candle in candles
        ),
    )


def _assert_equity_endpoint(
    curve: tuple[EquityPoint, ...], expected_net_profit: float
) -> None:
    if not curve or not isclose(
        curve[-1].equity_usdc,
        expected_net_profit,
        rel_tol=1e-10,
        abs_tol=1e-8,
    ):
        raise IntrabarExecutionError(
            "Protocol v3 intrabar equity endpoint does not match realized PnL"
        )


def _normalize_json(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )


__all__ = [
    "BASELINE_COST_PROFILE",
    "INTRABAR_EXECUTION_CONTRACT_PATH",
    "INTRABAR_EXECUTION_CONTRACT_SCHEMA",
    "INTRABAR_EXECUTION_CONTRACT_VERSION",
    "JOINT_STRESS_COST_PROFILE",
    "SLIPPAGE_STRESS_COST_PROFILE",
    "ExecutionCostProfile",
    "IntrabarExecutionError",
    "IntrabarExitDecision",
    "ProtocolV3IntrabarPortfolioTrade",
    "ProtocolV3IntrabarTrade",
    "load_intrabar_execution_contract",
    "simulate_protocol_v3_intrabar_portfolio_strategy",
    "simulate_protocol_v3_intrabar_strategy",
    "validate_intrabar_execution_contract",
]
