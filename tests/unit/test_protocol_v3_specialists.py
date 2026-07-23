from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3 import opportunity_regime, specialists, specialists_api

REPO_ROOT = Path(__file__).resolve().parents[2]
_FEATURE_PATH = Path(__file__).with_name("test_protocol_v3_feature_store.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task21_support", _FEATURE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
feature_support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(feature_support)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module
    monkeypatch.setattr(reporting_module, "_utc_now", lambda: datetime(2026, 7, 16, tzinfo=UTC))
    return feature_support.matrix_support.support.build_state(tmp_path, monkeypatch)


def _assessment(timestamp: int, structure: str, routing_allowed: bool = True):
    basis = {"state": opportunity_regime.COMPLETE, "context_timestamp_ms": timestamp, "structure": structure, "routing_allowed": routing_allowed}
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"))
    return opportunity_regime.OpportunityRegimeAssessment(canonical, hashlib.sha256(canonical.encode()).hexdigest())


def test_contract_api_pipeline_and_existing_engine_mapping_are_exact() -> None:
    contract = specialists.load_specialists_contract(REPO_ROOT)
    assert contract["contract_version"] == specialists.CONTRACT_VERSION
    assert contract["engine_policy"]["reuse_existing_simulator"] is True
    assert contract["engine_policy"]["second_simulation_engine_forbidden"] is True
    assert specialists_api.__all__ == specialists.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert specialists.CONTRACT_VERSION in pipeline["component_contracts"]["candidate_families"]
    for path in ("configs/protocol_v3_specialists_contract.json", "src/ethusdc_bot/protocol_v3/specialists.py", "src/ethusdc_bot/protocol_v3/specialists_api.py"):
        assert path in pipeline["source_bindings"]["candidate_families"]
    assert {value[0] for value in specialists.SPECS.values()} == {"pullback_in_trend", "breakout_volatility_filter", "mean_reversion_regime_filter", "momentum_trend_filter"}


def test_bundles_preserve_exact_base_candidate_and_enforce_bounds() -> None:
    candidate = StrategyCandidate("pullback_in_trend", {"symbol": "ETHUSDC", "side": "LONG", "max_hold_minutes": 180})
    bundle = specialists.build_specialist_bundle("trend_pullback_reclaim", candidate)
    assert bundle.base_candidate is candidate
    assert bundle.to_dict()["uses_existing_simulator"] is True
    assert specialists.validate_specialist_bundle(bundle) is bundle
    with pytest.raises(specialists.SpecialistError, match="base family"):
        specialists.build_specialist_bundle("range_reversion_confirmed", candidate)
    with pytest.raises(specialists.SpecialistError, match="bounds"):
        specialists.build_specialist_bundle("trend_pullback_reclaim", StrategyCandidate("pullback_in_trend", {"max_hold_minutes": 1440}))


def test_no_trade_and_absent_raw_signal_can_never_become_allowed(state) -> None:
    store = feature_support._synthetic_store(state["inner_fold_plan"].identity_payload)
    timestamp = store.to_dict()["common_context_timestamp_ms"]
    no_trade = specialists.build_specialist_bundle(specialists.NO_TRADE, None)
    gate = specialists.evaluate_specialist_confirmation(no_trade, store, _assessment(timestamp, "UNKNOWN", False), context_timestamp_ms=timestamp, raw_signal=True)
    assert gate["allowed"] is False and gate["reason"] == "no_trade_specialist"

    candidate = StrategyCandidate("momentum_trend_filter", {"max_hold_minutes": 1440})
    swing = specialists.build_specialist_bundle("multiday_swing_trend", candidate)
    gate = specialists.evaluate_specialist_confirmation(swing, store, _assessment(timestamp, "TREND"), context_timestamp_ms=timestamp, raw_signal=False)
    assert gate["allowed"] is False
    assert gate["reason"] == "base_engine_raw_signal_absent"
    assert gate["may_create_signal"] is False


def test_multiday_confirmation_filters_but_does_not_replace_engine_signal(state) -> None:
    store = feature_support._synthetic_store(state["inner_fold_plan"].identity_payload)
    timestamp = store.to_dict()["common_context_timestamp_ms"]
    candidate = StrategyCandidate("momentum_trend_filter", {"max_hold_minutes": 1440})
    bundle = specialists.build_specialist_bundle("multiday_swing_trend", candidate)
    passed = specialists.evaluate_specialist_confirmation(bundle, store, _assessment(timestamp, "TREND"), context_timestamp_ms=timestamp, raw_signal=True)
    assert passed["allowed"] is True
    assert passed["reason"] == "specialist_confirmation_passed"
    mismatch = specialists.evaluate_specialist_confirmation(bundle, store, _assessment(timestamp, "RANGE"), context_timestamp_ms=timestamp, raw_signal=True)
    assert mismatch["allowed"] is False


def test_tampered_bundle_and_future_feature_access_block(state) -> None:
    candidate = StrategyCandidate("momentum_trend_filter", {"max_hold_minutes": 1440})
    bundle = specialists.build_specialist_bundle("multiday_swing_trend", candidate)
    broken = replace(bundle, bundle_sha256="f" * 64)
    with pytest.raises(specialists.SpecialistError, match="identity"):
        specialists.validate_specialist_bundle(broken)
    store = feature_support._synthetic_store(state["inner_fold_plan"].identity_payload)
    timestamp = store.to_dict()["common_context_timestamp_ms"]
    with pytest.raises(specialists.SpecialistError, match="future"):
        specialists.evaluate_specialist_confirmation(bundle, store, _assessment(timestamp + 60_000, "TREND"), context_timestamp_ms=timestamp + 60_000, raw_signal=True)
