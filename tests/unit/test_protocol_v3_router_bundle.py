from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3 import feature_store, inner_selection, opportunity_regime
from ethusdc_bot.protocol_v3 import router_bundle, router_bundle_api

REPO_ROOT = Path(__file__).resolve().parents[2]
_SELECTION_PATH = Path(__file__).with_name("test_protocol_v3_inner_selection.py")
_OPPORTUNITY_PATH = Path(__file__).with_name("test_protocol_v3_opportunity_regime.py")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


selection_support = _load("protocol_v3_task22_selection_support", _SELECTION_PATH)
opportunity_support = _load("protocol_v3_task22_opportunity_support", _OPPORTUNITY_PATH)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(reporting_module, "_utc_now", lambda: datetime(2026, 7, 16, tzinfo=UTC))
    base = selection_support.support.build_state(tmp_path, monkeypatch)

    # The Task-20 fixture uses a compact synthetic store; preserve exact replay while
    # replacing only the expensive Task-10 source reconstruction in this unit fixture.
    _, store, feature_state, regime_state = opportunity_support._states(base, monkeypatch)
    monkeypatch.setattr(router_bundle, "validate_feature_store_against_binding", lambda value, binding: feature_store.validate_feature_store(value))

    original_classify = opportunity_regime._classify

    def trend_classify(metrics, thresholds):
        result = original_classify(metrics, thresholds)
        result.update({
            "state": opportunity_regime.COMPLETE,
            "reason": "causal_trend_structure",
            "opportunity": "HIGH",
            "structure": "TREND",
            "stress": False,
            "contradictory_context": False,
            "eligible_family_hint": "trend_pullback_or_multiday_swing",
            "required_action": opportunity_regime.ROUTER_MAY_EVALUATE_LOCAL_EDGE,
            "routing_allowed": True,
        })
        return result

    monkeypatch.setattr(opportunity_regime, "_classify", trend_classify)
    timestamp = feature_store._utc_ms(regime_state.to_dict()["fit_end_exclusive_utc"], "fit_end")
    assessment = opportunity_regime.assess_opportunity_regime(
        store, binding=base["binding"], feature_fit_state=feature_state,
        regime_fit_state=regime_state, context_timestamp_ms=timestamp,
    )

    candidate = StrategyCandidate(
        "pullback_in_trend",
        {"symbol": "ETHUSDC", "side": "LONG", "max_hold_minutes": 180},
    )
    rows = selection_support._candidate_rows(base, [(candidate, [0.25] * 6, 0.2)])
    config = selection_support._synthetic_config(base, rows)
    decision = inner_selection.select_candidate(base["training_window"], config)
    assert decision.outcome == inner_selection.CANDIDATE
    return {
        **base, "store": store, "feature_state": feature_state,
        "regime_state": regime_state, "assessment": assessment, "decision": decision,
    }


def _folds(state, *, net: float = 0.1, trades_per_day: int = 1):
    result = []
    for boundary in state["inner_fold_plan"].identity_payload["plan"]["folds"]:
        start = datetime.fromisoformat(boundary["validation_start_inclusive_utc"].replace("Z", "+00:00")).date()
        rows = [
            {
                "day": (start + timedelta(days=index)).isoformat(),
                "net_usdc": net,
                "gross_profit_usdc": max(net, 0.0) + 0.1 if trades_per_day else 0.0,
                "gross_loss_usdc": 0.1 if trades_per_day else 0.0,
                "trade_count": trades_per_day,
            }
            for index in range(60)
        ]
        result.append({"fold_index": boundary["fold_index"], "fold_id": boundary["fold_id"], "daily_local_net_mtm_usdc": rows})
    return result


def _route(state, edge):
    return router_bundle.route_specialist(
        state["decision"], edge, store=state["store"], binding=state["binding"],
        feature_fit_state=state["feature_state"], regime_fit_state=state["regime_state"],
        assessment=state["assessment"],
    )


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = router_bundle.load_router_bundle_contract(REPO_ROOT)
    assert contract["contract_version"] == router_bundle.CONTRACT_VERSION
    assert contract["router_policy"]["no_trade_is_default"] is True
    assert contract["router_policy"]["max_open_lots"] == 1
    assert router_bundle_api.__all__ == router_bundle.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert router_bundle.CONTRACT_VERSION in pipeline["component_contracts"]["candidate_families"]
    for path in (
        "configs/protocol_v3_router_bundle_contract.json",
        "src/ethusdc_bot/protocol_v3/router_bundle.py",
        "src/ethusdc_bot/protocol_v3/router_bundle_api.py",
    ):
        assert path in pipeline["source_bindings"]["candidate_families"]


def test_exact_local_edge_replay_selects_one_matching_specialist(state) -> None:
    edge = router_bundle.build_local_edge_evidence(
        state["decision"], specialist_id="trend_pullback_reclaim",
        folds=_folds(state),
    )
    assert edge.to_dict()["passed"] is True
    route = _route(state, edge)
    assert route.outcome == router_bundle.SPECIALIST
    assert route.to_dict()["specialist_id"] == "trend_pullback_reclaim"
    assert route.to_dict()["max_open_lots"] == 1
    assert router_bundle.validate_router_decision(
        route, state["decision"], edge, store=state["store"], binding=state["binding"],
        feature_fit_state=state["feature_state"], regime_fit_state=state["regime_state"],
        assessment=state["assessment"],
    ) is route


