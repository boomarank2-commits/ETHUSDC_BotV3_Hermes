"""Identity and contract model for Protocol v3 Task 13."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Final

from ethusdc_bot.protocol_v3.artifact_store_api import (
    INDEX_ROOT as ARTIFACT_INDEX_ROOT,
    read_compact_artifact_bundle,
)
from ethusdc_bot.protocol_v3.context_parity import (
    ContextParityBinding,
    validate_context_parity_binding,
)
from ethusdc_bot.protocol_v3.execution_parity import EXECUTION_PARITY_CONTRACT_VERSION
from ethusdc_bot.protocol_v3.intrabar_execution import INTRABAR_EXECUTION_CONTRACT_VERSION
from ethusdc_bot.protocol_v3.pipeline import (
    BudgetUsage,
    PreRunManifest,
    origin_cycle_seed,
    stagnation_stop_reason,
    validate_budget_usage,
    validate_pre_run_manifest,
)
from ethusdc_bot.protocol_v3.run_identity import RunFingerprint, validate_run_fingerprint
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy

TRANSACTION_CONTRACT_PATH: Final = Path("configs/protocol_v3_transaction_contract.json")
TRANSACTION_CONTRACT_SCHEMA: Final = "protocol_v3_transaction_contract_v1"
TRANSACTION_CONTRACT_VERSION: Final = "protocol_v3_content_addressed_cache_and_transactional_resume_v1"
IDENTITY_SLOT_SCHEMA_VERSION: Final = "protocol_v3_transaction_identity_slot_v1"
TRANSACTION_IDENTITY_SCHEMA_VERSION: Final = "protocol_v3_transaction_identity_v1"
CHECKPOINT_SCHEMA_VERSION: Final = "protocol_v3_transaction_checkpoint_v1"
CHECKPOINT_HEAD_SCHEMA_VERSION: Final = "protocol_v3_checkpoint_head_v1"
CACHE_RECORD_SCHEMA_VERSION: Final = "protocol_v3_cache_record_v1"
LOCK_SCHEMA_VERSION: Final = "protocol_v3_transaction_lock_v1"
PROTOCOL_VERSION: Final = "3.0.0"
CHECKPOINT_ROOT: Final = "reports/protocol_v3/checkpoints"
CACHE_ROOT: Final = "reports/protocol_v3/cache"
LOCK_ROOT: Final = "reports/protocol_v3/transaction_locks"
LOCK_RECOVERY_ROOT: Final = "reports/protocol_v3/recovered_locks"
BOUND: Final = "BOUND"
GENESIS: Final = "GENESIS"
NOT_APPLICABLE: Final = "NOT_APPLICABLE"
RAW_DATA_SLOT: Final = "three_market_data"
CODE_PIPELINE_SLOT: Final = "code_pipeline"
FEATURE_SLOT: Final = "feature_identity"
CONTEXT_SLOT: Final = "context_identity"
CANDIDATE_SLOT: Final = "candidate_identity"
FOLD_SLOT: Final = "fold_identity"
BOUNDARY_SLOT: Final = "boundary_identity"
HORIZON_SLOT: Final = "horizon_identity"
EXECUTION_SLOT: Final = "execution_identity"
SIMULATOR_SLOT: Final = "simulator_identity"
COST_SLOT: Final = "cost_identity"
QUALITY_SLOT: Final = "quality_gate_identity"
EXCHANGE_SLOT: Final = "exchange_info_identity"
TRIAL_LEDGER_SLOT: Final = "trial_ledger_head"
ROTATION_SLOT: Final = "rotation_state_identity"
STORE_HEADS_SLOT: Final = "sealed_store_heads"
CANDIDATE_PENDING_SCHEMA: Final = "protocol_v3_candidate_identity_pending_task15_v1"
FOLD_PENDING_SCHEMA: Final = "protocol_v3_fold_identity_pending_task14_v1"
ROTATION_GENESIS_SCHEMA: Final = "protocol_v3_rotation_identity_genesis_v1"
STORE_HEADS_SCHEMA: Final = "protocol_v3_sealed_store_heads_v1"
REQUIRED_IDENTITY_SLOTS: Final = (
    RAW_DATA_SLOT, CODE_PIPELINE_SLOT, FEATURE_SLOT, CONTEXT_SLOT,
    CANDIDATE_SLOT, FOLD_SLOT, BOUNDARY_SLOT, HORIZON_SLOT,
    EXECUTION_SLOT, SIMULATOR_SLOT, COST_SLOT, QUALITY_SLOT,
    EXCHANGE_SLOT, TRIAL_LEDGER_SLOT, ROTATION_SLOT, STORE_HEADS_SLOT,
)
TRANSACTION_PREFIX: Final = "protocol_v3_transaction_sha256"
CHECKPOINT_PREFIX: Final = "protocol_v3_checkpoint_sha256"
CACHE_PREFIX: Final = "protocol_v3_cache_sha256"
ZERO_HASH: Final = "0" * 64
SAFETY: Final = {
    "api_keys": "forbidden", "live": "locked", "orders": "locked",
    "paper": "locked", "testtrade": "locked", "trading_api": "forbidden",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SCHEMA_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}$")
_TRANSACTION_ID = re.compile(r"^protocol_v3_transaction_sha256:[0-9a-f]{64}$")
_CHECKPOINT_ID = re.compile(r"^protocol_v3_checkpoint_sha256:[0-9a-f]{64}$")
_CACHE_ID = re.compile(r"^protocol_v3_cache_sha256:[0-9a-f]{64}$")
_FORBIDDEN_RAW_KEYS = {
    "candles", "raw_candles", "klines", "ohlcv", "market_bars",
    "one_minute_bars", "raw_market_data",
}

CANONICAL_CONTRACT: dict[str, Any] = {
    "schema_version": TRANSACTION_CONTRACT_SCHEMA,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": TRANSACTION_CONTRACT_VERSION,
    "identity_slot_schema_version": IDENTITY_SLOT_SCHEMA_VERSION,
    "transaction_identity_schema_version": TRANSACTION_IDENTITY_SCHEMA_VERSION,
    "checkpoint_schema_version": CHECKPOINT_SCHEMA_VERSION,
    "checkpoint_head_schema_version": CHECKPOINT_HEAD_SCHEMA_VERSION,
    "cache_record_schema_version": CACHE_RECORD_SCHEMA_VERSION,
    "lock_schema_version": LOCK_SCHEMA_VERSION,
    "roots": {
        "checkpoint_root": CHECKPOINT_ROOT, "cache_root": CACHE_ROOT,
        "lock_root": LOCK_ROOT, "recovered_lock_root": LOCK_RECOVERY_ROOT,
    },
    "identity_policy": {
        "required_slots": list(REQUIRED_IDENTITY_SLOTS),
        "allowed_slot_states": [BOUND, GENESIS, NOT_APPLICABLE],
        "missing_slot_forbidden": True, "none_slot_forbidden": True,
        "caller_digest_claims_forbidden": True,
        "full_run_fingerprint_v2_required": True,
        "concrete_context_parity_binding_required": True,
        "trial_ledger_head_is_decision_time_head": True,
        "sealed_store_heads_are_transitively_revalidated": True,
    },
    "checkpoint_policy": {
        "pre_run_manifest_required": True,
        "seed_namespace_and_derived_state_required": True,
        "budget_reservations_required": True,
        "stop_and_stagnation_state_required": True,
        "temp_file_in_target_directory": True,
        "file_flush_and_fsync_required": True,
        "atomic_replace_required": True,
        "head_is_committed_visibility_marker": True,
        "resume_uses_last_committed_head_only": True,
        "orphan_temp_or_checkpoint_is_not_committed": True,
    },
    "lock_policy": {
        "exclusive_create": True, "blind_stale_overwrite_forbidden": True,
        "same_host_dead_process_evidence_required_for_recovery": True,
        "lock_digest_and_owner_required_for_release": True,
    },
    "cache_policy": {
        "cache_key_is_complete_transaction_identity_sha256": True,
        "transitive_reference_revalidation_on_hit": True,
        "cache_reuse_appended_to_permanent_trial_ledger": True,
        "cache_reuse_counts_as_independent_trial": False,
        "reuse_event_is_deterministic_and_idempotent": True,
        "crash_after_ledger_append_reuses_same_event_key": True,
    },
    "fault_injection_phases": [
        "before_checkpoint_temp", "after_checkpoint_temp_fsync",
        "after_checkpoint_temp_validate", "after_checkpoint_replace",
        "after_checkpoint_reload", "after_ledger_reuse_append",
        "before_head_replace", "after_head_replace",
    ],
    "deferred_scope": {
        "fold_planner_task": 14, "candidate_selector_task": 15,
        "router_task": 22, "outer_orchestration_task": 23,
        "rotation_persistence_task": 24, "final_evaluator_task": 31,
    },
    "safety": SAFETY,
}

class ProtocolV3TransactionError(RuntimeError):
    pass

@dataclass(frozen=True)
class IdentitySlot:
    canonical_json: str
    slot_sha256: str
    def to_dict(self) -> dict[str, Any]: return json.loads(self.canonical_json)
    @property
    def name(self) -> str: return str(self.to_dict()["name"])
    @property
    def state(self) -> str: return str(self.to_dict()["state"])

@dataclass(frozen=True)
class TransactionIdentity:
    canonical_json: str
    identity_sha256: str
    transaction_id: str
    def to_dict(self) -> dict[str, Any]: return json.loads(self.canonical_json)
    @property
    def work_unit_id(self) -> str: return str(self.to_dict()["work_unit_id"])
    @property
    def cache_key(self) -> str: return f"{CACHE_PREFIX}:{self.identity_sha256}"
    @property
    def resume_key(self) -> str: return self.transaction_id

@dataclass(frozen=True)
class TransactionLock:
    path: Path
    canonical_json: str
    lock_sha256: str
    def to_dict(self) -> dict[str, Any]: return json.loads(self.canonical_json)

@dataclass(frozen=True)
class TransactionCheckpoint:
    canonical_json: str
    checkpoint_sha256: str
    checkpoint_id: str
    def to_dict(self) -> dict[str, Any]: return json.loads(self.canonical_json)
    @property
    def sequence(self) -> int: return int(self.to_dict()["sequence"])

@dataclass(frozen=True)
class CacheRecord:
    canonical_json: str
    cache_record_sha256: str
    cache_record_id: str
    def to_dict(self) -> dict[str, Any]: return json.loads(self.canonical_json)


def load_transaction_contract(repo_root: str | Path | None = None, *, contract_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    path = Path(contract_path) if contract_path is not None else root / TRANSACTION_CONTRACT_PATH
    if not path.is_absolute(): path = root / path
    try: value = strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolV3TransactionError(f"Protocol v3 transaction contract is missing or invalid: {path}") from exc
    validate_transaction_contract(value)
    return value


def validate_transaction_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or normalize(value) != CANONICAL_CONTRACT:
        raise ProtocolV3TransactionError("Protocol v3 transaction contract is not canonical")


def build_bound_identity_slot(name: str, schema_version: str, payload: Mapping[str, Any]) -> IdentitySlot:
    normalized = dict(require_mapping(payload, f"{name}.payload"))
    if not normalized: raise ProtocolV3TransactionError("BOUND identity slots require a non-empty payload")
    return _build_slot(name, BOUND, schema_version, normalized, "bound")


def build_genesis_identity_slot(name: str, schema_version: str, reason: str) -> IdentitySlot:
    return _build_slot(name, GENESIS, schema_version, {}, required_text(reason, "reason"))


def build_not_applicable_identity_slot(name: str, schema_version: str, reason: str) -> IdentitySlot:
    return _build_slot(name, NOT_APPLICABLE, schema_version, {}, required_text(reason, "reason"))


def _build_slot(name: str, state: str, schema: str, payload: Mapping[str, Any], reason: str) -> IdentitySlot:
    basis = {
        "schema_version": IDENTITY_SLOT_SCHEMA_VERSION,
        "name": required_slot_name(name), "state": state,
        "identity_schema": schema_identifier(schema, f"{name}.identity_schema"),
        "payload": normalize(payload), "reason": reason,
    }
    return validate_identity_slot({**basis, "slot_sha256": digest(basis)})


def validate_identity_slot(value: IdentitySlot | Mapping[str, Any]) -> IdentitySlot:
    root = value.to_dict() if isinstance(value, IdentitySlot) else dict(require_mapping(value, "identity_slot"))
    exact_keys(root, {"schema_version", "name", "state", "identity_schema", "payload", "reason", "slot_sha256"}, "identity_slot")
    literal(root, "schema_version", IDENTITY_SLOT_SCHEMA_VERSION, "identity_slot")
    name = required_slot_name(root.get("name")); state = root.get("state")
    if state not in {BOUND, GENESIS, NOT_APPLICABLE}: raise ProtocolV3TransactionError(f"identity slot state is invalid: {name}")
    schema_identifier(root.get("identity_schema"), f"{name}.identity_schema")
    payload = dict(require_mapping(root.get("payload"), f"{name}.payload")); reason = required_text(root.get("reason"), f"{name}.reason")
    if state == BOUND and (not payload or reason != "bound"): raise ProtocolV3TransactionError(f"BOUND identity slot is incomplete: {name}")
    if state != BOUND and payload: raise ProtocolV3TransactionError(f"typed non-bound slot payload must be empty: {name}")
    reject_raw(payload, f"{name}.payload"); finite_json(payload, f"{name}.payload")
    observed = sha256(root.get("slot_sha256"), f"{name}.slot_sha256"); basis = dict(root); basis.pop("slot_sha256")
    if observed != digest(basis): raise ProtocolV3TransactionError(f"identity slot digest mismatch: {name}")
    return IdentitySlot(canonical(root), observed)


def build_sealed_store_heads_slot(index_paths: Sequence[str | Path], repository_root: str | Path) -> IdentitySlot:
    repo = repo_root(repository_root)
    if isinstance(index_paths, (str, bytes, bytearray)) or not isinstance(index_paths, Sequence):
        raise ProtocolV3TransactionError("sealed store index paths must be a sequence")
    if not index_paths:
        return build_genesis_identity_slot(STORE_HEADS_SLOT, STORE_HEADS_SCHEMA, "no_protocol_v3_artifact_index_committed")
    heads = sorted((_artifact_head(path, repo) for path in index_paths), key=lambda row: row["relative_path"])
    if len({row["relative_path"] for row in heads}) != len(heads): raise ProtocolV3TransactionError("sealed artifact index paths must be unique")
    return build_bound_identity_slot(STORE_HEADS_SLOT, STORE_HEADS_SCHEMA, {"indexes": heads})


def build_transaction_identity(*, run_fingerprint: RunFingerprint, context_binding: ContextParityBinding, horizon_policy: HorizonPolicy, work_unit_id: str, candidate_identity: IdentitySlot, fold_identity: IdentitySlot, rotation_state_identity: IdentitySlot, sealed_store_heads: IdentitySlot, repository_root: str | Path) -> TransactionIdentity:
    validate_run_fingerprint(run_fingerprint); validate_context_parity_binding(context_binding)
    if not isinstance(horizon_policy, HorizonPolicy): raise ProtocolV3TransactionError("horizon_policy must be a validated HorizonPolicy")
    run = run_fingerprint.payload(); runtime = normalize(run["context"]["runtime_binding"])
    observed_runtime = {
        "context_identity_sha256": context_binding.context_identity_sha256,
        "identity_payload": normalize(context_binding.identity_payload()),
        "cache_key": context_binding.cache_key, "resume_key": context_binding.resume_key,
    }
    if runtime != observed_runtime: raise ProtocolV3TransactionError("run fingerprint and concrete ContextParityBinding differ")
    supplied = {
        CANDIDATE_SLOT: validate_identity_slot(candidate_identity),
        FOLD_SLOT: validate_identity_slot(fold_identity),
        ROTATION_SLOT: validate_identity_slot(rotation_state_identity),
        STORE_HEADS_SLOT: validate_identity_slot(sealed_store_heads),
    }
    if any(slot.name != name for name, slot in supplied.items()): raise ProtocolV3TransactionError("supplied identity slot name mismatch")
    _validate_transition_slots(supplied); _validate_store_heads_slot(supplied[STORE_HEADS_SLOT], repository_root)
    horizon = {**horizon_policy.basis(), "policy_sha256": horizon_policy.policy_sha256}
    slots = {
        RAW_DATA_SLOT: build_bound_identity_slot(RAW_DATA_SLOT, "protocol_v3_run_raw_data_identity_v2", run["raw_data"]),
        CODE_PIPELINE_SLOT: build_bound_identity_slot(CODE_PIPELINE_SLOT, "protocol_v3_code_pipeline_identity_v1", {"code": run["code"], "pipeline": run["pipeline"]}),
        FEATURE_SLOT: build_bound_identity_slot(FEATURE_SLOT, "protocol_v3_feature_component_identity_v1", run["features"]),
        CONTEXT_SLOT: build_bound_identity_slot(CONTEXT_SLOT, "protocol_v3_context_runtime_identity_v2", runtime),
        BOUNDARY_SLOT: build_bound_identity_slot(BOUNDARY_SLOT, "protocol_v3_boundary_component_identity_v1", run["boundary"]),
        HORIZON_SLOT: build_bound_identity_slot(HORIZON_SLOT, "protocol_v3_horizon_policy_identity_v1", horizon),
        EXECUTION_SLOT: build_bound_identity_slot(EXECUTION_SLOT, "protocol_v3_execution_identity_v1", {
            "execution_parity_contract_version": EXECUTION_PARITY_CONTRACT_VERSION,
            "intrabar_execution_contract_version": INTRABAR_EXECUTION_CONTRACT_VERSION,
            "simulator_source_sha256": run["simulator"]["source_sha256"],
        }),
        SIMULATOR_SLOT: build_bound_identity_slot(SIMULATOR_SLOT, "protocol_v3_simulator_component_identity_v1", run["simulator"]),
        COST_SLOT: build_bound_identity_slot(COST_SLOT, "protocol_v3_cost_component_identity_v1", run["cost_model"]),
        QUALITY_SLOT: build_bound_identity_slot(QUALITY_SLOT, "protocol_v3_quality_gate_component_identity_v1", run["quality_gates"]),
        EXCHANGE_SLOT: build_bound_identity_slot(EXCHANGE_SLOT, "protocol_v3_exchange_info_identity_v1", run["exchange_info"]),
        TRIAL_LEDGER_SLOT: build_bound_identity_slot(TRIAL_LEDGER_SLOT, "protocol_v3_trial_ledger_decision_head_v1", run["trial_ledger_head"]),
        **supplied,
    }
    basis = {
        "schema_version": TRANSACTION_IDENTITY_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
        "contract_version": TRANSACTION_CONTRACT_VERSION, "work_unit_id": safe_id(work_unit_id, "work_unit_id"),
        "run_fingerprint": run_fingerprint.to_dict(), "context_binding": observed_runtime,
        "identity_slots": [slots[name].to_dict() for name in REQUIRED_IDENTITY_SLOTS], "safety": SAFETY,
    }
    identity_sha = digest(basis)
    return validate_transaction_identity({**basis, "identity_sha256": identity_sha, "transaction_id": f"{TRANSACTION_PREFIX}:{identity_sha}"}, repository_root=repository_root)


def validate_transaction_identity(value: TransactionIdentity | Mapping[str, Any], *, repository_root: str | Path) -> TransactionIdentity:
    root = value.to_dict() if isinstance(value, TransactionIdentity) else dict(require_mapping(value, "transaction_identity"))
    exact_keys(root, {"schema_version", "protocol_version", "contract_version", "work_unit_id", "run_fingerprint", "context_binding", "identity_slots", "safety", "identity_sha256", "transaction_id"}, "transaction_identity")
    literal(root, "schema_version", TRANSACTION_IDENTITY_SCHEMA_VERSION, "transaction_identity"); literal(root, "protocol_version", PROTOCOL_VERSION, "transaction_identity"); literal(root, "contract_version", TRANSACTION_CONTRACT_VERSION, "transaction_identity")
    safe_id(root.get("work_unit_id"), "transaction_identity.work_unit_id")
    run = dict(require_mapping(root.get("run_fingerprint"), "transaction_identity.run_fingerprint")); validate_run_fingerprint(run)
    runtime = dict(require_mapping(root.get("context_binding"), "transaction_identity.context_binding"))
    if normalize(run["context"]["runtime_binding"]) != normalize(runtime): raise ProtocolV3TransactionError("transaction context binding differs from run fingerprint")
    raw_slots = root.get("identity_slots")
    if not isinstance(raw_slots, list): raise ProtocolV3TransactionError("transaction identity slots must be a list")
    slots = [validate_identity_slot(row) for row in raw_slots]
    if [slot.name for slot in slots] != list(REQUIRED_IDENTITY_SLOTS): raise ProtocolV3TransactionError("transaction identity slots are missing, extra, or reordered")
    slot_map = {slot.name: slot for slot in slots}; _validate_derived_slots(run, runtime, slot_map); _validate_transition_slots(slot_map); _validate_horizon_slot(slot_map[HORIZON_SLOT]); _validate_store_heads_slot(slot_map[STORE_HEADS_SLOT], repository_root)
    if root.get("safety") != SAFETY: raise ProtocolV3TransactionError("transaction identity safety locks are invalid")
    observed = sha256(root.get("identity_sha256"), "transaction_identity.identity_sha256"); tx_id = transaction_id(root.get("transaction_id"))
    basis = dict(root); basis.pop("identity_sha256"); basis.pop("transaction_id"); expected = digest(basis)
    if observed != expected or tx_id != f"{TRANSACTION_PREFIX}:{expected}": raise ProtocolV3TransactionError("transaction identity digest or id mismatch")
    return TransactionIdentity(canonical(root), expected, tx_id)


def _validate_derived_slots(run: Mapping[str, Any], runtime: Mapping[str, Any], slots: Mapping[str, IdentitySlot]) -> None:
    expected = {
        RAW_DATA_SLOT: run["raw_data"], CODE_PIPELINE_SLOT: {"code": run["code"], "pipeline": run["pipeline"]},
        FEATURE_SLOT: run["features"], CONTEXT_SLOT: runtime, BOUNDARY_SLOT: run["boundary"],
        SIMULATOR_SLOT: run["simulator"], COST_SLOT: run["cost_model"], QUALITY_SLOT: run["quality_gates"],
        EXCHANGE_SLOT: run["exchange_info"], TRIAL_LEDGER_SLOT: run["trial_ledger_head"],
    }
    for name, payload in expected.items():
        row = slots[name].to_dict()
        if row["state"] != BOUND or normalize(row["payload"]) != normalize(payload): raise ProtocolV3TransactionError(f"derived identity slot differs from run fingerprint: {name}")
    execution = slots[EXECUTION_SLOT].to_dict()
    expected_execution = {
        "execution_parity_contract_version": EXECUTION_PARITY_CONTRACT_VERSION,
        "intrabar_execution_contract_version": INTRABAR_EXECUTION_CONTRACT_VERSION,
        "simulator_source_sha256": run["simulator"]["source_sha256"],
    }
    if execution["state"] != BOUND or execution["payload"] != expected_execution: raise ProtocolV3TransactionError("execution identity slot is not canonical")


def _validate_transition_slots(slots: Mapping[str, IdentitySlot]) -> None:
    expected = {
        CANDIDATE_SLOT: (NOT_APPLICABLE, CANDIDATE_PENDING_SCHEMA, "task15_not_implemented"),
        FOLD_SLOT: (NOT_APPLICABLE, FOLD_PENDING_SCHEMA, "task14_not_implemented"),
        ROTATION_SLOT: (GENESIS, ROTATION_GENESIS_SCHEMA, "no_rotation_state"),
    }
    for name, (state, schema, reason) in expected.items():
        row = slots[name].to_dict()
        if row["state"] != state or row["identity_schema"] != schema or row["reason"] != reason or row["payload"] != {}:
            raise ProtocolV3TransactionError(f"{name} is not the canonical typed Task-13 transition state")


def _validate_horizon_slot(slot: IdentitySlot) -> None:
    row = slot.to_dict(); payload = dict(row["payload"])
    if row["state"] != BOUND: raise ProtocolV3TransactionError("horizon identity must be BOUND")
    exact_keys(payload, {"contract_version", "max_label_horizon_minutes", "max_holding_period_minutes", "pending_entry_latency_minutes", "execution_bar_minutes", "policy_sha256"}, "horizon_identity.payload")
    policy = HorizonPolicy(payload["max_label_horizon_minutes"], payload["max_holding_period_minutes"], payload["pending_entry_latency_minutes"], payload["execution_bar_minutes"])
    if payload != {**policy.basis(), "policy_sha256": policy.policy_sha256}: raise ProtocolV3TransactionError("horizon identity payload is not canonical")


def _validate_store_heads_slot(slot: IdentitySlot, repository_root: str | Path) -> None:
    row = slot.to_dict()
    if row["identity_schema"] != STORE_HEADS_SCHEMA: raise ProtocolV3TransactionError("sealed store-head schema is invalid")
    if row["state"] == GENESIS:
        if row["reason"] != "no_protocol_v3_artifact_index_committed": raise ProtocolV3TransactionError("sealed store-head genesis reason is invalid")
        return
    if row["state"] != BOUND: raise ProtocolV3TransactionError("sealed store heads cannot be NOT_APPLICABLE")
    payload = dict(row["payload"]); exact_keys(payload, {"indexes"}, "sealed_store_heads.payload")
    if validate_artifact_heads(payload["indexes"], repository_root) != payload["indexes"]: raise ProtocolV3TransactionError("sealed store-head payload is not canonical")


def _artifact_head(index_path: str | Path, repo: Path) -> dict[str, Any]:
    bundle = read_compact_artifact_bundle(index_path, repo); path = Path(index_path)
    if not path.is_absolute(): path = repo / path
    relative = path.resolve(strict=True).relative_to(repo).as_posix(); payload = bundle.index.to_dict()
    return {"relative_path": relative, "index_id": payload["index_id"], "index_sha256": payload["index_sha256"], "parent_report_id": payload["parent_report"]["report_id"], "work_unit_id": payload["work_unit"]["work_unit_id"]}


def validate_artifact_heads(value: Any, repository_root: str | Path) -> list[dict[str, Any]]:
    if not isinstance(value, list): raise ProtocolV3TransactionError("artifact index heads must be a list")
    repo = repo_root(repository_root); normalized = []
    for index, raw in enumerate(value):
        row = dict(require_mapping(raw, f"artifact_indexes[{index}]")); exact_keys(row, {"relative_path", "index_id", "index_sha256", "parent_report_id", "work_unit_id"}, f"artifact_indexes[{index}]")
        relative = safe_relative(row["relative_path"], f"artifact_indexes[{index}].relative_path")
        if not str(relative).startswith(f"{ARTIFACT_INDEX_ROOT}/"): raise ProtocolV3TransactionError("artifact index head is outside the Task-12 index root")
        if row != _artifact_head(repo.joinpath(*relative.parts), repo): raise ProtocolV3TransactionError("artifact index head differs from revalidated index")
        normalized.append(row)
    if normalized != sorted(normalized, key=lambda row: row["relative_path"]): raise ProtocolV3TransactionError("artifact index heads must be canonically sorted")
    if len({row["relative_path"] for row in normalized}) != len(normalized): raise ProtocolV3TransactionError("artifact index heads must be unique")
    return normalized


def store_heads_from_identity(identity: TransactionIdentity) -> list[dict[str, Any]]:
    store = {row["name"]: row for row in identity.to_dict()["identity_slots"]}[STORE_HEADS_SLOT]
    return [] if store["state"] != BOUND else list(store["payload"]["indexes"])


def build_seed_state(manifest: PreRunManifest, *, origin_index: int, cycle_index: int, stage: str = "inner_search") -> dict[str, Any]:
    validate_pre_run_manifest(manifest); seed = origin_cycle_seed(manifest, origin_index=origin_index, cycle_index=cycle_index, stage=stage)
    basis = {"schema_version": "protocol_v3_checkpoint_seed_state_v1", "namespace": f"origin/{origin_index:02d}/cycle/{cycle_index:02d}/{stage}", "origin_index": origin_index, "cycle_index": cycle_index, "stage": stage, "derived_seed": seed}
    return {**basis, "seed_state_sha256": digest(basis)}


def validate_seed_state(value: Mapping[str, Any], manifest: PreRunManifest) -> dict[str, Any]:
    root = dict(require_mapping(value, "seed_state")); exact_keys(root, {"schema_version", "namespace", "origin_index", "cycle_index", "stage", "derived_seed", "seed_state_sha256"}, "seed_state")
    literal(root, "schema_version", "protocol_v3_checkpoint_seed_state_v1", "seed_state")
    expected = build_seed_state(manifest, origin_index=nonnegative_int(root["origin_index"], "seed_state.origin_index"), cycle_index=nonnegative_int(root["cycle_index"], "seed_state.cycle_index"), stage=required_text(root["stage"], "seed_state.stage"))
    if root != expected: raise ProtocolV3TransactionError("seed state does not match the frozen pre-run manifest")
    return root


def build_stop_state(*, completed_cycles: int, consecutive_non_improving_cycles: int) -> dict[str, Any]:
    reason = stagnation_stop_reason(completed_cycles=completed_cycles, consecutive_non_improving_cycles=consecutive_non_improving_cycles)
    basis = {"schema_version": "protocol_v3_checkpoint_stop_state_v1", "completed_cycles": completed_cycles, "consecutive_non_improving_cycles": consecutive_non_improving_cycles, "stop_reason": reason or "NOT_STOPPED"}
    return {**basis, "stop_state_sha256": digest(basis)}


def validate_stop_state(value: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(require_mapping(value, "stop_state")); exact_keys(root, {"schema_version", "completed_cycles", "consecutive_non_improving_cycles", "stop_reason", "stop_state_sha256"}, "stop_state")
    literal(root, "schema_version", "protocol_v3_checkpoint_stop_state_v1", "stop_state")
    expected = build_stop_state(completed_cycles=nonnegative_int(root["completed_cycles"], "stop_state.completed_cycles"), consecutive_non_improving_cycles=nonnegative_int(root["consecutive_non_improving_cycles"], "stop_state.consecutive_non_improving_cycles"))
    if root != expected: raise ProtocolV3TransactionError("stop/stagnation state is not canonical")
    return root


def budget_mapping(usage: BudgetUsage) -> dict[str, Any]:
    validate_budget_usage(usage)
    return {"cycles_by_origin": list(usage.cycles_by_origin), "reserved_generated": usage.reserved_generated, "reserved_tested": usage.reserved_tested, "reserved_walk_forward": usage.reserved_walk_forward, "reserved_finalists": usage.reserved_finalists}


def validate_budget_mapping(value: Mapping[str, Any]) -> None:
    exact_keys(value, {"cycles_by_origin", "reserved_generated", "reserved_tested", "reserved_walk_forward", "reserved_finalists"}, "budget usage")
    cycles = value["cycles_by_origin"]
    if not isinstance(cycles, list) or len(cycles) != 12: raise ProtocolV3TransactionError("budget usage must contain twelve origin counters")
    validate_budget_usage(BudgetUsage(tuple(cycles), value["reserved_generated"], value["reserved_tested"], value["reserved_walk_forward"], value["reserved_finalists"]))


def manifest_from_mapping(value: Mapping[str, Any]) -> PreRunManifest:
    raw = dict(value); digest_value = raw.pop("manifest_sha256", None)
    if not isinstance(digest_value, str): raise ProtocolV3TransactionError("pre-run manifest digest is missing")
    manifest = PreRunManifest(canonical(raw), digest_value); validate_pre_run_manifest(manifest); return manifest


def strict_loads(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result: raise ProtocolV3TransactionError(f"duplicate JSON key is forbidden: {key}")
            result[key] = value
        return result
    def reject(value: str) -> None: raise ProtocolV3TransactionError(f"non-finite JSON constant is forbidden: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject)


def canonical(value: Any) -> str:
    try: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc: raise ProtocolV3TransactionError(f"value is not strict JSON: {exc}") from exc

def canonical_bytes(value: Mapping[str, Any]) -> bytes: return (canonical(value) + "\n").encode("utf-8")
def digest(value: Any) -> str: return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
def normalize(value: Any) -> Any: return json.loads(canonical(value))

def require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping): raise ProtocolV3TransactionError(f"{path} must be an object")
    return value

def exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(value); extra = set(value) - expected
    if missing or extra: raise ProtocolV3TransactionError(f"{path} keys are invalid; missing={sorted(missing)} extra={sorted(extra)}")

def literal(value: Mapping[str, Any], key: str, expected: Any, path: str) -> None:
    observed = value.get(key)
    if observed != expected or type(observed) is not type(expected): raise ProtocolV3TransactionError(f"{path}.{key} must be {expected!r}")

def required_slot_name(value: Any) -> str:
    if value not in REQUIRED_IDENTITY_SLOTS: raise ProtocolV3TransactionError(f"identity slot name is invalid: {value!r}")
    return str(value)

def safe_id(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID.fullmatch(value): raise ProtocolV3TransactionError(f"{path} is not a safe identifier")
    return value

def schema_identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SCHEMA_ID.fullmatch(value): raise ProtocolV3TransactionError(f"{path} is not a valid schema identifier")
    return value

def required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip(): raise ProtocolV3TransactionError(f"{path} must be a non-empty string")
    return value.strip()

def sha256(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value): raise ProtocolV3TransactionError(f"{path} must be a lowercase SHA-256 digest")
    return value

def transaction_id(value: Any) -> str:
    if not isinstance(value, str) or not _TRANSACTION_ID.fullmatch(value): raise ProtocolV3TransactionError("transaction_id is invalid")
    return value

def checkpoint_id(value: Any) -> str:
    if not isinstance(value, str) or not _CHECKPOINT_ID.fullmatch(value): raise ProtocolV3TransactionError("checkpoint_id is invalid")
    return value

def cache_id(value: Any) -> str:
    if not isinstance(value, str) or not _CACHE_ID.fullmatch(value): raise ProtocolV3TransactionError("cache_record_id is invalid")
    return value

def safe_relative(value: Any, path: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value: raise ProtocolV3TransactionError(f"{path} must be a POSIX relative path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "." in relative.parts: raise ProtocolV3TransactionError(f"{path} escapes its root")
    return relative

def positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0: raise ProtocolV3TransactionError(f"{path} must be a positive integer")
    return value

def nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0: raise ProtocolV3TransactionError(f"{path} must be a non-negative integer")
    return value

def finite_json(value: Any, path: str) -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str): return
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value): raise ProtocolV3TransactionError(f"{path} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str): raise ProtocolV3TransactionError(f"{path} contains a non-string key")
            finite_json(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value): finite_json(item, f"{path}[{index}]")
        return
    raise ProtocolV3TransactionError(f"{path} contains a non-JSON value")

def reject_raw(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_RAW_KEYS: raise ProtocolV3TransactionError(f"{path} embeds forbidden raw market data")
            reject_raw(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value): reject_raw(item, f"{path}[{index}]")

def repo_root(value: str | Path) -> Path:
    path = Path(value)
    if not path.exists() or not path.is_dir() or path.is_symlink(): raise ProtocolV3TransactionError("repository_root must be an existing real directory")
    return path.resolve()

__all__ = [
    "BOUND", "GENESIS", "NOT_APPLICABLE",
    "CACHE_RECORD_SCHEMA_VERSION", "CACHE_ROOT",
    "CHECKPOINT_HEAD_SCHEMA_VERSION", "CHECKPOINT_ROOT", "CHECKPOINT_SCHEMA_VERSION",
    "IDENTITY_SLOT_SCHEMA_VERSION", "LOCK_RECOVERY_ROOT", "LOCK_ROOT", "LOCK_SCHEMA_VERSION",
    "REQUIRED_IDENTITY_SLOTS", "TRANSACTION_CONTRACT_PATH", "TRANSACTION_CONTRACT_SCHEMA",
    "TRANSACTION_CONTRACT_VERSION", "TRANSACTION_IDENTITY_SCHEMA_VERSION",
    "CANDIDATE_PENDING_SCHEMA", "FOLD_PENDING_SCHEMA", "ROTATION_GENESIS_SCHEMA", "STORE_HEADS_SCHEMA",
    "CANDIDATE_SLOT", "FOLD_SLOT", "ROTATION_SLOT", "STORE_HEADS_SLOT",
    "CacheRecord", "IdentitySlot", "ProtocolV3TransactionError", "TransactionCheckpoint",
    "TransactionIdentity", "TransactionLock",
    "build_bound_identity_slot", "build_genesis_identity_slot",
    "build_not_applicable_identity_slot", "build_sealed_store_heads_slot",
    "build_seed_state", "build_stop_state", "build_transaction_identity",
    "load_transaction_contract", "validate_identity_slot", "validate_seed_state",
    "validate_stop_state", "validate_transaction_contract", "validate_transaction_identity",
]
