from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
import math
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import feature_store, opportunity_regime, opportunity_regime_api

REPO_ROOT = Path(__file__).resolve().parents[2]
_FEATURE_PATH = Path(__file__).with_name("test_protocol_v3_feature_store.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task20_feature_support", _FEATURE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
feature_support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(feature_support)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module
    monkeypatch.setattr(reporting_module, "_utc_now", lambda: datetime(2026, 7, 16, tzinfo=UTC))
    return feature_support.matrix_support.support.build_state(tmp_path, monkeypatch)


def _row(start: int, end: int, index: int, previous: float | None, phase: float):
    open_value = 100.0 + index * 0.03 + math.sin(index / 9.0 + phase)
    close_value = open_value + 0.2 * math.sin(index / 5.0 + phase)
    high, low = max(open_value, close_value) + 0.4, min(open_value, close_value) - 0.4
    volume = 1000.0 + 20.0 * math.cos(index / 7.0 + phase)
    span = high - low
    return {"open_time_ms": start, "close_time_exclusive_ms": end, "source_minute_count": (end - start) // 60_000, "open": open_value, "high": high, "low": low, "close": close_value, "volume": volume, "features": {"return_1": None if previous is None else close_value / previous - 1.0, "range_bps": span / open_value * 10_000.0, "body_bps": (close_value - open_value) / open_value * 10_000.0, "close_location": (close_value - low) / span, "volume": volume}}


def _store(fold_identity):
    fold = fold_identity["plan"]["folds"][0]
    fit_start = feature_store._utc_ms(fold["fit_start_inclusive_utc"], "fit_start")
    fit_end = feature_store._utc_ms(fold["fit_end_exclusive_utc"], "fit_end")
    counts = {"5m": 4, "15m": 4, "30m": 4, "1h": 3000, "4h": 740, "1d": 120, "1w": 12, "1mo": 6}
    series = {}
    for market_index, symbol in enumerate(feature_store.MARKETS):
        series[symbol] = {}
        for timeframe, kind, minutes in feature_store.TIMEFRAMES:
            cursor = fit_start
            rows = []
            while len(rows) < counts[timeframe]:
                start, end = feature_store._bucket_bounds(cursor, kind, minutes)
                if start < fit_start:
                    cursor = end
                    continue
                if end > fit_end:
                    break
                previous = rows[-1]["close"] if rows else None
                rows.append(_row(start, end, len(rows) + 1, previous, market_index * 0.7))
                cursor = end
            series[symbol][timeframe] = rows
    identity = {"fixture": "task20"}
    basis = {"schema_version": feature_store.STORE_SCHEMA_VERSION, "protocol_version": feature_store.PROTOCOL_VERSION, "contract_version": feature_store.CONTRACT_VERSION, "context_identity": identity, "context_identity_sha256": feature_store._digest(identity), "source_first_open_time_ms": fit_start - 60_000, "source_last_open_time_ms": fit_end - 60_000, "common_context_timestamp_ms": fit_end, "timeframes": [row[0] for row in feature_store.TIMEFRAMES], "feature_fields": list(feature_store.FEATURES), "series": series, "safety": feature_store._SAFETY}
    return feature_store.validate_feature_store({**basis, "store_sha256": feature_store._digest(basis)})


def _states(state, monkeypatch):
    fold_identity = state["inner_fold_plan"].identity_payload
    store = _store(fold_identity)
    monkeypatch.setattr(feature_store, "validate_feature_store_against_binding", lambda value, binding: feature_store.validate_feature_store(value))
    monkeypatch.setattr(opportunity_regime, "validate_feature_store_against_binding", lambda value, binding: feature_store.validate_feature_store(value))
    feature_state = feature_store.fit_fold_feature_state(store, binding=state["binding"], fold_identity=fold_identity, fold_index=1)
    regime_state = opportunity_regime.fit_opportunity_regime_state(store, binding=state["binding"], feature_fit_state=feature_state, fold_identity=fold_identity, fold_index=1)
    return fold_identity, store, feature_state, regime_state


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = opportunity_regime.load_opportunity_regime_contract(REPO_ROOT)
    assert contract["contract_version"] == opportunity_regime.CONTRACT_VERSION
    assert contract["classification_policy"]["unknown_requires"] == opportunity_regime.NO_TRADE
    assert contract["classification_policy"]["may_select_specialist"] is False
    assert opportunity_regime_api.__all__ == opportunity_regime.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert opportunity_regime.CONTRACT_VERSION in pipeline["component_contracts"]["feature_contract"]
    for path in ("configs/protocol_v3_opportunity_regime_contract.json", "src/ethusdc_bot/protocol_v3/opportunity_regime.py", "src/ethusdc_bot/protocol_v3/opportunity_regime_api.py"):
        assert path in pipeline["source_bindings"]["feature_contract"]


def test_fit_is_training_only_hash_bound_and_replayable(state, monkeypatch) -> None:
    _, store, feature_state, regime_state = _states(state, monkeypatch)
    payload = regime_state.to_dict()
    assert payload["metric_row_count"] >= 60
    assert set(payload["thresholds"]) == set(opportunity_regime.METRICS)
    assert payload["warmup_excluded"] is True
    assert opportunity_regime.validate_opportunity_regime_fit_state(payload, store=store, binding=state["binding"], feature_fit_state=feature_state).to_dict() == payload


def test_assessment_is_causal_and_never_selects_a_strategy(state, monkeypatch) -> None:
    _, store, feature_state, regime_state = _states(state, monkeypatch)
    timestamp = feature_store._utc_ms(regime_state.to_dict()["fit_end_exclusive_utc"], "fit_end")
    assessment = opportunity_regime.assess_opportunity_regime(store, binding=state["binding"], feature_fit_state=feature_state, regime_fit_state=regime_state, context_timestamp_ms=timestamp)
    payload = assessment.to_dict()
    assert payload["legacy_regime"] in opportunity_regime.LEGACY_REGIMES
    assert payload["required_action"] in {opportunity_regime.NO_TRADE, opportunity_regime.ROUTER_MAY_EVALUATE_LOCAL_EDGE}
    assert payload["safety"]["may_select_strategy"] is False
    assert payload["eligible_family_hint"] is None or isinstance(payload["eligible_family_hint"], str)
    assert opportunity_regime.validate_opportunity_regime_assessment(payload, store=store, binding=state["binding"], feature_fit_state=feature_state, regime_fit_state=regime_state).to_dict() == payload


def test_unknown_or_contradictory_classification_is_fail_closed() -> None:
    metrics = {metric: 0.0 for metric in opportunity_regime.METRICS}
    thresholds = {metric: {"0.1": -1.0, "0.25": -1.0, "0.5": 0.0, "0.75": 1.0, "0.9": 1.0} for metric in opportunity_regime.METRICS}
    unknown = opportunity_regime._classify(metrics, thresholds)
    assert unknown["structure"] == "UNKNOWN"
    assert unknown["required_action"] == opportunity_regime.NO_TRADE
    assert unknown["routing_allowed"] is False
    assert unknown["eligible_family_hint"] is None

    conflicting = dict(metrics)
    conflicting.update({"trend_return": 2.0, "btc_context_return": -0.5, "ethbtc_context_return": -0.5})
    contradictory = opportunity_regime._classify(conflicting, thresholds)
    assert contradictory["contradictory_context"] is True
    assert contradictory["required_action"] == opportunity_regime.NO_TRADE


def test_trend_compression_range_and_stress_states_are_distinct() -> None:
    thresholds = {metric: {"0.1": 0.0, "0.25": 0.25, "0.5": 0.5, "0.75": 0.75, "0.9": 1.0} for metric in opportunity_regime.METRICS}
    base = {metric: 0.5 for metric in opportunity_regime.METRICS}
    base.update({"btc_context_return": 0.5, "ethbtc_context_return": 0.5})

    trend = opportunity_regime._classify({**base, "trend_return": 1.0, "trend_efficiency": 1.0}, thresholds)
    compressed = opportunity_regime._classify({**base, "compression_ratio": 0.1}, thresholds)
    ranged = opportunity_regime._classify({**base, "trend_return": 0.1, "trend_efficiency": 0.1}, thresholds)
    stress = opportunity_regime._classify({**base, "btc_context_return": -0.1}, thresholds)

    assert trend["structure"] == "TREND" and trend["routing_allowed"] is True
    assert compressed["structure"] == "COMPRESSION" and compressed["routing_allowed"] is True
    assert ranged["structure"] == "RANGE" and ranged["routing_allowed"] is True
    assert stress["structure"] == "STRESS" and stress["required_action"] == opportunity_regime.NO_TRADE


def test_rehashed_threshold_and_future_timestamp_tampering_block(state, monkeypatch) -> None:
    _, store, feature_state, regime_state = _states(state, monkeypatch)
    bad = deepcopy(regime_state.to_dict())
    bad["thresholds"]["trend_efficiency"]["0.75"] += 0.1
    basis = dict(bad); basis.pop("state_sha256")
    bad["state_sha256"] = opportunity_regime._digest(basis)
    with pytest.raises(opportunity_regime.OpportunityRegimeError, match="training-only replay"):
        opportunity_regime.validate_opportunity_regime_fit_state(bad, store=store, binding=state["binding"], feature_fit_state=feature_state)
    with pytest.raises(Exception):
        opportunity_regime.assess_opportunity_regime(store, binding=state["binding"], feature_fit_state=feature_state, regime_fit_state=regime_state, context_timestamp_ms=store.to_dict()["common_context_timestamp_ms"] + 60_000)
