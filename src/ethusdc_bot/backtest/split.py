"""Train/blind split logic for ETHUSDC backtests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from ethusdc_bot.backtest.data_loader import Candle

TRAINING_DAYS = 730
BLINDTEST_DAYS = 365
REQUIRED_DAYS = TRAINING_DAYS + BLINDTEST_DAYS


@dataclass(frozen=True)
class SplitResult:
    training: list[Candle]
    blindtest: list[Candle]
    data_start: str
    data_end: str
    training_start: str
    training_end: str
    blind_start: str
    blind_end: str
    training_days: int
    blindtest_days: int


@dataclass(frozen=True)
class ResearchWindowPlan:
    """Latest final window plus leakage-safe historical robustness origins."""

    final_window: SplitResult
    historical_origins: tuple[SplitResult, ...]
    latest_complete_day: str
    available_complete_days: int
    skipped_historical_origins: tuple[dict[str, str], ...] = ()

    @property
    def historical_origin_count(self) -> int:
        return len(self.historical_origins)

    @property
    def skipped_historical_origin_count(self) -> int:
        return len(self.skipped_historical_origins)


def build_research_window_plan(
    candles: list[Candle],
    *,
    training_days: int = TRAINING_DAYS,
    blindtest_days: int = BLINDTEST_DAYS,
    latest_complete_day: date | str | None = None,
    rolling_step_days: int = BLINDTEST_DAYS,
    max_historical_origins: int | None = None,
    expected_candles_per_day: int | None = None,
    excluded_selection_windows: Sequence[
        Mapping[str, object] | tuple[date | str, date | str]
    ] = (),
) -> ResearchWindowPlan:
    """Build a dynamic latest window and prior non-leaking rolling origins.

    The most recent ``training_days + blindtest_days`` consecutive complete
    UTC days form the final window. When ``expected_candles_per_day`` is set,
    an incomplete trailing day is ignored and incomplete days inside the
    selected range fail closed. Historical origins are allowed only when their
    out-of-sample period ends before the final window's blindtest starts.

    ``excluded_selection_windows`` is an inclusive consumed-data ledger. The
    final training slice and both slices of every historical origin are
    selection-bearing and may not overlap it. The final sealed holdout is not
    checked here because it is metadata-only during research.
    """

    if not candles:
        raise ValueError("Cannot build research windows from empty candles")
    if training_days <= 0 or blindtest_days <= 0:
        raise ValueError("training_days and blindtest_days must be positive")
    if rolling_step_days <= 0:
        raise ValueError("rolling_step_days must be positive")
    if max_historical_origins is not None and max_historical_origins < 0:
        raise ValueError("max_historical_origins must be non-negative")
    if expected_candles_per_day is not None and (
        isinstance(expected_candles_per_day, bool)
        or not isinstance(expected_candles_per_day, int)
        or expected_candles_per_day <= 0
    ):
        raise ValueError("expected_candles_per_day must be a positive integer or None")

    complete_days, observed_counts = _complete_utc_days(candles, expected_candles_per_day)
    if latest_complete_day is None:
        if not complete_days:
            raise ValueError("No complete UTC day is present in candles")
        endpoint = complete_days[-1]
    else:
        endpoint = _parse_day(latest_complete_day)
        if endpoint not in observed_counts:
            raise ValueError(f"Latest complete UTC day is not present in candles: {endpoint.isoformat()}")
        if endpoint not in complete_days:
            raise ValueError(f"Pinned latest UTC day is incomplete: {endpoint.isoformat()}")
    eligible_days = [day for day in complete_days if day <= endpoint]
    required_days = training_days + blindtest_days
    if len(eligible_days) < required_days:
        raise ValueError(f"Expected at least {required_days} complete UTC days, observed {len(eligible_days)}")

    excluded = _normalize_excluded_windows(excluded_selection_windows)
    final_days = eligible_days[-required_days:]
    final_window = _split_selected_days(candles, final_days, training_days, blindtest_days)
    _assert_selection_window_allowed(
        "final training",
        final_window.training_start,
        final_window.training_end,
        excluded,
    )

    historical_newest_first: list[SplitResult] = []
    skipped_historical_origins: list[dict[str, str]] = []
    historical_end_index = len(eligible_days) - blindtest_days - 1
    while historical_end_index - required_days + 1 >= 0 and (
        max_historical_origins is None or len(historical_newest_first) < max_historical_origins
    ):
        historical_start_index = historical_end_index - required_days + 1
        origin_days = eligible_days[historical_start_index : historical_end_index + 1]
        origin = _split_selected_days(candles, origin_days, training_days, blindtest_days)
        if origin.blind_end >= final_window.blind_start:
            raise ValueError("Historical rolling origin overlaps the final blindtest window")
        try:
            _assert_selection_window_allowed(
                "historical origin training",
                origin.training_start,
                origin.training_end,
                excluded,
            )
            _assert_selection_window_allowed(
                "historical origin out-of-sample",
                origin.blind_start,
                origin.blind_end,
                excluded,
            )
        except ValueError as exc:
            skipped_historical_origins.append(
                {
                    "training_start": origin.training_start,
                    "training_end": origin.training_end,
                    "oos_start": origin.blind_start,
                    "oos_end": origin.blind_end,
                    "reason": str(exc),
                }
            )
        else:
            historical_newest_first.append(origin)
        historical_end_index -= rolling_step_days

    return ResearchWindowPlan(
        final_window=final_window,
        historical_origins=tuple(reversed(historical_newest_first)),
        latest_complete_day=endpoint.isoformat(),
        available_complete_days=len(eligible_days),
        skipped_historical_origins=tuple(skipped_historical_origins),
    )


def split_train_blind(candles: list[Candle], *, required_days: int | None = REQUIRED_DAYS) -> SplitResult:
    if not candles:
        raise ValueError("Cannot split empty candles")
    dates = sorted({_utc_day(candle.open_time) for candle in candles})
    if required_days is not None and len(dates) != required_days:
        raise ValueError(f"Expected exactly {required_days} complete UTC days, observed {len(dates)}")
    if required_days is not None:
        training_day_count = TRAINING_DAYS
        blind_day_count = BLINDTEST_DAYS
    else:
        training_day_count = max(1, len(dates) * 2 // 3)
        blind_day_count = len(dates) - training_day_count
        if blind_day_count <= 0:
            training_day_count = max(1, len(dates) - 1)
            blind_day_count = len(dates) - training_day_count
    training_days = set(dates[:training_day_count])
    blind_days = set(dates[training_day_count : training_day_count + blind_day_count])
    training = [candle for candle in candles if _utc_day(candle.open_time) in training_days]
    blindtest = [candle for candle in candles if _utc_day(candle.open_time) in blind_days]
    if not training or not blindtest:
        raise ValueError("Split requires non-empty training and blindtest windows")
    if max(c.open_time for c in training) >= min(c.open_time for c in blindtest):
        raise ValueError("Training and blindtest windows overlap")
    return SplitResult(
        training=training,
        blindtest=blindtest,
        data_start=dates[0],
        data_end=dates[-1],
        training_start=dates[0],
        training_end=dates[training_day_count - 1],
        blind_start=dates[training_day_count],
        blind_end=dates[training_day_count + blind_day_count - 1],
        training_days=training_day_count,
        blindtest_days=blind_day_count,
    )


def _utc_day(open_time_ms: int) -> str:
    return _utc_date(open_time_ms).isoformat()


def _utc_date(open_time_ms: int) -> date:
    return datetime.fromtimestamp(open_time_ms / 1000, tz=UTC).date()


def _parse_day(value: date | str) -> date:
    return date.fromisoformat(value) if isinstance(value, str) else value


def _complete_utc_days(
    candles: list[Candle], expected_candles_per_day: int | None
) -> tuple[list[date], dict[date, int]]:
    open_times = [candle.open_time for candle in candles]
    if len(set(open_times)) != len(open_times):
        raise ValueError("Duplicate candle open_time prevents complete-day validation")

    observed_times: dict[date, list[int]] = {}
    for candle in candles:
        day = _utc_date(candle.open_time)
        observed_times.setdefault(day, []).append(candle.open_time)
    observed_counts = {day: len(times) for day, times in observed_times.items()}
    if expected_candles_per_day is None:
        return sorted(observed_counts), observed_counts

    overfilled = [
        day for day, count in observed_counts.items() if count > expected_candles_per_day
    ]
    if overfilled:
        first = min(overfilled)
        raise ValueError(
            f"UTC day {first.isoformat()} has more than {expected_candles_per_day} candles"
        )
    complete = sorted(
        day
        for day, count in observed_counts.items()
        if count == expected_candles_per_day
        and _has_expected_utc_grid(day, observed_times[day], expected_candles_per_day)
    )
    return complete, observed_counts


def _has_expected_utc_grid(
    day: date, open_times: list[int], expected_candles_per_day: int
) -> bool:
    if expected_candles_per_day != 1440:
        return True
    day_start_ms = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    return all(
        open_time == day_start_ms + minute * 60_000
        for minute, open_time in enumerate(sorted(open_times))
    )


def _normalize_excluded_windows(
    windows: Sequence[Mapping[str, object] | tuple[date | str, date | str]],
) -> tuple[tuple[date, date, str], ...]:
    normalized: list[tuple[date, date, str]] = []
    for index, window in enumerate(windows, start=1):
        if isinstance(window, Mapping):
            start_value = window.get("start")
            end_value = window.get("end")
            label = str(window.get("reason") or f"excluded window {index}")
        elif isinstance(window, tuple) and len(window) == 2:
            start_value, end_value = window
            label = f"excluded window {index}"
        else:
            raise ValueError(
                "excluded_selection_windows entries must be mappings with start/end or two-item tuples"
            )
        if not isinstance(start_value, (date, str)) or not isinstance(end_value, (date, str)):
            raise ValueError("excluded_selection_windows start/end must be ISO dates or date objects")
        start = _parse_day(start_value)
        end = _parse_day(end_value)
        if start > end:
            raise ValueError("excluded_selection_windows start must not be after end")
        normalized.append((start, end, label))
    return tuple(normalized)


def _assert_selection_window_allowed(
    selection_label: str,
    selection_start: date | str,
    selection_end: date | str,
    excluded: tuple[tuple[date, date, str], ...],
) -> None:
    start = _parse_day(selection_start)
    end = _parse_day(selection_end)
    for excluded_start, excluded_end, excluded_label in excluded:
        if start <= excluded_end and excluded_start <= end:
            raise ValueError(
                f"Selection-bearing {selection_label} {start.isoformat()}..{end.isoformat()} "
                f"overlaps consumed/excluded window {excluded_start.isoformat()}..{excluded_end.isoformat()} "
                f"({excluded_label})"
            )


def _split_selected_days(
    candles: list[Candle],
    selected_days: list[date],
    training_day_count: int,
    blind_day_count: int,
) -> SplitResult:
    expected_count = training_day_count + blind_day_count
    if len(selected_days) != expected_count:
        raise ValueError(f"Expected {expected_count} selected UTC days, observed {len(selected_days)}")
    _assert_continuous_days(selected_days)
    training_dates = set(selected_days[:training_day_count])
    blind_dates = set(selected_days[training_day_count:])
    training = sorted((candle for candle in candles if _utc_date(candle.open_time) in training_dates), key=lambda candle: candle.open_time)
    blindtest = sorted((candle for candle in candles if _utc_date(candle.open_time) in blind_dates), key=lambda candle: candle.open_time)
    if not training or not blindtest:
        raise ValueError("Split requires non-empty training and blindtest windows")
    if max(candle.open_time for candle in training) >= min(candle.open_time for candle in blindtest):
        raise ValueError("Training and blindtest windows overlap")
    return SplitResult(
        training=training,
        blindtest=blindtest,
        data_start=selected_days[0].isoformat(),
        data_end=selected_days[-1].isoformat(),
        training_start=selected_days[0].isoformat(),
        training_end=selected_days[training_day_count - 1].isoformat(),
        blind_start=selected_days[training_day_count].isoformat(),
        blind_end=selected_days[-1].isoformat(),
        training_days=training_day_count,
        blindtest_days=blind_day_count,
    )


def _assert_continuous_days(days: list[date]) -> None:
    for previous, current in zip(days, days[1:]):
        expected = previous + timedelta(days=1)
        if current != expected:
            raise ValueError(
                f"Complete UTC days must be continuous; expected {expected.isoformat()}, observed {current.isoformat()}"
            )
