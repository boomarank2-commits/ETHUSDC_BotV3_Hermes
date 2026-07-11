"""Tests for selection-only quality-gate evidence producers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.selection_evidence import (
    REGIME_DEFINITION,
    build_regime_evidence,
    build_rolling_evidence,
    build_temporal_evidence,
    generate_parameter_neighbors,
    run_cost_stress,
    run_parameter_stability,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate, Trade


def _timestamp(year: int, month: int, day: int, hour: int = 0) -> int:
    return int(datetime(year, month, day, hour, tzinfo=UTC).timestamp() * 1000)


def _trade(net: float, entry_time: int, *, fees: float = 0.2, slippage: float = 0.1) -> Trade:
    return Trade(
        symbol="ETHUSDC",
        side="LONG",
        entry_time=entry_time,
        exit_time=entry_time + 60_000,
        entry_price=100.0,
        exit_price=100.0 + net,
        quantity=1.0,
        gross_profit_usdc=net + fees,
        fees_usdc=fees,
        slippage_usdc=slippage,
        net_profit_usdc=net,
        exit_reason="test",
    )


def _candles(closes: list[float], *, start: datetime | None = None) -> list[Candle]:
    origin = start or datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(
            open_time=int((origin + timedelta(minutes=index)).timestamp() * 1000),
            open=close,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=1.0,
        )
        for index, close in enumerate(closes)
    ]


def test_rolling_evidence_removes_exact_best_five_positive_trades() -> None:
    trades = [
        _trade(value, _timestamp(2026, 1, index + 1))
        for index, value in enumerate([10.0, 8.0, 6.0, 4.0, 2.0, 1.0, -5.0, -1.0])
    ]
    result = SimpleNamespace(
        trades=trades,
        max_drawdown_usdc=7.5,
        max_underwater_days=12,
        drawdown_method="mark_to_market",
    )

    evidence = build_rolling_evidence(result)

    assert evidence["top1_positive_pnl_share"] == 10.0 / 31.0
    assert evidence["top5_positive_pnl_share"] == 30.0 / 31.0
    assert evidence["net_without_top5_usdc"] == -5.0
    assert evidence["profit_factor_without_top5"] == 1.0 / 6.0
    assert evidence["max_drawdown_usdc"] == 7.5
    assert evidence["max_underwater_days"] == 12
    assert evidence["drawdown_method"] == "mark_to_market"


def test_temporal_evidence_keeps_inactive_months_and_boundary_gaps() -> None:
    start = _timestamp(2025, 1, 1)
    end = _timestamp(2025, 3, 31, 23)
    trades = [
        _trade(2.0, _timestamp(2025, 1, 10)),
        _trade(-1.0, _timestamp(2025, 3, 20)),
    ]

    evidence = build_temporal_evidence(trades, window_start_ms=start, window_end_ms=end)

    assert evidence["months_observed"] == 3
    assert evidence["active_months"] == 2
    assert evidence["positive_months"] == 1
    assert evidence["quarters_observed"] == 1
    assert evidence["positive_quarters"] == 1
    assert evidence["min_quarter_trade_count"] == 2
    assert evidence["worst_month_net_usdc"] == -1.0
    assert evidence["max_no_trade_gap_days"] == 68
    assert [row["trade_count"] for row in evidence["months"]] == [1, 0, 1]


def test_temporal_evidence_counts_entire_window_when_no_trades() -> None:
    evidence = build_temporal_evidence(
        [],
        window_start_ms=_timestamp(2025, 1, 1),
        window_end_ms=_timestamp(2025, 1, 31, 23),
    )

    assert evidence["months_observed"] == 1
    assert evidence["active_months"] == 0
    assert evidence["max_no_trade_gap_days"] == 31
    assert evidence["min_quarter_trade_count"] == 0


def test_regime_evidence_is_training_thresholded_and_deterministic() -> None:
    training = _candles(
        [100 + index * 0.05 + (0.6 if index % 7 == 0 else 0.0) for index in range(180)]
    )
    evaluation = _candles(
        [100 + (index * 0.08 if index < 90 else (180 - index) * 0.12) + (1.2 if index % 11 == 0 else 0.0) for index in range(180)],
        start=datetime(2026, 2, 1, tzinfo=UTC),
    )
    trade_indices = [30, 70, 110, 160]
    trades = [
        _trade(value, evaluation[index].open_time)
        for index, value in zip(trade_indices, [2.0, -1.0, 3.0, 1.0])
    ]

    first = build_regime_evidence(training, evaluation, trades, lookback_minutes=20)
    second = build_regime_evidence(training, evaluation, trades, lookback_minutes=20)

    assert first == second
    assert first["definition"] == REGIME_DEFINITION
    assert first["threshold_source"] == "training_only"
    assert first["assignment_uses_entry_time_trailing_data_only"] is True
    assert first["regime_count"] == 4
    assert sum(row["trade_count"] for row in first["regimes"]) == 4
    assert first["training_median_volatility_bps"] >= 0


def test_fixed_cost_stress_profiles_are_explicit_and_order_free() -> None:
    candles = _candles([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    candidate = StrategyCandidate("always_long", {"max_hold_minutes": 1})

    evidence = run_cost_stress(candles, candidate, days=1)

    assert evidence["baseline"]["fee_bps_per_side"] == 10.0
    assert evidence["baseline"]["slippage_bps_per_side"] == 5.0
    assert evidence["joint"]["fee_bps_per_side"] == 15.0
    assert evidence["joint"]["slippage_bps_per_side"] == 10.0
    assert evidence["slippage"]["fee_bps_per_side"] == 10.0
    assert evidence["slippage"]["slippage_bps_per_side"] == 15.0
    assert evidence["joint"]["net_profit_usdc"] <= evidence["baseline"]["net_profit_usdc"]
    assert 0 <= evidence["friction_share_of_positive_pre_cost_pnl"]
    assert evidence["uses_audit_or_holdout"] is False


def test_parameter_neighbors_exclude_structural_fields_and_cover_both_sides() -> None:
    candidate = StrategyCandidate(
        "session_filter",
        {
            "symbol": "ETHUSDC",
            "side": "LONG",
            "base_family": "momentum",
            "lookback": 10,
            "threshold_bps": 20,
            "session_start_hour": 12,
            "session_end_hour": 21,
        },
    )

    neighbors, numeric_count = generate_parameter_neighbors(candidate)

    assert numeric_count == 4
    assert len(neighbors) == 8
    changed = {(parameter, direction, value) for parameter, direction, value, _ in neighbors}
    assert ("lookback", "minus", 9) in changed
    assert ("lookback", "plus", 11) in changed
    assert ("session_start_hour", "minus", 11) in changed
    assert ("session_start_hour", "plus", 13) in changed
    assert all(row[3].params["symbol"] == "ETHUSDC" for row in neighbors)
    assert all(row[3].params["base_family"] == "momentum" for row in neighbors)


def test_parameter_stability_reports_complete_deterministic_neighbors() -> None:
    candles = _candles([100 + index * 0.2 for index in range(80)])
    candidate = StrategyCandidate(
        "momentum",
        {
            "lookback": 5,
            "threshold_bps": 1,
            "take_profit_bps": 10_000,
            "stop_loss_bps": 10_000,
            "max_hold_minutes": 2,
        },
    )

    first = run_parameter_stability(candles, candidate, days=1)
    second = run_parameter_stability(candles, candidate, days=1)

    assert first == second
    assert first["numeric_parameter_count"] == 5
    assert first["neighbor_count"] == 10
    assert first["all_numeric_parameters_perturbed"] is True
    assert 0 <= first["passing_neighbor_fraction"] <= 1
    assert len(first["neighbors"]) == 10
    assert first["uses_audit_or_holdout"] is False
