"""Read-only backtest status and result presentation for the existing dashboard.

The module reads the durable Research Protocol-v2 supervisor checkpoint, the
compact text report, and selected small values from the canonical pretty JSON
report.  It never starts, stops, resumes, ranks, or modifies a research run.
Large JSON reports are scanned line-by-line; they are never deserialized as one
object.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
import ast
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any, TextIO


TARGET_USDC_PER_DAY = 3.0
CANONICAL_MAX_CYCLES = 8
CANONICAL_WFV_DAYS = 546
CANONICAL_VALIDATION_DAYS = 146
CANONICAL_TRAINING_DAYS = 730
CANONICAL_ROLLING_ORIGIN_DAYS = 365

_CHECKPOINT_PATTERN = "production_research_supervisor_*.checkpoint.json"
_CONSOLE_PATTERN = "production_research_*.console.log"
_KEY_LINE = re.compile(r'^(?P<indent> *)"(?P<key>[^"\\]+)"\s*:\s*(?P<value>.*)$')
_FINAL_REPORT_CACHE: dict[tuple[str, int, int], dict[str, Any]] = {}

_CYCLE_TEXT = re.compile(
    r"^Cycle\s+(?P<cycle>\d+):\s+generated=(?P<generated>\d+)\s+"
    r"tested=(?P<tested>\d+)\s+walk_forward=(?P<walk_forward>\d+)\s+"
    r"finalists=(?P<finalists>\d+)\s+best_validation=(?P<best>.*)$"
)


def collect_backtest_display_status(
    reports_root: str | Path,
    *,
    controller_status: Mapping[str, Any] | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Return one fail-safe UI model for idle, running, completed, or failed research."""

    root = Path(reports_root)
    controller = dict(controller_status or {})
    checkpoint_path = _latest_path(root, _CHECKPOINT_PATTERN)
    checkpoint, checkpoint_error = _read_json_object(checkpoint_path)
    console_path = _latest_path(root, _CONSOLE_PATTERN)

    if checkpoint is None:
        if bool(controller.get("running")):
            return _base_status(
                mode="running",
                status_text="Backtest wird gestartet",
                controller=controller,
                checkpoint_path=checkpoint_path,
                console_path=console_path,
                error=checkpoint_error,
            )
        report_path = _controller_report_path(controller)
        if report_path is not None and report_path.is_file():
            return _completed_from_report(
                report_path,
                controller=controller,
                checkpoint=None,
                checkpoint_path=None,
                console_path=console_path,
                now_utc=now_utc,
            )
        return _base_status(
            mode="idle",
            status_text="Kein Backtest aktiv",
            controller=controller,
            checkpoint_path=checkpoint_path,
            console_path=console_path,
            error=checkpoint_error,
        )

    status = str(checkpoint.get("status", "failed"))
    max_cycles = _safe_positive_int(checkpoint.get("max_cycles"), CANONICAL_MAX_CYCLES)
    completed_cycles = _safe_nonnegative_int(checkpoint.get("completed_cycle_count"), 0)
    active_cycle = _optional_positive_int(checkpoint.get("active_cycle"))
    cycles = _checkpoint_cycles(checkpoint.get("cycles"))
    best_cycle = _best_checkpoint_cycle(cycles)
    progress = 100.0 if status == "completed" else round(
        min(completed_cycles, max_cycles) / max_cycles * 100.0,
        1,
    )
    report_path = _checkpoint_report_path(checkpoint)
    elapsed_seconds = _elapsed_seconds(
        checkpoint.get("started_at_utc"),
        checkpoint.get("timestamp_utc") if status in {"completed", "failed", "interrupted"} else None,
        now_utc=now_utc,
    )

    if status == "completed" and report_path is not None and report_path.is_file():
        return _completed_from_report(
            report_path,
            controller=controller,
            checkpoint=checkpoint,
            checkpoint_path=checkpoint_path,
            console_path=console_path,
            now_utc=now_utc,
        )

    mode = status if status in {"starting", "running", "failed", "interrupted"} else "failed"
    if mode == "starting":
        status_text = "Backtest wird vorbereitet"
    elif mode == "running":
        status_text = (
            f"Backtest läuft – Zyklus {active_cycle}/{max_cycles}"
            if active_cycle is not None
            else f"Backtest läuft – {completed_cycles}/{max_cycles} Zyklen abgeschlossen"
        )
    elif mode == "interrupted":
        status_text = "Backtest wurde unterbrochen"
    else:
        status_text = "Backtest ist fehlgeschlagen"

    current_cycle = cycles[-1] if cycles else None
    return {
        **_base_status(
            mode=mode,
            status_text=status_text,
            controller=controller,
            checkpoint_path=checkpoint_path,
            console_path=console_path,
            error=checkpoint_error,
        ),
        "run_id": checkpoint.get("run_id"),
        "git_commit": checkpoint.get("git_commit"),
        "git_branch": checkpoint.get("git_branch"),
        "started_at_utc": checkpoint.get("started_at_utc"),
        "updated_at_utc": checkpoint.get("timestamp_utc"),
        "elapsed_seconds": elapsed_seconds,
        "progress_pct": progress,
        "progress_visible": mode in {"starting", "running"},
        "completed_cycles": completed_cycles,
        "max_cycles": max_cycles,
        "active_cycle": active_cycle,
        "latest_cycle": current_cycle,
        "best_cycle": best_cycle,
        "report_path": str(report_path) if report_path is not None else None,
        "final_summary": None,
        "context_enabled": _checkpoint_context_enabled(cycles),
        "audit_evaluated": bool(checkpoint.get("audit_evaluated", False)),
        "final_holdout_evaluated": bool(checkpoint.get("final_holdout_evaluated", False)),
        "safety": _safe_safety(checkpoint.get("safety")),
        "recent_log_lines": _tail_lines(console_path, 30),
        "child_exit_code": checkpoint.get("child_exit_code"),
    }


