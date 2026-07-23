from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import importlib.util
import json
import math
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import (
    dsr,
    dsr_api,
    dsr_batch,
    dsr_batch_api,
    inner_selection,
    pbo,
)
from ethusdc_bot.protocol_v3.trial_ledger import DEVELOPMENT_DSR_READY, read_trial_ledger

REPO_ROOT = Path(__file__).resolve().parents[2]
_PBO_PATH = Path(__file__).with_name("test_protocol_v3_pbo.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task18_pbo_support", _PBO_PATH)
assert _SPEC is not None and _SPEC.loader is not None
pbo_support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pbo_support)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(reporting_module, "_utc_now", lambda: datetime(2026, 7, 16, tzinfo=UTC))
    return pbo_support.matrix_support.support.build_state(tmp_path, monkeypatch)


def _values(base: float, phase: float) -> list[float]:
    return [base + 0.16 * math.sin(index / 8.0 + phase) + 0.04 * math.cos(index / 21.0) for index in range(360)]


def _matrix_and_pbo(state):
    candidate_a = pbo_support.matrix_support._candidate(201)
    candidate_b = pbo_support.matrix_support._candidate(202)
    matrix = pbo_support._matrix(
        state,
        [(candidate_a, _values(0.22, 0.0)), (candidate_b, _values(0.08, 1.3))],
    )
    return candidate_a, candidate_b, matrix, pbo.calculate_pbo(matrix)


def _complete_snapshot(state, matrix):
    snapshot = read_trial_ledger(state["ledger_root"])
    trial_ids = {
        profile["trial_id"]
        for cycle in matrix.to_dict()["cycles"]
        for profile in cycle["profiles"]
    }
    trials = {trial_id: snapshot.trials[trial_id] for trial_id in trial_ids}
    attached = {
        trial_id: rows
        for trial_id, rows in snapshot.attached_daily_series.items()
        if trial_id in trial_ids
    }
    status = replace(
        snapshot.status,
        resolved_trial_count=len(trials),
        native_trial_count=len(trials),
        historical_resolved_trial_count=0,
        known_observed_historical_evaluation_rows=180,
        historical_trial_count_is_lower_bound=False,
        canonical_historical_import_present=True,
        missing_daily_series_trial_ids=(),
        permanent_trial_count_lower_bound=len(trials),
        development_dsr_status=DEVELOPMENT_DSR_READY,
        only_release_decision_allowed=None,
    )
    return replace(snapshot, trials=trials, attached_daily_series=attached, status=status)


def test_contract_public_api_and_pipeline_binding_are_exact() -> None:
    contract = dsr.load_dsr_contract(REPO_ROOT)
    assert contract["contract_version"] == dsr.CONTRACT_VERSION
    assert contract["series_policy"]["lag_count_at_360"] == 5
    assert contract["trial_policy"]["n_eff_trials_is_diagnostic_only"] is True
    assert dsr_api.__all__ == dsr.__all__
    assert dsr_batch_api.__all__ == dsr_batch.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert dsr.CONTRACT_VERSION in pipeline["component_contracts"]["ranking"]
    for path in (
        "configs/protocol_v3_dsr_contract.json",
        "src/ethusdc_bot/protocol_v3/dsr.py",
        "src/ethusdc_bot/protocol_v3/dsr_api.py",
        "src/ethusdc_bot/protocol_v3/dsr_batch.py",
        "src/ethusdc_bot/protocol_v3/dsr_batch_api.py",
    ):
        assert path in pipeline["source_bindings"]["ranking"]


def test_real_incomplete_history_is_typed_and_blocks_without_number(state) -> None:
    candidate_a, _, matrix, pbo_evidence = _matrix_and_pbo(state)
    profile = matrix.to_dict()["cycles"][0]["profiles"][0]
    assert profile["candidate_id"] == candidate_a
    snapshot = read_trial_ledger(state["ledger_root"])
    evidence = dsr.calculate_dsr(
        pbo_evidence=pbo_evidence,
        selected_profile_id=profile["profile_id"],
        trial_ledger=snapshot,
    )
    payload = evidence.to_dict()
    assert payload["state"] == dsr.INSUFFICIENT_TRIAL_HISTORY
    assert payload["development_dsr"] is None
    assert payload["n_raw"] is None
    support = inner_selection.build_dsr_development_support(
        {
            row["candidate_id"]: dsr.calculate_dsr(
                pbo_evidence=pbo_evidence,
                selected_profile_id=row["profile_id"],
                trial_ledger=snapshot,
            )
            for row in matrix.to_dict()["cycles"][0]["profiles"]
        },
        cycle_index=1,
        trial_ledger=snapshot,
    ).to_dict()
    assert support["dsr"]["state"] == inner_selection.INSUFFICIENT_EVIDENCE
    assert support["dsr"]["value"] is None


