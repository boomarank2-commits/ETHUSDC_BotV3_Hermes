from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import inner_folds as folds
from ethusdc_bot.protocol_v3 import inner_folds_api
from ethusdc_bot.protocol_v3.boundaries import build_monthly_process_boundary_plan
from ethusdc_bot.protocol_v3.runtime_state import (
    HorizonPolicy,
    InformationInterval,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY = HorizonPolicy(120, 180, 2)

_SUPPORT_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task14_support",
    _SUPPORT_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)
tx = support.tx


def _plan(end: datetime = datetime(2026, 7, 8, tzinfo=UTC)) -> folds.InnerFoldPlan:
    return folds.build_inner_fold_plan(
        end - timedelta(days=730),
        end,
        POLICY,
        repo_root=REPO_ROOT,
    )


def _rehash_plan(payload: dict) -> dict:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {**payload, "plan_sha256": hashlib.sha256(canonical.encode()).hexdigest()}


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = folds.load_inner_fold_contract(REPO_ROOT)
    assert contract["contract_version"] == folds.INNER_FOLD_CONTRACT_VERSION
    assert contract["calendar_policy"] == {
        "timezone": "UTC",
        "development_days": 730,
        "validation_fold_count": 6,
        "validation_days_per_fold": 60,
        "validation_union_days": 360,
        "first_fit_days_before_purge": 370,
        "fit_growth_days_per_fold": 60,
        "half_open_intervals": True,
        "validation_folds_strictly_chronological": True,
        "validation_folds_non_overlapping": True,
        "validation_union_is_last_360_development_days": True,
    }
    assert inner_folds_api.__all__ == folds.__all__
    pipeline = json.loads(
        (REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text()
    )
    boundary_sources = pipeline["source_bindings"]["boundary_rules"]
    assert "configs/protocol_v3_inner_fold_contract.json" in boundary_sources
    assert "src/ethusdc_bot/protocol_v3/inner_folds.py" in boundary_sources
    assert "src/ethusdc_bot/protocol_v3/inner_folds_api.py" in boundary_sources
    assert (
        tx.TRANSACTION_CONTRACT_VERSION
        in pipeline["component_contracts"]["quality_gates"]
    )


def test_exact_six_by_sixty_formulas_and_expanding_fits() -> None:
    plan = _plan()
    assert plan == folds.validate_inner_fold_plan(plan, repo_root=REPO_ROOT)
    rows = plan.folds
    assert len(rows) == 6
    assert rows[0].validation_start_inclusive_utc == (
        plan.training_end_exclusive_utc - timedelta(days=360)
    )
    assert rows[-1].validation_end_exclusive_utc == plan.training_end_exclusive_utc
    assert [row.validation_days for row in rows] == [60] * 6
    assert [row.pre_purge_fit_days for row in rows] == [370, 430, 490, 550, 610, 670]
    assert [row.fold_id for row in rows] == [
        "inner_fold_01",
        "inner_fold_02",
        "inner_fold_03",
        "inner_fold_04",
        "inner_fold_05",
        "inner_fold_06",
    ]
    assert all(
        left.validation_end_exclusive_utc == right.validation_start_inclusive_utc
        for left, right in zip(rows, rows[1:])
    )
    assert all(
        row.fit_end_exclusive_utc
        == row.validation_start_inclusive_utc
        - timedelta(minutes=POLICY.purge_duration_minutes)
        for row in rows
    )
    validation_days = {
        row.validation_start_inclusive_utc + timedelta(days=offset)
        for row in rows
        for offset in range(60)
    }
    assert len(validation_days) == 360


@pytest.mark.parametrize("process_end", ["2024-03-08", "2025-03-08", "2026-07-08"])
def test_every_task2_origin_produces_the_same_exact_fold_shape(process_end: str) -> None:
    outer = build_monthly_process_boundary_plan(process_end)
    for origin in outer.origins:
        plan = folds.build_inner_fold_plan_for_origin(
            origin,
            POLICY,
            repo_root=REPO_ROOT,
        )
        assert plan.training_start_inclusive_utc.date() == origin.training_start_inclusive
        assert plan.training_end_exclusive_utc.date() == origin.training_end_exclusive
        assert plan.folds[0].pre_purge_fit_days == 370
        assert plan.folds[-1].pre_purge_fit_days == 670
        assert plan.folds[-1].validation_end_exclusive_utc.date() == origin.training_end_exclusive


def test_plan_rejects_wrong_window_timezone_and_semantic_rehash() -> None:
    end = datetime(2026, 7, 8, tzinfo=UTC)
    with pytest.raises(folds.InnerFoldPlanError, match="exactly 730"):
        folds.build_inner_fold_plan(
            end - timedelta(days=729), end, POLICY, repo_root=REPO_ROOT
        )
    with pytest.raises(folds.InnerFoldPlanError, match="UTC midnight"):
        folds.build_inner_fold_plan(
            end - timedelta(days=730, hours=-1), end, POLICY, repo_root=REPO_ROOT
        )
    payload = _plan().to_dict()
    payload["folds"][2]["validation_start_inclusive_utc"] = "2025-09-10T00:00:00Z"
    tampered = _rehash_plan(payload)
    with pytest.raises(
        folds.InnerFoldPlanError,
        match="pre_purge_fit_days|validation_start formula",
    ):
        folds.validate_inner_fold_plan(tampered, repo_root=REPO_ROOT)
    extra = _plan().to_dict()
    extra["unexpected"] = True
    with pytest.raises(folds.InnerFoldPlanError, match="keys invalid"):
        folds.validate_inner_fold_plan(_rehash_plan(extra), repo_root=REPO_ROOT)


def test_fixed_maximum_purge_and_task9_boundary_touch() -> None:
    plan = _plan()
    fold = plan.folds[0]
    kept = InformationInterval(
        "kept",
        fold.fit_end_ms - 120_000,
        fold.validation_start_ms - 1,
    )
    late_but_short = InformationInterval(
        "late_short",
        fold.fit_end_ms,
        fold.fit_end_ms,
    )
    boundary_touch = InformationInterval(
        "touch",
        fold.fit_end_ms - 60_000,
        fold.validation_start_ms,
    )
    result = folds.purge_fold_training_events(
        plan,
        1,
        [boundary_touch, late_but_short, kept],
        repo_root=REPO_ROOT,
    )
    assert [row.event_id for row in result.kept] == ["kept"]
    assert [row.event_id for row in result.purged] == ["touch", "late_short"]
    at_boundary = InformationInterval(
        "invalid_signal",
        fold.validation_start_ms,
        fold.validation_start_ms,
    )
    with pytest.raises(folds.InnerFoldPlanError, match="strictly before"):
        folds.purge_fold_training_events(
            plan, 1, [at_boundary], repo_root=REPO_ROOT
        )


def test_timestamp_spy_blocks_fit_validation_feature_and_label_leakage() -> None:
    fold = _plan().folds[-1]
    spy = folds.FoldTimestampSpy(fold)
    spy.observe("fit_feature", fold.fit_end_ms - 1)
    spy.observe("validation_signal", fold.validation_start_ms)
    spy.observe("warmup_feature_read", fold.fit_start_ms - 1)
    spy.observe_feature_read(
        decision_time_ms=fold.validation_start_ms,
        source_time_ms=fold.validation_start_ms - 1,
        decision_phase="validation",
    )
    spy.observe_validation_information_interval(
        InformationInterval(
            "valid_validation",
            fold.validation_start_ms,
            fold.validation_end_ms - 1,
        )
    )
    assert spy.observations
    with pytest.raises(folds.InnerFoldPlanError, match="outside the fold fit"):
        spy.observe("scaler_fit", fold.fit_end_ms)
    with pytest.raises(folds.InnerFoldPlanError, match="outside the validation"):
        spy.observe("validation_pnl", fold.validation_end_ms)
    with pytest.raises(folds.InnerFoldPlanError, match="follows its decision"):
        spy.observe_feature_read(
            decision_time_ms=fold.validation_start_ms,
            source_time_ms=fold.validation_start_ms + 1,
            decision_phase="validation",
        )
    with pytest.raises(folds.InnerFoldPlanError, match="reaches or crosses"):
        spy.observe_validation_information_interval(
            InformationInterval(
                "touches_training_end",
                fold.validation_start_ms,
                fold.validation_end_ms,
            )
        )


@pytest.fixture
def transaction_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    return support.build_state(tmp_path, monkeypatch)


def test_transaction_identity_requires_bound_semantic_fold_plan(transaction_state) -> None:
    state = transaction_state
    slot = {
        row["name"]: row for row in state["identity"].to_dict()["identity_slots"]
    }[tx.FOLD_SLOT]
    assert slot["state"] == tx.BOUND
    assert slot["identity_schema"] == folds.INNER_FOLD_IDENTITY_SCHEMA
    assert slot["payload"] == state["inner_fold_plan"].identity_payload

    legacy = tx.build_not_applicable_identity_slot(
        tx.FOLD_SLOT,
        tx.FOLD_PENDING_SCHEMA,
        "task14_not_implemented",
    )
    with pytest.raises(tx.ProtocolV3TransactionError, match="must be BOUND"):
        tx.build_transaction_identity(
            run_fingerprint=state["fingerprint"],
            context_binding=state["binding"],
            horizon_policy=support.HORIZON,
            work_unit_id="origin_01_cycle_01",
            candidate_identity=tx.build_not_applicable_identity_slot(
                tx.CANDIDATE_SLOT,
                tx.CANDIDATE_PENDING_SCHEMA,
                "task15_not_implemented",
            ),
            fold_identity=legacy,
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

    changed = deepcopy(state["inner_fold_plan"].identity_payload)
    changed["plan"]["folds"][0]["fold_id"] = "inner_fold_wrong"
    changed_plan = changed["plan"]
    changed_sha = hashlib.sha256(
        json.dumps(changed_plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    changed["plan_sha256"] = changed_sha
    changed["plan_id"] = f"protocol_v3_inner_fold_plan_sha256:{changed_sha}"
    with pytest.raises(tx.ProtocolV3TransactionError, match="valid Task-14 plan"):
        tx.build_transaction_identity(
            run_fingerprint=state["fingerprint"],
            context_binding=state["binding"],
            horizon_policy=support.HORIZON,
            work_unit_id="origin_01_cycle_01",
            candidate_identity=tx.build_not_applicable_identity_slot(
                tx.CANDIDATE_SLOT,
                tx.CANDIDATE_PENDING_SCHEMA,
                "task15_not_implemented",
            ),
            fold_identity=tx.build_bound_identity_slot(
                tx.FOLD_SLOT,
                tx.FOLD_IDENTITY_SCHEMA,
                changed,
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