def format_backtest_summary_for_display(status: Mapping[str, Any]) -> str:
    """Format the existing Kurzübersicht area for the active or latest backtest."""

    mode = str(status.get("mode", "idle"))
    if mode == "idle":
        return "Backtest\n\nKein Backtest aktiv oder abgeschlossen.\n"

    lines = [
        "BACKTEST – PR12 PROTOCOL V2",
        "",
        f"Status: {status.get('status_text')}",
        f"Run-ID: {_display(status.get('run_id'))}",
        f"Branch / Commit: {_display(status.get('git_branch'))} / {_display(status.get('git_commit'))}",
        (
            "Fortschritt: "
            f"{_number(status.get('progress_pct'), 1)} % – "
            f"{status.get('completed_cycles', 0)}/{status.get('max_cycles', CANONICAL_MAX_CYCLES)} "
            "vollständig abgeschlossene Zyklen"
        ),
        f"Aktiver Zyklus: {_display(status.get('active_cycle'))}",
        f"Laufzeit: {_duration(status.get('elapsed_seconds'))}",
        "",
    ]

    latest = status.get("latest_cycle")
    if isinstance(latest, Mapping):
        lines.extend(_cycle_lines("Letzter abgeschlossener Zyklus", latest))
    best = status.get("best_cycle")
    if (
        isinstance(best, Mapping)
        and best.get("cycle")
        != (latest.get("cycle") if isinstance(latest, Mapping) else None)
    ):
        lines.extend([""] + _cycle_lines("Bester bisheriger Zyklus", best))

    final = status.get("final_summary")
    if isinstance(final, Mapping):
        lines.extend(["", "ERGEBNIS DES ABGESCHLOSSENEN RESEARCH-BACKTESTS"])
        lines.extend(_final_summary_lines(final))

    safety = status.get("safety")
    if isinstance(safety, Mapping):
        lines.extend(
            [
                "",
                "Sicherheit:",
                f"- Audit ausgewertet: {bool(status.get('audit_evaluated'))}",
                f"- Finaler Holdout ausgewertet: {bool(status.get('final_holdout_evaluated'))}",
                f"- Live / Paper / Testtrade: {safety.get('live')} / {safety.get('paper')} / {safety.get('testtrade')}",
                f"- Orders: {safety.get('orders')}",
            ]
        )
    lines.append("")
    lines.append("Hinweis: Das ist Selection-/WFV-Evidenz. Es ist noch kein neuer versiegelter Final-Blindtest.")
    return "\n".join(lines) + "\n"


def format_backtest_log_for_display(status: Mapping[str, Any]) -> str:
    """Format the existing Kurzes Laufprotokoll area without creating another view."""

    lines = status.get("recent_log_lines")
    if isinstance(lines, Sequence) and not isinstance(lines, (str, bytes)) and lines:
        return "\n".join(str(line) for line in lines[-30:]) + "\n"
    return (
        f"{status.get('status_text', 'Backteststatus unbekannt')}\n"
        f"Checkpoint: {_display(status.get('checkpoint_path'))}\n"
        f"Report: {_display(status.get('report_path'))}\n"
    )


