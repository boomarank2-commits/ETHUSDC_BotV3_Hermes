from __future__ import annotations

from dataclasses import dataclass
import inspect
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.shadow import public_feed
from ethusdc_bot.shadow.public_feed import (
    PublicKlineNetworkError,
    PublicKlinePollerError,
    PublicKlineValidationError,
    fetch_closed_klines,
    run_public_kline_poller,
)


def _row(
    open_time: int,
    *,
    open_price: str = "2000.00",
    high: str = "2002.00",
    low: str = "1999.00",
    close: str = "2001.00",
    volume: str = "12.5",
) -> list[object]:
    return [
        open_time,
        open_price,
        high,
        low,
        close,
        volume,
        open_time + 59_999,
        "25000.0",
        42,
        "6.0",
        "12000.0",
        "0",
    ]


class _Response:
    def __init__(self, payload: object, *, status: int = 200) -> None:
        self.body = json.dumps(payload).encode("utf-8")
        self.status = status
        self.closed = False

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]

    def close(self) -> None:
        self.closed = True


def test_fetch_uses_only_fixed_public_get_and_returns_closed_candles() -> None:
    captured: dict[str, object] = {}
    response = _Response([_row(0), _row(60_000), _row(120_000)])

    def opener(request: object, *, timeout: float) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return response

    candles = fetch_closed_klines(
        start_time_ms=0,
        limit=3,
        now_ms=179_999,
        opener=opener,
    )

    request = captured["request"]
    assert request.get_method() == "GET"  # type: ignore[union-attr]
    parsed = urlparse(request.full_url)  # type: ignore[union-attr]
    assert parsed.scheme == "https"
    assert parsed.netloc == "data-api.binance.vision"
    assert parsed.path == "/api/v3/klines"
    assert parse_qs(parsed.query) == {
        "symbol": ["ETHUSDC"],
        "interval": ["1m"],
        "limit": ["3"],
        "startTime": ["0"],
    }
    assert response.closed is True
    assert [candle.open_time for candle in candles] == [0, 60_000]
    assert candles[1] == Candle(60_000, 2000.0, 2002.0, 1999.0, 2001.0, 12.5)


def test_close_time_equal_to_clock_is_not_closed() -> None:
    candles = fetch_closed_klines(
        now_ms=59_999,
        opener=lambda *_args, **_kwargs: _Response([_row(0)]),
    )
    assert candles == []


@pytest.mark.parametrize("limit", [0, 1001, True, 1.5, "10"])
def test_limit_is_strict_and_network_is_not_touched(limit: object) -> None:
    touched = False

    def opener(*_args: object, **_kwargs: object) -> _Response:
        nonlocal touched
        touched = True
        return _Response([])

    with pytest.raises(PublicKlineValidationError):
        fetch_closed_klines(limit=limit, opener=opener)  # type: ignore[arg-type]
    assert touched is False


@pytest.mark.parametrize("start", [-1, True, 1.2, "0"])
def test_start_time_is_strict_and_nonnegative(start: object) -> None:
    with pytest.raises(PublicKlineValidationError):
        fetch_closed_klines(
            start_time_ms=start,  # type: ignore[arg-type]
            opener=lambda *_args, **_kwargs: pytest.fail("network was touched"),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        ["not-a-row"],
        [[0] * 11],
        [_row(1)],
        [_row(0)[:-1] + [{}]],
        [_row(0, open_price="nan")],
        [_row(0, open_price="0")],
        [_row(0, high="1999.5")],
        [_row(0, low="2001.5")],
    ],
)
def test_malformed_shape_numbers_grid_and_ohlc_fail_closed(payload: object) -> None:
    opener = lambda *_args, **_kwargs: _Response(payload)
    with pytest.raises(PublicKlineValidationError):
        fetch_closed_klines(now_ms=1_000_000, opener=opener)


def test_invalid_utf8_and_nonfinite_json_fail_closed() -> None:
    class RawResponse(_Response):
        def __init__(self, body: bytes) -> None:
            self.body = body
            self.status = 200
            self.closed = False

    for body in (b"\xff", b"[[0, NaN]]"):
        with pytest.raises(PublicKlineValidationError):
            fetch_closed_klines(
                now_ms=1_000_000,
                opener=lambda *_args, _body=body, **_kwargs: RawResponse(_body),
            )


@pytest.mark.parametrize(
    "rows",
    [
        [_row(0), _row(0)],
        [_row(60_000), _row(0)],
        [_row(0), _row(120_000)],
    ],
)
def test_duplicate_reversal_and_gap_fail_closed(rows: list[list[object]]) -> None:
    with pytest.raises(PublicKlineValidationError):
        fetch_closed_klines(
            now_ms=1_000_000,
            opener=lambda *_args, **_kwargs: _Response(rows),
        )


def test_close_time_and_requested_start_are_validated() -> None:
    bad_close = _row(0)
    bad_close[6] = 60_000
    with pytest.raises(PublicKlineValidationError, match="close_time"):
        fetch_closed_klines(
            now_ms=1_000_000,
            opener=lambda *_args, **_kwargs: _Response([bad_close]),
        )
    with pytest.raises(PublicKlineValidationError, match="before"):
        fetch_closed_klines(
            start_time_ms=60_000,
            now_ms=1_000_000,
            opener=lambda *_args, **_kwargs: _Response([_row(0)]),
        )


