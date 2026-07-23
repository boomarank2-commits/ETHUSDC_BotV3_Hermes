"""Pure UTC boundary planning for Protocol v3 monthly research.

This module implements only task 2 of the Protocol v3 implementation sequence:
calendar boundaries, 730-day development windows, the exact 365-day process-OOS
union, the fixed 24-hour activation delay, and fail-closed late-button routing.
It does not select candidates, read market data, execute trades, or evaluate PnL.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Iterable

TRAINING_DAYS_PER_ORIGIN = 730
PROCESS_OOS_DAYS = 365
OUTER_ORIGINS = 12
DEPLOYMENT_ANCHOR_DAY_UTC = 8
ACTIVATION_DELAY_HOURS = 24


class BoundaryValidationError(ValueError):
    """Raised when a Protocol v3 calendar plan is incomplete or contradictory."""


@dataclass(frozen=True)
class MonthlyOriginBoundary:
    """One outer monthly origin and its strictly following OOS interval."""

    origin_index: int
    target_anchor: date
    target_anchor_is_synthetic: bool
    training_start_inclusive: date
    training_end_exclusive: date
    test_start_inclusive: date
    test_end_exclusive: date
    as_of_day: date
    valid_from: datetime
    valid_until: datetime
    manual_decision_deadline: datetime
    entry_enabled_at: datetime

    @property
    def training_day_count(self) -> int:
        return (self.training_end_exclusive - self.training_start_inclusive).days

    @property
    def test_day_count(self) -> int:
        return (self.test_end_exclusive - self.test_start_inclusive).days

    def iter_test_days(self) -> tuple[date, ...]:
        return tuple(_iter_days(self.test_start_inclusive, self.test_end_exclusive))

    def resolve_entry_enabled_at(self, flat_time: datetime | None) -> datetime | None:
        """Return ``max(valid_from, flat_time)`` or ``None`` after interval expiry."""

        normalized_flat = self.valid_from if flat_time is None else _require_utc_datetime(
            flat_time, "flat_time"
        )
        enabled_at = max(self.valid_from, normalized_flat)
        return enabled_at if enabled_at < self.valid_until else None


@dataclass(frozen=True)
class MonthlyProcessBoundaryPlan:
    """Twelve origins whose OOS intervals form exactly one 365-day union."""

    process_start_inclusive: date
    process_end_exclusive: date
    boundary_dates: tuple[date, ...]
    origins: tuple[MonthlyOriginBoundary, ...]
    timezone: str = "UTC"
    deployment_anchor_day_utc: int = DEPLOYMENT_ANCHOR_DAY_UTC
    training_days_per_origin: int = TRAINING_DAYS_PER_ORIGIN
    process_oos_days: int = PROCESS_OOS_DAYS
    activation_delay_hours: int = ACTIVATION_DELAY_HOURS

    def iter_process_oos_days(self) -> tuple[date, ...]:
        days: list[date] = []
        for origin in self.origins:
            days.extend(origin.iter_test_days())
        return tuple(days)


@dataclass(frozen=True)
class LateButtonResolution:
    """Fail-closed target for a manual research button press."""

    button_pressed_at: datetime
    target_anchor: date
    as_of_day: date
    valid_from: datetime
    is_late_for_current_anchor: bool
    retroactive_activation_allowed: bool
    status: str


def monthly_anchor(year: int, month: int, anchor_day: int = DEPLOYMENT_ANCHOR_DAY_UTC) -> date:
    """Return the month's anchor, clamped to its last valid calendar day."""

    if isinstance(anchor_day, bool) or not isinstance(anchor_day, int) or not 1 <= anchor_day <= 31:
        raise BoundaryValidationError("anchor_day must be an integer from 1 through 31")
    if isinstance(year, bool) or not isinstance(year, int) or year < 1:
        raise BoundaryValidationError("year must be a positive integer")
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise BoundaryValidationError("month must be an integer from 1 through 12")
    return date(year, month, min(anchor_day, calendar.monthrange(year, month)[1]))