def _completed_from_report(
    report_path: Path,
    *,
    controller: Mapping[str, Any],
    checkpoint: Mapping[str, Any] | None,
    checkpoint_path: Path | None,
    console_path: Path | None,
    now_utc: datetime | None,
) -> dict[str, Any]:
    compact = _read_compact_report(report_path.with_suffix(".txt"))
    extracted = _extract_final_report_summary(report_path)
    cycles = _checkpoint_cycles(checkpoint.get("cycles")) if checkpoint is not None else []
    best_checkpoint = _best_checkpoint_cycle(cycles)
    final = _merge_final_summary(compact, extracted, best_checkpoint)
    max_cycles = _safe_positive_int(
        (checkpoint or {}).get("max_cycles") or final.get("max_cycles"),
        CANONICAL_MAX_CYCLES,
    )
    completed = _safe_nonnegative_int(
        (checkpoint or {}).get("completed_cycle_count") or final.get("cycles_executed"),
        0,
    )
    return {
        **_base_status(
            mode="completed",
            status_text="Backtest abgeschlossen",
            controller=controller,
            checkpoint_path=checkpoint_path,
            console_path=console_path,
            error=None,
        ),
        "run_id": (checkpoint or {}).get("run_id") or final.get("loop_run_id"),
        "git_commit": (checkpoint or {}).get("git_commit") or final.get("git_commit"),
        "git_branch": (checkpoint or {}).get("git_branch"),
        "started_at_utc": (checkpoint or {}).get("started_at_utc"),
        "updated_at_utc": (checkpoint or {}).get("timestamp_utc"),
        "elapsed_seconds": _elapsed_seconds(
            (checkpoint or {}).get("started_at_utc"),
            (checkpoint or {}).get("timestamp_utc"),
            now_utc=now_utc,
        ),
        "progress_pct": 100.0,
        "progress_visible": False,
        "completed_cycles": completed,
        "max_cycles": max_cycles,
        "active_cycle": None,
        "latest_cycle": cycles[-1] if cycles else None,
        "best_cycle": best_checkpoint,
        "report_path": str(report_path),
        "final_summary": final,
        "context_enabled": _checkpoint_context_enabled(cycles) or bool(final.get("context_enabled")),
        "audit_evaluated": bool((checkpoint or {}).get("audit_evaluated", False)),
        "final_holdout_evaluated": bool((checkpoint or {}).get("final_holdout_evaluated", False)),
        "safety": _safe_safety((checkpoint or {}).get("safety")),
        "recent_log_lines": _tail_lines(console_path, 30),
        "child_exit_code": (checkpoint or {}).get("child_exit_code"),
    }


def _base_status(
    *,
    mode: str,
    status_text: str,
    controller: Mapping[str, Any],
    checkpoint_path: Path | None,
    console_path: Path | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": mode,
        "status_text": status_text,
        "run_id": None,
        "git_commit": None,
        "git_branch": None,
        "started_at_utc": controller.get("started_at"),
        "updated_at_utc": None,
        "elapsed_seconds": 0,
        "progress_pct": 0.0,
        "progress_visible": mode in {"starting", "running"},
        "completed_cycles": 0,
        "max_cycles": CANONICAL_MAX_CYCLES,
        "active_cycle": None,
        "latest_cycle": None,
        "best_cycle": None,
        "report_path": str(_controller_report_path(controller)) if _controller_report_path(controller) else None,
        "checkpoint_path": str(checkpoint_path) if checkpoint_path is not None else None,
        "console_log_path": str(console_path) if console_path is not None else None,
        "final_summary": None,
        "context_enabled": bool(controller.get("context_research_enabled", True)),
        "audit_evaluated": False,
        "final_holdout_evaluated": False,
        "safety": _safe_safety(None),
        "recent_log_lines": _tail_lines(console_path, 30),
        "error": error or controller.get("error"),
        "child_exit_code": None,
    }