def test_http_and_transport_failures_have_feed_exceptions() -> None:
    with pytest.raises(PublicKlineNetworkError):
        fetch_closed_klines(opener=lambda *_args, **_kwargs: _Response([], status=503))

    def broken(*_args: object, **_kwargs: object) -> _Response:
        raise OSError("offline")

    with pytest.raises(PublicKlineNetworkError) as caught:
        fetch_closed_klines(opener=broken)
    assert isinstance(caught.value.__cause__, OSError)


@dataclass
class _Stop:
    stopped: bool = False

    def is_set(self) -> bool:
        return self.stopped


def _candle(open_time: int) -> Candle:
    return Candle(open_time, 100.0, 101.0, 99.0, 100.5, 1.0)


def test_poller_deduplicates_overlap_and_advances_after_callback() -> None:
    stop = _Stop()
    calls: list[int] = []
    delivered: list[list[int]] = []
    requested_starts: list[int] = []
    batches = [[_candle(0), _candle(60_000)], [_candle(60_000), _candle(120_000)]]

    def fetcher(**kwargs: object) -> list[Candle]:
        requested_starts.append(kwargs["start_time_ms"])  # type: ignore[arg-type]
        return batches.pop(0)

    def callback(candles: list[Candle]) -> None:
        calls.append(len(delivered))
        delivered.append([candle.open_time for candle in candles])
        if len(delivered) == 2:
            stop.stopped = True

    run_public_kline_poller(
        0,
        stop,
        callback,
        fetcher=fetcher,
        sleeper=lambda _seconds: None,
        clock=lambda: 300_000,
    )

    assert calls == [0, 1]
    assert delivered == [[0, 60_000], [120_000]]
    assert requested_starts == [0, 120_000]


def test_poller_empty_batch_does_not_advance() -> None:
    stop = _Stop()
    starts: list[int] = []
    callbacks: list[list[Candle]] = []

    def fetcher(**kwargs: object) -> list[Candle]:
        starts.append(kwargs["start_time_ms"])  # type: ignore[arg-type]
        if len(starts) == 1:
            return []
        stop.stopped = True
        return []

    run_public_kline_poller(
        60_000,
        stop,
        callbacks.append,
        fetcher=fetcher,
        sleeper=lambda _seconds: None,
        clock=lambda: 300_000,
    )
    assert starts == [60_000, 60_000]
    assert callbacks == []


def test_poller_fetch_failure_never_calls_callback_and_is_visible() -> None:
    callbacks: list[list[Candle]] = []

    def fetcher(**_kwargs: object) -> list[Candle]:
        raise PublicKlineValidationError("bad remote payload")

    with pytest.raises(PublicKlineValidationError, match="bad remote payload"):
        run_public_kline_poller(
            0,
            _Stop(),
            callbacks.append,
            fetcher=fetcher,
            sleeper=lambda _seconds: None,
            clock=lambda: 300_000,
        )
    assert callbacks == []


def test_poller_rejects_missing_or_still_open_minutes_before_callback() -> None:
    callbacks: list[list[Candle]] = []
    for batch, now in (([_candle(60_000)], 300_000), ([_candle(0)], 59_999)):
        with pytest.raises(PublicKlinePollerError):
            run_public_kline_poller(
                0,
                _Stop(),
                callbacks.append,
                fetcher=lambda **_kwargs: batch,
                sleeper=lambda _seconds: None,
                clock=lambda _now=now: _now,
            )
    assert callbacks == []


def test_poller_rejects_malformed_injected_candle_as_own_exception() -> None:
    callbacks: list[list[Candle]] = []
    malformed = Candle(0, "100", 101.0, 99.0, 100.5, 1.0)  # type: ignore[arg-type]
    with pytest.raises(PublicKlinePollerError, match="OHLC"):
        run_public_kline_poller(
            0,
            _Stop(),
            callbacks.append,
            fetcher=lambda **_kwargs: [malformed],
            sleeper=lambda _seconds: None,
            clock=lambda: 120_000,
        )
    assert callbacks == []


def test_poller_does_not_advance_when_callback_rejects_batch() -> None:
    starts: list[int] = []

    def fetcher(**kwargs: object) -> list[Candle]:
        starts.append(kwargs["start_time_ms"])  # type: ignore[arg-type]
        return [_candle(0)]

    def reject(_candles: list[Candle]) -> None:
        raise RuntimeError("storage unavailable")

    with pytest.raises(PublicKlinePollerError, match="callback"):
        run_public_kline_poller(
            0,
            _Stop(),
            reject,
            fetcher=fetcher,
            sleeper=lambda _seconds: None,
            clock=lambda: 120_000,
        )
    assert starts == [0]


def test_source_contains_only_the_read_only_public_resource() -> None:
    source = Path(inspect.getsourcefile(public_feed) or "").read_text(encoding="utf-8").lower()
    forbidden_markers = (
        'method="post"',
        "/api/v3/order",
        "x-mbx-apikey",
        "signature=",
        "secret",
        "listenkey",
    )
    assert all(marker not in source for marker in forbidden_markers)
    assert source.count("https://") == 1
    assert "https://data-api.binance.vision/api/v3/klines" in source
