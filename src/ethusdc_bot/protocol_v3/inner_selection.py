"""Pure Protocol-v3 inner candidate selection for Task 15.

The selector consumes only immutable, explicit Protocol-v3 objects. It does not
load candles, read files, consult the UI, inspect outer results, use wall-clock
state, environment variables, or the network. Tasks 16-18 remain evidence
producers; until their production evidence exists the valid result is NO_TRADE.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Final, Mapping, Sequence

from ethusdc_bot.backtest.quality_gates import evaluate_quality_gates
from ethusdc_bot.backtest.search_space import canonical_candidate_signature
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3.inner_folds_api import (
    InnerFoldPlan,
    validate_inner_fold_identity_payload,
    validate_inner_fold_plan,
)
from ethusdc_bot.protocol_v3.pipeline import (
    PreRunManifest,
    origin_cycle_seed,
    validate_actual_cycle_counts,
    validate_pre_run_manifest,
)
from ethusdc_bot.protocol_v3.run_identity import RunFingerprint, validate_run_fingerprint

INNER_SELECTION_CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_inner_selection_contract.json"
)
INNER_SELECTION_CONTRACT_SCHEMA: Final = "protocol_v3_inner_selection_contract_v1"
INNER_SELECTION_CONTRACT_VERSION: Final = "protocol_v3_pure_inner_candidate_selection_v1"
TRAINING_WINDOW_SCHEMA: Final = "protocol_v3_selection_training_window_v1"
CANDIDATE_EVIDENCE_SCHEMA: Final = "protocol_v3_candidate_selection_evidence_v1"
DEVELOPMENT_EVIDENCE_SCHEMA: Final = "protocol_v3_development_support_v1"
FROZEN_CONFIG_SCHEMA: Final = "protocol_v3_frozen_selection_config_v1"
SELECTION_DECISION_SCHEMA: Final = "protocol_v3_inner_selection_decision_v1"
CANDIDATE_SELECTION_IDENTITY_SCHEMA: Final = "protocol_v3_candidate_selection_identity_v1"
PROTOCOL_VERSION: Final = "3.0.0"
NO_TRADE: Final = "NO_TRADE"
CANDIDATE: Final = "CANDIDATE"
PRODUCTION: Final = "PRODUCTION"
SYNTHETIC_TEST_FIXTURE: Final = "SYNTHETIC_TEST_FIXTURE"
COMPLETE: Final = "COMPLETE"
INSUFFICIENT_EVIDENCE: Final = "INSUFFICIENT_EVIDENCE"
ZERO_HASH: Final = "0" * 64
_MAX_PBO: Final = 0.10
_MIN_DSR: Final = 0.95
_REQUIRED_MATRIX_DAYS: Final = 360
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_CANDIDATE_ID = re.compile(r"^protocol_v3_candidate_sha256:[0-9a-f]{64}$")
_DECISION_ID = re.compile(r"^protocol_v3_selection_sha256:[0-9a-f]{64}$")
_FORBIDDEN_KEYS = {
    "target_usdc_per_day",
    "distance_to_target",
    "target_distance",
    "outer_results",
    "outer_pnl",
    "outer_rankings",
    "blindtest_metrics",
    "holdout_metrics",
    "ui_state",
    "environment",
    "wall_clock_time",
}
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_RANKING_ORDER: Final = [
    "worst_fold_net_usdc_per_day_desc",
    "median_fold_net_usdc_per_day_desc",
    "aggregate_wfv_net_usdc_per_day_desc",
    "joint_stress_net_usdc_per_day_desc",
    "max_drawdown_usdc_asc",
    "friction_share_asc",
    "free_parameter_count_asc",
    "canonical_candidate_id_asc",
]
_CANONICAL_CONTRACT: Final = {
    "schema_version": INNER_SELECTION_CONTRACT_SCHEMA,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": INNER_SELECTION_CONTRACT_VERSION,
    "training_window_schema_version": TRAINING_WINDOW_SCHEMA,
    "candidate_evidence_schema_version": CANDIDATE_EVIDENCE_SCHEMA,
    "development_evidence_schema_version": DEVELOPMENT_EVIDENCE_SCHEMA,
    "frozen_config_schema_version": FROZEN_CONFIG_SCHEMA,
    "decision_schema_version": SELECTION_DECISION_SCHEMA,
    "candidate_identity_schema_version": CANDIDATE_SELECTION_IDENTITY_SCHEMA,
    "ranking_policy": {
        "gate": "development_quality_gate_v1_must_pass",
        "order": _RANKING_ORDER,
        "target_usdc_per_day_used": False,
    },
    "budget_policy": {
        "generated_per_cycle": 40,
        "tested_per_cycle": 12,
        "walk_forward_per_cycle": 3,
        "finalists_per_cycle": 2,
    },
    "development_support_policy": {
        "matrix_task": 16,
        "pbo_task": 17,
        "dsr_task": 18,
        "required_matrix_days": _REQUIRED_MATRIX_DAYS,
        "max_development_pbo": _MAX_PBO,
        "min_development_dsr": _MIN_DSR,
        "production_missing_support_result": NO_TRADE,
        "production_matrix_complete_allowed_from_task16": True,
        "production_pbo_complete_allowed_from_task17": True,
        "production_dsr_complete_allowed_from_task18": True,
        "synthetic_pbo_dsr_support_is_fixture_only": True,
    },
    "purity_policy": {
        "explicit_inputs_only": True,
        "ui_state_forbidden": True,
        "outer_results_forbidden": True,
        "current_time_forbidden": True,
        "environment_variables_forbidden": True,
        "network_forbidden": True,
        "implicit_working_directory_files_forbidden": True,
        "reads_at_or_after_training_end_forbidden": True,
        "task14_plan_required": True,
        "same_input_same_decision": True,
    },
    "deferred_scope": {
        "candidate_daily_matrix_task": 16,
        "pbo_task": 17,
        "dsr_task": 18,
        "feature_store_task": 19,
        "router_task": 22,
        "outer_orchestration_task": 23,
    },
    "safety": _SAFETY,
}


class InnerSelectionError(ValueError):
    """Raised for malformed or contradictory selection inputs."""


@dataclass(frozen=True)
class SelectionTrainingWindow:
    canonical_json: str
    window_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["window_sha256"] = self.window_sha256
        return payload

    @property
    def start_utc(self) -> datetime:
        return _parse_utc(self.to_dict()["training_start_inclusive_utc"], "training_start")

    @property
    def end_utc(self) -> datetime:
        return _parse_utc(self.to_dict()["training_end_exclusive_utc"], "training_end")


@dataclass(frozen=True)
class CandidateSelectionEvidence:
    canonical_json: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["evidence_sha256"] = self.evidence_sha256
        return payload

    @property
    def canonical_candidate_id(self) -> str:
        return str(self.to_dict()["candidate"]["canonical_candidate_id"])


@dataclass(frozen=True)
class DevelopmentSupport:
    canonical_json: str
    support_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["support_sha256"] = self.support_sha256
        return payload


@dataclass(frozen=True)
class FrozenSelectionConfig:
    canonical_json: str
    config_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["config_sha256"] = self.config_sha256
        return payload


@dataclass(frozen=True)
class SelectionDecision:
    canonical_json: str
    decision_sha256: str
    decision_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["decision_sha256"] = self.decision_sha256
        payload["decision_id"] = self.decision_id
        return payload

    @property
    def outcome(self) -> str:
        return str(json.loads(self.canonical_json)["outcome"])

    @property
    def fixture_only(self) -> bool:
        return bool(json.loads(self.canonical_json)["fixture_only"])

    @property
    def candidate_identity_payload(self) -> dict[str, Any]:
        return build_candidate_selection_identity_payload(self)


class SelectionTimestampSpy:
    """Fail-closed consumer guard for training, warmup and outer timestamps."""

    def __init__(self, training_window: SelectionTrainingWindow) -> None:
        self.window = validate_selection_training_window(training_window)
        self._observations: list[dict[str, Any]] = []

    def observe_training_read(self, timestamp_ms: int) -> None:
        value = _nonnegative_int(timestamp_ms, "timestamp_ms")
        if not _timestamp_ms(self.window.start_utc) <= value < _timestamp_ms(self.window.end_utc):
            raise InnerSelectionError("training read lies outside [training_start, training_end)")
        self._observations.append({"purpose": "training_read", "timestamp_ms": value})

    def observe_warmup_feature_read(self, timestamp_ms: int) -> None:
        value = _nonnegative_int(timestamp_ms, "timestamp_ms")
        if value >= _timestamp_ms(self.window.start_utc):
            raise InnerSelectionError("warmup feature read must be before training_start")
        self._observations.append({"purpose": "warmup_feature_read", "timestamp_ms": value})

    def observe_outer_result(self, timestamp_ms: int) -> None:
        _nonnegative_int(timestamp_ms, "timestamp_ms")
        raise InnerSelectionError("outer result access is forbidden in inner selection")

    @property
    def observations(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in self._observations)


def load_inner_selection_contract(
    repo_root: str | Path,
    *,
    contract_path: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve(strict=True)
    path = Path(contract_path) if contract_path is not None else root / INNER_SELECTION_CONTRACT_PATH
    if not path.is_absolute():
        path = root / path
    try:
        value = _strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InnerSelectionError(f"inner selection contract is missing or invalid: {path}") from exc
    validate_inner_selection_contract(value)
    return value


def validate_inner_selection_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize(value) != _CANONICAL_CONTRACT:
        raise InnerSelectionError("Protocol v3 inner selection contract is not canonical")


def build_selection_training_window(plan: InnerFoldPlan | Mapping[str, Any]) -> SelectionTrainingWindow:
    validated_plan = validate_inner_fold_plan(plan)
    basis = {
        "schema_version": TRAINING_WINDOW_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "training_start_inclusive_utc": _utc_text(validated_plan.training_start_inclusive_utc),
        "training_end_exclusive_utc": _utc_text(validated_plan.training_end_exclusive_utc),
        "development_days": 730,
        "fold_identity": validated_plan.identity_payload,
        "safety": _SAFETY,
    }
    return validate_selection_training_window({**basis, "window_sha256": _digest(basis)})


def validate_selection_training_window(
    value: SelectionTrainingWindow | Mapping[str, Any],
) -> SelectionTrainingWindow:
    root = value.to_dict() if isinstance(value, SelectionTrainingWindow) else dict(_mapping(value, "training_window"))
    expected = {
        "schema_version", "protocol_version", "training_start_inclusive_utc",
        "training_end_exclusive_utc", "development_days", "fold_identity",
        "safety", "window_sha256",
    }
    _exact_keys(root, expected, "training_window")
    _literal(root, "schema_version", TRAINING_WINDOW_SCHEMA)
    _literal(root, "protocol_version", PROTOCOL_VERSION)
    start = _parse_utc(root["training_start_inclusive_utc"], "training_start")
    end = _parse_utc(root["training_end_exclusive_utc"], "training_end")
    if start.time() != datetime.min.time() or end.time() != datetime.min.time():
        raise InnerSelectionError("selection training boundaries must be UTC midnight")
    if end - start != timedelta(days=730) or root["development_days"] != 730:
        raise InnerSelectionError("selection training window must contain exactly 730 days")
    fold_identity = validate_inner_fold_identity_payload(root["fold_identity"])
    plan = fold_identity["plan"]
    if (
        plan["training_start_inclusive_utc"] != root["training_start_inclusive_utc"]
        or plan["training_end_exclusive_utc"] != root["training_end_exclusive_utc"]
    ):
        raise InnerSelectionError("Task-14 fold plan differs from selection training window")
    if root["safety"] != _SAFETY:
        raise InnerSelectionError("selection training-window safety locks are invalid")
    observed = _sha256(root["window_sha256"], "training_window.window_sha256")
    basis = dict(root)
    basis.pop("window_sha256")
    if observed != _digest(basis):
        raise InnerSelectionError("selection training-window digest mismatch")
    _reject_forbidden(root, "training_window")
    return SelectionTrainingWindow(_canonical(basis), observed)


def build_candidate_selection_evidence(
    candidate: StrategyCandidate,
    quality_evidence: Mapping[str, Any],
    training_window: SelectionTrainingWindow,
) -> CandidateSelectionEvidence:
    window = validate_selection_training_window(training_window)
    if not isinstance(candidate, StrategyCandidate):
        raise InnerSelectionError("candidate must be StrategyCandidate")
    candidate_payload = _candidate_payload(candidate)
    evidence = _normalize(dict(_mapping(quality_evidence, "quality_evidence")))
    _finite_json(evidence, "quality_evidence")
    _reject_forbidden(evidence, "quality_evidence")
    basis = {
        "schema_version": CANDIDATE_EVIDENCE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "candidate": candidate_payload,
        "training_window_sha256": window.window_sha256,
        "quality_evidence": evidence,
        "quality_evidence_sha256": _digest(evidence),
        "safety": _SAFETY,
    }
    return validate_candidate_selection_evidence({**basis, "evidence_sha256": _digest(basis)})


def validate_candidate_selection_evidence(
    value: CandidateSelectionEvidence | Mapping[str, Any],
) -> CandidateSelectionEvidence:
    root = value.to_dict() if isinstance(value, CandidateSelectionEvidence) else dict(_mapping(value, "candidate_evidence"))
    _exact_keys(
        root,
        {
            "schema_version", "protocol_version", "candidate",
            "training_window_sha256", "quality_evidence",
            "quality_evidence_sha256", "safety", "evidence_sha256",
        },
        "candidate_evidence",
    )
    _literal(root, "schema_version", CANDIDATE_EVIDENCE_SCHEMA)
    _literal(root, "protocol_version", PROTOCOL_VERSION)
    candidate = _validate_candidate_payload(root["candidate"])
    _sha256(root["training_window_sha256"], "candidate_evidence.training_window_sha256")
    evidence = _normalize(dict(_mapping(root["quality_evidence"], "quality_evidence")))
    _finite_json(evidence, "quality_evidence")
    _reject_forbidden(evidence, "quality_evidence")
    if root["quality_evidence_sha256"] != _digest(evidence):
        raise InnerSelectionError("quality-evidence digest mismatch")
    if root["candidate"] != candidate:
        raise InnerSelectionError("candidate evidence identity is not canonical")
    if root["safety"] != _SAFETY:
        raise InnerSelectionError("candidate evidence safety locks are invalid")
    observed = _sha256(root["evidence_sha256"], "candidate_evidence.evidence_sha256")
    basis = dict(root)
    basis.pop("evidence_sha256")
    if observed != _digest(basis):
        raise InnerSelectionError("candidate evidence digest mismatch")
    return CandidateSelectionEvidence(_canonical(basis), observed)


def build_incomplete_development_support(reason: str) -> DevelopmentSupport:
    text = _required_text(reason, "reason")
    basis = {
        "schema_version": DEVELOPMENT_EVIDENCE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "mode": PRODUCTION,
        "matrix": _incomplete_support_row("protocol_v3_candidate_daily_matrix_pending_task16_v1", text),
        "pbo": _incomplete_support_row("protocol_v3_pbo_pending_task17_v1", text),
        "dsr": _incomplete_support_row("protocol_v3_dsr_pending_task18_v1", text),
        "safety": _SAFETY,
    }
    return validate_development_support({**basis, "support_sha256": _digest(basis)})


def build_matrix_development_support(
    matrix: Any,
    *,
    cycle_index: int,
) -> DevelopmentSupport:
    from .candidate_matrix import validate_candidate_daily_matrix

    validated = validate_candidate_daily_matrix(matrix)
    identity = validated.identity_payload
    cycle = _positive_int(cycle_index, "cycle_index")
    rows = [row for row in validated.to_dict()["cycles"] if row["cycle_index"] == cycle]
    if len(rows) != 1:
        raise InnerSelectionError("Task-16 matrix does not contain the requested cycle")
    tested = rows[0]["tested_candidate_ids"]
    basis = {
        "schema_version": DEVELOPMENT_EVIDENCE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "mode": PRODUCTION,
        "matrix": {
            "state": COMPLETE,
            "schema_version": "protocol_v3_candidate_daily_matrix_v1",
            "candidate_ids": tested,
            "day_count": _REQUIRED_MATRIX_DAYS,
            "value": identity,
            "evidence_sha256": validated.matrix_sha256,
            "reason": "task16_complete_candidate_daily_matrix",
        },
        "pbo": _incomplete_support_row("protocol_v3_pbo_pending_task17_v1", "task17_not_implemented"),
        "dsr": _incomplete_support_row("protocol_v3_dsr_pending_task18_v1", "task18_not_implemented"),
        "safety": _SAFETY,
    }
    return validate_development_support({**basis, "support_sha256": _digest(basis)})


def build_pbo_development_support(
    evidence: Any,
    *,
    cycle_index: int,
) -> DevelopmentSupport:
    from .pbo import COMPLETE as PBO_COMPLETE, validate_pbo_evidence

    validated = validate_pbo_evidence(evidence)
    pbo = validated.to_dict()
    matrix_identity = pbo["matrix_identity"]
    matrix = matrix_identity["matrix"]
    cycle = _positive_int(cycle_index, "cycle_index")
    rows = [row for row in matrix["cycles"] if row["cycle_index"] == cycle]
    if len(rows) != 1:
        raise InnerSelectionError("Task-17 PBO matrix does not contain the requested cycle")
    tested = rows[0]["tested_candidate_ids"]
    matrix_row = {
        "state": COMPLETE,
        "schema_version": "protocol_v3_candidate_daily_matrix_v1",
        "candidate_ids": tested,
        "day_count": _REQUIRED_MATRIX_DAYS,
        "value": matrix_identity,
        "evidence_sha256": matrix_identity["matrix_sha256"],
        "reason": "task16_complete_candidate_daily_matrix",
    }
    if pbo["state"] != PBO_COMPLETE:
        pbo_row = _incomplete_support_row(
            "protocol_v3_pbo_evidence_v1",
            "task17_insufficient_evidence",
        )
    else:
        pbo_row = {
            "state": COMPLETE,
            "schema_version": "protocol_v3_pbo_evidence_v1",
            "candidate_ids": tested,
            "day_count": _REQUIRED_MATRIX_DAYS,
            "value": validated.identity_payload,
            "evidence_sha256": validated.evidence_sha256,
            "reason": "task17_complete_exact_cscv",
        }
    basis = {
        "schema_version": DEVELOPMENT_EVIDENCE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "mode": PRODUCTION,
        "matrix": matrix_row,
        "pbo": pbo_row,
        "dsr": _incomplete_support_row("protocol_v3_dsr_pending_task18_v1", "task18_not_implemented"),
        "safety": _SAFETY,
    }
    return validate_development_support({**basis, "support_sha256": _digest(basis)})


def build_dsr_development_support(
    evidence_by_candidate: Mapping[str, Any],
    *,
    cycle_index: int,
    trial_ledger: Any,
) -> DevelopmentSupport:
    """Bind Task-18 DSR evidence for every tested profile in one inner cycle."""

    from .dsr import COMPLETE as DSR_COMPLETE, validate_dsr_for_ledger

    if not isinstance(evidence_by_candidate, Mapping) or not evidence_by_candidate:
        raise InnerSelectionError("Task-18 DSR evidence mapping must not be empty")
    evidence = {
        _candidate_id(candidate_id): validate_dsr_for_ledger(value, trial_ledger)
        for candidate_id, value in evidence_by_candidate.items()
    }
    first = next(iter(evidence.values())).to_dict()
    pbo_identity = first["pbo_identity"]
    matrix_identity = pbo_identity["evidence"]["matrix_identity"]
    matrix = matrix_identity["matrix"]
    cycle = _positive_int(cycle_index, "cycle_index")
    cycles = [row for row in matrix["cycles"] if row["cycle_index"] == cycle]
    if len(cycles) != 1:
        raise InnerSelectionError("Task-18 DSR matrix does not contain the requested cycle")
    tested = cycles[0]["tested_candidate_ids"]
    if set(evidence) != set(tested):
        raise InnerSelectionError("Task-18 DSR evidence must cover every tested candidate exactly")
    profile_by_candidate = {row["candidate_id"]: row["profile_id"] for row in cycles[0]["profiles"]}
    identities: dict[str, Any] = {}
    for candidate_id, validated in sorted(evidence.items()):
        payload = validated.to_dict()
        if payload["pbo_identity"] != pbo_identity:
            raise InnerSelectionError("Task-18 DSR rows bind different PBO evidence")
        if payload["selected_profile_id"] != profile_by_candidate[candidate_id]:
            raise InnerSelectionError("Task-18 DSR profile differs from its cycle candidate")
        identities[candidate_id] = validated.identity_payload
    pbo_payload = pbo_identity["evidence"]
    matrix_row = {
        "state": COMPLETE,
        "schema_version": "protocol_v3_candidate_daily_matrix_v1",
        "candidate_ids": tested,
        "day_count": _REQUIRED_MATRIX_DAYS,
        "value": matrix_identity,
        "evidence_sha256": matrix_identity["matrix_sha256"],
        "reason": "task16_complete_candidate_daily_matrix",
    }
    pbo_row = {
        "state": COMPLETE,
        "schema_version": "protocol_v3_pbo_evidence_v1",
        "candidate_ids": tested,
        "day_count": _REQUIRED_MATRIX_DAYS,
        "value": pbo_identity,
        "evidence_sha256": pbo_identity["evidence_sha256"],
        "reason": "task17_complete_exact_cscv",
    }
    if pbo_payload["state"] != COMPLETE:
        pbo_row = _incomplete_support_row("protocol_v3_pbo_evidence_v1", "task17_insufficient_evidence")
    if all(row.to_dict()["state"] == DSR_COMPLETE for row in evidence.values()):
        dsr_row = {
            "state": COMPLETE,
            "schema_version": "protocol_v3_dsr_evidence_v1",
            "candidate_ids": tested,
            "day_count": _REQUIRED_MATRIX_DAYS,
            "value": identities,
            "evidence_sha256": _digest(identities),
            "reason": "task18_complete_exact_deflated_sharpe",
        }
    else:
        dsr_row = _incomplete_support_row(
            "protocol_v3_dsr_evidence_v1",
            "task18_insufficient_trial_history_or_statistics",
        )
    basis = {
        "schema_version": DEVELOPMENT_EVIDENCE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "mode": PRODUCTION,
        "matrix": matrix_row,
        "pbo": pbo_row,
        "dsr": dsr_row,
        "safety": _SAFETY,
    }
    return validate_development_support({**basis, "support_sha256": _digest(basis)})


def build_synthetic_complete_development_support(
    *,
    tested_candidate_ids: Sequence[str],
    dsr_by_candidate: Mapping[str, float],
    matrix_evidence_sha256: str,
    pbo_evidence_sha256: str,
    dsr_evidence_sha256: str,
    development_pbo: float,
) -> DevelopmentSupport:
    tested = _canonical_id_list(tested_candidate_ids, "tested_candidate_ids")
    dsr_values = {
        _candidate_id(key): _finite_number(value, f"dsr_by_candidate.{key}")
        for key, value in dsr_by_candidate.items()
    }
    if set(dsr_values) != set(tested):
        raise InnerSelectionError("synthetic DSR evidence must cover every tested candidate exactly")
    basis = {
        "schema_version": DEVELOPMENT_EVIDENCE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "mode": SYNTHETIC_TEST_FIXTURE,
        "matrix": {
            "state": COMPLETE,
            "schema_version": "protocol_v3_candidate_daily_matrix_fixture_v1",
            "candidate_ids": tested,
            "day_count": _REQUIRED_MATRIX_DAYS,
            "value": None,
            "evidence_sha256": _sha256(matrix_evidence_sha256, "matrix_evidence_sha256"),
            "reason": "synthetic_complete_fixture",
        },
        "pbo": {
            "state": COMPLETE,
            "schema_version": "protocol_v3_pbo_fixture_v1",
            "candidate_ids": tested,
            "day_count": _REQUIRED_MATRIX_DAYS,
            "value": _finite_number(development_pbo, "development_pbo"),
            "evidence_sha256": _sha256(pbo_evidence_sha256, "pbo_evidence_sha256"),
            "reason": "synthetic_complete_fixture",
        },
        "dsr": {
            "state": COMPLETE,
            "schema_version": "protocol_v3_dsr_fixture_v1",
            "candidate_ids": tested,
            "day_count": _REQUIRED_MATRIX_DAYS,
            "value": dict(sorted(dsr_values.items())),
            "evidence_sha256": _sha256(dsr_evidence_sha256, "dsr_evidence_sha256"),
            "reason": "synthetic_complete_fixture",
        },
        "safety": _SAFETY,
    }
    return validate_development_support({**basis, "support_sha256": _digest(basis)})


def validate_development_support(
    value: DevelopmentSupport | Mapping[str, Any],
) -> DevelopmentSupport:
    root = value.to_dict() if isinstance(value, DevelopmentSupport) else dict(_mapping(value, "development_support"))
    _exact_keys(
        root,
        {"schema_version", "protocol_version", "mode", "matrix", "pbo", "dsr", "safety", "support_sha256"},
        "development_support",
    )
    _literal(root, "schema_version", DEVELOPMENT_EVIDENCE_SCHEMA)
    _literal(root, "protocol_version", PROTOCOL_VERSION)
    mode = root["mode"]
    if mode not in {PRODUCTION, SYNTHETIC_TEST_FIXTURE}:
        raise InnerSelectionError("development support mode is invalid")
    matrix = _validate_support_row(root["matrix"], "matrix", mode)
    pbo = _validate_support_row(root["pbo"], "pbo", mode)
    dsr = _validate_support_row(root["dsr"], "dsr", mode)
    states = {matrix["state"], pbo["state"], dsr["state"]}
    if mode == PRODUCTION:
        if dsr["state"] not in {INSUFFICIENT_EVIDENCE, COMPLETE}:
            raise InnerSelectionError("production DSR support state is invalid")
        if matrix["state"] not in {INSUFFICIENT_EVIDENCE, COMPLETE}:
            raise InnerSelectionError("production matrix support state is invalid")
        if pbo["state"] not in {INSUFFICIENT_EVIDENCE, COMPLETE}:
            raise InnerSelectionError("production PBO support state is invalid")
        if pbo["state"] == COMPLETE and matrix["state"] != COMPLETE:
            raise InnerSelectionError("complete PBO requires complete Task-16 matrix evidence")
        if dsr["state"] == COMPLETE and (pbo["state"] != COMPLETE or matrix["state"] != COMPLETE):
            raise InnerSelectionError("complete DSR requires complete Task-16 and Task-17 evidence")
        if dsr["state"] == COMPLETE:
            ids = matrix["candidate_ids"]
            if pbo["candidate_ids"] != ids or dsr["candidate_ids"] != ids:
                raise InnerSelectionError("production development support inventories differ")
    if mode == SYNTHETIC_TEST_FIXTURE:
        if states != {COMPLETE}:
            raise InnerSelectionError("synthetic complete support must complete matrix, PBO and DSR")
        ids = matrix["candidate_ids"]
        if pbo["candidate_ids"] != ids or dsr["candidate_ids"] != ids:
            raise InnerSelectionError("synthetic development support candidate inventories differ")
        if matrix["day_count"] != _REQUIRED_MATRIX_DAYS or pbo["day_count"] != _REQUIRED_MATRIX_DAYS or dsr["day_count"] != _REQUIRED_MATRIX_DAYS:
            raise InnerSelectionError("synthetic development support must bind exactly 360 days")
        if not 0.0 <= pbo["value"] <= 1.0:
            raise InnerSelectionError("synthetic PBO value must be in [0,1]")
        if not isinstance(dsr["value"], dict) or set(dsr["value"]) != set(ids):
            raise InnerSelectionError("synthetic DSR mapping is incomplete")
        for candidate_id, score in dsr["value"].items():
            _candidate_id(candidate_id)
            if not 0.0 <= _finite_number(score, f"dsr.{candidate_id}") <= 1.0:
                raise InnerSelectionError("synthetic DSR values must be in [0,1]")
    if root["matrix"] != matrix or root["pbo"] != pbo or root["dsr"] != dsr:
        raise InnerSelectionError("development support payload is not canonical")
    if root["safety"] != _SAFETY:
        raise InnerSelectionError("development support safety locks are invalid")
    observed = _sha256(root["support_sha256"], "development_support.support_sha256")
    basis = dict(root)
    basis.pop("support_sha256")
    if observed != _digest(basis):
        raise InnerSelectionError("development support digest mismatch")
    _reject_forbidden(root, "development_support")
    return DevelopmentSupport(_canonical(basis), observed)


def build_frozen_selection_config(
    *,
    pre_run_manifest: PreRunManifest | Mapping[str, Any],
    run_fingerprint: RunFingerprint | Mapping[str, Any],
    fold_identity: Mapping[str, Any],
    origin_index: int,
    cycle_index: int,
    generated_candidate_ids: Sequence[str],
    tested_candidate_ids: Sequence[str],
    walk_forward_candidate_ids: Sequence[str],
    finalist_candidate_ids: Sequence[str],
    candidate_evidence: Sequence[CandidateSelectionEvidence | Mapping[str, Any]],
    development_support: DevelopmentSupport | Mapping[str, Any],
) -> FrozenSelectionConfig:
    manifest = _manifest_dict(pre_run_manifest)
    fingerprint = _fingerprint_dict(run_fingerprint)
    fold = validate_inner_fold_identity_payload(fold_identity)
    origin = _positive_int(origin_index, "origin_index")
    cycle = _positive_int(cycle_index, "cycle_index")
    generated = _canonical_id_list(generated_candidate_ids, "generated_candidate_ids")
    tested = _canonical_id_list(tested_candidate_ids, "tested_candidate_ids")
    promoted = _canonical_id_list(walk_forward_candidate_ids, "walk_forward_candidate_ids")
    finalists = _canonical_id_list(finalist_candidate_ids, "finalist_candidate_ids")
    validate_actual_cycle_counts(
        generated=len(generated), tested=len(tested), walk_forward=len(promoted), finalists=len(finalists)
    )
    if not set(finalists) <= set(promoted) <= set(tested) <= set(generated):
        raise InnerSelectionError("candidate stages are not nested subsets")
    evidence_rows = sorted(
        (validate_candidate_selection_evidence(row).to_dict() for row in candidate_evidence),
        key=lambda row: row["candidate"]["canonical_candidate_id"],
    )
    evidence_ids = [row["candidate"]["canonical_candidate_id"] for row in evidence_rows]
    if evidence_ids != finalists:
        raise InnerSelectionError("candidate evidence must cover the canonical finalist inventory exactly")
    support = validate_development_support(development_support).to_dict()
    if support["mode"] == SYNTHETIC_TEST_FIXTURE and support["matrix"]["candidate_ids"] != tested:
        raise InnerSelectionError("synthetic matrix inventory differs from tested candidates")
    _cross_validate_task16_matrix_support(support, origin, cycle, tested)
    _cross_validate_task17_pbo_support(support, origin, cycle, tested)
    _cross_validate_task18_dsr_support(support, origin, cycle, tested)
    seed = origin_cycle_seed(manifest, origin_index=origin, cycle_index=cycle, stage="inner_selection")
    _cross_validate_manifest_fingerprint_fold(manifest, fingerprint, fold, origin)
    basis = {
        "schema_version": FROZEN_CONFIG_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "pre_run_manifest": manifest,
        "run_fingerprint": fingerprint,
        "fold_identity": fold,
        "origin_index": origin,
        "cycle_index": cycle,
        "seed_namespace": f"origin/{origin:02d}/cycle/{cycle:02d}/inner_selection",
        "derived_seed": seed,
        "stage_candidate_ids": {
            "generated": generated,
            "tested": tested,
            "walk_forward": promoted,
            "finalists": finalists,
        },
        "candidate_evidence": evidence_rows,
        "development_support": support,
        "ranking_order": _RANKING_ORDER,
        "safety": _SAFETY,
    }
    return validate_frozen_selection_config({**basis, "config_sha256": _digest(basis)})


def validate_frozen_selection_config(
    value: FrozenSelectionConfig | Mapping[str, Any],
) -> FrozenSelectionConfig:
    root = value.to_dict() if isinstance(value, FrozenSelectionConfig) else dict(_mapping(value, "frozen_selection_config"))
    expected = {
        "schema_version", "protocol_version", "pre_run_manifest", "run_fingerprint",
        "fold_identity", "origin_index", "cycle_index", "seed_namespace",
        "derived_seed", "stage_candidate_ids", "candidate_evidence",
        "development_support", "ranking_order", "safety", "config_sha256",
    }
    _exact_keys(root, expected, "frozen_selection_config")
    _literal(root, "schema_version", FROZEN_CONFIG_SCHEMA)
    _literal(root, "protocol_version", PROTOCOL_VERSION)
    manifest = _manifest_dict(root["pre_run_manifest"])
    fingerprint = _fingerprint_dict(root["run_fingerprint"])
    fold = validate_inner_fold_identity_payload(root["fold_identity"])
    origin = _positive_int(root["origin_index"], "origin_index")
    cycle = _positive_int(root["cycle_index"], "cycle_index")
    expected_namespace = f"origin/{origin:02d}/cycle/{cycle:02d}/inner_selection"
    if root["seed_namespace"] != expected_namespace:
        raise InnerSelectionError("inner-selection seed namespace is invalid")
    if root["derived_seed"] != origin_cycle_seed(manifest, origin_index=origin, cycle_index=cycle, stage="inner_selection"):
        raise InnerSelectionError("inner-selection seed differs from pre-run manifest")
    stages = dict(_mapping(root["stage_candidate_ids"], "stage_candidate_ids"))
    _exact_keys(stages, {"generated", "tested", "walk_forward", "finalists"}, "stage_candidate_ids")
    generated = _canonical_id_list(stages["generated"], "stage.generated")
    tested = _canonical_id_list(stages["tested"], "stage.tested")
    promoted = _canonical_id_list(stages["walk_forward"], "stage.walk_forward")
    finalists = _canonical_id_list(stages["finalists"], "stage.finalists")
    validate_actual_cycle_counts(generated=len(generated), tested=len(tested), walk_forward=len(promoted), finalists=len(finalists))
    if not set(finalists) <= set(promoted) <= set(tested) <= set(generated):
        raise InnerSelectionError("candidate stages are not nested subsets")
    raw_evidence = root["candidate_evidence"]
    if not isinstance(raw_evidence, list):
        raise InnerSelectionError("candidate_evidence must be a list")
    evidence = sorted(
        (validate_candidate_selection_evidence(row).to_dict() for row in raw_evidence),
        key=lambda row: row["candidate"]["canonical_candidate_id"],
    )
    if [row["candidate"]["canonical_candidate_id"] for row in evidence] != finalists:
        raise InnerSelectionError("candidate evidence does not match finalists")
    support = validate_development_support(root["development_support"]).to_dict()
    if support["mode"] == SYNTHETIC_TEST_FIXTURE and support["matrix"]["candidate_ids"] != tested:
        raise InnerSelectionError("synthetic matrix inventory differs from tested candidates")
    _cross_validate_task16_matrix_support(support, origin, cycle, tested)
    _cross_validate_task17_pbo_support(support, origin, cycle, tested)
    _cross_validate_task18_dsr_support(support, origin, cycle, tested)
    _cross_validate_manifest_fingerprint_fold(manifest, fingerprint, fold, origin)
    normalized = {
        **root,
        "pre_run_manifest": manifest,
        "run_fingerprint": fingerprint,
        "fold_identity": fold,
        "stage_candidate_ids": {
            "generated": generated,
            "tested": tested,
            "walk_forward": promoted,
            "finalists": finalists,
        },
        "candidate_evidence": evidence,
        "development_support": support,
    }
    if normalized["ranking_order"] != _RANKING_ORDER:
        raise InnerSelectionError("inner-selection ranking order is not canonical")
    if normalized["safety"] != _SAFETY:
        raise InnerSelectionError("inner-selection safety locks are invalid")
    observed = _sha256(normalized["config_sha256"], "frozen_selection_config.config_sha256")
    basis = dict(normalized)
    basis.pop("config_sha256")
    if observed != _digest(basis):
        raise InnerSelectionError("frozen selection config digest mismatch")
    _reject_forbidden(basis, "frozen_selection_config")
    return FrozenSelectionConfig(_canonical(basis), observed)


def select_candidate(
    training_window: SelectionTrainingWindow | Mapping[str, Any],
    frozen_pipeline_config: FrozenSelectionConfig | Mapping[str, Any],
) -> SelectionDecision:
    window = validate_selection_training_window(training_window)
    config = validate_frozen_selection_config(frozen_pipeline_config)
    basis = _selection_basis(window, config)
    canonical = _canonical(basis)
    sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return SelectionDecision(canonical, sha, f"protocol_v3_selection_sha256:{sha}")


def validate_selection_decision(
    value: SelectionDecision | Mapping[str, Any],
) -> SelectionDecision:
    root = value.to_dict() if isinstance(value, SelectionDecision) else dict(_mapping(value, "selection_decision"))
    _exact_keys(
        root,
        {
            "schema_version", "protocol_version", "contract_version", "outcome",
            "fixture_only", "training_window", "frozen_pipeline_config",
            "selected_candidate", "eligible_candidate_ids", "ranking_evidence",
            "blockers", "fingerprints", "safety", "decision_sha256", "decision_id",
        },
        "selection_decision",
    )
    observed_sha = _sha256(root.pop("decision_sha256"), "selection_decision.decision_sha256")
    observed_id = root.pop("decision_id")
    if not isinstance(observed_id, str) or not _DECISION_ID.fullmatch(observed_id):
        raise InnerSelectionError("selection decision id is invalid")
    window = validate_selection_training_window(root["training_window"])
    config = validate_frozen_selection_config(root["frozen_pipeline_config"])
    expected = _selection_basis(window, config)
    if root != expected:
        raise InnerSelectionError("selection decision differs from recomputed pure decision")
    canonical = _canonical(expected)
    expected_sha = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if observed_sha != expected_sha or observed_id != f"protocol_v3_selection_sha256:{expected_sha}":
        raise InnerSelectionError("selection decision digest or id mismatch")
    return SelectionDecision(canonical, expected_sha, observed_id)


def build_candidate_selection_identity_payload(
    decision: SelectionDecision | Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_selection_decision(decision)
    basis = {
        "identity_schema_version": CANDIDATE_SELECTION_IDENTITY_SCHEMA,
        "decision": validated.to_dict(),
        "decision_sha256": validated.decision_sha256,
        "decision_id": validated.decision_id,
    }
    return {**basis, "identity_sha256": _digest(basis)}


def validate_candidate_selection_identity_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(_mapping(value, "candidate_selection_identity"))
    _exact_keys(
        root,
        {"identity_schema_version", "decision", "decision_sha256", "decision_id", "identity_sha256"},
        "candidate_selection_identity",
    )
    _literal(root, "identity_schema_version", CANDIDATE_SELECTION_IDENTITY_SCHEMA)
    decision = validate_selection_decision(root["decision"])
    if root["decision_sha256"] != decision.decision_sha256 or root["decision_id"] != decision.decision_id:
        raise InnerSelectionError("candidate-selection identity decision binding mismatch")
    basis = dict(root)
    observed = _sha256(basis.pop("identity_sha256"), "candidate_selection_identity.identity_sha256")
    if observed != _digest(basis):
        raise InnerSelectionError("candidate-selection identity digest mismatch")
    normalized = {
        "identity_schema_version": CANDIDATE_SELECTION_IDENTITY_SCHEMA,
        "decision": decision.to_dict(),
        "decision_sha256": decision.decision_sha256,
        "decision_id": decision.decision_id,
        "identity_sha256": observed,
    }
    if root != normalized:
        raise InnerSelectionError("candidate-selection identity is not canonical")
    return normalized


def _selection_basis(
    window: SelectionTrainingWindow,
    config: FrozenSelectionConfig,
) -> dict[str, Any]:
    """Build one typed, fail-closed selection decision from validated evidence."""

    w = window.to_dict()
    c = config.to_dict()
    if c["fold_identity"] != w["fold_identity"]:
        raise InnerSelectionError(
            "selection config and training window use different Task-14 plans"
        )
    for row in c["candidate_evidence"]:
        if row["training_window_sha256"] != window.window_sha256:
            raise InnerSelectionError(
                "candidate evidence belongs to a different training window"
            )

    support = c["development_support"]
    blockers: set[str] = set()
    if support["matrix"]["state"] != COMPLETE:
        blockers.add("TASK16_MATRIX_INSUFFICIENT_EVIDENCE")
    if support["pbo"]["state"] != COMPLETE:
        blockers.add("TASK17_PBO_INSUFFICIENT_EVIDENCE")
    if support["dsr"]["state"] != COMPLETE:
        blockers.add("TASK18_DSR_INSUFFICIENT_EVIDENCE")
    if not c["stage_candidate_ids"]["finalists"]:
        blockers.add("NO_FINALISTS")
    pbo_score, pbo_cash_pass = _pbo_selection_values(support, c["cycle_index"])
    if (
        support["pbo"]["state"] == COMPLETE
        and pbo_score is not None
        and pbo_score > _MAX_PBO
    ):
        blockers.add("DEVELOPMENT_PBO_GATE_FAILED")

    eligible: list[tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]] = []
    ranking_rows: list[dict[str, Any]] = []
    candidate_rejections: set[str] = set()
    dsr_values = _dsr_selection_values(support)

    for row in c["candidate_evidence"]:
        candidate_id = row["candidate"]["canonical_candidate_id"]
        gate = evaluate_quality_gates(
            row["quality_evidence"], stage="selection"
        ).to_dict()
        gate_passed = gate["passed"] is True and gate["status"] == "pass"
        dsr_score = (
            dsr_values.get(candidate_id)
            if isinstance(dsr_values, Mapping)
            else None
        )
        dsr_passed = (
            isinstance(dsr_score, (int, float))
            and not isinstance(dsr_score, bool)
            and math.isfinite(float(dsr_score))
            and float(dsr_score) >= _MIN_DSR
        )
        beats_cash = pbo_cash_pass.get(candidate_id)

        rank: dict[str, Any] | None = None
        ranking_error: str | None = None
        if gate_passed:
            try:
                rank = _ranking_row(row)
            except (KeyError, TypeError, ValueError, InnerSelectionError):
                ranking_error = "ranking_evidence_invalid_after_gate"
                candidate_rejections.add(
                    f"RANKING_EVIDENCE_INVALID:{candidate_id}"
                )

        ranking_row: dict[str, Any] = {
            "canonical_candidate_id": candidate_id,
            "quality_gate_status": gate["status"],
            "quality_gate_passed": gate_passed,
            "development_dsr": dsr_score,
            "development_dsr_passed": dsr_passed,
            "development_pbo": pbo_score,
            "development_pbo_passed": (
                pbo_score is not None and pbo_score <= _MAX_PBO
            ),
            "development_beats_cash": beats_cash,
            "quality_gate_report_sha256": _digest(gate),
            "ranking_error": ranking_error,
        }
        if rank is not None:
            ranking_row.update(rank)
        ranking_rows.append(ranking_row)

        if not gate_passed:
            candidate_rejections.add(
                f"QUALITY_GATE_NOT_PASSED:{candidate_id}:{gate['status']}"
            )
        if support["dsr"]["state"] == COMPLETE and not dsr_passed:
            candidate_rejections.add(
                f"DEVELOPMENT_DSR_GATE_FAILED:{candidate_id}"
            )
        if support["pbo"]["state"] == COMPLETE and beats_cash is not True:
            candidate_rejections.add(
                f"DEVELOPMENT_CASH_BASELINE_NOT_BEATEN:{candidate_id}"
            )
        if gate_passed and rank is not None and dsr_passed and beats_cash is True:
            eligible.append(
                (lexicographic_candidate_rank_key(rank), row["candidate"], gate)
            )

    ranking_rows.sort(key=lambda row: row["canonical_candidate_id"])
    selected: dict[str, Any] | None = None
    outcome = NO_TRADE
    eligible_ids = sorted(row[1]["canonical_candidate_id"] for row in eligible)
    fixture_only = support["mode"] == SYNTHETIC_TEST_FIXTURE
    if not blockers and eligible:
        eligible.sort(key=lambda item: item[0])
        selected = dict(eligible[0][1])
        outcome = CANDIDATE
    elif not eligible and c["candidate_evidence"]:
        blockers.update(candidate_rejections)
        blockers.add("NO_CANDIDATE_PASSED_ALL_DEVELOPMENT_GATES")

    return {
        "schema_version": SELECTION_DECISION_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": INNER_SELECTION_CONTRACT_VERSION,
        "outcome": outcome,
        "fixture_only": fixture_only,
        "training_window": w,
        "frozen_pipeline_config": c,
        "selected_candidate": selected,
        "eligible_candidate_ids": eligible_ids,
        "ranking_evidence": ranking_rows,
        "blockers": sorted(blockers),
        "fingerprints": _selection_fingerprints(window, config),
        "safety": _SAFETY,
    }

def _ranking_row(row: Mapping[str, Any]) -> dict[str, Any]:
    evidence = row["quality_evidence"]
    aggregate = _mapping(_mapping(evidence, "quality_evidence")["wfv"], "wfv")["aggregate"]
    aggregate = _mapping(aggregate, "wfv.aggregate")
    stress = _mapping(evidence["stress"], "stress")
    joint = _mapping(stress["joint"], "stress.joint")
    return {
        "canonical_candidate_id": row["candidate"]["canonical_candidate_id"],
        "worst_fold_net_usdc_per_day": _finite_number(aggregate["worst_fold_net_usdc_per_day"], "worst_fold_net_usdc_per_day"),
        "median_fold_net_usdc_per_day": _finite_number(aggregate["median_fold_net_usdc_per_day"], "median_fold_net_usdc_per_day"),
        "aggregate_wfv_net_usdc_per_day": _finite_number(aggregate["net_usdc_per_day"], "aggregate_wfv_net_usdc_per_day"),
        "joint_stress_net_usdc_per_day": _finite_number(joint["net_usdc_per_day"], "joint_stress_net_usdc_per_day"),
        "max_drawdown_usdc": _finite_number(aggregate["max_drawdown_usdc"], "max_drawdown_usdc"),
        "friction_share": _finite_number(stress["friction_share_of_positive_pre_cost_pnl"], "friction_share"),
        "free_parameter_count": _nonnegative_int(row["candidate"]["free_parameter_count"], "free_parameter_count"),
    }


def lexicographic_candidate_rank_key(
    row: Mapping[str, Any],
) -> tuple[Any, ...]:
    """Return the one canonical Task-15 ranking key.

    The production cross-cycle selector reuses this function so that the
    within-cycle and across-cycle decisions cannot silently diverge.
    """

    return (
        -_finite_number(
            row["worst_fold_net_usdc_per_day"],
            "worst_fold_net_usdc_per_day",
        ),
        -_finite_number(
            row["median_fold_net_usdc_per_day"],
            "median_fold_net_usdc_per_day",
        ),
        -_finite_number(
            row["aggregate_wfv_net_usdc_per_day"],
            "aggregate_wfv_net_usdc_per_day",
        ),
        -_finite_number(
            row["joint_stress_net_usdc_per_day"],
            "joint_stress_net_usdc_per_day",
        ),
        _finite_number(row["max_drawdown_usdc"], "max_drawdown_usdc"),
        _finite_number(row["friction_share"], "friction_share"),
        _nonnegative_int(
            row["free_parameter_count"], "free_parameter_count"
        ),
        _candidate_id(row["canonical_candidate_id"]),
    )


def _selection_fingerprints(window: SelectionTrainingWindow, config: FrozenSelectionConfig) -> dict[str, Any]:
    c = config.to_dict()
    run = c["run_fingerprint"]
    manifest = c["pre_run_manifest"]
    return {
        "training_window_sha256": window.window_sha256,
        "fold_plan_sha256": c["fold_identity"]["plan_sha256"],
        "fold_plan_id": c["fold_identity"]["plan_id"],
        "frozen_config_sha256": config.config_sha256,
        "pre_run_manifest_sha256": manifest["manifest_sha256"],
        "run_fingerprint_sha256": run["fingerprint_sha256"],
        "pipeline_generation_id": run["pipeline"]["generation_id"],
        "context_identity_sha256": run["context"]["runtime_binding"]["context_identity_sha256"],
        "cost_source_sha256": run["cost_model"]["source_sha256"],
        "quality_gate_source_sha256": run["quality_gates"]["source_sha256"],
        "trial_ledger_head_sha256": run["trial_ledger_head"]["head_sha256"],
        "development_support_sha256": c["development_support"]["support_sha256"],
        "derived_seed": c["derived_seed"],
    }


def _cross_validate_manifest_fingerprint_fold(
    manifest: Mapping[str, Any],
    fingerprint: Mapping[str, Any],
    fold: Mapping[str, Any],
    origin_index: int,
) -> None:
    if manifest["code_commit"] != fingerprint["code"]["git_commit"]:
        raise InnerSelectionError("manifest and run fingerprint code commits differ")
    if manifest["pipeline_generation"]["generation_id"] != fingerprint["pipeline"]["generation_id"]:
        raise InnerSelectionError("manifest and run fingerprint pipeline generations differ")
    origins = manifest["boundary_plan"]["origins"]
    matches = [row for row in origins if row.get("origin_index") == origin_index]
    if len(matches) != 1:
        raise InnerSelectionError("selection origin is absent or duplicated in pre-run manifest")
    origin = matches[0]
    plan = fold["plan"]
    expected_start = origin["training_start_inclusive"] + "T00:00:00Z"
    expected_end = origin["training_end_exclusive"] + "T00:00:00Z"
    if plan["training_start_inclusive_utc"] != expected_start or plan["training_end_exclusive_utc"] != expected_end:
        raise InnerSelectionError("Task-14 fold plan differs from selected manifest origin")


def _manifest_dict(value: PreRunManifest | Mapping[str, Any]) -> dict[str, Any]:
    result = value.to_dict() if isinstance(value, PreRunManifest) else dict(_mapping(value, "pre_run_manifest"))
    validate_pre_run_manifest(result)
    return _normalize(result)


def _fingerprint_dict(value: RunFingerprint | Mapping[str, Any]) -> dict[str, Any]:
    result = value.to_dict() if isinstance(value, RunFingerprint) else dict(_mapping(value, "run_fingerprint"))
    validate_run_fingerprint(result)
    return _normalize(result)


def _candidate_payload(candidate: StrategyCandidate) -> dict[str, Any]:
    params = dict(candidate.params)
    params.setdefault("symbol", "ETHUSDC")
    normalized = StrategyCandidate(str(candidate.family), params)
    signature = canonical_candidate_signature(normalized)
    signature_payload = [signature[0], [[key, value] for key, value in signature[1]]]
    signature_json = _canonical(signature_payload)
    digest = hashlib.sha256(signature_json.encode("utf-8")).hexdigest()
    free_count = len([key for key in params if key != "symbol"])
    return {
        "family": str(candidate.family),
        "params": _normalize(params),
        "canonical_signature": signature_payload,
        "canonical_candidate_id": f"protocol_v3_candidate_sha256:{digest}",
        "free_parameter_count": free_count,
    }


def _validate_candidate_payload(value: Any) -> dict[str, Any]:
    root = dict(_mapping(value, "candidate"))
    _exact_keys(root, {"family", "params", "canonical_signature", "canonical_candidate_id", "free_parameter_count"}, "candidate")
    family = _required_text(root["family"], "candidate.family")
    params = dict(_mapping(root["params"], "candidate.params"))
    _finite_json(params, "candidate.params")
    _reject_forbidden(params, "candidate.params")
    expected = _candidate_payload(StrategyCandidate(family, params))
    if root != expected:
        raise InnerSelectionError("candidate identity is not canonical")
    return expected


def _incomplete_support_row(schema: str, reason: str) -> dict[str, Any]:
    return {
        "state": INSUFFICIENT_EVIDENCE,
        "schema_version": schema,
        "candidate_ids": [],
        "day_count": 0,
        "value": None,
        "evidence_sha256": ZERO_HASH,
        "reason": reason,
    }


def _cross_validate_task16_matrix_support(
    support: Mapping[str, Any],
    origin_index: int,
    cycle_index: int,
    tested_candidate_ids: Sequence[str],
) -> None:
    matrix = support["matrix"]
    if matrix["state"] != COMPLETE or support["mode"] != PRODUCTION:
        return
    identity = matrix["value"]
    payload = identity["matrix"]
    if payload["origin_index"] != origin_index:
        raise InnerSelectionError("Task-16 matrix belongs to a different origin")
    cycles = [row for row in payload["cycles"] if row["cycle_index"] == cycle_index]
    if len(cycles) != 1 or cycles[0]["tested_candidate_ids"] != list(tested_candidate_ids):
        raise InnerSelectionError("Task-16 matrix inventory differs from selected cycle")


def _cross_validate_task17_pbo_support(
    support: Mapping[str, Any],
    origin_index: int,
    cycle_index: int,
    tested_candidate_ids: Sequence[str],
) -> None:
    pbo = support["pbo"]
    if pbo["state"] != COMPLETE or support["mode"] != PRODUCTION:
        return
    identity = pbo["value"]
    evidence = identity["evidence"]
    matrix_identity = support["matrix"]["value"]
    if evidence["matrix_identity"] != matrix_identity:
        raise InnerSelectionError("Task-17 PBO and Task-16 matrix identities differ")
    matrix = matrix_identity["matrix"]
    if matrix["origin_index"] != origin_index:
        raise InnerSelectionError("Task-17 PBO belongs to a different origin")
    cycles = [row for row in matrix["cycles"] if row["cycle_index"] == cycle_index]
    if len(cycles) != 1 or cycles[0]["tested_candidate_ids"] != list(tested_candidate_ids):
        raise InnerSelectionError("Task-17 PBO inventory differs from selected cycle")


def _pbo_selection_values(
    support: Mapping[str, Any],
    cycle_index: int,
) -> tuple[float | None, dict[str, bool]]:
    row = support["pbo"]
    if row["state"] != COMPLETE:
        return None, {}
    if support["mode"] == SYNTHETIC_TEST_FIXTURE:
        return float(row["value"]), {
            candidate_id: True for candidate_id in row["candidate_ids"]
        }
    evidence = row["value"]["evidence"]
    matrix = evidence["matrix_identity"]["matrix"]
    cycle_rows = [item for item in matrix["cycles"] if item["cycle_index"] == cycle_index]
    if len(cycle_rows) != 1:
        raise InnerSelectionError("Task-17 PBO cycle binding is invalid")
    beats_by_profile = evidence["candidate_beats_cash"]
    result: dict[str, bool] = {}
    for profile in cycle_rows[0]["profiles"]:
        result[profile["candidate_id"]] = beats_by_profile[profile["profile_id"]]
    return float(evidence["development_pbo"]), result


def _cross_validate_task18_dsr_support(
    support: Mapping[str, Any],
    origin_index: int,
    cycle_index: int,
    tested_candidate_ids: Sequence[str],
) -> None:
    row = support["dsr"]
    if row["state"] != COMPLETE or support["mode"] != PRODUCTION:
        return
    identities = row["value"]
    if set(identities) != set(tested_candidate_ids):
        raise InnerSelectionError("Task-18 DSR inventory differs from selected cycle")
    for candidate_id, identity in identities.items():
        evidence = identity["evidence"]
        if evidence["pbo_identity"] != support["pbo"]["value"]:
            raise InnerSelectionError("Task-18 DSR and Task-17 PBO identities differ")
        if evidence["pbo_identity"]["evidence"]["matrix_identity"] != support["matrix"]["value"]:
            raise InnerSelectionError("Task-18 DSR and Task-16 matrix identities differ")
        matrix = evidence["pbo_identity"]["evidence"]["matrix_identity"]["matrix"]
        if matrix["origin_index"] != origin_index:
            raise InnerSelectionError("Task-18 DSR belongs to a different origin")
        cycles = [item for item in matrix["cycles"] if item["cycle_index"] == cycle_index]
        if len(cycles) != 1:
            raise InnerSelectionError("Task-18 DSR cycle binding is invalid")
        profiles = [item for item in cycles[0]["profiles"] if item["candidate_id"] == candidate_id]
        if len(profiles) != 1 or evidence["selected_profile_id"] != profiles[0]["profile_id"]:
            raise InnerSelectionError("Task-18 DSR candidate/profile binding is invalid")


def _dsr_selection_values(support: Mapping[str, Any]) -> dict[str, float]:
    row = support["dsr"]
    if row["state"] != COMPLETE:
        return {}
    if support["mode"] == SYNTHETIC_TEST_FIXTURE:
        return {key: float(value) for key, value in row["value"].items()}
    return {
        candidate_id: float(identity["evidence"]["development_dsr"])
        for candidate_id, identity in row["value"].items()
    }


def _validate_support_row(value: Any, name: str, mode: str) -> dict[str, Any]:
    row = dict(_mapping(value, f"development_support.{name}"))
    _exact_keys(row, {"state", "schema_version", "candidate_ids", "day_count", "value", "evidence_sha256", "reason"}, f"development_support.{name}")
    _required_text(row["schema_version"], f"{name}.schema_version")
    row["candidate_ids"] = _canonical_id_list(row["candidate_ids"], f"{name}.candidate_ids")
    row["day_count"] = _nonnegative_int(row["day_count"], f"{name}.day_count")
    row["reason"] = _required_text(row["reason"], f"{name}.reason")
    if row["state"] == INSUFFICIENT_EVIDENCE:
        if row["candidate_ids"] or row["day_count"] != 0 or row["value"] is not None or row["evidence_sha256"] != ZERO_HASH:
            raise InnerSelectionError(f"{name} insufficient-evidence row is not canonical")
    elif row["state"] == COMPLETE:
        if mode == PRODUCTION and name not in {"matrix", "pbo", "dsr"}:
            raise InnerSelectionError(f"production {name} support is not implemented")
        empty_production_matrix = (
            mode == PRODUCTION and name == "matrix" and not row["candidate_ids"]
        )
        if (
            (not row["candidate_ids"] and not empty_production_matrix)
            or row["day_count"] != _REQUIRED_MATRIX_DAYS
        ):
            raise InnerSelectionError(f"{name} complete support has wrong inventory or day count")
        _sha256(row["evidence_sha256"], f"{name}.evidence_sha256")
        if row["evidence_sha256"] == ZERO_HASH:
            raise InnerSelectionError(f"{name} complete support requires nonzero evidence digest")
        if name == "matrix":
            if mode == SYNTHETIC_TEST_FIXTURE and row["value"] is not None:
                raise InnerSelectionError("synthetic matrix support value must be null")
            if mode == PRODUCTION:
                from .candidate_matrix import validate_candidate_matrix_identity_payload
                identity = validate_candidate_matrix_identity_payload(_mapping(row["value"], "matrix.value"))
                if row["evidence_sha256"] != identity["matrix_sha256"]:
                    raise InnerSelectionError("matrix support digest differs from Task-16 identity")
                row["value"] = identity
        if name == "pbo":
            if mode == SYNTHETIC_TEST_FIXTURE:
                row["value"] = _finite_number(row["value"], "pbo.value")
            else:
                from .pbo import validate_pbo_identity_payload
                identity = validate_pbo_identity_payload(_mapping(row["value"], "pbo.value"))
                if row["evidence_sha256"] != identity["evidence_sha256"]:
                    raise InnerSelectionError("PBO support digest differs from Task-17 identity")
                if identity["evidence"]["state"] != COMPLETE:
                    raise InnerSelectionError("complete PBO support contains insufficient evidence")
                row["value"] = identity
        if name == "dsr":
            if not isinstance(row["value"], Mapping):
                raise InnerSelectionError("dsr.value must be a candidate-score mapping")
            if mode == SYNTHETIC_TEST_FIXTURE:
                row["value"] = dict(sorted((_candidate_id(key), _finite_number(score, f"dsr.{key}")) for key, score in row["value"].items()))
            else:
                from .dsr import COMPLETE as DSR_COMPLETE, validate_dsr_identity_payload
                identities = {
                    _candidate_id(key): validate_dsr_identity_payload(_mapping(identity, f"dsr.{key}"))
                    for key, identity in row["value"].items()
                }
                if any(identity["evidence"]["state"] != DSR_COMPLETE for identity in identities.values()):
                    raise InnerSelectionError("complete DSR support contains insufficient evidence")
                if row["evidence_sha256"] != _digest(dict(sorted(identities.items()))):
                    raise InnerSelectionError("DSR support digest differs from Task-18 identities")
                row["value"] = dict(sorted(identities.items()))
    else:
        raise InnerSelectionError(f"{name} support state is invalid")
    return row


def _canonical_id_list(value: Any, path: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InnerSelectionError(f"{path} must be a candidate-id sequence")
    rows = [_candidate_id(item) for item in value]
    if len(rows) != len(set(rows)):
        raise InnerSelectionError(f"{path} contains duplicate candidate ids")
    return sorted(rows)


def _candidate_id(value: Any) -> str:
    if not isinstance(value, str) or not _CANDIDATE_ID.fullmatch(value):
        raise InnerSelectionError("canonical candidate id is invalid")
    return value


def _strict_loads(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise InnerSelectionError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject(value: str) -> None:
        raise InnerSelectionError(f"non-finite JSON constant: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject)


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InnerSelectionError(f"value is not strict JSON: {exc}") from exc


def _normalize(value: Any) -> Any:
    return json.loads(_canonical(value))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InnerSelectionError(f"{path} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        raise InnerSelectionError(f"{path} keys invalid; missing={sorted(missing)} extra={sorted(extra)}")


def _literal(value: Mapping[str, Any], key: str, expected: Any) -> None:
    observed = value.get(key)
    if observed != expected or type(observed) is not type(expected):
        raise InnerSelectionError(f"{key} must equal {expected!r}")


def _required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InnerSelectionError(f"{path} must be a non-empty string")
    return value.strip()


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InnerSelectionError(f"{path} must be a positive integer")
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InnerSelectionError(f"{path} must be a non-negative integer")
    return value


def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise InnerSelectionError(f"{path} must be a finite number")
    return float(value)


def _sha256(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise InnerSelectionError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _parse_utc(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InnerSelectionError(f"{path} must be UTC and end in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InnerSelectionError(f"{path} is invalid") from exc
    if parsed.utcoffset() != timedelta(0):
        raise InnerSelectionError(f"{path} must be UTC")
    return parsed.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise InnerSelectionError("timestamp must be timezone-aware UTC")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _timestamp_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def _finite_json(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise InnerSelectionError(f"{path} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise InnerSelectionError(f"{path} contains a non-string key")
            _finite_json(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _finite_json(item, f"{path}[{index}]")
        return
    raise InnerSelectionError(f"{path} contains a non-JSON value")


def _reject_forbidden(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                raise InnerSelectionError(f"{path} contains forbidden selection input: {key}")
            _reject_forbidden(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden(item, f"{path}[{index}]")


__all__ = [
    "CANDIDATE",
    "CANDIDATE_EVIDENCE_SCHEMA",
    "CANDIDATE_SELECTION_IDENTITY_SCHEMA",
    "COMPLETE",
    "DEVELOPMENT_EVIDENCE_SCHEMA",
    "FROZEN_CONFIG_SCHEMA",
    "INNER_SELECTION_CONTRACT_PATH",
    "INNER_SELECTION_CONTRACT_SCHEMA",
    "INNER_SELECTION_CONTRACT_VERSION",
    "INSUFFICIENT_EVIDENCE",
    "NO_TRADE",
    "PRODUCTION",
    "SELECTION_DECISION_SCHEMA",
    "SYNTHETIC_TEST_FIXTURE",
    "TRAINING_WINDOW_SCHEMA",
    "CandidateSelectionEvidence",
    "DevelopmentSupport",
    "FrozenSelectionConfig",
    "InnerSelectionError",
    "SelectionDecision",
    "SelectionTimestampSpy",
    "SelectionTrainingWindow",
    "build_candidate_selection_evidence",
    "build_candidate_selection_identity_payload",
    "build_frozen_selection_config",
    "build_incomplete_development_support",
    "build_dsr_development_support",
    "build_matrix_development_support",
    "build_pbo_development_support",
    "build_selection_training_window",
    "build_synthetic_complete_development_support",
    "lexicographic_candidate_rank_key",
    "load_inner_selection_contract",
    "select_candidate",
    "validate_candidate_selection_evidence",
    "validate_candidate_selection_identity_payload",
    "validate_development_support",
    "validate_frozen_selection_config",
    "validate_inner_selection_contract",
    "validate_selection_decision",
    "validate_selection_training_window",
]
