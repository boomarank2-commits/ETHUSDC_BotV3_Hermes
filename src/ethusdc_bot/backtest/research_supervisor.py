"""Durable, order-free supervisor for long local Research Protocol v2 runs.

The supervisor does not evaluate candidates and does not alter the canonical
research report. It starts the existing runner as a child process, mirrors its
stdout, and atomically records only already-emitted cycle progress. The final
runner JSON remains the sole performance and quality-gate truth.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence

from ethusdc_bot.backtest.research_protocol import safety_status


_CYCLE_START = re.compile(r"^cycle (?P<cycle>\d+)/(?P<maximum>\d+): starting$")
_CYCLE_COMPLETE = re.compile(
    r"^cycle (?P<cycle>\d+)/(?P<maximum>\d+): "
    r"generated=(?P<generated>\d+) "
    r"tested=(?P<tested>\d+) "
    r"walk_forward=(?P<walk_forward>\d+) "
    r"finalists=(?P<finalists>\d+) "
    r"selected_rank=(?P<selected_rank>.*)$"
)
_REPORT_JSON = re.compile(r"^Report JSON:\s+(?P<path>.+)$")
_CYCLE_PROOF = re.compile(
    r"^cycle (?P<cycle>\d+)/(?P<maximum>\d+) proof: "
    r"context_research\.enabled=(?P<context_enabled>true|false) "
    r"context_generated=(?P<context_generated>\d+) "
    r"context_tested=(?P<context_tested>\d+) "
    r"walk_forward_folds=(?P<walk_forward_folds>\d+) "
    r"rolling_origin_limit=(?P<rolling_origin_limit>\d+) "
    r"audit_evaluated=(?P<audit_evaluated>true|false) "
    r"final_holdout_evaluated=(?P<final_holdout_evaluated>true|false)$"
)


@dataclass(frozen=True)
class CycleRuntimeProof:
    cycle: int
    maximum: int
    context_research_enabled: bool
    context_generated: int
    context_tested: int
    walk_forward_folds: int
    rolling_origin_limit: int
    audit_evaluated: bool
    final_holdout_evaluated: bool


@dataclass(frozen=True)
class CycleProgress:
    cycle: int
    maximum: int
    generated: int
    tested: int
    walk_forward: int
    finalists: int
    selected_rank_text: str
    runtime_proof: CycleRuntimeProof | None = None


def parse_cycle_progress(line: str) -> CycleProgress | None:
    """Parse one canonical completed-cycle line from the existing runner."""

    match = _CYCLE_COMPLETE.fullmatch(line.strip())
    if match is None:
        return None
    values = {key: match.group(key) for key in match.groupdict()}
    cycle = int(values["cycle"])
    maximum = int(values["maximum"])
    if cycle < 1 or maximum < cycle:
        raise ValueError("research cycle progress indexes are invalid")
    return CycleProgress(
        cycle=cycle,
        maximum=maximum,
        generated=int(values["generated"]),
        tested=int(values["tested"]),
        walk_forward=int(values["walk_forward"]),
        finalists=int(values["finalists"]),
        selected_rank_text=values["selected_rank"],
    )


def parse_cycle_runtime_proof(line: str) -> CycleRuntimeProof | None:
    """Parse the fail-closed PR12 context proof emitted after one cycle."""

    match = _CYCLE_PROOF.fullmatch(line.strip())
    if match is None:
        return None
    values = match.groupdict()
    cycle = int(values["cycle"])
    maximum = int(values["maximum"])
    if cycle < 1 or maximum < cycle:
        raise ValueError("research cycle proof indexes are invalid")
    return CycleRuntimeProof(
        cycle=cycle,
        maximum=maximum,
        context_research_enabled=values["context_enabled"] == "true",
        context_generated=int(values["context_generated"]),
        context_tested=int(values["context_tested"]),
        walk_forward_folds=int(values["walk_forward_folds"]),
        rolling_origin_limit=int(values["rolling_origin_limit"]),
        audit_evaluated=values["audit_evaluated"] == "true",
        final_holdout_evaluated=values["final_holdout_evaluated"] == "true",
    )


def _canonical_context_proof(proof: CycleRuntimeProof) -> bool:
    return bool(
        proof.context_research_enabled
        and proof.context_generated == 6
        and proof.context_tested == 2
        and proof.walk_forward_folds == 6
        and proof.rolling_origin_limit == 3
        and proof.audit_evaluated is False
        and proof.final_holdout_evaluated is False
    )


def _canonical_cycle_safety(value: object) -> bool:
    expected = safety_status()
    return bool(
        isinstance(value, Mapping)
        and set(value) == set(expected)
        and all(value.get(key) == expected_value for key, expected_value in expected.items())
    )


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is unreadable: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} root is not an object")
    return payload


def _validate_runner_resume_state(
    path: Path,
    *,
    expected_run_id: str,
    context_required: bool,
) -> None:
    """Revalidate persisted runner cycles before any resumed child is started."""

    if not path.is_file():
        return
    manifest = _read_json_object(path, "runner resume state")
    if manifest.get("schema_version") != 1:
        raise RuntimeError("runner resume state schema is unsupported")
    if manifest.get("artifact_kind") != "research_loop_resume_state":
        raise RuntimeError("runner resume state artifact kind is invalid")
    if manifest.get("run_id") != expected_run_id:
        raise RuntimeError("runner resume state run_id does not match supervisor run")
    raw_files = manifest.get("cycle_files")
    if not isinstance(raw_files, list):
        raise RuntimeError("runner resume state has no cycle file list")
    if manifest.get("completed_cycle_count") != len(raw_files):
        raise RuntimeError("runner resume state completed count does not match cycle files")

    for expected_cycle, raw_name in enumerate(raw_files, start=1):
        if not isinstance(raw_name, str) or Path(raw_name).name != raw_name:
            raise RuntimeError("runner resume state contains an invalid cycle path")
        cycle = _read_json_object(path.parent / raw_name, "runner resume cycle")
        if cycle.get("cycle_id") != expected_cycle:
            raise RuntimeError("runner resume cycle artifacts are not contiguous")
        if not _canonical_cycle_safety(cycle.get("safety")):
            raise RuntimeError(
                f"runner resume cycle {expected_cycle} has no canonical safety contract"
            )
        if not context_required:
            continue
        context = cycle.get("context_research")
        wfv = cycle.get("wfv_summary")
        rolling = cycle.get("rolling_origin_summary")
        stage_counts = (
            cycle.get("generated_candidates"),
            cycle.get("tested_candidates"),
            cycle.get("walk_forward_candidates"),
            cycle.get("finalists"),
        )
        if stage_counts != (40, 12, 3, 2):
            raise RuntimeError(
                f"runner resume cycle {expected_cycle} stage counts are not 40/12/3/2"
            )
        if (
            not isinstance(context, Mapping)
            or context.get("enabled") is not True
            or context.get("uses_audit_or_holdout") is not False
            or cycle.get("selection_source") != "subtrain_validation_walk_forward_only"
            or not isinstance(wfv, Mapping)
            or wfv.get("fold_count") != 6
            or wfv.get("ranking_uses_blindtest") is not False
            or not isinstance(rolling, Mapping)
            or rolling.get("uses_final_audit") is not False
        ):
            raise RuntimeError(
                f"runner resume cycle {expected_cycle} violates the context/audit contract"
            )


def _checkpoint_cycle(progress: CycleProgress) -> dict[str, object]:
    row = asdict(progress)
    proof = progress.runtime_proof
    row["runtime_proof"] = (
        {
            "context_research": {"enabled": proof.context_research_enabled},
            "context_generated": proof.context_generated,
            "context_tested": proof.context_tested,
            "walk_forward_folds": proof.walk_forward_folds,
            "rolling_origin_limit": proof.rolling_origin_limit,
            "audit_evaluated": proof.audit_evaluated,
            "final_holdout_evaluated": proof.final_holdout_evaluated,
        }
        if proof is not None
        else None
    )
    return row


def _parse_supervisor_arguments(argv: Sequence[str]) -> tuple[Path, int, str | None, str | None]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--reports-root", default="reports/research_loop")
    parser.add_argument("--max-cycles", type=int, default=8)
    parser.add_argument("--run-id")
    parser.add_argument("--resume-state")
    known, _ = parser.parse_known_args(list(argv))
    if known.max_cycles < 1 or known.max_cycles > 8:
        raise ValueError("max-cycles must be between 1 and 8")
    return Path(known.reports_root), known.max_cycles, known.run_id, known.resume_state


def _git_value(*arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _checkpoint_payload(
    *,
    run_id: str,
    status: str,
    max_cycles: int,
    started_at_utc: str,
    completed_cycles: Sequence[CycleProgress],
    active_cycle: int | None,
    child_exit_code: int | None,
    report_json: str | None,
    supervisor_pid: int = 0,
    child_pid: int | None = None,
    resume_state_path: str | None = None,
) -> dict[str, object]:
    if status not in {"starting", "running", "completed", "failed", "interrupted"}:
        raise ValueError("invalid research supervisor status")
    return {
        "schema_version": 1,
        "artifact_kind": "research_supervisor_checkpoint",
        "run_id": run_id,
        "timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "started_at_utc": started_at_utc,
        "status": status,
        "git_commit": _git_value("rev-parse", "HEAD"),
        "git_branch": _git_value("branch", "--show-current"),
        "max_cycles": max_cycles,
        "completed_cycle_count": len(completed_cycles),
        "active_cycle": active_cycle,
        "cycles": [_checkpoint_cycle(cycle) for cycle in completed_cycles],
        "child_exit_code": child_exit_code,
        "report_json": report_json,
        "resume_supported": True,
        "resume_state_path": resume_state_path,
        "supervisor_pid": supervisor_pid,
        "child_pid": child_pid,
        "result_truth": "canonical_runner_json_only",
        "audit_evaluated": False,
        "final_holdout_evaluated": False,
        "safety": {
            "live": "locked",
            "paper": "locked",
            "testtrade": "locked",
            "orders": "not_created",
            "trading_api": "not_used",
            "api_keys": "not_used",
        },
    }


def write_checkpoint(path: Path, payload: dict[str, object]) -> None:
    """Atomically replace one strict-JSON supervisor checkpoint."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def _resume_checkpoint(
    path: Path,
    *,
    expected_run_id: str | None = None,
    expected_max_cycles: int | None = None,
    context_required: bool = False,
) -> tuple[str | None, list[CycleProgress], str | None]:
    if not path.is_file():
        return None, [], None
    payload = _read_json_object(path, "resume checkpoint")
    if payload.get("schema_version") != 1:
        raise RuntimeError("resume checkpoint schema is unsupported")
    if payload.get("artifact_kind") != "research_supervisor_checkpoint":
        raise RuntimeError("resume checkpoint artifact kind is invalid")
    if expected_run_id is not None and payload.get("run_id") != expected_run_id:
        raise RuntimeError("resume checkpoint run_id does not match requested run")
    if expected_max_cycles is not None and payload.get("max_cycles") != expected_max_cycles:
        raise RuntimeError("resume checkpoint max_cycles does not match requested run")
    rows = payload.get("cycles")
    if not isinstance(rows, list):
        raise RuntimeError("resume checkpoint has no cycle list")
    if payload.get("completed_cycle_count") != len(rows):
        raise RuntimeError("resume checkpoint completed count does not match cycle list")
    cycles: list[CycleProgress] = []
    for expected_cycle, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise RuntimeError("resume checkpoint contains an invalid cycle")
        if int(row.get("cycle", 0)) != expected_cycle:
            raise RuntimeError("resume checkpoint cycles are not contiguous")
        if expected_max_cycles is not None and int(row.get("maximum", 0)) != expected_max_cycles:
            raise RuntimeError("resume checkpoint cycle maximum does not match requested run")
        proof_payload = row.get("runtime_proof")
        proof = None
        if isinstance(proof_payload, dict):
            context = proof_payload.get("context_research")
            proof = CycleRuntimeProof(
                cycle=int(row["cycle"]),
                maximum=int(row["maximum"]),
                context_research_enabled=bool(isinstance(context, dict) and context.get("enabled")),
                context_generated=int(proof_payload.get("context_generated", 0)),
                context_tested=int(proof_payload.get("context_tested", 0)),
                walk_forward_folds=int(proof_payload.get("walk_forward_folds", 0)),
                rolling_origin_limit=int(proof_payload.get("rolling_origin_limit", 0)),
                audit_evaluated=bool(proof_payload.get("audit_evaluated", False)),
                final_holdout_evaluated=bool(proof_payload.get("final_holdout_evaluated", False)),
            )
        if context_required and (proof is None or not _canonical_context_proof(proof)):
            raise RuntimeError(
                f"resume checkpoint cycle {expected_cycle} has no canonical context proof"
            )
        cycles.append(
            CycleProgress(
                cycle=int(row["cycle"]),
                maximum=int(row["maximum"]),
                generated=int(row["generated"]),
                tested=int(row["tested"]),
                walk_forward=int(row["walk_forward"]),
                finalists=int(row["finalists"]),
                selected_rank_text=str(row["selected_rank_text"]),
                runtime_proof=proof,
            )
        )
    return payload.get("started_at_utc"), cycles, payload.get("report_json")


