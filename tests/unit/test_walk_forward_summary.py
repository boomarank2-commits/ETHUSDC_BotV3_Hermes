"""Regression tests for Walk-Forward fold variation reporting."""

from ethusdc_bot.backtest.walk_forward import summarize_walk_forward


def _fold(net_usdc_per_day: float) -> dict[str, object]:
    return {
        "metrics": {
            "net_usdc_per_day": net_usdc_per_day,
            "profit_factor": 1.0,
            "max_drawdown_usdc": 0.0,
            "trade_count": 0,
            "fees_usdc": 0.0,
            "slippage_usdc": 0.0,
        }
    }


def test_identical_zero_folds_have_zero_coefficient_of_variation() -> None:
    summary = summarize_walk_forward([_fold(0.0), _fold(0.0)])

    assert summary["fold_net_coefficient_of_variation"] == 0.0


def test_nonidentical_zero_mean_folds_keep_variation_undefined() -> None:
    summary = summarize_walk_forward([_fold(-1.0), _fold(1.0)])

    assert summary["fold_net_coefficient_of_variation"] is None
