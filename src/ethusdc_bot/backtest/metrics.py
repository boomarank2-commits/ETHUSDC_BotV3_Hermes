"""Backtest metrics for conservative ETHUSDC spot simulation."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import inf
from typing import Iterable, Protocol


class TradeLike(Protocol):
    net_profit_usdc: float
    fees_usdc: float
    slippage_usdc: float


@dataclass(frozen=True)
class BacktestMetrics:
    net_profit_usdc: float
    net_usdc_per_day: float
    trade_count: int
    winrate: float
    max_drawdown_usdc: float
    profit_factor: float
    average_trade_usdc: float
    fees_usdc: float
    slippage_usdc: float
    training_days: int
    blindtest_days: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def compute_metrics(
    trades: Iterable[TradeLike],
    *,
    days: int,
    training_days: int = 0,
    blindtest_days: int = 0,
) -> BacktestMetrics:
    trade_list = list(trades)
    profits = [trade.net_profit_usdc for trade in trade_list]
    net = round(sum(profits), 10)
    wins = [profit for profit in profits if profit > 0]
    losses = [profit for profit in profits if profit < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    trade_count = len(trade_list)
    return BacktestMetrics(
        net_profit_usdc=round(net, 10),
        net_usdc_per_day=round(net / days, 10) if days else 0.0,
        trade_count=trade_count,
        winrate=round(len(wins) / trade_count, 10) if trade_count else 0.0,
        max_drawdown_usdc=round(max_dd, 10),
        profit_factor=round(gross_win / gross_loss, 10) if gross_loss else (inf if gross_win else 0.0),
        average_trade_usdc=round(net / trade_count, 10) if trade_count else 0.0,
        fees_usdc=round(sum(trade.fees_usdc for trade in trade_list), 10),
        slippage_usdc=round(sum(trade.slippage_usdc for trade in trade_list), 10),
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
