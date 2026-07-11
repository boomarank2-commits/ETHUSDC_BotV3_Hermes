"""Safe asynchronous UI controller for Protocol-v2 training research.

Only the canonical training/validation/walk-forward research loop is started.
The controller has no final-holdout evaluator, exchange adapter, credentials,
account access, or order capability, and it never makes a run shadow-eligible.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import json
from pathlib import Path
import threading
from typing import Any

from ethusdc_bot.backtest.research_loop_runner import (
    LoopConfig,
    LoopRunResult,
    run_research_loop,
)
from ethusdc_bot.backtest.split import REQUIRED_DAYS


StatusCallback = Callable[[dict[str, Any]], None]
ResearchRunner = Callable[[LoopConfig], LoopRunResult | Any]


def build_initial_training_research_status() -> dict[str, Any]:
    """Return the fail-closed status before any training research is started."""

    return {
        "schema_version": 1,
        "phase": "initial",
        "running": False,
        "started_at": None,
        "finished_at": None,
        "report_path": None,
        "freeze_status": "not_run",
        "blocked": True,
        "blocked_reason": "training_research_not_run",
        "error": None,
        "final_holdout_evaluated": False,
        "shadow_eligible": False,
        "orders_created": False,
        "trading_api_used": False,
        "api_keys_used": False,
    }


def build_canonical_training_loop_config(
    raw_root: str | Path,
    reports_root: str | Path,
) -> LoopConfig:
    """Build the one production configuration permitted by this controller."""

    return LoopConfig(
        raw_root=raw_root,
        reports_root=reports_root,
        max_cycles=8,
        max_candidates_per_cycle=40,
        tested_candidates_per_cycle=12,
        walk_forward_candidates_per_cycle=3,
        finalists_per_cycle=2,
        walk_forward_fold_count=6,
        rolling_origin_limit=3,
        rolling_origin_step_days=365,
        min_cycles=3,
        stagnation_cycles=3,
        required_days=REQUIRED_DAYS,
    )


class TrainingResearchController:
    """Own a single daemon worker and reject overlapping research starts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._status = build_initial_training_research_status()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def start(
        self,
        raw_root: str | Path,
        reports_root: str | Path,
        status_callback: StatusCallback | None = None,
        runner: ResearchRunner = run_research_loop,
    ) -> tuple[threading.Thread, dict[str, Any]]:
        """Start exactly one canonical training-research worker.

        The returned container is updated to ``completed`` or ``failed`` by
        the worker. Exceptions are represented in that status and do not
        escape the background thread.
        """

        if not callable(runner):
            raise TypeError("runner must be callable")
        if status_callback is not None and not callable(status_callback):
            raise TypeError("status_callback must be callable or None")
        config = build_canonical_training_loop_config(raw_root, reports_root)
        started_at = _utc_now()
        running_status = _safe_status(
            phase="running",
            running=True,
            started_at=started_at,
            finished_at=None,
            freeze_status="not_evaluated_training_running",
            blocked=True,
            blocked_reason="training_research_running",
        )
        result_container: dict[str, Any] = {"status": dict(running_status)}

        with self._lock:
            if self._running:
                raise RuntimeError("training research is already running")
            self._running = True
            self._status = dict(running_status)

            def worker() -> None:
                try:
                    result = runner(config)
                    status = _completed_status(result, started_at=started_at)
                except BaseException as error:  # background boundary must publish failure
                    status = _failed_status(error, started_at=started_at)
                result_container["status"] = dict(status)
                with self._lock:
                    self._status = dict(status)
                    self._running = False
                _notify(status_callback, status)

            thread = threading.Thread(
                target=worker,
                name="ethusdc-training-research",
                daemon=True,
            )
            self._thread = thread

        _notify(status_callback, running_status)
        try:
            thread.start()
        except BaseException:
            with self._lock:
                self._running = False
            raise
        return thread, result_container


def run_training_research_async(
    raw_root: str | Path,
    reports_root: str | Path,
    status_callback: StatusCallback | None = None,
    runner: ResearchRunner = run_research_loop,
) -> tuple[threading.Thread, dict[str, Any]]:
    """Start canonical training-only research on the shared UI controller."""

    return _DEFAULT_CONTROLLER.start(
        raw_root,
        reports_root,
        status_callback=status_callback,
        runner=runner,
    )


def _completed_status(result: Any, *, started_at: str) -> dict[str, Any]:
    report_path = _result_report_path(result)
    if report_path is None:
        return _safe_status(
            phase="completed",
            running=False,
            started_at=started_at,
            finished_at=_utc_now(),
            report_path=None,
            freeze_status="blocked_missing_report",
            blocked=True,
            blocked_reason="training_runner_returned_no_report",
        )

    freeze_status, report_error = _read_freeze_status(report_path)
    if freeze_status is None:
        return _safe_status(
            phase="completed",
            running=False,
            started_at=started_at,
            finished_at=_utc_now(),
            report_path=str(report_path),
            freeze_status="blocked_missing_freeze_status",
            blocked=True,
            blocked_reason=report_error or "report_has_no_freeze_status",
        )

    frozen_for_holdout = freeze_status == "frozen_for_separate_sealed_holdout"
    return _safe_status(
        phase="completed",
        running=False,
        started_at=started_at,
        finished_at=_utc_now(),
        report_path=str(report_path),
        freeze_status=freeze_status,
        blocked=not frozen_for_holdout,
        blocked_reason=None if frozen_for_holdout else freeze_status,
    )


def _failed_status(error: BaseException, *, started_at: str) -> dict[str, Any]:
    error_text = f"{type(error).__name__}: {error}"
    return _safe_status(
        phase="failed",
        running=False,
        started_at=started_at,
        finished_at=_utc_now(),
        freeze_status="blocked",
        blocked=True,
        blocked_reason="training_research_failed",
        error=error_text,
    )


def _safe_status(**updates: Any) -> dict[str, Any]:
    status = build_initial_training_research_status()
    status.update(updates)
    # These values cannot be overridden by a runner or report.
    status.update(
        {
            "final_holdout_evaluated": False,
            "shadow_eligible": False,
            "orders_created": False,
            "trading_api_used": False,
            "api_keys_used": False,
        }
    )
    return status


def _result_report_path(result: Any) -> Path | None:
    report_paths = (
        result.get("report_paths") if isinstance(result, Mapping) else getattr(result, "report_paths", None)
    )
    json_path = (
        report_paths.get("json_path")
        if isinstance(report_paths, Mapping)
        else getattr(report_paths, "json_path", None)
    )
    if not isinstance(json_path, (str, Path)):
        return None
    return Path(json_path)


def _read_freeze_status(report_path: Path) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return None, f"report_unreadable: {error}"
    if not isinstance(payload, Mapping):
        return None, "report_root_is_not_an_object"
    freeze_status = payload.get("freeze_status")
    if not isinstance(freeze_status, str) or not freeze_status.strip():
        return None, "report_has_no_freeze_status"
    return freeze_status, None


def _notify(callback: StatusCallback | None, status: Mapping[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(dict(status))
    except Exception:
        # UI callback failures must not duplicate, cancel, or relaunch research.
        return


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


_DEFAULT_CONTROLLER = TrainingResearchController()


__all__ = [
    "TrainingResearchController",
    "build_canonical_training_loop_config",
    "build_initial_training_research_status",
    "run_training_research_async",
]
