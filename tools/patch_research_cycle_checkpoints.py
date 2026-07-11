from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "src/ethusdc_bot/backtest/research_loop_runner.py"
TESTS = ROOT / "tests/unit/test_research_loop_runner.py"

runner = RUNNER.read_text(encoding="utf-8")

old_cycle = '''        stored_cycle = _jsonable_cycle(cycle)
        cycles.append(stored_cycle)
        if not _safety_ok(cycle.get("safety", {})):
'''
new_cycle = '''        stored_cycle = _jsonable_cycle(cycle)
        cycles.append(stored_cycle)
        checkpoint_path = _write_cycle_checkpoint(
            run_id=run_id,
            git_commit=git_commit,
            config=config,
            cycles=cycles,
            status="running",
            stop_reason=None,
            final_report_paths=None,
        )
        print(
            f"cycle {cycle_index}/{config.max_cycles}: checkpoint={checkpoint_path}",
            flush=True,
        )
        if not _safety_ok(cycle.get("safety", {})):
'''
if old_cycle not in runner:
    raise SystemExit("cycle insertion anchor not found or already patched")
runner = runner.replace(old_cycle, new_cycle, 1)

old_final = '''    paths = _record_loop_report(report, config.reports_root)
    return LoopRunResult(run_id, len(cycles), stop_reason, False, best_candidate, paths)
'''
new_final = '''    paths = _record_loop_report(report, config.reports_root)
    checkpoint_path = _write_cycle_checkpoint(
        run_id=run_id,
        git_commit=git_commit,
        config=config,
        cycles=cycles,
        status="completed",
        stop_reason=stop_reason,
        final_report_paths={
            "json": str(paths.json_path),
            "txt": str(paths.txt_path),
            "index": str(paths.index_path),
        },
    )
    print(f"Checkpoint JSON: {checkpoint_path}", flush=True)
    return LoopRunResult(run_id, len(cycles), stop_reason, False, best_candidate, paths)
'''
if old_final not in runner:
    raise SystemExit("finalization insertion anchor not found or already patched")
runner = runner.replace(old_final, new_final, 1)

anchor = '''def _record_loop_report(report: dict[str, Any], reports_root: str | Path) -> ExperimentPaths:
'''
checkpoint_function = '''def _write_cycle_checkpoint(
    *,
    run_id: str,
    git_commit: str,
    config: LoopConfig,
    cycles: list[dict[str, Any]],
    status: str,
    stop_reason: str | None,
    final_report_paths: dict[str, str] | None,
) -> Path:
    """Atomically persist completed-cycle evidence for long local runs.

    The checkpoint is an observation and handoff artifact, not a resume token.
    Only fully validated cycles are included. Audit and final holdout evaluation
    remain explicitly false, and strict JSON rejects non-finite leakage.
    """

    if status not in {"running", "completed"}:
        raise ValueError("cycle checkpoint status must be running or completed")
    if not cycles:
        raise ValueError("cycle checkpoint requires at least one completed cycle")
    if status == "running" and (stop_reason is not None or final_report_paths is not None):
        raise ValueError("running checkpoint cannot contain final report metadata")
    if status == "completed" and (not stop_reason or not final_report_paths):
        raise ValueError("completed checkpoint requires stop reason and final report paths")

    root = Path(config.reports_root)
    root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = root / f"{run_id}.checkpoint.json"
    temporary_path = checkpoint_path.with_name(checkpoint_path.name + ".tmp")
    last_cycle = cycles[-1]
    payload = {
        "schema_version": 1,
        "artifact_kind": "research_cycle_checkpoint",
        "loop_run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_commit": git_commit,
        "execution_profile": (
            "production_protocol"
            if config.required_days == REQUIRED_DAYS
            else "fixture_smoke_non_production"
        ),
        "status": status,
        "completed_cycles": len(cycles),
        "max_cycles": config.max_cycles,
        "last_completed_cycle": last_cycle.get("cycle_id"),
        "next_cycle_index": (
            len(cycles) + 1 if status == "running" and len(cycles) < config.max_cycles else None
        ),
        "resume_supported": False,
        "resume_policy": "rerun_from_bound_git_commit_and_compare_completed_cycle_evidence",
        "stop_reason": stop_reason,
        "final_report_paths": final_report_paths,
        "candidate_stage_totals": {
            "generated": sum(int(cycle.get("generated_candidates", 0)) for cycle in cycles),
            "tested": sum(int(cycle.get("tested_candidates", 0)) for cycle in cycles),
            "walk_forward": sum(
                int(cycle.get("walk_forward_candidates", 0)) for cycle in cycles
            ),
            "finalists": sum(int(cycle.get("finalists", 0)) for cycle in cycles),
        },
        "audit_policy": {
            "evaluated_in_research_loop": False,
            "affects_selection": False,
        },
        "final_holdout_evaluated": False,
        "safety": safety_status(),
        "last_cycle_safety": last_cycle.get("safety"),
        "cycles": cycles,
    }
    temporary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    temporary_path.replace(checkpoint_path)
    return checkpoint_path


'''
if anchor not in runner:
    raise SystemExit("checkpoint function anchor not found")
