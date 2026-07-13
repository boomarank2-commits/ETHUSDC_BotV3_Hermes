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
import re
import subprocess
import threading
from typing import Any

from ethusdc_bot.backtest.research_loop_runner import LoopConfig
from ethusdc_bot.backtest.split import REQUIRED_DAYS


StatusCallback = Callable[[dict[str, Any]], None]
ResearchRunner = Callable[[LoopConfig], Any]
_REPORT_JSON = re.compile(r"^Report JSON:\s+(?P<path>.+)$")
_PRODUCTION_DATA_END_DAY = "2026-07-07"
_SUPERVISOR_CHECKPOINT_PATTERN = "production_research_supervisor_*.checkpoint.json"


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
        "production_path": "ui_to_windows_starter_to_supervisor_to_pr12_runner",
        "context_research_enabled": True,
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
        enable_context=True,
        data_end_day=_PRODUCTION_DATA_END_DAY,
    )


def run_production_research_via_starter(config: LoopConfig) -> dict[str, Any]:
    """Invoke the existing PR12 Windows starter instead of the direct runner."""

    if config.enable_context is not True:
        raise ValueError("UI production research requires context enabled")
    if config.data_end_day != _PRODUCTION_DATA_END_DAY:
        raise ValueError("UI production research requires the bound common data cutoff")
    repository_root = Path(__file__).resolve().parents[3]
    script = repository_root / "tools" / "run_production_research.ps1"
    if not script.is_file():
        raise RuntimeError(f"production research starter is missing: {script}")
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-RawRoot",
        str(config.raw_root),
        "-ReportsRoot",
        str(config.reports_root),
        "-MaxCycles",
        str(config.max_cycles),
        "-DataEndDay",
        config.data_end_day,
    ]
    process = subprocess.Popen(
        command,
        cwd=repository_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
        process.kill()
        raise RuntimeError("production research starter stdout is unavailable")
    output_tail: list[str] = []
    report_path: Path | None = None
    for raw_line in process.stdout:
        line = raw_line.rstrip("\r\n")
        print(line, flush=True)
        output_tail.append(line)
        output_tail = output_tail[-30:]
        match = _REPORT_JSON.fullmatch(line.strip())
        if match is not None:
            report_path = Path(match.group("path").strip())
    exit_code = process.wait()
    if exit_code != 0:
        detail = "\n".join(output_tail[-10:])
        raise RuntimeError(
            f"PR12 production starter failed with exit code {exit_code}: {detail}"
        )
    if report_path is None or not report_path.is_file():
        raise RuntimeError("PR12 production starter returned no existing report JSON")
    return {"report_paths": {"json_path": report_path}}


class TrainingResearchController:
    """Own one durable starter worker and reject overlapping research starts."""

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
        runner: ResearchRunner = run_production_research_via_starter,
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
        active_checkpoint = discover_active_research_checkpoint(reports_root)
        if active_checkpoint is not None:
            raise RuntimeError(
                "durable production research is already running: "
                f"{active_checkpoint.get('run_id') or 'unknown_run'}"
            )
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
                daemon=False,
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
    runner: ResearchRunner = run_production_research_via_starter,
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
            "production_path": "ui_to_windows_starter_to_supervisor_to_pr12_runner",
            "context_research_enabled": True,
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
    compact_path = report_path.with_suffix(".txt")
    try:
        if compact_path.is_file():
            for line in compact_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("Freeze status:"):
                    value = line.split(":", 1)[1].strip()
                    if value:
                        return value, None
    except (OSError, UnicodeError) as error:
        return None, f"compact_report_unreadable: {error}"
    try:
        if report_path.stat().st_size > 8_000_000:
            return None, "report_too_large_without_compact_freeze_status"
    except OSError as error:
        return None, f"report_unreadable: {error}"
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


def discover_active_research_checkpoint(reports_root: str | Path) -> dict[str, Any] | None:
    """Recover a durable active supervisor after a dashboard restart."""

    root = Path(reports_root)
    if not root.exists():
        return None
    paths = [path for path in root.glob(_SUPERVISOR_CHECKPOINT_PATTERN) if path.is_file()]
    if not paths:
        return None
    path = max(paths, key=lambda item: (item.stat().st_mtime_ns, item.name))
    try:
        if path.stat().st_size > 1_000_000:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("status") not in {"starting", "running"}:
        return None
    return payload


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
    "discover_active_research_checkpoint",
    "run_production_research_via_starter",
    "run_training_research_async",
]
