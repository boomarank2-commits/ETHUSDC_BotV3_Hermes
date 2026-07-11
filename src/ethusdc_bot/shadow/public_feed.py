"""Read-only public ETHUSDC one-minute market-data feed.

Only Binance's public Spot kline resource is used.  The module deliberately has
no concept of credentials, accounts, balances, or trading actions.  A candle is
published only after Binance's close timestamp is strictly older than the
caller-provided clock.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
import json
import math
import time
from typing import Any, Protocol
import urllib.error
import urllib.parse
import urllib.request

from ethusdc_bot.backtest.data_loader import Candle


SYMBOL = "ETHUSDC"
INTERVAL = "1m"
INTERVAL_MS = 60_000
# Binance's current Spot documentation recommends the dedicated market-data
# host for public-only consumers.  This host exposes no account or order use in
# this module; the fixed path below remains the public kline resource.
PUBLIC_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
DEFAULT_LIMIT = 1_000
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
MAX_RESPONSE_BYTES = 4_000_000


class PublicKlineFeedError(RuntimeError):
    """Base exception for a fail-closed public market-data operation."""


class PublicKlineNetworkError(PublicKlineFeedError):
    """Raised when the public endpoint cannot be read successfully."""


class PublicKlineValidationError(PublicKlineFeedError):
    """Raised when remote data violates the expected one-minute schema."""


class PublicKlinePollerError(PublicKlineFeedError):
    """Raised when a poller dependency or callback fails."""


class PublicKlineContinuityError(PublicKlinePollerError):
    """Raised when the public poller observes a missing forward minute."""


class _StopEvent(Protocol):
    def is_set(self) -> bool: ...


def _wall_clock_ms() -> int:
    return time.time_ns() // 1_000_000


def fetch_closed_klines(
    start_time_ms: int | None = None,
    limit: int = DEFAULT_LIMIT,
    now_ms: int | None = None,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[Candle]:
    """Fetch a validated, contiguous batch of fully closed ETHUSDC 1m candles.

    ``close_time < now_ms`` is the closure rule.  Therefore a candle whose
    close timestamp equals ``now_ms`` is not returned.  An empty result is a
    valid response when Binance has no fully closed candle for the request.
    """

    validated_limit = _require_limit(limit)
    validated_start = _optional_nonnegative_int(start_time_ms, "start_time_ms")
    effective_now = _require_nonnegative_int(
        _wall_clock_ms() if now_ms is None else now_ms,
        "now_ms",
    )

    query: dict[str, str] = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "limit": str(validated_limit),
    }
    if validated_start is not None:
        query["startTime"] = str(validated_start)
    url = f"{PUBLIC_KLINES_URL}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, method="GET")

    try:
        response = opener(request, timeout=DEFAULT_TIMEOUT_SECONDS)
        try:
            status = getattr(response, "status", 200)
            if status != 200:
                raise PublicKlineNetworkError(
                    f"Public kline endpoint returned HTTP status {status}"
                )
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except PublicKlineFeedError:
        raise
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        raise PublicKlineNetworkError("Public kline endpoint could not be read") from exc
    except Exception as exc:
        raise PublicKlineNetworkError("Public kline opener failed") from exc

    if not isinstance(raw, bytes):
        raise PublicKlineValidationError("Public kline response must be bytes")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise PublicKlineValidationError("Public kline response exceeds the size limit")
    try:
        text = raw.decode("utf-8", errors="strict")
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PublicKlineValidationError("Public kline response is not strict JSON") from exc

    rows = _require_kline_array(payload)
    parsed: list[tuple[Candle, int]] = []
    previous_open_time: int | None = None
    for index, row in enumerate(rows):
        candle, close_time = _parse_kline_row(row, index=index)
        if validated_start is not None and candle.open_time < validated_start:
            raise PublicKlineValidationError(
                "Public kline response starts before the requested timestamp"
            )
        if previous_open_time is not None:
            step = candle.open_time - previous_open_time
            if step != INTERVAL_MS:
                raise PublicKlineValidationError(
                    "Public kline response contains a duplicate, reversal, or gap"
                )
        parsed.append((candle, close_time))
        previous_open_time = candle.open_time

    return [candle for candle, close_time in parsed if close_time < effective_now]


def run_public_kline_poller(
    start_time_ms: int,
    stop_event: _StopEvent,
    on_candles: Callable[[list[Candle]], Any],
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    *,
    limit: int = DEFAULT_LIMIT,
    fetcher: Callable[..., list[Candle]] = fetch_closed_klines,
    sleeper: Callable[[float], Any] = time.sleep,
    clock: Callable[[], int] = _wall_clock_ms,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> None:
    """Poll closed public candles, emitting each minute at most once.

    The cursor moves only after the callback accepts a fully validated batch.
    Fetch, parsing, clock, and callback failures are surfaced as
    :class:`PublicKlineFeedError` subclasses; no callback is made for a failed
    fetch.  Repeated candles from an overlapping successful response are
    ignored, while any missing new minute stops the poller.
    """

    cursor = _require_nonnegative_int(start_time_ms, "start_time_ms")
    validated_limit = _require_limit(limit)
    interval = _require_positive_seconds(poll_interval_seconds)
    if not callable(on_candles):
        raise PublicKlinePollerError("on_candles must be callable")
    if not callable(fetcher) or not callable(sleeper) or not callable(clock):
        raise PublicKlinePollerError("poller dependencies must be callable")
    is_stopped = getattr(stop_event, "is_set", None)
    if not callable(is_stopped):
        raise PublicKlinePollerError("stop_event must provide is_set()")

    first_expected_open = _ceil_to_minute(cursor)
    last_emitted_open: int | None = None

    while not is_stopped():
        try:
            effective_now = _require_nonnegative_int(clock(), "clock result")
        except PublicKlineValidationError as exc:
            raise PublicKlinePollerError("poller clock returned an invalid value") from exc
        except Exception as exc:
            raise PublicKlinePollerError("poller clock failed") from exc

        try:
            batch = fetcher(
                start_time_ms=cursor,
                limit=validated_limit,
                now_ms=effective_now,
                opener=opener,
            )
        except PublicKlineFeedError:
            raise
        except Exception as exc:
            raise PublicKlinePollerError("public kline fetch failed") from exc

        validated_batch = _validate_poller_batch(batch, effective_now=effective_now)
        if is_stopped():
            return

        new_candles = [
            candle
            for candle in validated_batch
            if last_emitted_open is None or candle.open_time > last_emitted_open
        ]
        if new_candles:
            expected_open = (
                first_expected_open
                if last_emitted_open is None
                else last_emitted_open + INTERVAL_MS
            )
            if new_candles[0].open_time != expected_open:
                raise PublicKlineContinuityError(
                    "public kline poller detected a missing minute"
                )
            callback_last_open = new_candles[-1].open_time
            try:
                on_candles(list(new_candles))
            except Exception as exc:
                raise PublicKlinePollerError("public kline callback failed") from exc
            last_emitted_open = callback_last_open
            cursor = callback_last_open + INTERVAL_MS

        if is_stopped():
            return
        try:
            sleeper(interval)
        except Exception as exc:
            raise PublicKlinePollerError("public kline poller sleep failed") from exc


def _require_kline_array(payload: object) -> list[object]:
    if not isinstance(payload, list):
        raise PublicKlineValidationError("Public kline JSON must be an array")
    return payload


def _parse_kline_row(row: object, *, index: int) -> tuple[Candle, int]:
    if not isinstance(row, list) or len(row) != 12:
        raise PublicKlineValidationError(
            f"Public kline row {index} must contain exactly 12 fields"
        )

    open_time = _require_nonnegative_int(row[0], f"row {index} open_time")
    close_time = _require_nonnegative_int(row[6], f"row {index} close_time")
    if open_time % INTERVAL_MS != 0:
        raise PublicKlineValidationError(
            f"Public kline row {index} open_time is not on the 1m UTC grid"
        )
    if close_time != open_time + INTERVAL_MS - 1:
        raise PublicKlineValidationError(
            f"Public kline row {index} has an invalid close_time"
        )

    open_price = _require_decimal(row[1], f"row {index} open", positive=True)
    high_price = _require_decimal(row[2], f"row {index} high", positive=True)
    low_price = _require_decimal(row[3], f"row {index} low", positive=True)
    close_price = _require_decimal(row[4], f"row {index} close", positive=True)
    volume = _require_decimal(row[5], f"row {index} volume", positive=False)
    _require_decimal(row[7], f"row {index} quote volume", positive=False)
    _require_nonnegative_int(row[8], f"row {index} trade count")
    _require_decimal(row[9], f"row {index} taker base volume", positive=False)
    _require_decimal(row[10], f"row {index} taker quote volume", positive=False)
    _require_decimal(row[11], f"row {index} trailing field", positive=False)

    if high_price < max(open_price, close_price) or low_price > min(
        open_price, close_price
    ):
        raise PublicKlineValidationError(
            f"Public kline row {index} violates OHLC bounds"
        )
    if low_price > high_price:
        raise PublicKlineValidationError(
            f"Public kline row {index} has low above high"
        )

    candle = Candle(
        open_time=open_time,
        open=_finite_float(open_price, f"row {index} open"),
        high=_finite_float(high_price, f"row {index} high"),
        low=_finite_float(low_price, f"row {index} low"),
        close=_finite_float(close_price, f"row {index} close"),
        volume=_finite_float(volume, f"row {index} volume"),
    )
    return candle, close_time


def _validate_poller_batch(
    batch: object,
    *,
    effective_now: int,
) -> list[Candle]:
    if not isinstance(batch, list):
        raise PublicKlinePollerError("public kline fetcher must return a list")
    previous: int | None = None
    validated: list[Candle] = []
    for candle in batch:
        if not isinstance(candle, Candle):
            raise PublicKlinePollerError("public kline fetcher returned a non-Candle")
        if (
            isinstance(candle.open_time, bool)
            or not isinstance(candle.open_time, int)
            or candle.open_time < 0
            or candle.open_time % INTERVAL_MS != 0
        ):
            raise PublicKlinePollerError("public kline fetcher returned an invalid grid")
        if candle.open_time + INTERVAL_MS - 1 >= effective_now:
            raise PublicKlinePollerError("public kline fetcher returned an open candle")
        values = (candle.open, candle.high, candle.low, candle.close)
        if any(not _is_positive_finite_number(value) for value in values):
            raise PublicKlinePollerError("public kline fetcher returned invalid OHLC")
        if not _is_nonnegative_finite_number(candle.volume):
            raise PublicKlinePollerError("public kline fetcher returned invalid volume")
        if candle.high < max(candle.open, candle.close):
            raise PublicKlinePollerError("public kline fetcher returned invalid high")
        if candle.low > min(candle.open, candle.close):
            raise PublicKlinePollerError("public kline fetcher returned invalid low")
        if previous is not None and candle.open_time - previous != INTERVAL_MS:
            raise PublicKlinePollerError(
                "public kline fetcher returned a duplicate, reversal, or gap"
            )
        validated.append(candle)
        previous = candle.open_time
    return validated


def _require_limit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1_000:
        raise PublicKlineValidationError("limit must be an integer from 1 through 1000")
    return value


def _optional_nonnegative_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _require_nonnegative_int(value, field)


def _require_nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PublicKlineValidationError(f"{field} must be a nonnegative integer")
    return value


def _require_decimal(value: object, field: str, *, positive: bool) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise PublicKlineValidationError(f"{field} must be numeric")
    if isinstance(value, str) and (not value or value != value.strip()):
        raise PublicKlineValidationError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise PublicKlineValidationError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise PublicKlineValidationError(f"{field} must be finite")
    if positive and result <= 0:
        raise PublicKlineValidationError(f"{field} must be positive")
    if not positive and result < 0:
        raise PublicKlineValidationError(f"{field} must be nonnegative")
    return result


def _finite_float(value: Decimal, field: str) -> float:
    converted = float(value)
    if not math.isfinite(converted):
        raise PublicKlineValidationError(f"{field} cannot be represented safely")
    return converted


def _is_positive_finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value > 0
    )


def _is_nonnegative_finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= 0
    )


def _ceil_to_minute(timestamp_ms: int) -> int:
    quotient, remainder = divmod(timestamp_ms, INTERVAL_MS)
    return quotient * INTERVAL_MS if remainder == 0 else (quotient + 1) * INTERVAL_MS


def _require_positive_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PublicKlinePollerError("poll_interval_seconds must be numeric")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0:
        raise PublicKlinePollerError("poll_interval_seconds must be positive")
    return converted


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant is forbidden: {value}")
