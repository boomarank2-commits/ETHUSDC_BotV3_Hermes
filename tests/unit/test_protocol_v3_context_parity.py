"""Protocol v3 Task-10 tests for closed-bar three-market parity."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path

import pytest

import ethusdc_bot.protocol_v3.data_snapshot as snapshot_module
from ethusdc_bot.backtest.context_features import ContextVetoPolicy
from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3.context_parity import (
    CONTEXT_PATHS,
    ContextParityError,
    assert_context_identity_compatible,
    build_context_parity_binding,
    evaluate_closed_bar_context,
    load_context_parity_contract,
    simulate_protocol_v3_context_path,
    validate_context_parity_contract,
)
from ethusdc_bot.protocol_v3.data_snapshot import (
    MarketDayAudit,
    build_three_market_data_snapshot,
)
from ethusdc_bot.protocol_v3.run_identity import build_exchange_info_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKETS = ("ETHUSDC", "BTCUSDC", "ETHBTC")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fake_audit(symbol: str, day: date) -> MarketDayAudit:
    start_ms = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    return MarketDayAudit(
        symbol=symbol,
        day=day,
        candle_count=1440,
        first_open_time_ms=start_ms,
        last_open_time_ms=start_ms + 1439 * 60_000,
        zero_volume_candles=0,
        timestamp_grid_sha256=_digest(f"grid:{day.isoformat()}"),
        content_sha256=_digest(f"content:{symbol}:{day.isoformat()}"),
        zip_sha256=_digest(f"zip:{symbol}:{day.isoformat()}"),
        checksum_sha256=_digest(f"checksum:{symbol}:{day.isoformat()}"),
    )


class _FakeInspector:
    latest_day = date(2025, 3, 7)
    first_day = latest_day - timedelta(days=1200)

    def __init__(self, raw_root: Path) -> None:
        self.raw_root = raw_root

    def files_by_day(self, symbol: str) -> dict[date, Path]:
        result: dict[date, Path] = {}
        current = self.first_day
        while current <= self.latest_day:
            result[current] = Path(f"/{symbol}-1m-{current.isoformat()}.zip")
            current += timedelta(days=1)
        return result

    def audit_day(self, symbol: str, day: date, zip_path: Path) -> MarketDayAudit:
        return _fake_audit(symbol, day)


def _snapshot(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(snapshot_module, "_ZipMarketInspector", _FakeInspector)
    return build_three_market_data_snapshot(
        Path("/external/protocol-v3-data"),
        [
            {"name": "eth", "market": "ETHUSDC", "bars": 3, "bar_seconds": 60},
            {"name": "btc", "market": "BTCUSDC", "bars": 3, "bar_seconds": 60},
            {"name": "ratio", "market": "ETHBTC", "bars": 3, "bar_seconds": 60},
        ],
        repo_root=REPO_ROOT,
    )


def _exchange_snapshot():
    return build_exchange_info_snapshot(
        {
            "symbols": [
                {
                    "symbol": "ETHUSDC",
                    "status": "TRADING",
                    "baseAsset": "ETH",
                    "quoteAsset": "USDC",
                    "isSpotTradingAllowed": True,
                    "filters": [
                        {
                            "filterType": "PRICE_FILTER",
                            "minPrice": "0.01",
                            "maxPrice": "1000000",
                            "tickSize": "0.01",
                        },
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.0001",
                            "maxQty": "9000",
                            "stepSize": "0.0001",
                        },
                        {
                            "filterType": "MARKET_LOT_SIZE",
                            "minQty": "0.0001",
                            "maxQty": "1200",
                            "stepSize": "0.0001",
                        },
                        {
                            "filterType": "MIN_NOTIONAL",
                            "minNotional": "5",
                            "applyToMarket": True,
                            "avgPriceMins": 5,
                        },
                    ],
                }
            ]
        },
        snapshot_as_of_utc="2026-07-07T23:59:59Z",
    )


def _series(
    closes: list[float],
    *,
    start: int = int(datetime(2025, 3, 1, tzinfo=UTC).timestamp() * 1000),
) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            open_time=start + index * 60_000,
            open=close,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=10.0,
        )
        for index, close in enumerate(closes)
    )


def _context(
    *,
    btc: list[float] | None = None,
    ratio: list[float] | None = None,
) -> AlignedMarketCandles:
    return AlignedMarketCandles(
        ethusdc=_series([100, 100.1, 100.2, 100.3, 100.4, 100.5, 100.6, 100.7]),
        btcusdc=_series(btc or [100, 100.1, 100.2, 100.3, 100.4, 100.5, 100.6, 100.7]),
        ethbtc=_series(ratio or [1, 1.001, 1.002, 1.003, 1.004, 1.005, 1.006, 1.007]),
    )


def _policy(**changes: object) -> ContextVetoPolicy:
    values: dict[str, object] = {
        "btc_trend_lookback": 3,
        "btc_min_trend_bps": -20,
        "btc_volatility_lookback": 3,
        "btc_max_volatility_bps": 100,
        "ethbtc_trend_lookback": 3,
        "ethbtc_min_trend_bps": -20,
    }
    values.update(changes)
    return ContextVetoPolicy(**values)  # type: ignore[arg-type]


def _strategy(**changes: float | int | str) -> StrategyCandidate:
    params: dict[str, float | int | str] = {
        "side": "LONG",
        "symbol": "ETHUSDC",
        "stop_loss_bps": 500,
        "take_profit_bps": 500,
        "trailing_stop_bps": 0,
        "break_even_after_bps": 0,
        "max_hold_minutes": 10,
        "cooldown_minutes": 10,
    }
    params.update(changes)
    return StrategyCandidate("always_long", params)


def test_contract_is_exact_and_context_markets_can_never_trade() -> None:
    contract = load_context_parity_contract(REPO_ROOT)
    assert contract["paths"] == list(CONTEXT_PATHS)
    assert contract["markets"][0]["may_trigger_trade"] is True
    assert contract["markets"][1]["may_trigger_trade"] is False
    assert contract["markets"][2]["may_trigger_trade"] is False
    assert contract["time_policy"]["missing_context"] == "block"
    assert contract["time_policy"]["stale_context"] == "block"
    changed = json.loads(json.dumps(contract))
    changed["markets"][1]["may_trigger_trade"] = True
    with pytest.raises(ContextParityError, match="not canonical"):
        validate_context_parity_contract(changed)


def test_binding_is_snapshot_bound_and_content_addressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = build_context_parity_binding(
        _context(), _policy(), _snapshot(monkeypatch), repo_root=REPO_ROOT
    )
    assert binding.candle_count == 8
    assert binding.first_open_time_ms == binding.context.ethusdc[0].open_time
    assert binding.common_watermark_open_time_ms == binding.context.ethusdc[-1].open_time
    assert len(binding.context_identity_sha256) == 64
    assert binding.cache_key == binding.resume_key
    assert dict(binding.window_market_content_sha256).keys() == set(MARKETS)


def test_closed_bar_time_is_exact_and_stale_or_future_context_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = build_context_parity_binding(
        _context(), _policy(), _snapshot(monkeypatch), repo_root=REPO_ROOT
    )
    close_time = binding.context.ethusdc[5].open_time + 59_999
    assert evaluate_closed_bar_context(
        binding, 5, decision_time_ms=close_time
    ).allowed is True
    with pytest.raises(ContextParityError, match="unclosed"):
        evaluate_closed_bar_context(binding, 5, decision_time_ms=close_time - 1)
    with pytest.raises(ContextParityError, match="stale"):
        evaluate_closed_bar_context(binding, 5, decision_time_ms=close_time + 1)


def test_missing_misaligned_or_gapped_context_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot(monkeypatch)
    good = _context()
    shifted = list(good.btcusdc)
    shifted[4] = replace(shifted[4], open_time=shifted[4].open_time + 60_000)
    with pytest.raises(ContextParityError, match="timestamps differ|misaligned"):
        build_context_parity_binding(
            AlignedMarketCandles(good.ethusdc, tuple(shifted), good.ethbtc),
            _policy(),
            snapshot,
            repo_root=REPO_ROOT,
        )
    with pytest.raises(ContextParityError, match="equal length|timestamps differ"):
        build_context_parity_binding(
            AlignedMarketCandles(good.ethusdc, good.btcusdc[:-1], good.ethbtc),
            _policy(),
            snapshot,
            repo_root=REPO_ROOT,
        )


def test_context_only_vetoes_an_existing_ethusdc_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(btc=[100, 99.9, 99.8, 99.7, 99.6, 99.5, 99.4, 99.3])
    binding = build_context_parity_binding(
        context,
        _policy(btc_min_trend_bps=-5),
        _snapshot(monkeypatch),
        repo_root=REPO_ROOT,
    )
    result = simulate_protocol_v3_context_path(
        "research",
        binding,
        list(context.ethusdc),
        _strategy(),
        days=1,
        exchange_info_snapshot=_exchange_snapshot(),
    )
    assert result.trade_count == 0
    assert result.signal_funnel["raw_entry_signals"] > 0
    assert result.rejection_reasons["context_veto_btc_trend"] > 0


def test_all_paths_are_bit_identical_and_use_one_execution_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    binding = build_context_parity_binding(
        context, _policy(), _snapshot(monkeypatch), repo_root=REPO_ROOT
    )
    rows = []
    for path in CONTEXT_PATHS:
        result = simulate_protocol_v3_context_path(
            path,
            binding,
            list(context.ethusdc),
            _strategy(),
            days=1,
            exchange_info_snapshot=_exchange_snapshot(),
        )
        rows.append(
            {
                "trades": [asdict(trade) for trade in result.trades],
                "metrics": asdict(result.metrics),
                "funnel": dict(result.signal_funnel),
                "rejections": dict(result.rejection_reasons),
            }
        )
    assert rows[1:] == rows[:-1]


def test_context_identity_change_blocks_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot(monkeypatch)
    first = build_context_parity_binding(
        _context(), _policy(), snapshot, repo_root=REPO_ROOT
    )
    second = build_context_parity_binding(
        _context(ratio=[1, 1.001, 1.002, 1.003, 1.004, 1.005, 1.006, 1.5]),
        _policy(),
        snapshot,
        repo_root=REPO_ROOT,
    )
    assert first.context_identity_sha256 != second.context_identity_sha256
    with pytest.raises(ContextParityError, match="mismatch"):
        assert_context_identity_compatible(first, second)


def test_context_market_candidate_cannot_enter_trade_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    binding = build_context_parity_binding(
        context, _policy(), _snapshot(monkeypatch), repo_root=REPO_ROOT
    )
    with pytest.raises(ContextParityError, match="only ETHUSDC"):
        simulate_protocol_v3_context_path(
            "replay",
            binding,
            list(context.ethusdc),
            _strategy(symbol="BTCUSDC"),
            days=1,
            exchange_info_snapshot=_exchange_snapshot(),
        )


def test_snapshot_tampering_and_unknown_path_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot(monkeypatch).to_dict()
    snapshot["availability"]["latest_common_complete_day"] = "2025-03-08"
    with pytest.raises(ContextParityError, match="snapshot"):
        build_context_parity_binding(
            _context(), _policy(), snapshot, repo_root=REPO_ROOT
        )

    valid = build_context_parity_binding(
        _context(), _policy(), _snapshot(monkeypatch), repo_root=REPO_ROOT
    )
    with pytest.raises(ContextParityError, match="context path"):
        simulate_protocol_v3_context_path(
            "paper",
            valid,
            list(valid.context.ethusdc),
            _strategy(),
            days=1,
            exchange_info_snapshot=_exchange_snapshot(),
        )