def resolve_process_end_exclusive(
    latest_complete_day: date | str,
    *,
    anchor_day: int = DEPLOYMENT_ANCHOR_DAY_UTC,
) -> date:
    """Resolve the newest anchor whose immediately previous UTC day is complete."""

    latest = _parse_day(latest_complete_day, "latest_complete_day")
    candidate = monthly_anchor(latest.year, latest.month, anchor_day)
    if latest >= candidate - timedelta(days=1):
        return candidate
    previous_year, previous_month = _shift_month(latest.year, latest.month, -1)
    previous = monthly_anchor(previous_year, previous_month, anchor_day)
    if latest < previous - timedelta(days=1):
        raise BoundaryValidationError("latest_complete_day cannot support a previous monthly anchor")
    return previous


def resolve_target_anchor_for_button(
    button_pressed_at: datetime,
    *,
    anchor_day: int = DEPLOYMENT_ANCHOR_DAY_UTC,
    activation_delay_hours: int = ACTIVATION_DELAY_HOURS,
) -> LateButtonResolution:
    """Route a button press without ever backdating a monthly decision.

    Before the current month's anchor, or strictly before its ``T+24h`` deadline,
    the current anchor remains the target. At the deadline or later the press is
    late and can only plan the next monthly anchor.
    """

    pressed = _require_utc_datetime(button_pressed_at, "button_pressed_at")
    if activation_delay_hours != ACTIVATION_DELAY_HOURS:
        raise BoundaryValidationError("Protocol v3 activation_delay_hours must equal 24")

    current_anchor = monthly_anchor(pressed.year, pressed.month, anchor_day)
    current_anchor_at = _at_utc_midnight(current_anchor)
    current_deadline = current_anchor_at + timedelta(hours=activation_delay_hours)

    if pressed < current_anchor_at or pressed < current_deadline:
        target = current_anchor
        late = False
        status = "current_anchor_pending"
    else:
        next_year, next_month = _shift_month(current_anchor.year, current_anchor.month, 1)
        target = monthly_anchor(next_year, next_month, anchor_day)
        late = True
        status = "planned_for_next_anchor"

    return LateButtonResolution(
        button_pressed_at=pressed,
        target_anchor=target,
        as_of_day=target - timedelta(days=1),
        valid_from=_at_utc_midnight(target) + timedelta(hours=activation_delay_hours),
        is_late_for_current_anchor=late,
        retroactive_activation_allowed=False,
        status=status,
    )


def build_monthly_process_boundary_plan(
    process_end_exclusive: date | str,
) -> MonthlyProcessBoundaryPlan:
    """Build the exact twelve-origin Protocol v3 boundary plan."""

    process_end = _parse_day(process_end_exclusive, "process_end_exclusive")
    expected_anchor = monthly_anchor(
        process_end.year,
        process_end.month,
        DEPLOYMENT_ANCHOR_DAY_UTC,
    )
    if process_end != expected_anchor:
        raise BoundaryValidationError(
            "process_end_exclusive must be the Protocol v3 monthly anchor "
            f"{expected_anchor.isoformat()}"
        )

    process_start = process_end - timedelta(days=PROCESS_OOS_DAYS)
    real_monthly_anchors = _monthly_anchors_strictly_after(
        process_start,
        process_end,
        DEPLOYMENT_ANCHOR_DAY_UTC,
    )
    boundaries = (process_start, *real_monthly_anchors)
    if len(boundaries) != OUTER_ORIGINS + 1:
        raise BoundaryValidationError(
            f"Protocol v3 requires {OUTER_ORIGINS + 1} boundaries, observed {len(boundaries)}"
        )
    if boundaries[-1] != process_end:
        raise BoundaryValidationError("Monthly anchor sequence does not end at process_end_exclusive")

    origins: list[MonthlyOriginBoundary] = []
    for index, (test_start, test_end) in enumerate(zip(boundaries, boundaries[1:]), start=1):
        valid_from = _at_utc_midnight(test_start) + timedelta(hours=ACTIVATION_DELAY_HOURS)
        valid_until = _at_utc_midnight(test_end)
        origins.append(
            MonthlyOriginBoundary(
                origin_index=index,
                target_anchor=test_start,
                target_anchor_is_synthetic=index == 1,
                training_start_inclusive=test_start - timedelta(days=TRAINING_DAYS_PER_ORIGIN),
                training_end_exclusive=test_start,
                test_start_inclusive=test_start,
                test_end_exclusive=test_end,
                as_of_day=test_start - timedelta(days=1),
                valid_from=valid_from,
                valid_until=valid_until,
                manual_decision_deadline=valid_from,
                entry_enabled_at=valid_from,
            )
        )

    plan = MonthlyProcessBoundaryPlan(
        process_start_inclusive=process_start,
        process_end_exclusive=process_end,
        boundary_dates=tuple(boundaries),
        origins=tuple(origins),
    )
    validate_monthly_process_boundary_plan(plan)
    return plan


