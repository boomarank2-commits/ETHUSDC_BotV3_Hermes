"""Conservative Binance Spot LONG-only simulator for ETHUSDC."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from ethusdc_bot.backtest.data_loader import Candle, SYMBOL
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


@dataclass(frozen=True)
class SimulationResult:
    strategy: StrategyCandidate
    metrics: BacktestMetrics
    trades: list[Trade]
    rejection_reasons: Counter[str] = field(default_factory=Counter)

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
) -> SimulationResult:
    if str(strategy.params.get("side", "LONG")) != "LONG":
        raise ValueError("Simulator is LONG-only; shorts are forbidden")
    symbol = str(strategy.params.get("symbol", SYMBOL))
    rejections: Counter[str] = Counter()
    if symbol != SYMBOL:
        rejections["context_symbol_not_tradeable"] += 1
        return SimulationResult(strategy, compute_metrics([], days=days, training_days=training_days, blindtest_days=blindtest_days), [], rejections)
    trades: list[Trade] = []
    position: dict[str, float | int] | None = None
    pending_entry = False
    for index, candle in enumerate(candles):
        if pending_entry and position is None:
            entry_price = candle.open * (1 + slippage_bps / 10_000)
            quantity = trade_usdc / entry_price
            position = {"entry_price": entry_price, "quantity": quantity, "entry_time": candle.open_time, "entry_index": index}
            pending_entry = False
        if position is not None and _should_exit(candles, index, position, strategy):
            trade = _exit_trade(candle, position, fee_rate, slippage_bps, trade_usdc)
            trades.append(trade)
            position = None
            # A signal on this same candle may schedule a next-candle entry below.
        if position is None and index < len(candles) - 1 and _signal(candles, index, strategy):
            pending_entry = True
    if position is not None and candles:
        trades.append(_exit_trade(candles[-1], position, fee_rate, slippage_bps, trade_usdc, exit_reason="end_of_data"))
    metrics = compute_metrics(trades, days=days, training_days=training_days, blindtest_days=blindtest_days)
    return SimulationResult(strategy=strategy, metrics=metrics, trades=trades, rejection_reasons=rejections)


def _signal(candles: list[Candle], index: int, strategy: StrategyCandidate) -> bool:
    if strategy.family == "always_long":
        return True
    lookback = int(strategy.params.get("lookback", 5) or 5)
    if index < lookback:
        return False
    threshold = float(strategy.params.get("threshold_bps", 10) or 0) / 10_000
    current = candles[index].close
    reference = candles[index - lookback].close
    if reference <= 0:
        return False
    change = current / reference - 1
    if strategy.family == "momentum":
        return change >= threshold
    if strategy.family == "mean_reversion":
        return change <= -threshold
    if strategy.family == "breakout":
        previous_high = max(c.high for c in candles[index - lookback : index])
        return current >= previous_high * (1 + threshold)
    return False


def _should_exit(candles: list[Candle], index: int, position: dict[str, float | int], strategy: StrategyCandidate) -> bool:
    entry_index = int(position["entry_index"])
    if index <= entry_index:
        return False
    max_hold = int(strategy.params.get("max_hold_minutes", 30) or 30)
    if index - entry_index >= max_hold:
        return True
    entry_price = float(position["entry_price"])
    change_bps = (candles[index - 1].close / entry_price - 1) * 10_000
    take_profit = float(strategy.params.get("take_profit_bps", 80) or 80)
    stop_loss = float(strategy.params.get("stop_loss_bps", 60) or 60)
    return change_bps >= take_profit or change_bps <= -stop_loss


def _exit_trade(
    candle: Candle,
    position: dict[str, float | int],
    fee_rate: float,
    slippage_bps: float,
    trade_usdc: float,
    *,
    exit_reason: str = "rule",
) -> Trade:
    entry_price = float(position["entry_price"])
    quantity = float(position["quantity"])
    exit_price = candle.open * (1 - slippage_bps / 10_000)
    gross = (exit_price - entry_price) * quantity
    exit_notional = exit_price * quantity
    fees = trade_usdc * fee_rate + exit_notional * fee_rate
    ideal_qty = trade_usdc / max(candle.open, 1e-12)
    slippage = abs((entry_price - candle.open) * ideal_qty) + abs((candle.open - exit_price) * quantity)
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
    )
