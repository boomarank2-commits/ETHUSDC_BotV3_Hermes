from dataclasses import dataclass

from ethusdc_bot.backtest.metrics import BacktestMetrics, compute_metrics
from ethusdc_bot.backtest.research_runner import rank_candidates
from ethusdc_bot.backtest.simulator import StrategyCandidate


@dataclass(frozen=True)
class _Trade:
    net_profit_usdc: float
    fees_usdc: float = 0.0
    slippage_usdc: float = 0.0


def _metrics(
    *,
    net_per_day: float,
    trades: int,
    profit_factor: float,
    drawdown: float,
    fees: float = 0.0,
    slippage: float = 0.0,
) -> BacktestMetrics:
    return BacktestMetrics(
        net_profit_usdc=net_per_day * 100,
        net_usdc_per_day=net_per_day,
        trade_count=trades,
        winrate=0.5,
        max_drawdown_usdc=drawdown,
        profit_factor=profit_factor,
        average_trade_usdc=(net_per_day * 100 / trades) if trades else 0.0,
        fees_usdc=fees,
        slippage_usdc=slippage,
        training_days=584,
        blindtest_days=365,
    )


def test_lossless_profit_factor_is_finite_and_sample_aware():
    one_winner = compute_metrics([_Trade(1.0)], days=1)
    three_winners = compute_metrics(
        [_Trade(0.5), _Trade(1.0), _Trade(1.5)],
        days=1,
    )

    assert one_winner.profit_factor == 1.0
    assert three_winners.profit_factor == 3.0


def test_low_sample_high_pf_does_not_outrank_adequate_validation_evidence():
    candidate = StrategyCandidate("breakout_volatility_filter", {"symbol": "ETHUSDC"})
    low_sample = {
        "candidate_id": "low_sample",
        "candidate": candidate,
        "training_metrics": _metrics(
            net_per_day=0.02,
            trades=2,
            profit_factor=2.0,
            drawdown=1.0,
        ),
        "validation_metrics": _metrics(
            net_per_day=0.02,
            trades=2,
            profit_factor=2.0,
            drawdown=1.0,
        ),
    }
    adequate_sample = {
        "candidate_id": "adequate_sample",
        "candidate": candidate,
        "training_metrics": _metrics(
            net_per_day=0.01,
            trades=50,
            profit_factor=1.2,
            drawdown=5.0,
            fees=1.0,
            slippage=0.5,
        ),
        "validation_metrics": _metrics(
            net_per_day=0.01,
            trades=50,
            profit_factor=1.2,
            drawdown=5.0,
            fees=1.0,
            slippage=0.5,
        ),
    }

    ranked = rank_candidates([low_sample, adequate_sample])

    assert ranked[0]["candidate_id"] == "adequate_sample"
