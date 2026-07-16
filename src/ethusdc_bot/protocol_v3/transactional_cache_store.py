"""Filesystem transaction, checkpoint and cache store for Protocol v3 Task 13."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import errno
import hashlib
import os
from pathlib import Path, PurePosixPath
import socket
from typing import Any

from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.protocol_v3.pipeline import BudgetUsage, PreRunManifest, validate_pre_run_manifest
from ethusdc_bot.protocol_v3.trial_ledger import read_trial_ledger, record_cache_reuse
from . import transactional_cache_model as m

FaultInjector = Callable[[str], None]


def acquire_transaction_lock(transaction_id: str, repository_root: str | Path, *, owner_id: str) -> m.TransactionLock:
    tx_id = m.transaction_id(transaction_id); owner = m.safe_id(owner_id, "owner_id"); repo = m.repo_root(repository_root)
    root = _safe_root(repo, m.LOCK_ROOT, create=True); path = root / f"{tx_id.rsplit(':', 1)[1]}.lock.json"
    basis = {"schema_version": m.LOCK_SCHEMA_VERSION, "protocol_version": m.PROTOCOL_VERSION, "transaction_id": tx_id, "owner_id": owner, "process_id": os.getpid(), "host_sha256": _host_sha256(), "acquired_at_utc": _utc_now()}
    payload = {**basis, "lock_sha256": m.digest(basis)}
    try: _write_create_only(path, m.canonical_bytes(payload))
    except FileExistsError as exc:
        existing = _read_lock(path, repo).to_dict()
        raise m.ProtocolV3TransactionError(f"transaction lock is already held or stale; blind overwrite is forbidden (owner={existing['owner_id']}, process_id={existing['process_id']})") from exc
    return _read_lock(path, repo)


def inspect_transaction_lock(transaction_id: str, repository_root: str | Path) -> m.TransactionLock | None:
    tx_id = m.transaction_id(transaction_id); repo = m.repo_root(repository_root); root = _safe_root(repo, m.LOCK_ROOT, create=True)
    path = root / f"{tx_id.rsplit(':', 1)[1]}.lock.json"
    return None if not path.exists() else _read_lock(path, repo)


def release_transaction_lock(lock: m.TransactionLock, repository_root: str | Path) -> None:
    repo = m.repo_root(repository_root); current = _read_lock(lock.path, repo)
    if current != lock: raise m.ProtocolV3TransactionError("transaction lock changed; refusing release")
    if current.to_dict()["process_id"] != os.getpid(): raise m.ProtocolV3TransactionError("transaction lock is owned by a different process")
    current.path.unlink(); _fsync_directory(current.path.parent)


def recover_stale_transaction_lock(transaction_id: str, repository_root: str | Path) -> Path:
    lock = inspect_transaction_lock(transaction_id, repository_root)
    if lock is None: raise m.ProtocolV3TransactionError("no transaction lock exists to recover")
    payload = lock.to_dict()
    if payload["host_sha256"] != _host_sha256(): raise m.ProtocolV3TransactionError("lock host is different or unclear; recovery blocked")
    alive = _process_alive(payload["process_id"])
    if alive is True: raise m.ProtocolV3TransactionError("transaction lock process is still alive")
    if alive is None: raise m.ProtocolV3TransactionError("transaction lock process state is unclear")
    repo = m.repo_root(repository_root); recovery = _safe_root(repo, m.LOCK_RECOVERY_ROOT, create=True); target = recovery / f"{lock.lock_sha256}.json"
    if target.exists():
        existing, raw = _read_object(target, recovery)
        if existing != payload or raw != m.canonical_bytes(payload): raise m.ProtocolV3TransactionError("recovered-lock receipt conflicts")
        lock.path.unlink()
    else: os.replace(lock.path, target)
    _fsync_directory(target.parent); _fsync_directory(lock.path.parent); return target


def commit_checkpoint(*, identity: m.TransactionIdentity, pre_run_manifest: PreRunManifest, seed_state: Mapping[str, Any], budget_usage: BudgetUsage, stop_state: Mapping[str, Any], result_status: str, result_payload: Mapping[str, Any], repository_root: str | Path, trial_ledger_root: str | Path, lock: m.TransactionLock, cache_record: m.CacheRecord | None = None, fault_injector: FaultInjector | None = None) -> m.TransactionCheckpoint:
    repo = m.repo_root(repository_root); identity = m.validate_transaction_identity(identity, repository_root=repo); validate_pre_run_manifest(pre_run_manifest)
    manifest = pre_run_manifest.payload(); run = identity.to_dict()["run_fingerprint"]
    if manifest["code_commit"] != run["code"]["git_commit"]: raise m.ProtocolV3TransactionError("pre-run manifest code differs from run fingerprint")
    if manifest["pipeline_generation"]["generation_id"] != run["pipeline"]["generation_id"]: raise m.ProtocolV3TransactionError("pre-run manifest pipeline differs from run fingerprint")
    seed = m.validate_seed_state(seed_state, pre_run_manifest); budget = m.budget_mapping(budget_usage)
    budget_state = {"schema_version": "protocol_v3_checkpoint_budget_state_v1", "usage": budget, "budget_state_sha256": m.digest(budget)}
    stop = m.validate_stop_state(stop_state); _assert_lock(lock, identity.transaction_id, repo)
    tx_root = _checkpoint_root(repo, identity.transaction_id, create=True); previous = read_last_committed_checkpoint(identity.transaction_id, repo)
    receipt = _resolve_ledger_receipt(identity, trial_ledger_root, cache_record, previous, fault_injector, repo)
    if cache_record is not None:
        record = validate_cache_record(cache_record, repository_root=repo)
        if record.to_dict()["transaction_id"] != identity.transaction_id: raise m.ProtocolV3TransactionError("cache record identity differs from checkpoint")
        result = record.to_dict()["result"]; heads = record.to_dict()["artifact_indexes"]
    else:
        if result_status not in {"IN_PROGRESS", "COMPLETED", "NO_TRADE", "BLOCKED"}: raise m.ProtocolV3TransactionError("checkpoint result_status is invalid")
        payload = dict(m.require_mapping(result_payload, "result_payload")); m.reject_raw(payload, "result_payload"); m.finite_json(payload, "result_payload")
        basis = {"status": result_status, "payload": payload}; result = {**basis, "result_sha256": m.digest(basis)}; heads = m.store_heads_from_identity(identity)
    state_basis = {"identity_sha256": identity.identity_sha256, "pre_run_manifest_sha256": pre_run_manifest.manifest_sha256, "seed_state": seed, "budget_state": budget_state, "stop_state": stop, "result": result, "artifact_indexes": heads, "ledger_receipt": receipt}
    state_sha = m.digest(state_basis)
    if previous is not None and previous.to_dict()["state_sha256"] == state_sha: return previous
    sequence = 1 if previous is None else previous.sequence + 1; previous_sha = m.ZERO_HASH if previous is None else previous.checkpoint_sha256
    basis = {"schema_version": m.CHECKPOINT_SCHEMA_VERSION, "protocol_version": m.PROTOCOL_VERSION, "contract_version": m.TRANSACTION_CONTRACT_VERSION, "transaction_id": identity.transaction_id, "sequence": sequence, "previous_checkpoint_sha256": previous_sha, "state_sha256": state_sha, "identity": identity.to_dict(), "pre_run_manifest": pre_run_manifest.to_dict(), "seed_state": seed, "budget_state": budget_state, "stop_state": stop, "result": result, "artifact_indexes": heads, "ledger_receipt": receipt, "safety": m.SAFETY}
    checkpoint_sha = m.digest(basis); checkpoint = validate_checkpoint({**basis, "checkpoint_id": f"{m.CHECKPOINT_PREFIX}:{checkpoint_sha}", "checkpoint_sha256": checkpoint_sha}, repository_root=repo)
    committed = tx_root / "committed"; _ensure_directory(repo, committed); final_path = committed / f"{checkpoint_sha}.json"
    _fault(fault_injector, "before_checkpoint_temp"); _publish_checkpoint(final_path, m.canonical_bytes(checkpoint.to_dict()), lock.to_dict()["owner_id"], fault_injector)
    _fault(fault_injector, "after_checkpoint_replace")
    if _read_checkpoint(final_path, repo) != checkpoint: raise m.ProtocolV3TransactionError("committed checkpoint reload mismatch")
    _fault(fault_injector, "after_checkpoint_reload")
    head_basis = {"schema_version": m.CHECKPOINT_HEAD_SCHEMA_VERSION, "protocol_version": m.PROTOCOL_VERSION, "transaction_id": identity.transaction_id, "sequence": sequence, "checkpoint_id": checkpoint.checkpoint_id, "checkpoint_sha256": checkpoint.checkpoint_sha256}
    _fault(fault_injector, "before_head_replace"); _atomic_replace(tx_root / "HEAD.json", m.canonical_bytes({**head_basis, "head_sha256": m.digest(head_basis)}), lock.to_dict()["owner_id"], repo)
    if read_last_committed_checkpoint(identity.transaction_id, repo) != checkpoint: raise m.ProtocolV3TransactionError("checkpoint HEAD did not commit the expected state")
    _fault(fault_injector, "after_head_replace"); return checkpoint


def read_last_committed_checkpoint(transaction_id: str, repository_root: str | Path) -> m.TransactionCheckpoint | None:
    tx_id = m.transaction_id(transaction_id); repo = m.repo_root(repository_root); root = _checkpoint_root(repo, tx_id, create=True); head_path = root / "HEAD.json"
    if not head_path.exists(): return None
    head, raw = _read_object(_guard(head_path, root, repo), root); _validate_head(head)
    if raw != m.canonical_bytes(head): raise m.ProtocolV3TransactionError("checkpoint HEAD bytes are not canonical")
    if head["transaction_id"] != tx_id: raise m.ProtocolV3TransactionError("checkpoint HEAD transaction mismatch")
    checkpoint = _read_checkpoint(root / "committed" / f"{head['checkpoint_sha256']}.json", repo)
    if checkpoint.checkpoint_id != head["checkpoint_id"] or checkpoint.checkpoint_sha256 != head["checkpoint_sha256"] or checkpoint.sequence != head["sequence"]: raise m.ProtocolV3TransactionError("checkpoint HEAD target mismatch")
    _validate_chain(checkpoint, root, repo); return checkpoint


def resume_last_committed_checkpoint(*, current_identity: m.TransactionIdentity, current_pre_run_manifest: PreRunManifest, repository_root: str | Path) -> m.TransactionCheckpoint | None:
    repo = m.repo_root(repository_root); identity = m.validate_transaction_identity(current_identity, repository_root=repo); validate_pre_run_manifest(current_pre_run_manifest)
    checkpoint = read_last_committed_checkpoint(identity.transaction_id, repo)
    if checkpoint is None: return None
    payload = checkpoint.to_dict()
    if payload["identity"] != identity.to_dict(): raise m.ProtocolV3TransactionError("resume blocked: transaction identity changed")
    if payload["pre_run_manifest"] != current_pre_run_manifest.to_dict(): raise m.ProtocolV3TransactionError("resume blocked: pre-run manifest changed")
    return checkpoint


def publish_cache_record(*, checkpoint: m.TransactionCheckpoint, repository_root: str | Path, trial_ledger_root: str | Path, trial_id: str) -> m.CacheRecord:
    repo = m.repo_root(repository_root); checkpoint = validate_checkpoint(checkpoint, repository_root=repo); payload = checkpoint.to_dict()
    if read_last_committed_checkpoint(payload["transaction_id"], repo) != checkpoint: raise m.ProtocolV3TransactionError("cache publication requires the current committed checkpoint HEAD")
    if payload["result"]["status"] not in {"COMPLETED", "NO_TRADE"}: raise m.ProtocolV3TransactionError("only completed or NO_TRADE checkpoints are cacheable")
    ledger = read_trial_ledger(trial_ledger_root)
    if trial_id not in ledger.trials: raise m.ProtocolV3TransactionError("cache record trial_id is absent from permanent ledger")
    identity = m.validate_transaction_identity(payload["identity"], repository_root=repo); relative = _checkpoint_relative(checkpoint)
    basis = {"schema_version": m.CACHE_RECORD_SCHEMA_VERSION, "protocol_version": m.PROTOCOL_VERSION, "contract_version": m.TRANSACTION_CONTRACT_VERSION, "cache_key": identity.cache_key, "transaction_id": identity.transaction_id, "identity_sha256": identity.identity_sha256, "work_unit_id": identity.work_unit_id, "checkpoint_id": checkpoint.checkpoint_id, "checkpoint_sha256": checkpoint.checkpoint_sha256, "checkpoint_relative_path": relative.as_posix(), "trial_id": trial_id, "result": payload["result"], "artifact_indexes": payload["artifact_indexes"], "safety": m.SAFETY}
    record_sha = m.digest(basis); record = validate_cache_record({**basis, "cache_record_id": f"{m.CACHE_PREFIX}:{record_sha}", "cache_record_sha256": record_sha}, repository_root=repo)
    root = _safe_root(repo, m.CACHE_ROOT, create=True); path = _cache_path(identity, root, repo); _publish_immutable(path, m.canonical_bytes(record.to_dict()))
    return _read_cache(path, repo)


def lookup_cache_record(identity: m.TransactionIdentity, repository_root: str | Path, *, trial_ledger_root: str | Path) -> m.CacheRecord | None:
    repo = m.repo_root(repository_root); identity = m.validate_transaction_identity(identity, repository_root=repo); root = _safe_root(repo, m.CACHE_ROOT, create=True); path = _cache_path(identity, root, repo)
    if not path.exists(): return None
    record = _read_cache(path, repo)
    if record.to_dict()["identity_sha256"] != identity.identity_sha256: raise m.ProtocolV3TransactionError("cache hit blocked: complete identity changed")
    _validate_cache_ledger(record, identity, trial_ledger_root); return record


def validate_cache_record(value: m.CacheRecord | Mapping[str, Any], *, repository_root: str | Path) -> m.CacheRecord:
    root = value.to_dict() if isinstance(value, m.CacheRecord) else dict(m.require_mapping(value, "cache_record"))
    m.exact_keys(root, {"schema_version", "protocol_version", "contract_version", "cache_key", "transaction_id", "identity_sha256", "work_unit_id", "checkpoint_id", "checkpoint_sha256", "checkpoint_relative_path", "trial_id", "result", "artifact_indexes", "safety", "cache_record_id", "cache_record_sha256"}, "cache_record")
    m.literal(root, "schema_version", m.CACHE_RECORD_SCHEMA_VERSION, "cache_record"); m.literal(root, "protocol_version", m.PROTOCOL_VERSION, "cache_record"); m.literal(root, "contract_version", m.TRANSACTION_CONTRACT_VERSION, "cache_record")
    tx_id = m.transaction_id(root["transaction_id"]); identity_sha = m.sha256(root["identity_sha256"], "cache_record.identity_sha256")
    if root["cache_key"] != f"{m.CACHE_PREFIX}:{identity_sha}": raise m.ProtocolV3TransactionError("cache record key does not match identity")
    m.safe_id(root["work_unit_id"], "cache_record.work_unit_id"); checkpoint_id = m.checkpoint_id(root["checkpoint_id"]); checkpoint_sha = m.sha256(root["checkpoint_sha256"], "cache_record.checkpoint_sha256")
    relative = m.safe_relative(root["checkpoint_relative_path"], "cache checkpoint path"); expected_relative = PurePosixPath(m.CHECKPOINT_ROOT, tx_id.rsplit(":", 1)[1], "committed", f"{checkpoint_sha}.json")
    if relative != expected_relative: raise m.ProtocolV3TransactionError("cache checkpoint path is not canonical")
    m.required_text(root["trial_id"], "cache_record.trial_id"); result = _validate_result(root["result"]); heads = m.validate_artifact_heads(root["artifact_indexes"], repository_root)
    if root["safety"] != m.SAFETY: raise m.ProtocolV3TransactionError("cache record safety locks are invalid")
    observed = m.sha256(root["cache_record_sha256"], "cache_record.cache_record_sha256"); record_id = m.cache_id(root["cache_record_id"]); basis = dict(root); basis.pop("cache_record_id"); basis.pop("cache_record_sha256"); expected = m.digest(basis)
    if observed != expected or record_id != f"{m.CACHE_PREFIX}:{expected}": raise m.ProtocolV3TransactionError("cache record digest or id mismatch")
    repo = m.repo_root(repository_root); checkpoint = _read_checkpoint(repo.joinpath(*relative.parts), repo); committed = read_last_committed_checkpoint(tx_id, repo)
    if committed != checkpoint: raise m.ProtocolV3TransactionError("cache checkpoint is not the current committed checkpoint HEAD")
    checkpoint_payload = checkpoint.to_dict()
    if checkpoint.checkpoint_id != checkpoint_id or checkpoint_payload["identity"]["identity_sha256"] != identity_sha: raise m.ProtocolV3TransactionError("cache checkpoint identity mismatch")
    if checkpoint_payload["result"] != result or checkpoint_payload["artifact_indexes"] != heads: raise m.ProtocolV3TransactionError("cache content differs from checkpoint")
    return m.CacheRecord(m.canonical(root), expected, record_id)


def validate_checkpoint(value: m.TransactionCheckpoint | Mapping[str, Any], *, repository_root: str | Path) -> m.TransactionCheckpoint:
    root = value.to_dict() if isinstance(value, m.TransactionCheckpoint) else dict(m.require_mapping(value, "checkpoint"))
    m.exact_keys(root, {"schema_version", "protocol_version", "contract_version", "transaction_id", "sequence", "previous_checkpoint_sha256", "state_sha256", "identity", "pre_run_manifest", "seed_state", "budget_state", "stop_state", "result", "artifact_indexes", "ledger_receipt", "safety", "checkpoint_id", "checkpoint_sha256"}, "checkpoint")
    m.literal(root, "schema_version", m.CHECKPOINT_SCHEMA_VERSION, "checkpoint"); m.literal(root, "protocol_version", m.PROTOCOL_VERSION, "checkpoint"); m.literal(root, "contract_version", m.TRANSACTION_CONTRACT_VERSION, "checkpoint")
    tx_id = m.transaction_id(root["transaction_id"]); sequence = m.positive_int(root["sequence"], "checkpoint.sequence"); previous = m.sha256(root["previous_checkpoint_sha256"], "checkpoint.previous_checkpoint_sha256")
    if sequence == 1 and previous != m.ZERO_HASH: raise m.ProtocolV3TransactionError("first checkpoint must use the zero previous hash")
    identity = m.validate_transaction_identity(root["identity"], repository_root=repository_root)
    if identity.transaction_id != tx_id: raise m.ProtocolV3TransactionError("checkpoint transaction identity mismatch")
    manifest = m.manifest_from_mapping(dict(m.require_mapping(root["pre_run_manifest"], "checkpoint.pre_run_manifest"))); seed = m.validate_seed_state(root["seed_state"], manifest)
    budget_state = dict(m.require_mapping(root["budget_state"], "checkpoint.budget_state")); m.exact_keys(budget_state, {"schema_version", "usage", "budget_state_sha256"}, "checkpoint.budget_state"); m.literal(budget_state, "schema_version", "protocol_v3_checkpoint_budget_state_v1", "checkpoint.budget_state")
    usage = dict(m.require_mapping(budget_state["usage"], "checkpoint.budget_state.usage")); m.validate_budget_mapping(usage)
    if budget_state["budget_state_sha256"] != m.digest(usage): raise m.ProtocolV3TransactionError("checkpoint budget digest mismatch")
    stop = m.validate_stop_state(root["stop_state"]); result = _validate_result(root["result"]); heads = m.validate_artifact_heads(root["artifact_indexes"], repository_root); receipt = _validate_ledger_receipt(root["ledger_receipt"], identity)
    state_basis = {"identity_sha256": identity.identity_sha256, "pre_run_manifest_sha256": manifest.manifest_sha256, "seed_state": seed, "budget_state": budget_state, "stop_state": stop, "result": result, "artifact_indexes": heads, "ledger_receipt": receipt}
    if root["state_sha256"] != m.digest(state_basis): raise m.ProtocolV3TransactionError("checkpoint state digest mismatch")
    if root["safety"] != m.SAFETY: raise m.ProtocolV3TransactionError("checkpoint safety locks are invalid")
    checkpoint_sha = m.sha256(root["checkpoint_sha256"], "checkpoint.checkpoint_sha256"); checkpoint_id = m.checkpoint_id(root["checkpoint_id"]); basis = dict(root); basis.pop("checkpoint_id"); basis.pop("checkpoint_sha256"); expected = m.digest(basis)
    if checkpoint_sha != expected or checkpoint_id != f"{m.CHECKPOINT_PREFIX}:{expected}": raise m.ProtocolV3TransactionError("checkpoint digest or id mismatch")
    return m.TransactionCheckpoint(m.canonical(root), expected, checkpoint_id)


def _resolve_ledger_receipt(identity: m.TransactionIdentity, trial_ledger_root: str | Path, cache_record: m.CacheRecord | None, previous: m.TransactionCheckpoint | None, fault: FaultInjector | None, repo: Path) -> dict[str, Any]:
    decision = identity.to_dict()["run_fingerprint"]["trial_ledger_head"]; ledger = read_trial_ledger(trial_ledger_root)
    if cache_record is None:
        if previous is not None and previous.to_dict()["ledger_receipt"]["state"] == "CACHE_REUSE_RECORDED":
            receipt = previous.to_dict()["ledger_receipt"]; _verify_receipt_event(ledger, receipt); return receipt
        if ledger.status.head_sha256 != decision["head_sha256"] or ledger.status.event_count != decision["event_count"]: raise m.ProtocolV3TransactionError("trial ledger changed after decision identity")
        return {"schema_version": "protocol_v3_checkpoint_ledger_receipt_v1", "state": "NO_CACHE_REUSE", "decision_head_sha256": decision["head_sha256"], "decision_event_count": decision["event_count"], "event_key": "NOT_APPLICABLE", "event_sequence": 0, "event_hash": m.ZERO_HASH}
    record = validate_cache_record(cache_record, repository_root=repo); payload = record.to_dict(); trial_id = payload["trial_id"]
    reuse_scope = {"cache_record_id": payload["cache_record_id"], "transaction_id": identity.transaction_id, "checkpoint_id": payload["checkpoint_id"], "work_unit_id": identity.work_unit_id}
    event_key = f"cache_reuse:{m.digest({'trial_id': trial_id, 'reuse_scope': reuse_scope})}"; matching = [event for event in ledger.events if event.get("payload", {}).get("event_key") == event_key]
    if matching:
        if len(matching) != 1 or matching[0]["sequence"] != decision["event_count"] + 1 or ledger.status.event_count != matching[0]["sequence"]: raise m.ProtocolV3TransactionError("ledger advanced beyond the idempotent cache-reuse event")
        event = matching[0]
    else:
        if ledger.status.head_sha256 != decision["head_sha256"] or ledger.status.event_count != decision["event_count"]: raise m.ProtocolV3TransactionError("cache reuse decision ledger head is stale")
        ledger = record_cache_reuse(trial_ledger_root, trial_id=trial_id, reuse_scope=reuse_scope); matching = [event for event in ledger.events if event.get("payload", {}).get("event_key") == event_key]
        if len(matching) != 1: raise m.ProtocolV3TransactionError("cache reuse ledger event was not committed exactly once")
        event = matching[0]
    _fault(fault, "after_ledger_reuse_append")
    return {"schema_version": "protocol_v3_checkpoint_ledger_receipt_v1", "state": "CACHE_REUSE_RECORDED", "decision_head_sha256": decision["head_sha256"], "decision_event_count": decision["event_count"], "event_key": event_key, "event_sequence": event["sequence"], "event_hash": event["event_hash"]}


def _validate_cache_ledger(record: m.CacheRecord, identity: m.TransactionIdentity, trial_ledger_root: str | Path) -> None:
    payload = record.to_dict(); ledger = read_trial_ledger(trial_ledger_root)
    if payload["trial_id"] not in ledger.trials: raise m.ProtocolV3TransactionError("cache hit references a trial absent from the permanent ledger")
    decision = identity.to_dict()["run_fingerprint"]["trial_ledger_head"]
    if ledger.status.head_sha256 == decision["head_sha256"] and ledger.status.event_count == decision["event_count"]: return
    reuse_scope = {"cache_record_id": payload["cache_record_id"], "transaction_id": identity.transaction_id, "checkpoint_id": payload["checkpoint_id"], "work_unit_id": identity.work_unit_id}
    event_key = f"cache_reuse:{m.digest({'trial_id': payload['trial_id'], 'reuse_scope': reuse_scope})}"; matching = [event for event in ledger.events if event.get("payload", {}).get("event_key") == event_key]
    if len(matching) != 1 or matching[0]["sequence"] != decision["event_count"] + 1 or ledger.status.event_count != matching[0]["sequence"] or ledger.status.head_sha256 != matching[0]["event_hash"]: raise m.ProtocolV3TransactionError("cache hit blocked: permanent ledger is not at the decision head or its single idempotent cache-reuse successor")


def _validate_ledger_receipt(value: Any, identity: m.TransactionIdentity) -> dict[str, Any]:
    root = dict(m.require_mapping(value, "ledger_receipt")); m.exact_keys(root, {"schema_version", "state", "decision_head_sha256", "decision_event_count", "event_key", "event_sequence", "event_hash"}, "ledger_receipt"); m.literal(root, "schema_version", "protocol_v3_checkpoint_ledger_receipt_v1", "ledger_receipt")
    decision = identity.to_dict()["run_fingerprint"]["trial_ledger_head"]
    if root["decision_head_sha256"] != decision["head_sha256"] or root["decision_event_count"] != decision["event_count"]: raise m.ProtocolV3TransactionError("ledger receipt decision head mismatch")
    if root["state"] == "NO_CACHE_REUSE":
        if root["event_key"] != "NOT_APPLICABLE" or root["event_sequence"] != 0 or root["event_hash"] != m.ZERO_HASH: raise m.ProtocolV3TransactionError("NO_CACHE_REUSE receipt is invalid")
    elif root["state"] == "CACHE_REUSE_RECORDED":
        if not isinstance(root["event_key"], str) or not root["event_key"].startswith("cache_reuse:") or root["event_sequence"] != decision["event_count"] + 1: raise m.ProtocolV3TransactionError("cache reuse ledger receipt is invalid")
        m.sha256(root["event_hash"], "ledger_receipt.event_hash")
    else: raise m.ProtocolV3TransactionError("ledger receipt state is invalid")
    return root


def _verify_receipt_event(ledger: Any, receipt: Mapping[str, Any]) -> None:
    matching = [event for event in ledger.events if event.get("payload", {}).get("event_key") == receipt["event_key"]]
    if len(matching) != 1 or matching[0]["sequence"] != receipt["event_sequence"] or matching[0]["event_hash"] != receipt["event_hash"]: raise m.ProtocolV3TransactionError("checkpoint ledger receipt event is absent, duplicated, or changed")


def _validate_result(value: Any) -> dict[str, Any]:
    root = dict(m.require_mapping(value, "result")); m.exact_keys(root, {"status", "payload", "result_sha256"}, "result")
    if root["status"] not in {"IN_PROGRESS", "COMPLETED", "NO_TRADE", "BLOCKED"}: raise m.ProtocolV3TransactionError("result status is invalid")
    payload = dict(m.require_mapping(root["payload"], "result.payload")); m.reject_raw(payload, "result.payload"); m.finite_json(payload, "result.payload")
    if root["result_sha256"] != m.digest({"status": root["status"], "payload": payload}): raise m.ProtocolV3TransactionError("result digest mismatch")
    return root


def _validate_chain(checkpoint: m.TransactionCheckpoint, tx_root: Path, repo: Path) -> None:
    current = checkpoint; expected = current.sequence; seen = set()
    while True:
        if current.checkpoint_sha256 in seen: raise m.ProtocolV3TransactionError("checkpoint chain contains a cycle")
        seen.add(current.checkpoint_sha256); payload = current.to_dict()
        if current.sequence != expected: raise m.ProtocolV3TransactionError("checkpoint chain sequence is not contiguous")
        if current.sequence == 1:
            if payload["previous_checkpoint_sha256"] != m.ZERO_HASH: raise m.ProtocolV3TransactionError("checkpoint chain genesis is invalid")
            return
        previous = _read_checkpoint(tx_root / "committed" / f"{payload['previous_checkpoint_sha256']}.json", repo)
        if previous.to_dict()["transaction_id"] != payload["transaction_id"]: raise m.ProtocolV3TransactionError("checkpoint chain transaction changed")
        expected -= 1; current = previous


def _checkpoint_relative(checkpoint: m.TransactionCheckpoint) -> PurePosixPath:
    payload = checkpoint.to_dict(); return PurePosixPath(m.CHECKPOINT_ROOT, payload["transaction_id"].rsplit(":", 1)[1], "committed", f"{checkpoint.checkpoint_sha256}.json")
def _checkpoint_root(repo: Path, transaction_id: str, *, create: bool) -> Path:
    root = _safe_root(repo, m.CHECKPOINT_ROOT, create=create); target = root / transaction_id.rsplit(":", 1)[1]
    if create: _ensure_directory(repo, target)
    return target
def _cache_path(identity: m.TransactionIdentity, root: Path, repo: Path) -> Path:
    parent = root / identity.identity_sha256[:2]; _ensure_directory(repo, parent); return parent / f"{identity.identity_sha256}.json"
def _read_checkpoint(path: Path, repo: Path) -> m.TransactionCheckpoint:
    root = _safe_root(repo, m.CHECKPOINT_ROOT, create=False); value, raw = _read_object(_guard(path, root, repo), root); checkpoint = validate_checkpoint(value, repository_root=repo)
    if raw != m.canonical_bytes(checkpoint.to_dict()): raise m.ProtocolV3TransactionError("checkpoint bytes are not canonical")
    return checkpoint
def _read_cache(path: Path, repo: Path) -> m.CacheRecord:
    root = _safe_root(repo, m.CACHE_ROOT, create=False); value, raw = _read_object(_guard(path, root, repo), root); record = validate_cache_record(value, repository_root=repo)
    if raw != m.canonical_bytes(record.to_dict()): raise m.ProtocolV3TransactionError("cache record bytes are not canonical")
    return record
def _read_lock(path: Path, repo: Path) -> m.TransactionLock:
    root = _safe_root(repo, m.LOCK_ROOT, create=True); resolved = _guard(path, root, repo); value, raw = _read_object(resolved, root)
    m.exact_keys(value, {"schema_version", "protocol_version", "transaction_id", "owner_id", "process_id", "host_sha256", "acquired_at_utc", "lock_sha256"}, "transaction_lock"); m.literal(value, "schema_version", m.LOCK_SCHEMA_VERSION, "transaction_lock"); m.literal(value, "protocol_version", m.PROTOCOL_VERSION, "transaction_lock")
    m.transaction_id(value["transaction_id"]); m.safe_id(value["owner_id"], "transaction_lock.owner_id"); m.positive_int(value["process_id"], "transaction_lock.process_id"); m.sha256(value["host_sha256"], "transaction_lock.host_sha256"); _utc(value["acquired_at_utc"], "transaction_lock.acquired_at_utc")
    observed = m.sha256(value["lock_sha256"], "transaction_lock.lock_sha256"); basis = dict(value); basis.pop("lock_sha256")
    if observed != m.digest(basis) or raw != m.canonical_bytes(value): raise m.ProtocolV3TransactionError("transaction lock digest or bytes are invalid")
    return m.TransactionLock(resolved, m.canonical(value), observed)
def _assert_lock(lock: m.TransactionLock, transaction_id: str, repo: Path) -> None:
    current = _read_lock(lock.path, repo)
    if current != lock or current.to_dict()["transaction_id"] != transaction_id or current.to_dict()["process_id"] != os.getpid(): raise m.ProtocolV3TransactionError("valid exclusive transaction lock owned by this process is required")
def _validate_head(value: Mapping[str, Any]) -> None:
    m.exact_keys(value, {"schema_version", "protocol_version", "transaction_id", "sequence", "checkpoint_id", "checkpoint_sha256", "head_sha256"}, "checkpoint_head"); m.literal(value, "schema_version", m.CHECKPOINT_HEAD_SCHEMA_VERSION, "checkpoint_head"); m.literal(value, "protocol_version", m.PROTOCOL_VERSION, "checkpoint_head")
    m.transaction_id(value["transaction_id"]); m.positive_int(value["sequence"], "checkpoint_head.sequence"); m.checkpoint_id(value["checkpoint_id"]); m.sha256(value["checkpoint_sha256"], "checkpoint_head.checkpoint_sha256")
    observed = m.sha256(value["head_sha256"], "checkpoint_head.head_sha256"); basis = dict(value); basis.pop("head_sha256")
    if observed != m.digest(basis): raise m.ProtocolV3TransactionError("checkpoint HEAD digest mismatch")


def _publish_checkpoint(path: Path, raw: bytes, owner_id: str, fault: FaultInjector | None) -> None:
    if path.exists():
        value, observed = _read_object(path, path.parent)
        if observed != raw or m.canonical_bytes(value) != raw: raise m.ProtocolV3TransactionError("immutable checkpoint path already differs")
        return
    temp = path.parent / f".{path.name}.{owner_id}.tmp"
    if temp.exists() and temp.read_bytes() != raw: temp.unlink(); _fsync_directory(temp.parent)
    if not temp.exists(): _write_create_only(temp, raw)
    _fault(fault, "after_checkpoint_temp_fsync"); value, observed = _read_object(temp, temp.parent)
    if observed != raw or m.canonical_bytes(value) != raw: raise m.ProtocolV3TransactionError("checkpoint temp file failed validation")
    _fault(fault, "after_checkpoint_temp_validate"); os.replace(temp, path); _fsync_directory(path.parent)
def _publish_immutable(path: Path, raw: bytes) -> None:
    if path.exists():
        value, observed = _read_object(path, path.parent)
        if observed != raw or m.canonical_bytes(value) != raw: raise m.ProtocolV3TransactionError("immutable cache path already differs")
        return
    temp = path.parent / f".{path.name}.tmp"
    if temp.exists(): temp.unlink()
    _write_create_only(temp, raw); value, observed = _read_object(temp, temp.parent)
    if observed != raw or m.canonical_bytes(value) != raw: raise m.ProtocolV3TransactionError("cache temp file failed validation")
    os.replace(temp, path); _fsync_directory(path.parent)
def _atomic_replace(path: Path, raw: bytes, owner_id: str, repo: Path) -> None:
    _ensure_directory(repo, path.parent); temp = path.parent / f".{path.name}.{owner_id}.tmp"
    if temp.exists(): temp.unlink()
    _write_create_only(temp, raw); value, observed = _read_object(temp, temp.parent)
    if observed != raw or m.canonical_bytes(value) != raw: raise m.ProtocolV3TransactionError("atomic replacement temp failed validation")
    os.replace(temp, path); _fsync_directory(path.parent)
def _write_create_only(path: Path, raw: bytes) -> None:
    try:
        with path.open("xb") as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    except FileExistsError: raise
    except OSError as exc: raise m.ProtocolV3TransactionError(f"could not persist transaction file: {path}") from exc
def _safe_root(repo: Path, relative_root: str, *, create: bool) -> Path:
    relative = m.safe_relative(relative_root, "transaction storage root"); target = repo.joinpath(*relative.parts); _reject_symlinks(repo, target)
    if create: target.mkdir(parents=True, exist_ok=True)
    if not target.exists() or not target.is_dir() or target.is_symlink(): raise m.ProtocolV3TransactionError("transaction storage root is missing or unsafe")
    resolved = target.resolve()
    if not is_path_within(resolved, repo): raise m.ProtocolV3TransactionError("transaction storage root escapes repository_root")
    _reject_symlinks(repo, resolved); return resolved
def _ensure_directory(repo: Path, directory: Path) -> None:
    _reject_symlinks(repo, directory); directory.mkdir(parents=True, exist_ok=True); _reject_symlinks(repo, directory)
    if directory.is_symlink() or not is_path_within(directory.resolve(), repo): raise m.ProtocolV3TransactionError("transaction directory is unsafe")
def _reject_symlinks(repo: Path, target: Path) -> None:
    try: relative = target.relative_to(repo)
    except ValueError as exc: raise m.ProtocolV3TransactionError("transaction target escapes repository_root") from exc
    current = repo
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink(): raise m.ProtocolV3TransactionError("symlinked transaction paths are forbidden")
def _guard(path: Path, root: Path, repo: Path) -> Path:
    candidate = path if path.is_absolute() else repo / path
    try: relative = candidate.relative_to(root)
    except ValueError as exc: raise m.ProtocolV3TransactionError("transaction path is outside its canonical root") from exc
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink(): raise m.ProtocolV3TransactionError("symlinked transaction paths are forbidden")
    try: resolved = candidate.resolve(strict=True)
    except OSError as exc: raise m.ProtocolV3TransactionError("transaction path is missing or unreadable") from exc
    if not is_path_within(resolved, root): raise m.ProtocolV3TransactionError("transaction path escapes its canonical root")
    return resolved
def _read_object(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    try: resolved = path.resolve(strict=True)
    except OSError as exc: raise m.ProtocolV3TransactionError("transaction file is missing or unreadable") from exc
    if path.is_symlink() or not is_path_within(resolved, root.resolve()): raise m.ProtocolV3TransactionError("transaction file is outside its canonical root")
    try: raw = resolved.read_bytes(); value = m.strict_loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc: raise m.ProtocolV3TransactionError(f"transaction JSON is invalid: {path}") from exc
    if not isinstance(value, dict): raise m.ProtocolV3TransactionError("transaction JSON must contain one object")
    return value, raw
def _utc_now() -> str: return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
def _utc(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"): raise m.ProtocolV3TransactionError(f"{path} must be UTC and end in Z")
    try: parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc: raise m.ProtocolV3TransactionError(f"{path} is invalid") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed): raise m.ProtocolV3TransactionError(f"{path} must be UTC")
    return parsed
def _host_sha256() -> str: return hashlib.sha256(socket.gethostname().encode()).hexdigest()
def _process_alive(process_id: int) -> bool | None:
    try: os.kill(process_id, 0)
    except ProcessLookupError: return False
    except PermissionError: return None
    except OSError as exc:
        if exc.errno == errno.ESRCH: return False
        if exc.errno == errno.EPERM: return None
        return None
    return True
def _fsync_directory(path: Path) -> None:
    if os.name == "nt": return
    try: descriptor = os.open(path, os.O_RDONLY)
    except OSError as exc: raise m.ProtocolV3TransactionError(f"could not open directory for fsync: {path}") from exc
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
def _fault(injector: FaultInjector | None, phase: str) -> None:
    if injector is not None: injector(phase)

__all__ = [
    "acquire_transaction_lock", "inspect_transaction_lock", "release_transaction_lock",
    "recover_stale_transaction_lock", "commit_checkpoint", "read_last_committed_checkpoint",
    "resume_last_committed_checkpoint", "publish_cache_record", "lookup_cache_record",
    "validate_cache_record", "validate_checkpoint",
]
