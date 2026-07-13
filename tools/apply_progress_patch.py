"""Apply the reviewed granular research-progress patch once.

This temporary helper performs exact replacements and fails closed when the
expected Codex/GPT-reviewed source text is not present.
"""

from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path}: expected exactly one replacement, found {count}\n"
            f"--- expected source ---\n{old}"
        )
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_runner() -> None:
    path = "src/ethusdc_bot/backtest/research_loop_runner.py"
    replace_once(
        path,
        "from ethusdc_bot.backtest.quality_gates import QUALITY_GATE_V1, evaluate_quality_gates\nfrom ethusdc_bot.backtest.research_protocol import (\n",
        "from ethusdc_bot.backtest.quality_gates import QUALITY_GATE_V1, evaluate_quality_gates\nfrom ethusdc_bot.backtest.research_progress import ResearchProgressEmitter\nfrom ethusdc_bot.backtest.research_protocol import (\n",
    )
    replace_once(
        path,
        '''MAX_SELECTION_EVIDENCE_CANDIDATE_DAYS_PER_CYCLE = (
    CANDIDATE_STAGE_BUDGETS["finalists"]
    * (
        STRESS_PROFILES_BEYOND_BASELINE * TRAINING_DAYS
        + PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER
        * MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS
        * INTERNAL_VALIDATION_DAYS
    )
)


@dataclass(frozen=True)
''',
        '''MAX_SELECTION_EVIDENCE_CANDIDATE_DAYS_PER_CYCLE = (
    CANDIDATE_STAGE_BUDGETS["finalists"]
    * (
        STRESS_PROFILES_BEYOND_BASELINE * TRAINING_DAYS
        + PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER
        * MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS
        * INTERNAL_VALIDATION_DAYS
    )
)
TOTAL_CYCLE_PROGRESS_UNITS = (
    MAX_SELECTION_CANDIDATE_DAYS_PER_CYCLE
    + MAX_SELECTION_EVIDENCE_CANDIDATE_DAYS_PER_CYCLE
)


@dataclass(frozen=True)
''',
    )
    replace_once(
        path,
        '''    git_commit = _git_commit()
    run_id = config.run_id or datetime.now(UTC).strftime("research_loop_%Y%m%dT%H%M%SZ")
    resume_path = _resume_state_path(config, run_id)
    (
        cycles,
        state,
        best_selection_rank,
        best_candidate,
        no_improvement,
    ) = _load_resume_state(config, run_id, git_commit, resume_path)
    start_cycle = len(cycles) + 1
    stop_reason = "max_cycles_reached"
    runner = cycle_runner or _build_real_cycle_runner(config)
''',
        '''    git_commit = _git_commit()
    run_id = config.run_id or datetime.now(UTC).strftime("research_loop_%Y%m%dT%H%M%SZ")
    resume_path = _resume_state_path(config, run_id)
    progress = ResearchProgressEmitter(config.reports_root, run_id, config.max_cycles)
    (
        cycles,
        state,
        best_selection_rank,
        best_candidate,
        no_improvement,
    ) = _load_resume_state(config, run_id, git_commit, resume_path)
    progress.restore_completed(len(cycles))
    start_cycle = len(cycles) + 1
    stop_reason = "max_cycles_reached"
    runner = cycle_runner or _build_real_cycle_runner(config, progress=progress)
''',
    )
    replace_once(
        path,
        '''    for cycle_index in range(start_cycle, config.max_cycles + 1):
        print(f"cycle {cycle_index}/{config.max_cycles}: starting", flush=True)
''',
        '''    for cycle_index in range(start_cycle, config.max_cycles + 1):
        progress.start_cycle(
            cycle_index,
            total_work_units=TOTAL_CYCLE_PROGRESS_UNITS,
        )
        print(f"cycle {cycle_index}/{config.max_cycles}: starting", flush=True)
''',
    )
    replace_once(
        path,
        '''        current_selection_rank = _cycle_selected_rank(cycle)
        print(
''',
        '''        current_selection_rank = _cycle_selected_rank(cycle)
        progress.complete_cycle(cycle_index)
        print(
''',
    )
    replace_once(
        path,
        '''    paths = _record_loop_report(report, config.reports_root)
    return LoopRunResult(run_id, len(cycles), stop_reason, False, best_candidate, paths)
''',
        '''    paths = _record_loop_report(report, config.reports_root)
    progress.complete_run(stop_reason=stop_reason, cycles_executed=len(cycles))
    return LoopRunResult(run_id, len(cycles), stop_reason, False, best_candidate, paths)
''',
    )
    replace_once(
        path,
        "def _build_real_cycle_runner(config: LoopConfig) -> Callable[[int, SearchSpaceState], dict[str, Any]]:\n",
        '''def _build_real_cycle_runner(
    config: LoopConfig,
    *,
    progress: ResearchProgressEmitter | None = None,
) -> Callable[[int, SearchSpaceState], dict[str, Any]]:
''',
    )
    replace_once(
        path,
        '''    def runner(cycle_index: int, state: SearchSpaceState) -> dict[str, Any]:
        generated = generate_search_space(
''',
        '''    def runner(cycle_index: int, state: SearchSpaceState) -> dict[str, Any]:
        completed_work_units = 0

        def advance_progress(units: int, stage: str, message: str) -> None:
            nonlocal completed_work_units
            completed_work_units += max(0, int(units))
            if progress is not None:
                progress.update_cycle(
                    cycle_index,
                    stage=stage,
                    completed_work_units=completed_work_units,
                    message=message,
                )

        generated = generate_search_space(
''',
    )
    replace_once(
        path,
        '''        records: list[dict[str, Any]] = []
        for row in tested_rows:
            candidate = row["candidate"]
''',
        '''        records: list[dict[str, Any]] = []
        for tested_index, row in enumerate(tested_rows, start=1):
            candidate = row["candidate"]
''',
    )
    replace_once(
        path,
        '''            records.append(
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
''',
        '''            records.append(
                {
                    "candidate_id": row["candidate_id"],
                    "candidate": candidate,
                    "training_result": train_result,
                    "validation_result": validation_result,
                    "training_metrics": train_result.metrics,
                    "validation_metrics": validation_result.metrics,
                }
            )
            advance_progress(
                subtrain_days + validation_days,
                "training_validation",
                f"Training/Validation Kandidat {tested_index}/{len(tested_rows)} abgeschlossen",
            )
        if not records:
''',
    )
    replace_once(
        path,
        '''        wfv_ranked = rank_with_walk_forward(wfv_records)
        finalist_records = wfv_ranked[: config.finalists_per_cycle]
        for record in finalist_records:
''',
        '''        advance_progress(
            len(wfv_records) * TRAINING_DAYS,
            "walk_forward",
            f"Walk-Forward {len(wfv_records)}/{config.walk_forward_candidates_per_cycle} Kandidaten abgeschlossen",
        )
        wfv_ranked = rank_with_walk_forward(wfv_records)
        finalist_records = wfv_ranked[: config.finalists_per_cycle]
        for finalist_index, record in enumerate(finalist_records, start=1):
''',
    )
    replace_once(
        path,
        '''            record["full_training_result"] = full_training_result
            record["rolling_origin_summary"] = evaluate_rolling_origins(
''',
        '''            record["full_training_result"] = full_training_result
            advance_progress(
                TRAINING_DAYS,
                "finalist_full_training",
                f"Finalist {finalist_index}/{len(finalist_records)}: volles Training abgeschlossen",
            )
            record["rolling_origin_summary"] = evaluate_rolling_origins(
''',
    )
    replace_once(
        path,
        '''                market_context=market_context,
            )
            joint_stress_wfv = evaluate_walk_forward(
''',
        '''                market_context=market_context,
            )
            advance_progress(
                config.rolling_origin_limit * config.rolling_origin_step_days,
                "rolling_origins",
                f"Finalist {finalist_index}/{len(finalist_records)}: Rolling-Origin-Prüfung abgeschlossen",
            )
            joint_stress_wfv = evaluate_walk_forward(
''',
    )
    replace_once(
        path,
        '''                market_context=training_context,
            )
            slippage_stress_wfv = evaluate_walk_forward(
''',
        '''                market_context=training_context,
            )
            advance_progress(
                TRAINING_DAYS,
                "joint_cost_stress",
                f"Finalist {finalist_index}/{len(finalist_records)}: kombinierter Kostenstress abgeschlossen",
            )
            slippage_stress_wfv = evaluate_walk_forward(
''',
    )
    replace_once(
        path,
        '''                market_context=training_context,
            )
            baseline_selection = record["walk_forward_summary"].get(
''',
        '''                market_context=training_context,
            )
            advance_progress(
                TRAINING_DAYS,
                "slippage_stress",
                f"Finalist {finalist_index}/{len(finalist_records)}: Slippage-Stress abgeschlossen",
            )
            baseline_selection = record["walk_forward_summary"].get(
''',
    )
    replace_once(
        path,
        '''                },
            }
            evidence = _quality_evidence(record, full_training_result)
''',
        '''                },
            }
            advance_progress(
                PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER
                * MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS
                * INTERNAL_VALIDATION_DAYS,
                "parameter_stability",
                f"Finalist {finalist_index}/{len(finalist_records)}: Parameterstabilität abgeschlossen",
            )
            evidence = _quality_evidence(record, full_training_result)
''',
    )


