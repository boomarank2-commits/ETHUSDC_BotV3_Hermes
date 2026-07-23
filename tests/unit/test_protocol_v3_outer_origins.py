from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ethusdc_bot.protocol_v3 import boundaries, inner_folds, inner_selection
from ethusdc_bot.protocol_v3 import outer_origins, outer_origins_api, router_bundle, specialists

REPO_ROOT = Path(__file__).resolve().parents[2]
_SUPPORT_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task23_support", _SUPPORT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(reporting_module, "_utc_now", lambda: datetime(2026, 7, 16, tzinfo=UTC))
    base = support.build_state(tmp_path, monkeypatch)
    plan = boundaries.build_monthly_process_boundary_plan("2026-07-08")
    requests = []
    for origin in plan.origins:
        fold_plan = inner_folds.build_inner_fold_plan_for_origin(origin, support.HORIZON, repo_root=REPO_ROOT)
        config = inner_selection.build_frozen_selection_config(
            pre_run_manifest=base["manifest"], run_fingerprint=base["fingerprint"],
            fold_identity=fold_plan.identity_payload, origin_index=origin.origin_index, cycle_index=1,
            generated_candidate_ids=[], tested_candidate_ids=[], walk_forward_candidate_ids=[],
            finalist_candidate_ids=[], candidate_evidence=[],
            development_support=inner_selection.build_incomplete_development_support("no_complete_local_edge_evidence"),
        )
        context_ms = int(datetime(origin.test_start_inclusive.year, origin.test_start_inclusive.month, origin.test_start_inclusive.day, tzinfo=UTC).timestamp() * 1000)
        store = SimpleNamespace(to_dict=lambda value=context_ms: {"common_context_timestamp_ms": value})
        assessment = SimpleNamespace(to_dict=lambda value=context_ms: {"context_timestamp_ms": value})
        feature_state = SimpleNamespace(to_dict=lambda value=fold_plan.identity_payload: {"fold_identity": value})
        regime_state = SimpleNamespace(to_dict=lambda value=fold_plan.identity_payload: {"fold_identity": value})
        requests.append(outer_origins.OuterOriginRequest(config, None, store, object(), feature_state, regime_state, assessment))

    monkeypatch.setattr(outer_origins, "route_specialist", lambda *args, **kwargs: SimpleNamespace())

    def fake_bundle(route, decision, local_edge, **kwargs):
        decision_payload = decision.to_dict()
        router_basis = {
            "schema_version": router_bundle.ROUTER_DECISION_SCHEMA_VERSION,
            "protocol_version": outer_origins.PROTOCOL_VERSION,
            "contract_version": router_bundle.CONTRACT_VERSION,
            "outcome": router_bundle.NO_TRADE, "specialist_id": specialists.NO_TRADE,
            "reason": "selection_is_no_trade", "selection_decision_sha256": decision.decision_sha256,
            "local_edge_evidence_sha256": None, "assessment_sha256": "a" * 64,
            "feature_store_sha256": "b" * 64, "feature_fit_state_sha256": "c" * 64,
            "regime_fit_state_sha256": "d" * 64, "context_identity_sha256": "e" * 64,
            "max_open_lots": 1, "may_create_direction": False,
            "fixture_only": decision_payload["fixture_only"], "transaction_eligible": False,
            "safety": outer_origins._BUNDLE_SAFETY,
        }
        router = {**router_basis, "decision_sha256": outer_origins._digest(router_basis)}
        specialist_basis = {
            "schema_version": specialists.BUNDLE_SCHEMA_VERSION, "protocol_version": outer_origins.PROTOCOL_VERSION,
            "contract_version": specialists.CONTRACT_VERSION, "specialist_id": specialists.NO_TRADE,
            "base_candidate": None, "uses_existing_simulator": True, "safety": specialists._SAFETY,
        }
        specialist = {**specialist_basis, "bundle_sha256": outer_origins._digest(specialist_basis)}
        basis = {
            "schema_version": router_bundle.FROZEN_BUNDLE_SCHEMA_VERSION, "protocol_version": outer_origins.PROTOCOL_VERSION,
            "contract_version": router_bundle.CONTRACT_VERSION, "router_decision": router,
            "specialist_bundle": specialist, "scalar_parameters": None,
            "selection_decision_sha256": decision.decision_sha256, "local_edge_evidence_sha256": None,
            "feature_store_identity": {"identity_sha256": "f" * 64},
            "feature_fit_state": {"state_sha256": "1" * 64}, "regime_fit_state": {"state_sha256": "2" * 64},
            "assessment_sha256": "a" * 64, "context_policy": {"fixture": "task23"},
            "cost_model": decision_payload["frozen_pipeline_config"]["run_fingerprint"]["cost_model"],
            "rotation_policy": {"runtime_state_task": 24}, "predecessor_bundle_sha256": None,
            "validity": {"as_of_utc": kwargs["as_of_utc"], "valid_from_utc": kwargs["valid_from_utc"], "valid_until_utc": kwargs["valid_until_utc"]},
            "fixture_only": decision_payload["fixture_only"], "research_simulation_routable": False,
            "canonical_adoption_eligible": False, "safety": outer_origins._BUNDLE_SAFETY,
        }
        return router_bundle.FrozenCandidateBundle(outer_origins._canonical(basis), outer_origins._digest(basis))

    monkeypatch.setattr(outer_origins, "build_frozen_candidate_bundle", fake_bundle)
    return base, plan, requests


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = outer_origins.load_outer_origins_contract(REPO_ROOT)
    assert contract["contract_version"] == outer_origins.CONTRACT_VERSION
    assert contract["process_policy"]["pipeline_refit_per_origin"] is True
    assert contract["isolation_policy"]["outer_result_channel_exposed_to_selection"] is False
    assert outer_origins_api.__all__ == outer_origins.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert outer_origins.CONTRACT_VERSION in pipeline["component_contracts"]["ranking"]
    for path in ("configs/protocol_v3_outer_origins_contract.json", "src/ethusdc_bot/protocol_v3/outer_origins.py", "src/ethusdc_bot/protocol_v3/outer_origins_api.py"):
        assert path in pipeline["source_bindings"]["ranking"]