def _checkpoint_cycles(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    rows: list[dict[str, Any]] = []
    for source in value:
        if not isinstance(source, Mapping):
            continue
        rank = _parse_rank(source.get("selected_rank_text"))
        proof = source.get("runtime_proof") if isinstance(source.get("runtime_proof"), Mapping) else {}
        context = proof.get("context_research") if isinstance(proof, Mapping) else {}
        rows.append(
            {
                "cycle": _safe_positive_int(source.get("cycle"), len(rows) + 1),
                "maximum": _safe_positive_int(source.get("maximum"), CANONICAL_MAX_CYCLES),
                "generated": _safe_nonnegative_int(source.get("generated"), 0),
                "tested": _safe_nonnegative_int(source.get("tested"), 0),
                "walk_forward": _safe_nonnegative_int(source.get("walk_forward"), 0),
                "finalists": _safe_nonnegative_int(source.get("finalists"), 0),
                "selected_rank_text": source.get("selected_rank_text"),
                "quality_gate_passed": _rank_value(rank, 0) == 1.0,
                "wfv_net_usdc_per_day": _rank_value(rank, 1),
                "wfv_profit_factor": _rank_value(rank, 2),
                "wfv_max_drawdown_usdc": _negative_rank_value(rank, 3),
                "worst_fold_net_usdc_per_day": _rank_value(rank, 4),
                "positive_fold_count": _rank_value(rank, 5),
                "validation_net_usdc_per_day": _rank_value(rank, 6),
                "wfv_cost_load": _negative_rank_value(rank, 7),
                "rank": rank,
                "context_enabled": bool(context.get("enabled")) if isinstance(context, Mapping) else False,
                "context_generated": proof.get("context_generated") if isinstance(proof, Mapping) else None,
                "context_tested": proof.get("context_tested") if isinstance(proof, Mapping) else None,
                "walk_forward_folds": proof.get("walk_forward_folds") if isinstance(proof, Mapping) else None,
                "rolling_origin_limit": proof.get("rolling_origin_limit") if isinstance(proof, Mapping) else None,
            }
        )
    return rows


def _best_checkpoint_cycle(cycles: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    usable = [dict(row) for row in cycles if isinstance(row.get("rank"), tuple)]
    return max(usable, key=lambda row: row["rank"], default=None)


def _parse_rank(value: Any) -> tuple[float, ...] | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not (text.startswith("(") and text.endswith(")")):
        return None
    parts = [part.strip() for part in text[1:-1].split(",") if part.strip()]
    numbers: list[float] = []
    for part in parts:
        try:
            number = float(part)
        except (TypeError, ValueError):
            return None
        numbers.append(number)
    return tuple(numbers) if numbers else None


def _read_compact_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    result: dict[str, Any] = {"cycles": []}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}
    prefixes = {
        "Loop-Run-ID:": "loop_run_id",
        "Git commit:": "git_commit",
        "Cycles executed:": "cycles_text",
        "Stop reason:": "stop_reason",
        "Freeze status:": "freeze_status",
    }
    for line in lines:
        for prefix, key in prefixes.items():
            if line.startswith(prefix):
                result[key] = line.split(":", 1)[1].strip()
        match = _CYCLE_TEXT.fullmatch(line)
        if match is not None:
            try:
                best = ast.literal_eval(match.group("best"))
            except (SyntaxError, ValueError):
                best = {}
            result["cycles"].append(
                {
                    "cycle": int(match.group("cycle")),
                    "generated": int(match.group("generated")),
                    "tested": int(match.group("tested")),
                    "walk_forward": int(match.group("walk_forward")),
                    "finalists": int(match.group("finalists")),
                    "best_validation_candidate": best if isinstance(best, dict) else {},
                }
            )
    cycles_text = result.get("cycles_text")
    if isinstance(cycles_text, str) and "/" in cycles_text:
        left, right = cycles_text.split("/", 1)
        try:
            result["cycles_executed"] = int(left.strip())
            result["max_cycles"] = int(right.strip())
        except ValueError:
            pass
    return result


def _extract_final_report_summary(path: Path) -> dict[str, Any]:
    """Extract only small presentation values from a possibly multi-GB pretty JSON."""

    if not path.is_file():
        return {}
    stat = path.stat()
    cache_key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    cached = _FINAL_REPORT_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)
    top_keys = {
        "loop_run_id",
        "git_commit",
        "cycles_executed",
        "max_cycles",
        "stop_reason",
        "freeze_status",
        "target_usdc_per_day",
        "candidate_stage_totals",
        "safety_status",
    }
    cycle_keys = {
        "best_validation_candidate",
        "selected_candidate",
        "selected_candidate_score",
        "full_training_metrics",
        "rolling_origin_summary",
        "quality_gate",
        "context_research",
        "exit_reason_summary",
        "qualified_finalists",
    }
    extracted: dict[str, Any] = {"cycles": []}
    cycle_values: dict[str, list[Any]] = {key: [] for key in cycle_keys}
    aggregate_metrics: list[Any] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for indent, key, value in _iter_selected_pretty_json_values(
                handle,
                top_keys=top_keys,
                cycle_keys=cycle_keys,
            ):
                if indent == 2 and key in top_keys:
                    extracted[key] = value
                elif indent == 6 and key in cycle_keys:
                    cycle_values[key].append(value)
                elif indent == 8 and key == "aggregate_metrics":
                    aggregate_metrics.append(value)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        _FINAL_REPORT_CACHE[cache_key] = dict(extracted)
        return extracted

    cycle_count = max(
        [len(values) for values in cycle_values.values()] + [len(aggregate_metrics), 0]
    )
    for index in range(cycle_count):
        row = {
            key: values[index] if index < len(values) else None
            for key, values in cycle_values.items()
        }
        row["wfv_aggregate_metrics"] = (
            aggregate_metrics[index] if index < len(aggregate_metrics) else None
        )
        extracted["cycles"].append(row)
    _FINAL_REPORT_CACHE[cache_key] = dict(extracted)
    return extracted


