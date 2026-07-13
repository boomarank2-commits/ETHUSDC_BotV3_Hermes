import json
from pathlib import Path

import pytest

from ethusdc_bot.backtest import research_supervisor as supervisor
from ethusdc_bot.backtest.research_protocol import safety_status


def _cycle_payload(*, safe: bool = True) -> dict[str, object]:
    safety = safety_status()
    if not safe:
        safety["live"] = "unlocked"
    return {
        "cycle_id": 1,
        "generated_candidates": 40,
        "tested_candidates": 12,
        "walk_forward_candidates": 3,
        "finalists": 2,
        "context_research": {
            "enabled": True,
            "uses_audit_or_holdout": False,
        },
        "selection_source": "subtrain_validation_walk_forward_only",
        "wfv_summary": {
            "fold_count": 6,
            "ranking_uses_blindtest": False,
        },
        "rolling_origin_summary": {"uses_final_audit": False},
        "safety": safety,
    }


def _write_runner_resume(tmp_path: Path, *, safe: bool) -> Path:
    cycle_name = "research_loop_example.cycle-01.json"
    (tmp_path / cycle_name).write_text(
        json.dumps(_cycle_payload(safe=safe)),
        encoding="utf-8",
    )
    path = tmp_path / "research_loop_example.resume.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_kind": "research_loop_resume_state",
                "run_id": "research_loop_example",
                "completed_cycle_count": 1,
                "cycle_files": [cycle_name],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_runner_resume_revalidates_canonical_cycle_safety(tmp_path: Path) -> None:
    path = _write_runner_resume(tmp_path, safe=True)

    supervisor._validate_runner_resume_state(
        path,
        expected_run_id="research_loop_example",
        context_required=True,
    )


def test_runner_resume_rejects_persisted_unsafe_cycle(tmp_path: Path) -> None:
    path = _write_runner_resume(tmp_path, safe=False)

    with pytest.raises(RuntimeError, match="canonical safety"):
        supervisor._validate_runner_resume_state(
            path,
            expected_run_id="research_loop_example",
            context_required=True,
        )


def test_runner_resume_requires_state_when_supervisor_has_completed_cycles(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="runner resume state is missing"):
        supervisor._validate_runner_resume_state(
            tmp_path / "missing.resume.json",
            expected_run_id="research_loop_example",
            context_required=True,
            required=True,
        )


def test_context_resume_checkpoint_requires_bound_runtime_proof(tmp_path: Path) -> None:
    path = tmp_path / "production_research_example.checkpoint.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_kind": "research_supervisor_checkpoint",
                "run_id": "production_research_example",
                "max_cycles": 8,
                "completed_cycle_count": 1,
                "cycles": [
                    {
                        "cycle": 1,
                        "maximum": 8,
                        "generated": 40,
                        "tested": 12,
                        "walk_forward": 3,
                        "finalists": 2,
                        "selected_rank_text": "(0.0,)",
                        "runtime_proof": None,
                    }
                ],
                "started_at_utc": "2026-07-13T00:00:00Z",
                "report_json": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="canonical context proof"):
        supervisor._resume_checkpoint(
            path,
            expected_run_id="production_research_example",
            expected_max_cycles=8,
            context_required=True,
        )
