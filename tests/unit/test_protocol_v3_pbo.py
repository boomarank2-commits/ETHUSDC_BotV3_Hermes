from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import inner_selection as selection
from ethusdc_bot.protocol_v3 import pbo
from ethusdc_bot.protocol_v3 import pbo_api
from ethusdc_bot.protocol_v3.trial_ledger import read_trial_ledger

REPO_ROOT = Path(__file__).resolve().parents[2]
_MATRIX_PATH = Path(__file__).with_name("test_protocol_v3_candidate_matrix.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task17_matrix_support", _MATRIX_PATH)
assert _SPEC is not None and _SPEC.loader is not None
matrix_support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(matrix_support)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    return matrix_support.support.build_state(tmp_path, monkeypatch)


def _folds_from_values(plan, values: list[float]):
    assert len(values) == 360
    folds = matrix_support._folds(plan)
    offset = 0
    for fold in folds:
        for row, value in zip(fold["daily_net_mtm_usdc"], values[offset:offset + 60], strict=True):
            row["net_usdc"] = value
        offset += 60
    return folds


def _matrix(state, rows):
    cycles = []
    for cycle, (candidate_id, values) in enumerate(rows, start=1):
        folds = _folds_from_values(state["inner_fold_plan"], values)
        record = matrix_support._trial(state, candidate_id, cycle, folds)
        cycles.append(matrix_support._cycle(candidate_id, record.trial_id, folds, cycle=cycle))
    return matrix_support._build(state, cycles)


def test_contract_public_api_and_pipeline_binding_are_exact() -> None:
    contract = pbo.load_pbo_contract(REPO_ROOT)
    assert contract["contract_version"] == pbo.CONTRACT_VERSION
    assert contract["cash_id"] == pbo.CASH_ID
    assert contract["ranking_policy"]["oos_ties"] == "average_rank"
    assert pbo_api.__all__ == pbo.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert pbo.CONTRACT_VERSION in pipeline["component_contracts"]["ranking"]
    for path in (
        "configs/protocol_v3_pbo_contract.json",
        "src/ethusdc_bot/protocol_v3/pbo.py",
        "src/ethusdc_bot/protocol_v3/pbo_api.py",
    ):
        assert path in pipeline["source_bindings"]["ranking"]


def test_constant_positive_profiles_have_zero_pbo_and_beat_cash(state) -> None:
    candidate_a = matrix_support._candidate(101)
    candidate_b = matrix_support._candidate(102)
    matrix = _matrix(state, [(candidate_a, [1.0] * 360), (candidate_b, [0.5] * 360)])
    evidence = pbo.calculate_pbo(matrix)
    payload = evidence.to_dict()
    assert payload["state"] == pbo.COMPLETE
    assert payload["split_count"] == 924
    assert payload["negative_lambda_count"] == 0
    assert payload["development_pbo"] == 0.0
    assert all(payload["candidate_beats_cash"].values())
    assert pbo.validate_pbo_identity_payload(evidence.identity_payload) == evidence.identity_payload


def test_mirrored_overfit_profiles_have_pbo_one(state) -> None:
    candidate_a = matrix_support._candidate(103)
    candidate_b = matrix_support._candidate(104)
    a = [1.0] * 180 + [-1.0] * 180
    b = [-1.0] * 180 + [1.0] * 180
    payload = pbo.calculate_pbo(_matrix(state, [(candidate_a, a), (candidate_b, b)])).to_dict()
    assert payload["negative_lambda_count"] == 924
    assert payload["development_pbo"] == 1.0
    assert not any(payload["candidate_beats_cash"].values())


def test_identical_zero_profiles_use_average_rank_and_have_pbo_one(state) -> None:
    candidate_a = matrix_support._candidate(105)
    candidate_b = matrix_support._candidate(106)
    payload = pbo.calculate_pbo(
        _matrix(state, [(candidate_b, [0.0] * 360), (candidate_a, [0.0] * 360)])
    ).to_dict()
    assert payload["development_pbo"] == 1.0
    assert all(row["oos_average_rank"] == 2.0 for row in payload["splits"])
    assert all(row["lambda"] == 0.0 for row in payload["splits"])
    assert not any(payload["candidate_beats_cash"].values())