def validate_monthly_process_boundary_plan(plan: MonthlyProcessBoundaryPlan) -> None:
    """Validate every invariant required by Protocol v3 task 2."""

    if plan.timezone != "UTC":
        raise BoundaryValidationError("Protocol v3 timezone must be UTC")
    if plan.deployment_anchor_day_utc != DEPLOYMENT_ANCHOR_DAY_UTC:
        raise BoundaryValidationError("Protocol v3 deployment anchor day must equal 8")
    if plan.training_days_per_origin != TRAINING_DAYS_PER_ORIGIN:
        raise BoundaryValidationError("Protocol v3 training window must equal 730 days")
    if plan.process_oos_days != PROCESS_OOS_DAYS:
        raise BoundaryValidationError("Protocol v3 process OOS must equal 365 days")
    if plan.activation_delay_hours != ACTIVATION_DELAY_HOURS:
        raise BoundaryValidationError("Protocol v3 activation delay must equal 24 hours")
    if plan.process_end_exclusive != monthly_anchor(
        plan.process_end_exclusive.year,
        plan.process_end_exclusive.month,
        DEPLOYMENT_ANCHOR_DAY_UTC,
    ):
        raise BoundaryValidationError("process_end_exclusive is not a Protocol v3 monthly anchor")
    if plan.process_start_inclusive != plan.process_end_exclusive - timedelta(days=PROCESS_OOS_DAYS):
        raise BoundaryValidationError("process start/end do not span exactly 365 days")
    if len(plan.boundary_dates) != OUTER_ORIGINS + 1:
        raise BoundaryValidationError("boundary plan must contain exactly 13 boundaries")
    if len(plan.origins) != OUTER_ORIGINS:
        raise BoundaryValidationError("boundary plan must contain exactly 12 origins")
    if plan.boundary_dates[0] != plan.process_start_inclusive:
        raise BoundaryValidationError("first boundary must equal process_start_inclusive")
    if plan.boundary_dates[-1] != plan.process_end_exclusive:
        raise BoundaryValidationError("last boundary must equal process_end_exclusive")

    for previous, current in zip(plan.boundary_dates, plan.boundary_dates[1:]):
        if current <= previous:
            raise BoundaryValidationError("boundary dates must be strictly increasing and unique")

    expected_days = tuple(_iter_days(plan.process_start_inclusive, plan.process_end_exclusive))
    actual_days = plan.iter_process_oos_days()
    if len(actual_days) != PROCESS_OOS_DAYS:
        raise BoundaryValidationError(
            f"process OOS must contain exactly {PROCESS_OOS_DAYS} days, observed {len(actual_days)}"
        )
    if len(set(actual_days)) != len(actual_days):
        raise BoundaryValidationError("an OOS day appears in more than one origin")
    if actual_days != expected_days:
        raise BoundaryValidationError("OOS day union contains a gap, reordering, or wrong boundary")

    for expected_index, origin in enumerate(plan.origins, start=1):
        expected_start = plan.boundary_dates[expected_index - 1]
        expected_end = plan.boundary_dates[expected_index]
        if origin.origin_index != expected_index:
            raise BoundaryValidationError("origin indexes must be consecutive from 1 through 12")
        if origin.target_anchor != expected_start:
            raise BoundaryValidationError("origin target_anchor must equal its test_start")
        if origin.target_anchor_is_synthetic != (expected_index == 1):
            raise BoundaryValidationError("only the first process boundary may be marked synthetic")
        if origin.test_start_inclusive != expected_start or origin.test_end_exclusive != expected_end:
            raise BoundaryValidationError("origin test boundaries do not match the plan boundary sequence")
        if origin.training_start_inclusive != expected_start - timedelta(days=TRAINING_DAYS_PER_ORIGIN):
            raise BoundaryValidationError("origin training_start is not exactly 730 days before test_start")
        if origin.training_end_exclusive != expected_start:
            raise BoundaryValidationError("origin training must end exclusively at test_start")
        if origin.training_day_count != TRAINING_DAYS_PER_ORIGIN:
            raise BoundaryValidationError("origin training window does not contain exactly 730 days")
        if origin.training_end_exclusive > origin.test_start_inclusive:
            raise BoundaryValidationError("an OOS day lies inside its own training window")
        if origin.as_of_day != expected_start - timedelta(days=1):
            raise BoundaryValidationError("origin as_of_day must be the UTC day before test_start")

        expected_valid_from = _at_utc_midnight(expected_start) + timedelta(
            hours=ACTIVATION_DELAY_HOURS
        )
        expected_valid_until = _at_utc_midnight(expected_end)
        if origin.valid_from != expected_valid_from:
            raise BoundaryValidationError("origin valid_from must equal T+24h")
        if origin.valid_until != expected_valid_until:
            raise BoundaryValidationError("origin valid_until must equal the next boundary")
        if origin.manual_decision_deadline != expected_valid_from:
            raise BoundaryValidationError("manual decision deadline must equal T+24h")
        if origin.entry_enabled_at != expected_valid_from:
            raise BoundaryValidationError("flat-at-anchor entry_enabled_at must equal T+24h")
        if origin.valid_from >= origin.valid_until:
            raise BoundaryValidationError("activation delay leaves no valid deployment interval")

        if expected_index > 1 and expected_start != monthly_anchor(
            expected_start.year,
            expected_start.month,
            DEPLOYMENT_ANCHOR_DAY_UTC,
        ):
            raise BoundaryValidationError("boundaries b1..b12 must be real monthly anchors")


