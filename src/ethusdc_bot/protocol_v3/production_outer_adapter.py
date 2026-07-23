"""Real-data execution planning for the Protocol-v3 outer-origin adapter.

This module proves that the frozen three-market archives, the twelve causal
origins, all six inner folds, the current pipeline generation, and the
permanent trial ledger agree before any expensive candidate evaluation starts.
It intentionally does not claim that the executor exists: a planning
attestation alone cannot clear Task 33.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Final

from ethusdc_bot.path_safety import is_path_within

from .boundaries import build_monthly_process_boundary_plan
from .data_snapshot import validate_frozen_data_snapshot
from .inner_folds import build_inner_fold_plan_for_origin
from .legacy_multiplicity import (
    load_legacy_multiplicity_policy,
    validate_ledger_status_for_legacy_floor,
)
from .pipeline import build_pipeline_generation
from .production_runtime import load_production_runtime_inputs
from .run_identity import validate_exchange_info_snapshot
from .runtime_state import HorizonPolicy
from .trial_ledger import TrialLedgerSnapshot, read_trial_ledger

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_production_outer_adapter_contract.json"
)
CONTRACT_SCHEMA_VERSION: Final = (
    "protocol_v3_production_outer_adapter_contract_v1"
)
CONTRACT_VERSION: Final = "protocol_v3_real_outer_origin_production_adapter_v1"
PLAN_SCHEMA_VERSION: Final = "protocol_v3_production_outer_adapter_plan_v1"
PLAN_READY: Final = "ADAPTER_PLAN_READY"
EXECUTOR_NOT_READY: Final = "EXECUTOR_NOT_READY"
MARKETS: Final = ("ETHUSDC", "BTCUSDC", "ETHBTC")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_DAY_FILE = re.compile(
    r"^(ETHUSDC|BTCUSDC|ETHBTC)-1m-(\d{4}-\d{2}-\d{2})\.zip$"
)
_TASK_BINDING_FILES: Final = {
    "13": (
        "configs/protocol_v3_transaction_contract.json",
        "src/ethusdc_bot/protocol_v3/transactional_cache.py",
        "src/ethusdc_bot/protocol_v3/transactional_cache_model.py",
        "src/ethusdc_bot/protocol_v3/transactional_cache_store.py",
    ),
    "14": (
        "configs/protocol_v3_inner_fold_contract.json",
        "src/ethusdc_bot/protocol_v3/inner_folds.py",
        "src/ethusdc_bot/protocol_v3/production_fold_evaluator.py",
    ),
    "15": (
        "configs/protocol_v3_inner_selection_contract.json",
        "src/ethusdc_bot/protocol_v3/inner_selection.py",
    ),
    "16": (
        "configs/protocol_v3_candidate_matrix_contract.json",
        "src/ethusdc_bot/protocol_v3/candidate_matrix.py",
        "src/ethusdc_bot/protocol_v3/production_inner_cycle.py",
    ),
    "17": (
        "configs/protocol_v3_pbo_contract.json",
        "src/ethusdc_bot/protocol_v3/pbo.py",
    ),
    "18": (
        "configs/protocol_v3_dsr_contract.json",
        "src/ethusdc_bot/protocol_v3/dsr.py",
    ),
    "19": (
        "configs/protocol_v3_feature_store_contract.json",
        "src/ethusdc_bot/protocol_v3/feature_store.py",
    ),
    "20": (
        "configs/protocol_v3_opportunity_regime_contract.json",
        "src/ethusdc_bot/protocol_v3/opportunity_regime.py",
    ),
    "21": (
        "configs/protocol_v3_specialists_contract.json",
        "src/ethusdc_bot/protocol_v3/specialists.py",
    ),
    "22": (
        "configs/protocol_v3_router_bundle_contract.json",
        "src/ethusdc_bot/protocol_v3/router_bundle.py",
    ),
    "23": (
        "configs/protocol_v3_outer_origins_contract.json",
        "src/ethusdc_bot/protocol_v3/outer_origins.py",
    ),
    "24": (
        "configs/protocol_v3_runtime_state_contract.json",
        "src/ethusdc_bot/protocol_v3/runtime_state.py",
    ),
    "25": (
        "configs/protocol_v3_outer_mtm_ledger_contract.json",
        "src/ethusdc_bot/protocol_v3/outer_mtm_ledger.py",
    ),
    "26": (
        "configs/protocol_v3_monthly_quality_gate_contract.json",
        "src/ethusdc_bot/protocol_v3/monthly_quality_gate.py",
    ),
    "27": (
        "configs/protocol_v3_historical_diagnostics_contract.json",
        "src/ethusdc_bot/protocol_v3/historical_diagnostics.py",
        "src/ethusdc_bot/protocol_v3/hindsight_solvers.py",
        "src/ethusdc_bot/protocol_v3/hindsight_binding.py",
    ),
}
_SAFETY: Final = {
    "api_keys": "forbidden",
    "canonical_adoption": "locked",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_PROCESS_POLICY: Final = {
    "outer_origins": 12,
    "cycles_per_origin_max": 8,
    "inner_folds_per_origin": 6,
    "validation_days_per_fold": 60,
    "process_oos_days": 365,
    "training_days_per_origin": 730,
    "raw_archive_inventory_must_cover_frozen_snapshot_interval": True,
    "task13_resume_required": True,
    "plan_write_is_create_only": True,
    "old_protocol_v2_runner_forbidden": True,
    "fixture_evidence_forbidden": True,
}


class ProductionOuterAdapterError(ValueError):
    """Raised when real-data adapter planning is incomplete or contradictory."""


@dataclass(frozen=True)
class ProductionOuterAdapterPlan:
    canonical_json: str
    plan_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["plan_sha256"] = self.plan_sha256
        return value


def load_production_outer_adapter_contract(
    repo_root: str | Path,
) -> dict[str, Any]:
    root = Path(repo_root).resolve(strict=True)
    try:
        value = _strict_loads(
            (root / CONTRACT_PATH).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProductionOuterAdapterError(
            "production outer-adapter contract is unreadable"
        ) from exc
    if not isinstance(value, dict):
        raise ProductionOuterAdapterError(
            "production outer-adapter contract must be an object"
        )
    if (
        value.get("schema_version") != CONTRACT_SCHEMA_VERSION
        or value.get("protocol_version") != PROTOCOL_VERSION
        or value.get("contract_version") != CONTRACT_VERSION
        or value.get("markets") != list(MARKETS)
        or value.get("process_policy") != _PROCESS_POLICY
        or value.get("safety") != _SAFETY
    ):
        raise ProductionOuterAdapterError(
            "production outer-adapter contract is not canonical"
        )
    if value.get("readiness_policy") != {
        "plan_state": PLAN_READY,
        "execution_state_before_executor": EXECUTOR_NOT_READY,
        "plan_alone_may_clear_task33": False,
        "plan_alone_may_start_research": False,
        "task33_requires_validated_executor_attestation": True,
    }:
        raise ProductionOuterAdapterError(
            "production outer-adapter readiness policy is unsafe"
        )
    expected_tasks = {str(index) for index in range(13, 28)}
    if set(value.get("required_task_contracts", {})) != expected_tasks:
        raise ProductionOuterAdapterError(
            "production outer-adapter task range is incomplete"
        )
    return value


def build_production_outer_adapter_plan(
    *,
    repo_root: str | Path,
    raw_root: str | Path,
    data_snapshot: Mapping[str, Any],
    exchange_info_snapshot: Mapping[str, Any],
    trial_ledger: TrialLedgerSnapshot,
    code_commit: str,
) -> ProductionOuterAdapterPlan:
    repo = Path(repo_root).resolve(strict=True)
    contract = load_production_outer_adapter_contract(repo)
    commit = str(code_commit).strip().lower()
    if not _COMMIT.fullmatch(commit):
        raise ProductionOuterAdapterError(
            "code_commit must be a full lowercase git SHA"
        )
    validate_frozen_data_snapshot(data_snapshot, repo_root=repo)
    validate_exchange_info_snapshot(exchange_info_snapshot, repo_root=repo)
    ledger = _current_ledger(trial_ledger)
    policy = load_legacy_multiplicity_policy(repo)
    validate_ledger_status_for_legacy_floor(ledger.status.to_dict(), policy)
    runtime = load_production_runtime_inputs(repo)
    horizon = _horizon(runtime["horizon_policy"])
    generation = build_pipeline_generation(repo)
    _validate_task_bindings(contract, generation.basis(), repo)

    snapshot = _mapping(data_snapshot, "data_snapshot")
    boundary = _mapping(snapshot.get("boundary"), "data_snapshot.boundary")
    process_end = _day(
        boundary.get("process_end_exclusive"),
        "data_snapshot.boundary.process_end_exclusive",
    )
    plan = build_monthly_process_boundary_plan(process_end)
    raw = _real_external_root(raw_root, repo)
    inventory = _archive_inventory(raw, snapshot)

    origins = []
    for origin in plan.origins:
        folds = build_inner_fold_plan_for_origin(
            origin, horizon, repo_root=repo
        )
        origins.append(
            {
                "origin_index": origin.origin_index,
                "training_start_inclusive": (
                    origin.training_start_inclusive.isoformat()
                ),
                "training_end_exclusive": (
                    origin.training_end_exclusive.isoformat()
                ),
                "test_start_inclusive": origin.test_start_inclusive.isoformat(),
                "test_end_exclusive": origin.test_end_exclusive.isoformat(),
                "fold_plan_sha256": folds.plan_sha256,
                "fold_count": len(folds.folds),
                "validation_days": sum(
                    fold.validation_days for fold in folds.folds
                ),
                "max_cycles": 8,
            }
        )
    task_bindings = _task_bindings(contract, repo)
    basis = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "state": PLAN_READY,
        "execution_state": EXECUTOR_NOT_READY,
        "code_commit": commit,
        "pipeline_generation_id": generation.generation_id,
        "data_snapshot_sha256": snapshot["snapshot_sha256"],
        "exchange_info_snapshot_sha256": (
            exchange_info_snapshot["snapshot_sha256"]
        ),
        "trial_ledger_head_sha256": ledger.status.head_sha256,
        "legacy_multiplicity_floor": policy.legacy_multiplicity_floor,
        "runtime_contract_version": runtime["contract_version"],
        "raw_root_sha256": _digest(str(raw)),
        "archive_inventory": inventory,
        "process_start_inclusive": (
            plan.process_start_inclusive.isoformat()
        ),
        "process_end_exclusive": plan.process_end_exclusive.isoformat(),
        "origin_count": len(origins),
        "origins": origins,
        "task_bindings": task_bindings,
        "work_budget": {
            "outer_origins": 12,
            "max_cycles": 96,
            "max_generated_candidates": 3840,
            "max_tested_candidates": 1152,
            "max_walk_forward_candidates": 288,
            "max_finalists": 192,
        },
        "resume": {
            "task": 13,
            "transactional_resume_required": True,
            "cache_reuse_is_not_new_trial": True,
        },
        "task33": {
            "plan_may_clear_blocker": False,
            "executor_attestation_required": True,
            "full_research_run_started": False,
        },
        "safety": dict(_SAFETY),
    }
    return validate_production_outer_adapter_plan(
        ProductionOuterAdapterPlan(_canonical(basis), _digest(basis)),
        repo_root=repo,
    )


def validate_production_outer_adapter_plan(
    value: ProductionOuterAdapterPlan | Mapping[str, Any],
    *,
    repo_root: str | Path,
) -> ProductionOuterAdapterPlan:
    root = (
        value.to_dict()
        if isinstance(value, ProductionOuterAdapterPlan)
        else dict(_mapping(value, "production_outer_adapter_plan"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "state",
        "execution_state",
        "code_commit",
        "pipeline_generation_id",
        "data_snapshot_sha256",
        "exchange_info_snapshot_sha256",
        "trial_ledger_head_sha256",
        "legacy_multiplicity_floor",
        "runtime_contract_version",
        "raw_root_sha256",
        "archive_inventory",
        "process_start_inclusive",
        "process_end_exclusive",
        "origin_count",
        "origins",
        "task_bindings",
        "work_budget",
        "resume",
        "task33",
        "safety",
        "plan_sha256",
    }
    if set(root) != required:
        raise ProductionOuterAdapterError(
            "production outer-adapter plan fields are invalid"
        )
    if (
        root["schema_version"] != PLAN_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
        or root["state"] != PLAN_READY
        or root["execution_state"] != EXECUTOR_NOT_READY
        or root["safety"] != _SAFETY
        or not _COMMIT.fullmatch(str(root["code_commit"]))
    ):
        raise ProductionOuterAdapterError(
            "production outer-adapter plan identity is invalid"
        )
    repo = Path(repo_root).resolve(strict=True)
    contract = load_production_outer_adapter_contract(repo)
    generation = build_pipeline_generation(repo)
    if root["pipeline_generation_id"] != generation.generation_id:
        raise ProductionOuterAdapterError(
            "production outer-adapter pipeline generation is stale"
        )
    if root["task_bindings"] != _task_bindings(contract, repo):
        raise ProductionOuterAdapterError(
            "production outer-adapter task bindings are stale"
        )
    origins = root["origins"]
    if (
        not isinstance(origins, list)
        or any(not isinstance(row, Mapping) for row in origins)
    ):
        raise ProductionOuterAdapterError(
            "production outer-adapter origins must be a list of objects"
        )
    plan = build_monthly_process_boundary_plan(
        _day(root["process_end_exclusive"], "process_end_exclusive")
    )
    if (
        root["process_start_inclusive"]
        != plan.process_start_inclusive.isoformat()
        or root["origin_count"] != 12
        or len(origins) != 12
        or [row.get("origin_index") for row in origins]
        != list(range(1, 13))
        or any(
            row.get("fold_count") != 6
            or row.get("validation_days") != 360
            or row.get("max_cycles") != 8
            for row in origins
        )
    ):
        raise ProductionOuterAdapterError(
            "production outer-adapter origin plan is invalid"
        )
    if root["task33"] != {
        "plan_may_clear_blocker": False,
        "executor_attestation_required": True,
        "full_research_run_started": False,
    }:
        raise ProductionOuterAdapterError(
            "production outer-adapter plan overclaims readiness"
        )
    observed = _sha(root.pop("plan_sha256"), "plan_sha256")
    if observed != _digest(root):
        raise ProductionOuterAdapterError(
            "production outer-adapter plan digest mismatch"
        )
    return ProductionOuterAdapterPlan(_canonical(root), observed)


def write_production_outer_adapter_plan(
    value: ProductionOuterAdapterPlan | Mapping[str, Any],
    path: str | Path,
    *,
    repo_root: str | Path,
) -> Path:
    """Persist a validated plan exactly once without replacing evidence."""

    plan = validate_production_outer_adapter_plan(value, repo_root=repo_root)
    target = Path(path)
    if not target.is_absolute():
        raise ProductionOuterAdapterError(
            "production outer-adapter plan path must be absolute"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical(plan.to_dict()) + "\n")
    except FileExistsError as exc:
        raise ProductionOuterAdapterError(
            "production outer-adapter plan is create-only"
        ) from exc
    return target


def _archive_inventory(
    raw_root: Path, snapshot: Mapping[str, Any]
) -> dict[str, Any]:
    raw_interval = _mapping(
        snapshot.get("raw_interval"), "data_snapshot.raw_interval"
    )
    first = _day(
        raw_interval.get("audited_full_day_start"),
        "raw_interval.audited_full_day_start",
    )
    last = _day(
        raw_interval.get("audited_full_day_end_inclusive"),
        "raw_interval.audited_full_day_end_inclusive",
    )
    required_days = {
        first + timedelta(days=offset)
        for offset in range((last - first).days + 1)
    }
    rows = []
    for symbol in MARKETS:
        folder = (
            raw_root
            / "raw"
            / "binance"
            / "spot"
            / symbol
            / "klines"
            / "1m"
        )
        if (
            not folder.is_dir()
            or folder.is_symlink()
            or not is_path_within(folder.resolve(), raw_root)
        ):
            raise ProductionOuterAdapterError(
                f"{symbol} archive folder is missing or unsafe"
            )
        by_day: dict[date, Path] = {}
        for path in folder.glob(f"{symbol}-1m-*.zip"):
            match = _DAY_FILE.fullmatch(path.name)
            if match is None or path.is_symlink() or not path.is_file():
                continue
            day = _day(match.group(2), f"{symbol} archive day")
            if day in by_day:
                raise ProductionOuterAdapterError(
                    f"{symbol} has duplicate daily archives"
                )
            by_day[day] = path
        missing = sorted(required_days - set(by_day))
        if missing:
            raise ProductionOuterAdapterError(
                f"{symbol} archive inventory misses {len(missing)} required days"
            )
        inventory_rows = []
        for day in sorted(required_days):
            archive = by_day[day]
            checksum = archive.with_name(archive.name + ".CHECKSUM")
            if (
                not checksum.is_file()
                or checksum.is_symlink()
                or checksum.stat().st_size <= 0
            ):
                raise ProductionOuterAdapterError(
                    f"{symbol} archive checksum is missing"
                )
            inventory_rows.append(
                {
                    "day": day.isoformat(),
                    "archive_bytes": archive.stat().st_size,
                    "checksum_bytes": checksum.stat().st_size,
                }
            )
        rows.append(
            {
                "symbol": symbol,
                "required_day_count": len(inventory_rows),
                "first_day": first.isoformat(),
                "last_day": last.isoformat(),
                "inventory_sha256": _digest(inventory_rows),
            }
        )
    basis = {
        "markets": rows,
        "common_required_day_count": len(required_days),
    }
    return {**basis, "inventory_sha256": _digest(basis)}


def _task_bindings(
    contract: Mapping[str, Any], repo: Path
) -> list[dict[str, Any]]:
    versions = _mapping(
        contract.get("required_task_contracts"),
        "required_task_contracts",
    )
    return [
        {
            "task": int(task),
            "contract_version": versions[task],
            "source_paths": list(_TASK_BINDING_FILES[task]),
            "source_sha256": _paths_digest(repo, _TASK_BINDING_FILES[task]),
        }
        for task in sorted(_TASK_BINDING_FILES, key=int)
    ]


def _validate_task_bindings(
    contract: Mapping[str, Any],
    generation_basis: Mapping[str, Any],
    repo: Path,
) -> None:
    available = set()
    for value in _mapping(
        generation_basis.get("component_contracts"),
        "pipeline.component_contracts",
    ).values():
        if isinstance(value, list):
            available.update(str(item) for item in value)
        else:
            available.add(str(value))
    if CONTRACT_VERSION not in available:
        raise ProductionOuterAdapterError(
            "pipeline generation omits the production outer adapter"
        )
    required = _mapping(
        contract.get("required_task_contracts"),
        "required_task_contracts",
    )
    for task, paths in _TASK_BINDING_FILES.items():
        try:
            task_contract = _strict_loads(
                (repo / paths[0]).read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProductionOuterAdapterError(
                f"Task-{task} contract is unreadable"
            ) from exc
        if (
            not isinstance(task_contract, Mapping)
            or task_contract.get("contract_version") != required[task]
        ):
            raise ProductionOuterAdapterError(
                f"Task-{task} contract version is stale"
            )
    _task_bindings(contract, repo)


def _paths_digest(repo: Path, paths: tuple[str, ...]) -> str:
    rows = []
    for relative in paths:
        path = repo / relative
        if not path.is_file() or path.is_symlink():
            raise ProductionOuterAdapterError(
                f"required adapter source is missing or unsafe: {relative}"
            )
        rows.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return _digest(rows)


def _current_ledger(value: TrialLedgerSnapshot) -> TrialLedgerSnapshot:
    if not isinstance(value, TrialLedgerSnapshot):
        raise ProductionOuterAdapterError(
            "verified permanent trial-ledger snapshot required"
        )
    current = read_trial_ledger(value.root)
    if current.status.head_sha256 != value.status.head_sha256:
        raise ProductionOuterAdapterError(
            "permanent trial ledger advanced during adapter planning"
        )
    return current


def _real_external_root(value: str | Path, repo: Path) -> Path:
    candidate = Path(value)
    if (
        not candidate.is_absolute()
        or not candidate.is_dir()
        or candidate.is_symlink()
    ):
        raise ProductionOuterAdapterError(
            "raw_root must be an existing real absolute directory"
        )
    resolved = candidate.resolve(strict=True)
    if (
        resolved == repo
        or is_path_within(resolved, repo)
        or is_path_within(repo, resolved)
    ):
        raise ProductionOuterAdapterError(
            "raw_root must remain outside the repository"
        )
    return resolved


def _horizon(value: Mapping[str, Any]) -> HorizonPolicy:
    try:
        return HorizonPolicy(
            max_label_horizon_minutes=value["max_label_horizon_minutes"],
            max_holding_period_minutes=value["max_holding_period_minutes"],
            pending_entry_latency_minutes=value[
                "pending_entry_latency_minutes"
            ],
            execution_bar_minutes=value["execution_bar_minutes"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionOuterAdapterError(
            "frozen production HorizonPolicy is invalid"
        ) from exc


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionOuterAdapterError(f"{path} must be an object")
    return dict(value)


def _day(value: Any, path: str) -> date:
    if not isinstance(value, str):
        raise ProductionOuterAdapterError(f"{path} must be an ISO day")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ProductionOuterAdapterError(
            f"{path} must be an ISO day"
        ) from exc


def _sha(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ProductionOuterAdapterError(
            f"{path} must be a lowercase SHA-256 digest"
        )
    return value


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _strict_loads(text: str) -> Any:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProductionOuterAdapterError(
                    f"duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    return json.loads(
        text,
        object_pairs_hook=hook,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ProductionOuterAdapterError(
                f"non-finite JSON constant: {token}"
            )
        ),
    )


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_VERSION",
    "EXECUTOR_NOT_READY",
    "PLAN_READY",
    "ProductionOuterAdapterError",
    "ProductionOuterAdapterPlan",
    "build_production_outer_adapter_plan",
    "load_production_outer_adapter_contract",
    "validate_production_outer_adapter_plan",
    "write_production_outer_adapter_plan",
]
