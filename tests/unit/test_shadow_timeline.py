"""Tests for exact forward-only Shadow minute selection."""

from datetime import datetime

from ethusdc_bot.shadow.timeline import first_shadow_candle_open_time_ms


def _ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()) * 1000


def test_exact_minute_is_eligible_after_that_candle_closes():
    assert first_shadow_candle_open_time_ms("2026-01-01T00:00:00Z") == _ms(
        "2026-01-01T00:00:00Z"
    )


def test_any_subminute_adoption_advances_to_next_full_minute():
    expected = _ms("2026-01-01T00:01:00Z")
    assert first_shadow_candle_open_time_ms("2026-01-01T00:00:00.000001Z") == expected
    assert first_shadow_candle_open_time_ms("2026-01-01T00:00:59.999999Z") == expected