def patch_display() -> None:
    path = "src/ethusdc_bot/ui/backtest_display.py"
    helper = '''\n\ndef _read_research_progress(\n    root: Path,\n    checkpoint: Mapping[str, Any],\n) -> dict[str, Any] | None:\n    supervisor_run_id = checkpoint.get("run_id")\n    if not isinstance(supervisor_run_id, str) or not supervisor_run_id:\n        return None\n    runner_run_id = supervisor_run_id.replace(\n        "production_research_", "research_loop_", 1\n    )\n    path = root / f"{runner_run_id}.progress.json"\n    try:\n        payload = json.loads(path.read_text(encoding="utf-8"))\n    except (OSError, UnicodeError, json.JSONDecodeError):\n        return None\n    if not isinstance(payload, dict):\n        return None\n    if payload.get("schema_version") != 1:\n        return None\n    if payload.get("artifact_kind") != "research_loop_progress":\n        return None\n    if payload.get("run_id") != runner_run_id:\n        return None\n    return payload\n\n\ndef _running_progress_values(\n    *,\n    status: str,\n    completed_cycles: int,\n    max_cycles: int,\n    active_cycle: int | None,\n    live_progress: Mapping[str, Any] | None,\n) -> tuple[float, float, str | None, str | None]:\n    if status == "completed":\n        return 100.0, 100.0, "run_complete", "Backtest abgeschlossen"\n    baseline = min(completed_cycles, max_cycles) / max_cycles * 100.0\n    if active_cycle is None or not isinstance(live_progress, Mapping):\n        return round(baseline, 1), 0.0, None, None\n    try:\n        progress_cycle = int(live_progress.get("active_cycle"))\n        cycle_pct = float(live_progress.get("cycle_progress_pct"))\n        overall_pct = float(live_progress.get("overall_progress_pct"))\n    except (TypeError, ValueError, OverflowError):\n        return round(baseline, 1), 0.0, None, None\n    if progress_cycle != active_cycle:\n        return round(baseline, 1), 0.0, None, None\n    upper = min(100.0, (completed_cycles + 1) / max_cycles * 100.0)\n    overall_pct = min(upper, max(baseline, overall_pct))\n    cycle_pct = min(99.5, max(0.0, cycle_pct))\n    stage = live_progress.get("stage")\n    message = live_progress.get("message")\n    return (\n        round(overall_pct, 3),\n        round(cycle_pct, 3),\n        str(stage) if stage else None,\n        str(message) if message else None,\n    )\n'''
    replace_once(
        path,
        '''    progress = 100.0 if status == "completed" else round(
        min(completed_cycles, max_cycles) / max_cycles * 100.0,
        1,
    )
''',
        '''    live_progress = _read_research_progress(root, checkpoint)
    progress, cycle_progress, progress_stage, progress_message = _running_progress_values(
        status=status,
        completed_cycles=completed_cycles,
        max_cycles=max_cycles,
        active_cycle=active_cycle,
        live_progress=live_progress,
    )
''',
    )
    replace_once(
        path,
        '''        "progress_pct": progress,
        "progress_visible": mode in {"starting", "running"},
        "completed_cycles": completed_cycles,
''',
        '''        "progress_pct": progress,
        "cycle_progress_pct": cycle_progress,
        "progress_stage": progress_stage,
        "progress_message": progress_message,
        "progress_visible": mode in {"starting", "running"},
        "completed_cycles": completed_cycles,
''',
    )
    replace_once(
        path,
        '''        "progress_pct": 100.0,
        "progress_visible": False,
        "completed_cycles": completed,
''',
        '''        "progress_pct": 100.0,
        "cycle_progress_pct": 100.0,
        "progress_stage": "run_complete",
        "progress_message": "Backtest abgeschlossen",
        "progress_visible": False,
        "completed_cycles": completed,
''',
    )
    replace_once(
        path,
        '''        "progress_pct": 0.0,
        "progress_visible": mode in {"starting", "running"},
        "completed_cycles": 0,
''',
        '''        "progress_pct": 0.0,
        "cycle_progress_pct": 0.0,
        "progress_stage": None,
        "progress_message": None,
        "progress_visible": mode in {"starting", "running"},
        "completed_cycles": 0,
''',
    )
    replace_once(
        path,
        "\ndef format_backtest_summary_for_display(status: Mapping[str, Any]) -> str:\n",
        helper + "\n\ndef format_backtest_summary_for_display(status: Mapping[str, Any]) -> str:\n",
    )


