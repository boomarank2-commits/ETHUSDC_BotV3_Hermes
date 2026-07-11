"""Tests for train/blind split boundaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.split import build_research_window_plan, split_train_blind


def _daily_candles(
    days: int, *, start: datetime = datetime(2023, 1, 1, tzinfo=UTC)
) -> list[Candle]:
    return [
        Candle(open_time=int((start + timedelta(days=day)).timestamp() * 1000), open=100, high=101, low=99, close=100, volume=1)
        for day in range(days)
    ]


def _intraday_candles(day_counts: list[int]) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Candle(
            open_time=int((start + timedelta(days=day, minutes=minute)).timestamp() * 1000),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        )
        for day, count in enumerate(day_counts)
        for minute in range(count)
    ]


def _minute_day(day: datetime, *, displaced_minute: int | None = None) -> list[Candle]:
    return [
        Candle(
            open_time=int(
                (
                    day
                    + timedelta(
                        minutes=minute,
                        seconds=30 if minute == displaced_minute else 0,
                    )
                ).timestamp()
                * 1000
            ),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=1,
        )
        for minute in range(1440)
    ]


def test_split_uses_730_training_and_365_blindtest_days():
    result = split_train_blind(_daily_candles(1095))

    assert result.training_days == 730
    assert result.blindtest_days == 365
    assert len(result.training) == 730
    assert len(result.blindtest) == 365


def test_split_has_no_overlap():
    result = split_train_blind(_daily_candles(1095))

    training_times = {c.open_time for c in result.training}
    blind_times = {c.open_time for c in result.blindtest}
    assert training_times.isdisjoint(blind_times)
    assert max(training_times) < min(blind_times)


def test_blindtest_data_is_not_in_training():
    result = split_train_blind(_daily_candles(1095))

    assert result.training_end < result.blind_start
    assert result.data_start == result.training_start
    assert result.data_end == result.blind_end


def test_research_window_plan_uses_latest_730_plus_365_days():
    candles = _daily_candles(1100)

    plan = build_research_window_plan(candles)

    assert plan.available_complete_days == 1100
    assert plan.latest_complete_day == "2026-01-04"
    assert plan.final_window.data_start == "2023-01-06"
    assert plan.final_window.data_end == "2026-01-04"
    assert plan.final_window.training_days == 730
    assert plan.final_window.blindtest_days == 365
    assert len(plan.final_window.training) == 730
    assert len(plan.final_window.blindtest) == 365


def test_research_window_plan_honestly_has_zero_origins_below_1460_days():
    plan = build_research_window_plan(_daily_candles(1459))

    assert plan.historical_origin_count == 0
    assert plan.historical_origins == ()


def test_research_window_plan_first_historical_origin_requires_1460_days():
    plan = build_research_window_plan(_daily_candles(1460))

    assert plan.historical_origin_count == 1
    origin = plan.historical_origins[0]
    assert origin.data_start == "2023-01-01"
    assert origin.blind_end == plan.final_window.training_end
    assert origin.blind_end < plan.final_window.blind_start


def test_research_window_plan_orders_multiple_origins_chronologically():
    plan = build_research_window_plan(_daily_candles(1825), rolling_step_days=365)

    assert plan.historical_origin_count == 2
    assert [origin.data_start for origin in plan.historical_origins] == ["2023-01-01", "2024-01-01"]
    assert all(origin.blind_end < plan.final_window.blind_start for origin in plan.historical_origins)


def test_research_window_plan_can_disable_historical_origins_with_zero_cap():
    plan = build_research_window_plan(_daily_candles(1825), max_historical_origins=0)

    assert plan.historical_origin_count == 0
    assert plan.historical_origins == ()


def test_research_window_plan_can_pin_the_latest_complete_utc_day():
    candles = _daily_candles(1101)

    plan = build_research_window_plan(candles, latest_complete_day="2026-01-04")

    assert plan.latest_complete_day == "2026-01-04"
    assert plan.final_window.data_end == "2026-01-04"
    assert max(candle.open_time for candle in plan.final_window.blindtest) < candles[-1].open_time


def test_research_window_plan_rejects_non_contiguous_complete_days():
    candles = _daily_candles(1096)
    del candles[500]

    with pytest.raises(ValueError, match="continuous"):
        build_research_window_plan(candles)


def test_research_window_plan_excludes_partial_latest_utc_day():
    candles = _intraday_candles([2, 2, 1])

    plan = build_research_window_plan(
        candles,
        training_days=1,
        blindtest_days=1,
        expected_candles_per_day=2,
    )

    assert plan.latest_complete_day == "2024-01-02"
    assert plan.available_complete_days == 2
    assert plan.final_window.data_start == "2024-01-01"
    assert plan.final_window.data_end == "2024-01-02"
    assert len(plan.final_window.training) == 2
    assert len(plan.final_window.blindtest) == 2


def test_research_window_plan_rejects_pinned_partial_utc_day():
    candles = _intraday_candles([2, 2, 1])

    with pytest.raises(ValueError, match="Pinned latest UTC day is incomplete"):
        build_research_window_plan(
            candles,
            training_days=1,
            blindtest_days=1,
            latest_complete_day="2024-01-03",
            expected_candles_per_day=2,
        )


def test_research_window_plan_rejects_1440_rows_with_gap_compensated_timestamp():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    candles = [
        *_minute_day(start),
        *_minute_day(start + timedelta(days=1)),
        *_minute_day(start + timedelta(days=2), displaced_minute=500),
    ]

    with pytest.raises(ValueError, match="Pinned latest UTC day is incomplete"):
        build_research_window_plan(
            candles,
            training_days=1,
            blindtest_days=1,
            latest_complete_day="2024-01-03",
            expected_candles_per_day=1440,
        )


def test_research_window_plan_allows_consumed_final_holdout_at_1095_day_boundary():
    candles = _daily_candles(1095, start=datetime(2023, 7, 9, tzinfo=UTC))
    consumed_holdout = (
        {"start": "2025-07-08", "end": "2026-07-07", "reason": "viewed"},
    )

    plan = build_research_window_plan(
        candles,
        expected_candles_per_day=1,
        excluded_selection_windows=consumed_holdout,
    )

    assert plan.final_window.training_end == "2025-07-07"
    assert plan.final_window.blind_start == "2025-07-08"
    assert plan.final_window.blind_end == "2026-07-07"


def test_research_window_plan_rejects_consumed_training_overlap_at_1096_days():
    candles = _daily_candles(1096, start=datetime(2023, 7, 9, tzinfo=UTC))
    consumed_holdout = (
        {"start": "2025-07-08", "end": "2026-07-07", "reason": "viewed"},
    )

    with pytest.raises(ValueError, match="Selection-bearing final training.*overlaps"):
        build_research_window_plan(
            candles,
            expected_candles_per_day=1,
            excluded_selection_windows=consumed_holdout,
        )


def test_research_window_plan_skips_contaminated_optional_origins_and_keeps_2030_window_dynamic():
    start = datetime(2023, 1, 1, tzinfo=UTC)
    days = (datetime(2031, 1, 1, tzinfo=UTC) - start).days
    consumed = (
        {"start": "2025-07-08", "end": "2026-07-07", "reason": "viewed"},
    )

    plan = build_research_window_plan(
        _daily_candles(days, start=start),
        expected_candles_per_day=1,
        excluded_selection_windows=consumed,
        max_historical_origins=3,
    )

    assert plan.latest_complete_day == "2030-12-31"
    assert plan.final_window.data_end == "2030-12-31"
    assert plan.skipped_historical_origin_count > 0
    assert plan.historical_origin_count > 0
    for origin in plan.historical_origins:
        assert origin.training_end < "2025-07-08" or origin.training_start > "2026-07-07"
        assert origin.blind_end < "2025-07-08" or origin.blind_start > "2026-07-07"


def test_research_window_plan_reports_and_skips_excluded_optional_historical_origin_data():
    candles = _daily_candles(8)

    plan = build_research_window_plan(
        candles,
        training_days=4,
        blindtest_days=2,
        rolling_step_days=2,
        expected_candles_per_day=1,
        excluded_selection_windows=(("2023-01-01", "2023-01-02"),),
    )

    assert plan.historical_origin_count == 0
    assert plan.skipped_historical_origin_count == 1
    assert "historical origin training" in plan.skipped_historical_origins[0]["reason"]
    assert "overlaps" in plan.skipped_historical_origins[0]["reason"]
