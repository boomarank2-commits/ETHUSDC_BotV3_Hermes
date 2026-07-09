"""Exit-reason and trade-cause summaries for offline research."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from ethusdc_bot.backtest.simulator import Trade


def analyze_exit_reasons(trades: Iterable[Trade]) -> dict[str, Any]:
    """Aggregate realized trades by simulator-provided exit reason.

    The function only summarizes actual trade fields. It does not invent reasons
    or infer future information.
    """

    trade_list = list(trades)
    total = len(trade_list)
    grouped: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"count": 0, "net_usdc": 0.0, "fees_usdc": 0.0, "slippage_usdc": 0.0, "average_trade_usdc": 0.0}
    )
    losses = [trade.net_profit_usdc for trade in trade_list if trade.net_profit_usdc < 0]
    for trade in trade_list:
        reason = trade.exit_reason or "unknown"
        row = grouped[reason]
        row["count"] = int(row["count"]) + 1
        row["net_usdc"] = float(row["net_usdc"]) + trade.net_profit_usdc
        row["fees_usdc"] = float(row["fees_usdc"]) + trade.fees_usdc
        row["slippage_usdc"] = float(row["slippage_usdc"]) + trade.slippage_usdc
    by_reason: dict[str, dict[str, float | int]] = {}
    for reason, row in sorted(grouped.items()):
        count = int(row["count"])
        net = round(float(row["net_usdc"]), 10)
        fees = round(float(row["fees_usdc"]), 10)
        slippage = round(float(row["slippage_usdc"]), 10)
        by_reason[reason] = {
            "count": count,
            "net_usdc": net,
            "fees_usdc": fees,
            "slippage_usdc": slippage,
            "average_trade_usdc": round(net / count, 10) if count else 0.0,
        }
    total_fees = sum(trade.fees_usdc for trade in trade_list)
    total_slippage = sum(trade.slippage_usdc for trade in trade_list)
    return {
        "total_trades": total,
        "by_exit_reason": by_reason,
        "stop_loss_share": _share(by_reason, total, "stop_loss"),
        "take_profit_share": _share(by_reason, total, "take_profit"),
        "time_exit_share": _share(by_reason, total, "time_exit"),
        "trailing_or_break_even_share": round((_count(by_reason, "trailing_stop") + _count(by_reason, "break_even")) / total, 10) if total else 0.0,
        "cost_load_per_trade": round((total_fees + total_slippage) / total, 10) if total else 0.0,
        "loss_per_losing_trade": round(sum(losses) / len(losses), 10) if losses else 0.0,
    }


def _count(by_reason: dict[str, dict[str, float | int]], reason: str) -> int:
    return int(by_reason.get(reason, {}).get("count", 0))


def _share(by_reason: dict[str, dict[str, float | int]], total: int, reason: str) -> float:
    return round(_count(by_reason, reason) / total, 10) if total else 0.0
