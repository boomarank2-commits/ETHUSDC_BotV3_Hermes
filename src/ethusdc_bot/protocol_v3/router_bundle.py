"""Deterministic NO_TRADE router and complete frozen candidate bundle (Task 22)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Final

from ethusdc_bot.backtest.simulator import StrategyCandidate

from .context_parity import ContextParityBinding, validate_context_parity_binding
from .feature_store import (
    FoldFeatureFitState,
    MultiTimeframeFeatureStore,
    validate_feature_store_against_binding,
    validate_fold_feature_state,
)
from .inner_selection import CANDIDATE, SelectionDecision, validate_selection_decision
from .opportunity_regime import (
    COMPLETE,
    OpportunityRegimeAssessment,
    OpportunityRegimeFitState,
    validate_opportunity_regime_assessment,
    validate_opportunity_regime_fit_state,
)
from .specialists import (
    NO_TRADE as NO_TRADE_SPECIALIST,
    SPECS,
    build_specialist_bundle,
)

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_router_bundle_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_router_bundle_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_deterministic_no_trade_router_and_frozen_candidate_bundle_v1"
LOCAL_EDGE_SCHEMA_VERSION: Final = "protocol_v3_local_specialist_edge_replay_v1"
ROUTER_DECISION_SCHEMA_VERSION: Final = "protocol_v3_router_decision_v1"
FROZEN_BUNDLE_SCHEMA_VERSION: Final = "protocol_v3_frozen_candidate_bundle_v1"
SPECIALIST: Final = "SPECIALIST"
NO_TRADE: Final = "NO_TRADE"
MIN_TRADES: Final = 20
MIN_PROFIT_FACTOR: Final = 1.05
_SAFETY: Final = {
    "api_keys": "forbidden", "live": "locked", "orders": "locked",
    "paper": "locked", "testtrade": "locked", "trading_api": "forbidden",
    "long_only": True, "symbol": "ETHUSDC",
}
_ROTATION_POLICY: Final = {
    "entry_delay_hours": 24, "entry_before_valid_from_forbidden": True,
    "retiring_bundle_mode": "EXIT_ONLY", "flat_handoff_required": True,
    "max_open_lots": 1, "runtime_state_task": 24,
}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "router_policy": {
        "outcomes": [SPECIALIST, NO_TRADE], "exactly_one_outcome": True,
        "no_trade_is_default": True, "task15_selection_required": True,
        "task20_assessment_must_be_exactly_revalidated": True,
        "task21_specialist_mapping_required": True, "local_edge_replay_required": True,
        "btc_or_ethbtc_may_create_position": False,
        "opportunity_may_determine_direction": False, "max_open_lots": 1,
    },
    "local_edge_policy": {
        "required_folds": 6, "days_per_fold": 60, "required_days": 360,
        "minimum_total_trades": MIN_TRADES, "minimum_profit_factor": MIN_PROFIT_FACTOR,
        "every_fold_net_usdc_per_day_must_be_positive": True,
        "daily_rows_are_specialist_filtered_net_mtm": True,
        "missing_days_are_not_zero": True, "outer_results_forbidden": True,
    },
    "bundle_policy": {
        "binds": ["router_decision", "specialist_bundle", "scalar_parameters",
                  "feature_scalers_and_quantiles", "opportunity_regime_quantiles",
                  "feature_store_identity", "context_policy", "cost_model",
                  "selection_and_local_edge_evidence", "rotation_policy", "validity"],
        "valid_from_is_as_of_plus_hours": 24, "entry_before_valid_from_forbidden": True,
        "retiring_bundle_is_exit_only": True, "flat_handoff_required": True,
        "task24_runtime_rotation_state_deferred": True,
        "flat_strategy_candidate_params_are_not_executable": True,
    },
    "deferred_scope": {"outer_orchestration_task": 23, "runtime_rotation_state_task": 24, "daily_mtm_task": 25},
    "safety": _SAFETY,
}


class RouterBundleError(ValueError):
    """Raised when routing or frozen bundle evidence is incomplete or contradictory."""


@dataclass(frozen=True)
class LocalEdgeEvidence:
    canonical_json: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["evidence_sha256"] = self.evidence_sha256
        return value


@dataclass(frozen=True)
class RouterDecision:
    canonical_json: str
    decision_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["decision_sha256"] = self.decision_sha256
        return value

    @property
    def outcome(self) -> str:
        return str(json.loads(self.canonical_json)["outcome"])


@dataclass(frozen=True)
class FrozenCandidateBundle:
    canonical_json: str
    bundle_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["bundle_sha256"] = self.bundle_sha256
        return value


def load_router_bundle_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RouterBundleError("router/bundle contract is missing or invalid") from exc
    if value != _CANONICAL_CONTRACT:
        raise RouterBundleError("Protocol v3 router/bundle contract is not canonical")
    return value


def build_local_edge_evidence(
    selection: SelectionDecision | Mapping[str, Any],
    *,
    specialist_id: str,
    folds: Sequence[Mapping[str, Any]],
) -> LocalEdgeEvidence:
    """Calculate exact-regime local edge from six complete specialist-filtered folds."""

    decision = validate_selection_decision(selection).to_dict()
    selected = decision["selected_candidate"]
    candidate_id = selected["canonical_candidate_id"] if selected is not None else None
    if specialist_id not in SPECS:
        raise RouterBundleError("local edge requires a known trading specialist")
    if selected is None or SPECS[specialist_id][0] != selected["family"]:
        raise RouterBundleError("local edge specialist does not match selected candidate")
    normalized = _local_folds(folds, decision)
    replay = _digest({"selection_decision_sha256": decision["decision_sha256"], "specialist_id": specialist_id, "folds": normalized})
    flat = [row for fold in normalized for row in fold["daily_local_net_mtm_usdc"]]
    total_trades = sum(row["trade_count"] for row in flat)
    gross_profit = math.fsum(row["gross_profit_usdc"] for row in flat)
    gross_loss = math.fsum(row["gross_loss_usdc"] for row in flat)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    fold_rates = [math.fsum(row["net_usdc"] for row in fold["daily_local_net_mtm_usdc"]) / 60.0 for fold in normalized]
    passed = total_trades >= MIN_TRADES and profit_factor >= MIN_PROFIT_FACTOR and all(value > 0 for value in fold_rates)
    basis = {
        "schema_version": LOCAL_EDGE_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION, "selection_decision_sha256": decision["decision_sha256"],
        "selected_candidate_id": candidate_id, "specialist_id": specialist_id,
        "required_structure": SPECS[specialist_id][1], "replay_sha256": replay,
        "folds": normalized, "day_count": len(flat), "total_trades": total_trades,
        "gross_profit_usdc": gross_profit, "gross_loss_usdc": gross_loss,
        "profit_factor": "Infinity" if math.isinf(profit_factor) else profit_factor,
        "fold_net_usdc_per_day": fold_rates, "passed": passed,
        "fixture_only": decision["fixture_only"], "outer_results_used": False, "safety": _SAFETY,
    }
    return validate_local_edge_evidence({**basis, "evidence_sha256": _digest(basis)}, selection=selection)


def validate_local_edge_evidence(
    value: LocalEdgeEvidence | Mapping[str, Any], *, selection: SelectionDecision | Mapping[str, Any]
) -> LocalEdgeEvidence:
    decision = validate_selection_decision(selection)
    root = value.to_dict() if isinstance(value, LocalEdgeEvidence) else dict(_mapping(value, "local_edge_evidence"))
    required = {"schema_version", "protocol_version", "contract_version", "selection_decision_sha256",
                "selected_candidate_id", "specialist_id", "required_structure", "replay_sha256", "folds",
                "day_count", "total_trades", "gross_profit_usdc", "gross_loss_usdc", "profit_factor",
                "fold_net_usdc_per_day", "passed", "fixture_only", "outer_results_used", "safety", "evidence_sha256"}
    if set(root) != required or root["schema_version"] != LOCAL_EDGE_SCHEMA_VERSION or root["protocol_version"] != PROTOCOL_VERSION or root["contract_version"] != CONTRACT_VERSION:
        raise RouterBundleError("local-edge fields or versions are invalid")
    selected = decision.to_dict()["selected_candidate"]
    if root["selection_decision_sha256"] != decision.decision_sha256 or selected is None:
        raise RouterBundleError("local edge is not bound to a selected candidate")
    if root["selected_candidate_id"] != selected["canonical_candidate_id"] or root["specialist_id"] not in SPECS or SPECS[root["specialist_id"]][0] != selected["family"]:
        raise RouterBundleError("local edge candidate/specialist identity mismatch")
    if root["required_structure"] != SPECS[root["specialist_id"]][1]:
        raise RouterBundleError("local edge structure mismatch")
    expected = build_local_edge_evidence_unvalidated(decision.to_dict(), root["specialist_id"], root["folds"])
    if root != expected:
        raise RouterBundleError("local edge differs from exact replay calculation")
    return LocalEdgeEvidence(_canonical({k: root[k] for k in root if k != "evidence_sha256"}), root["evidence_sha256"])


def route_specialist(
    selection: SelectionDecision | Mapping[str, Any],
    local_edge: LocalEdgeEvidence | Mapping[str, Any] | None,
    *,
    store: MultiTimeframeFeatureStore | Mapping[str, Any], binding: ContextParityBinding,
    feature_fit_state: FoldFeatureFitState | Mapping[str, Any],
    regime_fit_state: OpportunityRegimeFitState | Mapping[str, Any],
    assessment: OpportunityRegimeAssessment | Mapping[str, Any],
) -> RouterDecision:
    decision = validate_selection_decision(selection)
    validate_context_parity_binding(binding)
    feature_store = validate_feature_store_against_binding(store, binding)
    feature_state = validate_fold_feature_state(feature_fit_state, store=feature_store, binding=binding)
    regime_state = validate_opportunity_regime_fit_state(regime_fit_state, store=feature_store, binding=binding, feature_fit_state=feature_state)
    regime = validate_opportunity_regime_assessment(assessment, store=feature_store, binding=binding, feature_fit_state=feature_state, regime_fit_state=regime_state)
    payload = decision.to_dict(); assessment_payload = regime.to_dict()
    outcome, specialist_id, reason, edge_payload = NO_TRADE, NO_TRADE_SPECIALIST, "selection_is_no_trade", None
    selected = payload["selected_candidate"]
    if payload["outcome"] == CANDIDATE and selected is not None:
        matching = sorted(key for key, spec in SPECS.items() if spec[0] == selected["family"])
        if len(matching) != 1:
            reason = "selected_family_has_no_unique_specialist"
        elif local_edge is None:
            reason = "local_edge_evidence_missing"
        else:
            edge = validate_local_edge_evidence(local_edge, selection=decision); edge_payload = edge.to_dict()
            expected = matching[0]
            if edge_payload["specialist_id"] != expected:
                reason = "local_edge_specialist_mismatch"
            elif edge_payload["passed"] is not True:
                reason = "local_edge_gate_failed"
            elif assessment_payload["state"] != COMPLETE or assessment_payload["routing_allowed"] is not True:
                reason = "regime_requires_no_trade"
            elif assessment_payload["structure"] != SPECS[expected][1]:
                reason = "current_regime_does_not_match_local_edge"
            else:
                outcome, specialist_id, reason = SPECIALIST, expected, "local_edge_and_current_regime_confirmed"
    basis = {
        "schema_version": ROUTER_DECISION_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION, "outcome": outcome, "specialist_id": specialist_id,
        "reason": reason, "selection_decision_sha256": decision.decision_sha256,
        "local_edge_evidence_sha256": None if edge_payload is None else edge_payload["evidence_sha256"],
        "assessment_sha256": regime.assessment_sha256, "feature_store_sha256": feature_store.store_sha256,
        "feature_fit_state_sha256": feature_state.state_sha256, "regime_fit_state_sha256": regime_state.state_sha256,
        "context_identity_sha256": binding.context_identity_sha256, "max_open_lots": 1,
        "may_create_direction": False, "fixture_only": payload["fixture_only"],
        "transaction_eligible": False, "safety": _SAFETY,
    }
    return RouterDecision(_canonical(basis), _digest(basis))


def validate_router_decision(
    value: RouterDecision,
    selection: SelectionDecision | Mapping[str, Any],
    local_edge: LocalEdgeEvidence | Mapping[str, Any] | None,
    **dependencies: Any,
) -> RouterDecision:
    if not isinstance(value, RouterDecision):
        raise RouterBundleError("verified RouterDecision required")
    expected = route_specialist(selection, local_edge, **dependencies)
    if value.to_dict() != expected.to_dict():
        raise RouterBundleError("router decision differs from exact dependency replay")
    return value


def build_frozen_candidate_bundle(
    router: RouterDecision,
    selection: SelectionDecision | Mapping[str, Any],
    local_edge: LocalEdgeEvidence | Mapping[str, Any] | None,
    *,
    store: MultiTimeframeFeatureStore | Mapping[str, Any], binding: ContextParityBinding,
    feature_fit_state: FoldFeatureFitState | Mapping[str, Any],
    regime_fit_state: OpportunityRegimeFitState | Mapping[str, Any],
    assessment: OpportunityRegimeAssessment | Mapping[str, Any],
    as_of_utc: str, valid_from_utc: str, valid_until_utc: str,
    predecessor_bundle_sha256: str | None = None,
) -> FrozenCandidateBundle:
    validate_router_decision(
        router, selection, local_edge, store=store, binding=binding,
        feature_fit_state=feature_fit_state, regime_fit_state=regime_fit_state,
        assessment=assessment,
    )
    decision = validate_selection_decision(selection); payload = decision.to_dict()
    feature_store = validate_feature_store_against_binding(store, binding)
    feature_state = validate_fold_feature_state(feature_fit_state, store=feature_store, binding=binding)
    regime_state = validate_opportunity_regime_fit_state(regime_fit_state, store=feature_store, binding=binding, feature_fit_state=feature_state)
    regime = validate_opportunity_regime_assessment(assessment, store=feature_store, binding=binding, feature_fit_state=feature_state, regime_fit_state=regime_state)
    as_of, valid_from, valid_until = _validity(as_of_utc, valid_from_utc, valid_until_utc)
    predecessor = None if predecessor_bundle_sha256 is None else _sha(predecessor_bundle_sha256, "predecessor_bundle_sha256")
    selected = payload["selected_candidate"]
    if router.outcome == SPECIALIST:
        if selected is None:
            raise RouterBundleError("specialist route requires selected candidate")
        candidate = StrategyCandidate(selected["family"], dict(selected["params"]))
        specialist = build_specialist_bundle(router.to_dict()["specialist_id"], candidate)
    else:
        specialist = build_specialist_bundle(NO_TRADE_SPECIALIST, None)
    run = payload["frozen_pipeline_config"]["run_fingerprint"]
    basis = {
        "schema_version": FROZEN_BUNDLE_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION, "router_decision": router.to_dict(),
        "specialist_bundle": specialist.to_dict(),
        "scalar_parameters": None if selected is None else selected["params"],
        "selection_decision_sha256": decision.decision_sha256,
        "local_edge_evidence_sha256": None if local_edge is None else validate_local_edge_evidence(local_edge, selection=decision).evidence_sha256,
        "feature_store_identity": feature_store.identity_payload,
        "feature_fit_state": feature_state.to_dict(), "regime_fit_state": regime_state.to_dict(),
        "assessment_sha256": regime.assessment_sha256, "context_policy": binding.identity_payload(),
        "cost_model": run["cost_model"], "rotation_policy": _ROTATION_POLICY,
        "predecessor_bundle_sha256": predecessor,
        "validity": {"as_of_utc": as_of, "valid_from_utc": valid_from, "valid_until_utc": valid_until},
        "fixture_only": payload["fixture_only"],
        "research_simulation_routable": router.outcome == SPECIALIST and payload["fixture_only"] is False,
        "canonical_adoption_eligible": False, "safety": _SAFETY,
    }
    return FrozenCandidateBundle(_canonical(basis), _digest(basis))


def validate_frozen_candidate_bundle(bundle: FrozenCandidateBundle, *args: Any, **kwargs: Any) -> FrozenCandidateBundle:
    if not isinstance(bundle, FrozenCandidateBundle):
        raise RouterBundleError("verified FrozenCandidateBundle required")
    root = bundle.to_dict(); validity = root.get("validity", {})
    rebuilt = build_frozen_candidate_bundle(*args, as_of_utc=validity.get("as_of_utc"),
                                            valid_from_utc=validity.get("valid_from_utc"),
                                            valid_until_utc=validity.get("valid_until_utc"),
                                            predecessor_bundle_sha256=root.get("predecessor_bundle_sha256"), **kwargs)
    if root != rebuilt.to_dict():
        raise RouterBundleError("frozen candidate bundle differs from exact dependency replay")
    return bundle


def build_local_edge_evidence_unvalidated(decision: Mapping[str, Any], specialist_id: str, folds: Any) -> dict[str, Any]:
    normalized = _local_folds(folds, decision)
    replay_sha256 = _digest({"selection_decision_sha256": decision["decision_sha256"], "specialist_id": specialist_id, "folds": normalized})
    flat = [row for fold in normalized for row in fold["daily_local_net_mtm_usdc"]]
    total_trades = sum(row["trade_count"] for row in flat)
    gross_profit = math.fsum(row["gross_profit_usdc"] for row in flat)
    gross_loss = math.fsum(row["gross_loss_usdc"] for row in flat)
    pf = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)
    rates = [math.fsum(row["net_usdc"] for row in fold["daily_local_net_mtm_usdc"]) / 60.0 for fold in normalized]
    selected = decision["selected_candidate"]
    basis = {"schema_version": LOCAL_EDGE_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
             "contract_version": CONTRACT_VERSION, "selection_decision_sha256": decision["decision_sha256"],
             "selected_candidate_id": selected["canonical_candidate_id"], "specialist_id": specialist_id,
             "required_structure": SPECS[specialist_id][1], "replay_sha256": replay_sha256,
             "folds": normalized, "day_count": len(flat), "total_trades": total_trades,
             "gross_profit_usdc": gross_profit, "gross_loss_usdc": gross_loss,
             "profit_factor": "Infinity" if math.isinf(pf) else pf, "fold_net_usdc_per_day": rates,
             "passed": total_trades >= MIN_TRADES and pf >= MIN_PROFIT_FACTOR and all(value > 0 for value in rates),
             "fixture_only": decision["fixture_only"], "outer_results_used": False, "safety": _SAFETY}
    return {**basis, "evidence_sha256": _digest(basis)}


def _local_folds(raw: Any, decision: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 6:
        raise RouterBundleError("local edge requires exactly six folds")
    boundaries = decision["frozen_pipeline_config"]["fold_identity"]["plan"]["folds"]
    result = []
    for supplied, boundary in zip(raw, boundaries, strict=True):
        fold = dict(_mapping(supplied, "local_edge.fold"))
        allowed_keys = {"fold_index", "fold_id", "daily_local_net_mtm_usdc"}
        if set(fold) not in (allowed_keys, allowed_keys | {"fold_sha256"}) or fold["fold_index"] != boundary["fold_index"] or fold["fold_id"] != boundary["fold_id"]:
            raise RouterBundleError("local edge fold provenance mismatch")
        rows = fold["daily_local_net_mtm_usdc"]
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)) or len(rows) != 60:
            raise RouterBundleError("local edge fold requires exactly 60 daily rows")
        start = datetime.fromisoformat(boundary["validation_start_inclusive_utc"].replace("Z", "+00:00")).date()
        expected_days = [(start + timedelta(days=i)).isoformat() for i in range(60)]
        normalized = []
        for expected_day, item in zip(expected_days, rows, strict=True):
            row = dict(_mapping(item, "local_edge.daily_row"))
            if set(row) != {"day", "net_usdc", "gross_profit_usdc", "gross_loss_usdc", "trade_count"} or row["day"] != expected_day:
                raise RouterBundleError("local edge daily grid or fields are invalid")
            net = _number(row["net_usdc"], "net_usdc"); profit = _nonnegative(row["gross_profit_usdc"], "gross_profit_usdc")
            loss = _nonnegative(row["gross_loss_usdc"], "gross_loss_usdc"); trades = _nonnegative_int(row["trade_count"], "trade_count")
            if not math.isclose(net, profit - loss, rel_tol=0.0, abs_tol=1e-12):
                raise RouterBundleError("daily local net differs from gross profit minus gross loss")
            if (trades == 0) != (profit == 0.0 and loss == 0.0):
                raise RouterBundleError("daily local trade count contradicts gross PnL")
            normalized.append({"day": expected_day, "net_usdc": net, "gross_profit_usdc": profit, "gross_loss_usdc": loss, "trade_count": trades})
        basis = {"fold_index": fold["fold_index"], "fold_id": fold["fold_id"], "daily_local_net_mtm_usdc": normalized}
        if "fold_sha256" in fold and fold["fold_sha256"] != _digest(basis):
            raise RouterBundleError("local edge fold digest mismatch")
        result.append({**basis, "fold_sha256": _digest(basis)})
    return result


def _validity(as_of_raw: Any, valid_from_raw: Any, valid_until_raw: Any) -> tuple[str, str, str]:
    as_of = _utc(as_of_raw, "as_of_utc"); valid_from = _utc(valid_from_raw, "valid_from_utc"); valid_until = _utc(valid_until_raw, "valid_until_utc")
    if valid_from != as_of + timedelta(hours=24) or valid_until <= valid_from:
        raise RouterBundleError("bundle validity must be [as_of+24h, valid_until)")
    return (_utc_text(as_of), _utc_text(valid_from), _utc_text(valid_until))


def _utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str): raise RouterBundleError(f"{name} must be UTC text")
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc: raise RouterBundleError(f"{name} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0): raise RouterBundleError(f"{name} must be UTC")
    return parsed.astimezone(UTC)


def _utc_text(value: datetime) -> str: return value.isoformat(timespec="seconds").replace("+00:00", "Z")
def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping): raise RouterBundleError(f"{name} must be an object")
    return value
def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)): raise RouterBundleError(f"{name} must be finite")
    return float(value)
def _nonnegative(value: Any, name: str) -> float:
    result = _number(value, name)
    if result < 0: raise RouterBundleError(f"{name} must be nonnegative")
    return result
def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0: raise RouterBundleError(f"{name} must be a nonnegative integer")
    return value
def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value): raise RouterBundleError(f"{name} must be lowercase sha256")
    return value
def _canonical(value: Any) -> str: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
def _digest(value: Any) -> str: return hashlib.sha256(_canonical(value).encode()).hexdigest()


__all__ = ["CONTRACT_PATH", "CONTRACT_SCHEMA_VERSION", "CONTRACT_VERSION", "FROZEN_BUNDLE_SCHEMA_VERSION",
           "LOCAL_EDGE_SCHEMA_VERSION", "NO_TRADE", "ROUTER_DECISION_SCHEMA_VERSION", "SPECIALIST",
           "FrozenCandidateBundle", "LocalEdgeEvidence", "RouterBundleError", "RouterDecision",
           "build_frozen_candidate_bundle", "build_local_edge_evidence", "load_router_bundle_contract",
           "route_specialist", "validate_frozen_candidate_bundle", "validate_local_edge_evidence",
           "validate_router_decision"]
