"""Aggregate selection evidence from chronological Walk-Forward folds.

The aggregator receives only fold-local training and validation windows plus
hypothetical simulation results. It has no loader or holdout dependency.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.equity import (
    EquityPoint,
    max_drawdown_usdc,
    max_underwater_calendar_days,
)
from ethusdc_bot.backtest.selection_evidence import (
    REGIME_DEFINITION,
    REGIME_LABELS,
    REGIME_THRESHOLD_SOURCE,
    build_regime_evidence,
    build_rolling_evidence,
    build_temporal_evidence,
)
from ethusdc_bot.backtest.simulator import SimulationResult, Trade


@dataclass(frozen=True)
class FoldSelectionObservation:
    fold_id: int
    training_candles: Sequence[Candle]
    validation_candles: Sequence[Candle]
    result: SimulationResult


def build_walk_forward_selection_evidence(
    observations: Sequence[FoldSelectionObservation],
    *,
    chained_equity: Sequence[EquityPoint],
    regime_lookback_minutes: int = 60,
) -> dict[str, Any]:
    """Build rolling, temporal and fold-local regime evidence."""

    if not observations:
        return {
            "rolling": build_rolling_evidence(
                SimpleNamespace(
                    trades=[],
                    max_drawdown_usdc=0.0,
                    max_underwater_days=0,
                    drawdown_method="mark_to_market",
                )
            ),
            "temporal": {
                "months_observed": 0,
                "positive_months": 0,
                "active_months": 0,
                "max_no_trade_gap_days": 0,
                "quarters_observed": 0,
                "positive_quarters": 0,
                "min_quarter_trade_count": 0,
                "worst_month_net_usdc": 0.0,
                "window_start_utc": None,
                "window_end_utc": None,
                "months": [],
                "quarters": [],
            },
            "regime": _aggregate_regime_rows([], regime_lookback_minutes),
            "friction_share_of_positive_pre_cost_pnl": 1.0,
            "fold_count": 0,
            "uses_audit_or_holdout": False,
        }

    all_trades: list[Trade] = []
    regime_reports: list[dict[str, Any]] = []
    for observation in observations:
        if not observation.training_candles or not observation.validation_candles:
            raise ValueError("Walk-Forward evidence folds must contain training and validation candles")
        all_trades.extend(observation.result.trades)
        regime_reports.append(
            build_regime_evidence(
                observation.training_candles,
                observation.validation_candles,
                observation.result.trades,
                lookback_minutes=regime_lookback_minutes,
            )
        )

    rolling = build_rolling_evidence(
        SimpleNamespace(
            trades=all_trades,
            max_drawdown_usdc=max_drawdown_usdc(chained_equity),
            max_underwater_days=max_underwater_calendar_days(chained_equity),
            drawdown_method="mark_to_market",
        )
    )
    first_validation = observations[0].validation_candles
    last_validation = observations[-1].validation_candles
    temporal = build_temporal_evidence(
        all_trades,
        window_start_ms=int(first_validation[0].open_time),
        window_end_ms=int(last_validation[-1].open_time),
    )
    positive_pre_cost = sum(
        max(
            0.0,
            float(trade.net_profit_usdc + trade.fees_usdc + trade.slippage_usdc),
        )
        for trade in all_trades
    )
    friction = sum(float(trade.fees_usdc + trade.slippage_usdc) for trade in all_trades)
    return {
        "rolling": rolling,
        "temporal": temporal,
        "regime": _aggregate_regime_rows(regime_reports, regime_lookback_minutes),
        "friction_share_of_positive_pre_cost_pnl": (
            round(friction / positive_pre_cost, 10) if positive_pre_cost > 0 else 1.0
        ),
        "fold_count": len(observations),
        "uses_audit_or_holdout": False,
    }


def build_walk_forward_stress_evidence(
    baseline_summary: dict[str, Any],
    joint_summary: dict[str, Any],
    slippage_summary: dict[str, Any],
    *,
    baseline_fee_bps: float,
    baseline_slippage_bps: float,
    joint_fee_bps: float,
    joint_slippage_bps: float,
    slippage_fee_bps: float,
    slippage_stress_bps: float,
) -> dict[str, Any]:
    """Convert three same-fold WFV summaries into strict stress evidence."""

    return {
        "baseline": _stress_row(
            baseline_summary,
            fee_bps=baseline_fee_bps,
            slippage_bps=baseline_slippage_bps,
        ),
        "joint": _stress_row(
            joint_summary,
            fee_bps=joint_fee_bps,
            slippage_bps=joint_slippage_bps,
        ),
        "slippage": _stress_row(
            slippage_summary,
            fee_bps=slippage_fee_bps,
            slippage_bps=slippage_stress_bps,
        ),
        "friction_share_of_positive_pre_cost_pnl": float(
            baseline_summary.get("selection_evidence", {}).get(
                "friction_share_of_positive_pre_cost_pnl", 1.0
            )
        ),
        "same_walk_forward_folds": True,
        "uses_audit_or_holdout": False,
    }


def _stress_row(
    summary: dict[str, Any],
    *,
    fee_bps: float,
    slippage_bps: float,
) -> dict[str, Any]:
    metrics = summary.get("aggregate_metrics")
    if not isinstance(metrics, dict):
        metrics = {}
    return {
        "fee_bps_per_side": float(fee_bps),
        "slippage_bps_per_side": float(slippage_bps),
        "net_usdc_per_day": metrics.get("net_usdc_per_day"),
        "net_profit_usdc": metrics.get("net_profit_usdc"),
        "profit_factor": metrics.get("profit_factor"),
        "max_drawdown_usdc": metrics.get("max_drawdown_usdc"),
        "drawdown_method": metrics.get("drawdown_method"),
        "trade_count": metrics.get("trade_count"),
        "fold_count": summary.get("fold_count"),
    }


def _aggregate_regime_rows(
    reports: Sequence[dict[str, Any]],
    lookback_minutes: int,
) -> dict[str, Any]:
    values: dict[str, dict[str, float | int]] = {
        label: {
            "trade_count": 0,
            "net_profit_usdc": 0.0,
            "gross_profit_usdc": 0.0,
            "gross_loss_usdc": 0.0,
        }
        for label in REGIME_LABELS
    }
    thresholds: list[dict[str, Any]] = []
    for fold_index, report in enumerate(reports, start=1):
        thresholds.append(
            {
                "fold_id": fold_index,
                "training_median_volatility_bps": report.get(
                    "training_median_volatility_bps", 0.0
                ),
            }
        )
        for row in report.get("regimes", []):
            label = row.get("regime")
            if label not in values:
                raise ValueError(f"unexpected regime label: {label!r}")
            target = values[label]
            target["trade_count"] = int(target["trade_count"]) + int(
                row.get("trade_count", 0)
            )
            target["net_profit_usdc"] = float(target["net_profit_usdc"]) + float(
                row.get("net_profit_usdc", 0.0)
            )
            target["gross_profit_usdc"] = float(
                target["gross_profit_usdc"]
            ) + float(row.get("gross_profit_usdc", 0.0))
            target["gross_loss_usdc"] = float(target["gross_loss_usdc"]) + float(
                row.get("gross_loss_usdc", 0.0)
            )

    total_positive = sum(float(row["gross_profit_usdc"]) for row in values.values())
    rows: list[dict[str, Any]] = []
    for label in REGIME_LABELS:
        source = values[label]
        gross_profit = float(source["gross_profit_usdc"])
        gross_loss = float(source["gross_loss_usdc"])
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = 1_000_000_000_000.0
        else:
            profit_factor = 0.0
        rows.append(
            {
                "regime": label,
                "trade_count": int(source["trade_count"]),
                "net_profit_usdc": round(float(source["net_profit_usdc"]), 10),
                "gross_profit_usdc": round(gross_profit, 10),
                "gross_loss_usdc": round(gross_loss, 10),
                "profit_factor": round(profit_factor, 10),
                "positive_pnl_share": (
                    round(gross_profit / total_positive, 10)
                    if total_positive > 0
                    else 0.0
                ),
            }
        )
    return {
        "definition": REGIME_DEFINITION,
        "threshold_source": REGIME_THRESHOLD_SOURCE,
        "assignment_uses_entry_time_trailing_data_only": True,
        "lookback_minutes": lookback_minutes,
        "fold_training_thresholds": thresholds,
        "regime_count": len(rows),
        "min_trades_per_regime": min(
            (row["trade_count"] for row in rows), default=0
        ),
        "positive_regime_count": sum(
            1 for row in rows if row["net_profit_usdc"] > 0
        ),
        "regimes_pf_at_least_1_05": sum(
            1 for row in rows if row["profit_factor"] >= 1.05
        ),
        "worst_regime_profit_factor": min(
            (row["profit_factor"] for row in rows), default=0.0
        ),
        "worst_regime_net_usdc": min(
            (row["net_profit_usdc"] for row in rows), default=0.0
        ),
        "max_positive_pnl_share": max(
            (row["positive_pnl_share"] for row in rows), default=0.0
        ),
        "regimes": rows,
    }


__all__ = [
    "FoldSelectionObservation",
    "build_walk_forward_selection_evidence",
    "build_walk_forward_stress_evidence",
]
