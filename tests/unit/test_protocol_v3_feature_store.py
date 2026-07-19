from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
from ethusdc_bot.protocol_v3 import feature_store, feature_store_api

REPO_ROOT = Path(__file__).resolve().parents[2]
_MATRIX_PATH = Path(__file__).with_name("test_protocol_v3_candidate_matrix.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task19_support", _MATRIX_PATH)
assert _SPEC is not None and _SPEC.loader is not None
matrix_support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(matrix_support)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(reporting_module, "_utc_now", lambda: datetime(2026, 7, 16, tzinfo=UTC))
    return matrix_support.support.build_state(tmp_path, monkeypatch)


def _context(start: datetime, minutes: int) -> AlignedMarketCandles:
    rows = []
    for index in range(minutes):
        base = 100.0 + index * 0.001 + math.sin(index / 17.0) * 0.02
        rows.append(Candle(
            open_time=int((start + timedelta(minutes=index)).timestamp() * 1000),
            open=base,
            high=base + 0.08,
            low=base - 0.06,
            close=base + 0.01,
            volume=10.0 + index % 11,
        ))
    series = tuple(rows)
    return AlignedMarketCandles(series, series, series)


def _fake_binding(context: AlignedMarketCandles):
    identity = {"fixture": "task19", "candle_count": context.candle_count}
    digest = feature_store._digest(identity)
    return SimpleNamespace(
        context=context,
        context_identity_sha256=digest,
        first_open_time_ms=context.ethusdc[0].open_time,
        common_watermark_open_time_ms=context.ethusdc[-1].open_time,
        identity_payload=lambda: identity,
    )


def _bar(start: int, end: int, index: int, previous_close: float | None):
    open_value = 100.0 + index
    close_value = open_value + 0.25
    high, low = close_value + 0.5, open_value - 0.5
    volume = 1000.0 + index
    span = high - low
    return {
        "open_time_ms": start,
        "close_time_exclusive_ms": end,
        "source_minute_count": (end - start) // 60_000,
        "open": open_value,
        "high": high,
        "low": low,
        "close": close_value,
        "volume": volume,
        "features": {
            "return_1": None if previous_close is None else close_value / previous_close - 1.0,
            "range_bps": span / open_value * 10_000.0,
            "body_bps": (close_value - open_value) / open_value * 10_000.0,
            "close_location": (close_value - low) / span,
            "volume": volume,
        },
    }


def _synthetic_store(fold_identity):
    plan = fold_identity["plan"]
    fold = plan["folds"][0]
    fit_start = feature_store._utc_ms(fold["fit_start_inclusive_utc"], "fit_start")
    fit_end = feature_store._utc_ms(fold["fit_end_exclusive_utc"], "fit_end")
    series = {}
    for symbol in feature_store.MARKETS:
        series[symbol] = {}
        for timeframe, kind, minutes in feature_store.TIMEFRAMES:
            cursor = fit_start
            rows = []
            while len(rows) < 4:
                start, end = feature_store._bucket_bounds(cursor, kind, minutes)
                if start < fit_start:
                    cursor = end
                    continue
                previous = rows[-1]["close"] if rows else None
                rows.append(_bar(start, end, len(rows) + 1, previous))
                cursor = end
            series[symbol][timeframe] = rows
    context_identity = {"fixture": "fold_fit"}
    basis = {
        "schema_version": feature_store.STORE_SCHEMA_VERSION,
        "protocol_version": feature_store.PROTOCOL_VERSION,
        "contract_version": feature_store.CONTRACT_VERSION,
        "context_identity": context_identity,
        "context_identity_sha256": feature_store._digest(context_identity),
        "source_first_open_time_ms": fit_start - 60_000,
        "source_last_open_time_ms": fit_end,
        "common_context_timestamp_ms": fit_end + 60_000,
        "timeframes": [row[0] for row in feature_store.TIMEFRAMES],
        "feature_fields": list(feature_store.FEATURES),
        "series": series,
        "safety": feature_store._SAFETY,
    }
    return feature_store.validate_feature_store({**basis, "store_sha256": feature_store._digest(basis)})


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = feature_store.load_feature_store_contract(REPO_ROOT)
    assert contract["contract_version"] == feature_store.CONTRACT_VERSION
    assert [row["id"] for row in contract["timeframes"]] == [row[0] for row in feature_store.TIMEFRAMES]
    assert contract["feature_policy"]["opportunity_and_regime_classification_deferred_to_task20"] is True
    assert feature_store_api.__all__ == feature_store.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert feature_store.CONTRACT_VERSION in pipeline["component_contracts"]["feature_contract"]
    for path in (
        "configs/protocol_v3_feature_store_contract.json",
        "src/ethusdc_bot/protocol_v3/feature_store.py",
        "src/ethusdc_bot/protocol_v3/feature_store_api.py",
    ):
        assert path in pipeline["source_bindings"]["feature_contract"]


def test_real_task10_binding_builds_and_replays_exactly(state) -> None:
    store = feature_store.build_feature_store(state["binding"])
    assert store.to_dict()["context_identity_sha256"] == state["binding"].context_identity_sha256
    assert feature_store.validate_feature_store_against_binding(store, state["binding"]).to_dict() == store.to_dict()