def supervise(argv: Sequence[str]) -> int:
    reports_root, max_cycles, requested_run_id, requested_resume_state = _parse_supervisor_arguments(argv)
    context_required = "--enable-context" in argv
    started = datetime.now(UTC)
    run_id = requested_run_id or started.strftime("production_research_supervisor_%Y%m%dT%H%M%SZ")
    runner_run_id = run_id.replace("production_research_", "research_loop_", 1)
    resume_state_path = requested_resume_state or str(
        reports_root / f"research_loop_{run_id.removeprefix('production_research_')}.resume.json"
    )
    checkpoint_path = reports_root / f"{run_id}.checkpoint.json"
    if requested_run_id:
        _validate_runner_resume_state(
            Path(resume_state_path),
            expected_run_id=runner_run_id,
            context_required=context_required,
        )
        resumed_started_at, resumed_cycles, resumed_report_json = _resume_checkpoint(
            checkpoint_path,
            expected_run_id=run_id,
            expected_max_cycles=max_cycles,
            context_required=context_required,
        )
    else:
        resumed_started_at, resumed_cycles, resumed_report_json = None, [], None
    if resumed_started_at:
        started = datetime.fromisoformat(resumed_started_at.replace("Z", "+00:00"))
    completed_cycles: list[CycleProgress] = resumed_cycles
    active_cycle: int | None = None
    report_json: str | None = resumed_report_json

    def persist(status: str, exit_code: int | None = None) -> None:
        write_checkpoint(
            checkpoint_path,
            _checkpoint_payload(
                run_id=run_id,
                status=status,
                max_cycles=max_cycles,
                started_at_utc=started.isoformat().replace("+00:00", "Z"),
                completed_cycles=completed_cycles,
                active_cycle=active_cycle,
                child_exit_code=exit_code,
                report_json=report_json,
                supervisor_pid=os.getpid(),
                child_pid=child_pid,
                resume_state_path=resume_state_path,
            ),
        )

    child_pid: int | None = None
    persist("starting")
    command = [
        sys.executable,
        "-m",
        "ethusdc_bot.backtest.research_loop_runner",
        *argv,
        "--run-id",
        runner_run_id,
        "--resume-state",
        resume_state_path,
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    child_pid = getattr(process, "pid", None)
    persist("starting")
    if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
        process.kill()
        raise RuntimeError("research supervisor could not capture child output")

    try:
        for raw_line in process.stdout:
            line = raw_line.rstrip("\r\n")
            print(line, flush=True)
            start_match = _CYCLE_START.fullmatch(line.strip())
            if start_match is not None:
                active_cycle = int(start_match.group("cycle"))
                persist("running")
                continue
            progress = parse_cycle_progress(line)
            if progress is not None:
                if completed_cycles and progress.cycle <= completed_cycles[-1].cycle:
                    raise RuntimeError("research runner emitted non-monotone cycle progress")
                if context_required and (
                    progress.generated,
                    progress.tested,
                    progress.walk_forward,
                    progress.finalists,
                ) != (40, 12, 3, 2):
                    raise RuntimeError("context production stage counts are not 40/12/3/2")
                completed_cycles.append(progress)
                active_cycle = None
                persist("running")
                print(f"Supervisor checkpoint: {checkpoint_path}", flush=True)
                continue
            proof = parse_cycle_runtime_proof(line)
            if proof is not None:
                if (
                    not completed_cycles
                    or completed_cycles[-1].cycle != proof.cycle
                    or completed_cycles[-1].maximum != proof.maximum
                ):
                    raise RuntimeError("research cycle proof is not bound to the latest cycle")
                if context_required and not _canonical_context_proof(proof):
                    raise RuntimeError("research cycle context proof violates the production contract")
                completed_cycles[-1] = replace(
                    completed_cycles[-1], runtime_proof=proof
                )
                persist("running")
                print(f"Supervisor checkpoint: {checkpoint_path}", flush=True)
                continue
            report_match = _REPORT_JSON.fullmatch(line.strip())
            if report_match is not None:
                report_json = report_match.group("path").strip()
        exit_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait(timeout=30)
        persist("interrupted", process.returncode)
        raise
    except BaseException:
        process.terminate()
        process.wait(timeout=30)
        persist("failed", process.returncode)
        raise

    missing_context_proof = context_required and (
        not completed_cycles
        or any(progress.runtime_proof is None for progress in completed_cycles)
    )
    supervisor_exit_code = 9 if exit_code == 0 and missing_context_proof else exit_code
    status = "completed" if supervisor_exit_code == 0 and report_json else "failed"
    persist(status, supervisor_exit_code)
    print(f"Supervisor checkpoint: {checkpoint_path}", flush=True)
    return supervisor_exit_code


def main(argv: Iterable[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    return supervise(values)


if __name__ == "__main__":
    raise SystemExit(main())