runner = runner.replace(anchor, checkpoint_function + anchor, 1)
RUNNER.write_text(runner, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
addition = '''

def test_cycle_checkpoint_is_atomically_finalized_with_the_report(tmp_path):
    result = run_research_loop(
        _config(tmp_path),
        cycle_runner=lambda cycle_index, state: _cycle(
            f"candidate_{cycle_index}", validation=-0.1 * cycle_index
        ),
    )

    checkpoints = list(tmp_path.glob("research_loop_*.checkpoint.json"))
    assert len(checkpoints) == 1
    data = json.loads(checkpoints[0].read_text(encoding="utf-8"))
    assert data["artifact_kind"] == "research_cycle_checkpoint"
    assert data["status"] == "completed"
    assert data["completed_cycles"] == 3
    assert data["last_completed_cycle"] == 3
    assert data["next_cycle_index"] is None
    assert data["resume_supported"] is False
    assert data["stop_reason"] == "max_cycles_reached"
    assert data["final_report_paths"]["json"] == str(result.report_paths.json_path)
    assert data["audit_policy"] == {
        "evaluated_in_research_loop": False,
        "affects_selection": False,
    }
    assert data["final_holdout_evaluated"] is False
    assert data["safety"]["orders"] == "not_created"
    assert data["candidate_stage_totals"] == {
        "generated": 6,
        "tested": 6,
        "walk_forward": 3,
        "finalists": 3,
    }


def test_completed_cycle_checkpoint_survives_a_later_cycle_exception(tmp_path):
    def interrupted_runner(cycle_index, state):
        if cycle_index == 2:
            raise RuntimeError("synthetic interruption")
        return _cycle("candidate_1", validation=-0.2)

    with pytest.raises(RuntimeError, match="synthetic interruption"):
        run_research_loop(_config(tmp_path), cycle_runner=interrupted_runner)

    checkpoints = list(tmp_path.glob("research_loop_*.checkpoint.json"))
    assert len(checkpoints) == 1
    data = json.loads(checkpoints[0].read_text(encoding="utf-8"))
    assert data["status"] == "running"
    assert data["completed_cycles"] == 1
    assert data["last_completed_cycle"] == 1
    assert data["next_cycle_index"] == 2
    assert data["stop_reason"] is None
    assert data["final_report_paths"] is None
    assert data["resume_supported"] is False
    assert data["cycles"][0]["cycle_id"] == 1
    assert data["audit_policy"]["evaluated_in_research_loop"] is False
    assert data["final_holdout_evaluated"] is False
'''
if "test_cycle_checkpoint_is_atomically_finalized_with_the_report" in tests:
    raise SystemExit("checkpoint tests already present")
TESTS.write_text(tests.rstrip() + addition + "\n", encoding="utf-8")
