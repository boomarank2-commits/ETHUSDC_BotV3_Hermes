"""Protocol v3 fixed-lot Binance Spot execution parity.

Task 7 keeps the existing signal and exit-timing engines unchanged and reprices
those deterministic trades with exact Decimal quantity/notional/fee rules from a
frozen public ETHUSDC Exchange-Info snapshot. It creates no orders and does not
unlock Paper, Testtrade, Live, private endpoints, account data, or API keys.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from functools import reduce
import hashlib
import json
from math import gcd, isclose
from pathlib import Path
from typing import Any, Mapping, Sequence

from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS
from ethusdc_bot.backtest.equity import (
    EquityPoint,
    max_drawdown_usdc,
    max_underwater_calendar_days,
)
from ethusdc_bot.backtest.metrics import compute_metrics
from ethusdc_bot.backtest.portfolio_simulator import (
    PortfolioSimulationResult,
    simulate_portfolio_strategy,
)
from ethusdc_bot.backtest.simulator import (
    SimulationResult,
    StrategyCandidate,
    Trade,
    simulate_strategy,
)
from ethusdc_bot.portfolio import FIXED_LOT_NOTIONAL_USDC, PortfolioPolicy
from ethusdc_bot.protocol_v3.run_identity import (
    FrozenExchangeInfoSnapshot,
    validate_exchange_info_snapshot,
)

EXECUTION_PARITY_CONTRACT_PATH = Path(
    "configs/protocol_v3_execution_parity_contract.json"
)
EXECUTION_PARITY_CONTRACT_SCHEMA = "protocol_v3_execution_parity_contract_v1"
EXECUTION_PARITY_CONTRACT_VERSION = "ethusdc_spot_fixed_lot_execution_parity_v1"
FIXED_REQUESTED_NOTIONAL = Decimal("100")
FIXED_RESERVED_NOTIONAL = Decimal("100")
BASELINE_FEE_RATE = Decimal("0.001")
BASELINE_SLIPPAGE_BPS = Decimal("5")

_CANONICAL_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: dict[str, Any] = {
    "schema_version": EXECUTION_PARITY_CONTRACT_SCHEMA,
    "protocol_version": "3.0.0",
    "contract_version": EXECUTION_PARITY_CONTRACT_VERSION,
    "market": {
        "exchange": "binance",
        "market_type": "spot",
        "symbol": "ETHUSDC",
        "side": "LONG",
    },
    "lot_policy": {
        "requested_entry_notional_usdc": "100",
        "reserved_entry_notional_usdc": "100",
        "executed_entry_notional_must_not_exceed_requested": True,
        "fees_are_additional": True,
        "compounding_enabled": False,
        "max_open_lots_for_research_profile": 1,
    },
    "quantity_policy": {
        "arithmetic": "decimal_exact",
        "rounding": "ROUND_DOWN",
        "required_filters": ["LOT_SIZE", "MARKET_LOT_SIZE"],
        "positive_step_intersection_required": True,
        "zero_step_disables_individual_filter": True,
        "at_least_one_positive_step_required": True,
        "min_quantity_uses_stricter_bound": True,
        "max_quantity_uses_stricter_bound": True,
        "exit_quantity_equals_entry_quantity": True,
    },
    "notional_policy": {
        "required_filter_any_of": ["MIN_NOTIONAL", "NOTIONAL"],
        "market_applicability_flags_are_respected": True,
        "actual_simulated_fill_price_is_notional_reference": True,
        "entry_and_exit_are_validated": True,
    },
    "cost_policy": {
        "baseline_fee_bps_per_side": "10",
        "baseline_slippage_bps_per_side": "5",
        "entry_fee_base": "executed_entry_notional",
        "exit_fee_base": "executed_exit_notional",
        "fee_is_not_deducted_from_requested_notional": True,
    },
    "price_policy": {
        "positive_price_required": True,
        "price_filter_min_max_validated": True,
        "tick_rounding_deferred_to_task_8": True,
    },
    "safety": _CANONICAL_SAFETY,
}


class ExecutionParityError(RuntimeError):
    """Raised when a simulated fill violates the frozen Spot execution contract."""


@dataclass(frozen=True)
class MarketExecutionRules:
    exchange_info_snapshot_sha256: str
    effective_quantity_step: Decimal
    quantity_step_sources: tuple[str, ...]
    minimum_quantity: Decimal
    maximum_quantity: Decimal
    minimum_notional: Decimal | None
    maximum_notional: Decimal | None
    minimum_price: Decimal
    maximum_price: Decimal
    tick_size: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange_info_snapshot_sha256": self.exchange_info_snapshot_sha256,
            "effective_quantity_step": _decimal_text(self.effective_quantity_step),
            "quantity_step_sources": list(self.quantity_step_sources),
            "minimum_quantity": _decimal_text(self.minimum_quantity),
            "maximum_quantity": _decimal_text(self.maximum_quantity),
            "minimum_notional": (
                _decimal_text(self.minimum_notional)
                if self.minimum_notional is not None
                else None
            ),
            "maximum_notional": (
                _decimal_text(self.maximum_notional)
                if self.maximum_notional is not None
                else None
            ),
            "minimum_price": _decimal_text(self.minimum_price),
            "maximum_price": _decimal_text(self.maximum_price),
            "tick_size": _decimal_text(self.tick_size),
            "price_tick_rounding_deferred_to_task_8": True,
        }

    @property
    def rules_sha256(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class MarketEntryExecution:
    requested_entry_notional: Decimal
    reserved_entry_notional: Decimal
    raw_quantity: Decimal
    executed_quantity: Decimal
    executed_entry_notional: Decimal
    unspent_reserved_notional: Decimal
    entry_fee: Decimal
    entry_cash_cost_including_fee: Decimal


@dataclass(frozen=True)
class MarketExitExecution:
    executed_quantity: Decimal
    executed_exit_notional: Decimal
    exit_fee: Decimal
    exit_proceeds_after_fee: Decimal


@dataclass(frozen=True)
class ProtocolV3Trade(Trade):
    requested_entry_notional_usdc: float = 100.0
    reserved_entry_notional_usdc: float = 100.0
    executed_entry_notional_usdc: float = 0.0
    unspent_reserved_notional_usdc: float = 0.0
    entry_cash_cost_including_fee_usdc: float = 0.0
    executed_exit_notional_usdc: float = 0.0
    exit_proceeds_after_fee_usdc: float = 0.0
    exit_quantity: float = 0.0
    quantity_step_size: float = 0.0
    quantity_rounding_mode: str = "ROUND_DOWN"
    execution_rules_sha256: str = ""
    exchange_info_snapshot_sha256: str = ""
    compounding_enabled: bool = False


@dataclass(frozen=True)
class ProtocolV3PortfolioTrade(ProtocolV3Trade):
    lot_id: str = ""
    entry_notional_usdc: float = 100.0


def load_execution_parity_contract(
    repo_root: str | Path | None = None,
    *,
    contract_path: str | Path | None = None,
) -> dict[str, Any]:
    root = _resolve_repo_root(repo_root)
    path = (
        Path(contract_path)
        if contract_path is not None
        else root / EXECUTION_PARITY_CONTRACT_PATH
    )
    if not path.is_absolute():
        path = root / path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExecutionParityError(
            f"execution parity contract is missing or invalid: {path}"
        ) from exc
    validate_execution_parity_contract(value)
    return value


def validate_execution_parity_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize_json(value) != _CANONICAL_CONTRACT:
        raise ExecutionParityError(
            "Protocol v3 execution parity contract is not canonical"
        )


def build_market_execution_rules(
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
) -> MarketExecutionRules:
    validate_exchange_info_snapshot(exchange_info_snapshot)
    snapshot = (
        exchange_info_snapshot.to_dict()
        if isinstance(exchange_info_snapshot, FrozenExchangeInfoSnapshot)
        else dict(exchange_info_snapshot)
    )
    snapshot_sha = snapshot.get("snapshot_sha256")
    if not isinstance(snapshot_sha, str) or len(snapshot_sha) != 64:
        raise ExecutionParityError("exchange-info snapshot digest is invalid")
    filters = _require_mapping(snapshot.get("filters"), "exchange-info filters")
    price_filter = _require_mapping(filters.get("PRICE_FILTER"), "PRICE_FILTER")
    lot_filter = _require_mapping(filters.get("LOT_SIZE"), "LOT_SIZE")
    market_filter = _require_mapping(
        filters.get("MARKET_LOT_SIZE"), "MARKET_LOT_SIZE"
    )

    lot_step = _decimal(lot_filter.get("step_size"), "LOT_SIZE.step_size")
    market_step = _decimal(
        market_filter.get("step_size"),
        "MARKET_LOT_SIZE.step_size",
        allow_zero=True,
    )
    positive_steps = [
        (name, step)
        for name, step in (
            ("LOT_SIZE", lot_step),
            ("MARKET_LOT_SIZE", market_step),
        )
        if step > 0
    ]
    if not positive_steps:
        raise ExecutionParityError(
            "at least one effective quantity step must be positive"
        )
    effective_step = _decimal_lcm([step for _, step in positive_steps])

    minimum_quantity = max(
        _decimal(lot_filter.get("min_qty"), "LOT_SIZE.min_qty", allow_zero=True),
        _decimal(
            market_filter.get("min_qty"),
            "MARKET_LOT_SIZE.min_qty",
            allow_zero=True,
        ),
    )
    maximum_quantity = min(
        _decimal(lot_filter.get("max_qty"), "LOT_SIZE.max_qty"),
        _decimal(market_filter.get("max_qty"), "MARKET_LOT_SIZE.max_qty"),
    )
    if maximum_quantity < minimum_quantity:
        raise ExecutionParityError("quantity filter bounds have no common interval")

    minimum_notional_values: list[Decimal] = []
    maximum_notional_values: list[Decimal] = []
    minimum_filter = filters.get("MIN_NOTIONAL")
    if minimum_filter is not None:
        row = _require_mapping(minimum_filter, "MIN_NOTIONAL")
        if row.get("apply_to_market") is True:
            minimum_notional_values.append(
                _decimal(row.get("min_notional"), "MIN_NOTIONAL.min_notional")
            )
        elif row.get("apply_to_market") is not False:
            raise ExecutionParityError("MIN_NOTIONAL.apply_to_market must be boolean")
    notional_filter = filters.get("NOTIONAL")
    if notional_filter is not None:
        row = _require_mapping(notional_filter, "NOTIONAL")
        if row.get("apply_min_to_market") is True:
            minimum_notional_values.append(
                _decimal(row.get("min_notional"), "NOTIONAL.min_notional")
            )
        elif row.get("apply_min_to_market") is not False:
            raise ExecutionParityError("NOTIONAL.apply_min_to_market must be boolean")
        if row.get("apply_max_to_market") is True:
            maximum_notional_values.append(
                _decimal(row.get("max_notional"), "NOTIONAL.max_notional")
            )
        elif row.get("apply_max_to_market") is not False:
            raise ExecutionParityError("NOTIONAL.apply_max_to_market must be boolean")

    minimum_notional = (
        max(minimum_notional_values) if minimum_notional_values else None
    )
    maximum_notional = (
        min(maximum_notional_values) if maximum_notional_values else None
    )
    if (
        minimum_notional is not None
        and maximum_notional is not None
        and maximum_notional < minimum_notional
    ):
        raise ExecutionParityError("notional filter bounds have no common interval")

    rules = MarketExecutionRules(
        exchange_info_snapshot_sha256=snapshot_sha,
        effective_quantity_step=effective_step,
        quantity_step_sources=tuple(name for name, _ in positive_steps),
        minimum_quantity=minimum_quantity,
        maximum_quantity=maximum_quantity,
        minimum_notional=minimum_notional,
        maximum_notional=maximum_notional,
        minimum_price=_decimal(
            price_filter.get("min_price"), "PRICE_FILTER.min_price", allow_zero=True
        ),
        maximum_price=_decimal(
            price_filter.get("max_price"), "PRICE_FILTER.max_price", allow_zero=True
        ),
        tick_size=_decimal(price_filter.get("tick_size"), "PRICE_FILTER.tick_size"),
    )
    _validate_rules(rules)
    return rules


def prepare_market_entry(
    entry_price: Decimal | float | int | str,
    fee_rate: Decimal | float | int | str,
    rules: MarketExecutionRules,
    *,
    requested_entry_notional: Decimal | float | int | str = FIXED_REQUESTED_NOTIONAL,
    reserved_entry_notional: Decimal | float | int | str = FIXED_RESERVED_NOTIONAL,
) -> MarketEntryExecution:
    price = _validated_price(entry_price, rules, "entry_price")
    fee = _rate(fee_rate, "fee_rate")
    requested = _decimal(
        requested_entry_notional, "requested_entry_notional_usdc"
    )
    reserved = _decimal(
        reserved_entry_notional, "reserved_entry_notional_usdc"
    )
    if requested != FIXED_REQUESTED_NOTIONAL:
        raise ExecutionParityError(
            "requested_entry_notional_usdc must remain exactly 100"
        )
    if reserved != FIXED_RESERVED_NOTIONAL:
        raise ExecutionParityError(
            "reserved_entry_notional_usdc must remain exactly 100"
        )
    raw_quantity = requested / price
    quantity = _floor_to_step(raw_quantity, rules.effective_quantity_step)
    _validate_quantity(quantity, rules)
    executed_notional = price * quantity
    if executed_notional > requested:
        raise ExecutionParityError(
            "rounded executed entry notional exceeds requested 100 USDC"
        )
    _validate_notional(executed_notional, rules, "entry")
    entry_fee = executed_notional * fee
    return MarketEntryExecution(
        requested_entry_notional=requested,
        reserved_entry_notional=reserved,
        raw_quantity=raw_quantity,
        executed_quantity=quantity,
        executed_entry_notional=executed_notional,
        unspent_reserved_notional=reserved - executed_notional,
        entry_fee=entry_fee,
        entry_cash_cost_including_fee=executed_notional + entry_fee,
    )


def prepare_market_exit(
    exit_price: Decimal | float | int | str,
    executed_entry_quantity: Decimal | float | int | str,
    fee_rate: Decimal | float | int | str,
    rules: MarketExecutionRules,
) -> MarketExitExecution:
    price = _validated_price(exit_price, rules, "exit_price")
    quantity = _decimal(
        executed_entry_quantity, "executed_entry_quantity"
    )
    fee = _rate(fee_rate, "fee_rate")
    _validate_quantity(quantity, rules)
    exit_notional = price * quantity
    _validate_notional(exit_notional, rules, "exit")
    exit_fee = exit_notional * fee
    return MarketExitExecution(
        executed_quantity=quantity,
        executed_exit_notional=exit_notional,
        exit_fee=exit_fee,
        exit_proceeds_after_fee=exit_notional - exit_fee,
    )


def simulate_protocol_v3_strategy(
    candles: list[Candle],
    strategy: StrategyCandidate,
    *,
    days: int,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
    training_days: int = 0,
    blindtest_days: int = 0,
    market_context: Any = None,
) -> SimulationResult:
    """Run the existing timing engine and apply exact Protocol-v3 fill parity."""

    load_execution_parity_contract()
    if _decimal(fee_rate, "fee_rate", allow_zero=True) != BASELINE_FEE_RATE:
        raise ExecutionParityError(
            "canonical Protocol-v3 strategy fee_rate must be exactly 0.001"
        )
    if _decimal(
        slippage_bps, "slippage_bps", allow_zero=True
    ) != BASELINE_SLIPPAGE_BPS:
        raise ExecutionParityError(
            "canonical Protocol-v3 strategy slippage_bps must be exactly 5"
        )
    rules = build_market_execution_rules(exchange_info_snapshot)
    base = simulate_strategy(
        candles,
        strategy,
        days=days,
        trade_usdc=FIXED_LOT_NOTIONAL_USDC,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        training_days=training_days,
        blindtest_days=blindtest_days,
        market_context=market_context,
    )
    repriced = [
        _reprice_trade(trade, rules=rules, fee_rate=fee_rate)
        for trade in base.trades
    ]
    curve, _ = _rebuild_equity_curve(
        candles,
        repriced,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
    )
    metrics = compute_metrics(
        repriced,
        days=days,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
    metrics = replace(metrics, max_drawdown_usdc=max_drawdown_usdc(curve))
    _assert_equity_endpoint(curve, metrics.net_profit_usdc)
    return replace(
        base,
        trades=repriced,
        metrics=metrics,
        equity_curve=curve,
        max_underwater_days=max_underwater_calendar_days(curve),
        drawdown_method="mark_to_market_protocol_v3_execution_parity",
    )


def simulate_protocol_v3_portfolio_strategy(
    candles: list[Candle],
    strategy: StrategyCandidate,
    *,
    days: int,
    policy: PortfolioPolicy,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    training_days: int = 0,
    blindtest_days: int = 0,
) -> PortfolioSimulationResult:
    """Apply the same exact fills to the shared portfolio/Shadow timing reducer."""

    load_execution_parity_contract()
    rules = build_market_execution_rules(exchange_info_snapshot)
    base = simulate_portfolio_strategy(
        candles,
        strategy,
        days=days,
        policy=policy,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
    fee_rate = policy.baseline_fee_bps_per_side / 10_000
    repriced: list[ProtocolV3PortfolioTrade] = []
    for trade in base.trades:
        core = _reprice_trade(trade, rules=rules, fee_rate=fee_rate)
        repriced.append(
            ProtocolV3PortfolioTrade(
                **vars(core),
                lot_id=str(getattr(trade, "lot_id", "")),
                entry_notional_usdc=FIXED_LOT_NOTIONAL_USDC,
            )
        )
    curve, max_executed_exposure = _rebuild_equity_curve(
        candles,
        repriced,
        fee_rate=fee_rate,
        slippage_bps=policy.baseline_slippage_bps_per_side,
    )
    metrics = compute_metrics(
        repriced,
        days=days,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
    metrics = replace(metrics, max_drawdown_usdc=max_drawdown_usdc(curve))
    _assert_equity_endpoint(curve, metrics.net_profit_usdc)
    return replace(
        base,
        trades=repriced,
        metrics=metrics,
        equity_curve=curve,
        max_underwater_days=max_underwater_calendar_days(curve),
        max_open_entry_exposure_usdc=max_executed_exposure,
        drawdown_method="mark_to_market_portfolio_protocol_v3_execution_parity",
    )


def _reprice_trade(
    trade: Trade,
    *,
    rules: MarketExecutionRules,
    fee_rate: Decimal | float | int | str,
) -> ProtocolV3Trade:
    entry = prepare_market_entry(trade.entry_price, fee_rate, rules)
    exit_fill = prepare_market_exit(
        trade.exit_price, entry.executed_quantity, fee_rate, rules
    )
    entry_price = _decimal(trade.entry_price, "trade.entry_price")
    exit_price = _decimal(trade.exit_price, "trade.exit_price")
    entry_mid = _decimal(trade.entry_mid_price, "trade.entry_mid_price")
    exit_mid = _decimal(trade.exit_mid_price, "trade.exit_mid_price")
    quantity = entry.executed_quantity
    gross = (exit_price - entry_price) * quantity
    entry_slippage = (entry_price - entry_mid) * quantity
    exit_slippage = (exit_mid - exit_price) * quantity
    total_fee = entry.entry_fee + exit_fill.exit_fee
    net = gross - total_fee
    return ProtocolV3Trade(
        symbol=trade.symbol,
        side=trade.side,
        entry_time=trade.entry_time,
        exit_time=trade.exit_time,
        entry_price=_float10(entry_price),
        exit_price=_float10(exit_price),
        quantity=_float10(quantity),
        gross_profit_usdc=_float10(gross),
        fees_usdc=_float10(total_fee),
        slippage_usdc=_float10(entry_slippage + exit_slippage),
        net_profit_usdc=_float10(net),
        exit_reason=trade.exit_reason,
        entry_mid_price=_float10(entry_mid),
        exit_mid_price=_float10(exit_mid),
        entry_slippage_usdc=_float10(entry_slippage),
        exit_slippage_usdc=_float10(exit_slippage),
        entry_fee_usdc=_float10(entry.entry_fee),
        exit_fee_usdc=_float10(exit_fill.exit_fee),
        requested_entry_notional_usdc=100.0,
        reserved_entry_notional_usdc=100.0,
        executed_entry_notional_usdc=_float10(entry.executed_entry_notional),
        unspent_reserved_notional_usdc=_float10(
            entry.unspent_reserved_notional
        ),
        entry_cash_cost_including_fee_usdc=_float10(
            entry.entry_cash_cost_including_fee
        ),
        executed_exit_notional_usdc=_float10(
            exit_fill.executed_exit_notional
        ),
        exit_proceeds_after_fee_usdc=_float10(
            exit_fill.exit_proceeds_after_fee
        ),
        exit_quantity=_float10(exit_fill.executed_quantity),
        quantity_step_size=_float10(rules.effective_quantity_step),
        execution_rules_sha256=rules.rules_sha256,
        exchange_info_snapshot_sha256=rules.exchange_info_snapshot_sha256,
    )


def _rebuild_equity_curve(
    candles: Sequence[Candle],
    trades: Sequence[ProtocolV3Trade],
    *,
    fee_rate: Decimal | float | int | str,
    slippage_bps: Decimal | float | int | str,
) -> tuple[tuple[EquityPoint, ...], float]:
    if not candles:
        return (EquityPoint(0, 0.0),), 0.0
    entries: dict[int, list[int]] = defaultdict(list)
    exits: dict[int, list[int]] = defaultdict(list)
    for index, trade in enumerate(trades):
        entries[trade.entry_time].append(index)
        exits[trade.exit_time].append(index)
    open_indexes: set[int] = set()
    realized = Decimal("0")
    rate = _rate(fee_rate, "fee_rate")
    slip = _decimal(slippage_bps, "slippage_bps", allow_zero=True) / Decimal(
        "10000"
    )
    curve: list[EquityPoint] = [EquityPoint(candles[0].open_time, 0.0)]
    max_executed_exposure = Decimal("0")
    for candle in candles:
        for trade_index in entries.get(candle.open_time, ()):  # fill first
            open_indexes.add(trade_index)
        exposure_at_open = sum(
            _decimal(
                trades[index].executed_entry_notional_usdc,
                "executed_entry_notional_usdc",
                allow_zero=True,
            )
            for index in open_indexes
        )
        max_executed_exposure = max(max_executed_exposure, exposure_at_open)
        for trade_index in exits.get(candle.open_time, ()):  # then exact exit qty
            if trade_index not in open_indexes:
                raise ExecutionParityError(
                    "trade exit occurs without its exact purchased quantity open"
                )
            realized += _decimal(
                trades[trade_index].net_profit_usdc,
                "trade.net_profit_usdc",
                allow_negative=True,
            )
            open_indexes.remove(trade_index)
        mark_mid = _decimal(candle.close, "candle.close")
        mark_exit_price = mark_mid * (Decimal("1") - slip)
        equity = realized
        for trade_index in open_indexes:
            trade = trades[trade_index]
            entry_price = _decimal(trade.entry_price, "trade.entry_price")
            quantity = _decimal(trade.quantity, "trade.quantity")
            gross = (mark_exit_price - entry_price) * quantity
            entry_fee = _decimal(
                trade.entry_fee_usdc, "trade.entry_fee_usdc", allow_zero=True
            )
            hypothetical_exit_fee = mark_exit_price * quantity * rate
            equity += gross - entry_fee - hypothetical_exit_fee
        curve.append(
            EquityPoint(
                candle.open_time + EXPECTED_STEP_MS - 1,
                _float10(equity),
            )
        )
    if open_indexes:
        raise ExecutionParityError("repriced simulation ended with an open quantity")
    return tuple(curve), _float10(max_executed_exposure)


def _validate_rules(rules: MarketExecutionRules) -> None:
    if rules.effective_quantity_step <= 0:
        raise ExecutionParityError("effective quantity step must be positive")
    if rules.minimum_quantity < 0 or rules.maximum_quantity <= 0:
        raise ExecutionParityError("quantity bounds are invalid")
    if rules.maximum_quantity < rules.minimum_quantity:
        raise ExecutionParityError("quantity bounds are contradictory")
    if rules.tick_size <= 0:
        raise ExecutionParityError("PRICE_FILTER tick_size must be positive")
    if rules.minimum_price < 0 or rules.maximum_price < 0:
        raise ExecutionParityError("PRICE_FILTER bounds must be non-negative")
    if rules.maximum_price and rules.maximum_price < rules.minimum_price:
        raise ExecutionParityError("PRICE_FILTER bounds are contradictory")


def _validated_price(
    value: Decimal | float | int | str,
    rules: MarketExecutionRules,
    label: str,
) -> Decimal:
    price = _decimal(value, label)
    if rules.minimum_price and price < rules.minimum_price:
        raise ExecutionParityError(f"{label} is below PRICE_FILTER minimum")
    if rules.maximum_price and price > rules.maximum_price:
        raise ExecutionParityError(f"{label} is above PRICE_FILTER maximum")
    return price


def _validate_quantity(quantity: Decimal, rules: MarketExecutionRules) -> None:
    if quantity <= 0:
        raise ExecutionParityError("rounded market quantity is zero")
    if quantity < rules.minimum_quantity:
        raise ExecutionParityError("rounded market quantity is below minimum")
    if quantity > rules.maximum_quantity:
        raise ExecutionParityError("rounded market quantity is above maximum")
    if quantity % rules.effective_quantity_step != 0:
        raise ExecutionParityError("market quantity is not on the effective step grid")


def _validate_notional(
    notional: Decimal, rules: MarketExecutionRules, side: str
) -> None:
    if rules.minimum_notional is not None and notional < rules.minimum_notional:
        raise ExecutionParityError(
            f"{side} notional is below the applicable market minimum"
        )
    if rules.maximum_notional is not None and notional > rules.maximum_notional:
        raise ExecutionParityError(
            f"{side} notional is above the applicable market maximum"
        )


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _decimal_lcm(values: Sequence[Decimal]) -> Decimal:
    if not values or any(value <= 0 for value in values):
        raise ExecutionParityError("positive quantity steps are required")
    scale = max(max(0, -value.as_tuple().exponent) for value in values)
    multiplier = 10**scale
    integers = [int(value * multiplier) for value in values]
    if any(value <= 0 for value in integers):
        raise ExecutionParityError("quantity steps cannot be represented exactly")

    def lcm(left: int, right: int) -> int:
        return abs(left * right) // gcd(left, right)

    return Decimal(reduce(lcm, integers)) / Decimal(multiplier)


def _rate(value: Decimal | float | int | str, label: str) -> Decimal:
    rate = _decimal(value, label, allow_zero=True)
    if rate >= 1:
        raise ExecutionParityError(f"{label} must be below 1")
    return rate


def _decimal(
    value: Any,
    label: str,
    *,
    allow_zero: bool = False,
    allow_negative: bool = False,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int, float)):
        raise ExecutionParityError(f"{label} must be a finite decimal value")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ExecutionParityError(f"{label} is not a valid decimal") from exc
    if not parsed.is_finite():
        raise ExecutionParityError(f"{label} must be finite")
    if allow_negative:
        return parsed
    if parsed < 0 or (parsed == 0 and not allow_zero):
        requirement = "non-negative" if allow_zero else "positive"
        raise ExecutionParityError(f"{label} must be {requirement}")
    return parsed


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        raise ExecutionParityError("decimal value is missing")
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _float10(value: Decimal) -> float:
    return round(float(value), 10)


def _assert_equity_endpoint(
    curve: tuple[EquityPoint, ...], expected_net_profit: float
) -> None:
    if not curve or not isclose(
        curve[-1].equity_usdc,
        expected_net_profit,
        rel_tol=1e-10,
        abs_tol=1e-8,
    ):
        raise ExecutionParityError(
            "Protocol v3 equity endpoint does not match repriced realized PnL"
        )


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExecutionParityError(f"{label} must be an object")
    return value


def _normalize_json(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ExecutionParityError(
            "execution parity payload is not strict canonical JSON"
        ) from exc


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _resolve_repo_root(repo_root: str | Path | None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    return Path(__file__).resolve().parents[3]


__all__ = [
    "BASELINE_FEE_RATE",
    "BASELINE_SLIPPAGE_BPS",
    "EXECUTION_PARITY_CONTRACT_PATH",
    "EXECUTION_PARITY_CONTRACT_SCHEMA",
    "EXECUTION_PARITY_CONTRACT_VERSION",
    "ExecutionParityError",
    "FIXED_REQUESTED_NOTIONAL",
    "FIXED_RESERVED_NOTIONAL",
    "MarketEntryExecution",
    "MarketExecutionRules",
    "MarketExitExecution",
    "ProtocolV3PortfolioTrade",
    "ProtocolV3Trade",
    "build_market_execution_rules",
    "load_execution_parity_contract",
    "prepare_market_entry",
    "prepare_market_exit",
    "simulate_protocol_v3_portfolio_strategy",
    "simulate_protocol_v3_strategy",
    "validate_execution_parity_contract",
]
