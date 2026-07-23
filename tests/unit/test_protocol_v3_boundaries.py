"""Protocol v3 task-2 tests for monthly calendar and boundary invariants."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from ethusdc_bot.protocol_v3.boundaries import (
    BoundaryValidationError,
    build_monthly_process_boundary_plan,
    monthly_anchor,
    resolve_process_end_exclusive,
    resolve_target_anchor_for_button,
    validate_monthly_process_boundary_plan,
)


@pytest.mark.parametrize(
    ("process_end", "expected_start"),
    [
        (date(2024, 3, 8), date(2023, 3, 9)),
        (date(2025, 3, 8), date(2024, 3, 8)),
        (date(2026, 7, 8), date(2025, 7, 8)),
    ],
)
def test_boundary_fixtures_cover_exactly_twelve_origins_and_365_days(
    process_end: date,
    expected_start: date,
) -> None:
    plan = build_monthly_process_boundary_plan(process_end)

    assert plan.process_start_inclusive == expected_start
    assert plan.process_end_exclusive == process_end
    assert len(plan.boundary_dates) == 13
    assert len(plan.origins) == 12
    assert len(plan.iter_process_oos_days()) == 365
    assert plan.iter_process_oos_days()[0] == expected_start
    assert plan.iter_process_oos_days()[-1] == process_end - timedelta(days=1)


def test_leap_window_uses_synthetic_b0_then_real_monthly_anchors() -> None:
    plan = build_monthly_process_boundary_plan("2024-03-08")

    assert plan.boundary_dates[0] == date(2023, 3, 9)
    assert plan.origins[0].target_anchor_is_synthetic is True
    assert plan.origins[0].target_anchor == date(2023, 3, 9)
    assert plan.boundary_dates[1] == date(2023, 4, 8)
    assert all(not origin.target_anchor_is_synthetic for origin in plan.origins[1:])
    assert all(boundary.day == 8 for boundary in plan.boundary_dates[1:])


def test_non_leap_start_is_still_the_conceptual_synthetic_b0() -> None:
    plan = build_monthly_process_boundary_plan("2026-07-08")

    assert plan.process_start_inclusive == date(2025, 7, 8)
    assert plan.origins[0].target_anchor_is_synthetic is True
    assert plan.origins[1].target_anchor_is_synthetic is False


def test_each_origin_has_730_training_days_and_no_oos_overlap() -> None:
    plan = build_monthly_process_boundary_plan("2026-07-08")
    all_oos_days: list[date] = []

    for origin in plan.origins:
        training_days = {
            origin.training_start_inclusive + timedelta(days=offset)
            for offset in range(origin.training_day_count)
        }
        test_days = set(origin.iter_test_days())
        assert origin.training_day_count == 730
        assert origin.training_end_exclusive == origin.test_start_inclusive
        assert training_days.isdisjoint(test_days)
        all_oos_days.extend(origin.iter_test_days())

    assert len(all_oos_days) == 365
    assert len(set(all_oos_days)) == 365
    assert all_oos_days == sorted(all_oos_days)


def test_origin_dates_and_activation_fields_follow_contract() -> None:
    first = build_monthly_process_boundary_plan("2026-07-08").origins[0]

    assert first.origin_index == 1
    assert first.test_start_inclusive == date(2025, 7, 8)
    assert first.test_end_exclusive == date(2025, 8, 8)
    assert first.training_start_inclusive == date(2023, 7, 9)
    assert first.training_end_exclusive == date(2025, 7, 8)
    assert first.as_of_day == date(2025, 7, 7)
    assert first.valid_from == datetime(2025, 7, 9, tzinfo=UTC)
    assert first.manual_decision_deadline == first.valid_from
    assert first.entry_enabled_at == first.valid_from
    assert first.valid_until == datetime(2025, 8, 8, tzinfo=UTC)


def test_entry_enabled_at_waits_for_delay_and_flat_time() -> None:
    origin = build_monthly_process_boundary_plan("2026-07-08").origins[0]

    assert origin.resolve_entry_enabled_at(None) == origin.valid_from
    assert origin.resolve_entry_enabled_at(origin.valid_from - timedelta(hours=4)) == origin.valid_from
    later_flat = origin.valid_from + timedelta(days=2, hours=3)
    assert origin.resolve_entry_enabled_at(later_flat) == later_flat
    assert origin.resolve_entry_enabled_at(origin.valid_until) is None


def test_entry_enabled_at_rejects_naive_and_non_utc_times() -> None:
    origin = build_monthly_process_boundary_plan("2026-07-08").origins[0]

    with pytest.raises(BoundaryValidationError, match="timezone-aware UTC"):
        origin.resolve_entry_enabled_at(datetime(2025, 7, 10))
    with pytest.raises(BoundaryValidationError, match="nonzero offset"):
        origin.resolve_entry_enabled_at(
            datetime(2025, 7, 10, tzinfo=timezone(timedelta(hours=2)))
        )


def test_button_before_anchor_targets_current_anchor_without_backdating() -> None:
    resolution = resolve_target_anchor_for_button(datetime(2026, 7, 7, 12, tzinfo=UTC))

    assert resolution.target_anchor == date(2026, 7, 8)
    assert resolution.as_of_day == date(2026, 7, 7)
    assert resolution.valid_from == datetime(2026, 7, 9, tzinfo=UTC)
    assert resolution.is_late_for_current_anchor is False
    assert resolution.retroactive_activation_allowed is False
    assert resolution.status == "current_anchor_pending"


def test_button_inside_window_targets_current_anchor() -> None:
    resolution = resolve_target_anchor_for_button(datetime(2026, 7, 8, 23, 59, 59, tzinfo=UTC))
    assert resolution.target_anchor == date(2026, 7, 8)
    assert resolution.is_late_for_current_anchor is False


def test_button_at_or_after_deadline_targets_only_next_anchor() -> None:
    resolutions = (
        resolve_target_anchor_for_button(datetime(2026, 7, 9, tzinfo=UTC)),
        resolve_target_anchor_for_button(datetime(2026, 7, 20, 17, tzinfo=UTC)),
    )

    for resolution in resolutions:
        assert resolution.target_anchor == date(2026, 8, 8)
        assert resolution.as_of_day == date(2026, 8, 7)
        assert resolution.valid_from == datetime(2026, 8, 9, tzinfo=UTC)
        assert resolution.is_late_for_current_anchor is True
        assert resolution.retroactive_activation_allowed is False
        assert resolution.status == "planned_for_next_anchor"


def test_button_resolution_requires_utc_and_fixed_delay() -> None:
    with pytest.raises(BoundaryValidationError, match="timezone-aware UTC"):
        resolve_target_anchor_for_button(datetime(2026, 7, 8, 12))
    with pytest.raises(BoundaryValidationError, match="nonzero offset"):
        resolve_target_anchor_for_button(
            datetime(2026, 7, 8, 12, tzinfo=timezone(timedelta(hours=2)))
        )
    with pytest.raises(BoundaryValidationError, match="must equal 24"):
        resolve_target_anchor_for_button(
            datetime(2026, 7, 8, 12, tzinfo=UTC), activation_delay_hours=23
        )


def test_process_end_resolves_from_latest_complete_day() -> None:
    assert resolve_process_end_exclusive("2026-07-07") == date(2026, 7, 8)
    assert resolve_process_end_exclusive("2026-07-06") == date(2026, 6, 8)
    assert resolve_process_end_exclusive("2024-03-07") == date(2024, 3, 8)
    assert resolve_process_end_exclusive("2024-03-06") == date(2024, 2, 8)


def test_monthly_anchor_clamps_short_months() -> None:
    assert monthly_anchor(2024, 2, 31) == date(2024, 2, 29)
    assert monthly_anchor(2025, 2, 31) == date(2025, 2, 28)
    assert monthly_anchor(2025, 4, 31) == date(2025, 4, 30)


@pytest.mark.parametrize("bad_anchor", [0, 32, True, 8.0])
def test_monthly_anchor_rejects_invalid_days(bad_anchor: object) -> None:
    with pytest.raises(BoundaryValidationError, match="anchor_day"):
        monthly_anchor(2026, 7, bad_anchor)  # type: ignore[arg-type]


def test_process_end_must_be_real_day_8_anchor() -> None:
    with pytest.raises(BoundaryValidationError, match="monthly anchor"):
        build_monthly_process_boundary_plan("2026-07-07")


def test_datetime_is_rejected_where_date_is_required() -> None:
    with pytest.raises(BoundaryValidationError, match="date, not a datetime"):
        build_monthly_process_boundary_plan(  # type: ignore[arg-type]
            datetime(2026, 7, 8, tzinfo=UTC)
        )


def test_validator_rejects_duplicate_or_gapped_boundaries() -> None:
    plan = build_monthly_process_boundary_plan("2026-07-08")
    duplicated = replace(
        plan,
        boundary_dates=(plan.boundary_dates[0], plan.boundary_dates[0], *plan.boundary_dates[2:]),
    )
    with pytest.raises(BoundaryValidationError, match="strictly increasing"):
        validate_monthly_process_boundary_plan(duplicated)

    origins = list(plan.origins)
    origins[0] = replace(
        origins[0],
        test_end_exclusive=origins[0].test_end_exclusive - timedelta(days=1),
        valid_until=origins[0].valid_until - timedelta(days=1),
    )
    with pytest.raises(
        BoundaryValidationError,
        match="exactly 365|gap|wrong boundary|do not match",
    ):
        validate_monthly_process_boundary_plan(replace(plan, origins=tuple(origins)))


def test_validator_rejects_training_overlap_and_wrong_activation() -> None:
    plan = build_monthly_process_boundary_plan("2026-07-08")
    origins = list(plan.origins)
    origins[0] = replace(
        origins[0],
        training_end_exclusive=origins[0].test_start_inclusive + timedelta(days=1),
    )
    with pytest.raises(BoundaryValidationError, match="training"):
        validate_monthly_process_boundary_plan(replace(plan, origins=tuple(origins)))

    origins = list(plan.origins)
    origins[0] = replace(origins[0], valid_from=origins[0].valid_from - timedelta(seconds=1))
    with pytest.raises(BoundaryValidationError, match=r"T\+24h"):
        validate_monthly_process_boundary_plan(replace(plan, origins=tuple(origins)))


def test_validator_rejects_wrong_protocol_constants() -> None:
    plan = build_monthly_process_boundary_plan("2026-07-08")

    with pytest.raises(BoundaryValidationError, match="timezone"):
        validate_monthly_process_boundary_plan(replace(plan, timezone="Europe/Berlin"))
    with pytest.raises(BoundaryValidationError, match="730"):
        validate_monthly_process_boundary_plan(replace(plan, training_days_per_origin=729))
    with pytest.raises(BoundaryValidationError, match="365"):
        validate_monthly_process_boundary_plan(replace(plan, process_oos_days=364))
    with pytest.raises(BoundaryValidationError, match="24"):
        validate_monthly_process_boundary_plan(replace(plan, activation_delay_hours=23))


def test_same_input_produces_same_frozen_plan() -> None:
    assert build_monthly_process_boundary_plan("2026-07-08") == (
        build_monthly_process_boundary_plan(date(2026, 7, 8))
    )
