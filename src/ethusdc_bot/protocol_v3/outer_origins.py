"""Twelve-origin causal selection orchestrator without an outer-result input channel."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from .boundaries import (
    MonthlyOriginBoundary,
    MonthlyProcessBoundaryPlan,
    validate_monthly_process_boundary_plan,
)
from .inner_selection import (
    FrozenSelectionConfig,
    build_selection_training_window,
    select_candidate,
    validate_frozen_selection_config,
    validate_selection_decision,
)
from .router_bundle import (
    CONTRACT_VERSION as BUNDLE_CONTRACT_VERSION,
    FROZEN_BUNDLE_SCHEMA_VERSION,
    LocalEdgeEvidence,
    build_frozen_candidate_bundle,
    route_specialist,
)

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_outer_origins_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_outer_origins_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_twelve_causal_outer_origin_orchestrator_v1"
ORIGIN_SCHEMA_VERSION: Final = "protocol_v3_outer_origin_selection_v1"
PROCESS_SCHEMA_VERSION: Final = "protocol_v3_outer_origin_process_v1"
_FORBIDDEN_RESULT_KINDS: Final = {
    "pnl",
    "ranking",
    "report",
    "gate_result",
    "human_interpretation",
}
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_BUNDLE_SAFETY: Final = {**_SAFETY, "long_only": True, "symbol": "ETHUSDC"}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "process_policy": {
        "outer_origins": 12,
        "development_days_per_origin": 730,
        "process_oos_days": 365,
        "pipeline_refit_per_origin": True,
        "same_pipeline_generation_required": True,
        "same_code_commit_required": True,
        "distinct_fit_cutoffs_required": True,
        "complete_oos_union_required": True,
        "selection_pipeline_invoked_inside_orchestrator": True,
        "exactly_one_frozen_bundle_per_origin": True,
    },
    "isolation_policy": {
        "prior_raw_market_observations_may_become_causal_training_history": True,
        "prior_outer_pnl_forbidden": True,
        "prior_outer_rankings_forbidden": True,
        "prior_outer_reports_forbidden": True,
        "prior_outer_gate_results_forbidden": True,
        "human_result_interpretation_forbidden": True,
        "outer_result_channel_exposed_to_selection": False,
    },
    "deferred_scope": {
        "entry_delay_and_rotation_task": 24,
        "daily_mtm_and_time_aggregation_task": 25,
        "monthly_quality_gate_task": 26,
    },
    "safety": _SAFETY,
}


class OuterOriginError(ValueError):
    """Raised when an outer origin is incomplete, inconsistent, or leaky."""


@dataclass(frozen=True)
class OuterOriginRequest:
    frozen_selection_config: FrozenSelectionConfig
    local_edge: LocalEdgeEvidence | None
    store: Any
    binding: Any
    feature_fit_state: Any
    regime_fit_state: Any
    assessment: Any


@dataclass(frozen=True)
class OuterOriginSelection:
    canonical_json: str
    origin_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["origin_sha256"] = self.origin_sha256
        return value


@dataclass(frozen=True)
class OuterOriginProcess:
    canonical_json: str
    process_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["process_sha256"] = self.process_sha256
        return value


class OuterIsolationSpy:
    """Prove raw history is causal while earlier outer results stay unreachable."""

    def __init__(self, plan: MonthlyProcessBoundaryPlan) -> None:
        validate_monthly_process_boundary_plan(plan)
        self._plan = plan
        self._reads: list[dict[str, Any]] = []

    def observe_raw_market_day(
        self, *, origin_index: int, day: date | str
    ) -> None:
        origin = _origin(self._plan, origin_index)
        observed = _day(day, "day")
        if not (
            origin.training_start_inclusive
            <= observed
            < origin.training_end_exclusive
        ):
            raise OuterOriginError(
                "raw market day lies outside the origin's causal 730-day window"
            )
        self._reads.append(
            {
                "origin_index": origin_index,
                "kind": "raw_market",
                "day": observed.isoformat(),
            }
        )

    def observe_prior_outer_result(
        self,
        *,
        origin_index: int,
        prior_origin_index: int,
        kind: str,
    ) -> None:
        _origin(self._plan, origin_index)
        _origin(self._plan, prior_origin_index)
        if prior_origin_index >= origin_index:
            raise OuterOriginError("outer result source is not a prior origin")
        if kind not in _FORBIDDEN_RESULT_KINDS:
            raise OuterOriginError("unknown outer result kind")
        raise OuterOriginError(f"prior outer {kind} is forbidden in later fits")

    @property
    def raw_reads(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in self._reads)


def load_outer_origins_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise OuterOriginError(
            "outer-origins contract is missing or invalid"
        ) from exc
    if value != _CANONICAL_CONTRACT:
        raise OuterOriginError("Protocol v3 outer-origins contract is not canonical")
    return value


def orchestrate_outer_origins(
    boundary_plan: MonthlyProcessBoundaryPlan,
    requests: Sequence[OuterOriginRequest],
) -> OuterOriginProcess:
    """Invoke the unchanged pure selection path once for each of twelve origins."""

    validate_monthly_process_boundary_plan(boundary_plan)
    if (
        not isinstance(requests, Sequence)
        or isinstance(requests, (str, bytes))
        or len(requests) != 12
    ):
        raise OuterOriginError(
            "outer process requires exactly twelve origin requests"
        )
    rows = [
        run_outer_origin(origin, request)
        for origin, request in zip(
            boundary_plan.origins, requests, strict=True
        )
    ]
    _same_pipeline(rows)
    day_grid = [day.isoformat() for day in boundary_plan.iter_process_oos_days()]
    basis = {
        "schema_version": PROCESS_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "pipeline_refit_per_origin": True,
        "process_start_inclusive": boundary_plan.process_start_inclusive.isoformat(),
        "process_end_exclusive": boundary_plan.process_end_exclusive.isoformat(),
        "process_oos_day_grid": day_grid,
        "process_oos_day_grid_sha256": _digest(day_grid),
        "origins": [row.to_dict() for row in rows],
        "origin_count": 12,
        "outer_result_channel_exposed_to_selection": False,
        "rotation_state_deferred_to_task": 24,
        "daily_mtm_deferred_to_task": 25,
        "safety": _SAFETY,
    }
    return validate_outer_origin_process(
        {**basis, "process_sha256": _digest(basis)},
        boundary_plan=boundary_plan,
    )


def run_outer_origin(
    origin: MonthlyOriginBoundary,
    request: OuterOriginRequest,
    *,
    predecessor_bundle_sha256: str | None = None,
) -> OuterOriginSelection:
    """Run the exact Task-15/22 path for one bound origin.

    Task 23 calls this with no predecessor. Task 28 reuses the same path and may
    bind the immediately preceding frozen bundle without adding another
    selection or routing implementation.
    """

    if not isinstance(origin, MonthlyOriginBoundary):
        raise OuterOriginError("verified MonthlyOriginBoundary required")
    if not isinstance(request, OuterOriginRequest):
        raise OuterOriginError("verified OuterOriginRequest required")
    if predecessor_bundle_sha256 is not None:
        _sha(predecessor_bundle_sha256, "predecessor_bundle_sha256")
    config = validate_frozen_selection_config(request.frozen_selection_config)
    config_payload = config.to_dict()
    if config_payload["origin_index"] != origin.origin_index:
        raise OuterOriginError("selection config belongs to another origin")
    fold_identity = config_payload["fold_identity"]
    training_window = build_selection_training_window(
        {**fold_identity["plan"], "plan_sha256": fold_identity["plan_sha256"]}
    )
    if (
        training_window.start_utc.date() != origin.training_start_inclusive
        or training_window.end_utc.date() != origin.training_end_exclusive
    ):
        raise OuterOriginError(
            "selection window differs from exact outer 730-day window"
        )
    expected_context_ms = int(
        _midnight(origin.test_start_inclusive).timestamp() * 1000
    )
    store_payload = _object_payload(request.store, "feature_store")
    assessment_payload = _object_payload(
        request.assessment, "regime_assessment"
    )
    feature_state_payload = _object_payload(
        request.feature_fit_state, "feature_fit_state"
    )
    regime_state_payload = _object_payload(
        request.regime_fit_state, "regime_fit_state"
    )
    if store_payload.get("common_context_timestamp_ms") != expected_context_ms:
        raise OuterOriginError(
            "feature store cutoff must equal the origin fit timestamp"
        )
    if assessment_payload.get("context_timestamp_ms") != expected_context_ms:
        raise OuterOriginError(
            "regime assessment cutoff must equal the origin fit timestamp"
        )
    if (
        feature_state_payload.get("fold_identity") != fold_identity
        or regime_state_payload.get("fold_identity") != fold_identity
    ):
        raise OuterOriginError(
            "feature/regime fit state belongs to another origin fold plan"
        )
    decision = select_candidate(training_window, config)
    route = route_specialist(
        decision,
        request.local_edge,
        store=request.store,
        binding=request.binding,
        feature_fit_state=request.feature_fit_state,
        regime_fit_state=request.regime_fit_state,
        assessment=request.assessment,
    )
    anchor = _midnight(origin.test_start_inclusive)
    bundle = build_frozen_candidate_bundle(
        route,
        decision,
        request.local_edge,
        store=request.store,
        binding=request.binding,
        feature_fit_state=request.feature_fit_state,
        regime_fit_state=request.regime_fit_state,
        assessment=request.assessment,
        as_of_utc=_utc_text(anchor),
        valid_from_utc=_utc_text(origin.valid_from),
        valid_until_utc=_utc_text(origin.valid_until),
        predecessor_bundle_sha256=predecessor_bundle_sha256,
    )
    return _origin_envelope(origin, decision.to_dict(), bundle.to_dict())


# Backward-compatible private name for internal callers and tests.
_run_origin = run_outer_origin


def validate_outer_origin_selection(
    value: OuterOriginSelection | Mapping[str, Any],
    *,
    origin: MonthlyOriginBoundary,
) -> OuterOriginSelection:
    """Validate one canonical origin envelope with the full Task-23 rules."""

    if not isinstance(origin, MonthlyOriginBoundary):
        raise OuterOriginError("verified MonthlyOriginBoundary required")
    root = value.to_dict() if isinstance(value, OuterOriginSelection) else value
    normalized = _validate_origin_envelope(root, origin)
    observed = normalized["origin_sha256"]
    basis = dict(normalized)
    basis.pop("origin_sha256")
    return OuterOriginSelection(_canonical(basis), observed)


def validate_outer_origin_process(
    value: OuterOriginProcess | Mapping[str, Any],
    *,
    boundary_plan: MonthlyProcessBoundaryPlan,
) -> OuterOriginProcess:
    validate_monthly_process_boundary_plan(boundary_plan)
    root = (
        value.to_dict()
        if isinstance(value, OuterOriginProcess)
        else dict(_mapping(value, "outer_process"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "pipeline_refit_per_origin",
        "process_start_inclusive",
        "process_end_exclusive",
        "process_oos_day_grid",
        "process_oos_day_grid_sha256",
        "origins",
        "origin_count",
        "outer_result_channel_exposed_to_selection",
        "rotation_state_deferred_to_task",
        "daily_mtm_deferred_to_task",
        "safety",
        "process_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != PROCESS_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
    ):
        raise OuterOriginError("outer process fields or versions are invalid")
    expected_days = [day.isoformat() for day in boundary_plan.iter_process_oos_days()]
    if (
        root["process_start_inclusive"]
        != boundary_plan.process_start_inclusive.isoformat()
        or root["process_end_exclusive"]
        != boundary_plan.process_end_exclusive.isoformat()
    ):
        raise OuterOriginError("outer process boundary mismatch")
    if (
        root["process_oos_day_grid"] != expected_days
        or len(expected_days) != 365
        or len(set(expected_days)) != 365
        or root["process_oos_day_grid_sha256"] != _digest(expected_days)
    ):
        raise OuterOriginError(
            "outer process OOS union is incomplete or duplicated"
        )
    rows = root["origins"]
    if not isinstance(rows, list) or len(rows) != 12 or root["origin_count"] != 12:
        raise OuterOriginError("outer process must contain twelve origins")
    normalized = [
        _validate_origin_envelope(row, origin)
        for row, origin in zip(rows, boundary_plan.origins, strict=True)
    ]
    _same_pipeline_payloads(normalized)
    if (
        root["origins"] != normalized
        or root["pipeline_refit_per_origin"] is not True
        or root["outer_result_channel_exposed_to_selection"] is not False
    ):
        raise OuterOriginError("outer process orchestration policy is invalid")
    if (
        root["rotation_state_deferred_to_task"] != 24
        or root["daily_mtm_deferred_to_task"] != 25
        or root["safety"] != _SAFETY
    ):
        raise OuterOriginError("outer process scope or safety locks are invalid")
    observed = _sha(root["process_sha256"], "process_sha256")
    basis = dict(root)
    basis.pop("process_sha256")
    if observed != _digest(basis):
        raise OuterOriginError("outer process digest mismatch")
    return OuterOriginProcess(_canonical(basis), observed)


def _origin_envelope(
    origin: MonthlyOriginBoundary,
    decision: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> OuterOriginSelection:
    basis = {
        "schema_version": ORIGIN_SCHEMA_VERSION,
        "origin_index": origin.origin_index,
        "training_start_inclusive": origin.training_start_inclusive.isoformat(),
        "training_end_exclusive": origin.training_end_exclusive.isoformat(),
        "test_start_inclusive": origin.test_start_inclusive.isoformat(),
        "test_end_exclusive": origin.test_end_exclusive.isoformat(),
        "selection_decision": dict(decision),
        "frozen_candidate_bundle": dict(bundle),
        "pipeline_generation_id": decision["fingerprints"][
            "pipeline_generation_id"
        ],
        "code_commit": decision["frozen_pipeline_config"]["run_fingerprint"][
            "code"
        ]["git_commit"],
        "outer_results_visible_during_fit": False,
        "safety": _SAFETY,
    }
    return OuterOriginSelection(_canonical(basis), _digest(basis))


def _validate_origin_envelope(
    raw: Any, origin: MonthlyOriginBoundary
) -> dict[str, Any]:
    root = dict(_mapping(raw, "outer_origin"))
    required = {
        "schema_version",
        "origin_index",
        "training_start_inclusive",
        "training_end_exclusive",
        "test_start_inclusive",
        "test_end_exclusive",
        "selection_decision",
        "frozen_candidate_bundle",
        "pipeline_generation_id",
        "code_commit",
        "outer_results_visible_during_fit",
        "safety",
        "origin_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != ORIGIN_SCHEMA_VERSION
        or root["origin_index"] != origin.origin_index
    ):
        raise OuterOriginError(
            "outer origin fields, version, or index are invalid"
        )
    expected_bounds = (
        origin.training_start_inclusive.isoformat(),
        origin.training_end_exclusive.isoformat(),
        origin.test_start_inclusive.isoformat(),
        origin.test_end_exclusive.isoformat(),
    )
    if tuple(
        root[key]
        for key in (
            "training_start_inclusive",
            "training_end_exclusive",
            "test_start_inclusive",
            "test_end_exclusive",
        )
    ) != expected_bounds:
        raise OuterOriginError("outer origin boundary mismatch")
    decision = validate_selection_decision(root["selection_decision"]).to_dict()
    bundle = _bundle_envelope(
        root["frozen_candidate_bundle"], decision, origin
    )
    if (
        root["selection_decision"] != decision
        or root["frozen_candidate_bundle"] != bundle
    ):
        raise OuterOriginError(
            "outer origin decision or bundle is not canonical"
        )
    run = decision["frozen_pipeline_config"]["run_fingerprint"]
    if (
        root["pipeline_generation_id"]
        != decision["fingerprints"]["pipeline_generation_id"]
        or root["code_commit"] != run["code"]["git_commit"]
    ):
        raise OuterOriginError("outer origin code or pipeline identity mismatch")
    if (
        root["outer_results_visible_during_fit"] is not False
        or root["safety"] != _SAFETY
    ):
        raise OuterOriginError("outer origin isolation or safety is invalid")
    observed = _sha(root["origin_sha256"], "origin_sha256")
    basis = dict(root)
    basis.pop("origin_sha256")
    if observed != _digest(basis):
        raise OuterOriginError("outer origin digest mismatch")
    return root


def _bundle_envelope(
    raw: Any,
    decision: Mapping[str, Any],
    origin: MonthlyOriginBoundary,
) -> dict[str, Any]:
    bundle = dict(_mapping(raw, "frozen_candidate_bundle"))
    observed = _sha(bundle.get("bundle_sha256"), "bundle_sha256")
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "router_decision",
        "specialist_bundle",
        "scalar_parameters",
        "selection_decision_sha256",
        "local_edge_evidence_sha256",
        "feature_store_identity",
        "feature_fit_state",
        "regime_fit_state",
        "assessment_sha256",
        "context_policy",
        "cost_model",
        "rotation_policy",
        "predecessor_bundle_sha256",
        "validity",
        "fixture_only",
        "research_simulation_routable",
        "canonical_adoption_eligible",
        "safety",
        "bundle_sha256",
    }
    if (
        set(bundle) != required
        or bundle.get("protocol_version") != PROTOCOL_VERSION
        or bundle.get("contract_version") != BUNDLE_CONTRACT_VERSION
    ):
        raise OuterOriginError(
            "frozen candidate bundle fields or versions are invalid"
        )
    basis = dict(bundle)
    basis.pop("bundle_sha256", None)
    if (
        bundle.get("schema_version") != FROZEN_BUNDLE_SCHEMA_VERSION
        or observed != _digest(basis)
    ):
        raise OuterOriginError("frozen candidate bundle identity is invalid")
    predecessor = bundle.get("predecessor_bundle_sha256")
    if predecessor is not None:
        _sha(predecessor, "predecessor_bundle_sha256")
    if bundle.get("selection_decision_sha256") != decision["decision_sha256"]:
        raise OuterOriginError("bundle does not bind its origin selection")
    validity = bundle.get("validity")
    expected = {
        "as_of_utc": _utc_text(_midnight(origin.test_start_inclusive)),
        "valid_from_utc": _utc_text(origin.valid_from),
        "valid_until_utc": _utc_text(origin.valid_until),
    }
    if (
        validity != expected
        or bundle.get("canonical_adoption_eligible") is not False
    ):
        raise OuterOriginError("bundle validity or adoption lock is invalid")
    router = dict(_mapping(bundle.get("router_decision"), "router_decision"))
    router_observed = _sha(
        router.get("decision_sha256"), "router.decision_sha256"
    )
    router_basis = dict(router)
    router_basis.pop("decision_sha256", None)
    if router_observed != _digest(router_basis):
        raise OuterOriginError("bundle router decision digest mismatch")
    if (
        router.get("selection_decision_sha256") != decision["decision_sha256"]
        or router.get("transaction_eligible") is not False
    ):
        raise OuterOriginError(
            "bundle router does not bind the selection or transaction lock"
        )
    if (
        bundle.get("safety") != _BUNDLE_SAFETY
        or router.get("safety") != _BUNDLE_SAFETY
    ):
        raise OuterOriginError("bundle or router safety locks are invalid")
    specialist = dict(
        _mapping(bundle.get("specialist_bundle"), "specialist_bundle")
    )
    specialist_observed = _sha(
        specialist.get("bundle_sha256"), "specialist.bundle_sha256"
    )
    specialist_basis = dict(specialist)
    specialist_basis.pop("bundle_sha256", None)
    if specialist_observed != _digest(specialist_basis):
        raise OuterOriginError("specialist bundle digest mismatch")
    return bundle


def _same_pipeline(rows: Sequence[OuterOriginSelection]) -> None:
    _same_pipeline_payloads([row.to_dict() for row in rows])


def _same_pipeline_payloads(rows: Sequence[Mapping[str, Any]]) -> None:
    generations = {row["pipeline_generation_id"] for row in rows}
    commits = {row["code_commit"] for row in rows}
    cutoffs = [row["training_end_exclusive"] for row in rows]
    if len(generations) != 1 or len(commits) != 1:
        raise OuterOriginError(
            "all origins must use one frozen pipeline generation and code commit"
        )
    if len(set(cutoffs)) != 12 or cutoffs != sorted(cutoffs):
        raise OuterOriginError(
            "outer fit cutoffs must be distinct and chronological"
        )


def _origin(
    plan: MonthlyProcessBoundaryPlan, index: int
) -> MonthlyOriginBoundary:
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or not 1 <= index <= 12
    ):
        raise OuterOriginError("origin_index must be 1..12")
    return plan.origins[index - 1]


def _day(value: date | str, name: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise OuterOriginError(f"{name} is invalid") from exc
    raise OuterOriginError(f"{name} must be a date")


def _midnight(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OuterOriginError(f"{name} must be an object")
    return value


def _object_payload(value: Any, name: str) -> Mapping[str, Any]:
    if not hasattr(value, "to_dict") or not callable(value.to_dict):
        raise OuterOriginError(f"{name} must be a verified typed object")
    return _mapping(value.to_dict(), name)


def _sha(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise OuterOriginError(f"{name} must be lowercase sha256")
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
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "ORIGIN_SCHEMA_VERSION",
    "PROCESS_SCHEMA_VERSION",
    "OuterIsolationSpy",
    "OuterOriginError",
    "OuterOriginProcess",
    "OuterOriginRequest",
    "OuterOriginSelection",
    "load_outer_origins_contract",
    "orchestrate_outer_origins",
    "run_outer_origin",
    "validate_outer_origin_process",
    "validate_outer_origin_selection",
]
