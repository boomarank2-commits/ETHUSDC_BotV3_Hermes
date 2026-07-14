"""Frozen Protocol v3 pipeline identity, seeds, budgets, and stop rules.

This module implements task 3 only.  It does not run candidate search, create a
trial ledger, load market data, or evaluate PnL.  It turns the already approved
pipeline contract into a content-addressed generation and supplies fail-closed
primitives that later Protocol v3 orchestration must use.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from .boundaries import (
    OUTER_ORIGINS,
    MonthlyProcessBoundaryPlan,
    build_monthly_process_boundary_plan,
    validate_monthly_process_boundary_plan,
)

PIPELINE_CONTRACT_PATH = Path("configs/protocol_v3_pipeline_contract.json")
PIPELINE_SCHEMA_VERSION = "protocol_v3_pipeline_contract_v1"
PIPELINE_CONTRACT_VERSION = "monthly_refit_pipeline_v3.0.0"
PRE_RUN_MANIFEST_SCHEMA_VERSION = "protocol_v3_pre_run_manifest_v1"
PIPELINE_GENERATION_PREFIX = "protocol_v3_pipeline_sha256"

_CANONICAL_BUDGET = {
    "outer_origins": 12,
    "max_cycles_per_origin": 8,
    "generated_per_cycle": 40,
    "tested_per_cycle": 12,
    "walk_forward_per_cycle": 3,
    "finalists_per_cycle": 2,
    "max_total_cycles": 96,
    "max_total_generated": 3840,
    "max_total_tested": 1152,
    "max_total_walk_forward": 288,
    "max_total_finalists": 192,
}
_CANONICAL_STOP_POLICY = {
    "maximum_cycles_reason": "max_cycles_reached",
    "stagnation_reason": "selection_stagnation_3_cycles",
    "stagnation_patience_cycles": 3,
    "minimum_completed_cycles_before_stagnation": 3,
    "may_expand_budget": False,
    "target_hit_may_stop_search": False,
}
_CANONICAL_SEED_POLICY = {
    "algorithm": "sha256_canonical_pre_run_manifest_namespace_v1",
    "seed_bits": 64,
    "timestamps_forbidden": True,
    "system_random_forbidden": True,
}
_CANONICAL_LEDGER_POLICY = {
    "forward_ledger_namespace_prefix": "protocol_v3_forward_generation",
    "permanent_trial_counter_namespace": "protocol_v3_permanent_trial_counter_v1",
    "new_generation_resets_forward_ledger": True,
    "new_generation_resets_permanent_trial_counter": False,
}
_CANONICAL_TARGET_POLICY = {
    "target_usdc_per_calendar_day": 3.0,
    "target_is_acceptance_metric": True,
    "target_is_search_loss": False,
    "target_hit_may_stop_search": False,
}
_CANONICAL_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_REQUIRED_COMPONENTS = {
    "boundary_rules",
    "candidate_families",
    "context_policy",
    "cost_model",
    "feature_contract",
    "quality_gates",
    "ranking",
    "search_space",
    "simulator",
}
_FORBIDDEN_MANIFEST_TIME_KEYS = {
    "created_at",
    "generated_at",
    "started_at",
    "timestamp",
    "wall_clock_time",
}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_NAMESPACE_RE = re.compile(r"^[a-z0-9][a-z0-9._:/-]{0,127}$")


class PipelineContractError(ValueError):
    """Raised when Protocol v3 identity, budget, or seed state is contradictory."""


@dataclass(frozen=True)
class PipelineGeneration:
    """Immutable content-addressed identity for one pipeline generation."""

    generation_id: str
    contract_sha256: str
    canonical_basis_json: str
    forward_ledger_namespace: str
    permanent_trial_counter_namespace: str

    def basis(self) -> dict[str, Any]:
        return json.loads(self.canonical_basis_json)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation_id": self.generation_id,
            "contract_sha256": self.contract_sha256,
            "generation_basis": self.basis(),
            "forward_ledger_namespace": self.forward_ledger_namespace,
            "permanent_trial_counter_namespace": self.permanent_trial_counter_namespace,
        }


@dataclass(frozen=True)
class PreRunManifest:
    """Canonical timestamp-free manifest from which all run seeds derive."""

    canonical_payload_json: str
    manifest_sha256: str

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_payload_json)

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        payload["manifest_sha256"] = self.manifest_sha256
        return payload


@dataclass(frozen=True)
class SearchBudgetPolicy:
    outer_origins: int = 12
    max_cycles_per_origin: int = 8
    generated_per_cycle: int = 40
    tested_per_cycle: int = 12
    walk_forward_per_cycle: int = 3
    finalists_per_cycle: int = 2
    max_total_cycles: int = 96
    max_total_generated: int = 3840
    max_total_tested: int = 1152
    max_total_walk_forward: int = 288
    max_total_finalists: int = 192

    @classmethod
    def canonical(cls) -> "SearchBudgetPolicy":
        return cls(**_CANONICAL_BUDGET)

    def to_dict(self) -> dict[str, int]:
        return {
            "outer_origins": self.outer_origins,
            "max_cycles_per_origin": self.max_cycles_per_origin,
            "generated_per_cycle": self.generated_per_cycle,
            "tested_per_cycle": self.tested_per_cycle,
            "walk_forward_per_cycle": self.walk_forward_per_cycle,
            "finalists_per_cycle": self.finalists_per_cycle,
            "max_total_cycles": self.max_total_cycles,
            "max_total_generated": self.max_total_generated,
            "max_total_tested": self.max_total_tested,
            "max_total_walk_forward": self.max_total_walk_forward,
            "max_total_finalists": self.max_total_finalists,
        }

    def validate(self) -> None:
        if self.to_dict() != _CANONICAL_BUDGET:
            raise PipelineContractError("Protocol v3 search budgets must match canonical 12/8/40/12/3/2 limits")
        if self.outer_origins != OUTER_ORIGINS:
            raise PipelineContractError("budget outer_origins conflicts with the boundary contract")
        if self.max_total_cycles != self.outer_origins * self.max_cycles_per_origin:
            raise PipelineContractError("max_total_cycles is inconsistent")
        expected_totals = {
            "max_total_generated": self.max_total_cycles * self.generated_per_cycle,
            "max_total_tested": self.max_total_cycles * self.tested_per_cycle,
            "max_total_walk_forward": self.max_total_cycles * self.walk_forward_per_cycle,
            "max_total_finalists": self.max_total_cycles * self.finalists_per_cycle,
        }
        for field_name, expected in expected_totals.items():
            if getattr(self, field_name) != expected:
                raise PipelineContractError(f"{field_name} is inconsistent with per-cycle caps")


@dataclass(frozen=True)
class BudgetUsage:
    """Immutable full-cap reservations; one reservation equals one inner cycle."""

    cycles_by_origin: tuple[int, ...] = (0,) * OUTER_ORIGINS
    reserved_generated: int = 0
    reserved_tested: int = 0
    reserved_walk_forward: int = 0
    reserved_finalists: int = 0

    @property
    def total_cycles(self) -> int:
        return sum(self.cycles_by_origin)

    def reserve_next_cycle(
        self,
        origin_index: int,
        policy: SearchBudgetPolicy | None = None,
    ) -> "BudgetUsage":
        active_policy = policy or SearchBudgetPolicy.canonical()
        active_policy.validate()
        validate_budget_usage(self, active_policy)
        _validate_index(origin_index, 1, active_policy.outer_origins, "origin_index")
        offset = origin_index - 1
        if self.cycles_by_origin[offset] >= active_policy.max_cycles_per_origin:
            raise PipelineContractError(
                f"origin {origin_index} exceeds the {active_policy.max_cycles_per_origin}-cycle cap"
            )
        cycles = list(self.cycles_by_origin)
        cycles[offset] += 1
        updated = replace(
            self,
            cycles_by_origin=tuple(cycles),
            reserved_generated=self.reserved_generated + active_policy.generated_per_cycle,
            reserved_tested=self.reserved_tested + active_policy.tested_per_cycle,
            reserved_walk_forward=(
                self.reserved_walk_forward + active_policy.walk_forward_per_cycle
            ),
            reserved_finalists=self.reserved_finalists + active_policy.finalists_per_cycle,
        )
        validate_budget_usage(updated, active_policy)
        return updated


def validate_budget_usage(
    usage: BudgetUsage,
    policy: SearchBudgetPolicy | None = None,
) -> None:
    active_policy = policy or SearchBudgetPolicy.canonical()
    active_policy.validate()
    if len(usage.cycles_by_origin) != active_policy.outer_origins:
        raise PipelineContractError("budget usage must contain exactly twelve origin counters")
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > active_policy.max_cycles_per_origin
        for value in usage.cycles_by_origin
    ):
        raise PipelineContractError("origin cycle usage is invalid or above cap")
    total_cycles = usage.total_cycles
    expected = {
        "reserved_generated": total_cycles * active_policy.generated_per_cycle,
        "reserved_tested": total_cycles * active_policy.tested_per_cycle,
        "reserved_walk_forward": total_cycles * active_policy.walk_forward_per_cycle,
        "reserved_finalists": total_cycles * active_policy.finalists_per_cycle,
    }
    maxima = {
        "reserved_generated": active_policy.max_total_generated,
        "reserved_tested": active_policy.max_total_tested,
        "reserved_walk_forward": active_policy.max_total_walk_forward,
        "reserved_finalists": active_policy.max_total_finalists,
    }
    if total_cycles > active_policy.max_total_cycles:
        raise PipelineContractError("global cycle budget exceeded")
    for field_name, expected_value in expected.items():
        actual = getattr(usage, field_name)
        if isinstance(actual, bool) or not isinstance(actual, int) or actual != expected_value:
            raise PipelineContractError(f"{field_name} does not match full-cap cycle reservations")
        if actual > maxima[field_name]:
            raise PipelineContractError(f"{field_name} exceeds its global maximum")


def validate_actual_cycle_counts(
    *,
    generated: int,
    tested: int,
    walk_forward: int,
    finalists: int,
    policy: SearchBudgetPolicy | None = None,
) -> None:
    active_policy = policy or SearchBudgetPolicy.canonical()
    active_policy.validate()
    values = (generated, tested, walk_forward, finalists)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise PipelineContractError("actual cycle counts must be non-negative integers")
    if not finalists <= walk_forward <= tested <= generated:
        raise PipelineContractError("actual cycle counts must form nested stage subsets")
    caps = (
        active_policy.generated_per_cycle,
        active_policy.tested_per_cycle,
        active_policy.walk_forward_per_cycle,
        active_policy.finalists_per_cycle,
    )
    if any(value > cap for value, cap in zip(values, caps)):
        raise PipelineContractError("actual cycle count exceeds the frozen 40/12/3/2 caps")


def stagnation_stop_reason(
    *,
    completed_cycles: int,
    consecutive_non_improving_cycles: int,
    policy: SearchBudgetPolicy | None = None,
) -> str | None:
    """Return only the frozen shortening reason; this function never changes budgets."""

    active_policy = policy or SearchBudgetPolicy.canonical()
    active_policy.validate()
    _validate_index(completed_cycles, 0, active_policy.max_cycles_per_origin, "completed_cycles")
    _validate_index(
        consecutive_non_improving_cycles,
        0,
        completed_cycles,
        "consecutive_non_improving_cycles",
    )
    if (
        completed_cycles >= _CANONICAL_STOP_POLICY["minimum_completed_cycles_before_stagnation"]
        and consecutive_non_improving_cycles
        >= _CANONICAL_STOP_POLICY["stagnation_patience_cycles"]
    ):
        return str(_CANONICAL_STOP_POLICY["stagnation_reason"])
    return None


def build_pipeline_generation(
    repo_root: str | Path | None = None,
    *,
    contract_path: str | Path | None = None,
) -> PipelineGeneration:
    """Build a generation whose identity changes with any bound contract source."""

    root = _resolve_repo_root(repo_root)
    contract_file = (
        Path(contract_path)
        if contract_path is not None
        else root / PIPELINE_CONTRACT_PATH
    )
    if not contract_file.is_absolute():
        contract_file = root / contract_file
    contract = _load_json_object(contract_file, "pipeline contract")
    validate_pipeline_contract(contract)

    source_file_sha256: dict[str, str] = {}
    component_source_sha256: dict[str, str] = {}
    bindings = contract["source_bindings"]
    for component in sorted(bindings):
        rows: list[dict[str, str]] = []
        for relative_text in bindings[component]:
            relative = _validate_relative_repo_path(relative_text)
            source_path = root / Path(relative.as_posix())
            try:
                digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            except OSError as exc:
                raise PipelineContractError(
                    f"bound pipeline source is missing or unreadable: {relative.as_posix()}"
                ) from exc
            source_file_sha256[relative.as_posix()] = digest
            rows.append({"path": relative.as_posix(), "sha256": digest})
        component_source_sha256[component] = _sha256_json(rows)

    contract_sha256 = _sha256_json(contract)
    basis = {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "protocol_version": contract["protocol_version"],
        "pipeline_contract_version": contract["pipeline_contract_version"],
        "contract_sha256": contract_sha256,
        "component_contracts": contract["component_contracts"],
        "component_source_sha256": component_source_sha256,
        "source_file_sha256": dict(sorted(source_file_sha256.items())),
        "budget_policy": contract["budget_policy"],
        "stop_policy": contract["stop_policy"],
        "seed_policy": contract["seed_policy"],
        "ledger_policy": contract["ledger_policy"],
        "target_policy": contract["target_policy"],
        "safety": contract["safety"],
    }
    canonical_basis_json = _canonical_json(basis)
    basis_digest = hashlib.sha256(canonical_basis_json.encode("utf-8")).hexdigest()
    generation_id = f"{PIPELINE_GENERATION_PREFIX}:{basis_digest}"
    ledger = contract["ledger_policy"]
    generation = PipelineGeneration(
        generation_id=generation_id,
        contract_sha256=contract_sha256,
        canonical_basis_json=canonical_basis_json,
        forward_ledger_namespace=(
            f"{ledger['forward_ledger_namespace_prefix']}:{generation_id}"
        ),
        permanent_trial_counter_namespace=str(
            ledger["permanent_trial_counter_namespace"]
        ),
    )
    validate_pipeline_generation(generation)
    return generation


def validate_pipeline_contract(contract: Mapping[str, Any]) -> None:
    required_top = {
        "schema_version",
        "protocol_version",
        "pipeline_contract_version",
        "component_contracts",
        "source_bindings",
        "budget_policy",
        "stop_policy",
        "seed_policy",
        "ledger_policy",
        "target_policy",
        "safety",
    }
    if set(contract) != required_top:
        raise PipelineContractError("pipeline contract top-level fields are missing or unexpected")
    if contract.get("schema_version") != PIPELINE_SCHEMA_VERSION:
        raise PipelineContractError("pipeline contract schema version is invalid")
    if contract.get("protocol_version") != "3.0.0":
        raise PipelineContractError("pipeline protocol_version must equal 3.0.0")
    if contract.get("pipeline_contract_version") != PIPELINE_CONTRACT_VERSION:
        raise PipelineContractError("pipeline_contract_version is invalid")

    components = contract.get("component_contracts")
    bindings = contract.get("source_bindings")
    if not isinstance(components, dict) or set(components) != _REQUIRED_COMPONENTS:
        raise PipelineContractError("component_contracts must define every required pipeline component")
    if not isinstance(bindings, dict) or set(bindings) != _REQUIRED_COMPONENTS:
        raise PipelineContractError("source_bindings must define every required pipeline component")
    for component, version in components.items():
        if isinstance(version, str):
            valid_version = bool(version.strip())
        elif isinstance(version, list):
            valid_version = bool(version) and all(
                isinstance(item, str) and bool(item.strip()) for item in version
            )
        else:
            valid_version = False
        if not valid_version:
            raise PipelineContractError(f"component contract version is invalid: {component}")
    for component, paths in bindings.items():
        if not isinstance(paths, list) or not paths:
            raise PipelineContractError(f"source binding list is empty: {component}")
        normalized = [_validate_relative_repo_path(path).as_posix() for path in paths]
        if len(set(normalized)) != len(normalized):
            raise PipelineContractError(f"source binding contains duplicates: {component}")

    if contract.get("budget_policy") != _CANONICAL_BUDGET:
        raise PipelineContractError("budget policy must equal the frozen 12/8/40/12/3/2 contract")
    SearchBudgetPolicy(**dict(contract["budget_policy"])).validate()
    if contract.get("stop_policy") != _CANONICAL_STOP_POLICY:
        raise PipelineContractError("stop policy must equal the frozen three-cycle stagnation contract")
    if contract.get("seed_policy") != _CANONICAL_SEED_POLICY:
        raise PipelineContractError("seed policy is not canonical")
    if contract.get("ledger_policy") != _CANONICAL_LEDGER_POLICY:
        raise PipelineContractError("ledger reset policy is not canonical")
    if contract.get("target_policy") != _CANONICAL_TARGET_POLICY:
        raise PipelineContractError("target policy is not canonical")
    if contract.get("safety") != _CANONICAL_SAFETY:
        raise PipelineContractError("pipeline safety locks are not canonical")


def validate_pipeline_generation(generation: PipelineGeneration) -> None:
    basis = generation.basis()
    if basis.get("schema_version") != PIPELINE_SCHEMA_VERSION:
        raise PipelineContractError("pipeline generation schema is invalid")
    expected_digest = hashlib.sha256(
        generation.canonical_basis_json.encode("utf-8")
    ).hexdigest()
    expected_id = f"{PIPELINE_GENERATION_PREFIX}:{expected_digest}"
    if generation.generation_id != expected_id:
        raise PipelineContractError("pipeline generation id does not match its canonical basis")
    if basis.get("contract_sha256") != generation.contract_sha256:
        raise PipelineContractError("pipeline generation contract digest is inconsistent")
    ledger = basis.get("ledger_policy")
    if not isinstance(ledger, dict) or ledger != _CANONICAL_LEDGER_POLICY:
        raise PipelineContractError("pipeline generation ledger policy is invalid")
    expected_forward = (
        f"{ledger['forward_ledger_namespace_prefix']}:{generation.generation_id}"
    )
    if generation.forward_ledger_namespace != expected_forward:
        raise PipelineContractError("forward ledger namespace is not generation-specific")
    if (
        generation.permanent_trial_counter_namespace
        != ledger["permanent_trial_counter_namespace"]
    ):
        raise PipelineContractError("permanent trial counter namespace changed with generation")


def build_pre_run_manifest(
    generation: PipelineGeneration,
    boundary_plan: MonthlyProcessBoundaryPlan,
    *,
    code_commit: str,
) -> PreRunManifest:
    """Create a canonical timestamp-free manifest for one exact run boundary."""

    validate_pipeline_generation(generation)
    validate_monthly_process_boundary_plan(boundary_plan)
    normalized_commit = str(code_commit).strip().lower()
    if not _COMMIT_RE.fullmatch(normalized_commit):
        raise PipelineContractError("code_commit must be a full lowercase 40-character git SHA")
    boundary_payload = _boundary_plan_payload(boundary_plan)
    payload = {
        "schema_version": PRE_RUN_MANIFEST_SCHEMA_VERSION,
        "protocol_version": "3.0.0",
        "code_commit": normalized_commit,
        "pipeline_generation": generation.to_dict(),
        "boundary_plan": boundary_payload,
        "boundary_plan_sha256": _sha256_json(boundary_payload),
        "seed_policy": generation.basis()["seed_policy"],
        "budget_policy": generation.basis()["budget_policy"],
        "stop_policy": generation.basis()["stop_policy"],
        "target_policy": generation.basis()["target_policy"],
        "safety": generation.basis()["safety"],
    }
    _reject_forbidden_time_keys(payload)
    canonical_payload_json = _canonical_json(payload)
    manifest = PreRunManifest(
        canonical_payload_json=canonical_payload_json,
        manifest_sha256=hashlib.sha256(canonical_payload_json.encode("utf-8")).hexdigest(),
    )
    validate_pre_run_manifest(manifest)
    return manifest


def validate_pre_run_manifest(value: PreRunManifest | Mapping[str, Any]) -> None:
    if isinstance(value, PreRunManifest):
        payload = value.payload()
        manifest_sha256 = value.manifest_sha256
        canonical_payload_json = value.canonical_payload_json
    elif isinstance(value, Mapping):
        raw = dict(value)
        manifest_sha256 = raw.pop("manifest_sha256", None)
        payload = raw
        canonical_payload_json = _canonical_json(payload)
    else:
        raise PipelineContractError("pre-run manifest must be an object")

    required = {
        "schema_version",
        "protocol_version",
        "code_commit",
        "pipeline_generation",
        "boundary_plan",
        "boundary_plan_sha256",
        "seed_policy",
        "budget_policy",
        "stop_policy",
        "target_policy",
        "safety",
    }
    if set(payload) != required:
        raise PipelineContractError("pre-run manifest fields are missing or unexpected")
    if payload.get("schema_version") != PRE_RUN_MANIFEST_SCHEMA_VERSION:
        raise PipelineContractError("pre-run manifest schema is invalid")
    if payload.get("protocol_version") != "3.0.0":
        raise PipelineContractError("pre-run protocol version is invalid")
    if not isinstance(payload.get("code_commit"), str) or not _COMMIT_RE.fullmatch(
        payload["code_commit"]
    ):
        raise PipelineContractError("pre-run code_commit is invalid")
    if not isinstance(manifest_sha256, str) or manifest_sha256 != hashlib.sha256(
        canonical_payload_json.encode("utf-8")
    ).hexdigest():
        raise PipelineContractError("pre-run manifest digest mismatch")
    _reject_forbidden_time_keys(payload)

    generation_payload = payload.get("pipeline_generation")
    if not isinstance(generation_payload, dict):
        raise PipelineContractError("pre-run pipeline generation is missing")
    generation = _generation_from_dict(generation_payload)
    validate_pipeline_generation(generation)
    basis = generation.basis()
    for key in ("seed_policy", "budget_policy", "stop_policy", "target_policy", "safety"):
        if payload.get(key) != basis.get(key):
            raise PipelineContractError(f"pre-run {key} conflicts with pipeline generation")

    boundary_payload = payload.get("boundary_plan")
    if not isinstance(boundary_payload, dict):
        raise PipelineContractError("pre-run boundary plan is missing")
    if payload.get("boundary_plan_sha256") != _sha256_json(boundary_payload):
        raise PipelineContractError("pre-run boundary plan digest mismatch")
    process_end = boundary_payload.get("process_end_exclusive")
    if not isinstance(process_end, str):
        raise PipelineContractError("pre-run process_end_exclusive is missing")
    expected_boundary = _boundary_plan_payload(
        build_monthly_process_boundary_plan(process_end)
    )
    if boundary_payload != expected_boundary:
        raise PipelineContractError("pre-run boundary plan is not the canonical task-2 plan")


def derive_seed(
    manifest: PreRunManifest | Mapping[str, Any],
    namespace: str,
) -> int:
    """Derive one stable unsigned 64-bit seed from the canonical manifest."""

    validate_pre_run_manifest(manifest)
    if not isinstance(namespace, str) or not _NAMESPACE_RE.fullmatch(namespace):
        raise PipelineContractError("seed namespace is invalid")
    manifest_dict = manifest.to_dict() if isinstance(manifest, PreRunManifest) else dict(manifest)
    manifest_sha256 = str(manifest_dict["manifest_sha256"])
    digest = hashlib.sha256(
        f"{manifest_sha256}\0{namespace}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=False)


def origin_cycle_seed(
    manifest: PreRunManifest | Mapping[str, Any],
    *,
    origin_index: int,
    cycle_index: int,
    stage: str = "inner_search",
) -> int:
    policy = SearchBudgetPolicy.canonical()
    _validate_index(origin_index, 1, policy.outer_origins, "origin_index")
    _validate_index(cycle_index, 1, policy.max_cycles_per_origin, "cycle_index")
    if not isinstance(stage, str) or not _NAMESPACE_RE.fullmatch(stage):
        raise PipelineContractError("seed stage is invalid")
    return derive_seed(
        manifest,
        f"origin/{origin_index:02d}/cycle/{cycle_index:02d}/{stage}",
    )


def _boundary_plan_payload(plan: MonthlyProcessBoundaryPlan) -> dict[str, Any]:
    return {
        "timezone": plan.timezone,
        "process_start_inclusive": plan.process_start_inclusive.isoformat(),
        "process_end_exclusive": plan.process_end_exclusive.isoformat(),
        "boundary_dates": [day.isoformat() for day in plan.boundary_dates],
        "origins": [
            {
                "origin_index": origin.origin_index,
                "target_anchor": origin.target_anchor.isoformat(),
                "target_anchor_is_synthetic": origin.target_anchor_is_synthetic,
                "training_start_inclusive": origin.training_start_inclusive.isoformat(),
                "training_end_exclusive": origin.training_end_exclusive.isoformat(),
                "test_start_inclusive": origin.test_start_inclusive.isoformat(),
                "test_end_exclusive": origin.test_end_exclusive.isoformat(),
                "as_of_day": origin.as_of_day.isoformat(),
                "valid_from": _utc_text(origin.valid_from),
                "valid_until": _utc_text(origin.valid_until),
                "manual_decision_deadline": _utc_text(origin.manual_decision_deadline),
                "entry_enabled_at": _utc_text(origin.entry_enabled_at),
            }
            for origin in plan.origins
        ],
    }


def _generation_from_dict(value: Mapping[str, Any]) -> PipelineGeneration:
    required = {
        "generation_id",
        "contract_sha256",
        "generation_basis",
        "forward_ledger_namespace",
        "permanent_trial_counter_namespace",
    }
    if set(value) != required or not isinstance(value.get("generation_basis"), dict):
        raise PipelineContractError("pipeline generation payload is invalid")
    return PipelineGeneration(
        generation_id=str(value["generation_id"]),
        contract_sha256=str(value["contract_sha256"]),
        canonical_basis_json=_canonical_json(value["generation_basis"]),
        forward_ledger_namespace=str(value["forward_ledger_namespace"]),
        permanent_trial_counter_namespace=str(
            value["permanent_trial_counter_namespace"]
        ),
    )


def _resolve_repo_root(repo_root: str | Path | None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    try:
        return root.resolve(strict=True)
    except OSError as exc:
        raise PipelineContractError(f"repository root is missing or unreadable: {root}") from exc


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineContractError(f"{label} is missing or invalid: {path}") from exc
    if not isinstance(value, dict):
        raise PipelineContractError(f"{label} root must be an object")
    return value


def _validate_relative_repo_path(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip():
        raise PipelineContractError("source binding path must be a non-empty string")
    if "\\" in value:
        raise PipelineContractError("source binding paths must use canonical forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise PipelineContractError("source binding path must remain inside the repository")
    return path


def _canonical_json(value: Any) -> str:
    normalized = _normalize_json(value)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PipelineContractError("non-finite numbers are forbidden in canonical manifests")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PipelineContractError("canonical manifest object keys must be strings")
            normalized[key] = _normalize_json(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, datetime):
        raise PipelineContractError("wall-clock datetimes are forbidden in canonical manifests")
    raise PipelineContractError(f"unsupported canonical manifest value: {type(value).__name__}")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _reject_forbidden_time_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_MANIFEST_TIME_KEYS:
                raise PipelineContractError(
                    f"wall-clock field is forbidden in canonical pre-run manifest: {key}"
                )
            _reject_forbidden_time_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden_time_keys(item)


def _validate_index(value: Any, minimum: int, maximum: int, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise PipelineContractError(
            f"{field_name} must be an integer from {minimum} through {maximum}"
        )


def _utc_text(value: datetime) -> str:
    if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise PipelineContractError("boundary datetime is not UTC")
    return value.isoformat().replace("+00:00", "Z")


__all__ = [
    "PIPELINE_CONTRACT_PATH",
    "PIPELINE_CONTRACT_VERSION",
    "PIPELINE_GENERATION_PREFIX",
    "PIPELINE_SCHEMA_VERSION",
    "PRE_RUN_MANIFEST_SCHEMA_VERSION",
    "BudgetUsage",
    "PipelineContractError",
    "PipelineGeneration",
    "PreRunManifest",
    "SearchBudgetPolicy",
    "build_pipeline_generation",
    "build_pre_run_manifest",
    "derive_seed",
    "origin_cycle_seed",
    "stagnation_stop_reason",
    "validate_actual_cycle_counts",
    "validate_budget_usage",
    "validate_pipeline_contract",
    "validate_pipeline_generation",
    "validate_pre_run_manifest",
]
