"""Full cross-cycle selection for one real Protocol-v3 monthly origin.

The existing production inner-cycle runner evaluates one cycle at a time.
This module is the mandatory convergence point: it rebuilds one Task-16
matrix from every tested profile in all eight cycles, recomputes Task-17 PBO
and Task-18 DSR at the current permanent-ledger head, and only then accepts
Task-15 decisions that bind that exact evidence.

Missing Task-15 quality evidence is a typed ``NO_TRADE`` blocker.  Per-cycle
net profit, a last-cycle shortcut, or stale per-cycle PBO/DSR can never select
an origin candidate.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Final

from .candidate_matrix import (
    build_candidate_daily_matrix,
    validate_candidate_daily_matrix,
)
from .dsr_batch import calculate_dsr_batch_evidence
from .inner_folds import InnerFoldPlan, validate_inner_fold_plan
from .inner_selection import (
    CANDIDATE,
    build_dsr_batch_development_support,
    build_frozen_selection_config,
    build_selection_training_window,
    lexicographic_candidate_rank_key,
    select_candidate,
    validate_selection_decision,
)
from .pbo import calculate_pbo, validate_pbo_evidence
from .pipeline import PreRunManifest, build_pipeline_generation
from .production_inner_cycle import (
    ProductionInnerCycleResult,
    validate_production_inner_cycle_result,
)
from .run_identity import RunFingerprint, validate_run_fingerprint
from .trial_ledger import TrialLedgerSnapshot, read_trial_ledger

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_production_origin_selection_contract.json"
)
CONTRACT_SCHEMA_VERSION: Final = (
    "protocol_v3_production_origin_selection_contract_v1"
)
CONTRACT_VERSION: Final = "protocol_v3_full_cross_cycle_origin_selection_v2"
RESULT_SCHEMA_VERSION: Final = (
    "protocol_v3_production_origin_selection_result_v2"
)
MAX_CYCLES_REACHED: Final = "max_cycles_reached"
READY_CANDIDATE: Final = "READY_CANDIDATE"
NO_TRADE: Final = "NO_TRADE"
_CYCLES: Final = tuple(range(1, 9))
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_PIPELINE = re.compile(r"^protocol_v3_pipeline_sha256:[0-9a-f]{64}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "outer_results": "forbidden",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_DECISION_BINDING_CACHE: dict[str, dict[str, Any]] = {}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "input_policy": {
        "origin_count": 1,
        "required_cycle_indexes": list(_CYCLES),
        "terminal_stop_reason": MAX_CYCLES_REACHED,
        "same_code_commit_required": True,
        "same_pipeline_generation_required": True,
        "same_fold_plan_required": True,
        "current_permanent_trial_ledger_required": True,
        "every_cycle_artifact_digest_validated": True,
    },
    "recomputation_policy": {
        "all_tested_profiles_from_all_cycles_retained": True,
        "candidate_matrix_rebuilt_at_current_ledger_head": True,
        "pbo_recomputed_from_full_origin_matrix": True,
        "dsr_recomputed_for_every_profile": True,
        "cache_reuse_is_not_independent_trial": True,
        "stored_per_cycle_pbo_or_dsr_may_select": False,
    },
    "selection_policy": {
        "task15_decision_recomputed_for_every_cycle": True,
        "task15_decision_must_bind_recomputed_matrix_pbo_dsr": True,
        "caller_supplied_task15_decisions_allowed": False,
        "only_candidate_outcomes_may_compete": True,
        "ranking_source": "protocol_v3_lexicographic_inner_ranking_v1",
        "target_usdc_per_day_used": False,
        "no_gate_passing_candidate_result": NO_TRADE,
    },
    "artifact_policy": {
        "full_task15_cycle_decisions_embedded": True,
        "full_task15_cycle_decisions_validated": True,
        "task15_decision_encoding": "gzip_base64_canonical_json_v1",
        "full_source_cycle_results_embedded": False,
        "source_result_digests_retained": True,
        "dsr_summaries_embedded": True,
        "full_dsr_identity_repetition_forbidden": True,
        "write_is_create_only": True,
    },
    "safety": _SAFETY,
}


class ProductionOriginSelectionError(ValueError):
    """Raised when cross-cycle production evidence is incomplete or mixed."""


@dataclass(frozen=True)
class ProductionOriginSelectionResult:
    canonical_json: str
    result_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["result_sha256"] = self.result_sha256
        return payload


def load_production_origin_selection_contract(
    repo_root: str | Path,
) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        payload = _strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProductionOriginSelectionError(
            "production origin-selection contract is missing or invalid"
        ) from exc
    if payload != _CANONICAL_CONTRACT:
        raise ProductionOriginSelectionError(
            "production origin-selection contract is not canonical"
        )
    return payload


def build_production_origin_selection(
    *,
    repo_root: str | Path,
    fold_plan: InnerFoldPlan | Mapping[str, Any],
    trial_ledger: TrialLedgerSnapshot,
    cycle_results: Sequence[
        ProductionInnerCycleResult | Mapping[str, Any]
    ],
    pre_run_manifest: PreRunManifest | Mapping[str, Any],
    run_fingerprint: RunFingerprint | Mapping[str, Any],
    code_commit: str,
    terminal_stop_reason: str = MAX_CYCLES_REACHED,
) -> ProductionOriginSelectionResult:
    """Recompute complete origin evidence and select only from Task-15 output."""

    repo = Path(repo_root).resolve(strict=True)
    load_production_origin_selection_contract(repo)
    plan = validate_inner_fold_plan(fold_plan)
    ledger = _current_ledger(trial_ledger)
    commit = _commit(code_commit)
    if terminal_stop_reason != MAX_CYCLES_REACHED:
        raise ProductionOriginSelectionError(
            "only the pre-registered max-cycles terminal path is supported"
        )
    pipeline = build_pipeline_generation(repo)
    _validate_current_run_fingerprint(
        run_fingerprint,
        repo_root=repo,
        ledger=ledger,
        pipeline_generation_id=pipeline.generation_id,
        code_commit=commit,
    )
    rows = _validated_cycle_rows(
        cycle_results,
        plan=plan,
        pipeline_generation_id=pipeline.generation_id,
        code_commit=commit,
    )
    origin = rows[0]["origin_index"]
    matrix = build_candidate_daily_matrix(
        fold_plan=plan,
        origin_index=origin,
        cycles=[_matrix_cycle_input(row["matrix"]) for row in rows],
        trial_ledger=ledger,
    )
    pbo = calculate_pbo(matrix)
    matrix_payload = matrix.to_dict()
    pbo_payload = pbo.to_dict()
    decisions = {}
    dsr_summaries = []
    support_summaries = []
    for cycle in matrix_payload["cycles"]:
        dsr_batch = calculate_dsr_batch_evidence(
            pbo_evidence=pbo,
            cycle_index=cycle["cycle_index"],
            trial_ledger=ledger,
        )
        support = build_dsr_batch_development_support(
            dsr_batch,
            trial_ledger=ledger,
        )
        support_summaries.append(
            _support_summary(cycle["cycle_index"], support.to_dict())
        )
        batch_payload = dsr_batch.to_dict()
        dsr_summaries.extend(
            _dsr_batch_summary(
                row,
                batch_payload["shared_statistics"],
            )
            for row in batch_payload["profiles"]
        )
        source = next(
            row for row in rows if row["cycle_index"] == cycle["cycle_index"]
        )
        decisions[cycle["cycle_index"]] = _build_cycle_decision(
            source,
            plan=plan,
            origin_index=origin,
            support=support,
            pre_run_manifest=pre_run_manifest,
            run_fingerprint=run_fingerprint,
        )
    blockers: list[str] = []
    ranked = []
    decision_archives = []
    decision_bindings = []
    decision_summaries = []
    for cycle_index, decision in sorted(decisions.items()):
        payload = validate_selection_decision(decision).to_dict()
        decision_archives.append(_archive_decision(cycle_index, payload))
        decision_bindings.append(_decision_binding(cycle_index, payload))
        selected = payload["selected_candidate"]
        ranking = None
        if payload["outcome"] == CANDIDATE and selected is not None:
            candidate_id = selected["canonical_candidate_id"]
            matches = [
                row
                for row in payload["ranking_evidence"]
                if row["canonical_candidate_id"] == candidate_id
            ]
            if len(matches) != 1:
                raise ProductionOriginSelectionError(
                    "Task-15 selected candidate lacks one ranking row"
                )
            ranking = matches[0]
            if not (
                ranking["quality_gate_passed"] is True
                and ranking["development_dsr_passed"] is True
                and ranking["development_pbo_passed"] is True
                and ranking["development_beats_cash"] is True
                and ranking["ranking_error"] is None
            ):
                raise ProductionOriginSelectionError(
                    "Task-15 candidate did not pass every development gate"
                )
            ranked.append(
                (
                    lexicographic_candidate_rank_key(ranking),
                    cycle_index,
                    selected,
                    ranking,
                    decision,
                )
            )
        decision_summaries.append(_decision_summary(cycle_index, payload))

    selected_candidate = None
    selected_ranking = None
    selected_cycle_index = None
    selected_decision_id = None
    if ranked:
        ranked.sort(key=lambda item: (item[0], item[1]))
        _, selected_cycle_index, selected_candidate, selected_ranking, chosen = (
            ranked[0]
        )
        selected_decision_id = chosen.decision_id
        state = READY_CANDIDATE
        outcome = CANDIDATE
    else:
        state = NO_TRADE
        outcome = NO_TRADE

    basis = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "pipeline_generation_id": pipeline.generation_id,
        "code_commit": commit,
        "origin_index": origin,
        "terminal_stop_reason": terminal_stop_reason,
        "source_cycle_result_digests": [
            {
                "cycle_index": row["cycle_index"],
                "result_sha256": row["result_sha256"],
            }
            for row in rows
        ],
        "matrix": matrix_payload,
        "pbo_summary": _pbo_summary(pbo_payload),
        "dsr_summaries": sorted(
            dsr_summaries,
            key=lambda row: row["profile_id"],
        ),
        "development_support_summaries": support_summaries,
        "cycle_decision_archives": decision_archives,
        "cycle_decision_bindings": decision_bindings,
        "cycle_decision_summaries": decision_summaries,
        "state": state,
        "outcome": outcome,
        "selected_cycle_index": selected_cycle_index,
        "selected_decision_id": selected_decision_id,
        "selected_candidate": selected_candidate,
        "selected_ranking_evidence": selected_ranking,
        "blockers": blockers,
        "target_usdc_per_day_used_for_selection": False,
        "trial_ledger_head_sha256": ledger.status.head_sha256,
        "safety": dict(_SAFETY),
    }
    return validate_production_origin_selection(
        ProductionOriginSelectionResult(_canonical(basis), _digest(basis))
    )


def validate_production_origin_selection(
    value: ProductionOriginSelectionResult | Mapping[str, Any],
) -> ProductionOriginSelectionResult:
    root = (
        value.to_dict()
        if isinstance(value, ProductionOriginSelectionResult)
        else dict(_mapping(value, "production_origin_selection"))
    )
    expected = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "pipeline_generation_id",
        "code_commit",
        "origin_index",
        "terminal_stop_reason",
        "source_cycle_result_digests",
        "matrix",
        "pbo_summary",
        "dsr_summaries",
        "development_support_summaries",
        "cycle_decision_archives",
        "cycle_decision_bindings",
        "cycle_decision_summaries",
        "state",
        "outcome",
        "selected_cycle_index",
        "selected_decision_id",
        "selected_candidate",
        "selected_ranking_evidence",
        "blockers",
        "target_usdc_per_day_used_for_selection",
        "trial_ledger_head_sha256",
        "safety",
        "result_sha256",
    }
    if set(root) != expected:
        raise ProductionOriginSelectionError(
            "production origin-selection fields are missing or unexpected"
        )
    if (
        root["schema_version"] != RESULT_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
        or root["terminal_stop_reason"] != MAX_CYCLES_REACHED
        or root["safety"] != _SAFETY
        or root["target_usdc_per_day_used_for_selection"] is not False
        or not _PIPELINE.fullmatch(str(root["pipeline_generation_id"]))
        or not _COMMIT.fullmatch(str(root["code_commit"]))
    ):
        raise ProductionOriginSelectionError(
            "production origin-selection contract binding is invalid"
        )
    origin = _positive(root["origin_index"], "origin_index")
    sources = root["source_cycle_result_digests"]
    if not isinstance(sources, list) or [
        row.get("cycle_index") for row in sources if isinstance(row, Mapping)
    ] != list(_CYCLES):
        raise ProductionOriginSelectionError(
            "production origin-selection requires cycles 1..8"
        )
    if any(
        set(row) != {"cycle_index", "result_sha256"}
        or not _SHA.fullmatch(str(row["result_sha256"]))
        for row in sources
    ):
        raise ProductionOriginSelectionError(
            "source cycle digests are invalid"
        )
    matrix = validate_candidate_daily_matrix(root["matrix"]).to_dict()
    if (
        matrix["origin_index"] != origin
        or [row["cycle_index"] for row in matrix["cycles"]] != list(_CYCLES)
        or matrix["profile_count"] != 96
        or matrix["trial_ledger_head_sha256"]
        != root["trial_ledger_head_sha256"]
    ):
        raise ProductionOriginSelectionError(
            "full cross-cycle matrix is incomplete or stale"
        )
    pbo = _mapping(root["pbo_summary"], "pbo_summary")
    if (
        pbo.get("matrix_sha256") != matrix["matrix_sha256"]
        or not _SHA.fullmatch(str(pbo.get("evidence_sha256")))
    ):
        raise ProductionOriginSelectionError(
            "PBO summary does not bind the full matrix"
        )
    dsr = root["dsr_summaries"]
    supports = root["development_support_summaries"]
    expected_profiles = {
        profile["profile_id"]
        for cycle in matrix["cycles"]
        for profile in cycle["profiles"]
    }
    if (
        not isinstance(dsr, list)
        or len(dsr) != 96
        or {row.get("profile_id") for row in dsr} != expected_profiles
        or any(
            not _SHA.fullmatch(str(row.get("evidence_sha256")))
            or row.get("state") not in {
                "COMPLETE",
                "INSUFFICIENT_EVIDENCE",
                "INSUFFICIENT_TRIAL_HISTORY",
            }
            for row in dsr
        )
        or not isinstance(supports, list)
        or [row.get("cycle_index") for row in supports] != list(_CYCLES)
        or any(
            row.get("matrix_state") != "COMPLETE"
            or row.get("pbo_state") not in {
                "COMPLETE",
                "INSUFFICIENT_EVIDENCE",
            }
            or row.get("dsr_state") not in {
                "COMPLETE",
                "INSUFFICIENT_EVIDENCE",
            }
            or not _SHA.fullmatch(str(row.get("support_sha256")))
            for row in supports
        )
    ):
        raise ProductionOriginSelectionError(
            "DSR or development-support inventory is incomplete"
        )
    if not _SHA.fullmatch(str(root["trial_ledger_head_sha256"])):
        raise ProductionOriginSelectionError(
            "trial ledger head is invalid"
        )
    state = root["state"]
    outcome = root["outcome"]
    blockers = root["blockers"]
    if not isinstance(blockers, list) or any(
        not isinstance(item, str) or not item for item in blockers
    ):
        raise ProductionOriginSelectionError("blockers are invalid")
    archives = root["cycle_decision_archives"]
    if not isinstance(archives, list) or len(archives) != 8:
        raise ProductionOriginSelectionError(
            "exactly eight full Task-15 decision archives are required"
        )
    try:
        validated_bindings = [
            _read_decision_archive(row, expected_cycle=cycle)
            for cycle, row in zip(_CYCLES, archives, strict=True)
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionOriginSelectionError(
            "full Task-15 decision archive is invalid"
        ) from exc
    bindings = root["cycle_decision_bindings"]
    expected_bindings = [
        dict(binding) for binding in validated_bindings
    ]
    if bindings != expected_bindings:
        raise ProductionOriginSelectionError(
            "Task-15 decision bindings differ from full archives"
        )
    full_decision_cycles = [
        row["cycle_index"] for row in validated_bindings
    ]
    if full_decision_cycles != list(_CYCLES):
        raise ProductionOriginSelectionError(
            "full Task-15 decisions must be ordered cycles 1..8"
        )
    for cycle_index, binding in zip(
        _CYCLES, validated_bindings, strict=True
    ):
        matrix_cycle = matrix["cycles"][cycle_index - 1]
        if (
            binding["origin_index"] != origin
            or binding["pipeline_generation_id"]
            != root["pipeline_generation_id"]
            or binding["trial_ledger_head_sha256"]
            != root["trial_ledger_head_sha256"]
            or binding["fold_plan_sha256"]
            != matrix["fold_identity"]["plan_sha256"]
            or binding["code_commit"] != root["code_commit"]
            or binding["stage_candidate_ids"]["tested"]
            != matrix_cycle["tested_candidate_ids"]
            or binding["stage_candidate_ids"]["walk_forward"]
            != matrix_cycle["promoted_candidate_ids"]
            or binding["stage_candidate_ids"]["finalists"]
            != matrix_cycle["finalist_candidate_ids"]
            or binding["matrix_evidence_sha256"] != matrix["matrix_sha256"]
            or binding["development_support_sha256"]
            != supports[cycle_index - 1]["support_sha256"]
        ):
            raise ProductionOriginSelectionError(
                "Task-15 decision does not bind the full origin evidence"
            )
        if (
            binding["pbo_state"] == "COMPLETE"
            and binding["pbo_evidence_sha256"]
            != pbo["evidence_sha256"]
        ):
            raise ProductionOriginSelectionError(
                "Task-15 decision does not bind the recomputed PBO"
            )

    decisions = root["cycle_decision_summaries"]
    if not isinstance(decisions, list):
        raise ProductionOriginSelectionError(
            "cycle decision summaries must be a list"
        )
    decision_cycles = [
        row.get("cycle_index") for row in decisions if isinstance(row, Mapping)
    ]
    if (
        len(decision_cycles) != len(decisions)
        or decision_cycles != sorted(set(decision_cycles))
        or any(cycle not in _CYCLES for cycle in decision_cycles)
        or decisions
        != [
            _summary_from_binding(binding)
            for binding in validated_bindings
        ]
    ):
        raise ProductionOriginSelectionError(
            "cycle decision summaries differ from full Task-15 decisions"
        )
    missing_decisions = [cycle for cycle in _CYCLES if cycle not in decision_cycles]
    ranked_decisions = []
    for cycle_index, binding in zip(
        _CYCLES, validated_bindings, strict=True
    ):
        selected = binding["selected_candidate"]
        if binding["outcome"] == CANDIDATE and selected is not None:
            selected_id = selected["canonical_candidate_id"]
            ranking = binding["ranking_evidence"]
            ranked_decisions.append(
                (
                    lexicographic_candidate_rank_key(ranking),
                    cycle_index,
                    binding,
                )
            )
    ranked_decisions.sort(key=lambda item: (item[0], item[1]))
    if state == READY_CANDIDATE:
        if (
            outcome != CANDIDATE
            or blockers
            or missing_decisions
            or not ranked_decisions
            or root["selected_cycle_index"] not in _CYCLES
            or root["selected_candidate"] is None
            or root["selected_ranking_evidence"] is None
        ):
            raise ProductionOriginSelectionError(
                "ready origin candidate is incomplete"
            )
        expected_cycle = ranked_decisions[0][1]
        selected_binding = ranked_decisions[0][2]
        selected_id = root["selected_candidate"]["canonical_candidate_id"]
        if (
            root["selected_cycle_index"] != expected_cycle
            or selected_binding["decision_id"]
            != root["selected_decision_id"]
            or selected_binding["selected_candidate"]
            != root["selected_candidate"]
            or selected_binding["selected_candidate_id"] != selected_id
            or selected_binding["ranking_evidence"]
            != root["selected_ranking_evidence"]
        ):
            raise ProductionOriginSelectionError(
                "selected origin candidate differs from its Task-15 decision"
            )
    elif state == NO_TRADE:
        if (
            outcome != NO_TRADE
            or blockers
            or missing_decisions
            or root["selected_cycle_index"] is not None
            or root["selected_decision_id"] is not None
            or root["selected_candidate"] is not None
            or root["selected_ranking_evidence"] is not None
            or any(
                binding["outcome"] != NO_TRADE
                for binding in validated_bindings
            )
        ):
            raise ProductionOriginSelectionError(
                "complete NO_TRADE selection is inconsistent"
            )
    else:
        raise ProductionOriginSelectionError(
            "origin-selection state is invalid"
        )
    observed = root.pop("result_sha256")
    if observed != _digest(root):
        raise ProductionOriginSelectionError(
            "production origin-selection digest mismatch"
        )
    return ProductionOriginSelectionResult(_canonical(root), observed)


def write_production_origin_selection(
    value: ProductionOriginSelectionResult | Mapping[str, Any],
    path: str | Path,
) -> Path:
    result = validate_production_origin_selection(value)
    target = Path(path)
    if not target.is_absolute():
        raise ProductionOriginSelectionError(
            "origin-selection output path must be absolute"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical(result.to_dict()) + "\n")
    except FileExistsError as exc:
        raise ProductionOriginSelectionError(
            "production origin-selection result is create-only"
        ) from exc
    return target


def _validated_cycle_rows(
    values: Sequence[ProductionInnerCycleResult | Mapping[str, Any]],
    *,
    plan: InnerFoldPlan,
    pipeline_generation_id: str,
    code_commit: str,
) -> list[dict[str, Any]]:
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes))
        or len(values) != len(_CYCLES)
    ):
        raise ProductionOriginSelectionError(
            "exactly eight production cycle results are required"
        )
    rows = [
        validate_production_inner_cycle_result(value).to_dict()
        for value in values
    ]
    rows.sort(key=lambda row: row["cycle_index"])
    if [row["cycle_index"] for row in rows] != list(_CYCLES):
        raise ProductionOriginSelectionError(
            "production cycle indexes must be exactly 1..8"
        )
    origins = {row["origin_index"] for row in rows}
    for row in rows:
        matrix = validate_candidate_daily_matrix(row["matrix"]).to_dict()
        validate_pbo_evidence(row["pbo"])
        if (
            row["pipeline_generation_id"] != pipeline_generation_id
            or row["code_commit"] != code_commit
            or row["fold_plan_sha256"] != plan.plan_sha256
            or len(matrix["cycles"]) != 1
            or matrix["cycles"][0]["cycle_index"] != row["cycle_index"]
            or matrix["origin_index"] != row["origin_index"]
            or matrix["profile_count"] != 12
            or sorted(
                item["candidate_id"]
                for item in row["candidate_summaries"]
            )
            != matrix["cycles"][0]["tested_candidate_ids"]
        ):
            raise ProductionOriginSelectionError(
                "production cycle artifacts mix identity or incomplete evidence"
            )
    if len(origins) != 1:
        raise ProductionOriginSelectionError(
            "production cycle artifacts belong to different origins"
        )
    return rows


def _matrix_cycle_input(matrix: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_candidate_daily_matrix(matrix).to_dict()
    cycle = validated["cycles"][0]
    return {
        "cycle_index": cycle["cycle_index"],
        "tested_candidate_ids": cycle["tested_candidate_ids"],
        "promoted_candidate_ids": cycle["promoted_candidate_ids"],
        "finalist_candidate_ids": cycle["finalist_candidate_ids"],
        "profiles": [
            {
                "candidate_id": profile["candidate_id"],
                "trial_id": profile["trial_id"],
                "cache_reuse": profile["cache_reuse"],
                "folds": [
                    {
                        "fold_index": fold["fold_index"],
                        "fold_id": fold["fold_id"],
                        "daily_net_mtm_usdc": fold["daily_net_mtm_usdc"],
                    }
                    for fold in profile["folds"]
                ],
            }
            for profile in cycle["profiles"]
        ],
    }


def _build_cycle_decision(
    row: Mapping[str, Any],
    *,
    plan: InnerFoldPlan,
    origin_index: int,
    support: Any,
    pre_run_manifest: PreRunManifest | Mapping[str, Any],
    run_fingerprint: RunFingerprint | Mapping[str, Any],
) -> Any:
    window = build_selection_training_window(plan)
    cycle = row["cycle_index"]
    matrix_cycle = validate_candidate_daily_matrix(
        row["matrix"]
    ).to_dict()["cycles"][0]
    try:
        config = build_frozen_selection_config(
            pre_run_manifest=pre_run_manifest,
            run_fingerprint=run_fingerprint,
            fold_identity=plan.identity_payload,
            origin_index=origin_index,
            cycle_index=cycle,
            generated_candidate_ids=row["generated_candidate_ids"],
            tested_candidate_ids=matrix_cycle["tested_candidate_ids"],
            walk_forward_candidate_ids=matrix_cycle[
                "promoted_candidate_ids"
            ],
            finalist_candidate_ids=matrix_cycle["finalist_candidate_ids"],
            candidate_evidence=row["finalist_candidate_evidence"],
            development_support=support,
        )
        decision = select_candidate(window, config)
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionOriginSelectionError(
            "production cycle cannot build a recomputed Task-15 decision"
        ) from exc
    if decision.to_dict()["fixture_only"] is not False:
        raise ProductionOriginSelectionError(
            "production Task-15 decision cannot use fixture evidence"
        )
    return decision


def build_production_cycle_selection_decision(
    cycle_result: ProductionInnerCycleResult | Mapping[str, Any],
    *,
    fold_plan: InnerFoldPlan | Mapping[str, Any],
    pre_run_manifest: PreRunManifest | Mapping[str, Any],
    run_fingerprint: RunFingerprint | Mapping[str, Any],
) -> Any:
    """Build the real Task-15 decision used by one cycle checkpoint."""

    row = validate_production_inner_cycle_result(cycle_result).to_dict()
    plan = validate_inner_fold_plan(fold_plan)
    matrix = validate_candidate_daily_matrix(row["matrix"]).to_dict()
    if (
        row["fold_plan_sha256"] != plan.plan_sha256
        or matrix["origin_index"] != row["origin_index"]
    ):
        raise ProductionOriginSelectionError(
            "cycle result and fold plan identities differ"
        )
    return validate_selection_decision(
        _build_cycle_decision(
            row,
            plan=plan,
            origin_index=row["origin_index"],
            support=row["development_support"],
            pre_run_manifest=pre_run_manifest,
            run_fingerprint=run_fingerprint,
        )
    )


def _pbo_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "state": payload["state"],
        "reason": payload["reason"],
        "development_pbo": payload["development_pbo"],
        "candidate_beats_cash": payload["candidate_beats_cash"],
        "split_count": payload["split_count"],
        "negative_lambda_count": payload["negative_lambda_count"],
        "rank_universe_size": payload["rank_universe_size"],
        "matrix_sha256": payload["matrix_identity"]["matrix_sha256"],
        "evidence_sha256": payload["evidence_sha256"],
    }


def _dsr_summary(profile_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    score = payload["development_dsr"]
    if score is not None and (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
    ):
        raise ProductionOriginSelectionError("DSR score is non-finite")
    return {
        "profile_id": profile_id,
        "candidate_id": payload.get("selected_candidate_id"),
        "state": payload["state"],
        "reason": payload["reason"],
        "development_dsr": score,
        "passed_minimum_dsr": payload["passed_minimum_dsr"],
        "n_raw": payload["n_raw"],
        "complete_native_trial_count": payload[
            "complete_native_trial_count"
        ],
        "evidence_sha256": payload["evidence_sha256"],
    }


def _dsr_batch_summary(
    payload: Mapping[str, Any],
    shared: Mapping[str, Any],
) -> dict[str, Any]:
    result = payload["result"]
    score = result["development_dsr"]
    if score is not None and (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(float(score))
    ):
        raise ProductionOriginSelectionError("batch DSR score is non-finite")
    return {
        "profile_id": payload["profile_id"],
        "candidate_id": payload["candidate_id"],
        "state": result["state"],
        "reason": result["reason"],
        "development_dsr": score,
        "passed_minimum_dsr": result["passed_minimum_dsr"],
        "n_raw": shared.get("n_raw"),
        "complete_native_trial_count": shared.get(
            "complete_native_trial_count"
        ),
        "evidence_sha256": payload["profile_evidence_sha256"],
    }


def _support_summary(cycle_index: int, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "cycle_index": cycle_index,
        "matrix_state": payload["matrix"]["state"],
        "pbo_state": payload["pbo"]["state"],
        "dsr_state": payload["dsr"]["state"],
        "support_sha256": payload["support_sha256"],
    }


def _decision_summary(
    cycle_index: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    selected = payload["selected_candidate"]
    selected_id = (
        None if selected is None else selected["canonical_candidate_id"]
    )
    ranking = None
    if selected_id is not None:
        matches = [
            row
            for row in payload["ranking_evidence"]
            if row["canonical_candidate_id"] == selected_id
        ]
        if len(matches) != 1:
            raise ProductionOriginSelectionError(
                "Task-15 selected candidate lacks one ranking row"
            )
        ranking = matches[0]
    return {
        "cycle_index": cycle_index,
        "decision_id": payload["decision_id"],
        "decision_sha256": payload["decision_sha256"],
        "outcome": payload["outcome"],
        "selected_candidate_id": selected_id,
        "ranking_evidence": ranking,
    }


def _decision_binding(
    cycle_index: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    config = payload["frozen_pipeline_config"]
    fingerprints = payload["fingerprints"]
    support = config["development_support"]
    pbo = support["pbo"]
    return {
        **_decision_summary(cycle_index, payload),
        "origin_index": config["origin_index"],
        "pipeline_generation_id": fingerprints["pipeline_generation_id"],
        "code_commit": config["run_fingerprint"]["code"]["git_commit"],
        "trial_ledger_head_sha256": fingerprints[
            "trial_ledger_head_sha256"
        ],
        "fold_plan_sha256": fingerprints["fold_plan_sha256"],
        "stage_candidate_ids": config["stage_candidate_ids"],
        "matrix_evidence_sha256": support["matrix"]["evidence_sha256"],
        "pbo_state": pbo["state"],
        "pbo_evidence_sha256": pbo.get("evidence_sha256"),
        "development_support_sha256": support["support_sha256"],
        "selected_candidate": payload["selected_candidate"],
    }


def _summary_from_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: binding[key]
        for key in (
            "cycle_index",
            "decision_id",
            "decision_sha256",
            "outcome",
            "selected_candidate_id",
            "ranking_evidence",
        )
    }


def _archive_decision(
    cycle_index: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    canonical = _canonical(payload).encode("utf-8")
    compressed = gzip.compress(canonical, compresslevel=9, mtime=0)
    compressed_sha256 = hashlib.sha256(compressed).hexdigest()
    _DECISION_BINDING_CACHE[compressed_sha256] = _decision_binding(
        cycle_index, payload
    )
    return {
        "cycle_index": cycle_index,
        "encoding": "gzip_base64_canonical_json_v1",
        "decision_id": payload["decision_id"],
        "decision_sha256": payload["decision_sha256"],
        "canonical_json_sha256": hashlib.sha256(canonical).hexdigest(),
        "compressed_sha256": compressed_sha256,
        "payload_base64": base64.b64encode(compressed).decode("ascii"),
    }


def _read_decision_archive(
    value: Any,
    *,
    expected_cycle: int,
) -> dict[str, Any]:
    row = dict(_mapping(value, "cycle_decision_archive"))
    if set(row) != {
        "cycle_index",
        "encoding",
        "decision_id",
        "decision_sha256",
        "canonical_json_sha256",
        "compressed_sha256",
        "payload_base64",
    }:
        raise ProductionOriginSelectionError(
            "Task-15 decision archive fields are invalid"
        )
    if (
        row["cycle_index"] != expected_cycle
        or row["encoding"] != "gzip_base64_canonical_json_v1"
    ):
        raise ProductionOriginSelectionError(
            "Task-15 decision archive identity is invalid"
        )
    try:
        compressed = base64.b64decode(
            row["payload_base64"], validate=True
        )
    except (ValueError, TypeError) as exc:
        raise ProductionOriginSelectionError(
            "Task-15 decision archive base64 is invalid"
        ) from exc
    if hashlib.sha256(compressed).hexdigest() != row["compressed_sha256"]:
        raise ProductionOriginSelectionError(
            "Task-15 compressed decision digest mismatch"
        )
    cached = _DECISION_BINDING_CACHE.get(row["compressed_sha256"])
    if cached is not None:
        if (
            cached["cycle_index"] != expected_cycle
            or cached["decision_id"] != row["decision_id"]
            or cached["decision_sha256"] != row["decision_sha256"]
        ):
            raise ProductionOriginSelectionError(
                "Task-15 cached decision binding mismatch"
            )
        return json.loads(_canonical(cached))
    try:
        canonical = gzip.decompress(compressed)
    except (OSError, EOFError) as exc:
        raise ProductionOriginSelectionError(
            "Task-15 decision archive gzip is invalid"
        ) from exc
    if (
        len(canonical) > 256_000_000
        or hashlib.sha256(canonical).hexdigest()
        != row["canonical_json_sha256"]
    ):
        raise ProductionOriginSelectionError(
            "Task-15 canonical decision digest mismatch"
        )
    payload = _strict_loads(canonical.decode("utf-8"))
    if _canonical(payload).encode("utf-8") != canonical:
        raise ProductionOriginSelectionError(
            "Task-15 decision archive is not canonical"
        )
    decision = validate_selection_decision(payload).to_dict()
    if (
        decision["decision_id"] != row["decision_id"]
        or decision["decision_sha256"] != row["decision_sha256"]
        or decision["frozen_pipeline_config"]["cycle_index"]
        != expected_cycle
    ):
        raise ProductionOriginSelectionError(
            "Task-15 decision archive binding mismatch"
        )
    binding = _decision_binding(expected_cycle, decision)
    _DECISION_BINDING_CACHE[row["compressed_sha256"]] = binding
    return json.loads(_canonical(binding))


def restore_archived_cycle_decision(
    value: Mapping[str, Any],
    *,
    expected_cycle: int,
) -> Any:
    """Restore one full validated Task-15 decision for downstream Task 13/23."""

    row = dict(_mapping(value, "cycle_decision_archive"))
    if (
        row.get("cycle_index") != expected_cycle
        or row.get("encoding") != "gzip_base64_canonical_json_v1"
    ):
        raise ProductionOriginSelectionError(
            "Task-15 decision archive identity is invalid"
        )
    try:
        compressed = base64.b64decode(
            row["payload_base64"], validate=True
        )
        canonical = gzip.decompress(compressed)
        payload = _strict_loads(canonical.decode("utf-8"))
    except (KeyError, TypeError, ValueError, OSError, EOFError) as exc:
        raise ProductionOriginSelectionError(
            "Task-15 decision archive cannot be restored"
        ) from exc
    if (
        hashlib.sha256(compressed).hexdigest()
        != row.get("compressed_sha256")
        or hashlib.sha256(canonical).hexdigest()
        != row.get("canonical_json_sha256")
        or _canonical(payload).encode("utf-8") != canonical
    ):
        raise ProductionOriginSelectionError(
            "Task-15 decision archive content is invalid"
        )
    decision = validate_selection_decision(payload)
    restored = decision.to_dict()
    if (
        restored["decision_id"] != row.get("decision_id")
        or restored["decision_sha256"] != row.get("decision_sha256")
        or restored["frozen_pipeline_config"]["cycle_index"]
        != expected_cycle
    ):
        raise ProductionOriginSelectionError(
            "Task-15 restored decision binding mismatch"
        )
    return decision


def _validate_current_run_fingerprint(
    value: RunFingerprint | Mapping[str, Any],
    *,
    repo_root: Path,
    ledger: TrialLedgerSnapshot,
    pipeline_generation_id: str,
    code_commit: str,
) -> None:
    try:
        validate_run_fingerprint(value, repo_root=repo_root)
    except (KeyError, TypeError, ValueError) as exc:
        raise ProductionOriginSelectionError(
            "run fingerprint is invalid"
        ) from exc
    if isinstance(value, RunFingerprint):
        payload = value.payload()
    else:
        payload = dict(value)
        for key in ("fingerprint_sha256", "resume_key", "cache_key"):
            payload.pop(key, None)
    ledger_identity = payload["trial_ledger_head"]
    if (
        payload["code"]["git_commit"] != code_commit
        or payload["pipeline"]["generation_id"] != pipeline_generation_id
        or ledger_identity["head_sha256"] != ledger.status.head_sha256
        or ledger_identity["event_count"] != ledger.status.event_count
    ):
        raise ProductionOriginSelectionError(
            "run fingerprint is stale or differs from origin identity"
        )


def _current_ledger(value: TrialLedgerSnapshot) -> TrialLedgerSnapshot:
    if not isinstance(value, TrialLedgerSnapshot):
        raise ProductionOriginSelectionError(
            "trial_ledger must be a verified snapshot"
        )
    current = read_trial_ledger(value.root)
    if current.status.head_sha256 != value.status.head_sha256:
        raise ProductionOriginSelectionError(
            "trial ledger advanced after origin-selection input was frozen"
        )
    return current


def _commit(value: Any) -> str:
    text = str(value).strip().lower()
    if not _COMMIT.fullmatch(text):
        raise ProductionOriginSelectionError(
            "code_commit must be a full lowercase git SHA"
        )
    return text


def _positive(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProductionOriginSelectionError(
            f"{path} must be a positive integer"
        )
    return value


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionOriginSelectionError(f"{path} must be an object")
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


def _strict_loads(text: str) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProductionOriginSelectionError(
                    f"duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    return json.loads(
        text,
        object_pairs_hook=hook,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ProductionOriginSelectionError(
                f"non-finite JSON constant: {value}"
            )
        ),
    )


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "MAX_CYCLES_REACHED",
    "NO_TRADE",
    "ProductionOriginSelectionError",
    "ProductionOriginSelectionResult",
    "READY_CANDIDATE",
    "RESULT_SCHEMA_VERSION",
    "build_production_origin_selection",
    "build_production_cycle_selection_decision",
    "load_production_origin_selection_contract",
    "restore_archived_cycle_decision",
    "validate_production_origin_selection",
    "write_production_origin_selection",
]