def _iter_selected_pretty_json_values(
    handle: TextIO,
    *,
    top_keys: set[str],
    cycle_keys: set[str],
):
    for line in handle:
        match = _KEY_LINE.match(line)
        if match is None:
            continue
        indent = len(match.group("indent"))
        key = match.group("key")
        wanted = (
            (indent == 2 and key in top_keys)
            or (indent == 6 and key in cycle_keys)
            or (indent == 8 and key == "aggregate_metrics")
        )
        if not wanted:
            continue
        fragment = match.group("value")
        value = _read_json_value_fragment(handle, fragment, max_bytes=8_000_000)
        yield indent, key, value


def _read_json_value_fragment(handle: TextIO, first: str, *, max_bytes: int) -> Any:
    parts = [first.rstrip("\r\n")]
    text = parts[0].lstrip()
    if not text:
        raise ValueError("missing JSON value")
    if text[0] not in "[{":
        return json.loads(text.rstrip().removesuffix(","))

    balance = 0
    in_string = False
    escaped = False

    def scan(chunk: str) -> None:
        nonlocal balance, in_string, escaped
        for char in chunk:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in "[{":
                balance += 1
            elif char in "]}":
                balance -= 1

    scan(parts[0])
    size = len(parts[0].encode("utf-8"))
    while balance > 0:
        line = handle.readline()
        if not line:
            raise ValueError("truncated JSON value")
        parts.append(line.rstrip("\r\n"))
        size += len(line.encode("utf-8"))
        if size > max_bytes:
            raise ValueError("selected JSON value exceeds UI extraction cap")
        scan(line)
    return json.loads("\n".join(parts).rstrip().removesuffix(","))


