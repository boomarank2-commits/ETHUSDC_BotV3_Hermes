"""Task-13 production candidate identity after completed Tasks 16-18."""
from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pytest

from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3 import dsr, inner_selection, pbo
from ethusdc_bot.protocol_v3 import transactional_cache as tx
from ethusdc_bot.protocol_v3.trial_ledger import read_trial_ledger

REPO_ROOT = Path(__file__).resolve().parents[2]

_INNER_PATH = Path(__file__).with_name("test_protocol_v3_inner_selection.py")
_INNER_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task13_candidate_inner_support", _INNER_PATH
)
assert _INNER_SPEC is not None and _INNER_SPEC.loader is not None
inner_support = importlib.util.module_from_spec(_INNER_SPEC)
_INNER_SPEC.loader.exec_module(inner_support)

_MATRIX_PATH = Path(__file__).with_name("test_protocol_v3_candidate_matrix.py")
_MATRIX_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task13_candidate_matrix_support", _MATRIX_PATH
)
assert _MATRIX_SPEC is not None and _MATRIX_SPEC.loader is not None
matrix_support = importlib.util.module_from_spec(_MATRIX_SPEC)
_MATRIX_SPEC.loader.exec_module(matrix_support)

_DSR_PATH = Path(__file__).with_name("test_protocol_v3_dsr.py")
_DSR_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task13_candidate_dsr_support", _DSR_PATH
)
assert _DSR_SPEC is not None and _DSR_SPEC.loader is not None
dsr_support = importlib.util.module_from_spec(_DSR_SPEC)
_DSR_SPEC.loader.exec_module(dsr_support)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    return matrix_support.support.build_state(tmp_path, monkeypatch)


def _production_decision(state, monkeypatch: pytest.MonkeyPatch):
    candidates = [
        StrategyCandidate("fixture_family", {"lookback": 10}),
        StrategyCandidate("fixture_family", {"lookback": 20}),
    ]
    rows = [
        inner_selection.build_candidate_selection_evidence(
            candidate,
            inner_support._quality_evidence([value] * 6, joint_net=value),
            state["training_window"],
        )
        for candidate, value in zip(candidates, (0.30, 0.20), strict=True)
    ]
    candidate_ids = [row.canonical_candidate_id for row in rows]
    profiles = []
    for candidate_id, value in zip(candidate_ids, (0.30, 0.20), strict=True):
        folds = matrix_support._folds(state["inner_fold_plan"], value)
        trial = matrix_support._trial(state, candidate_id, 1, folds)
        profiles.append(
            {
                "candidate_id": candidate_id,
                "trial_id": trial.trial_id,
                "cache_reuse": False,
                "folds": folds,
            }
        )
    matrix = matrix_support._build(
        state,
        [
            {
                "cycle_index": 1,
                "tested_candidate_ids": candidate_ids,
                "promoted_candidate_ids": candidate_ids,
                "finalist_candidate_ids": candidate_ids,
                "profiles": profiles,
            }
        ],
    )
    pbo_evidence = pbo.calculate_pbo(matrix)
    snapshot = dsr_support._complete_snapshot(state, matrix)
    monkeypatch.setattr(dsr, "_current_ledger", lambda value: snapshot)
    dsr_evidence = {
        profile["candidate_id"]: dsr.calculate_dsr(
            pbo_evidence=pbo_evidence,
            selected_profile_id=profile["profile_id"],
            trial_ledger=snapshot,
        )
        for profile in matrix.to_dict()["cycles"][0]["profiles"]
    }
    development = inner_selection.build_dsr_development_support(
        dsr_evidence,
        cycle_index=1,
        trial_ledger=snapshot,
    )
    config = inner_selection.build_frozen_selection_config(
        pre_run_manifest=state["manifest"],
        run_fingerprint=state["fingerprint"],
        fold_identity=state["inner_fold_plan"].identity_payload,
        origin_index=1,
        cycle_index=1,
        generated_candidate_ids=candidate_ids,
        tested_candidate_ids=candidate_ids,
        walk_forward_candidate_ids=candidate_ids,
        finalist_candidate_ids=candidate_ids,
        candidate_evidence=rows,
        development_support=development,
    )
    decision = inner_selection.select_candidate(state["training_window"], config)
    assert decision.outcome == inner_selection.CANDIDATE
    assert decision.fixture_only is False
    return decision


def test_real_task16_to_18_candidate_is_bound_in_task13_identity(
    state, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision = _production_decision(state, monkeypatch)
    identity = tx.build_transaction_identity(
        run_fingerprint=state["fingerprint"],
        context_binding=state["binding"],
        horizon_policy=matrix_support.support.HORIZON,
        work_unit_id="origin_01_cycle_01_candidate",
        candidate_identity=tx.build_bound_identity_slot(
            tx.CANDIDATE_SLOT,
            tx.CANDIDATE_SELECTION_IDENTITY_SCHEMA,
            decision.candidate_identity_payload,
        ),
        fold_identity=tx.build_bound_identity_slot(
            tx.FOLD_SLOT,
            tx.FOLD_IDENTITY_SCHEMA,
            state["inner_fold_plan"].identity_payload,
        ),
        rotation_state_identity=tx.build_genesis_identity_slot(
            tx.ROTATION_SLOT,
            tx.ROTATION_GENESIS_SCHEMA,
            "no_rotation_state",
        ),
        sealed_store_heads=tx.build_sealed_store_heads_slot(
            [state["index_path"]], state["repo"]
        ),
        repository_root=state["repo"],
    )

    slots = {
        row["name"]: row for row in identity.to_dict()["identity_slots"]
    }
    candidate = slots[tx.CANDIDATE_SLOT]
    assert candidate["state"] == tx.BOUND
    assert candidate["payload"]["decision"]["outcome"] == inner_selection.CANDIDATE
    assert candidate["payload"]["decision"]["fixture_only"] is False


def test_transaction_contract_declares_completed_candidate_support() -> None:
    contract = tx.load_transaction_contract(REPO_ROOT)
    assert contract["identity_policy"][
        "production_candidate_selection_supported_after_tasks_16_18"
    ] is True
    assert "candidate_matrix_task" not in contract["deferred_scope"]
    assert "pbo_task" not in contract["deferred_scope"]
    assert "dsr_task" not in contract["deferred_scope"]