def test_orchestrator_runs_exactly_twelve_refits_and_365_oos_days(state) -> None:
    _, plan, requests = state
    first = outer_origins.orchestrate_outer_origins(plan, requests)
    repeated = outer_origins.orchestrate_outer_origins(plan, requests)
    assert first.to_dict() == repeated.to_dict()
    payload = first.to_dict()
    assert payload["origin_count"] == 12
    assert len(payload["process_oos_day_grid"]) == len(set(payload["process_oos_day_grid"])) == 365
    assert [row["origin_index"] for row in payload["origins"]] == list(range(1, 13))
    assert len({row["training_end_exclusive"] for row in payload["origins"]}) == 12
    assert all(row["selection_decision"]["outcome"] == inner_selection.NO_TRADE for row in payload["origins"])
    assert all(row["frozen_candidate_bundle"]["validity"]["valid_from_utc"].endswith("00:00:00Z") for row in payload["origins"])
    assert outer_origins.validate_outer_origin_process(first, boundary_plan=plan).to_dict() == payload


def test_later_fit_may_read_prior_raw_market_but_never_outer_results(state) -> None:
    _, plan, _ = state
    spy = outer_origins.OuterIsolationSpy(plan)
    prior_oos_day = plan.origins[0].test_start_inclusive
    spy.observe_raw_market_day(origin_index=2, day=prior_oos_day)
    assert spy.raw_reads[0]["kind"] == "raw_market"
    for kind in ("pnl", "ranking", "report", "gate_result", "human_interpretation"):
        with pytest.raises(outer_origins.OuterOriginError, match="forbidden"):
            spy.observe_prior_outer_result(origin_index=2, prior_origin_index=1, kind=kind)


def test_missing_reordered_or_cross_origin_requests_fail_closed(state) -> None:
    _, plan, requests = state
    with pytest.raises(outer_origins.OuterOriginError, match="exactly twelve"):
        outer_origins.orchestrate_outer_origins(plan, requests[:-1])
    reordered = list(requests)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    with pytest.raises(outer_origins.OuterOriginError, match="another origin"):
        outer_origins.orchestrate_outer_origins(plan, reordered)
    stale = list(requests)
    stale[0] = replace(stale[0], assessment=SimpleNamespace(to_dict=lambda: {"context_timestamp_ms": 0}))
    with pytest.raises(outer_origins.OuterOriginError, match="assessment cutoff"):
        outer_origins.orchestrate_outer_origins(plan, stale)
    cross_origin_state = list(requests)
    cross_origin_state[0] = replace(cross_origin_state[0], feature_fit_state=requests[1].feature_fit_state)
    with pytest.raises(outer_origins.OuterOriginError, match="another origin fold plan"):
        outer_origins.orchestrate_outer_origins(plan, cross_origin_state)


def test_rehashed_oos_and_origin_bundle_tampering_are_rejected(state) -> None:
    _, plan, requests = state
    process = outer_origins.orchestrate_outer_origins(plan, requests)
    bad_days = deepcopy(process.to_dict())
    bad_days["process_oos_day_grid"][0] = bad_days["process_oos_day_grid"][1]
    bad_days["process_oos_day_grid_sha256"] = outer_origins._digest(bad_days["process_oos_day_grid"])
    basis = dict(bad_days); basis.pop("process_sha256")
    bad_days["process_sha256"] = outer_origins._digest(basis)
    with pytest.raises(outer_origins.OuterOriginError, match="OOS union"):
        outer_origins.validate_outer_origin_process(bad_days, boundary_plan=plan)

    bad_bundle = deepcopy(process.to_dict())
    bad_bundle["origins"][0]["frozen_candidate_bundle"]["canonical_adoption_eligible"] = True
    bundle = bad_bundle["origins"][0]["frozen_candidate_bundle"]
    bundle_basis = dict(bundle); bundle_basis.pop("bundle_sha256")
    bundle["bundle_sha256"] = outer_origins._digest(bundle_basis)
    origin = bad_bundle["origins"][0]
    origin_basis = dict(origin); origin_basis.pop("origin_sha256")
    origin["origin_sha256"] = outer_origins._digest(origin_basis)
    process_basis = dict(bad_bundle); process_basis.pop("process_sha256")
    bad_bundle["process_sha256"] = outer_origins._digest(process_basis)
    with pytest.raises(outer_origins.OuterOriginError, match="adoption lock"):
        outer_origins.validate_outer_origin_process(bad_bundle, boundary_plan=plan)
