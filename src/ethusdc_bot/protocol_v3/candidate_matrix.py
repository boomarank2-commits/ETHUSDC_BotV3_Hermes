"""Protocol-v3 Task 16 candidate daily matrix and promotion evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Final

from .inner_folds import (
    InnerFoldPlan,
    validate_inner_fold_identity_payload,
    validate_inner_fold_plan,
)
from .pipeline import PipelineContractError, validate_actual_cycle_counts
from .trial_ledger import TrialLedgerSnapshot, read_trial_ledger

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_candidate_matrix_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_candidate_matrix_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_complete_candidate_daily_matrix_and_promotion_v1"
MATRIX_SCHEMA_VERSION: Final = "protocol_v3_candidate_daily_matrix_v1"
MATRIX_IDENTITY_SCHEMA_VERSION: Final = "protocol_v3_candidate_daily_matrix_identity_v1"
PROFILE_ID_PREFIX: Final = "protocol_v3_profile_sha256:"
REQUIRED_DAYS: Final = 360
ZERO_HASH: Final = "0" * 64

_SAFETY = {
    "api_keys": "forbidden", "live": "locked", "orders": "locked",
    "paper": "locked", "testtrade": "locked", "trading_api": "forbidden",
}
_CANONICAL_CONTRACT = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "matrix_schema_version": MATRIX_SCHEMA_VERSION,
    "matrix_identity_schema_version": MATRIX_IDENTITY_SCHEMA_VERSION,
    "required_folds": 6, "days_per_fold": 60, "required_days": 360,
    "cycle_budgets": {"tested_max": 12, "promoted_max": 3, "finalists_max": 2},
    "evidence_policy": {
        "all_declared_tested_profiles_required": True, "all_cycles_retained": True,
        "daily_values_are_net_mtm_deltas": True, "no_trade_day_is_zero": True,
        "missing_day_is_insufficient_evidence": True,
        "permanent_trial_ledger_required": True,
        "cache_reuse_is_not_independent_trial": True, "outer_results_forbidden": True,
    },
    "deferred_scope": {"pbo_task": 17, "dsr_task": 18, "feature_store_task": 19, "regime_task": 20},
    "safety": _SAFETY,
}


class CandidateMatrixError(ValueError):
    """Raised when Task-16 evidence is incomplete or contradictory."""


@dataclass(frozen=True)
class CandidateDailyMatrix:
    canonical_json: str
    matrix_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["matrix_sha256"] = self.matrix_sha256
        return payload

    @property
    def matrix_id(self) -> str:
        return f"protocol_v3_candidate_matrix_sha256:{self.matrix_sha256}"

    @property
    def identity_payload(self) -> dict[str, Any]:
        return build_candidate_matrix_identity_payload(self)


def load_candidate_matrix_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        payload = _strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateMatrixError("candidate matrix contract is missing or invalid") from exc
    if payload != _CANONICAL_CONTRACT:
        raise CandidateMatrixError("Protocol v3 candidate matrix contract is not canonical")
    return payload


def build_candidate_daily_matrix(
    *,
    fold_plan: InnerFoldPlan | Mapping[str, Any],
    origin_index: int,
    cycles: Sequence[Mapping[str, Any]],
    trial_ledger: TrialLedgerSnapshot,
) -> CandidateDailyMatrix:
    plan = validate_inner_fold_plan(fold_plan)
    origin = _positive_int(origin_index, "origin_index")
    ledger = _current_ledger(trial_ledger)
    if not isinstance(cycles, Sequence) or isinstance(cycles, (str, bytes)) or not cycles:
        raise CandidateMatrixError("cycles must be a non-empty sequence")
    normalized_cycles = [_normalize_cycle(row, origin, plan, ledger) for row in cycles]
    indexes = [row["cycle_index"] for row in normalized_cycles]
    if indexes != sorted(indexes) or len(indexes) != len(set(indexes)):
        raise CandidateMatrixError("cycles must be strictly ordered and unique")
    profiles = [profile for cycle in normalized_cycles for profile in cycle["profiles"]]
    profile_ids = [row["profile_id"] for row in profiles]
    if len(profile_ids) != len(set(profile_ids)):
        raise CandidateMatrixError("cycle/origin profile-id collision")
    day_grid = _expected_days(plan)
    basis = {
        "schema_version": MATRIX_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "origin_index": origin,
        "fold_identity": plan.identity_payload,
        "day_grid": day_grid,
        "day_grid_sha256": _digest(day_grid),
        "cycles": normalized_cycles,
        "profile_count": len(profiles),
        "trial_ledger_head_sha256": ledger.status.head_sha256,
        "content_sha256": _digest(profiles),
        "safety": _SAFETY,
    }
    return validate_candidate_daily_matrix({**basis, "matrix_sha256": _digest(basis)})


def validate_candidate_daily_matrix(value: CandidateDailyMatrix | Mapping[str, Any]) -> CandidateDailyMatrix:
    root = value.to_dict() if isinstance(value, CandidateDailyMatrix) else dict(_mapping(value, "matrix"))
    expected = {"schema_version", "protocol_version", "contract_version", "origin_index", "fold_identity", "day_grid", "day_grid_sha256", "cycles", "profile_count", "trial_ledger_head_sha256", "content_sha256", "safety", "matrix_sha256"}
    if set(root) != expected:
        raise CandidateMatrixError("candidate matrix fields are missing or unexpected")
    if root["schema_version"] != MATRIX_SCHEMA_VERSION or root["protocol_version"] != PROTOCOL_VERSION or root["contract_version"] != CONTRACT_VERSION:
        raise CandidateMatrixError("candidate matrix versions are invalid")
    origin = _positive_int(root["origin_index"], "origin_index")
    fold_identity = validate_inner_fold_identity_payload(root["fold_identity"])
    plan = validate_inner_fold_plan(
        {**fold_identity["plan"], "plan_sha256": fold_identity["plan_sha256"]}
    )
    if root["fold_identity"] != plan.identity_payload:
        raise CandidateMatrixError("candidate matrix fold identity is not canonical")
    day_grid = _expected_days(plan)
    if root["day_grid"] != day_grid or root["day_grid_sha256"] != _digest(day_grid):
        raise CandidateMatrixError("candidate matrix day grid is invalid")
    cycles = root["cycles"]
    if not isinstance(cycles, list) or not cycles:
        raise CandidateMatrixError("candidate matrix cycles are missing")
    profiles: list[dict[str, Any]] = []
    previous_cycle = 0
    for cycle in cycles:
        row = dict(_mapping(cycle, "cycle"))
        if set(row) != {"cycle_index", "tested_candidate_ids", "promoted_candidate_ids", "finalist_candidate_ids", "profiles", "cycle_sha256"}:
            raise CandidateMatrixError("candidate matrix cycle fields are invalid")
        index = _positive_int(row["cycle_index"], "cycle_index")
        if index <= previous_cycle:
            raise CandidateMatrixError("candidate matrix cycles are not strictly ordered")
        previous_cycle = index
        tested = _ids(row["tested_candidate_ids"], "tested_candidate_ids")
        promoted = _ids(row["promoted_candidate_ids"], "promoted_candidate_ids")
        finalists = _ids(row["finalist_candidate_ids"], "finalist_candidate_ids")
        _validate_counts(tested, promoted, finalists)
        if not set(finalists) <= set(promoted) <= set(tested):
            raise CandidateMatrixError("promotion inventories are not nested")
        raw_profiles = row["profiles"]
        if not isinstance(raw_profiles, list):
            raise CandidateMatrixError("cycle profiles must be a list")
        normalized_profiles = [_validate_profile(item, origin, index, plan) for item in raw_profiles]
        if [item["candidate_id"] for item in normalized_profiles] != tested:
            raise CandidateMatrixError("declared tested inventory lacks complete profile evidence")
        cycle_basis = {key: row[key] for key in row if key != "cycle_sha256"}
        if row["cycle_sha256"] != _digest(cycle_basis):
            raise CandidateMatrixError("cycle digest mismatch")
        profiles.extend(normalized_profiles)
    if len({row["profile_id"] for row in profiles}) != len(profiles):
        raise CandidateMatrixError("cycle/origin profile-id collision")
    if root["profile_count"] != len(profiles) or root["content_sha256"] != _digest(profiles):
        raise CandidateMatrixError("candidate matrix profile inventory or content digest mismatch")
    _sha(root["trial_ledger_head_sha256"], "trial_ledger_head_sha256")
    if root["safety"] != _SAFETY:
        raise CandidateMatrixError("candidate matrix safety locks are invalid")
    observed = _sha(root["matrix_sha256"], "matrix_sha256")
    basis = dict(root); basis.pop("matrix_sha256")
    if observed != _digest(basis):
        raise CandidateMatrixError("candidate matrix digest mismatch")
    return CandidateDailyMatrix(_canonical(basis), observed)


def build_candidate_matrix_identity_payload(matrix: CandidateDailyMatrix | Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_candidate_daily_matrix(matrix)
    basis = {"identity_schema_version": MATRIX_IDENTITY_SCHEMA_VERSION, "matrix": validated.to_dict(), "matrix_sha256": validated.matrix_sha256, "matrix_id": validated.matrix_id}
    return {**basis, "identity_sha256": _digest(basis)}


def validate_candidate_matrix_identity_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(_mapping(value, "matrix_identity"))
    if set(root) != {"identity_schema_version", "matrix", "matrix_sha256", "matrix_id", "identity_sha256"} or root["identity_schema_version"] != MATRIX_IDENTITY_SCHEMA_VERSION:
        raise CandidateMatrixError("candidate matrix identity fields or version are invalid")
    matrix = validate_candidate_daily_matrix(root["matrix"])
    expected = build_candidate_matrix_identity_payload(matrix)
    if root != expected:
        raise CandidateMatrixError("candidate matrix identity is not canonical")
    return expected


def _normalize_cycle(raw: Mapping[str, Any], origin: int, plan: InnerFoldPlan, ledger: TrialLedgerSnapshot) -> dict[str, Any]:
    row = dict(_mapping(raw, "cycle"))
    if set(row) != {"cycle_index", "tested_candidate_ids", "promoted_candidate_ids", "finalist_candidate_ids", "profiles"}:
        raise CandidateMatrixError("cycle input fields are invalid")
    index = _positive_int(row["cycle_index"], "cycle_index")
    tested = _ids(row["tested_candidate_ids"], "tested_candidate_ids")
    promoted = _ids(row["promoted_candidate_ids"], "promoted_candidate_ids")
    finalists = _ids(row["finalist_candidate_ids"], "finalist_candidate_ids")
    _validate_counts(tested, promoted, finalists)
    if not set(finalists) <= set(promoted) <= set(tested):
        raise CandidateMatrixError("promotion inventories are not nested")
    raw_profiles = row["profiles"]
    if not isinstance(raw_profiles, Sequence) or isinstance(raw_profiles, (str, bytes)):
        raise CandidateMatrixError("profiles must be a sequence")
    profiles = [_normalize_profile(item, origin, index, plan, ledger) for item in raw_profiles]
    profiles.sort(key=lambda item: item["candidate_id"])
    if [item["candidate_id"] for item in profiles] != tested:
        raise CandidateMatrixError("every declared tested candidate requires exactly one complete profile")
    basis = {"cycle_index": index, "tested_candidate_ids": tested, "promoted_candidate_ids": promoted, "finalist_candidate_ids": finalists, "profiles": profiles}
    return {**basis, "cycle_sha256": _digest(basis)}


def _normalize_profile(raw: Mapping[str, Any], origin: int, cycle: int, plan: InnerFoldPlan, ledger: TrialLedgerSnapshot) -> dict[str, Any]:
    row = dict(_mapping(raw, "profile"))
    if set(row) != {"candidate_id", "trial_id", "cache_reuse", "folds"}:
        raise CandidateMatrixError("profile input fields are invalid")
    candidate = _text(row["candidate_id"], "candidate_id")
    trial_id = _text(row["trial_id"], "trial_id")
    if not isinstance(row["cache_reuse"], bool):
        raise CandidateMatrixError("cache_reuse must be boolean")
    folds = _normalize_folds(row["folds"], plan)
    daily = [day for fold in folds for day in fold["daily_net_mtm_usdc"]]
    trial = ledger.trials.get(trial_id)
    if trial is None or trial["identity_basis"]["candidate"]["candidate_id"] != candidate:
        raise CandidateMatrixError("profile is absent from the permanent trial ledger")
    if trial["daily_net_mtm_usdc"] != daily:
        raise CandidateMatrixError("matrix daily series differs from immutable trial-ledger evidence")
    if row["cache_reuse"]:
        matches = [event for event in ledger.events if event.get("event_type") == "cache_reuse" and event.get("payload", {}).get("trial_id") == trial_id]
        if not any(event["payload"].get("reuse_scope", {}).get("origin_index") == origin and event["payload"].get("reuse_scope", {}).get("cycle_index") == cycle for event in matches):
            raise CandidateMatrixError("cache reuse is not visible for this origin/cycle")
    else:
        scope = trial["identity_basis"]["evaluation_scope"]
        if scope.get("origin_index") != origin or scope.get("cycle_index") != cycle:
            raise CandidateMatrixError("independent trial scope differs from origin/cycle")
    identity = {"origin_index": origin, "cycle_index": cycle, "candidate_id": candidate, "trial_id": trial_id}
    profile_id = PROFILE_ID_PREFIX + _digest(identity)
    basis = {"profile_id": profile_id, **identity, "cache_reuse": row["cache_reuse"], "folds": folds, "daily_net_mtm_usdc": daily, "daily_series_sha256": _digest(daily), "net_mtm_total_usdc": sum(item["net_usdc"] for item in daily)}
    return {**basis, "profile_sha256": _digest(basis)}


def _validate_profile(raw: Any, origin: int, cycle: int, plan: InnerFoldPlan) -> dict[str, Any]:
    row = dict(_mapping(raw, "profile"))
    expected = {"profile_id", "origin_index", "cycle_index", "candidate_id", "trial_id", "cache_reuse", "folds", "daily_net_mtm_usdc", "daily_series_sha256", "net_mtm_total_usdc", "profile_sha256"}
    if set(row) != expected or row["origin_index"] != origin or row["cycle_index"] != cycle:
        raise CandidateMatrixError("profile fields or origin/cycle binding are invalid")
    if not isinstance(row["cache_reuse"], bool):
        raise CandidateMatrixError("cache_reuse must be boolean")
    candidate = _text(row["candidate_id"], "candidate_id"); trial_id = _text(row["trial_id"], "trial_id")
    identity = {"origin_index": origin, "cycle_index": cycle, "candidate_id": candidate, "trial_id": trial_id}
    if row["profile_id"] != PROFILE_ID_PREFIX + _digest(identity):
        raise CandidateMatrixError("profile id is not canonical")
    folds = _normalize_folds(row["folds"], plan)
    daily = [day for fold in folds for day in fold["daily_net_mtm_usdc"]]
    if row["daily_net_mtm_usdc"] != daily or row["daily_series_sha256"] != _digest(daily):
        raise CandidateMatrixError("profile daily series or digest is invalid")
    total = _number(row["net_mtm_total_usdc"], "net_mtm_total_usdc")
    if not math.isclose(total, sum(item["net_usdc"] for item in daily), rel_tol=0.0, abs_tol=1e-12):
        raise CandidateMatrixError("profile daily sum differs from net MTM evidence")
    basis = dict(row); observed = _sha(basis.pop("profile_sha256"), "profile_sha256")
    if observed != _digest(basis):
        raise CandidateMatrixError("profile digest mismatch")
    return row


def _normalize_folds(raw: Any, plan: InnerFoldPlan) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 6:
        raise CandidateMatrixError("every profile requires exactly six fold series")
    result = []
    for supplied, boundary in zip(raw, plan.folds, strict=True):
        row = dict(_mapping(supplied, "fold"))
        input_keys = {"fold_index", "fold_id", "daily_net_mtm_usdc"}
        if frozenset(row) not in {frozenset(input_keys), frozenset({*input_keys, "fold_sha256"})} or row["fold_index"] != boundary.fold_index or row["fold_id"] != boundary.fold_id:
            raise CandidateMatrixError("fold provenance differs from Task-14 plan")
        days = _daily(row["daily_net_mtm_usdc"])
        expected = [(boundary.validation_start_inclusive_utc.date() + timedelta(days=i)).isoformat() for i in range(60)]
        if [item["day"] for item in days] != expected:
            raise CandidateMatrixError("fold daily series must contain the exact ordered 60-day grid")
        basis = {"fold_index": boundary.fold_index, "fold_id": boundary.fold_id, "daily_net_mtm_usdc": days}
        digest = _digest(basis)
        if "fold_sha256" in row and row["fold_sha256"] != digest:
            raise CandidateMatrixError("fold content digest mismatch")
        result.append({**basis, "fold_sha256": digest})
    return result


def _daily(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise CandidateMatrixError("daily series must be a sequence")
    result = []
    for item in raw:
        row = dict(_mapping(item, "daily row"))
        if set(row) != {"day", "net_usdc"}:
            raise CandidateMatrixError("daily rows require day and net_usdc")
        result.append({"day": _text(row["day"], "day"), "net_usdc": _number(row["net_usdc"], "net_usdc")})
    return result


def _expected_days(plan: InnerFoldPlan) -> list[str]:
    days = [(fold.validation_start_inclusive_utc.date() + timedelta(days=i)).isoformat() for fold in plan.folds for i in range(60)]
    if len(days) != REQUIRED_DAYS or len(set(days)) != REQUIRED_DAYS:
        raise CandidateMatrixError("Task-14 fold plan does not expose one 360-day validation union")
    return days


def _current_ledger(value: TrialLedgerSnapshot) -> TrialLedgerSnapshot:
    if not isinstance(value, TrialLedgerSnapshot):
        raise CandidateMatrixError("trial_ledger must be a verified snapshot")
    current = read_trial_ledger(value.root)
    if current.status.head_sha256 != value.status.head_sha256:
        raise CandidateMatrixError("trial ledger advanced after matrix input was frozen")
    return current


def _ids(raw: Any, path: str) -> list[str]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise CandidateMatrixError(f"{path} must be a sequence")
    result = sorted(_text(item, path) for item in raw)
    if len(result) != len(set(result)):
        raise CandidateMatrixError(f"{path} contains duplicates")
    return result


def _validate_counts(tested: Sequence[str], promoted: Sequence[str], finalists: Sequence[str]) -> None:
    try:
        validate_actual_cycle_counts(
            generated=len(tested),
            tested=len(tested),
            walk_forward=len(promoted),
            finalists=len(finalists),
        )
    except PipelineContractError as exc:
        raise CandidateMatrixError(str(exc)) from exc


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CandidateMatrixError(f"{path} must be a positive integer")
    return value


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise CandidateMatrixError(f"{path} must be finite")
    return float(value)


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateMatrixError(f"{path} must be non-empty text")
    return value.strip()


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateMatrixError(f"{path} must be an object")
    return value


def _sha(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise CandidateMatrixError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _strict_loads(text: str) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CandidateMatrixError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=hook, parse_constant=lambda value: (_ for _ in ()).throw(CandidateMatrixError(f"non-finite JSON constant: {value}")))


__all__ = ["CONTRACT_PATH", "CONTRACT_SCHEMA_VERSION", "CONTRACT_VERSION", "MATRIX_IDENTITY_SCHEMA_VERSION", "MATRIX_SCHEMA_VERSION", "CandidateDailyMatrix", "CandidateMatrixError", "build_candidate_daily_matrix", "build_candidate_matrix_identity_payload", "load_candidate_matrix_contract", "validate_candidate_daily_matrix", "validate_candidate_matrix_identity_payload"]
