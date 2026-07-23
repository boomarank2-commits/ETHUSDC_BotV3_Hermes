"""Complete deterministic Quality-Gate evidence used only by unit fixtures."""

from __future__ import annotations

from ethusdc_bot.backtest.quality_gates import QUALITY_GATE_V1


def complete_quality_evidence(
    fold_nets: list[float] | None = None,
    *,
    joint_net: float = 0.2,
) -> dict:
    values = fold_nets or [0.25] * 6
    folds = []
    total_gross_profit = 0.0
    total_gross_loss = 0.0
    for value in values:
        net_profit = value * 60
        gross_loss = 10.0
        gross_profit = gross_loss + net_profit
        total_gross_profit += gross_profit
        total_gross_loss += gross_loss
        folds.append(
            {
                "days": 60,
                "metrics": {
                    "trade_count": 30,
                    "net_profit_usdc": net_profit,
                    "net_usdc_per_day": value,
                    "profit_factor": gross_profit / gross_loss,
                    "gross_profit_usdc": gross_profit,
                    "gross_loss_usdc": gross_loss,
                    "max_drawdown_usdc": 0.0,
                    "drawdown_method": "mark_to_market",
                },
                "equity_curve_usdc": [0.0, net_profit],
            }
        )
    mean = sum(values) / 6
    variance = sum((value - mean) ** 2 for value in values) / 6
    ordered = sorted(values)
    median = (ordered[2] + ordered[3]) / 2
    return {
        "protocol": {
            "gate_version": QUALITY_GATE_V1.version,
            "gate_frozen_before_evaluation": True,
            "selection_uses_audit": False,
        },
        "validation": {
            "trade_count": 60,
            "net_usdc_per_day": max(0.2, mean),
            "profit_factor": 1.5,
            "drawdown_method": "mark_to_market",
            "max_drawdown_usdc": 5.0,
        },
        "wfv": {
            "fold_count": 6,
            "folds": folds,
            "aggregate": {
                "trade_count": 180,
                "net_profit_usdc": sum(value * 60 for value in values),
                "net_usdc_per_day": mean,
                "profit_factor": total_gross_profit / total_gross_loss,
                "drawdown_method": "mark_to_market",
                "max_drawdown_usdc": 0.0,
                "positive_fold_count": sum(value > 0 for value in values),
                "folds_pf_at_least_1_05": 6,
                "worst_fold_profit_factor": min(
                    row["metrics"]["profit_factor"] for row in folds
                ),
                "median_fold_net_usdc_per_day": median,
                "worst_fold_net_usdc_per_day": min(values),
                "fold_net_coefficient_of_variation": (
                    variance**0.5 / abs(mean)
                ),
                "full_training_net_usdc_per_day": mean / 0.8,
            },
        },
        "rolling": {
            "drawdown_method": "mark_to_market",
            "max_drawdown_usdc": 5.0,
            "max_underwater_days": 10,
            "top1_positive_pnl_share": 0.05,
            "top5_positive_pnl_share": 0.20,
            "net_without_top5_usdc": 10.0,
            "profit_factor_without_top5": 1.2,
        },
        "stress": {
            "baseline": {
                "fee_bps_per_side": 10.0,
                "slippage_bps_per_side": 5.0,
                "net_usdc_per_day": mean,
            },
            "joint": {
                "fee_bps_per_side": 15.0,
                "slippage_bps_per_side": 10.0,
                "net_usdc_per_day": joint_net,
                "profit_factor": 1.2,
                "drawdown_method": "mark_to_market",
                "max_drawdown_usdc": 6.0,
            },
            "slippage": {
                "fee_bps_per_side": 10.0,
                "slippage_bps_per_side": 15.0,
                "net_usdc_per_day": max(0.1, joint_net),
                "profit_factor": 1.1,
            },
            "friction_share_of_positive_pre_cost_pnl": 0.2,
        },
        "parameter_stability": {
            "all_numeric_parameters_perturbed": True,
            "numeric_parameter_count": 1,
            "neighbor_count": 2,
            "perturbation_fraction": 0.10,
            "session_hour_step": 1,
            "passing_neighbor_fraction": 1.0,
            "median_net_retention": 0.9,
            "worst_neighbor_net_usdc_per_day": 0.0,
        },
        "temporal": {
            "months_observed": 12,
            "positive_months": 10,
            "active_months": 12,
            "max_no_trade_gap_days": 10,
            "quarters_observed": 4,
            "positive_quarters": 4,
            "min_quarter_trade_count": 20,
            "worst_month_net_usdc": 0.0,
        },
        "regime": {
            "definition": QUALITY_GATE_V1.regime_definition,
            "threshold_source": QUALITY_GATE_V1.regime_threshold_source,
            "assignment_uses_entry_time_trailing_data_only": True,
            "regime_count": 4,
            "min_trades_per_regime": 20,
            "positive_regime_count": 4,
            "regimes_pf_at_least_1_05": 4,
            "worst_regime_profit_factor": 1.0,
            "worst_regime_net_usdc": 0.0,
            "max_positive_pnl_share": 0.4,
        },
    }


__all__ = ["complete_quality_evidence"]
