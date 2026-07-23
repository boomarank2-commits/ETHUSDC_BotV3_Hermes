"""Task-33 real-run preflight and blocker-report tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import task33_preflight as preflight
from ethusdc_bot.protocol_v3 import task33_preflight_api
from ethusdc_bot.protocol_v3.production_runtime import build_task33_runtime_inputs

REPO_ROOT = Path(__file__).resolve().parents[2]


def _kwargs() -> dict[str, object]:
    return {
        "repo_root": REPO_ROOT,
        "run_id": "task33-real-preflight-test",
        "created_at_utc": "2026-07-22T15:00:00Z",
        "code_commit": "a" * 40,
        "pipeline_generation_id": "protocol_v3_pipeline_sha256:" + "b" * 64,
        "data_snapshot": {"snapshot_sha256": "c" * 64, "quality_status": "usable_for_protocol_v3_snapshot"},
        "exchange_info_snapshot": {"snapshot_sha256": "d" * 64, "symbol": "ETHUSDC"},
        "trial_ledger_status": {
            "head_sha256": "e" * 64,
            "development_dsr_status": "INSUFFICIENT_TRIAL_HISTORY",
            "only_release_decision_allowed": "NO_TRADE",
            "historical_trial_count_is_lower_bound": True,
            "canonical_historical_import_present": True,
            "known_observed_historical_evaluation_rows": 180,
            "historical_resolved_trial_count": 0,
        },
        "runtime_inputs": {"active_lookbacks": [], "horizon_policy": None, "production_outer_origin_adapter": False},
    }


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = preflight.load_task33_contract(REPO_ROOT)
    assert contract["contract_version"] == preflight.CONTRACT_VERSION
    assert task33_preflight_api.__all__ == preflight.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert preflight.CONTRACT_VERSION in pipeline["component_contracts"]["quality_gates"]
    for path in ("configs/protocol_v3_task33_contract.json", "src/ethusdc_bot/protocol_v3/task33_preflight.py", "src/ethusdc_bot/protocol_v3/task33_preflight_api.py"):
        assert path in pipeline["source_bindings"]["quality_gates"]


def test_conservative_floor_removes_only_the_irrecoverable_history_blocker() -> None:
    report = preflight.build_task33_preflight_report(**_kwargs())
    payload = report.to_dict()
    assert payload["status"] == preflight.BLOCKED_INPUTS
    assert "INSUFFICIENT_TRIAL_HISTORY" not in payload["blockers"]
    assert payload["legacy_multiplicity_policy"]["legacy_multiplicity_floor"] == 180
    assert payload["legacy_multiplicity_policy"]["legacy_daily_series_used"] is False
    assert payload["research_execution"]["full_research_run_started"] is False
    assert payload["research_execution"]["result_status"] == "not_executed_due_blocker"
    assert all(value is None for value in payload["results"].values())
    assert payload["release_decision"] == "NO_TRADE"
    assert payload["adoption_eligible"] is False
    assert payload["bot_start_allowed"] is False


def test_mismatched_legacy_inventory_still_blocks_history_first() -> None:
    kwargs = _kwargs()
    kwargs["trial_ledger_status"] = {
        **kwargs["trial_ledger_status"],
        "known_observed_historical_evaluation_rows": 179,
    }

    payload = preflight.build_task33_preflight_report(**kwargs).to_dict()

    assert payload["status"] == preflight.BLOCKED_HISTORY
    assert payload["blockers"][0] == "INSUFFICIENT_TRIAL_HISTORY"


def test_ready_preflight_still_cannot_claim_execution_or_adoption() -> None:
    kwargs = _kwargs()
    kwargs["trial_ledger_status"] = {
        **_kwargs()["trial_ledger_status"],
        "development_dsr_status": "READY_FOR_DSR_IMPLEMENTATION",
        "only_release_decision_allowed": None,
    }
    kwargs["runtime_inputs"] = build_task33_runtime_inputs(
        REPO_ROOT, production_outer_origin_adapter=True
    )
    payload = preflight.build_task33_preflight_report(**kwargs).to_dict()
    assert payload["status"] == preflight.READY
    assert payload["research_execution"]["result_status"] == "awaiting_explicit_execution"
    assert payload["bot_start_allowed"] is False


def test_unfrozen_positive_runtime_values_do_not_clear_preflight() -> None:
    kwargs = _kwargs()
    kwargs["trial_ledger_status"] = {
        **_kwargs()["trial_ledger_status"],
        "development_dsr_status": "READY_FOR_DSR_IMPLEMENTATION",
        "only_release_decision_allowed": None,
    }
    kwargs["runtime_inputs"] = {
        "active_lookbacks": [{"name": "plausible_but_unbound"}],
        "horizon_policy": {
            "max_label_horizon_minutes": 120,
            "max_holding_period_minutes": 180,
            "pending_order_latency_minutes": 2,
        },
        "production_outer_origin_adapter": True,
    }

    payload = preflight.build_task33_preflight_report(**kwargs).to_dict()

    assert payload["status"] == preflight.BLOCKED_INPUTS
    assert "MISSING_FROZEN_ACTIVE_LOOKBACKS" in payload["blockers"]
    assert "MISSING_FROZEN_HORIZON_POLICY" in payload["blockers"]


def test_tampering_and_create_only_overwrite_fail_closed(tmp_path: Path) -> None:
    report = preflight.build_task33_preflight_report(**_kwargs())
    forged = deepcopy(report.to_dict())
    forged["results"]["trades"] = 1
    with pytest.raises(preflight.Task33PreflightError, match="complete and null"):
        preflight.validate_task33_preflight_report(forged)
    target = tmp_path / "task33.json"
    preflight.write_task33_preflight_report(report, target)
    assert target.read_bytes() == (report.canonical_json + "\n").encode()
    with pytest.raises(preflight.Task33PreflightError, match="create-only"):
        preflight.write_task33_preflight_report(report, target)


def test_missing_identity_and_rehashed_unsafe_claims_fail_closed() -> None:
    kwargs = _kwargs()
    kwargs["code_commit"] = "short"
    with pytest.raises(preflight.Task33PreflightError, match="git SHA"):
        preflight.build_task33_preflight_report(**kwargs)
    report = preflight.build_task33_preflight_report(**_kwargs()).to_dict()
    report["bot_start_allowed"] = True
    with pytest.raises(preflight.Task33PreflightError, match="safety claim"):
        preflight.validate_task33_preflight_report(report)


def test_rehashed_legacy_status_bypass_is_rejected() -> None:
    report = preflight.build_task33_preflight_report(**_kwargs()).to_dict()
    report["status"] = preflight.READY
    report["blockers"] = []

    with pytest.raises(preflight.Task33PreflightError, match="exact preflight replay"):
        preflight.validate_task33_preflight_report(report)
