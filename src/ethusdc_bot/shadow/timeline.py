"""Forward-only UTC minute boundaries for adopted Shadow deployments."""

from __future__ import annotations

from datetime import datetime, timedelta

from ethusdc_bot.backtest.data_loader import EXPECTED_STEP_MS


def first_shadow_candle_open_time_ms(created_at_utc: object) -> int:
    """Return the first candle open that contains no pre-adoption observations.

    An adoption exactly on a UTC minute boundary may consume that minute after
    the candle closes.  Any seconds or microseconds inside an already-open
    minute advance the cursor to the next full minute.
    """

    if not isinstance(created_at_utc, str) or not created_at_utc.endswith("Z"):
        raise ValueError("deployment creation timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(created_at_utc[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("deployment creation timestamp is invalid") from exc
    minute = parsed.replace(second=0, microsecond=0)
    if parsed != minute:
        minute += timedelta(minutes=1)
    timestamp_ms = int(minute.timestamp()) * 1000
    if timestamp_ms < 0 or timestamp_ms % EXPECTED_STEP_MS != 0:
        raise ValueError("deployment creation timestamp is invalid")
    return timestamp_ms


__all__ = ["first_shadow_candle_open_time_ms"]