def _merge_final_summary(
    compact: Mapping[str, Any],
    extracted: Mapping[str, Any],
    checkpoint_best: Mapping[str, Any] | None,
) -> dict[str, Any]:
    report_cycles = extracted.get("cycles") if isinstance(extracted.get("cycles"), Sequence) else []
    best_report_cycle = _best_report_cycle(report_cycles)
    compact_cycles = compact.get("cycles") if isinstance(compact.get("cycles"), Sequence) else []
    best_validation = None
    validation_rows = [
        row.get("best_validation_candidate")
        for row in compact_cycles
        if isinstance(row, Mapping) and isinstance(row.get("best_validation_candidate"), Mapping)
    ]
    validation_rows.extend(
        row.get("best_validation_candidate")
        for row in report_cycles
        if isinstance(row, Mapping) and isinstance(row.get("best_validation_candidate"), Mapping)
    )
    if validation_rows:
        best_validation = max(
            validation_rows,
            key=lambda row: _finite_number(row.get("net_usdc_per_day"), float("-inf")),
        )

    score = (
        best_report_cycle.get("selected_candidate_score")
        if isinstance(best_report_cycle, Mapping)
        and isinstance(best_report_cycle.get("selected_candidate_score"), Mapping)
        else checkpoint_best or {}
    )
    aggregate = (
        best_report_cycle.get("wfv_aggregate_metrics")
        if isinstance(best_report_cycle, Mapping)
        and isinstance(best_report_cycle.get("wfv_aggregate_metrics"), Mapping)
        else {}
    )
    full_training = (
        best_report_cycle.get("full_training_metrics")
        if isinstance(best_report_cycle, Mapping)
        and isinstance(best_report_cycle.get("full_training_metrics"), Mapping)
        else {}
    )
    rolling = (
        best_report_cycle.get("rolling_origin_summary")
        if isinstance(best_report_cycle, Mapping)
        and isinstance(best_report_cycle.get("rolling_origin_summary"), Mapping)
        else {}
    )
    selected = (
        best_report_cycle.get("selected_candidate")
        if isinstance(best_report_cycle, Mapping)
        and isinstance(best_report_cycle.get("selected_candidate"), Mapping)
        else {}
    )
    gate = (
        best_report_cycle.get("quality_gate")
        if isinstance(best_report_cycle, Mapping)
        and isinstance(best_report_cycle.get("quality_gate"), Mapping)
        else {}
    )
    context = (
        best_report_cycle.get("context_research")
        if isinstance(best_report_cycle, Mapping)
        and isinstance(best_report_cycle.get("context_research"), Mapping)
        else {}
    )
    exits = (
        best_report_cycle.get("exit_reason_summary")
        if isinstance(best_report_cycle, Mapping)
        and isinstance(best_report_cycle.get("exit_reason_summary"), Mapping)
        else {}
    )

    wfv_net = _first_number(
        score.get("wfv_net_usdc_per_day"),
        aggregate.get("net_usdc_per_day"),
    )
    target_gap = None if wfv_net is None else round(wfv_net - TARGET_USDC_PER_DAY, 10)
    return {
        "loop_run_id": extracted.get("loop_run_id") or compact.get("loop_run_id"),
        "git_commit": extracted.get("git_commit") or compact.get("git_commit"),
        "cycles_executed": extracted.get("cycles_executed") or compact.get("cycles_executed"),
        "max_cycles": extracted.get("max_cycles") or compact.get("max_cycles"),
        "stop_reason": extracted.get("stop_reason") or compact.get("stop_reason"),
        "freeze_status": extracted.get("freeze_status") or compact.get("freeze_status"),
        "target_usdc_per_day": extracted.get("target_usdc_per_day") or TARGET_USDC_PER_DAY,
        "target_gap_usdc_per_day": target_gap,
        "target_reached_in_selection": bool(wfv_net is not None and wfv_net >= TARGET_USDC_PER_DAY),
        "selected_candidate": dict(selected),
        "best_validation": dict(best_validation or {}),
        "wfv_net_usdc_per_day": wfv_net,
        "wfv_net_profit_usdc": _first_number(aggregate.get("net_profit_usdc")),
        "wfv_profit_factor": _first_number(score.get("wfv_profit_factor"), aggregate.get("profit_factor")),
        "wfv_trade_count": _first_int(aggregate.get("trade_count")),
        "wfv_trades_per_day": _rate(_first_int(aggregate.get("trade_count")), CANONICAL_WFV_DAYS),
        "wfv_winrate": _first_number(aggregate.get("winrate")),
        "wfv_average_trade_usdc": _first_number(aggregate.get("average_trade_usdc")),
        "wfv_max_drawdown_usdc": _first_number(score.get("wfv_max_drawdown_usdc"), aggregate.get("max_drawdown_usdc")),
        "wfv_worst_fold_net_usdc_per_day": _first_number(score.get("worst_fold_net_usdc_per_day")),
        "wfv_positive_fold_count": _first_int(score.get("positive_fold_count")),
        "wfv_fees_usdc": _first_number(aggregate.get("fees_usdc")),
        "wfv_slippage_usdc": _first_number(aggregate.get("slippage_usdc")),
        "wfv_cost_load_usdc": _first_number(score.get("wfv_cost_load")),
        "validation_trades_per_day": _rate(
            _first_int((best_validation or {}).get("trade_count")),
            CANONICAL_VALIDATION_DAYS,
        ),
        "full_training": dict(full_training),
        "full_training_trades_per_day": _rate(
            _first_int(full_training.get("trade_count")),
            CANONICAL_TRAINING_DAYS,
        ),
        "rolling": dict(rolling),
        "rolling_trades_per_day": _rate(
            _first_int(rolling.get("trade_count")),
            _safe_positive_int(rolling.get("origin_count"), 0) * CANONICAL_ROLLING_ORIGIN_DAYS,
        ),
        "quality_gate_passed": bool(gate.get("passed")),
        "quality_gate_failed_codes": _failed_gate_codes(gate),
        "qualified_finalists": (
            best_report_cycle.get("qualified_finalists")
            if isinstance(best_report_cycle, Mapping)
            else None
        ),
        "context_enabled": bool(context.get("enabled")),
        "exit_summary": dict(exits),
        "candidate_stage_totals": extracted.get("candidate_stage_totals"),
        "safety_status": extracted.get("safety_status"),
    }


def _best_report_cycle(rows: Sequence[Any]) -> Mapping[str, Any] | None:
    usable = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        score = row.get("selected_candidate_score")
        if isinstance(score, Mapping):
            usable.append(row)
    return max(usable, key=lambda row: _score_tuple(row["selected_candidate_score"]), default=None)


def _score_tuple(score: Mapping[str, Any]) -> tuple[float, ...]:
    return (
        1.0 if score.get("quality_gate_passed") is True else 0.0,
        _finite_number(score.get("wfv_net_usdc_per_day"), float("-inf")),
        _finite_number(score.get("wfv_profit_factor"), float("-inf")),
        -_finite_number(score.get("wfv_max_drawdown_usdc"), float("inf")),
        _finite_number(score.get("worst_fold_net_usdc_per_day"), float("-inf")),
        _finite_number(score.get("positive_fold_count"), float("-inf")),
        _finite_number(score.get("validation_net_usdc_per_day"), float("-inf")),
        -_finite_number(score.get("wfv_cost_load"), float("inf")),
    )