def _monthly_anchors_strictly_after(
    start_exclusive: date,
    end_inclusive: date,
    anchor_day: int,
) -> tuple[date, ...]:
    year, month = start_exclusive.year, start_exclusive.month
    candidate = monthly_anchor(year, month, anchor_day)
    if candidate <= start_exclusive:
        year, month = _shift_month(year, month, 1)
        candidate = monthly_anchor(year, month, anchor_day)

    anchors: list[date] = []
    while candidate <= end_inclusive:
        anchors.append(candidate)
        year, month = _shift_month(year, month, 1)
        candidate = monthly_anchor(year, month, anchor_day)
    return tuple(anchors)


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + offset
    shifted_year, zero_based_month = divmod(absolute, 12)
    if shifted_year < 1:
        raise BoundaryValidationError("month shift falls outside supported calendar range")
    return shifted_year, zero_based_month + 1


def _iter_days(start_inclusive: date, end_exclusive: date) -> Iterable[date]:
    current = start_inclusive
    while current < end_exclusive:
        yield current
        current += timedelta(days=1)


def _at_utc_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _parse_day(value: date | str, field_name: str) -> date:
    if isinstance(value, datetime):
        raise BoundaryValidationError(f"{field_name} must be a date, not a datetime")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise BoundaryValidationError(f"{field_name} must be an ISO date") from exc
    raise BoundaryValidationError(f"{field_name} must be an ISO date or date object")


def _require_utc_datetime(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise BoundaryValidationError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise BoundaryValidationError(f"{field_name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise BoundaryValidationError(f"{field_name} must use UTC, not a nonzero offset")
    return value.astimezone(UTC)


__all__ = [
    "ACTIVATION_DELAY_HOURS",
    "DEPLOYMENT_ANCHOR_DAY_UTC",
    "OUTER_ORIGINS",
    "PROCESS_OOS_DAYS",
    "TRAINING_DAYS_PER_ORIGIN",
    "BoundaryValidationError",
    "LateButtonResolution",
    "MonthlyOriginBoundary",
    "MonthlyProcessBoundaryPlan",
    "build_monthly_process_boundary_plan",
    "monthly_anchor",
    "resolve_process_end_exclusive",
    "resolve_target_anchor_for_button",
    "validate_monthly_process_boundary_plan",
]
