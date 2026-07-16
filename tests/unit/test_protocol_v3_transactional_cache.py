"""Task-13 tests for content-addressed cache and transactional resume."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import ethusdc_bot.protocol_v3.reporting as reporting_module

_SUPPORT_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task13_support", _SUPPORT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)

tx = support.tx
transactional_cache_api = support.transactional_cache_api
read_trial_ledger = support.read_trial_ledger
REPO_ROOT = support.REPO_ROOT
_commit = support._commit


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    return support.build_state(tmp_path, monkeypatch)


def test_contract_public_api_and_pipeline_binding_are_exact() -> None:
    contract = tx.load_transaction_contract(REPO_ROOT)
    assert contract["contract_version"] == tx.TRANSACTION_CONTRACT_VERSION
    assert contract["identity_policy"]["required_slots"] == list(tx.REQUIRED_IDENTITY_SLOTS)
    assert transactional_cache_api.__all__ == tx.__all__
    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert tx.TRANSACTION_CONTRACT_VERSION in pipeline["component_contracts"]["quality_gates"]
    for path in (
        "configs/protocol_v3_transaction_contract.json",
        "src/ethusdc_bot/protocol_v3/transactional_cache.py",
        "src/ethusdc_bot/protocol_v3/transactional_cache_api.py",
        "src/ethusdc_bot/protocol_v3/transactional_cache_model.py",
        "src/ethusdc_bot/protocol_v3/transactional_cache_store.py",
    ):
        assert path in pipeline["source_bindings"]["quality_gates"]


def test_real_identity_binds_all_slots_and_missing_or_none_blocks(state) -> None:
    payload = state["identity"].to_dict()
    assert [row["name"] for row in payload["identity_slots"]] == list(tx.REQUIRED_IDENTITY_SLOTS)
    assert payload["context_binding"]["context_identity_sha256"] == state["binding"].context_identity_sha256
    missing = deepcopy(payload)
    missing["identity_slots"].pop()
    with pytest.raises(tx.ProtocolV3TransactionError, match="missing, extra, or reordered"):
        tx.validate_transaction_identity(missing, repository_root=state["repo"])
    none_value = deepcopy(payload)
    none_value["identity_slots"][-1] = None
    with pytest.raises(tx.ProtocolV3TransactionError):
        tx.validate_transaction_identity(none_value, repository_root=state["repo"])


def test_checkpoint_roundtrip_chain_and_new_process_reload(state) -> None:
    _commit(state, status="IN_PROGRESS", payload={"step": 1})
    state["stop"] = tx.build_stop_state(completed_cycles=1, consecutive_non_improving_cycles=0)
    second = _commit(state, payload={"step": 2})
    assert second.sequence == 2
    assert tx.read_last_committed_checkpoint(state["identity"].transaction_id, state["repo"]) == second
    assert tx.resume_last_committed_checkpoint(
        current_identity=state["identity"],
        current_pre_run_manifest=state["manifest"],
        repository_root=state["repo"],
    ) == second
    code = (
        "from ethusdc_bot.protocol_v3.transactional_cache_api import read_last_committed_checkpoint;"
        f"x=read_last_committed_checkpoint('{state['identity'].transaction_id}',r'{state['repo']}');"
        "print(x.checkpoint_sha256)"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run([sys.executable, "-c", code], text=True, capture_output=True, check=True, env=env)
    assert result.stdout.strip() == second.checkpoint_sha256


def test_faults_before_head_do_not_publish_and_after_head_do(state) -> None:
    baseline = _commit(state, status="IN_PROGRESS", payload={"step": 1})
    state["stop"] = tx.build_stop_state(completed_cycles=1, consecutive_non_improving_cycles=0)
    for phase in (
        "before_checkpoint_temp", "after_checkpoint_temp_fsync",
        "after_checkpoint_temp_validate", "after_checkpoint_replace",
        "after_checkpoint_reload", "before_head_replace",
    ):
        def fail(observed, target=phase):
            if observed == target:
                raise RuntimeError(target)
        with pytest.raises(RuntimeError, match=phase):
            _commit(state, payload={"step": phase}, fault=fail)
        assert tx.read_last_committed_checkpoint(state["identity"].transaction_id, state["repo"]) == baseline

    def after_head(observed):
        if observed == "after_head_replace":
            raise RuntimeError(observed)

    with pytest.raises(RuntimeError, match="after_head_replace"):
        _commit(state, payload={"step": "visible"}, fault=after_head)
    assert tx.read_last_committed_checkpoint(state["identity"].transaction_id, state["repo"]).sequence == 2


def test_cache_hit_revalidates_checkpoint_artifacts_and_each_identity(state) -> None:
    checkpoint = _commit(state)
    record = tx.publish_cache_record(
        checkpoint=checkpoint,
        repository_root=state["repo"],
        trial_ledger_root=state["ledger_root"],
        trial_id=state["record"].trial_id,
    )
    assert tx.lookup_cache_record(
        state["identity"], state["repo"], trial_ledger_root=state["ledger_root"]
    ) == record
    changed = deepcopy(state["identity"].to_dict())
    changed["work_unit_id"] = "origin_01_cycle_02"
    basis = dict(changed)
    basis.pop("identity_sha256")
    basis.pop("transaction_id")
    digest = hashlib.sha256(
        json.dumps(basis, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    changed["identity_sha256"] = digest
    changed["transaction_id"] = f"protocol_v3_transaction_sha256:{digest}"
    changed_identity = tx.validate_transaction_identity(changed, repository_root=state["repo"])
    assert tx.lookup_cache_record(
        changed_identity, state["repo"], trial_ledger_root=state["ledger_root"]
    ) is None

    artifact = next((state["repo"] / "reports/protocol_v3/artifacts/objects").rglob("*.json"))
    artifact.write_bytes(artifact.read_bytes()[:20])
    with pytest.raises(Exception):
        tx.lookup_cache_record(
            state["identity"], state["repo"], trial_ledger_root=state["ledger_root"]
        )


def test_cache_reuse_crash_retry_records_one_ledger_event(state) -> None:
    checkpoint = _commit(state)
    record = tx.publish_cache_record(
        checkpoint=checkpoint,
        repository_root=state["repo"],
        trial_ledger_root=state["ledger_root"],
        trial_id=state["record"].trial_id,
    )

    def fail(phase):
        if phase == "after_ledger_reuse_append":
            raise RuntimeError(phase)

    with pytest.raises(RuntimeError, match="after_ledger_reuse_append"):
        _commit(state, cache_record=record, fault=fail)
    after_crash = read_trial_ledger(state["ledger_root"])
    assert after_crash.status.cache_reuse_count == 1
    resumed = _commit(state, cache_record=record)
    assert resumed.to_dict()["ledger_receipt"]["state"] == "CACHE_REUSE_RECORDED"
    assert read_trial_ledger(state["ledger_root"]).status.cache_reuse_count == 1


def test_exclusive_lock_and_evidence_based_recovery(state) -> None:
    lock = tx.acquire_transaction_lock(
        state["identity"].transaction_id, state["repo"], owner_id="owner"
    )
    with pytest.raises(tx.ProtocolV3TransactionError, match="blind overwrite"):
        tx.acquire_transaction_lock(
            state["identity"].transaction_id, state["repo"], owner_id="other"
        )
    with pytest.raises(tx.ProtocolV3TransactionError, match="still alive"):
        tx.recover_stale_transaction_lock(state["identity"].transaction_id, state["repo"])
    tx.release_transaction_lock(lock, state["repo"])


def test_dead_same_host_lock_can_be_recovered_with_receipt(state) -> None:
    code = (
        "from ethusdc_bot.protocol_v3.transactional_cache_api import acquire_transaction_lock;"
        f"acquire_transaction_lock('{state['identity'].transaction_id}',r'{state['repo']}',owner_id='dead_owner')"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    subprocess.run(
        [sys.executable, "-c", code], text=True, capture_output=True, check=True, env=env
    )
    assert tx.inspect_transaction_lock(
        state["identity"].transaction_id, state["repo"]
    ) is not None
    receipt = tx.recover_stale_transaction_lock(
        state["identity"].transaction_id, state["repo"]
    )
    assert receipt.exists()
    assert tx.inspect_transaction_lock(
        state["identity"].transaction_id, state["repo"]
    ) is None


def test_truncated_head_duplicate_json_and_symlink_fail_closed(state) -> None:
    _commit(state)
    head = (
        state["repo"] / tx.CHECKPOINT_ROOT
        / state["identity"].identity_sha256 / "HEAD.json"
    )
    head.write_bytes(head.read_bytes()[:20])
    with pytest.raises(tx.ProtocolV3TransactionError):
        tx.read_last_committed_checkpoint(
            state["identity"].transaction_id, state["repo"]
        )

    outside = state["repo"] / "outside.json"
    outside.write_text('{"a":1,"a":2}', encoding="utf-8")
    cache_root = state["repo"] / tx.CACHE_ROOT
    cache_root.mkdir(parents=True, exist_ok=True)
    linked = cache_root / state["identity"].identity_sha256[:2]
    try:
        linked.symlink_to(outside)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(tx.ProtocolV3TransactionError):
        tx.lookup_cache_record(
            state["identity"], state["repo"], trial_ledger_root=state["ledger_root"]
        )
