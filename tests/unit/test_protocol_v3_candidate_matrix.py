from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import candidate_matrix as matrix
from ethusdc_bot.protocol_v3 import candidate_matrix_api
from ethusdc_bot.protocol_v3 import inner_selection as selection
from ethusdc_bot.protocol_v3.trial_ledger import (
    append_trial,
    build_trial_record,
    read_trial_ledger,
    record_cache_reuse,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_SUPPORT_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task16_support", _SUPPORT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    return support.build_state(tmp_path, monkeypatch)


def _candidate(number: int) -> str:
    return "protocol_v3_candidate_sha256:" + hashlib.sha256(str(number).encode()).hexdigest()


def _folds(plan, value: float = 0.0):
    result = []
    for boundary in plan.folds:
        daily = [
            {
                "day": (boundary.validation_start_inclusive_utc.date() + timedelta(days=index)).isoformat(),
                "net_usdc": value if index == 0 else 0.0,
            }
            for index in range(60)
        ]
        result.append(
            {
                "fold_index": boundary.fold_index,
                "fold_id": boundary.fold_id,
                "daily_net_mtm_usdc": daily,
            }
        )
    return result


def _daily(folds):
    return [row for fold in folds for row in fold["daily_net_mtm_usdc"]]


def _trial(state, candidate_id: str, cycle: int, folds):
    record = build_trial_record(
        source_kind="native_evaluation",
        candidate_id=candidate_id,
        family="task16_fixture",
        parameters={"symbol": "ETHUSDC", "cycle": cycle},
        feature_variant="task16_fixture",
        seed=cycle,
        versions={
            "pipeline_generation": state["manifest"].to_dict()["pipeline_generation"]["generation_id"],
            "ranking_version": selection.INNER_SELECTION_CONTRACT_VERSION,
            "gate_version": "monthly_quality_gate_v1",
            "simulator_version": "task16_fixture",
            "cost_model_version": "task16_fixture",
            "boundary_version": "task16_fixture",
        },
        code_commit="a" * 40,
        evaluation_scope={"origin_index": 1, "cycle_index": cycle},
        daily_net_mtm_usdc=_daily(folds),
        result_summary={"net_mtm_total_usdc": sum(row["net_usdc"] for row in _daily(folds))},
    )
    append_trial(state["ledger_root"], record)
    return record


def _cycle(candidate_id: str, trial_id: str, folds, *, cycle: int = 1, cache_reuse: bool = False):
    return {
        "cycle_index": cycle,
        "tested_candidate_ids": [candidate_id],
        "promoted_candidate_ids": [],
        "finalist_candidate_ids": [],
        "profiles": [
            {
                "candidate_id": candidate_id,
                "trial_id": trial_id,
                "cache_reuse": cache_reuse,
                "folds": folds,
            }
        ],
    }


def _build(state, cycles):
    return matrix.build_candidate_daily_matrix(
        fold_plan=state["inner_fold_plan"],
        origin_index=1,
        cycles=cycles,
        trial_ledger=read_trial_ledger(state["ledger_root"]),
    )


def test_contract_public_api_and_pipeline_binding_are_exact() -> None:
    contract = matrix.load_candidate_matrix_contract(REPO_ROOT)
    assert contract["contract_version"] == matrix.CONTRACT_VERSION
    assert candidate_matrix_api.__all__ == matrix.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert matrix.CONTRACT_VERSION in pipeline["component_contracts"]["ranking"]
    for path in (
        "configs/protocol_v3_candidate_matrix_contract.json",
        "src/ethusdc_bot/protocol_v3/candidate_matrix.py",
        "src/ethusdc_bot/protocol_v3/candidate_matrix_api.py",
    ):
        assert path in pipeline["source_bindings"]["ranking"]


def test_complete_matrix_retains_all_cycles_zero_days_and_deltas(state) -> None:
    first_id, second_id = _candidate(1), _candidate(2)
    first_folds, second_folds = _folds(state["inner_fold_plan"], 1.0), _folds(state["inner_fold_plan"], -0.5)
    first = _trial(state, first_id, 1, first_folds)
    second = _trial(state, second_id, 2, second_folds)
    built = _build(
        state,
        [
            _cycle(first_id, first.trial_id, first_folds, cycle=1),
            _cycle(second_id, second.trial_id, second_folds, cycle=2),
        ],
    )
    payload = built.to_dict()
    assert len(payload["day_grid"]) == 360
    assert payload["profile_count"] == 2
    assert [row["cycle_index"] for row in payload["cycles"]] == [1, 2]
    assert payload["cycles"][0]["profiles"][0]["net_mtm_total_usdc"] == 6.0
    assert sum(row["net_usdc"] == 0.0 for row in payload["cycles"][0]["profiles"][0]["daily_net_mtm_usdc"]) == 354
    assert matrix.validate_candidate_matrix_identity_payload(built.identity_payload) == built.identity_payload
    assert _build(state, list(reversed([_cycle(second_id, second.trial_id, second_folds, cycle=2), _cycle(first_id, first.trial_id, first_folds, cycle=1)]))).matrix_sha256 == built.matrix_sha256


def test_legitimately_small_inventory_is_not_filled_and_missing_profile_blocks(state) -> None:
    candidate_id = _candidate(3)
    folds = _folds(state["inner_fold_plan"])
    record = _trial(state, candidate_id, 1, folds)
    built = _build(state, [_cycle(candidate_id, record.trial_id, folds)])
    assert built.to_dict()["profile_count"] == 1
    broken = _cycle(candidate_id, record.trial_id, folds)
    broken["profiles"] = []
    with pytest.raises(matrix.CandidateMatrixError, match="every declared tested"):
        _build(state, [broken])


def test_cycle_budget_caps_block_without_forced_fill(state) -> None:
    too_many = {
        "cycle_index": 1,
        "tested_candidate_ids": [_candidate(index) for index in range(20, 33)],
        "promoted_candidate_ids": [],
        "finalist_candidate_ids": [],
        "profiles": [],
    }
    with pytest.raises(matrix.CandidateMatrixError):
        _build(state, [too_many])


def test_zero_test_cycle_is_not_artificially_filled(state) -> None:
    built = _build(
        state,
        [{
            "cycle_index": 1,
            "tested_candidate_ids": [],
            "promoted_candidate_ids": [],
            "finalist_candidate_ids": [],
            "profiles": [],
        }],
    )
    assert built.to_dict()["profile_count"] == 0
    development = selection.build_matrix_development_support(built, cycle_index=1)
    assert development.to_dict()["matrix"]["candidate_ids"] == []


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "reordered", "nonfinite"])
def test_invalid_daily_grids_block_instead_of_becoming_zero(state, mutation) -> None:
    candidate_id = _candidate(4)
    good_folds = _folds(state["inner_fold_plan"])
    record = _trial(state, candidate_id, 1, good_folds)
    bad = deepcopy(good_folds)
    if mutation == "missing":
        bad[-1]["daily_net_mtm_usdc"].pop()
    elif mutation == "extra":
        bad[-1]["daily_net_mtm_usdc"].append({"day": "2099-01-01", "net_usdc": 0.0})
    elif mutation == "duplicate":
        bad[-1]["daily_net_mtm_usdc"][-1]["day"] = bad[-1]["daily_net_mtm_usdc"][-2]["day"]
    elif mutation == "reordered":
        bad[-1]["daily_net_mtm_usdc"][-2:] = reversed(bad[-1]["daily_net_mtm_usdc"][-2:])
    else:
        bad[-1]["daily_net_mtm_usdc"][-1]["net_usdc"] = float("nan")
    with pytest.raises(matrix.CandidateMatrixError):
        _build(state, [_cycle(candidate_id, record.trial_id, bad)])


