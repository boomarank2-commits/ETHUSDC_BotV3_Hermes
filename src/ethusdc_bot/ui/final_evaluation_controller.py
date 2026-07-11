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
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            invalid_count += 1
            continue
        if not isinstance(payload, Mapping):
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
