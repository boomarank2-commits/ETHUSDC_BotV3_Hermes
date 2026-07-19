"""Task-28 current 730-day refit and Champion/Challenger/Cash envelope.

The module reuses the unchanged Task-15/22 single-origin path. Historical
process, quality-gate, and hindsight results are provenance only and are never
passed into candidate selection or routing.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3.boundaries import (
    MonthlyProcessBoundaryPlan,
    validate_monthly_process_boundary_plan,
)
from ethusdc_bot.protocol_v3.historical_diagnostics import (
    HistoricalDiagnostics,
    validate_historical_diagnostics,
)
from ethusdc_bot.protocol_v3.inner_selection import (
    CANDIDATE,
    _candidate_payload,
    validate_selection_decision,
)
from ethusdc_bot.protocol_v3.monthly_quality_gate import (
    MonthlyQualityGateReport,
    validate_monthly_quality_gate_report,
)
from ethusdc_bot.protocol_v3.outer_mtm_ledger import (
    OuterMtmLedger,
    validate_outer_mtm_ledger,
)
from ethusdc_bot.protocol_v3.outer_origins import (
    OuterOriginProcess,
    OuterOriginRequest,
    _validate_origin_envelope,
    run_outer_origin,
    validate_outer_origin_process,
)
from ethusdc_bot.protocol_v3.runtime_state import (
    build_outer_rotation_state,
    restore_outer_rotation_state,
)

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_current_refit_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_current_refit_contract_v1"
CONTRACT_VERSION: Final = (
    "protocol_v3_current_730_day_refit_champion_challenger_cash_v1"
)
REPORT_SCHEMA_VERSION: Final = "protocol_v3_current_refit_decision_v1"
CHAMPION: Final = "CHAMPION"
CHALLENGER: Final = "CHALLENGER"
CASH: Final = "CASH"
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "refit_policy": {
        "development_days": 730,
        "selection_entrypoint": "outer_origins.run_outer_origin",
        "selection_pipeline_must_be_unchanged": True,
        "target_anchor_is_current_origin_test_start": True,
        "valid_from_formula": "T+24h",
        "valid_until_formula": "next_monthly_anchor",
        "entry_enabled_at_formula": "max(valid_from,flat_time)",
        "deadline": "T+24h",
        "late_completion_may_not_activate_retroactively": True,
    },
    "decision_policy": {
        "choices": [CHAMPION, CHALLENGER, CASH],
        "cash_net_usdc_per_day": 0,
        "current_selection_and_router_only": True,
        "historical_outer_gate_hindsight_feedback_forbidden": True,
        "missing_champion_retest_is_fail_closed": True,
    },
    "evidence_policy": {
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "canonical_adoption_eligible": False,
        "manual_research_shadow_start_required": True,
        "manual_research_shadow_start_allowed": False,
        "sealed_final_holdout_used": False,
    },
    "safety": _SAFETY,
}


class CurrentRefitError(ValueError):
    """Raised when the current refit is late, incomplete, or inconsistent."""


@dataclass(frozen=True)
class CurrentRefitDecision:
    canonical_json: str
    report_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["report_sha256"] = self.report_sha256
        return value


def load_current_refit_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CurrentRefitError("current-refit contract is missing or invalid") from exc
    if value != _CANONICAL_CONTRACT:
        raise CurrentRefitError("current-refit contract is not canonical")
    return value


def build_current_refit_decision(
    *,
    historical_boundary_plan: MonthlyProcessBoundaryPlan,
    current_boundary_plan: MonthlyProcessBoundaryPlan,
    historical_outer_process: OuterOriginProcess,
    baseline_ledger: OuterMtmLedger,
    monthly_quality_report: MonthlyQualityGateReport,
    historical_diagnostics: HistoricalDiagnostics,
    current_request: OuterOriginRequest,
    requested_at_utc: datetime,
) -> CurrentRefitDecision:
    """Run one exact current origin and freeze a diagnostic deployment decision."""

    validate_monthly_process_boundary_plan(historical_boundary_plan)
    validate_monthly_process_boundary_plan(current_boundary_plan)
    process = validate_outer_origin_process(
        historical_outer_process,
        boundary_plan=historical_boundary_plan,
    ).to_dict()
    ledger = validate_outer_mtm_ledger(
        baseline_ledger,
        boundary_plan=historical_boundary_plan,
        outer_process=historical_outer_process,
    ).to_dict()
    gate = validate_monthly_quality_gate_report(monthly_quality_report).to_dict()
    diagnostics = validate_historical_diagnostics(historical_diagnostics).to_dict()
    _bind_prior_evidence(process, ledger, gate, diagnostics)

    target = historical_boundary_plan.process_end_exclusive
    origin = current_boundary_plan.origins[-1]
    if origin.test_start_inclusive != target:
        raise CurrentRefitError(
            "current plan does not start its final origin at the historical process end"
        )
    if (
        origin.training_start_inclusive != target - timedelta(days=730)
        or origin.training_end_exclusive != target
    ):
        raise CurrentRefitError("current refit window must be exactly [T-730,T)")
    requested = _utc(requested_at_utc, "requested_at_utc")
    if requested > origin.valid_from:
        raise CurrentRefitError(
            "current refit missed T+24h and may not activate retroactively"
        )
    if ledger["origin_ledgers"][-1]["ending_open_position_bundle_sha256"] is not None:
        raise CurrentRefitError(
            "historical process must be flat before the current refit"
        )

    predecessor = process["origins"][-1]["frozen_candidate_bundle"]
    predecessor_sha = _sha(
        predecessor["bundle_sha256"], "predecessor_bundle_sha256"
    )
    current_origin = run_outer_origin(
        origin,
        current_request,
        predecessor_bundle_sha256=predecessor_sha,
    )
    current_payload = current_origin.to_dict()
    bundle = current_payload["frozen_candidate_bundle"]
    if bundle["predecessor_bundle_sha256"] != predecessor_sha:
        raise CurrentRefitError("current bundle does not bind its predecessor")
    rotation = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=bundle["bundle_sha256"],
        previous_runtime=None,
    )
    rotation_payload = rotation.to_dict()
    choice = _pairwise_decision(predecessor, current_payload)
    selection = current_payload["selection_decision"]
    manifest = {
        "schema_version": "protocol_v3_current_refit_identity_manifest_v1",
        "target_anchor_utc": _utc_text(_midnight(target)),
        "training_start_inclusive": origin.training_start_inclusive.isoformat(),
        "training_end_exclusive": origin.training_end_exclusive.isoformat(),
        "valid_from_utc": _utc_text(origin.valid_from),
        "valid_until_utc": _utc_text(origin.valid_until),
        "requested_at_utc": _utc_text(requested),
        "historical_outer_process_sha256": process["process_sha256"],
        "historical_outer_ledger_sha256": ledger["ledger_sha256"],
        "historical_monthly_gate_sha256": gate["report_sha256"],
        "historical_diagnostics_sha256": diagnostics["report_sha256"],
        "predecessor_bundle_sha256": predecessor_sha,
        "current_origin_sha256": current_payload["origin_sha256"],
        "current_selection_decision_sha256": selection["decision_sha256"],
        "current_bundle_sha256": bundle["bundle_sha256"],
        "current_rotation_state_sha256": rotation_payload["state_sha256"],
        "current_run_fingerprint_sha256": selection["fingerprints"][
            "run_fingerprint_sha256"
        ],
        "current_pipeline_generation_id": selection["fingerprints"][
            "pipeline_generation_id"
        ],
        "current_training_window_sha256": selection["fingerprints"][
            "training_window_sha256"
        ],
        "current_fold_plan_sha256": selection["fingerprints"][
            "fold_plan_sha256"
        ],
        "current_context_identity_sha256": selection["fingerprints"][
            "context_identity_sha256"
        ],
        "current_cost_source_sha256": selection["fingerprints"][
            "cost_source_sha256"
        ],
        "current_quality_gate_source_sha256": selection["fingerprints"][
            "quality_gate_source_sha256"
        ],
        "current_trial_ledger_head_sha256": selection["fingerprints"][
            "trial_ledger_head_sha256"
        ],
        "current_development_support_sha256": selection["fingerprints"][
            "development_support_sha256"
        ],
        "current_derived_seed": selection["fingerprints"]["derived_seed"],
        "current_feature_store_identity": bundle["feature_store_identity"],
        "current_feature_fit_state": bundle["feature_fit_state"],
        "current_regime_fit_state": bundle["regime_fit_state"],
        "current_assessment_sha256": bundle["assessment_sha256"],
        "current_cost_model": bundle["cost_model"],
    }
    prior_status = {
        "monthly_quality_status": gate["status"],
        "robustness_passed": gate["robustness_passed"],
        "historically_hit": gate["historically_hit"],
        "historical_bootstrap_lower_bound": diagnostics[
            "historical_bootstrap_lower_bound"
        ],
        "freshness": "NOT_FRESH",
        "feedback_into_current_selection": False,
    }
    basis = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "identity_manifest": manifest,
        "identity_manifest_sha256": _digest(manifest),
        "current_origin": current_payload,
        "frozen_candidate_bundle": bundle,
        "outer_rotation_state": rotation_payload,
        "champion_challenger_cash_decision": choice,
        "prior_process_diagnostic_status": prior_status,
        "selection_input_forbidden_fields": [
            "outer_pnl",
            "outer_ranking",
            "historical_hindsight",
            "monthly_gate_result",
            "human_interpretation",
        ],
        "outer_or_hindsight_feedback_used": False,
        "deadline_met": True,
        "late_activation_allowed": False,
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "canonical_adoption_eligible": False,
        "manual_research_shadow_start_required": True,
        "manual_research_shadow_start_allowed": False,
        "sealed_final_holdout_used": False,
        "bot_start_allowed": False,
        "safety": _SAFETY,
    }
    return validate_current_refit_decision(
        CurrentRefitDecision(_canonical(basis), _digest(basis))
    )


def validate_current_refit_decision(
    value: CurrentRefitDecision | Mapping[str, Any],
    *,
    historical_boundary_plan: MonthlyProcessBoundaryPlan | None = None,
    current_boundary_plan: MonthlyProcessBoundaryPlan | None = None,
    historical_outer_process: OuterOriginProcess | None = None,
    baseline_ledger: OuterMtmLedger | None = None,
    monthly_quality_report: MonthlyQualityGateReport | None = None,
    historical_diagnostics: HistoricalDiagnostics | None = None,
    current_request: OuterOriginRequest | None = None,
    requested_at_utc: datetime | None = None,
) -> CurrentRefitDecision:
    root = (
        value.to_dict()
        if isinstance(value, CurrentRefitDecision)
        else dict(_mapping(value, "current_refit_decision"))
    )
    if not isinstance(value, CurrentRefitDecision):
        dependencies = (
            historical_boundary_plan,
            current_boundary_plan,
            historical_outer_process,
            baseline_ledger,
            monthly_quality_report,
            historical_diagnostics,
            current_request,
            requested_at_utc,
        )
        if any(item is None for item in dependencies):
            raise CurrentRefitError(
                "persisted current refit requires complete source replay"
            )
        expected = build_current_refit_decision(
            historical_boundary_plan=historical_boundary_plan,
            current_boundary_plan=current_boundary_plan,
            historical_outer_process=historical_outer_process,
            baseline_ledger=baseline_ledger,
            monthly_quality_report=monthly_quality_report,
            historical_diagnostics=historical_diagnostics,
            current_request=current_request,
            requested_at_utc=requested_at_utc,
        ).to_dict()
        if root != expected:
            raise CurrentRefitError(
                "persisted current refit differs from exact source replay"
            )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "identity_manifest",
        "identity_manifest_sha256",
        "current_origin",
        "frozen_candidate_bundle",
        "outer_rotation_state",
        "champion_challenger_cash_decision",
        "prior_process_diagnostic_status",
        "selection_input_forbidden_fields",
        "outer_or_hindsight_feedback_used",
        "deadline_met",
        "late_activation_allowed",
        "freshness",
        "diagnostic_only",
        "canonical_adoption_eligible",
        "manual_research_shadow_start_required",
        "manual_research_shadow_start_allowed",
        "sealed_final_holdout_used",
        "bot_start_allowed",
        "safety",
        "report_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != REPORT_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
    ):
        raise CurrentRefitError("current-refit fields or versions are invalid")
    manifest = dict(_mapping(root["identity_manifest"], "identity_manifest"))
    if root["identity_manifest_sha256"] != _digest(manifest):
        raise CurrentRefitError("current-refit identity manifest digest mismatch")
    target = date.fromisoformat(manifest["target_anchor_utc"][:10])
    from .boundaries import build_monthly_process_boundary_plan

    replay_plan = build_monthly_process_boundary_plan(
        date.fromisoformat(manifest["valid_until_utc"][:10])
    )
    origin = replay_plan.origins[-1]
    if origin.test_start_inclusive != target:
        raise CurrentRefitError("current-refit target and validity are inconsistent")
    current_origin = _validate_origin_envelope(root["current_origin"], origin)
    bundle = current_origin["frozen_candidate_bundle"]
    if root["frozen_candidate_bundle"] != bundle:
        raise CurrentRefitError("current-refit bundle differs from current origin")
    rotation = restore_outer_rotation_state(
        root["outer_rotation_state"], origin=origin
    ).to_dict()
    if (
        rotation["new_candidate_bundle_sha256"] != bundle["bundle_sha256"]
        or rotation["entry_enabled_at_utc"] != bundle["validity"]["valid_from_utc"]
    ):
        raise CurrentRefitError("rotation state and bundle validity mismatch")
    if manifest != _identity_manifest_from_root(root):
        raise CurrentRefitError("current-refit identity manifest is not canonical")
    expected_choice = _pairwise_decision(
        _predecessor_from_manifest(root), current_origin
    )
    if root["champion_challenger_cash_decision"] != expected_choice:
        raise CurrentRefitError("Champion/Challenger/Cash decision was manipulated")
    prior = root["prior_process_diagnostic_status"]
    if (
        not isinstance(prior, Mapping)
        or prior.get("freshness") != "NOT_FRESH"
        or prior.get("feedback_into_current_selection") is not False
    ):
        raise CurrentRefitError("prior process evidence may not feed selection")
    if root["selection_input_forbidden_fields"] != [
        "outer_pnl",
        "outer_ranking",
        "historical_hindsight",
        "monthly_gate_result",
        "human_interpretation",
    ]:
        raise CurrentRefitError("selection forbidden-field lock is invalid")
    if (
        root["outer_or_hindsight_feedback_used"] is not False
        or root["deadline_met"] is not True
        or root["late_activation_allowed"] is not False
        or root["freshness"] != "NOT_FRESH"
        or root["diagnostic_only"] is not True
        or root["canonical_adoption_eligible"] is not False
        or root["manual_research_shadow_start_required"] is not True
        or root["manual_research_shadow_start_allowed"] is not False
        or root["sealed_final_holdout_used"] is not False
        or root["bot_start_allowed"] is not False
        or root["safety"] != _SAFETY
    ):
        raise CurrentRefitError("current-refit safety, freshness, or scope lock failed")
    observed = _sha(root["report_sha256"], "report_sha256")
    basis = dict(root)
    basis.pop("report_sha256")
    if observed != _digest(basis):
        raise CurrentRefitError("current-refit report digest mismatch")
    return CurrentRefitDecision(_canonical(basis), observed)


def _bind_prior_evidence(
    process: Mapping[str, Any],
    ledger: Mapping[str, Any],
    gate: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
) -> None:
    if (
        gate["outer_process_sha256"] != process["process_sha256"]
        or gate["baseline_ledger_sha256"] != ledger["ledger_sha256"]
        or diagnostics["outer_process_sha256"] != process["process_sha256"]
        or diagnostics["outer_ledger_sha256"] != ledger["ledger_sha256"]
        or diagnostics["monthly_gate_report_sha256"] != gate["report_sha256"]
    ):
        raise CurrentRefitError(
            "historical process, ledger, gate, and diagnostics do not chain"
        )
    if (
        gate["freshness"] != "NOT_FRESH"
        or gate["diagnostic_only"] is not True
        or diagnostics["freshness"] != "NOT_FRESH"
        or diagnostics["diagnostic_only"] is not True
    ):
        raise CurrentRefitError("prior evidence must remain historical diagnostics")


def _pairwise_decision(
    predecessor_bundle: Mapping[str, Any],
    current_origin: Mapping[str, Any],
) -> dict[str, Any]:
    predecessor = dict(_mapping(predecessor_bundle, "predecessor_bundle"))
    current = dict(_mapping(current_origin, "current_origin"))
    selection = validate_selection_decision(current["selection_decision"]).to_dict()
    bundle = dict(_mapping(current["frozen_candidate_bundle"], "current_bundle"))
    champion_candidate = predecessor["specialist_bundle"]["base_candidate"]
    champion_id = _candidate_id(champion_candidate)
    selected = selection["selected_candidate"]
    selected_id = selected["canonical_candidate_id"] if selected is not None else None
    ranking = {
        row["canonical_candidate_id"]: row for row in selection["ranking_evidence"]
    }
    if champion_id is not None:
        tested = selection["frozen_pipeline_config"]["stage_candidate_ids"]["tested"]
        if champion_id not in tested:
            raise CurrentRefitError(
                "current inventory did not retest the incumbent Champion"
            )
    router_routable = (
        bundle["router_decision"]["outcome"] != "NO_TRADE"
        and bundle["research_simulation_routable"] is True
    )
    if selection["outcome"] != CANDIDATE or not router_routable:
        choice = CASH
        reason = (
            "current_selection_is_no_trade"
            if selection["outcome"] != CANDIDATE
            else "current_router_is_no_trade"
        )
        winner_id = None
        challenger_id = selected_id
    else:
        row = ranking.get(selected_id)
        if (
            row is None
            or row["quality_gate_passed"] is not True
            or row["development_dsr_passed"] is not True
            or row["development_pbo_passed"] is not True
            or row["development_beats_cash"] is not True
            or row["ranking_error"] is not None
        ):
            raise CurrentRefitError(
                "selected candidate lacks complete gate, DSR, PBO, or Cash evidence"
            )
        winner_id = selected_id
        if champion_id == selected_id:
            choice = CHAMPION
            challenger_id = None
            reason = "incumbent_champion_reselected_by_current_pipeline"
        else:
            choice = CHALLENGER
            challenger_id = selected_id
            reason = "current_challenger_out_ranked_champion_and_cash"
    basis = {
        "schema_version": "protocol_v3_champion_challenger_cash_decision_v1",
        "choice": choice,
        "reason": reason,
        "champion_candidate_id": champion_id,
        "challenger_candidate_id": challenger_id,
        "winner_candidate_id": winner_id,
        "cash_net_usdc_per_day": 0,
        "current_selection_outcome": selection["outcome"],
        "current_selected_candidate_id": selected_id,
        "current_selected_ranking_evidence": ranking.get(selected_id),
        "current_router_outcome": bundle["router_decision"]["outcome"],
        "current_bundle_sha256": bundle["bundle_sha256"],
        "predecessor_bundle_sha256": predecessor["bundle_sha256"],
        "outer_gate_or_hindsight_feedback_used": False,
    }
    return {**basis, "decision_sha256": _digest(basis)}


def _candidate_id(candidate: Any) -> str | None:
    if candidate is None:
        return None
    value = dict(_mapping(candidate, "base_candidate"))
    if set(value) != {"family", "params"}:
        raise CurrentRefitError("Champion candidate fields are invalid")
    payload = _candidate_payload(
        StrategyCandidate(value["family"], dict(value["params"]))
    )
    return payload["canonical_candidate_id"]


def _identity_manifest_from_root(root: Mapping[str, Any]) -> dict[str, Any]:
    current = root["current_origin"]
    selection = current["selection_decision"]
    bundle = root["frozen_candidate_bundle"]
    rotation = root["outer_rotation_state"]
    old = root["identity_manifest"]
    return {
        "schema_version": "protocol_v3_current_refit_identity_manifest_v1",
        "target_anchor_utc": old["target_anchor_utc"],
        "training_start_inclusive": current["training_start_inclusive"],
        "training_end_exclusive": current["training_end_exclusive"],
        "valid_from_utc": bundle["validity"]["valid_from_utc"],
        "valid_until_utc": bundle["validity"]["valid_until_utc"],
        "requested_at_utc": old["requested_at_utc"],
        "historical_outer_process_sha256": old[
            "historical_outer_process_sha256"
        ],
        "historical_outer_ledger_sha256": old[
            "historical_outer_ledger_sha256"
        ],
        "historical_monthly_gate_sha256": old[
            "historical_monthly_gate_sha256"
        ],
        "historical_diagnostics_sha256": old[
            "historical_diagnostics_sha256"
        ],
        "predecessor_bundle_sha256": bundle["predecessor_bundle_sha256"],
        "current_origin_sha256": current["origin_sha256"],
        "current_selection_decision_sha256": selection["decision_sha256"],
        "current_bundle_sha256": bundle["bundle_sha256"],
        "current_rotation_state_sha256": rotation["state_sha256"],
        "current_run_fingerprint_sha256": selection["fingerprints"][
            "run_fingerprint_sha256"
        ],
        "current_pipeline_generation_id": selection["fingerprints"][
            "pipeline_generation_id"
        ],
        "current_training_window_sha256": selection["fingerprints"][
            "training_window_sha256"
        ],
        "current_fold_plan_sha256": selection["fingerprints"][
            "fold_plan_sha256"
        ],
        "current_context_identity_sha256": selection["fingerprints"][
            "context_identity_sha256"
        ],
        "current_cost_source_sha256": selection["fingerprints"][
            "cost_source_sha256"
        ],
        "current_quality_gate_source_sha256": selection["fingerprints"][
            "quality_gate_source_sha256"
        ],
        "current_trial_ledger_head_sha256": selection["fingerprints"][
            "trial_ledger_head_sha256"
        ],
        "current_development_support_sha256": selection["fingerprints"][
            "development_support_sha256"
        ],
        "current_derived_seed": selection["fingerprints"]["derived_seed"],
        "current_feature_store_identity": bundle["feature_store_identity"],
        "current_feature_fit_state": bundle["feature_fit_state"],
        "current_regime_fit_state": bundle["regime_fit_state"],
        "current_assessment_sha256": bundle["assessment_sha256"],
        "current_cost_model": bundle["cost_model"],
    }


def _predecessor_from_manifest(root: Mapping[str, Any]) -> dict[str, Any]:
    choice = root["champion_challenger_cash_decision"]
    champion_id = choice["champion_candidate_id"]
    base_candidate = None
    if champion_id is not None:
        # The exact candidate body is not separately accepted. Reconstruct it from
        # the current tested inventory only when it is present there.
        evidence = root["current_origin"]["selection_decision"][
            "frozen_pipeline_config"
        ]["candidate_evidence"]
        matches = [
            row["candidate"]
            for row in evidence
            if row["candidate"]["canonical_candidate_id"] == champion_id
        ]
        if len(matches) != 1:
            raise CurrentRefitError("Champion candidate cannot be reconstructed")
        base_candidate = {
            "family": matches[0]["family"],
            "params": matches[0]["parameters"],
        }
    return {
        "bundle_sha256": root["identity_manifest"][
            "predecessor_bundle_sha256"
        ],
        "specialist_bundle": {"base_candidate": base_candidate},
    }


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CurrentRefitError(f"{name} must be an object")
    return value


def _midnight(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _utc(value: datetime, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise CurrentRefitError(f"{name} must be UTC")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _sha(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise CurrentRefitError(f"{name} must be lowercase sha256")
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
    "CASH",
    "CHALLENGER",
    "CHAMPION",
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "REPORT_SCHEMA_VERSION",
    "CurrentRefitDecision",
    "CurrentRefitError",
    "build_current_refit_decision",
    "load_current_refit_contract",
    "validate_current_refit_decision",
]