def test_all_924_splits_are_unique_exact_complements_of_180_days(state) -> None:
    matrix = _matrix(
        state,
        [
            (matrix_support._candidate(107), [1.0] * 360),
            (matrix_support._candidate(108), [0.5] * 360),
        ],
    )
    rows = pbo.calculate_pbo(matrix).to_dict()["splits"]
    assert len(rows) == 924
    assert len({tuple(row["is_blocks"]) for row in rows}) == 924
    for row in rows:
        assert row["is_day_count"] == row["oos_day_count"] == 180
        assert set(row["is_blocks"]).isdisjoint(row["oos_blocks"])
        assert sorted(row["is_blocks"] + row["oos_blocks"]) == list(range(12))


def test_fewer_than_two_profiles_is_typed_insufficient_without_number(state) -> None:
    matrix = _matrix(state, [(matrix_support._candidate(109), [1.0] * 360)])
    payload = pbo.calculate_pbo(matrix).to_dict()
    assert payload["state"] == pbo.INSUFFICIENT_EVIDENCE
    assert payload["development_pbo"] is None
    assert payload["negative_lambda_count"] is None
    assert payload["split_count"] == 0
    support = selection.build_pbo_development_support(pbo.calculate_pbo(matrix), cycle_index=1)
    assert support.to_dict()["pbo"]["state"] == selection.INSUFFICIENT_EVIDENCE


def test_task17_support_is_complete_but_selection_stays_no_trade_without_dsr(state) -> None:
    candidate_a = matrix_support._candidate(110)
    candidate_b = matrix_support._candidate(111)
    matrix = _matrix(state, [(candidate_a, [1.0] * 360), (candidate_b, [0.5] * 360)])
    evidence = pbo.calculate_pbo(matrix)
    development = selection.build_pbo_development_support(evidence, cycle_index=1)
    payload = development.to_dict()
    assert payload["matrix"]["state"] == selection.COMPLETE
    assert payload["pbo"]["state"] == selection.COMPLETE
    assert payload["dsr"]["state"] == selection.INSUFFICIENT_EVIDENCE
    assert payload["pbo"]["value"] == evidence.identity_payload
    config = selection.build_frozen_selection_config(
        pre_run_manifest=state["manifest"],
        run_fingerprint=state["fingerprint"],
        fold_identity=state["inner_fold_plan"].identity_payload,
        origin_index=1,
        cycle_index=1,
        generated_candidate_ids=[candidate_a],
        tested_candidate_ids=[candidate_a],
        walk_forward_candidate_ids=[],
        finalist_candidate_ids=[],
        candidate_evidence=[],
        development_support=development,
    )
    decision = selection.select_candidate(state["training_window"], config)
    assert decision.outcome == selection.NO_TRADE
    assert "TASK17_PBO_INSUFFICIENT_EVIDENCE" not in decision.to_dict()["blockers"]
    assert "TASK18_DSR_INSUFFICIENT_EVIDENCE" in decision.to_dict()["blockers"]


def test_tampered_rehashed_pbo_and_permuted_day_grid_block(state) -> None:
    matrix = _matrix(
        state,
        [
            (matrix_support._candidate(112), [1.0] * 360),
            (matrix_support._candidate(113), [0.5] * 360),
        ],
    )
    payload = pbo.calculate_pbo(matrix).to_dict()
    payload["development_pbo"] = 0.5
    basis = dict(payload); basis.pop("evidence_sha256")
    payload["evidence_sha256"] = pbo._digest(basis)
    with pytest.raises(pbo.PBOError, match="recomputation"):
        pbo.validate_pbo_evidence(payload)

    bad_matrix = deepcopy(matrix.to_dict())
    bad_matrix["day_grid"][0], bad_matrix["day_grid"][1] = bad_matrix["day_grid"][1], bad_matrix["day_grid"][0]
    with pytest.raises(Exception):
        pbo.calculate_pbo(bad_matrix)