def test_cash_is_not_applicable_and_never_receives_numeric_dsr(state) -> None:
    _, _, _, pbo_evidence = _matrix_and_pbo(state)
    payload = dsr.calculate_dsr(
        pbo_evidence=pbo_evidence,
        selected_profile_id=pbo.CASH_ID,
        trial_ledger=read_trial_ledger(state["ledger_root"]),
    ).to_dict()
    assert payload["state"] == dsr.NOT_APPLICABLE_NO_TRADE
    assert payload["development_dsr"] is None
    assert "selected_candidate_id" not in payload


def test_complete_inventory_reproduces_exact_dsr_and_diagnostics(state, monkeypatch) -> None:
    candidate_a, candidate_b, matrix, pbo_evidence = _matrix_and_pbo(state)
    snapshot = _complete_snapshot(state, matrix)
    monkeypatch.setattr(dsr, "_current_ledger", lambda value: snapshot)
    monkeypatch.setattr(
        dsr_batch,
        "_current_ledger",
        lambda value: snapshot,
    )
    profiles = matrix.to_dict()["cycles"][0]["profiles"]
    evidence = {
        row["candidate_id"]: dsr.calculate_dsr(
            pbo_evidence=pbo_evidence,
            selected_profile_id=row["profile_id"],
            trial_ledger=snapshot,
        )
        for row in profiles
    }
    batch = dsr.calculate_dsr_batch(
        pbo_evidence=pbo_evidence,
        selected_profile_ids=[row["profile_id"] for row in profiles],
        trial_ledger=snapshot,
    )
    assert {
        profile_id: value.to_dict()
        for profile_id, value in batch.items()
    } == {
        row["profile_id"]: evidence[row["candidate_id"]].to_dict()
        for row in profiles
    }
    compact = dsr_batch.calculate_dsr_batch_evidence(
        pbo_evidence=pbo_evidence,
        cycle_index=1,
        trial_ledger=snapshot,
    )
    compact_payload = compact.to_dict()
    assert [
        row["result"]["development_dsr"]
        for row in compact_payload["profiles"]
    ] == [
        evidence[row["candidate_id"]].to_dict()["development_dsr"]
        for row in profiles
    ]
    assert dsr_batch.validate_dsr_batch_evidence(compact) == compact
    support_from_batch = (
        inner_selection.build_dsr_batch_development_support(
            compact,
            trial_ledger=snapshot,
        ).to_dict()
    )
    assert support_from_batch["dsr"]["state"] == inner_selection.COMPLETE
    assert inner_selection._dsr_selection_values(
        support_from_batch
    ) == {
        row["candidate_id"]: evidence[row["candidate_id"]].to_dict()[
            "development_dsr"
        ]
        for row in profiles
    }
    payload = evidence[candidate_a].to_dict()
    assert payload["state"] == dsr.COMPLETE
    assert payload["n"] == 360
    assert payload["lag_count"] == 5
    assert payload["complete_native_trial_count"] == snapshot.status.native_trial_count == 2
    assert payload["same_grid_native_trial_count"] == 2
    assert payload["n_raw"] == 182
    assert payload["legacy_multiplicity_floor"] == 180
    assert payload["legacy_daily_series_used"] is False
    assert payload["n_eff_trials"] <= payload["n_raw"]
    assert 0.0 <= payload["development_dsr"] <= 1.0
    assert payload["passed_minimum_dsr"] == (payload["development_dsr"] >= 0.95)
    assert dsr.validate_dsr_evidence(payload).to_dict() == payload
    support = inner_selection.build_dsr_development_support(
        evidence,
        cycle_index=1,
        trial_ledger=snapshot,
    ).to_dict()
    assert support["dsr"]["state"] == inner_selection.COMPLETE
    assert set(support["dsr"]["value"]) == {candidate_a}
    assert inner_selection._dsr_selection_values(support)[candidate_a] == payload["development_dsr"]
    assert payload["sharpe"] == pytest.approx(1.8556730004083697)
    assert payload["vif"] == pytest.approx(5.731442118827879)
    assert payload["n_eff"] == pytest.approx(62.811416836505124)
    assert payload["skew"] == pytest.approx(-0.006542110704607639)
    assert payload["pearson_kurtosis"] == pytest.approx(1.6623697577699468)
    assert payload["sigma_sr"] == pytest.approx(0.8278556501279813)
    assert payload["sr0"] == pytest.approx(2.2638123917557365)
    assert payload["denominator"] == pytest.approx(1.582361273555969)
    assert payload["z"] == pytest.approx(-2.550880060221503)
    assert payload["development_dsr"] == pytest.approx(0.005372564844706884)
    assert payload["passed_minimum_dsr"] is False


