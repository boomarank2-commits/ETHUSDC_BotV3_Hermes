"""Task-27 tests for bound hindsight capture diagnostics and bootstrap."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
import importlib.util
import inspect
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import historical_diagnostics as diagnostics
from ethusdc_bot.protocol_v3 import historical_diagnostics_api, monthly_quality_gate
from ethusdc_bot.protocol_v3 import hindsight_binding, hindsight_solvers
from ethusdc_bot.protocol_v3.execution_parity import build_market_execution_rules
from ethusdc_bot.protocol_v3.run_identity import build_exchange_info_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK26_PATH = Path(__file__).with_name("test_protocol_v3_monthly_quality_gate.py")
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task27_support", _TASK26_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
task26 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(task26)


def _exchange():
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
        repo_root=REPO_ROOT,
    )


def _bound(plan, process, baseline):
    process_payload = process.to_dict()
    ledger_payload = baseline.to_dict()
    exchange = _exchange().to_dict()
    rules = build_market_execution_rules(exchange)
    zero_daily = [
        {
            "day_utc": day.isoformat(),
            "net_usdc": "0",
            "trade_count": 0,
        }
        for day in plan.iter_process_oos_days()
    ]
    policies = []
    origin_hashes = []
    bundle_chain = []
    rotation_chain = []
    for origin, origin_ledger, boundary in zip(
        process_payload["origins"],
        ledger_payload["origin_ledgers"],
        plan.origins,
        strict=True,
    ):
        bundle = origin["frozen_candidate_bundle"]
        policy = hindsight_solvers.HindsightOriginPolicy(
            origin_index=boundary.origin_index,
            start_inclusive_utc=datetime.combine(
                boundary.test_start_inclusive, datetime.min.time(), UTC
            ),
            end_exclusive_utc=datetime.combine(
                boundary.test_end_exclusive, datetime.min.time(), UTC
            ),
            valid_from_utc=boundary.valid_from,
            origin_selection_sha256=origin["origin_sha256"],
            candidate_bundle_sha256=bundle["bundle_sha256"],
            rotation_state_sha256=origin_ledger["rotation_state_sha256"],
            max_roundtrips_per_utc_day=0,
            max_holding_minutes=0,
            entry_allowed=False,
        )
        policies.append(policy.to_dict())
        origin_hashes.append(origin["origin_sha256"])
        bundle_chain.append(
            {
                "origin_index": boundary.origin_index,
                "bundle_sha256": bundle["bundle_sha256"],
                "predecessor_bundle_sha256": bundle["predecessor_bundle_sha256"],
                "router_decision_sha256": bundle["router_decision"][
                    "decision_sha256"
                ],
                "cost_model": bundle["cost_model"],
                "validity": bundle["validity"],
            }
        )
        rotation_chain.append(
            {
                "origin_index": boundary.origin_index,
                "rotation_state_sha256": origin_ledger["rotation_state_sha256"],
                "new_candidate_bundle_sha256": origin_ledger["rotation_state"][
                    "new_candidate_bundle_sha256"
                ],
                "open_position": origin_ledger["rotation_state"]["open_position"],
                "entry_enabled_at": origin_ledger["rotation_state"][
                    "entry_enabled_at"
                ],
                "flat_time": origin_ledger["rotation_state"]["flat_time"],
            }
        )
    all_solver = hindsight_solvers._solver_evidence(
        hindsight_solvers.ALL_CANDLE_SOLVER,
        data_sha="1" * 64,
        exchange_sha=exchange["snapshot_sha256"],
        rules=rules,
        policy_chain=None,
        process_start=plan.process_start_inclusive,
        process_end=plan.process_end_exclusive,
        daily=zero_daily,
        trades=[],
        total=Decimal(0),
    ).to_dict()
    candidate_solver = hindsight_solvers._solver_evidence(
        hindsight_solvers.CANDIDATE_MATCHED_SOLVER,
        data_sha="1" * 64,
        exchange_sha=exchange["snapshot_sha256"],
        rules=rules,
        policy_chain=policies,
        process_start=plan.process_start_inclusive,
        process_end=plan.process_end_exclusive,
        daily=zero_daily,
        trades=[],
        total=Decimal(0),
    ).to_dict()
    source_binding = {
        path: f"{index + 10:064x}"
        for index, path in enumerate(hindsight_binding._SOURCE_PATHS)
    }
    day_index = [
        {"day": day.isoformat(), "content_sha256": "2" * 64}
        for day in plan.iter_process_oos_days()
    ]
    fingerprints = [
        origin["selection_decision"]["frozen_pipeline_config"][
            "run_fingerprint"
        ]["fingerprint_sha256"]
        for origin in process_payload["origins"]
    ]
    manifest = {
        "schema_version": "protocol_v3_hindsight_binding_manifest_v1",
        "data_snapshot_sha256": "3" * 64,
        "ethusdc_snapshot_market_content_sha256": "4" * 64,
        "ethusdc_process_data_sha256": "1" * 64,
        "ethusdc_process_day_index": day_index,
        "ethusdc_process_day_index_sha256": hindsight_binding._digest(day_index),
        "outer_process_sha256": process_payload["process_sha256"],
        "outer_ledger_sha256": ledger_payload["ledger_sha256"],
        "origin_hashes": origin_hashes,
        "origin_chain_sha256": hindsight_binding._digest(origin_hashes),
        "candidate_bundle_chain": bundle_chain,
        "candidate_bundle_chain_sha256": hindsight_binding._digest(bundle_chain),
        "rotation_state_chain": rotation_chain,
        "rotation_state_chain_sha256": hindsight_binding._digest(rotation_chain),
        "origin_run_fingerprint_sha256": fingerprints,
        "origin_run_fingerprint_chain_sha256": hindsight_binding._digest(
            fingerprints
        ),
        "code_commit": "a" * 40,
        "pipeline_generation_id": "protocol_v3_pipeline_sha256:" + "5" * 64,
        "current_pipeline_generation_basis_sha256": "5" * 64,
        "current_pipeline_contract_sha256": "6" * 64,
        "current_pipeline_component_source_sha256": {"quality_gates": "7" * 64},
        "current_pipeline_component_contracts": {
            "quality_gates": [diagnostics.CONTRACT_VERSION]
        },
        "candidate_policy_chain_sha256": hindsight_binding._digest(policies),
        "execution_rules_sha256": rules.rules_sha256,
        "exchange_info_snapshot_sha256": exchange["snapshot_sha256"],
        "solver_source_binding": source_binding,
        "solver_source_binding_sha256": hindsight_binding._digest(source_binding),
        "all_candle_solver_evidence_sha256": all_solver["evidence_sha256"],
        "candidate_matched_solver_evidence_sha256": candidate_solver[
            "evidence_sha256"
        ],
    }
    basis = {
        "schema_version": hindsight_binding.BINDING_SCHEMA_VERSION,
        "protocol_version": hindsight_binding.PROTOCOL_VERSION,
        "contract_version": hindsight_binding.BINDING_CONTRACT_VERSION,
        "binding_manifest": manifest,
        "binding_manifest_sha256": hindsight_binding._digest(manifest),
        "all_candle_solver_evidence": all_solver,
        "candidate_matched_solver_evidence": candidate_solver,
        "candidate_max_roundtrips_per_utc_day": 0,
        "candidate_policy_chain": policies,
        "candidate_policy_chain_sha256": hindsight_binding._digest(policies),
        "future_prices_used_for_diagnostic_only": True,
        "selection_feedback_allowed": False,
        "monthly_quality_gate_feedback_allowed": False,
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "canonical_adoption_eligible": False,
        "safety": hindsight_binding._SAFETY,
    }
    bound = hindsight_binding.BoundHindsightBenchmarks(
        hindsight_binding._canonical(basis), hindsight_binding._digest(basis)
    )
    return hindsight_binding.validate_bound_hindsight_benchmarks(bound)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, process, baseline = task26.state.__wrapped__(tmp_path, monkeypatch)
    gate = monthly_quality_gate.evaluate_monthly_quality_gate(
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        joint_stress_ledger=baseline,
        slippage_stress_ledger=baseline,
        stress_identity_evidence=task26._stress_identity(),
        regime_evidence={},
        integrity_evidence=task26._integrity(),
    )
    bound = _bound(plan, process, baseline)
    report = diagnostics.build_historical_diagnostics(
        boundary_plan=plan,
        outer_process=process,
        baseline_ledger=baseline,
        monthly_quality_report=gate,
        bound_hindsight_benchmarks=bound,
    )
    return plan, process, baseline, gate, bound, report


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = diagnostics.load_historical_diagnostics_contract(REPO_ROOT)
    assert contract["bootstrap_policy"]["replications"] == 10_000
    assert contract["benchmark_policy"][
        "caller_supplied_benchmark_numbers_forbidden"
    ] is True
    assert historical_diagnostics_api.__all__ == diagnostics.__all__
    pipeline = json.loads(
        (REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text()
    )
    assert hindsight_solvers.SOLVER_CONTRACT_VERSION in pipeline[
        "component_contracts"
    ]["quality_gates"]
    assert hindsight_binding.BINDING_CONTRACT_VERSION in pipeline[
        "component_contracts"
    ]["quality_gates"]
    assert diagnostics.CONTRACT_VERSION in pipeline["component_contracts"][
        "quality_gates"
    ]
    for path in (
        "configs/protocol_v3_historical_diagnostics_contract.json",
        "src/ethusdc_bot/protocol_v3/hindsight_solvers.py",
        "src/ethusdc_bot/protocol_v3/hindsight_binding.py",
        "src/ethusdc_bot/protocol_v3/historical_diagnostics.py",
        "src/ethusdc_bot/protocol_v3/historical_diagnostics_api.py",
    ):
        assert path in pipeline["source_bindings"]["quality_gates"]


def test_zero_history_bootstrap_and_capture_are_honest_diagnostics(state) -> None:
    plan, process, baseline, gate_report, bound, report = state
    payload = report.to_dict()
    assert [row["expected_block_length"] for row in payload["bootstrap_results"]] == [
        5,
        10,
        20,
    ]
    assert all(row["replications"] == 10_000 for row in payload["bootstrap_results"])
    assert all(
        row["lower_bound_usdc_per_day"] == "0" for row in payload["bootstrap_results"]
    )
    assert payload["historical_bootstrap_lower_bound"] is False
    assert payload["benchmarks"]["all_candle_one_trade_capture_ratio_diagnostic"] is None
    assert payload["benchmarks"]["candidate_matched_tradeable_capture_ratio"] is None
    assert payload["bound_hindsight_benchmarks_sha256"] == bound.binding_sha256
    assert payload["freshness"] == "NOT_FRESH"
    assert payload["statistically_supported"] is False
    assert payload["sealed_bootstrap_target_supported"] is False
    assert payload["canonical_adoption_eligible"] is False
    assert (
        diagnostics.validate_historical_diagnostics(
            payload,
            boundary_plan=plan,
            outer_process=process,
            baseline_ledger=baseline,
            monthly_quality_report=gate_report,
            bound_hindsight_benchmarks=bound,
        )
        == report
    )


def test_constant_three_series_uses_exact_500th_order_statistic() -> None:
    result = diagnostics._stationary_bootstrap([Decimal("3")] * 365, 123)
    assert all(row["lower_bound_usdc_per_day"] == "3" for row in result)
    assert all(row["order_statistic_one_based"] == 500 for row in result)


def test_manifest_seed_is_deterministic_and_excludes_outputs(state) -> None:
    *_, report = state
    payload = report.to_dict()
    manifest = payload["pre_bootstrap_input_manifest"]
    digest = diagnostics._digest(manifest)
    assert payload["pre_bootstrap_input_manifest_sha256"] == digest
    assert payload["seed_uint64"] == int(digest[:16], 16)
    assert manifest["hindsight_binding_sha256"] == payload[
        "bound_hindsight_benchmarks_sha256"
    ]
    assert "bootstrap_results" not in manifest
    assert "report_sha256" not in manifest


def test_free_benchmark_claim_channel_no_longer_exists() -> None:
    parameters = inspect.signature(
        diagnostics.build_historical_diagnostics
    ).parameters
    assert "benchmark_evidence" not in parameters
    assert "data_identity_sha256" not in parameters
    assert "code_commit" not in parameters
    assert "pipeline_generation_id" not in parameters


def test_rehashed_bound_feedback_or_fresh_adoption_claim_is_rejected(state) -> None:
    *_, report = state
    changed = deepcopy(report.to_dict())
    embedded = changed["bound_hindsight_benchmarks"]
    embedded["selection_feedback_allowed"] = True
    binding_basis = dict(embedded)
    binding_basis.pop("binding_sha256")
    embedded["binding_sha256"] = hindsight_binding._digest(binding_basis)
    changed["bound_hindsight_benchmarks_sha256"] = embedded["binding_sha256"]
    report_basis = dict(changed)
    report_basis.pop("report_sha256")
    bad = diagnostics.HistoricalDiagnostics(
        diagnostics._canonical(report_basis), diagnostics._digest(report_basis)
    )
    with pytest.raises(Exception, match="feedback|solver pair|binding"):
        diagnostics.validate_historical_diagnostics(bad)

    fresh = deepcopy(report.to_dict())
    fresh["freshness"] = "FRESH"
    fresh["statistically_supported"] = True
    fresh["sealed_bootstrap_target_supported"] = True
    fresh["canonical_adoption_eligible"] = True
    fresh_basis = dict(fresh)
    fresh_basis.pop("report_sha256")
    bad_fresh = diagnostics.HistoricalDiagnostics(
        diagnostics._canonical(fresh_basis), diagnostics._digest(fresh_basis)
    )
    with pytest.raises(diagnostics.HistoricalDiagnosticsError, match="safety"):
        diagnostics.validate_historical_diagnostics(bad_fresh)
