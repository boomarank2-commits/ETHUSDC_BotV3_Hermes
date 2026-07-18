"""Stable public Protocol-v3 inner-selection API for Task 15."""
from __future__ import annotations

from typing import Any, Mapping

from . import inner_selection as _impl


def _selection_basis_fail_closed(window: Any, config: Any) -> dict[str, Any]:
    """Return typed NO_TRADE when candidate evidence is incomplete.

    The quality gate is the evidence validator. Ranking metrics are read only
    after that gate passes, so a missing or contradictory field cannot escape as
    KeyError/TypeError and cannot be mistaken for an eligible candidate.
    """

    w = window.to_dict()
    c = config.to_dict()
    if c["fold_identity"] != w["fold_identity"]:
        raise _impl.InnerSelectionError(
            "selection config and training window use different Task-14 plans"
        )
    for row in c["candidate_evidence"]:
        if row["training_window_sha256"] != window.window_sha256:
            raise _impl.InnerSelectionError(
                "candidate evidence belongs to a different training window"
            )

    support = c["development_support"]
    blockers: set[str] = set()
    if support["matrix"]["state"] != _impl.COMPLETE:
        blockers.add("TASK16_MATRIX_INSUFFICIENT_EVIDENCE")
    if support["pbo"]["state"] != _impl.COMPLETE:
        blockers.add("TASK17_PBO_INSUFFICIENT_EVIDENCE")
    if support["dsr"]["state"] != _impl.COMPLETE:
        blockers.add("TASK18_DSR_INSUFFICIENT_EVIDENCE")
    if not c["stage_candidate_ids"]["finalists"]:
        blockers.add("NO_FINALISTS")
    if (
        support["pbo"]["state"] == _impl.COMPLETE
        and support["pbo"]["value"] > _impl._MAX_PBO
    ):
        blockers.add("DEVELOPMENT_PBO_GATE_FAILED")

    eligible: list[tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]] = []
    ranking_rows: list[dict[str, Any]] = []
    candidate_rejections: set[str] = set()
    dsr_values = (
        support["dsr"]["value"]
        if support["dsr"]["state"] == _impl.COMPLETE
        else {}
    )

    for row in c["candidate_evidence"]:
        candidate_id = row["candidate"]["canonical_candidate_id"]
        gate = _impl.evaluate_quality_gates(
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
            and _impl.math.isfinite(float(dsr_score))
            and float(dsr_score) >= _impl._MIN_DSR
        )

        rank: dict[str, Any] | None = None
        ranking_error: str | None = None
        if gate_passed:
            try:
                rank = _impl._ranking_row(row)
            except (KeyError, TypeError, ValueError, _impl.InnerSelectionError):
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
            "quality_gate_report_sha256": _impl._digest(gate),
            "ranking_error": ranking_error,
        }
        if rank is not None:
            ranking_row.update(rank)
        ranking_rows.append(ranking_row)

        if not gate_passed:
            candidate_rejections.add(
                f"QUALITY_GATE_NOT_PASSED:{candidate_id}:{gate['status']}"
            )
        if support["dsr"]["state"] == _impl.COMPLETE and not dsr_passed:
            candidate_rejections.add(
                f"DEVELOPMENT_DSR_GATE_FAILED:{candidate_id}"
            )
        if gate_passed and rank is not None and dsr_passed:
            eligible.append((_impl._rank_key(rank), row["candidate"], gate))

    ranking_rows.sort(key=lambda row: row["canonical_candidate_id"])
    selected: dict[str, Any] | None = None
    outcome = _impl.NO_TRADE
    eligible_ids = sorted(row[1]["canonical_candidate_id"] for row in eligible)
    fixture_only = support["mode"] == _impl.SYNTHETIC_TEST_FIXTURE
    if not blockers and eligible:
        eligible.sort(key=lambda item: item[0])
        selected = dict(eligible[0][1])
        outcome = _impl.CANDIDATE
    elif not eligible and c["candidate_evidence"]:
        blockers.update(candidate_rejections)
        blockers.add("NO_CANDIDATE_PASSED_ALL_DEVELOPMENT_GATES")

    return {
        "schema_version": _impl.SELECTION_DECISION_SCHEMA,
        "protocol_version": _impl.PROTOCOL_VERSION,
        "contract_version": _impl.INNER_SELECTION_CONTRACT_VERSION,
        "outcome": outcome,
        "fixture_only": fixture_only,
        "training_window": w,
        "frozen_pipeline_config": c,
        "selected_candidate": selected,
        "eligible_candidate_ids": eligible_ids,
        "ranking_evidence": ranking_rows,
        "blockers": sorted(blockers),
        "fingerprints": _impl._selection_fingerprints(window, config),
        "safety": _impl._SAFETY,
    }


# Patch the exact implementation module used by select_candidate and by
# validate_selection_decision. This keeps one canonical decision recomputation
# path while the stable public facade enforces typed fail-closed evidence.
_impl._selection_basis = _selection_basis_fail_closed

from .inner_selection import (  # noqa: E402
    CANDIDATE,
    CANDIDATE_EVIDENCE_SCHEMA,
    CANDIDATE_SELECTION_IDENTITY_SCHEMA,
    COMPLETE,
    DEVELOPMENT_EVIDENCE_SCHEMA,
    FROZEN_CONFIG_SCHEMA,
    INNER_SELECTION_CONTRACT_PATH,
    INNER_SELECTION_CONTRACT_SCHEMA,
    INNER_SELECTION_CONTRACT_VERSION,
    INSUFFICIENT_EVIDENCE,
    NO_TRADE,
    PRODUCTION,
    SELECTION_DECISION_SCHEMA,
    SYNTHETIC_TEST_FIXTURE,
    TRAINING_WINDOW_SCHEMA,
    CandidateSelectionEvidence,
    DevelopmentSupport,
    FrozenSelectionConfig,
    InnerSelectionError,
    SelectionDecision,
    SelectionTimestampSpy,
    SelectionTrainingWindow,
    build_candidate_selection_evidence,
    build_candidate_selection_identity_payload,
    build_frozen_selection_config,
    build_incomplete_development_support,
    build_selection_training_window,
    build_synthetic_complete_development_support,
    load_inner_selection_contract,
    select_candidate,
    validate_candidate_selection_evidence,
    validate_candidate_selection_identity_payload,
    validate_development_support,
    validate_frozen_selection_config,
    validate_inner_selection_contract,
    validate_selection_decision,
    validate_selection_training_window,
)

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
    "build_selection_training_window",
    "build_synthetic_complete_development_support",
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