def patch_operator_dashboard() -> None:
    replace_once(
        "src/ethusdc_bot/ui/operator_dashboard.py",
        '''        f"Fortschritt: {_number(status.get('progress_pct'), 1)} %",
        f"Zyklen: {completed}/{maximum} vollständig; aktiv {_text(status.get('active_cycle'))}",
''',
        '''        f"Fortschritt gesamt: {_number(status.get('progress_pct'), 2)} %",
        f"Fortschritt aktiver Zyklus: {_number(status.get('cycle_progress_pct'), 1)} %",
        f"Aktueller Rechenschritt: {_text(status.get('progress_message') or status.get('progress_stage'))}",
        f"Zyklen: {completed}/{maximum} vollständig; aktiv {_text(status.get('active_cycle'))}",
''',
    )


def patch_dashboard() -> None:
    path = "src/ethusdc_bot/ui/dashboard.py"
    replace_once(path, "        self.progress_var = tk.IntVar(value=0)\n", "        self.progress_var = tk.DoubleVar(value=0.0)\n")
    replace_once(
        path,
        '''        progress = float(status.get("progress_pct", 0.0) or 0.0)
        elapsed = int(status.get("elapsed_seconds", 0) or 0)
''',
        '''        progress = float(status.get("progress_pct", 0.0) or 0.0)
        cycle_progress = float(status.get("cycle_progress_pct", 0.0) or 0.0)
        progress_message = status.get("progress_message") or status.get("progress_stage")
        elapsed = int(status.get("elapsed_seconds", 0) or 0)
''',
    )
    replace_once(
        path,
        '''            self.count_var.set(
                f"Backtestfortschritt: {progress:.1f}% ({completed}/{maximum} Zyklen vollständig)"
            )
            self.task_var.set(f"Aktueller Schritt: {phase}")
''',
        '''            self.count_var.set(
                f"Backtestfortschritt: {progress:.2f}% gesamt / "
                f"{cycle_progress:.1f}% im aktiven Zyklus "
                f"({completed}/{maximum} Zyklen vollständig)"
            )
            self.task_var.set(f"Aktueller Schritt: {progress_message or phase}")
''',
    )
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    expected = text.count("self.progress_var.set(int(progress))")
    if expected != 2:
        raise RuntimeError(
            f"{path}: expected two integer progress assignments, found {expected}"
        )
    file_path.write_text(
        text.replace("self.progress_var.set(int(progress))", "self.progress_var.set(progress)"),
        encoding="utf-8",
    )


def main() -> None:
    patch_runner()
    patch_display()
    patch_operator_dashboard()
    patch_dashboard()


if __name__ == "__main__":
    main()
