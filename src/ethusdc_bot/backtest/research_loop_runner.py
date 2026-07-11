"""Leakage-safe multi-cycle offline research runner for ETHUSDC."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from math import isfinite
from pathlib import Path
import subprocess
from typing import Any, Callable

from ethusdc_bot.backtest.data_loader import DEFAULT_RAW_ROOT, Candle, load_ethusdc_1m_candles
from ethusdc_bot.backtest.exit_reason_analysis import analyze_exit_reasons
from ethusdc_bot.backtest.experiment_registry import ExperimentPaths
from ethusdc_bot.backtest.features import build_feature_rows
from ethusdc_bot.backtest.quality_gates import QUALITY_GATE_V1, evaluate_quality_gates
from ethusdc_bot.backtest.research_protocol import (
    CANDIDATE_STAGE_BUDGETS,
    CONSUMED_AUDIT_WINDOWS,
    build_research_protocol,
    safety_status,
    validate_research_protocol,
)
from ethusdc_bot.backtest.research_runner import (
    build_candidate_diagnosis,
    build_candidate_leaderboard,
    build_family_aggregates,
    build_family_diagnosis,
    rank_candidates,
)
from ethusdc_bot.backtest.selection_evidence import run_parameter_stability
from ethusdc_bot.backtest.search_space import (
    SearchSpaceState,
    canonical_candidate_signature,
    generate_search_space,
    next_search_space_state,
    search_frontier_summary,
    select_candidates_for_testing,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy
from ethusdc_bot.backtest.split import (
    BLINDTEST_DAYS,
    REQUIRED_DAYS,
    TRAINING_DAYS,
    ResearchWindowPlan,
    build_research_window_plan,
    split_train_blind,
)
from ethusdc_bot.backtest.strategy_search import TARGET_USDC_PER_DAY
from ethusdc_bot.backtest.walk_forward import (
    evaluate_rolling_origins,
    evaluate_walk_forward,
    evaluate_walk_forward_frontier,
    rank_with_walk_forward,
)
from ethusdc_bot.backtest.walk_forward_evidence import (
    build_walk_forward_stress_evidence,
)
from ethusdc_bot.data_pipeline.data_readiness import build_data_readiness_report


MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS = 12
PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER = 2
STRESS_PROFILES_BEYOND_BASELINE = 2
INTERNAL_VALIDATION_DAYS = TRAINING_DAYS // 5
MAX_SELECTION_CANDIDATE_DAYS_PER_CYCLE = (
    (
        CANDIDATE_STAGE_BUDGETS["tested_candidates"]
        + CANDIDATE_STAGE_BUDGETS["walk_forward_candidates"]
        + CANDIDATE_STAGE_BUDGETS["finalists"]
    )
    * TRAINING_DAYS
    + CANDIDATE_STAGE_BUDGETS["finalists"] * 3 * BLINDTEST_DAYS
)
MAX_SELECTION_EVIDENCE_CANDIDATE_DAYS_PER_CYCLE = (
    CANDIDATE_STAGE_BUDGETS["finalists"]
    * (
        STRESS_PROFILES_BEYOND_BASELINE * TRAINING_DAYS
        + PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER
        * MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS
        * INTERNAL_VALIDATION_DAYS
    )
)


@dataclass(frozen=True)
class LoopConfig:
    raw_root: str | Path = DEFAULT_RAW_ROOT
    reports_root: str | Path = "reports/research_loop"
    max_cycles: int = 8
    max_candidates_per_cycle: int = 40
    tested_candidates_per_cycle: int = 12
    walk_forward_candidates_per_cycle: int = 3
    finalists_per_cycle: int = 2
    walk_forward_fold_count: int = 6
    rolling_origin_limit: int = 3
    rolling_origin_step_days: int = 365
    min_cycles: int = 3
    stagnation_cycles: int = 3
    required_days: int | None = REQUIRED_DAYS

    def __post_init__(self) -> None:
        integer_controls = (
            self.max_cycles,
            self.min_cycles,
            self.stagnation_cycles,
            self.walk_forward_fold_count,
            self.rolling_origin_limit,
            self.rolling_origin_step_days,
        )
        if any(not isinstance(value, int) or isinstance(value, bool) for value in integer_controls):
            raise ValueError("cycle and validation controls must be integers")
        caps = (
            self.max_candidates_per_cycle,
            self.tested_candidates_per_cycle,
            self.walk_forward_candidates_per_cycle,
            self.finalists_per_cycle,
        )
        if not all(isinstance(cap, int) and not isinstance(cap, bool) and cap > 0 for cap in caps):
            raise ValueError("candidate stage caps must be positive integers")
        if not (
            self.finalists_per_cycle
            <= self.walk_forward_candidates_per_cycle
            <= self.tested_candidates_per_cycle
            <= self.max_candidates_per_cycle
        ):
            raise ValueError("candidate stage caps must be monotone")
        configured_caps = {
            "generated_candidates": self.max_candidates_per_cycle,
            "tested_candidates": self.tested_candidates_per_cycle,
            "walk_forward_candidates": self.walk_forward_candidates_per_cycle,
            "finalists": self.finalists_per_cycle,
        }
        for stage, cap in configured_caps.items():
            if cap > CANDIDATE_STAGE_BUDGETS[stage]:
                raise ValueError(
                    f"{stage} exceeds the Protocol-v2 hard cap {CANDIDATE_STAGE_BUDGETS[stage]}"
                )
        if self.max_cycles <= 0 or self.min_cycles <= 0 or self.stagnation_cycles <= 0:
            raise ValueError("cycle counts must be positive")
        if self.max_cycles > 8:
            raise ValueError("max_cycles exceeds the Protocol-v2 hard cap of 8")
        if self.min_cycles > self.max_cycles:
            raise ValueError("min_cycles must not exceed max_cycles")
        if self.walk_forward_fold_count <= 0 or self.rolling_origin_limit < 0 or self.rolling_origin_step_days <= 0:
            raise ValueError("validation and rolling-origin budgets are invalid")
        if self.required_days not in {None, REQUIRED_DAYS}:
            raise ValueError("required_days must be 1095 for production or None for fixture smoke")
        if self.required_days == REQUIRED_DAYS:
            configured_caps = {
                "generated_candidates": self.max_candidates_per_cycle,
                "tested_candidates": self.tested_candidates_per_cycle,
                "walk_forward_candidates": self.walk_forward_candidates_per_cycle,
                "finalists": self.finalists_per_cycle,
            }
            if configured_caps != CANDIDATE_STAGE_BUDGETS:
                raise ValueError("production runs require the canonical 40/12/3/2 stage budgets")
            if self.walk_forward_fold_count != QUALITY_GATE_V1.required_wfv_folds:
                raise ValueError("production runs require exactly six walk-forward folds")
            if self.rolling_origin_limit != 3 or self.rolling_origin_step_days != BLINDTEST_DAYS:
                raise ValueError("production runs require the canonical three 365-day historical origins")
        if _selection_candidate_day_cap(self) > MAX_SELECTION_CANDIDATE_DAYS_PER_CYCLE:
            raise ValueError(
                "selection work exceeds the Protocol-v2 candidate-day hard cap "
                f"{MAX_SELECTION_CANDIDATE_DAYS_PER_CYCLE}"
            )


@dataclass(frozen=True)
class LoopRunResult:
    loop_run_id: str
    cycles_executed: int
    stop_reason: str
    target_reached: bool
    best_candidate: dict[str, Any] | None
    report_paths: ExperimentPaths


def run_research_loop(
    config: LoopConfig,
    *,
    cycle_runner: Callable[[int, SearchSpaceState], dict[str, Any]] | None = None,
) -> LoopRunResult:
    """Run selection research without evaluating any final/audit holdout."""

    if cycle_runner is not None and config.required_days is not None:
        raise ValueError("custom cycle runners are fixture/test-only and cannot produce production reports")

    run_id = datetime.now(UTC).strftime("research_loop_%Y%m%dT%H%M%SZ")
    git_commit = _git_commit()
    state = SearchSpaceState(cycle_index=1, diagnosis={"problem_assessment": "costs_and_insufficient_edge"})
    cycles: list[dict[str, Any]] = []
    best_selection_rank: tuple[float, ...] | None = None
    best_candidate: dict[str, Any] | None = None
    no_improvement = 0
    stop_reason = "max_cycles_reached"
    runner = cycle_runner or _build_real_cycle_runner(config)

    for cycle_index in range(1, config.max_cycles + 1):
        print(f"cycle {cycle_index}/{config.max_cycles}: starting", flush=True)
        cycle = dict(runner(cycle_index, state))
        cycle["cycle_id"] = cycle_index
        _validate_cycle_payload(cycle, expected_budget=_resource_budget(config))
        stored_cycle = _jsonable_cycle(cycle)
        cycles.append(stored_cycle)
        if not _safety_ok(cycle.get("safety", {})):
            stop_reason = "safety_violation"
            break
        current_selection_rank = _cycle_selected_rank(cycle)
        print(
            f"cycle {cycle_index}/{config.max_cycles}: generated={cycle['generated_candidates']} "
            f"tested={cycle['tested_candidates']} walk_forward={cycle['walk_forward_candidates']} "
            f"finalists={cycle['finalists']} selected_rank={current_selection_rank}",
            flush=True,
        )
        if best_selection_rank is None or current_selection_rank > best_selection_rank:
            best_selection_rank = current_selection_rank
            best_candidate = cycle.get("selected_candidate")
            no_improvement = 0
        else:
            no_improvement += 1
        if cycle_index >= config.min_cycles and no_improvement >= config.stagnation_cycles:
            stop_reason = f"selection_stagnation_{config.stagnation_cycles}_cycles"
            break
        state = next_search_space_state(cycle)
    else:
        stop_reason = "max_cycles_reached"

    frozen_candidate = _select_frozen_candidate(cycles) if config.required_days == REQUIRED_DAYS else None
    report = _loop_report(
        run_id=run_id,
        git_commit=git_commit,
        config=config,
        cycles=cycles,
        stop_reason=stop_reason,
        best_candidate=best_candidate,
        frozen_candidate=frozen_candidate,
    )
    paths = _record_loop_report(report, config.reports_root)
    return LoopRunResult(run_id, len(cycles), stop_reason, False, best_candidate, paths)


def _build_real_cycle_runner(config: LoopConfig) -> Callable[[int, SearchSpaceState], dict[str, Any]]:
    raw_root = Path(config.raw_root)
    if config.required_days == REQUIRED_DAYS:
        readiness = build_data_readiness_report(raw_root)
        if not readiness["data_gate_ready"]:
            raise RuntimeError(f"Data gate blocked: {readiness['overall_status']}")
    candles = load_ethusdc_1m_candles(raw_root)
    plan = _build_window_plan(candles, config)
    split = plan.final_window
    build_feature_rows(split.training[: min(len(split.training), 5000)])
    subtrain, validation = _split_subtrain_validation_on_utc_days(split.training)
    subtrain_days = _calendar_day_count(subtrain)
    validation_days = _calendar_day_count(validation)

    def runner(cycle_index: int, state: SearchSpaceState) -> dict[str, Any]:
        generated = generate_search_space(state, max_candidates=config.max_candidates_per_cycle)
        frontier_summary = search_frontier_summary(
            generated,
            state,
            requested_cap=config.max_candidates_per_cycle,
        )
        generated_rows = [
            {
                "candidate_id": f"{candidate.family}_{cycle_index:02d}_{index:03d}",
                "candidate": candidate,
            }
            for index, candidate in enumerate(generated, start=1)
        ]

        # Search Frontier v2 contains only simulator-backed ETHUSDC families.
        # Context candidates return only after aligned BTCUSDC/ETHBTC data is
        # actually consumed by the signal engine.
        supported_rows = list(generated_rows)
        supported = [row["candidate"] for row in supported_rows]
        selected_for_testing = select_candidates_for_testing(supported, config.tested_candidates_per_cycle)
        rows_by_signature = {
            canonical_candidate_signature(row["candidate"]): row for row in supported_rows
        }
        tested_rows = [rows_by_signature[canonical_candidate_signature(candidate)] for candidate in selected_for_testing]

        records: list[dict[str, Any]] = []
        for row in tested_rows:
            candidate = row["candidate"]
            train_result = simulate_strategy(
                subtrain,
                candidate,
                days=subtrain_days,
                training_days=split.training_days,
                blindtest_days=split.blindtest_days,
            )
            validation_result = simulate_strategy(
                validation,
                candidate,
                days=validation_days,
                training_days=split.training_days,
                blindtest_days=split.blindtest_days,
            )
            records.append(
                {
                    "candidate_id": row["candidate_id"],
                    "candidate": candidate,
                    "training_result": train_result,
                    "validation_result": validation_result,
                    "training_metrics": train_result.metrics,
                    "validation_metrics": validation_result.metrics,
                }
            )
        if not records:
            raise RuntimeError("Research cycle has no eligible candidates to test")

        validation_ranked = rank_candidates(records)
        validation_leader = validation_ranked[0]
        wfv_records = evaluate_walk_forward_frontier(
            split.training,
            validation_ranked,
            candidate_limit=config.walk_forward_candidates_per_cycle,
            fold_count=config.walk_forward_fold_count,
            training_days=split.training_days,
            blindtest_days=split.blindtest_days,
            expected_candles_per_day=1440,
        )
        wfv_ranked = rank_with_walk_forward(wfv_records)
        finalist_records = wfv_ranked[: config.finalists_per_cycle]
        for record in finalist_records:
            full_training_result = simulate_strategy(
                split.training,
                record["candidate"],
                days=split.training_days,
                training_days=split.training_days,
                blindtest_days=split.blindtest_days,
            )
            record["full_training_result"] = full_training_result
            record["rolling_origin_summary"] = evaluate_rolling_origins(
                list(plan.historical_origins),
                record["candidate"],
                origin_limit=config.rolling_origin_limit,
            )
            joint_stress_wfv = evaluate_walk_forward(
                split.training,
                record["candidate"],
                fold_count=config.walk_forward_fold_count,
                training_days=split.training_days,
                blindtest_days=split.blindtest_days,
                expected_candles_per_day=1440,
                fee_rate=QUALITY_GATE_V1.joint_stress_fee_bps_per_side / 10_000,
                slippage_bps=QUALITY_GATE_V1.joint_stress_slippage_bps_per_side,
                include_selection_evidence=False,
            )
            slippage_stress_wfv = evaluate_walk_forward(
                split.training,
                record["candidate"],
                fold_count=config.walk_forward_fold_count,
                training_days=split.training_days,
                blindtest_days=split.blindtest_days,
                expected_candles_per_day=1440,
                fee_rate=QUALITY_GATE_V1.slippage_stress_fee_bps_per_side / 10_000,
                slippage_bps=QUALITY_GATE_V1.slippage_stress_slippage_bps_per_side,
                include_selection_evidence=False,
            )
            baseline_selection = record["walk_forward_summary"].get(
                "selection_evidence", {}
            )
            record["selection_evidence"] = {
                "rolling": baseline_selection.get("rolling", {}),
                "temporal": baseline_selection.get("temporal", {}),
                "regime": baseline_selection.get("regime", {}),
                "stress": build_walk_forward_stress_evidence(
                    record["walk_forward_summary"],
                    joint_stress_wfv,
                    slippage_stress_wfv,
                    baseline_fee_bps=QUALITY_GATE_V1.baseline_fee_bps_per_side,
                    baseline_slippage_bps=(
                        QUALITY_GATE_V1.baseline_slippage_bps_per_side
                    ),
                    joint_fee_bps=QUALITY_GATE_V1.joint_stress_fee_bps_per_side,
                    joint_slippage_bps=(
                        QUALITY_GATE_V1.joint_stress_slippage_bps_per_side
                    ),
                    slippage_fee_bps=(
                        QUALITY_GATE_V1.slippage_stress_fee_bps_per_side
                    ),
                    slippage_stress_bps=(
                        QUALITY_GATE_V1.slippage_stress_slippage_bps_per_side
                    ),
                ),
                "parameter_stability": run_parameter_stability(
                    validation,
                    record["candidate"],
                    days=validation_days,
                    gate=QUALITY_GATE_V1,
                    baseline_result=record["validation_result"],
                    max_numeric_parameters=(
                        MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS
                    ),
                ),
                "provenance": {
                    "selection_data_only": True,
                    "uses_audit_or_holdout": False,
                    "rolling_temporal_regime_source": (
                        "chronological_walk_forward_validation_folds"
                    ),
                    "parameter_source": "internal_validation_only",
                    "stress_source": "same_walk_forward_folds_fixed_cost_profiles",
                },
            }
            evidence = _quality_evidence(record, full_training_result)
            record["quality_gate_evidence"] = evidence
            record["quality_gate"] = _bind_quality_gate(
                evaluate_quality_gates(evidence, stage="selection").to_dict(),
                candidate_id=record["candidate_id"],
                candidate=record["candidate"],
            )
        finalist_records = sorted(finalist_records, key=_finalist_score, reverse=True)
        selected_record = finalist_records[0] if finalist_records else validation_ranked[0]
        selected = selected_record["candidate"]

        leaderboard = build_candidate_leaderboard(
            records,
            selected_candidate_id=selected_record["candidate_id"],
        )
        candidate_diagnosis = build_candidate_diagnosis(leaderboard)
        family_aggregates = build_family_aggregates(leaderboard)
        family_diagnosis = build_family_diagnosis(family_aggregates)
        exit_summary = analyze_exit_reasons(selected_record["validation_result"].trades)
        selected_wfv = selected_record.get(
            "walk_forward_summary",
            {"ranking_uses_blindtest": False, "not_evaluated_reason": "outside_walk_forward_frontier"},
        )
        selected_rolling = selected_record.get(
            "rolling_origin_summary", {"uses_final_audit": False, "origin_count": 0, "origins": []}
        )
        selected_gate = selected_record.get("quality_gate")
        if selected_gate is None:
            selected_gate = _bind_quality_gate(
                evaluate_quality_gates({}, stage="selection").to_dict(),
                candidate_id=selected_record["candidate_id"],
                candidate=selected,
            )
        selected_signature = _candidate_signature(selected.family, selected.params)
        selected_score = _selected_record_score(selected_record)

        generated_ids = [row["candidate_id"] for row in generated_rows]
        tested_ids = [record["candidate_id"] for record in records]
        wfv_ids = [record["candidate_id"] for record in wfv_records]
        finalist_ids = [record["candidate_id"] for record in finalist_records]
        walk_forward_summaries = [
            {
                "candidate_id": record["candidate_id"],
                "family": record["candidate"].family,
                "summary": record["walk_forward_summary"],
            }
            for record in wfv_records
        ]
        finalist_summaries = [
            {
                "candidate_id": record["candidate_id"],
                "family": record["candidate"].family,
                "walk_forward_summary": record["walk_forward_summary"],
                "historical_replay_summary": record["rolling_origin_summary"],
                "quality_gate_evidence": record["quality_gate_evidence"],
                "quality_gate": record["quality_gate"],
            }
            for record in finalist_records
        ]
        tested_signatures = {canonical_candidate_signature(record["candidate"]) for record in records}
        not_tested = []
        for row in generated_rows:
            signature = canonical_candidate_signature(row["candidate"])
            if signature in tested_signatures:
                continue
            not_tested.append(
                {"candidate_id": row["candidate_id"], "reason": "tested_stage_budget"}
            )
        not_tested_by_id = {row["candidate_id"]: row["reason"] for row in not_tested}
        generated_inventory = [
            {
                "candidate_id": row["candidate_id"],
                "family": row["candidate"].family,
                "params": dict(row["candidate"].params),
                "candidate_signature": _candidate_signature(
                    row["candidate"].family, row["candidate"].params
                ),
                "tested": row["candidate_id"] in tested_ids,
                "not_tested_reason": not_tested_by_id.get(row["candidate_id"]),
            }
            for row in generated_rows
        ]

        return {
            "generated_candidates": len(generated_ids),
            "tested_candidates": len(tested_ids),
            "walk_forward_candidates": len(wfv_ids),
            "finalists": len(finalist_ids),
            "qualified_finalists": sum(1 for record in finalist_records if record["quality_gate"]["passed"]),
            "walk_forward_summaries": walk_forward_summaries,
            "finalist_summaries": finalist_summaries,
            "candidate_stage_ids": {
                "generated": generated_ids,
                "tested": tested_ids,
                "walk_forward": wfv_ids,
                "finalists": finalist_ids,
            },
            "generated_candidate_inventory": generated_inventory,
            "search_frontier": frontier_summary,
            "resource_budget": _resource_budget(config),
            "not_tested_candidates": not_tested,
            "best_training_candidate": _best_metric_row(records, "training_metrics"),
            "best_validation_candidate": {
                "candidate_id": validation_leader["candidate_id"],
                "family": validation_leader["candidate"].family,
                "net_usdc_per_day": validation_leader["validation_metrics"].net_usdc_per_day,
                "trade_count": validation_leader["validation_metrics"].trade_count,
                "profit_factor": validation_leader["validation_metrics"].profit_factor,
            },
            "best_validation_metrics": validation_leader["validation_metrics"],
            "wfv_summary": selected_wfv,
            "rolling_origin_summary": selected_rolling,
            "quality_gate": selected_gate,
            "quality_gate_evidence": selected_record.get("quality_gate_evidence", {}),
            "candidate_leaderboard_summary": leaderboard,
            "family_aggregate_summary": family_aggregates,
            "family_diagnosis": family_diagnosis,
            "candidate_diagnosis": candidate_diagnosis,
            "exit_reason_summary": exit_summary,
            "selected_candidate": {
                "candidate_id": selected_record["candidate_id"],
                "family": selected.family,
                "params": dict(selected.params),
                "candidate_signature": selected_signature,
            },
            "selected_candidate_score": {
                "candidate_id": selected_record["candidate_id"],
                "candidate_signature": selected_signature,
                "ranking_rule": "quality_gate_then_wfv_aggregate_pf_drawdown_then_fold_tiebreakers",
                "quality_gate_passed": selected_score[0] == 1.0,
                "wfv_net_usdc_per_day": selected_score[1],
                "wfv_profit_factor": selected_score[2],
                "wfv_max_drawdown_usdc": -selected_score[3],
                "worst_fold_net_usdc_per_day": selected_score[4],
                "positive_fold_count": selected_score[5],
                "validation_net_usdc_per_day": selected_score[6],
                "wfv_cost_load": -selected_score[7],
            },
            "full_training_metrics": selected_record.get("full_training_result", selected_record["training_result"]).metrics,
            "window_plan": _window_plan_summary(plan),
            "training_evaluation_note": "full chronological subtrain/validation and WFV use training data only; final holdout metadata is recorded but never evaluated",
            "next_search_space_adjustment": _adjustment_reason(candidate_diagnosis, family_diagnosis, exit_summary),
            "safety": safety_status(),
            "selection_source": "subtrain_validation_walk_forward_only",
            "historical_replay_role": "diagnostic_fixed_candidate_replay_not_selection_evidence",
        }

    return runner


def _build_window_plan(candles: list[Candle], config: LoopConfig) -> ResearchWindowPlan:
    if config.required_days is None:
        fixture_split = split_train_blind(candles, required_days=None)
        return build_research_window_plan(
            candles,
            training_days=fixture_split.training_days,
            blindtest_days=fixture_split.blindtest_days,
            max_historical_origins=0,
            expected_candles_per_day=1440,
            excluded_selection_windows=CONSUMED_AUDIT_WINDOWS,
        )
    return build_research_window_plan(
        candles,
        rolling_step_days=config.rolling_origin_step_days,
        max_historical_origins=config.rolling_origin_limit,
        expected_candles_per_day=1440,
        excluded_selection_windows=CONSUMED_AUDIT_WINDOWS,
    )


def _quality_evidence(record: dict[str, Any], full_training_result: Any) -> dict[str, Any]:
    wfv = record.get("walk_forward_summary", {})
    aggregate = dict(wfv.get("aggregate_metrics", {}))
    aggregate.update(
        {
            "positive_fold_count": wfv.get("positive_fold_count"),
            "folds_pf_at_least_1_05": wfv.get("folds_pf_at_least_1_05"),
            "worst_fold_profit_factor": wfv.get("worst_fold_profit_factor"),
            "median_fold_net_usdc_per_day": wfv.get("median_fold_net_usdc_per_day"),
            "worst_fold_net_usdc_per_day": wfv.get("worst_fold_net_usdc_per_day"),
            "fold_net_coefficient_of_variation": wfv.get("fold_net_coefficient_of_variation"),
            "full_training_net_usdc_per_day": full_training_result.metrics.net_usdc_per_day,
        }
    )
    selection_evidence = record.get("selection_evidence", {})
    validation = record["validation_metrics"].to_dict()
    validation_result = record["validation_result"]
    validation["drawdown_method"] = validation_result.drawdown_method
    validation["max_underwater_days"] = validation_result.max_underwater_days
    folds: list[dict[str, Any]] = []
    for source in wfv.get("folds", []) or []:
        fold = dict(source)
        metrics = dict(fold.get("metrics", {}))
        fold["metrics"] = metrics
        folds.append(fold)
    return {
        "protocol": {
            "gate_version": QUALITY_GATE_V1.version,
            "gate_frozen_before_evaluation": True,
            "selection_uses_audit": False,
        },
        "validation": validation,
        "wfv": {
            "fold_count": wfv.get("fold_count"),
            "folds": folds,
            "aggregate": aggregate,
        },
        "rolling": dict(selection_evidence.get("rolling", {})),
        "stress": dict(selection_evidence.get("stress", {})),
        "parameter_stability": dict(
            selection_evidence.get("parameter_stability", {})
        ),
        "temporal": dict(selection_evidence.get("temporal", {})),
        "regime": dict(selection_evidence.get("regime", {})),
        "selection_evidence_provenance": dict(
            selection_evidence.get("provenance", {})
        ),
    }


def _finalist_score(record: dict[str, Any]) -> tuple[float, ...]:
    return _selected_record_score(record)


def _selected_record_score(record: dict[str, Any]) -> tuple[float, ...]:
    wfv = record.get("walk_forward_summary", {})
    aggregate = wfv.get("aggregate_metrics", {})
    aggregate_cost = _finite_rank_value(aggregate.get("fees_usdc")) + _finite_rank_value(
        aggregate.get("slippage_usdc")
    )
    gate_passed = 1.0 if record.get("quality_gate", {}).get("passed") else 0.0
    return (
        gate_passed,
        _finite_rank_value(aggregate.get("net_usdc_per_day")),
        _finite_rank_value(aggregate.get("profit_factor")),
        -_finite_rank_value(aggregate.get("max_drawdown_usdc")),
        _finite_rank_value(wfv.get("worst_fold_net_usdc_per_day")),
        _finite_rank_value(wfv.get("positive_fold_count")),
        _finite_rank_value(record["validation_metrics"].net_usdc_per_day),
        -aggregate_cost,
    )


def _finite_rank_value(value: Any) -> float:
    try:
        number = float(value) if value is not None else 0.0
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if isfinite(number):
        return number
    return 1_000_000_000_000.0 if number > 0 else -1_000_000_000_000.0


def _candidate_signature(family: str, params: Any) -> str:
    normalized_params = dict(params)
    normalized_params.setdefault("symbol", "ETHUSDC")
    return json.dumps(
        {"family": str(family), "params": normalized_params},
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _bind_quality_gate(
    gate: dict[str, Any], *, candidate_id: str, candidate: StrategyCandidate
) -> dict[str, Any]:
    bound = dict(gate)
    bound["candidate_id"] = candidate_id
    bound["candidate_signature"] = _candidate_signature(candidate.family, candidate.params)
    return bound


def _cycle_selected_rank(cycle: dict[str, Any]) -> tuple[float, ...]:
    score = cycle.get("selected_candidate_score", {})
    return (
        1.0 if score.get("quality_gate_passed") is True else 0.0,
        float(score.get("wfv_net_usdc_per_day", float("-inf"))),
        float(score.get("wfv_profit_factor", float("-inf"))),
        -float(score.get("wfv_max_drawdown_usdc", float("inf"))),
        float(score.get("worst_fold_net_usdc_per_day", float("-inf"))),
        float(score.get("positive_fold_count", float("-inf"))),
        float(score.get("validation_net_usdc_per_day", float("-inf"))),
        -float(score.get("wfv_cost_load", float("inf"))),
    )


def _best_metric_row(records: list[dict[str, Any]], metric_key: str) -> dict[str, Any]:
    record = max(records, key=lambda row: getattr(row[metric_key], "net_usdc_per_day"))
    metrics = record[metric_key]
    return {
        "candidate_id": record["candidate_id"],
        "family": record["candidate"].family,
        "net_usdc_per_day": metrics.net_usdc_per_day,
    }


def _cycle_validation_net(cycle: dict[str, Any]) -> float:
    best = cycle.get("best_validation_candidate", {})
    if isinstance(best, dict) and "net_usdc_per_day" in best:
        return float(best["net_usdc_per_day"])
    metrics = cycle.get("best_validation_metrics")
    if hasattr(metrics, "net_usdc_per_day"):
        return float(metrics.net_usdc_per_day)
    if isinstance(metrics, dict):
        return float(metrics.get("net_usdc_per_day", 0.0))
    return 0.0


def _adjustment_reason(
    candidate_diagnosis: dict[str, Any], family_diagnosis: dict[str, Any], exit_summary: dict[str, Any]
) -> str:
    if exit_summary.get("stop_loss_share", 0) > 0.45:
        return "stop_loss_dominates: tighten entry trend/volatility filters"
    if exit_summary.get("time_exit_share", 0) > 0.45:
        return "time_exit_dominates: test session/regime and exit timing variants"
    if family_diagnosis.get("problem_assessment") == "costs_and_insufficient_edge":
        return "costs_high: increase expected move thresholds and cooldown, reduce slippage-sensitive setups"
    return str(candidate_diagnosis.get("why_not_profitable_enough", "continue validation-only refinement"))


def _validate_cycle_payload(cycle: dict[str, Any], *, expected_budget: dict[str, int]) -> None:
    forbidden = {"blindtest_audit", "blindtest_metrics", "audit_result", "holdout_result", "holdout_metrics"}
    present = sorted(_find_forbidden_keys(cycle, forbidden))
    if present:
        raise ValueError(f"Research cycle contains forbidden audit/blindtest/holdout payload: {present}")

    stage_names = ("generated", "tested", "walk_forward", "finalists")
    count_keys = {
        "generated": "generated_candidates",
        "tested": "tested_candidates",
        "walk_forward": "walk_forward_candidates",
        "finalists": "finalists",
    }
    ids = cycle.get("candidate_stage_ids")
    if not isinstance(ids, dict) or any(not isinstance(ids.get(stage), list) for stage in stage_names):
        raise ValueError("candidate stage ids must list generated, tested, walk_forward, and finalists")
    counts = []
    for stage in stage_names:
        count = cycle.get(count_keys[stage])
        if not isinstance(count, int) or isinstance(count, bool) or count < 0 or count != len(ids[stage]):
            raise ValueError("candidate stage counts must match candidate stage id lists")
        if len(ids[stage]) != len(set(ids[stage])):
            raise ValueError("candidate stage ids must be unique")
        counts.append(count)
    generated, tested, walk_forward, finalists = counts
    if not (finalists <= walk_forward <= tested <= generated):
        raise ValueError("candidate stage counts must satisfy finalists <= walk_forward <= tested <= generated")
    for parent, child in zip(stage_names, stage_names[1:]):
        if not set(ids[child]).issubset(set(ids[parent])):
            raise ValueError("candidate stage ids must form nested subsets")

    inventory = cycle.get("generated_candidate_inventory")
    if not isinstance(inventory, list) or len(inventory) != generated:
        raise ValueError("generated candidate inventory must describe every generated candidate")
    inventory_ids: list[str] = []
    inventory_signatures: list[str] = []
    for row in inventory:
        if not isinstance(row, dict):
            raise ValueError("generated candidate inventory rows must be objects")
        try:
            signature = _candidate_signature(row["family"], row["params"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("generated candidate inventory contains an invalid identity") from exc
        if row.get("candidate_signature") != signature or not isinstance(row.get("candidate_id"), str):
            raise ValueError("generated candidate inventory signature is invalid")
        if row.get("tested") is not (row["candidate_id"] in ids["tested"]):
            raise ValueError("generated candidate inventory tested status is inconsistent")
        expected_reason_missing = row["candidate_id"] in ids["tested"]
        if expected_reason_missing and row.get("not_tested_reason") is not None:
            raise ValueError("tested candidate must not have a not-tested reason")
        if not expected_reason_missing and not isinstance(row.get("not_tested_reason"), str):
            raise ValueError("untested candidate must have an explicit reason")
        inventory_ids.append(row["candidate_id"])
        inventory_signatures.append(signature)
    if inventory_ids != ids["generated"] or len(set(inventory_signatures)) != len(inventory_signatures):
        raise ValueError("generated candidate inventory must match stage order with unique candidates")
    inventory_by_id = {row["candidate_id"]: row for row in inventory}

    budget = cycle.get("resource_budget")
    budget_keys = ("generated_cap", "tested_cap", "walk_forward_cap", "finalists_cap")
    if not isinstance(budget, dict) or any(
        not isinstance(budget.get(key), int) or isinstance(budget.get(key), bool) for key in budget_keys
    ):
        raise ValueError("candidate stage resource budget is missing")
    caps = [budget[key] for key in budget_keys]
    if any(cap <= 0 for cap in caps):
        raise ValueError("candidate stage resource caps must be positive")
    if not (caps[3] <= caps[2] <= caps[1] <= caps[0]):
        raise ValueError("candidate stage resource caps must be monotone")
    if any(count > cap for count, cap in zip(counts, caps)):
        raise ValueError("candidate stage count exceeds its resource cap")
    if budget != expected_budget:
        raise ValueError("cycle resource budget must exactly match the configured Protocol-v2 budget")

    selected = cycle.get("selected_candidate")
    if not isinstance(selected, dict):
        raise ValueError("selected candidate is missing")
    selected_id = selected.get("candidate_id")
    if finalists > 0 and selected_id not in ids["finalists"]:
        raise ValueError("selected candidate must be one of the reported finalists")
    try:
        expected_signature = _candidate_signature(selected["family"], selected["params"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("selected candidate identity is invalid") from exc
    if selected.get("candidate_signature") != expected_signature:
        raise ValueError("selected candidate signature does not match its family and parameters")
    if inventory_by_id.get(selected_id, {}).get("candidate_signature") != expected_signature:
        raise ValueError("selected candidate identity does not match the generated inventory")

    score = cycle.get("selected_candidate_score")
    score_fields = (
        "wfv_net_usdc_per_day",
        "wfv_profit_factor",
        "wfv_max_drawdown_usdc",
        "worst_fold_net_usdc_per_day",
        "positive_fold_count",
        "validation_net_usdc_per_day",
        "wfv_cost_load",
    )
    if not isinstance(score, dict):
        raise ValueError("selected candidate score is missing")
    if score.get("candidate_id") != selected_id or score.get("candidate_signature") != expected_signature:
        raise ValueError("selected candidate score is not bound to the selected finalist")
    if not isinstance(score.get("quality_gate_passed"), bool) or any(
        not isinstance(score.get(field), (int, float))
        or isinstance(score.get(field), bool)
        or not isfinite(float(score[field]))
        for field in score_fields
    ):
        raise ValueError("selected candidate score contains invalid ranking evidence")
    if (
        score.get("ranking_rule")
        != "quality_gate_then_wfv_aggregate_pf_drawdown_then_fold_tiebreakers"
        or float(score["wfv_max_drawdown_usdc"]) < 0
        or float(score["positive_fold_count"]) < 0
        or float(score["wfv_cost_load"]) < 0
    ):
        raise ValueError("selected candidate score does not follow the canonical ranking rule")

    gate = cycle.get("quality_gate")
    if not isinstance(gate, dict) or not isinstance(gate.get("passed"), bool):
        raise ValueError("selected candidate quality gate is missing or invalid")
    evidence = cycle.get("quality_gate_evidence")
    if not isinstance(evidence, dict):
        raise ValueError("selected candidate quality-gate evidence is missing")
    recomputed_gate = _bind_quality_gate(
        evaluate_quality_gates(evidence, stage="selection").to_dict(),
        candidate_id=str(selected_id),
        candidate=StrategyCandidate(str(selected["family"]), dict(selected["params"])),
    )
    if gate != recomputed_gate:
        raise ValueError("quality gate does not match a canonical re-evaluation of its evidence")
    if score["quality_gate_passed"] is not gate["passed"]:
        raise ValueError("selected candidate score and quality gate disagree")
    if gate["passed"] is True and not _quality_gate_freeze_eligible(cycle):
        raise ValueError("passed quality gate is not validly bound to the selected finalist")


def _find_forbidden_keys(value: Any, forbidden: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in forbidden or _looks_like_forbidden_audit_result_key(normalized_key):
                found.add(str(key))
            found.update(_find_forbidden_keys(item, forbidden))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_find_forbidden_keys(item, forbidden))
    return found


def _looks_like_forbidden_audit_result_key(key: str) -> bool:
    if key in {"required_sealed_holdout_evaluations"}:
        return False
    if key in {"audit", "blindtest", "holdout"}:
        return True
    contains_protected_window = any(token in key for token in ("audit", "blindtest", "holdout"))
    contains_result = any(
        token in key
        for token in (
            "metric",
            "result",
            "performance",
            "pnl",
            "profit",
            "return",
            "score",
            "drawdown",
            "trade",
            "evaluated",
            "evaluation",
            "outcome",
            "stat",
            "data",
            "candle",
            "payload",
            "evidence",
            "equity",
            "curve",
        )
    )
    return contains_protected_window and contains_result


def _select_frozen_candidate(cycles: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [
        cycle
        for cycle in cycles
        if _quality_gate_freeze_eligible(cycle) and _cycle_has_sealed_unopened_holdout(cycle)
    ]
    if not eligible:
        return None
    best = max(eligible, key=_cycle_selected_rank)
    return best.get("selected_candidate")


def _cycle_has_sealed_unopened_holdout(cycle: dict[str, Any]) -> bool:
    window_plan = cycle.get("window_plan")
    if not isinstance(window_plan, dict):
        return False
    return _sealed_holdout_window_ready(window_plan.get("final_holdout_window"))


def _sealed_holdout_window_ready(value: Any) -> bool:
    return bool(
        isinstance(value, dict)
        and value.get("status") == "sealed_unopened"
        and value.get("consumed_audit_window") is False
        and value.get("evaluated") is False
        and value.get("days") == BLINDTEST_DAYS
        and not isinstance(value.get("days"), bool)
    )


def _freeze_status(
    config: LoopConfig,
    frozen_candidate: dict[str, Any] | None,
    active_holdout: Any,
) -> str:
    if config.required_days is None:
        return "fixture_nonproduction_no_freeze"
    if frozen_candidate is not None and _sealed_holdout_window_ready(active_holdout):
        return "frozen_for_separate_sealed_holdout"
    if not _sealed_holdout_window_ready(active_holdout):
        return "blocked_by_holdout_policy"
    return "blocked_by_quality_gates"


def _quality_gate_freeze_eligible(cycle: dict[str, Any]) -> bool:
    gate = cycle.get("quality_gate")
    selected = cycle.get("selected_candidate")
    stage_ids = cycle.get("candidate_stage_ids")
    if not isinstance(gate, dict) or not isinstance(selected, dict) or not isinstance(stage_ids, dict):
        return False
    selected_id = selected.get("candidate_id")
    selected_signature = selected.get("candidate_signature")
    finalists = stage_ids.get("finalists")
    readiness = gate.get("stage_readiness")
    gate_safety = gate.get("safety")
    checks = gate.get("checks")
    finalist_summaries = cycle.get("finalist_summaries")
    selected_summary = next(
        (
            summary
            for summary in finalist_summaries
            if isinstance(summary, dict) and summary.get("candidate_id") == selected_id
        ),
        None,
    ) if isinstance(finalist_summaries, list) else None
    expected_check_codes = _canonical_selection_gate_check_codes()
    return bool(
        cycle.get("finalists", 0) > 0
        and _safety_ok(cycle.get("safety", {}))
        and isinstance(finalists, list)
        and selected_id in finalists
        and gate.get("schema_version") == 1
        and gate.get("gate_version") == QUALITY_GATE_V1.version
        and gate.get("stage") == "selection"
        and gate.get("status") == "pass"
        and gate.get("passed") is True
        and gate.get("thresholds") == QUALITY_GATE_V1.to_dict()
        and gate.get("missing_evidence") == []
        and gate.get("invalid_evidence") == []
        and isinstance(readiness, dict)
        and readiness.get("research_evidence_complete") is True
        and readiness.get("sealed_holdout_ready") is True
        and readiness.get("candidate_adoption_ready") is False
        and readiness.get("live_ready") is False
        and isinstance(gate_safety, dict)
        and gate_safety.get("candidate_adoptable") is False
        and gate_safety.get("live") == "locked"
        and gate_safety.get("paper") == "locked"
        and gate_safety.get("testtrade") == "locked"
        and gate.get("candidate_id") == selected_id
        and gate.get("candidate_signature") == selected_signature
        and isinstance(checks, list)
        and [check.get("code") for check in checks if isinstance(check, dict)] == expected_check_codes
        and len(checks) == len(expected_check_codes)
        and all(
            isinstance(check, dict)
            and check.get("phase") == "selection"
            and check.get("passed") is True
            and check.get("reason") == "passed"
            and isinstance(check.get("evidence_paths"), list)
            and bool(check["evidence_paths"])
            for check in checks
        )
        and isinstance(finalist_summaries, list)
        and [summary.get("candidate_id") for summary in finalist_summaries if isinstance(summary, dict)]
        == finalists
        and len(finalist_summaries) == len(finalists)
        and isinstance(selected_summary, dict)
        and selected_summary.get("quality_gate") == gate
    )


def _canonical_selection_gate_check_codes() -> list[str]:
    report = evaluate_quality_gates({}, stage="selection").to_dict()
    return [str(check["code"]) for check in report["checks"]]


def _loop_report(**kwargs: Any) -> dict[str, Any]:
    cycles = kwargs["cycles"]
    config: LoopConfig = kwargs["config"]
    best_validation_result = max(
        (cycle.get("best_validation_candidate", {}) for cycle in cycles),
        key=lambda row: row.get("net_usdc_per_day", float("-inf")),
        default={},
    )
    stage_totals = {
        "generated": sum(int(cycle.get("generated_candidates", 0)) for cycle in cycles),
        "tested": sum(int(cycle.get("tested_candidates", 0)) for cycle in cycles),
        "walk_forward": sum(int(cycle.get("walk_forward_candidates", 0)) for cycle in cycles),
        "finalists": sum(int(cycle.get("finalists", 0)) for cycle in cycles),
    }
    budgets = {
        "generated_candidates": config.max_candidates_per_cycle,
        "tested_candidates": config.tested_candidates_per_cycle,
        "walk_forward_candidates": config.walk_forward_candidates_per_cycle,
        "finalists": config.finalists_per_cycle,
    }
    window_plan = cycles[0].get("window_plan", {}) if cycles else {}
    active_holdout = window_plan.get("final_holdout_window", {}) if isinstance(window_plan, dict) else {}
    active_consumed = bool(active_holdout.get("consumed_audit_window", True))
    active_holdout_freeze_ready = _sealed_holdout_window_ready(active_holdout)
    protocol = build_research_protocol(
        raw_root=config.raw_root,
        git_commit=kwargs["git_commit"],
        run_id=kwargs["run_id"],
        data_window=window_plan,
        parameter_space={
            "source": "generated_candidate_inventory",
            "cycles": [
                {
                    "cycle_id": cycle.get("cycle_id"),
                    "candidates": cycle.get("generated_candidate_inventory", []),
                }
                for cycle in cycles
            ],
        },
        candidate_stage_budgets=budgets,
    )
    validation = validate_research_protocol(protocol)
    if not validation["valid"]:
        raise RuntimeError(f"Invalid Research Protocol v2: {validation['errors']}")
    frozen_candidate = (
        kwargs["frozen_candidate"] if active_holdout_freeze_ready else None
    )
    return {
        "schema_version": 2,
        "loop_run_id": kwargs["run_id"],
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_commit": kwargs["git_commit"],
        "raw_root": str(config.raw_root),
        "execution_profile": (
            "production_protocol" if config.required_days == REQUIRED_DAYS else "fixture_smoke_non_production"
        ),
        "fixture_data_only": config.required_days is None,
        "max_cycles": config.max_cycles,
        "cycles_executed": len(cycles),
        "stop_reason": kwargs["stop_reason"],
        "target_reached": False,
        "target_status": "not_evaluated_no_sealed_holdout_run",
        "target_usdc_per_day": TARGET_USDC_PER_DAY,
        "best_candidate": kwargs["best_candidate"],
        "best_validation_result": best_validation_result,
        "frozen_candidate": frozen_candidate,
        "freeze_status": _freeze_status(config, frozen_candidate, active_holdout),
        "candidate_stage_totals": stage_totals,
        "resource_budget": _resource_budget(config),
        "loop_resource_budget": {
            "max_cycles": config.max_cycles,
            "selection_candidate_days_cap": (
                _selection_candidate_day_cap(config) * config.max_cycles
            ),
            "selection_candle_evaluations_cap": (
                _selection_candidate_day_cap(config) * config.max_cycles * 1440
            ),
            "selection_total_candidate_days_cap": (
                _resource_budget(config)["selection_total_candidate_days_cap"]
                * config.max_cycles
            ),
            "selection_total_candle_evaluations_cap": (
                _resource_budget(config)[
                    "selection_total_candle_evaluations_cap"
                ]
                * config.max_cycles
            ),
        },
        "cycles": cycles,
        "window_plan": window_plan,
        "audit_policy": {
            "consumed_audit_window": active_consumed,
            "evaluated_in_research_loop": False,
            "affects_selection": False,
            "allowed_uses": ["historical_reference", "defect_analysis"],
            "freeze_eligible": active_holdout_freeze_ready,
            "freeze_blocker": (
                None
                if active_holdout_freeze_ready
                else "final holdout must be 365 days, sealed_unopened, unconsumed, and unevaluated"
            ),
        },
        "quality_gate_version": QUALITY_GATE_V1.version,
        "research_protocol": protocol,
        "all_report_paths": {},
        "safety": safety_status(),
        "safety_status": "ok" if all(_safety_ok(cycle.get("safety", {})) for cycle in cycles) else "violation",
        "result_text": "Final holdout not evaluated; +3 USDC/day target not evaluated.",
    }


def _resource_budget(config: LoopConfig) -> dict[str, int]:
    candidate_days = _selection_candidate_day_cap(config)
    stress_days = (
        config.finalists_per_cycle
        * STRESS_PROFILES_BEYOND_BASELINE
        * TRAINING_DAYS
    )
    parameter_days = (
        config.finalists_per_cycle
        * PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER
        * MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS
        * INTERNAL_VALIDATION_DAYS
    )
    total_days = candidate_days + stress_days + parameter_days
    return {
        "generated_cap": config.max_candidates_per_cycle,
        "tested_cap": config.tested_candidates_per_cycle,
        "walk_forward_cap": config.walk_forward_candidates_per_cycle,
        "finalists_cap": config.finalists_per_cycle,
        "walk_forward_folds": config.walk_forward_fold_count,
        "rolling_origin_cap": config.rolling_origin_limit,
        "selection_candidate_days_cap": candidate_days,
        "selection_candle_evaluations_cap": candidate_days * 1440,
        "stress_evidence_candidate_days_cap": stress_days,
        "parameter_evidence_candidate_days_cap": parameter_days,
        "selection_total_candidate_days_cap": total_days,
        "selection_total_candle_evaluations_cap": total_days * 1440,
        "max_numeric_parameters_per_finalist": (
            MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS
        ),
    }


def _selection_candidate_day_cap(config: LoopConfig) -> int:
    testing = config.tested_candidates_per_cycle * TRAINING_DAYS
    walk_forward = config.walk_forward_candidates_per_cycle * TRAINING_DAYS
    full_training = config.finalists_per_cycle * TRAINING_DAYS
    historical_replay = (
        config.finalists_per_cycle * config.rolling_origin_limit * BLINDTEST_DAYS
    )
    return testing + walk_forward + full_training + historical_replay


def _window_plan_summary(plan: ResearchWindowPlan) -> dict[str, Any]:
    final = plan.final_window
    overlaps_consumed = any(
        not (final.blind_end < window["start"] or final.blind_start > window["end"])
        for window in CONSUMED_AUDIT_WINDOWS
    )
    return {
        "latest_complete_utc_day": plan.latest_complete_day,
        "available_complete_days": plan.available_complete_days,
        "training_window": {
            "start": final.training_start,
            "end": final.training_end,
            "days": final.training_days,
        },
        "final_holdout_window": {
            "start": final.blind_start,
            "end": final.blind_end,
            "days": final.blindtest_days,
            "status": "consumed" if overlaps_consumed else "sealed_unopened",
            "consumed_audit_window": overlaps_consumed,
            "evaluated": False,
        },
        "historical_origin_count": plan.historical_origin_count,
        "skipped_historical_origin_count": plan.skipped_historical_origin_count,
        "skipped_historical_origins": list(plan.skipped_historical_origins),
        "historical_origins": [
            {
                "training_start": origin.training_start,
                "training_end": origin.training_end,
                "oos_start": origin.blind_start,
                "oos_end": origin.blind_end,
                "uses_final_audit": False,
            }
            for origin in plan.historical_origins
        ],
    }


def _record_loop_report(report: dict[str, Any], reports_root: str | Path) -> ExperimentPaths:
    _validate_loop_report_contract(report)
    root = Path(reports_root)
    root.mkdir(parents=True, exist_ok=True)
    json_path = _unique_path(root / f"{report['loop_run_id']}.json")
    txt_path = json_path.with_suffix(".txt")
    stored = dict(report)
    stored["loop_run_id"] = json_path.stem
    stored["all_report_paths"] = {
        "json": str(json_path),
        "txt": str(txt_path),
        "index": str(root / "index.jsonl"),
    }
    json_path.write_text(json.dumps(stored, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    txt_path.write_text(_format_loop_text(stored), encoding="utf-8")
    index_path = root / "index.jsonl"
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "loop_run_id": stored["loop_run_id"],
                    "timestamp": stored["timestamp"],
                    "stop_reason": stored["stop_reason"],
                    "target_reached": False,
                    "json": str(json_path),
                    "txt": str(txt_path),
                },
                sort_keys=True,
            )
            + "\n"
        )
    return ExperimentPaths(json_path=json_path, txt_path=txt_path, index_path=index_path)


def _validate_loop_report_contract(report: dict[str, Any]) -> None:
    required_top = {
        "loop_run_id",
        "window_plan",
        "research_protocol",
        "cycles",
        "candidate_stage_totals",
        "audit_policy",
        "safety_status",
    }
    if not required_top.issubset(report):
        raise RuntimeError("Protocol-v2 report is missing canonical top-level paths")
    protocol = report.get("research_protocol")
    cycles = report.get("cycles")
    if not isinstance(protocol, dict) or not isinstance(cycles, list):
        raise RuntimeError("Protocol-v2 report protocol/cycles shape is invalid")
    parameter_space = protocol.get("parameter_space")
    if (
        not isinstance(parameter_space, dict)
        or parameter_space.get("source") != "generated_candidate_inventory"
        or not isinstance(parameter_space.get("cycles"), list)
        or len(parameter_space["cycles"]) != len(cycles)
    ):
        raise RuntimeError("Protocol-v2 report parameter inventory is missing")
    required_cycle = {
        "generated_candidate_inventory",
        "candidate_leaderboard_summary",
        "walk_forward_summaries",
        "finalist_summaries",
    }
    if any(not isinstance(cycle, dict) or not required_cycle.issubset(cycle) for cycle in cycles):
        raise RuntimeError("Protocol-v2 report is missing canonical per-cycle result paths")


def _format_loop_text(report: dict[str, Any]) -> str:
    lines = [
        "ETHUSDC Offline Research Loop - Protocol v2",
        f"Loop-Run-ID: {report.get('loop_run_id')}",
        f"Git commit: {report.get('git_commit')}",
        f"Raw root: {report.get('raw_root')}",
        f"Cycles executed: {report.get('cycles_executed')}/{report.get('max_cycles')}",
        f"Stop reason: {report.get('stop_reason')}",
        "Holdout evaluated: False",
        "Consumed audit affects selection: False",
        f"Candidate stage totals: {report.get('candidate_stage_totals')}",
        f"Best validation: {report.get('best_validation_result')}",
        f"Freeze status: {report.get('freeze_status')}",
        str(report.get("result_text")),
        "Live/Paper/Testtrade locked. No orders, no Trading API, no API keys.",
    ]
    for cycle in report.get("cycles", []):
        lines.append(
            f"Cycle {cycle.get('cycle_id')}: generated={cycle.get('generated_candidates')} "
            f"tested={cycle.get('tested_candidates')} walk_forward={cycle.get('walk_forward_candidates')} "
            f"finalists={cycle.get('finalists')} best_validation={cycle.get('best_validation_candidate')}"
        )
    lines.append("")
    return "\n".join(lines)


def _jsonable_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if hasattr(value, "to_dict"):
            return convert(value.to_dict())
        if isinstance(value, StrategyCandidate):
            return {"family": value.family, "params": dict(value.params)}
        if isinstance(value, dict):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if isinstance(value, float) and not isfinite(value):
            return str(value)
        return value

    return convert(cycle)


def _safety_ok(safety: dict[str, Any]) -> bool:
    required = safety_status()
    return all(safety.get(key) == value for key, value in required.items())


def _calendar_day_count(candles: list[Candle]) -> int:
    days = {datetime.fromtimestamp(candle.open_time / 1000, tz=UTC).date() for candle in candles}
    return max(1, len(days))


def _split_subtrain_validation_on_utc_days(
    training: list[Candle],
) -> tuple[list[Candle], list[Candle]]:
    days = sorted(
        {datetime.fromtimestamp(candle.open_time / 1000, tz=UTC).date() for candle in training}
    )
    if len(days) < 2:
        raise RuntimeError("at least two complete UTC training days are required for subtrain/validation")
    validation_day_count = max(1, len(days) // 5)
    validation_days = set(days[-validation_day_count:])
    subtrain = [
        candle
        for candle in training
        if datetime.fromtimestamp(candle.open_time / 1000, tz=UTC).date() not in validation_days
    ]
    validation = [
        candle
        for candle in training
        if datetime.fromtimestamp(candle.open_time / 1000, tz=UTC).date() in validation_days
    ]
    if not subtrain or not validation:
        raise RuntimeError("could not build complete-day subtrain/validation windows")
    return subtrain, validation


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index:03d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("could not allocate unique loop report path")


def _git_commit() -> str:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], check=True, text=True, capture_output=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--short"], check=True, text=True, capture_output=True
        ).stdout.strip()
        return f"{commit}-dirty" if status else commit
    except Exception:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run leakage-safe ETHUSDC research. No orders/API/live.")
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    parser.add_argument("--reports-root", default="reports/research_loop")
    parser.add_argument("--max-cycles", type=int, default=8)
    parser.add_argument("--max-candidates-per-cycle", type=int, default=40)
    parser.add_argument("--tested-candidates-per-cycle", type=int, default=12)
    parser.add_argument("--walk-forward-candidates-per-cycle", type=int, default=3)
    parser.add_argument("--finalists-per-cycle", type=int, default=2)
    parser.add_argument("--walk-forward-folds", type=int, default=6)
    parser.add_argument("--rolling-origin-limit", type=int, default=3)
    parser.add_argument("--fixture-smoke", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = LoopConfig(
        raw_root=args.raw_root,
        reports_root=args.reports_root,
        max_cycles=args.max_cycles,
        max_candidates_per_cycle=args.max_candidates_per_cycle,
        tested_candidates_per_cycle=args.tested_candidates_per_cycle,
        walk_forward_candidates_per_cycle=args.walk_forward_candidates_per_cycle,
        finalists_per_cycle=args.finalists_per_cycle,
        walk_forward_fold_count=args.walk_forward_folds,
        rolling_origin_limit=args.rolling_origin_limit,
        required_days=None if args.fixture_smoke else REQUIRED_DAYS,
    )
    result = run_research_loop(config)
    print(f"Research loop run_id: {result.loop_run_id}")
    print(f"Report JSON: {result.report_paths.json_path}")
    print(f"Report TXT: {result.report_paths.txt_path}")
    print(f"Cycles executed: {result.cycles_executed}")
    print(f"Stop reason: {result.stop_reason}")
    print("Final holdout was not evaluated; +3 USDC/day target was not evaluated.")
    print("Live/Paper/Testtrade bleiben gesperrt. Keine Orders/API-Keys/Trading API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
