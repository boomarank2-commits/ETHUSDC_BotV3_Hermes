"""Hand-calculated tests for QualityGateV1 rolling and temporal evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

import pytest

from ethusdc_bot.backtest.equity import EquityPoint
from ethusdc_bot.backtest.portfolio_simulator import PortfolioTrade
from ethusdc_bot.backtest.quality_evidence import (
    FAIL_CLOSED_RATIO_SENTINEL,
    build_rolling_evidence,
    build_temporal_evidence,
)


def _ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _serialized_trade(
    exit_at: datetime,
    pnl: float,
    lot_id: str,
    **extra: object,
) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": "ETHUSDC",
        "side": "LONG",
        "entry_time": _ms(exit_at - timedelta(minutes=1)),
        "exit_time": _ms(exit_at),
        "net_profit_usdc": pnl,
        "lot_id": lot_id,
    }
    row.update(extra)
    return row


def _portfolio_trade(exit_at: datetime, pnl: float, lot_id: str) -> PortfolioTrade:
    return PortfolioTrade(
        symbol="ETHUSDC",
        side="LONG",
        entry_time=_ms(exit_at - timedelta(minutes=1)),
        exit_time=_ms(exit_at),
        entry_price=100.0,
        exit_price=100.0,
        quantity=1.0,
        gross_profit_usdc=pnl,
        fees_usdc=0.0,
        slippage_usdc=0.0,
        net_profit_usdc=pnl,
        exit_reason="test",
        lot_id=lot_id,
        entry_notional_usdc=100.0,
    )


def test_rolling_evidence_recomputes_hand_calculated_mtm_and_top5_metrics():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 5, tzinfo=UTC)
    pnls = [10.0, 8.0, 6.0, 4.0, 2.0, 1.0, -5.0, -5.0]
    trades: list[PortfolioTrade | dict[str, object]] = [
        _portfolio_trade(start + timedelta(hours=1), pnls[0], "lot-1")
    ]
    trades.extend(
        _serialized_trade(
            start + timedelta(hours=index + 1),
            pnl,
            f"lot-{index + 1}",
            # Untrusted precomputed values must not influence the reducer.
            max_drawdown_usdc=-999.0,
            profit_factor=999.0,
        )
        for index, pnl in enumerate(pnls[1:], start=1)
    )
    curve = [
        EquityPoint(_ms(start), 0.0),
        EquityPoint(_ms(start + timedelta(days=1)), 12.0),
        EquityPoint(_ms(start + timedelta(days=2)), 6.0),
        EquityPoint(_ms(start + timedelta(days=3)), 10.0),
        EquityPoint(_ms(end) - 1, 21.0),
    ]

    evidence = build_rolling_evidence(_ms(start), _ms(end), trades, curve)

    assert evidence["drawdown_method"] == "mark_to_market"
    assert evidence["max_drawdown_usdc"] == 6.0
    assert evidence["max_underwater_days"] == 2
    assert evidence["top1_positive_pnl_share"] == pytest.approx(10 / 31)
    assert evidence["top5_positive_pnl_share"] == pytest.approx(30 / 31)
    assert evidence["net_without_top5_usdc"] == -9.0
    assert evidence["profit_factor_without_top5"] == 0.1
    assert evidence["proof"]["top5_removed_trade_indices"] == [0, 1, 2, 3, 4]
    assert evidence["proof"]["remaining_gross_profit_usdc"] == 1.0
    assert evidence["proof"]["remaining_gross_loss_usdc"] == 10.0
    json.dumps(evidence, allow_nan=False)


def test_rolling_evidence_is_order_independent_after_canonical_trade_sort():
    start = datetime(2026, 2, 1, tzinfo=UTC)
    end = datetime(2026, 2, 2, tzinfo=UTC)
    trades = [
        _serialized_trade(start + timedelta(hours=1), 2.0, "lot-a"),
        _serialized_trade(start + timedelta(hours=2), -1.0, "lot-b"),
        _serialized_trade(start + timedelta(hours=3), 1.0, "lot-c"),
        _serialized_trade(start + timedelta(hours=4), -1.0, "lot-d"),
        _serialized_trade(start + timedelta(hours=5), 1.0, "lot-e"),
        _serialized_trade(start + timedelta(hours=6), -1.0, "lot-f"),
    ]
    curve = [
        {"timestamp_ms": _ms(start), "equity_usdc": 0.0},
        {"timestamp_ms": _ms(start + timedelta(hours=4)), "equity_usdc": -3.0},
        {"timestamp_ms": _ms(end) - 1, "equity_usdc": 1.0},
    ]

    forward = build_rolling_evidence(_ms(start), _ms(end), trades, curve)
    backward = build_rolling_evidence(_ms(start), _ms(end), list(reversed(trades)), curve)

    assert backward == forward


def test_temporal_evidence_includes_empty_periods_and_both_window_edge_gaps():
    start = datetime(2025, 12, 15, tzinfo=UTC)
    end = datetime(2026, 4, 1, tzinfo=UTC)
    trades = [
        _serialized_trade(datetime(2025, 12, 31, 12, tzinfo=UTC), 2.0, "dec"),
        _serialized_trade(datetime(2026, 1, 15, 12, tzinfo=UTC), -3.0, "jan"),
        _serialized_trade(datetime(2026, 3, 1, 12, tzinfo=UTC), 5.0, "mar"),
    ]

    evidence = build_temporal_evidence(_ms(start), _ms(end), trades)

    assert evidence["months_observed"] == 4
    assert evidence["positive_months"] == 2
    assert evidence["active_months"] == 3
    assert evidence["quarters_observed"] == 2
    assert evidence["positive_quarters"] == 2
    assert evidence["min_quarter_trade_count"] == 1
    assert evidence["worst_month_net_usdc"] == -3.0
    assert evidence["max_no_trade_gap_days"] == 44

    month_rows = evidence["proof"]["month_rows"]
    assert [row["period"] for row in month_rows] == [
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
    ]
    assert month_rows[2] == {
        "period": "2026-02",
        "observed_start_ms": _ms(datetime(2026, 2, 1, tzinfo=UTC)),
        "observed_end_ms_exclusive": _ms(datetime(2026, 3, 1, tzinfo=UTC)),
        "trade_count": 0,
        "net_profit_usdc": 0.0,
        "active": False,
        "positive": False,
    }
    gap_rows = evidence["proof"]["no_trade_gap_rows"]
    assert gap_rows[0]["touches_window_start"] is True
    assert gap_rows[-1]["touches_window_end"] is True
    assert any(row["days"] == 44 for row in gap_rows)


def test_zero_trade_window_uses_finite_fail_closed_ratios_and_full_edge_gap():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 2, 1, tzinfo=UTC)
    curve = [EquityPoint(_ms(start), 0.0), EquityPoint(_ms(end) - 1, 0.0)]

    rolling = build_rolling_evidence(_ms(start), _ms(end), [], curve)
    temporal = build_temporal_evidence(_ms(start), _ms(end), [])

    assert rolling["top1_positive_pnl_share"] == FAIL_CLOSED_RATIO_SENTINEL
    assert rolling["top5_positive_pnl_share"] == FAIL_CLOSED_RATIO_SENTINEL
    assert rolling["profit_factor_without_top5"] == FAIL_CLOSED_RATIO_SENTINEL
    assert set(
        rolling["proof"]["zero_denominator_policy"]["applied_fields"]
    ) == {
        "profit_factor_without_top5",
        "top1_positive_pnl_share",
        "top5_positive_pnl_share",
    }
    assert temporal["months_observed"] == 1
    assert temporal["quarters_observed"] == 1
    assert temporal["active_months"] == 0
    assert temporal["positive_months"] == 0
    assert temporal["positive_quarters"] == 0
    assert temporal["min_quarter_trade_count"] == 0
    assert temporal["worst_month_net_usdc"] == 0.0
    assert temporal["max_no_trade_gap_days"] == 31
    assert temporal["proof"]["no_trade_gap_rows"] == [
        {
            "start_utc_date": "2026-01-01",
            "end_utc_date": "2026-01-31",
            "days": 31,
            "touches_window_start": True,
            "touches_window_end": True,
        }
    ]
    json.dumps({"rolling": rolling, "temporal": temporal}, allow_nan=False)


@pytest.mark.parametrize(
    "bad_trade",
    [
        {
            "symbol": "ETHUSDC",
            "side": "LONG",
            "entry_time": _ms(datetime(2025, 12, 31, 23, 59, tzinfo=UTC)),
            "exit_time": _ms(datetime(2026, 1, 1, tzinfo=UTC)),
            "net_profit_usdc": 1.0,
        },
        {
            "symbol": "ETHUSDC",
            "side": "LONG",
            "entry_time": _ms(datetime(2026, 1, 1, tzinfo=UTC)),
            "exit_time": _ms(datetime(2026, 1, 2, tzinfo=UTC)),
            "net_profit_usdc": 1.0,
        },
        {
            "symbol": "ETHUSDC",
            "side": "LONG",
            "entry_time": _ms(datetime(2026, 1, 1, tzinfo=UTC)),
            "exit_time": _ms(datetime(2026, 1, 1, 1, tzinfo=UTC)),
            "net_profit_usdc": float("nan"),
        },
    ],
)
def test_trade_rows_outside_window_or_non_finite_are_rejected(bad_trade):
    start = _ms(datetime(2026, 1, 1, tzinfo=UTC))
    end = _ms(datetime(2026, 1, 2, tzinfo=UTC))

    with pytest.raises((TypeError, ValueError)):
        build_temporal_evidence(start, end, [bad_trade])


def test_truncated_reordered_or_net_mismatched_mtm_proof_is_rejected():
    start_dt = datetime(2026, 1, 1, tzinfo=UTC)
    end_dt = datetime(2026, 1, 2, tzinfo=UTC)
    start = _ms(start_dt)
    end = _ms(end_dt)
    trade = _serialized_trade(start_dt + timedelta(hours=1), 1.0, "lot-1")

    with pytest.raises(ValueError, match="must end"):
        build_rolling_evidence(
            start,
            end,
            [trade],
            [EquityPoint(start, 0.0), EquityPoint(end - 2, 1.0)],
        )
    with pytest.raises(ValueError, match="strictly chronological"):
        build_rolling_evidence(
            start,
            end,
            [trade],
            [
                EquityPoint(start, 0.0),
                EquityPoint(end - 1, 1.0),
                EquityPoint(start + 1, 1.0),
            ],
        )
    with pytest.raises(ValueError, match="must equal"):
        build_rolling_evidence(
            start,
            end,
            [trade],
            [EquityPoint(start, 0.0), EquityPoint(end - 1, 99.0)],
        )


def test_window_boundaries_must_be_utc_midnight():
    start = _ms(datetime(2026, 1, 1, 0, 1, tzinfo=UTC))
    end = _ms(datetime(2026, 1, 2, tzinfo=UTC))

    with pytest.raises(ValueError, match="UTC midnight"):
        build_temporal_evidence(start, end, [])
