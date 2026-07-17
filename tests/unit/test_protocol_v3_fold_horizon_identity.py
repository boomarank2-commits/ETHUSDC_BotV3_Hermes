from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pytest

import ethusdc_bot.protocol_v3.reporting as reporting_module
from ethusdc_bot.protocol_v3.inner_folds import build_inner_fold_plan
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy

_SUPPORT_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC = importlib.util.spec_from_file_location("task14_support_horizon", _SUPPORT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)
tx = support.tx


def test_fold_plan_must_use_the_transaction_horizon(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    state = support.build_state(tmp_path, monkeypatch)
    other_policy = HorizonPolicy(11, 10, 2)
    other_plan = build_inner_fold_plan(
        state["inner_fold_plan"].training_start_inclusive_utc,
        state["inner_fold_plan"].training_end_exclusive_utc,
        other_policy,
        repo_root=support.REPO_ROOT,
    )
    with pytest.raises(
        tx.ProtocolV3TransactionError,
        match="horizon differs from transaction horizon identity",
    ):
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
                other_plan.identity_payload,
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