def test_cross_origin_native_trial_counts_for_multiplicity_but_not_same_grid_stats(
    state, monkeypatch
) -> None:
    _, _, matrix, pbo_evidence = _matrix_and_pbo(state)
    snapshot = _complete_snapshot(state, matrix)
    trials = deepcopy(snapshot.trials)
    source_trial = deepcopy(next(iter(trials.values())))
    shifted_start = date(2024, 1, 1)
    source_trial["daily_net_mtm_usdc"] = [
        {
            "day": (shifted_start + timedelta(days=index)).isoformat(),
            "net_usdc": value,
        }
        for index, value in enumerate(_values(0.11, 0.7))
    ]
    trials["cross-origin-native-trial"] = source_trial
    expanded = replace(
        snapshot,
        trials=trials,
        status=replace(
            snapshot.status,
            resolved_trial_count=3,
            native_trial_count=3,
            permanent_trial_count_lower_bound=3,
        ),
    )
    monkeypatch.setattr(dsr, "_current_ledger", lambda value: expanded)
    profile = matrix.to_dict()["cycles"][0]["profiles"][0]

    payload = dsr.calculate_dsr(
        pbo_evidence=pbo_evidence,
        selected_profile_id=profile["profile_id"],
        trial_ledger=expanded,
    ).to_dict()

    assert payload["state"] == dsr.COMPLETE
    assert payload["n_raw"] == 183
    assert payload["complete_native_trial_count"] == 3
    assert payload["same_grid_native_trial_count"] == 2
    assert len(payload["trial_rows"]) == 2
    assert dsr.validate_dsr_evidence(payload).to_dict() == payload


def test_noncontiguous_native_trial_grid_is_typed_incomplete_evidence(
    state, monkeypatch
) -> None:
    _, _, matrix, pbo_evidence = _matrix_and_pbo(state)
    snapshot = _complete_snapshot(state, matrix)
    trials = deepcopy(snapshot.trials)
    trial_id = next(iter(trials))
    daily = list(
        trials[trial_id].get("daily_net_mtm_usdc")
        or snapshot.attached_daily_series[trial_id]
    )
    daily[-1] = {
        **daily[-1],
        "day": (
            date.fromisoformat(daily[-1]["day"]) + timedelta(days=1)
        ).isoformat(),
    }
    trials[trial_id]["daily_net_mtm_usdc"] = daily
    broken = replace(snapshot, trials=trials, attached_daily_series={})
    monkeypatch.setattr(dsr, "_current_ledger", lambda value: broken)
    profile = matrix.to_dict()["cycles"][0]["profiles"][0]

    payload = dsr.calculate_dsr(
        pbo_evidence=pbo_evidence,
        selected_profile_id=profile["profile_id"],
        trial_ledger=broken,
    ).to_dict()

    assert payload["state"] == dsr.INSUFFICIENT_EVIDENCE
    assert payload["reason"] == "native_trial_daily_grid_is_not_contiguous"
    assert payload["development_dsr"] is None


def test_invalid_statistics_are_typed_and_tampering_is_rejected(state, monkeypatch) -> None:
    _, _, matrix, pbo_evidence = _matrix_and_pbo(state)
    snapshot = _complete_snapshot(state, matrix)
    selected_trial_id = matrix.to_dict()["cycles"][0]["profiles"][0]["trial_id"]
    first_trial_id = next(trial_id for trial_id in snapshot.trials if trial_id != selected_trial_id)
    broken_trials = deepcopy(snapshot.trials)
    constant = [{"day": day, "net_usdc": 1.0} for day in matrix.to_dict()["day_grid"]]
    broken_trials[first_trial_id]["daily_net_mtm_usdc"] = constant
    broken = replace(snapshot, trials=broken_trials, attached_daily_series={})
    monkeypatch.setattr(dsr, "_current_ledger", lambda value: broken)
    profile = matrix.to_dict()["cycles"][0]["profiles"][0]
    payload = dsr.calculate_dsr(
        pbo_evidence=pbo_evidence,
        selected_profile_id=profile["profile_id"],
        trial_ledger=broken,
    ).to_dict()
    assert payload["state"] == dsr.INSUFFICIENT_EVIDENCE
    assert payload["reason"] == "trial_series_zero_variance"
    assert payload["development_dsr"] is None

    tampered = deepcopy(payload)
    tampered["development_dsr"] = 1.0
    basis = dict(tampered)
    basis.pop("evidence_sha256")
    tampered["evidence_sha256"] = dsr._digest(basis)
    with pytest.raises(dsr.DSRError, match="numeric replacement"):
        dsr.validate_dsr_evidence(tampered)


def test_stale_ledger_head_blocks_before_selection_freeze(state, monkeypatch) -> None:
    _, _, matrix, pbo_evidence = _matrix_and_pbo(state)
    snapshot = read_trial_ledger(state["ledger_root"])
    profile = matrix.to_dict()["cycles"][0]["profiles"][0]
    evidence = dsr.calculate_dsr(
        pbo_evidence=pbo_evidence,
        selected_profile_id=profile["profile_id"],
        trial_ledger=snapshot,
    )
    newer = replace(snapshot, status=replace(snapshot.status, head_sha256="f" * 64))
    monkeypatch.setattr(dsr, "_current_ledger", lambda value: newer)
    with pytest.raises(dsr.DSRError, match="stale"):
        dsr.validate_dsr_for_ledger(evidence, snapshot)
