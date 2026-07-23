from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import production_origin_work_unit as work_unit
from ethusdc_bot.protocol_v3 import production_origin_work_unit_api
from ethusdc_bot.protocol_v3 import transactional_cache as tx
from ethusdc_bot.protocol_v3.boundaries import (
    build_monthly_process_boundary_plan,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
_SUPPORT_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_origin_work_unit_task13_support",
    _SUPPORT_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)


def test_contract_and_public_api_are_canonical() -> None:
    contract = work_unit.load_production_origin_work_unit_contract(
        REPO_ROOT
    )
    assert contract["cycle_policy"]["required_cycles"] == 8
    assert contract["identity_policy"]["real_task15_decision_required"]
    assert contract["origin_policy"][
        "execution_may_remediate_sole_outer_adapter_blocker"
    ]
    assert production_origin_work_unit_api.__all__ == work_unit.__all__


def test_intent_is_atomic_create_only_and_tamper_evident(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    state = support.build_state(tmp_path, monkeypatch)
    artifact = tmp_path / "cycle.json"
    artifact.write_text('{"ok":true}\n', encoding="utf-8")
    intent = work_unit._build_intent(
        identity=state["identity"],
        manifest=state["manifest"],
        artifact_path=artifact,
        artifact_sha256="1" * 64,
        origin_index=1,
        cycle_index=1,
        kind="cycle",
        repo=tmp_path,
    )
    target = tmp_path / "cycle.intent.json"
    work_unit._write_create_only_atomic(target, intent)
    assert work_unit._read_intent(target, tmp_path) == intent
    with pytest.raises(
        work_unit.ProductionOriginWorkUnitError,
        match="create-only",
    ):
        work_unit._write_create_only_atomic(target, intent)

    tampered = json.loads(target.read_text(encoding="utf-8"))
    tampered["cycle_index"] = 2
    target.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(
        work_unit.ProductionOriginWorkUnitError,
        match="digest mismatch",
    ):
        work_unit._read_intent(target, tmp_path)


def test_work_unit_checkpoint_uses_real_task13_identity_and_resumes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    state = support.build_state(tmp_path, monkeypatch)
    artifact = tmp_path / "result.json"
    artifact.write_text('{"result":"NO_TRADE"}\n', encoding="utf-8")
    reference = work_unit._artifact_reference(
        tmp_path,
        artifact,
        "2" * 64,
    )
    checkpoint = work_unit._commit_intent(
        repo=tmp_path,
        ledger_root=state["ledger_root"],
        identity=state["identity"],
        manifest=state["manifest"],
        result_status="NO_TRADE",
        result_payload=reference,
        origin_index=1,
        cycle_index=1,
        stage="inner_search",
    )
    resumed = tx.resume_last_committed_checkpoint(
        current_identity=state["identity"],
        current_pre_run_manifest=state["manifest"],
        repository_root=tmp_path,
    )
    assert resumed == checkpoint
    assert resumed.to_dict()["result"]["payload"] == reference
    assert work_unit._budget(1, 8).cycles_by_origin[0] == 8
    assert tx.inspect_transaction_lock(
        state["identity"].transaction_id,
        tmp_path,
    ) is None


def test_fresh_origin_requires_exact_preflight_ledger_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    state = support.build_state(tmp_path, monkeypatch)
    status = support.read_trial_ledger(state["ledger_root"]).status.to_dict()
    root = tmp_path / "origin"
    root.mkdir()
    work_unit._validate_initial_ledger_binding(
        repo=tmp_path,
        root=root,
        ledger_root=state["ledger_root"],
        initial_status=status,
    )
    stale = dict(status)
    stale["event_count"] -= 1
    with pytest.raises(
        work_unit.ProductionOriginWorkUnitError,
        match="exact preflight ledger head",
    ):
        work_unit._validate_initial_ledger_binding(
            repo=tmp_path,
            root=root,
            ledger_root=state["ledger_root"],
            initial_status=stale,
        )


def test_fold_plan_is_bound_to_selected_origin_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    state = support.build_state(tmp_path, monkeypatch)
    boundary = build_monthly_process_boundary_plan("2026-07-08")
    work_unit._validate_origin_plan_binding(
        boundary_plan=boundary,
        fold_plan=state["inner_fold_plan"],
        origin_index=1,
    )
    with pytest.raises(
        work_unit.ProductionOriginWorkUnitError,
        match="training window differs",
    ):
        work_unit._validate_origin_plan_binding(
            boundary_plan=boundary,
            fold_plan=state["inner_fold_plan"],
            origin_index=2,
        )
