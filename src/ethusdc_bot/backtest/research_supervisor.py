"""Durable, order-free supervisor for long local Research Protocol v2 runs.

The supervisor does not evaluate candidates and does not alter the canonical
research report. It starts the existing runner as a child process, mirrors its
stdout, and atomically records only already-emitted cycle progress. The final
runner JSON remains the sole performance and quality-gate truth.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable, Sequence


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


@dataclass(frozen=True)
class CycleProgress:
    cycle: int
    maximum: int
    generated: int
    tested: int
    walk_forward: int
    finalists: int
    selected_rank_text: str


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


def _parse_supervisor_arguments(argv: Sequence[str]) -> tuple[Path, int]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--reports-root", default="reports/research_loop")
    parser.add_argument("--max-cycles", type=int, default=8)
    known, _ = parser.parse_known_args(list(argv))
    if known.max_cycles < 1 or known.max_cycles > 8:
        raise ValueError("max-cycles must be between 1 and 8")
    return Path(known.reports_root), known.max_cycles


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
        "cycles": [asdict(cycle) for cycle in completed_cycles],
        "child_exit_code": child_exit_code,
        "report_json": report_json,
        "resume_supported": False,
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


def supervise(argv: Sequence[str]) -> int:
    reports_root, max_cycles = _parse_supervisor_arguments(argv)
    started = datetime.now(UTC)
    run_id = started.strftime("production_research_supervisor_%Y%m%dT%H%M%SZ")
    checkpoint_path = reports_root / f"{run_id}.checkpoint.json"
    completed_cycles: list[CycleProgress] = []
    active_cycle: int | None = None
    report_json: str | None = None

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
            ),
        )

    persist("starting")
    command = [
        sys.executable,
        "-m",
        "ethusdc_bot.backtest.research_loop_runner",
        *argv,
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
                completed_cycles.append(progress)
                active_cycle = None
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

    status = "completed" if exit_code == 0 and report_json else "failed"
    persist(status, exit_code)
    print(f"Supervisor checkpoint: {checkpoint_path}", flush=True)
    return exit_code


def main(argv: Iterable[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    return supervise(values)


if __name__ == "__main__":
    raise SystemExit(main())