def test_semantically_valid_rehashed_source_change_fails_bound_replay(state) -> None:
    store = feature_store.build_feature_store(state["binding"])
    changed = deepcopy(store.to_dict())
    bar = changed["series"]["ETHUSDC"]["5m"][0]
    bar["volume"] += 1.0
    bar["features"]["volume"] += 1.0
    basis = dict(changed)
    basis.pop("store_sha256")
    changed["store_sha256"] = feature_store._digest(basis)
    feature_store.validate_feature_store(changed)
    with pytest.raises(feature_store.FeatureStoreError, match="replay"):
        feature_store.validate_feature_store_against_binding(changed, state["binding"])


def test_only_complete_fixed_weekly_and_monthly_bars_are_visible(monkeypatch) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)  # Monday and month boundary.
    context = _context(start, 31 * 1440 + 4)
    monkeypatch.setattr(feature_store, "validate_context_parity_binding", lambda value: None)
    store = feature_store.build_feature_store(_fake_binding(context))
    payload = store.to_dict()
    assert len(payload["series"]["ETHUSDC"]["5m"]) == (31 * 1440) // 5
    assert len(payload["series"]["ETHUSDC"]["1w"]) == 4
    assert len(payload["series"]["ETHUSDC"]["1mo"]) == 1
    assert payload["series"]["ETHUSDC"]["1mo"][0]["close_time_exclusive_ms"] == int(datetime(2024, 2, 1, tzinfo=UTC).timestamp() * 1000)
    assert all(row["close_time_exclusive_ms"] <= payload["common_context_timestamp_ms"] for market in payload["series"].values() for rows in market.values() for row in rows)


def test_prefix_replay_is_identical_and_future_snapshot_blocks(monkeypatch) -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    context = _context(start, 65)
    monkeypatch.setattr(feature_store, "validate_context_parity_binding", lambda value: None)
    full = feature_store.build_feature_store(_fake_binding(context))
    prefix_context = AlignedMarketCandles(context.ethusdc[:60], context.btcusdc[:60], context.ethbtc[:60])
    prefix = feature_store.build_feature_store(_fake_binding(prefix_context))
    assert full.to_dict()["series"]["ETHUSDC"]["15m"][:4] == prefix.to_dict()["series"]["ETHUSDC"]["15m"]
    snapshot = feature_store.feature_snapshot_at(full, context_timestamp_ms=int((start + timedelta(minutes=60)).timestamp() * 1000))
    assert snapshot["series"]["ETHUSDC"]["15m"]["close_time_exclusive_ms"] <= snapshot["context_timestamp_ms"]
    with pytest.raises(feature_store.FeatureStoreError, match="future"):
        feature_store.feature_snapshot_at(full, context_timestamp_ms=full.to_dict()["common_context_timestamp_ms"] + 60_000)


def test_fold_fit_excludes_warmup_and_is_hash_replayable(state, monkeypatch) -> None:
    fold_identity = state["inner_fold_plan"].identity_payload
    store = _synthetic_store(fold_identity)
    monkeypatch.setattr(feature_store, "validate_feature_store_against_binding", lambda value, binding: feature_store.validate_feature_store(value))
    fitted = feature_store.fit_fold_feature_state(store, binding=state["binding"], fold_identity=fold_identity, fold_index=1)
    payload = fitted.to_dict()
    assert payload["warmup_excluded"] is True
    stats = payload["statistics"]["ETHUSDC"]["5m"]["volume"]
    assert stats["count"] == 4
    assert stats["mean"] == pytest.approx(1002.5)
    assert stats["quantiles"] == {"0.25": 1001.75, "0.5": 1002.5, "0.75": 1003.25}
    assert feature_store.validate_fold_feature_state(payload, store=store, binding=state["binding"]).to_dict() == payload
    assert feature_store.normalize_feature(fitted, store=store, binding=state["binding"], symbol="ETHUSDC", timeframe="5m", feature="volume", value=stats["mean"]) == 0.0


def test_tampered_rehashed_feature_and_fold_boundary_are_rejected(state, monkeypatch) -> None:
    fold_identity = state["inner_fold_plan"].identity_payload
    store = _synthetic_store(fold_identity)
    monkeypatch.setattr(feature_store, "validate_feature_store_against_binding", lambda value, binding: feature_store.validate_feature_store(value))
    bad = deepcopy(store.to_dict())
    bad["series"]["ETHUSDC"]["5m"][1]["features"]["range_bps"] += 1.0
    basis = dict(bad); basis.pop("store_sha256")
    bad["store_sha256"] = feature_store._digest(basis)
    with pytest.raises(feature_store.FeatureStoreError, match="recomputation"):
        feature_store.validate_feature_store(bad)

    fitted = feature_store.fit_fold_feature_state(store, binding=state["binding"], fold_identity=fold_identity, fold_index=1).to_dict()
    fitted["fit_end_exclusive_utc"] = fitted["fit_start_inclusive_utc"]
    basis = dict(fitted); basis.pop("state_sha256")
    fitted["state_sha256"] = feature_store._digest(basis)
    with pytest.raises(feature_store.FeatureStoreError, match="boundary"):
        feature_store.validate_fold_feature_state(fitted, store=store, binding=state["binding"])