def test_missing_or_failed_local_edge_is_actual_no_trade(state) -> None:
    missing = _route(state, None)
    assert missing.outcome == router_bundle.NO_TRADE
    assert missing.to_dict()["reason"] == "local_edge_evidence_missing"

    production_default = router_bundle.route_specialist(
        state["selection_decision"], None, store=state["store"], binding=state["binding"],
        feature_fit_state=state["feature_state"], regime_fit_state=state["regime_state"],
        assessment=state["assessment"],
    )
    assert production_default.outcome == router_bundle.NO_TRADE
    assert production_default.to_dict()["reason"] == "selection_is_no_trade"

    failed = router_bundle.build_local_edge_evidence(
        state["decision"], specialist_id="trend_pullback_reclaim",
        folds=_folds(state, net=0.0, trades_per_day=0),
    )
    assert failed.to_dict()["passed"] is False
    assert _route(state, failed).to_dict()["reason"] == "local_edge_gate_failed"


def test_wrong_family_grid_and_rehashed_metric_tampering_block(state) -> None:
    with pytest.raises(router_bundle.RouterBundleError, match="does not match"):
        router_bundle.build_local_edge_evidence(
            state["decision"], specialist_id="range_reversion_confirmed",
            folds=_folds(state),
        )
    broken_grid = _folds(state)
    broken_grid[0]["daily_local_net_mtm_usdc"][0]["day"] = "2000-01-01"
    with pytest.raises(router_bundle.RouterBundleError, match="daily grid"):
        router_bundle.build_local_edge_evidence(
            state["decision"], specialist_id="trend_pullback_reclaim",
            folds=broken_grid,
        )
    edge = router_bundle.build_local_edge_evidence(
        state["decision"], specialist_id="trend_pullback_reclaim",
        folds=_folds(state),
    )
    tampered = deepcopy(edge.to_dict())
    tampered["fold_net_usdc_per_day"][0] += 1.0
    basis = dict(tampered); basis.pop("evidence_sha256")
    tampered["evidence_sha256"] = router_bundle._digest(basis)
    with pytest.raises(router_bundle.RouterBundleError, match="exact replay"):
        router_bundle.validate_local_edge_evidence(tampered, selection=state["decision"])


def test_frozen_bundle_binds_full_state_cost_context_rotation_and_validity(state) -> None:
    edge = router_bundle.build_local_edge_evidence(
        state["decision"], specialist_id="trend_pullback_reclaim",
        folds=_folds(state),
    )
    route = _route(state, edge)
    bundle = router_bundle.build_frozen_candidate_bundle(
        route, state["decision"], edge, store=state["store"], binding=state["binding"],
        feature_fit_state=state["feature_state"], regime_fit_state=state["regime_state"],
        assessment=state["assessment"], as_of_utc="2026-07-08T00:00:00Z",
        valid_from_utc="2026-07-09T00:00:00Z", valid_until_utc="2026-08-08T00:00:00Z",
    )
    payload = bundle.to_dict()
    assert payload["scalar_parameters"]["max_hold_minutes"] == 180
    assert payload["feature_fit_state"]["statistics"]
    assert payload["regime_fit_state"]["thresholds"]
    assert payload["context_policy"] == state["binding"].identity_payload()
    assert payload["cost_model"] == state["decision"].to_dict()["frozen_pipeline_config"]["run_fingerprint"]["cost_model"]
    assert payload["rotation_policy"]["max_open_lots"] == 1
    assert payload["canonical_adoption_eligible"] is False
    assert payload["fixture_only"] is True
    assert payload["research_simulation_routable"] is False
    assert router_bundle.validate_frozen_candidate_bundle(
        bundle, route, state["decision"], edge, store=state["store"], binding=state["binding"],
        feature_fit_state=state["feature_state"], regime_fit_state=state["regime_state"],
        assessment=state["assessment"],
    ) is bundle
    with pytest.raises(router_bundle.RouterBundleError, match="exact dependency replay"):
        router_bundle.validate_frozen_candidate_bundle(
            replace(bundle, bundle_sha256="f" * 64), route, state["decision"], edge,
            store=state["store"], binding=state["binding"], feature_fit_state=state["feature_state"],
            regime_fit_state=state["regime_state"], assessment=state["assessment"],
        )


def test_invalid_delay_and_flat_params_cannot_claim_complete_bundle(state) -> None:
    edge = router_bundle.build_local_edge_evidence(
        state["decision"], specialist_id="trend_pullback_reclaim",
        folds=_folds(state),
    )
    route = _route(state, edge)
    kwargs = dict(
        store=state["store"], binding=state["binding"], feature_fit_state=state["feature_state"],
        regime_fit_state=state["regime_state"], assessment=state["assessment"],
        as_of_utc="2026-07-08T00:00:00Z", valid_from_utc="2026-07-08T00:00:00Z",
        valid_until_utc="2026-08-08T00:00:00Z",
    )
    with pytest.raises(router_bundle.RouterBundleError, match=r"as_of\+24h"):
        router_bundle.build_frozen_candidate_bundle(route, state["decision"], edge, **kwargs)
    assert not hasattr(StrategyCandidate("pullback_in_trend", {"max_hold_minutes": 180}), "bundle_sha256")
