"""Asynchronous UI boundary for the irreversible sealed-holdout evaluator.

The controller never selects or changes a candidate.  It only hands an
already-frozen Protocol-v2 report to the one-shot runner.  No result from this
controller can unlock live, paper, testtrade, an account, or an order path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import json
from pathlib import Path
import threading
from typing import Any

from ethusdc_bot.backtest.sealed_holdout_runner import run_sealed_holdout
from ethusdc_bot.shadow.adoption import assess_final_report


StatusCallback = Callable[[dict[str, Any]], None]
FinalRunner = Callable[[str | Path, str | Path, str | Path], Any]
_DIRECT_REPORT_READ_LIMIT_BYTES = 8_000_000
_DISCOVERY_CACHE: dict[tuple[str, int, int], dict[str, Any] | None] = {}


def build_initial_final_evaluation_status() -> dict[str, Any]:
    return _safe_status(
        phase="initial",
        running=False,
        started_at=None,
        finished_at=None,
        source_research_report_path=None,
        final_report_path=None,
        assessment_color="none",
        target_reached=False,
        shadow_eligible=False,
        error=None,
        retry_allowed=False,
        final_holdout_evaluated=False,
        final_holdout_outcome="not_run",
    )


def discover_latest_frozen_research_report(reports_root: str | Path) -> dict[str, Any]:
    """Return a read-only UI hint; the one-shot runner performs real validation."""

    root = Path(reports_root)
    reports = sorted(root.glob("*.json")) if root.exists() else []
    frozen: list[tuple[Path, dict[str, Any]]] = []
    invalid_count = 0
    for path in reports:
        if not path.is_file():
            continue
        payload = _read_research_discovery_fields(path)
        if payload is None:
            invalid_count += 1
            continue
        audit = payload.get("audit_policy")
        holdout = payload.get("window_plan", {})
        holdout = holdout.get("final_holdout_window") if isinstance(holdout, Mapping) else None
        if (
            payload.get("schema_version") == 2
            and payload.get("execution_profile") == "production_protocol"
            and payload.get("fixture_data_only") is False
            and payload.get("freeze_status") == "frozen_for_separate_sealed_holdout"
            and isinstance(payload.get("frozen_candidate"), Mapping)
            and isinstance(audit, Mapping)
            and audit.get("freeze_eligible") is True
            and isinstance(holdout, Mapping)
            and holdout.get("status") == "sealed_unopened"
            and holdout.get("consumed_audit_window") is False
            and holdout.get("evaluated") is False
            and holdout.get("days") == 365
        ):
            frozen.append((path, dict(payload)))
    if not frozen:
        return {
            "status": "not_ready",
            "report_path": None,
            "run_id": None,
            "candidate_id": None,
            "invalid_report_count": invalid_count,
            "reason": "no_frozen_unconsumed_sealed_holdout_report",
        }
    path, payload = frozen[-1]
    candidate = payload["frozen_candidate"]
    return {
        "status": "ready_for_explicit_one_shot",
        "report_path": str(path),
        "run_id": payload.get("loop_run_id"),
        "candidate_id": candidate.get("candidate_id"),
        "invalid_report_count": invalid_count,
        "reason": None,
    }


def _read_research_discovery_fields(path: Path) -> dict[str, Any] | None:
    """Read only bounded UI-discovery fields from one research artifact.

    Multi-gigabyte detail reports are rejected from the hot path by their
    compact report whenever they are not frozen. A genuinely frozen large
    report is scanned line-by-line once and cached; it is never loaded as one
    Python string or JSON object.
    """

    try:
        stat = path.stat()
    except OSError:
        return None
    cache_key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if cache_key in _DISCOVERY_CACHE:
        cached = _DISCOVERY_CACHE[cache_key]
        return dict(cached) if cached is not None else None

    if stat.st_size <= _DIRECT_REPORT_READ_LIMIT_BYTES:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            value = None
        result = dict(value) if isinstance(value, Mapping) else None
        _DISCOVERY_CACHE[cache_key] = result
        return dict(result) if result is not None else None

    if _compact_freeze_status(path.with_suffix(".txt")) != "frozen_for_separate_sealed_holdout":
        _DISCOVERY_CACHE[cache_key] = None
        return None

    wanted = {
        "schema_version",
        "execution_profile",
        "fixture_data_only",
        "freeze_status",
        "frozen_candidate",
        "loop_run_id",
        "audit_policy",
        "window_plan",
    }
    result: dict[str, Any] = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.startswith('  "'):
                    continue
                stripped = line.lstrip()
                if not stripped.startswith('"') or '":' not in stripped:
                    continue
                key = stripped[1 : stripped.index('"', 1)]
                if key not in wanted:
                    continue
                first = stripped.split(":", 1)[1].lstrip()
                result[key] = _read_bounded_json_fragment(handle, first)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        result = {}
    cached_result = result if wanted.issubset(result) else None
    _DISCOVERY_CACHE[cache_key] = cached_result
    return dict(cached_result) if cached_result is not None else None


def _compact_freeze_status(path: Path) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > 1_000_000:
            return None
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("Freeze status:"):
                    return line.split(":", 1)[1].strip() or None
    except (OSError, UnicodeError):
        return None
    return None


def _read_bounded_json_fragment(handle: Any, first: str, max_bytes: int = 2_000_000) -> Any:
    parts = [first.rstrip("\r\n")]
    text = parts[0].lstrip()
    if not text:
        raise ValueError("missing JSON value")
    if text[0] not in "[{":
        return json.loads(text.rstrip().removesuffix(","))

    balance = 0
    in_string = False
    escaped = False
    size = 0
    while True:
        chunk = parts[-1]
        size += len(chunk.encode("utf-8"))
        if size > max_bytes:
            raise ValueError("research discovery value exceeds bounded UI cap")
        for char in chunk:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char in "[{":
                balance += 1
            elif char in "]}":
                balance -= 1
        if balance <= 0:
            break
        line = handle.readline()
        if not line:
            raise ValueError("truncated JSON value")
        parts.append(line.rstrip("\r\n"))
    return json.loads("\n".join(parts).rstrip().removesuffix(","))


class FinalEvaluationController:
    """Allow at most one one-shot final-evaluation worker per UI process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._status = build_initial_final_evaluation_status()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def start(
        self,
        frozen_research_report_path: str | Path,
        raw_root: str | Path,
        reports_root: str | Path,
        *,
        status_callback: StatusCallback | None = None,
        runner: FinalRunner = run_sealed_holdout,
    ) -> tuple[threading.Thread, dict[str, Any]]:
        if not callable(runner):
            raise TypeError("runner must be callable")
        if status_callback is not None and not callable(status_callback):
            raise TypeError("status_callback must be callable or None")
        source = Path(frozen_research_report_path)
        started = _utc_now()
        running = _safe_status(
            phase="running",
            running=True,
            started_at=started,
            finished_at=None,
            source_research_report_path=str(source),
            final_report_path=None,
            assessment_color="none",
            target_reached=False,
            shadow_eligible=False,
            error=None,
            retry_allowed=False,
            final_holdout_evaluated=False,
            final_holdout_outcome="one_shot_in_progress",
        )
        container: dict[str, Any] = {"status": dict(running)}
        with self._lock:
            if self._running:
                raise RuntimeError("sealed final evaluation is already running")
            self._running = True
            self._status = dict(running)

        def worker() -> None:
            try:
                result = runner(source, raw_root, reports_root)
                report_path = _result_report_path(result)
                assessment = assess_final_report(report_path)
                status = _safe_status(
                    phase="completed",
                    running=False,
                    started_at=started,
                    finished_at=_utc_now(),
                    source_research_report_path=str(source),
                    final_report_path=str(report_path),
                    assessment_color=assessment.color,
                    target_reached=assessment.target_reached,
                    shadow_eligible=assessment.shadow_eligible,
                    error=None,
                    retry_allowed=False,
                    final_holdout_evaluated=True,
                    final_holdout_outcome="completed_once",
                )
            except BaseException as exc:
                status = _safe_status(
                    phase="failed",
                    running=False,
                    started_at=started,
                    finished_at=_utc_now(),
                    source_research_report_path=str(source),
                    final_report_path=None,
                    assessment_color="red",
                    target_reached=False,
                    shadow_eligible=False,
                    error=f"{type(exc).__name__}: {exc}",
                    retry_allowed=False,
                    final_holdout_evaluated=False,
                    final_holdout_outcome="failed_or_claimed_manual_audit_required",
                )
            container["status"] = dict(status)
            with self._lock:
                self._status = dict(status)
                self._running = False
            _notify(status_callback, status)

        thread = threading.Thread(
            target=worker,
            name="ethusdc-sealed-final-evaluation",
            daemon=True,
        )
        _notify(status_callback, running)
        try:
            thread.start()
        except BaseException:
            with self._lock:
                self._running = False
            raise
        return thread, container


def _result_report_path(result: Any) -> Path:
    value = (
        result.get("final_report_path")
        if isinstance(result, Mapping)
        else getattr(result, "final_report_path", None)
    )
    if not isinstance(value, (str, Path)):
        raise RuntimeError("sealed runner returned no final_report_path")
    return Path(value)


def _safe_status(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        **values,
        "orders_created": False,
        "trading_api_used": False,
        "api_keys_used": False,
        "live_eligible": False,
        "paper_eligible": False,
        "testtrade_eligible": False,
    }


def _notify(callback: StatusCallback | None, status: Mapping[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(dict(status))
    except Exception:
        return


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "FinalEvaluationController",
    "build_initial_final_evaluation_status",
    "discover_latest_frozen_research_report",
]