def _cycle_lines(title: str, row: Mapping[str, Any]) -> list[str]:
    return [
        f"{title}:",
        f"- Zyklus: {_display(row.get('cycle'))}/{_display(row.get('maximum'))}",
        (
            "- Kandidaten: "
            f"{_display(row.get('generated'))} erzeugt / {_display(row.get('tested'))} getestet / "
            f"{_display(row.get('walk_forward'))} WFV / {_display(row.get('finalists'))} Finalisten"
        ),
        f"- Kontext: {bool(row.get('context_enabled'))} ({_display(row.get('context_generated'))}/{_display(row.get('context_tested'))})",
        f"- WFV netto/Tag: {_usdc(row.get('wfv_net_usdc_per_day'))}",
        f"- WFV Profit Factor: {_number(row.get('wfv_profit_factor'), 4)}",
        f"- WFV Max-Drawdown: {_usdc(row.get('wfv_max_drawdown_usdc'))}",
        f"- Schlechtester Fold netto/Tag: {_usdc(row.get('worst_fold_net_usdc_per_day'))}",
        f"- Positive Folds: {_number(row.get('positive_fold_count'), 0)}/{_display(row.get('walk_forward_folds') or 6)}",
        f"- Validation netto/Tag: {_usdc(row.get('validation_net_usdc_per_day'))}",
        f"- Gebühren + Slippage: {_usdc(row.get('wfv_cost_load'))}",
        f"- Quality Gate bestanden: {bool(row.get('quality_gate_passed'))}",
    ]


def _final_summary_lines(final: Mapping[str, Any]) -> list[str]:
    selected = final.get("selected_candidate") if isinstance(final.get("selected_candidate"), Mapping) else {}
    validation = final.get("best_validation") if isinstance(final.get("best_validation"), Mapping) else {}
    training = final.get("full_training") if isinstance(final.get("full_training"), Mapping) else {}
    rolling = final.get("rolling") if isinstance(final.get("rolling"), Mapping) else {}
    failed = final.get("quality_gate_failed_codes") or []
    lines = [
        f"- Stop-Grund: {_display(final.get('stop_reason'))}",
        f"- Zyklen: {_display(final.get('cycles_executed'))}/{_display(final.get('max_cycles'))}",
        f"- Ausgewählter Kandidat: {_display(selected.get('candidate_id'))} / {_display(selected.get('family'))}",
        f"- Bestes WFV netto/Tag: {_usdc(final.get('wfv_net_usdc_per_day'))}",
        f"- Abstand zum Ziel 3 USDC/Tag: {_usdc(final.get('target_gap_usdc_per_day'))}",
        f"- WFV Netto gesamt: {_usdc(final.get('wfv_net_profit_usdc'))}",
        f"- WFV Trades: {_display(final.get('wfv_trade_count'))} / {_number(final.get('wfv_trades_per_day'), 4)} pro Tag",
        f"- WFV Profit Factor: {_number(final.get('wfv_profit_factor'), 4)}",
        f"- WFV Winrate: {_percent(final.get('wfv_winrate'))}",
        f"- WFV durchschnittlicher Trade: {_usdc(final.get('wfv_average_trade_usdc'))}",
        f"- WFV Max-Drawdown: {_usdc(final.get('wfv_max_drawdown_usdc'))}",
        f"- WFV schlechtester Fold: {_usdc(final.get('wfv_worst_fold_net_usdc_per_day'))}/Tag",
        f"- WFV positive Folds: {_display(final.get('wfv_positive_fold_count'))}/6",
        f"- Gebühren: {_usdc(final.get('wfv_fees_usdc'))}",
        f"- Slippage: {_usdc(final.get('wfv_slippage_usdc'))}",
        f"- Beste Validation: {_usdc(validation.get('net_usdc_per_day'))}/Tag, { _display(validation.get('trade_count')) } Trades, PF {_number(validation.get('profit_factor'), 4)}",
        f"- Validation Trades/Tag: {_number(final.get('validation_trades_per_day'), 4)}",
        f"- Volles Training: {_usdc(training.get('net_usdc_per_day'))}/Tag, {_display(training.get('trade_count'))} Trades, {_number(final.get('full_training_trades_per_day'), 4)} Trades/Tag",
        f"- Rolling Origins Ø: {_usdc(rolling.get('average_oos_net_usdc_per_day'))}/Tag",
        f"- Rolling Origins schlechtester: {_usdc(rolling.get('worst_oos_net_usdc_per_day'))}/Tag",
        f"- Rolling positive Origins: {_display(rolling.get('positive_origin_count'))}/{_display(rolling.get('origin_count'))}",
        f"- Quality Gate bestanden: {bool(final.get('quality_gate_passed'))}",
        f"- Fehlgeschlagene Gates: {', '.join(str(code) for code in failed) if failed else 'keine'}",
        f"- Freeze-Status: {_display(final.get('freeze_status'))}",
    ]
    return lines