def test_cache_reuse_is_visible_without_new_independent_trial(state) -> None:
    candidate_id = _candidate(5)
    folds = _folds(state["inner_fold_plan"], 0.25)
    record = _trial(state, candidate_id, 1, folds)
    before = read_trial_ledger(state["ledger_root"]).status.resolved_trial_count
    record_cache_reuse(
        state["ledger_root"],
        trial_id=record.trial_id,
        reuse_scope={"origin_index": 1, "cycle_index": 2},
    )
    built = _build(
        state,
        [
            _cycle(candidate_id, record.trial_id, folds, cycle=1),
            _cycle(candidate_id, record.trial_id, folds, cycle=2, cache_reuse=True),
        ],
    )
    ledger = read_trial_ledger(state["ledger_root"])
    assert ledger.status.resolved_trial_count == before
    assert ledger.status.cache_reuse_count >= 1
    assert built.to_dict()["profile_count"] == 2


def test_task16_support_binds_origin_cycle_and_remains_no_trade_without_pbo_dsr(state) -> None:
    candidate_id = _candidate(6)
    folds = _folds(state["inner_fold_plan"])
    record = _trial(state, candidate_id, 1, folds)
    built = _build(state, [_cycle(candidate_id, record.trial_id, folds)])
    development = selection.build_matrix_development_support(built, cycle_index=1)
    payload = development.to_dict()
    assert payload["matrix"]["state"] == selection.COMPLETE
    assert payload["pbo"]["state"] == selection.INSUFFICIENT_EVIDENCE
    assert payload["dsr"]["state"] == selection.INSUFFICIENT_EVIDENCE
    assert payload["matrix"]["value"] == built.identity_payload
    config = selection.build_frozen_selection_config(
        pre_run_manifest=state["manifest"],
        run_fingerprint=state["fingerprint"],
        fold_identity=state["inner_fold_plan"].identity_payload,
        origin_index=1,
        cycle_index=1,
        generated_candidate_ids=[candidate_id],
        tested_candidate_ids=[candidate_id],
        walk_forward_candidate_ids=[],
        finalist_candidate_ids=[],
        candidate_evidence=[],
        development_support=development,
    )
    decision = selection.select_candidate(state["training_window"], config)
    assert decision.outcome == selection.NO_TRADE
    assert "TASK16_MATRIX_INSUFFICIENT_EVIDENCE" not in decision.to_dict()["blockers"]
    assert "TASK17_PBO_INSUFFICIENT_EVIDENCE" in decision.to_dict()["blockers"]
    assert "TASK18_DSR_INSUFFICIENT_EVIDENCE" in decision.to_dict()["blockers"]


def test_tampered_rehashed_content_and_outer_fields_block(state) -> None:
    candidate_id = _candidate(7)
    folds = _folds(state["inner_fold_plan"])
    record = _trial(state, candidate_id, 1, folds)
    payload = _build(state, [_cycle(candidate_id, record.trial_id, folds)]).to_dict()
    payload["cycles"][0]["profiles"][0]["daily_net_mtm_usdc"][0]["net_usdc"] = 99.0
    payload["content_sha256"] = matrix._digest([row for cycle in payload["cycles"] for row in cycle["profiles"]])
    basis = dict(payload); basis.pop("matrix_sha256")
    payload["matrix_sha256"] = matrix._digest(basis)
    with pytest.raises(matrix.CandidateMatrixError):
        matrix.validate_candidate_daily_matrix(payload)
    forbidden = _cycle(candidate_id, record.trial_id, folds)
    forbidden["outer_results"] = {"pnl": 1.0}
    with pytest.raises(matrix.CandidateMatrixError):
        _build(state, [forbidden])
