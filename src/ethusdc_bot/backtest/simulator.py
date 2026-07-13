"""Conservative Binance Spot LONG-only simulator for ETHUSDC."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from math import isclose

from ethusdc_bot.backtest.context_features import ContextVetoPolicy, evaluate_context_veto, validate_context_against_trade_candles
from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle, EXPECTED_STEP_MS, SYMBOL
from ethusdc_bot.backtest.equity import EquityPoint, max_drawdown_usdc, max_underwater_calendar_days
from ethusdc_bot.backtest.metrics import BacktestMetrics, compute_metrics


@dataclass(frozen=True)
class StrategyCandidate:
    family: str
    params: dict[str, float | int | str]


@dataclass(frozen=True)
class Trade:
    symbol: str
    side: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    quantity: float
    gross_profit_usdc: float
    fees_usdc: float
    slippage_usdc: float
    net_profit_usdc: float
    exit_reason: str
    entry_mid_price: float = 0.0
    exit_mid_price: float = 0.0
    entry_slippage_usdc: float = 0.0
    exit_slippage_usdc: float = 0.0
    entry_fee_usdc: float = 0.0
    exit_fee_usdc: float = 0.0


@dataclass(frozen=True)
class EntryDecision:
    """One trailing-data-only entry decision with diagnostic attribution."""

    allowed: bool
    raw_signal: bool
    reason: str | None


@dataclass(frozen=True)
class SimulationResult:
    strategy: StrategyCandidate
    metrics: BacktestMetrics
    trades: list[Trade]
    rejection_reasons: Counter[str] = field(default_factory=Counter)
    signal_funnel: Counter[str] = field(default_factory=Counter)
    equity_curve: tuple[EquityPoint, ...] = ()
    max_underwater_days: int = 0
    drawdown_method: str = "mark_to_market"

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


def simulate_strategy(
    candles: list[Candle],
    strategy: StrategyCandidate,
    *,
    days: int,
    trade_usdc: float = 100.0,
    fee_rate: float = 0.001,
    slippage_bps: float = 5.0,
    training_days: int = 0,
    blindtest_days: int = 0,
    market_context: AlignedMarketCandles | None = None,
) -> SimulationResult:
    if str(strategy.params.get("side", "LONG")) != "LONG":
        raise ValueError("Simulator is LONG-only; shorts are forbidden")
    symbol = str(strategy.params.get("symbol", SYMBOL))
    rejections: Counter[str] = Counter()
    signal_funnel: Counter[str] = Counter()
    if symbol != SYMBOL:
        rejections["context_symbol_not_tradeable"] += 1
        signal_funnel.update(
            {
                "observations_total": len(candles),
                "entry_evaluations": 1,
                "rejected_signals": 1,
                "rejected.context_symbol_not_tradeable": 1,
            }
        )
        return _build_result(
            strategy,
            [],
            rejections,
            signal_funnel,
            _zero_equity_curve(candles),
            days=days,
            training_days=training_days,
            blindtest_days=blindtest_days,
        )
    context_policy: ContextVetoPolicy | None = None
    if strategy.family == "context_filter":
        context_policy = ContextVetoPolicy.from_candidate_params(strategy.params)
        if market_context is not None:
            validate_context_against_trade_candles(candles, market_context)
    trades: list[Trade] = []
    position: dict[str, float | int] | None = None
    pending_entry = False
    cooldown_until_index = -1
    realized_net_usdc = 0.0
    equity_curve: list[EquityPoint] = [
        EquityPoint(candles[0].open_time if candles else 0, 0.0)
    ]
    for index, candle in enumerate(candles):
        signal_funnel["observations_total"] += 1
        if pending_entry and position is None:
            entry_mid_price = candle.open
            entry_price = entry_mid_price * (1 + slippage_bps / 10_000)
            quantity = trade_usdc / entry_price
            position = {
                "entry_mid_price": entry_mid_price,
                "entry_price": entry_price,
                "quantity": quantity,
                "entry_time": candle.open_time,
                "entry_index": index,
                "entry_fee_usdc": entry_price * quantity * fee_rate,
            }
            pending_entry = False
        if position is not None:
            exit_reason = _exit_reason(candles, index, position, strategy)
        else:
            exit_reason = None
        if position is not None and exit_reason is not None:
            trade = _exit_trade(candle, position, fee_rate, slippage_bps, trade_usdc, exit_reason=exit_reason)
            trades.append(trade)
            realized_net_usdc += trade.net_profit_usdc
            position = None
            cooldown_until_index = index + int(strategy.params.get("cooldown_minutes", 0) or 0)
            # A signal on this same candle may schedule a next-candle entry below.
        if position is not None and index == len(candles) - 1:
            trade = _exit_trade(
                candle,
                position,
                fee_rate,
                slippage_bps,
                trade_usdc,
                exit_reason="end_of_data",
            )
            trades.append(trade)
            realized_net_usdc += trade.net_profit_usdc
            position = None
        if position is not None:
            signal_funnel["blocked.position_open"] += 1
        elif index >= len(candles) - 1:
            signal_funnel["blocked.end_of_data"] += 1
        elif index < cooldown_until_index:
            signal_funnel["blocked.cooldown"] += 1
        else:
            signal_funnel["entry_evaluations"] += 1
            decision = _entry_decision(
                candles,
                index,
                strategy,
                market_context=market_context,
                context_policy=context_policy,
            )
            if decision.raw_signal:
                signal_funnel["raw_entry_signals"] += 1
            if decision.allowed:
                signal_funnel["accepted_entry_signals"] += 1
                pending_entry = True
            else:
                rejection_reason = decision.reason or "entry_signal_absent"
                rejections[rejection_reason] += 1
                signal_funnel["rejected_signals"] += 1
                signal_funnel[f"rejected.{rejection_reason}"] += 1
        equity_curve.append(
            EquityPoint(
                timestamp_ms=candle.open_time + EXPECTED_STEP_MS - 1,
                equity_usdc=_liquidation_equity_usdc(
                    realized_net_usdc,
                    position,
                    candle.close,
                    fee_rate,
                    slippage_bps,
                ),
            )
        )
    return _build_result(
        strategy,
        trades,
        rejections,
        signal_funnel,
        tuple(equity_curve),
        days=days,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )


def _build_result(
    strategy: StrategyCandidate,
    trades: list[Trade],
    rejection_reasons: Counter[str],
    signal_funnel: Counter[str],
    equity_curve: tuple[EquityPoint, ...],
    *,
    days: int,
    training_days: int,
    blindtest_days: int,
) -> SimulationResult:
    for key in (
        "observations_total",
        "entry_evaluations",
        "raw_entry_signals",
        "accepted_entry_signals",
        "rejected_signals",
        "blocked.position_open",
        "blocked.cooldown",
        "blocked.end_of_data",
    ):
        signal_funnel.setdefault(key, 0)
    metrics = compute_metrics(
        trades,
        days=days,
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
    if not equity_curve:
        equity_curve = (EquityPoint(0, 0.0),)
    endpoint = metrics.net_profit_usdc
    if not isclose(equity_curve[-1].equity_usdc, endpoint, rel_tol=1e-10, abs_tol=1e-8):
        raise RuntimeError("Mark-to-market equity endpoint does not match realized net profit")
    if equity_curve[-1].equity_usdc != endpoint:
        equity_curve = (*equity_curve[:-1], replace(equity_curve[-1], equity_usdc=endpoint))
    metrics = replace(metrics, max_drawdown_usdc=max_drawdown_usdc(equity_curve))
    return SimulationResult(
        strategy=strategy,
        metrics=metrics,
        trades=trades,
        rejection_reasons=rejection_reasons,
        signal_funnel=signal_funnel,
        equity_curve=equity_curve,
        max_underwater_days=max_underwater_calendar_days(equity_curve),
    )


def _zero_equity_curve(candles: list[Candle]) -> tuple[EquityPoint, ...]:
    if not candles:
        return (EquityPoint(0, 0.0),)
    return (
        EquityPoint(candles[0].open_time, 0.0),
        *(EquityPoint(candle.open_time + EXPECTED_STEP_MS - 1, 0.0) for candle in candles),
    )


def _liquidation_equity_usdc(
    realized_net_usdc: float,
    position: dict[str, float | int] | None,
    mark_mid_price: float,
    fee_rate: float,
    slippage_bps: float,
) -> float:
    """Mark an open LONG at conservative immediate-liquidation value.

    Execution slippage is embedded in entry and hypothetical exit prices. Only
    fees are subtracted explicitly, which prevents slippage from being charged
    a second time.
    """

    if position is None:
        return round(realized_net_usdc, 10)
    entry_price = float(position["entry_price"])
    quantity = float(position["quantity"])
    exit_price = mark_mid_price * (1 - slippage_bps / 10_000)
    gross = (exit_price - entry_price) * quantity
    entry_fee = float(position.get("entry_fee_usdc", entry_price * quantity * fee_rate))
    exit_fee = exit_price * quantity * fee_rate
    return round(realized_net_usdc + gross - entry_fee - exit_fee, 10)


def _entry_decision(
    candles: list[Candle],
    index: int,
    strategy: StrategyCandidate,
    *,
    market_context: AlignedMarketCandles | None,
    context_policy: ContextVetoPolicy | None,
) -> EntryDecision:
    if strategy.family != "context_filter":
        return _signal_decision(candles, index, strategy)

    base_family = str(
        strategy.params.get(
            "context_base_family",
            strategy.params.get("base_family", "momentum"),
        )
    )
    if base_family == "context_filter":
        return EntryDecision(False, False, "context_recursive_base_forbidden")
    base_params = {
        key: value
        for key, value in strategy.params.items()
        if key != "context_base_family" and not key.startswith("context_")
    }
    base_decision = _signal_decision(
        candles,
        index,
        StrategyCandidate(base_family, base_params),
    )
    if not base_decision.allowed:
        return base_decision
    if market_context is None or context_policy is None:
        return EntryDecision(False, base_decision.raw_signal, "context_data_missing")
    decision = evaluate_context_veto(market_context, index, context_policy)
    if decision.allowed:
        return EntryDecision(True, base_decision.raw_signal, None)
    return EntryDecision(False, base_decision.raw_signal, decision.reason)


def _signal(candles: list[Candle], index: int, strategy: StrategyCandidate) -> bool:
    return _signal_decision(candles, index, strategy).allowed


def _signal_decision(
    candles: list[Candle], index: int, strategy: StrategyCandidate
) -> EntryDecision:
    if strategy.family == "always_long":
        return EntryDecision(True, True, None)
    lookback = int(strategy.params.get("lookback", 5) or 5)
    if index < lookback:
        return EntryDecision(False, False, "entry_warmup")
    threshold = float(strategy.params.get("threshold_bps", 10) or 0) / 10_000
    current = candles[index].close
    reference = candles[index - lookback].close
    if reference <= 0:
        return EntryDecision(False, False, "entry_reference_invalid")
    change = current / reference - 1
    if strategy.family == "momentum":
        allowed = change >= threshold
        return EntryDecision(allowed, allowed, None if allowed else "momentum_threshold_not_met")
    if strategy.family == "mean_reversion":
        allowed = change <= -threshold
        return EntryDecision(allowed, allowed, None if allowed else "mean_reversion_threshold_not_met")
    if strategy.family == "breakout":
        previous_high = max(c.high for c in candles[index - lookback : index])
        allowed = current >= previous_high * (1 + threshold)
        return EntryDecision(allowed, allowed, None if allowed else "breakout_threshold_not_met")
    if strategy.family == "momentum_trend_filter":
        trend = _trend_bps(candles, index, int(strategy.params.get("trend_lookback", lookback) or lookback))
        raw_signal = change >= threshold
        if not raw_signal:
            return EntryDecision(False, False, "momentum_threshold_not_met")
        allowed = trend >= float(strategy.params.get("trend_min_bps", 0) or 0)
        return EntryDecision(allowed, True, None if allowed else "trend_filter_rejected")
    if strategy.family == "breakout_volatility_filter":
        previous_high = max(c.high for c in candles[index - lookback : index])
        vol = _volatility_bps(candles, index, int(strategy.params.get("volatility_lookback", lookback) or lookback))
        raw_signal = current >= previous_high * (1 + threshold)
        if not raw_signal:
            return EntryDecision(False, False, "breakout_threshold_not_met")
        if vol < float(strategy.params.get("min_vol_bps", 0) or 0):
            return EntryDecision(False, True, "volatility_below_min")
        if vol > float(strategy.params.get("max_vol_bps", 10_000) or 10_000):
            return EntryDecision(False, True, "volatility_above_max")
        return EntryDecision(True, True, None)
    if strategy.family == "mean_reversion_regime_filter":
        trend = abs(_trend_bps(candles, index, int(strategy.params.get("trend_lookback", lookback) or lookback)))
        raw_signal = change <= -threshold
        if not raw_signal:
            return EntryDecision(False, False, "mean_reversion_threshold_not_met")
        allowed = trend <= float(strategy.params.get("max_abs_trend_bps", 10_000) or 10_000)
        return EntryDecision(allowed, True, None if allowed else "regime_filter_rejected")
    if strategy.family == "pullback_in_trend":
        trend = _trend_bps(candles, index, int(strategy.params.get("trend_lookback", lookback) or lookback))
        raw_signal = change <= -threshold
        if not raw_signal:
            return EntryDecision(False, False, "pullback_threshold_not_met")
        allowed = trend >= float(strategy.params.get("trend_min_bps", 0) or 0)
        return EntryDecision(allowed, True, None if allowed else "trend_filter_rejected")
    if strategy.family == "session_filter":
        base = _signal_decision(
            candles,
            index,
            StrategyCandidate(str(strategy.params.get("base_family", "momentum")), dict(strategy.params)),
        )
        if not _in_session(candles[index].open_time, int(strategy.params.get("session_start_hour", 0) or 0), int(strategy.params.get("session_end_hour", 24) or 24)):
            return EntryDecision(False, base.raw_signal, "session_filter_closed")
        return base
    if strategy.family == "cooldown_fee_aware":
        base = _signal_decision(
            candles,
            index,
            StrategyCandidate(str(strategy.params.get("base_family", "momentum")), dict(strategy.params)),
        )
        if abs(change) * 10_000 < float(strategy.params.get("min_expected_move_bps", 0) or 0):
            return EntryDecision(False, base.raw_signal, "expected_move_below_min")
        return base
    if strategy.family == "context_filter":
        return EntryDecision(False, False, "context_requires_entry_boundary")
    return EntryDecision(False, False, "unknown_strategy_family")


def _trend_bps(candles: list[Candle], index: int, lookback: int) -> float:
    if index < lookback:
        return 0.0
    reference = candles[index - lookback].close
    return ((candles[index].close / reference) - 1) * 10_000 if reference else 0.0


def _volatility_bps(candles: list[Candle], index: int, lookback: int) -> float:
    if index <= 0:
        return 0.0
    start = max(1, index - lookback + 1)
    moves = []
    for cursor in range(start, index + 1):
        previous = candles[cursor - 1].close
        if previous:
            moves.append(abs(candles[cursor].close / previous - 1) * 10_000)
    return sum(moves) / len(moves) if moves else 0.0


def _in_session(open_time: int, start_hour: int, end_hour: int) -> bool:
    hour = datetime.fromtimestamp(open_time / 1000, tz=UTC).hour
    if start_hour <= end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _exit_reason(candles: list[Candle], index: int, position: dict[str, float | int], strategy: StrategyCandidate) -> str | None:
    entry_index = int(position["entry_index"])
    if index <= entry_index:
        return None
    max_hold = int(strategy.params.get("max_hold_minutes", 30) or 30)
    if index - entry_index >= max_hold:
        return "time_exit"
    entry_price = float(position["entry_price"])
    previous_close = candles[index - 1].close
    change_bps = (previous_close / entry_price - 1) * 10_000
    take_profit = float(strategy.params.get("take_profit_bps", 80) or 80)
    stop_loss = float(strategy.params.get("stop_loss_bps", 60) or 60)
    if change_bps >= take_profit:
        return "take_profit"
    if change_bps <= -stop_loss:
        return "stop_loss"
    best_close = max(c.close for c in candles[entry_index:index])
    best_change_bps = (best_close / entry_price - 1) * 10_000
    break_even_after = float(strategy.params.get("break_even_after_bps", 0) or 0)
    if break_even_after > 0 and best_change_bps >= break_even_after and change_bps <= 0:
        return "break_even"
    trailing_stop = float(strategy.params.get("trailing_stop_bps", 0) or 0)
    if trailing_stop > 0 and best_change_bps > trailing_stop and (best_close / previous_close - 1) * 10_000 >= trailing_stop:
        return "trailing_stop"
    return None


def _should_exit(candles: list[Candle], index: int, position: dict[str, float | int], strategy: StrategyCandidate) -> bool:
    return _exit_reason(candles, index, position, strategy) is not None


def _exit_trade(
    candle: Candle,
    position: dict[str, float | int],
    fee_rate: float,
    slippage_bps: float,
    trade_usdc: float,
    *,
    exit_reason: str = "rule",
) -> Trade:
    entry_mid_price = float(position.get("entry_mid_price", position["entry_price"]))
    entry_price = float(position["entry_price"])
    quantity = float(position["quantity"])
    exit_mid_price = candle.open
    exit_price = exit_mid_price * (1 - slippage_bps / 10_000)
    gross = (exit_price - entry_price) * quantity
    exit_notional = exit_price * quantity
    entry_fee = entry_price * quantity * fee_rate
    exit_fee = exit_notional * fee_rate
    fees = entry_fee + exit_fee
    entry_slippage = (entry_price - entry_mid_price) * quantity
    exit_slippage = (exit_mid_price - exit_price) * quantity
    slippage = entry_slippage + exit_slippage
    net = gross - fees
    return Trade(
        symbol=SYMBOL,
        side="LONG",
        entry_time=int(position["entry_time"]),
        exit_time=candle.open_time,
        entry_price=entry_price,
        exit_price=exit_price,
        quantity=quantity,
        gross_profit_usdc=round(gross, 10),
        fees_usdc=round(fees, 10),
        slippage_usdc=round(slippage, 10),
        net_profit_usdc=round(net, 10),
        exit_reason=exit_reason,
        entry_mid_price=entry_mid_price,
        exit_mid_price=exit_mid_price,
        entry_slippage_usdc=round(entry_slippage, 10),
        exit_slippage_usdc=round(exit_slippage, 10),
        entry_fee_usdc=round(entry_fee, 10),
        exit_fee_usdc=round(exit_fee, 10),
    )
