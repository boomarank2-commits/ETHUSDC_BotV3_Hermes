"""Regression tests for the Task-13/Task-4 ledger event adapter."""
from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pytest

import ethusdc_bot.protocol_v3.reporting as reporting_module
from ethusdc_bot.protocol_v3.trial_ledger import (
    read_trial_ledger,
    record_cache_reuse,
)

_SUPPORT_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task13_support_adapter",
    _SUPPORT_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)

tx = support.tx
_commit = support._commit


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    return support.build_state(tmp_path, monkeypatch)


def test_receipt_binds_real_event_sha256_and_foreign_advance_blocks(state) -> None:
    checkpoint = _commit(state)
    record = tx.publish_cache_record(
        checkpoint=checkpoint,
        repository_root=state["repo"],
        trial_ledger_root=state["ledger_root"],
        trial_id=state["record"].trial_id,
    )

    reused = _commit(state, cache_record=record)
    receipt = reused.to_dict()["ledger_receipt"]
    ledger = read_trial_ledger(state["ledger_root"])
    event = ledger.events[-1]

    assert "event_sha256" in event
    assert "event_hash" not in event
    assert receipt["event_hash"] == event["event_sha256"]
    assert ledger.status.head_sha256 == event["event_sha256"]

    record_cache_reuse(
        state["ledger_root"],
        trial_id=state["record"].trial_id,
        reuse_scope={"foreign": "ledger_advance"},
    )
    with pytest.raises(tx.ProtocolV3TransactionError, match="no longer the head"):
        _commit(state, payload={"step": "must_block"})