def _failed_gate_codes(gate: Mapping[str, Any]) -> list[str]:
    checks = gate.get("checks")
    if not isinstance(checks, Sequence) or isinstance(checks, (str, bytes)):
        return []
    return [
        str(check.get("code"))
        for check in checks
        if isinstance(check, Mapping) and check.get("passed") is not True and check.get("code")
    ]


def _latest_path(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    paths = [path for path in root.glob(pattern) if path.is_file()]
    return max(paths, key=lambda path: (path.stat().st_mtime_ns, path.name), default=None)


def _read_json_object(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, f"Checkpoint nicht lesbar: {error}"
    if not isinstance(value, dict):
        return None, "Checkpoint-Wurzel ist kein Objekt"
    return value, None


def _tail_lines(path: Path | None, limit: int) -> list[str]:
    if path is None or not path.is_file() or limit <= 0:
        return []
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            position = handle.tell()
            block = 4096
            data = b""
            while position > 0 and data.count(b"\n") <= limit:
                read_size = min(block, position)
                position -= read_size
                handle.seek(position)
                data = handle.read(read_size) + data
        text = data.decode("utf-8", errors="replace")
    except OSError:
        return []
    return [line for line in text.splitlines() if line.strip()][-limit:]


def _controller_report_path(controller: Mapping[str, Any]) -> Path | None:
    value = controller.get("report_path")
    return Path(value) if isinstance(value, (str, Path)) and str(value) else None


def _checkpoint_report_path(checkpoint: Mapping[str, Any]) -> Path | None:
    value = checkpoint.get("report_json")
    return Path(value) if isinstance(value, str) and value else None


def _checkpoint_context_enabled(cycles: Sequence[Mapping[str, Any]]) -> bool:
    return bool(cycles and all(bool(row.get("context_enabled")) for row in cycles))


def _safe_safety(value: Any) -> dict[str, str]:
    source = value if isinstance(value, Mapping) else {}
    return {
        "live": str(source.get("live", "locked")),
        "paper": str(source.get("paper", "locked")),
        "testtrade": str(source.get("testtrade", "locked")),
        "orders": str(source.get("orders", "not_created")),
        "trading_api": str(source.get("trading_api", "not_used")),
        "api_keys": str(source.get("api_keys", "not_used")),
    }


def _elapsed_seconds(start: Any, finish: Any, *, now_utc: datetime | None) -> int:
    start_dt = _parse_datetime(start)
    if start_dt is None:
        return 0
    finish_dt = _parse_datetime(finish) or now_utc or datetime.now(UTC)
    if finish_dt.tzinfo is None:
        finish_dt = finish_dt.replace(tzinfo=UTC)
    return max(0, int((finish_dt - start_dt).total_seconds()))


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _safe_positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number > 0 else default


def _safe_nonnegative_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number >= 0 else default


def _optional_positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _rank_value(rank: tuple[float, ...] | None, index: int) -> float | None:
    if rank is None or index >= len(rank):
        return None
    value = rank[index]
    return value if isfinite(value) else None


def _negative_rank_value(rank: tuple[float, ...] | None, index: int) -> float | None:
    value = _rank_value(rank, index)
    return -value if value is not None else None


def _finite_number(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if isfinite(number) else default


def _first_number(*values: Any) -> float | None:
    for value in values:
        number = _finite_number(value)
        if number is not None:
            return number
    return None


def _first_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _rate(count: int | None, days: int) -> float | None:
    if count is None or days <= 0:
        return None
    return round(count / days, 10)


def _display(value: Any) -> str:
    return "–" if value is None or value == "" else str(value)


def _number(value: Any, digits: int) -> str:
    number = _finite_number(value)
    return "–" if number is None else f"{number:.{digits}f}"


def _usdc(value: Any) -> str:
    number = _finite_number(value)
    return "–" if number is None else f"{number:.6f} USDC"


def _percent(value: Any) -> str:
    number = _finite_number(value)
    return "–" if number is None else f"{number * 100:.2f} %"


def _duration(value: Any) -> str:
    seconds = _safe_nonnegative_int(value, 0)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


__all__ = [
    "collect_backtest_display_status",
    "format_backtest_log_for_display",
    "format_backtest_summary_for_display",
]
