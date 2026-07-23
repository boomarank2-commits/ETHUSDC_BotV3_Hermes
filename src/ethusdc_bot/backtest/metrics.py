"""Backtest metrics for conservative ETHUSDC spot simulation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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


def _conservative_profit_factor(wins: list[float], gross_loss: float) -> float:
    """Return a finite PF and avoid tiny lossless samples dominating ranking.

    A lossless sample has no observed loss denominator.  Treat one average
    winning trade as a conservative pseudo-loss, which yields PF == win count.
    One isolated winner therefore scores 1.0 instead of infinity, while a
    genuinely broader lossless sample remains distinguishable and still has to
    satisfy the existing trade-count and robustness gates.
    """

    gross_win = sum(wins)
    if gross_loss > 0:
        return gross_win / gross_loss
    if not wins or gross_win <= 0:
        return 0.0
    pseudo_loss = gross_win / len(wins)
    return gross_win / pseudo_loss if pseudo_loss > 0 else 0.0


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
        profit_factor=round(_conservative_profit_factor(wins, gross_loss), 10),
        average_trade_usdc=round(net / trade_count, 10) if trade_count else 0.0,
        fees_usdc=round(sum(trade.fees_usdc for trade in trade_list), 10),
        slippage_usdc=round(sum(trade.slippage_usdc for trade in trade_list), 10),
        training_days=training_days,
        blindtest_days=blindtest_days,
    )
