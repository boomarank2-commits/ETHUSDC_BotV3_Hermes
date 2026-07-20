"""Task-30 asynchronous UI boundary for the Task-29 research challenger.

The controller contains no market-data loader and no trading logic.  Manual start
only creates the validated empty Task-29 state.  Resume requires an explicit
public-data worker supplied by the existing backend boundary.  No method can
adopt a candidate, write active_config, access private endpoints, or create an
order.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
import threading
from typing import Any, Protocol

from ethusdc_bot.protocol_v3.current_refit import CurrentRefitDecision
from ethusdc_bot.protocol_v3.pipeline import PipelineGeneration
from ethusdc_bot.protocol_v3.research_challenger import (
    ResearchChallengerState,
    start_research_challenger,
    validate_research_challenger_state,
)
from ethusdc_bot.protocol_v3.run_identity import FrozenExchangeInfoSnapshot

StatusCallback = Callable[[dict[str, Any]], None]


class ChallengerInitializer(Protocol):
    def __call__(
        self,
        task28_decision: CurrentRefitDecision,
        *,
        started_at_utc: datetime,
        current_pipeline_generation: PipelineGeneration,
        exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any] | None,
    ) -> ResearchChallengerState: ...


class ChallengerResumeWorker(Protocol):
    def __call__(
        self,
        state: ResearchChallengerState,
        stop_event: threading.Event,
        status_callback: StatusCallback | None,
    ) -> ResearchChallengerState: ...


def build_initial_research_challenger_ui_status() -> dict[str, Any]:
    return _safe_status(
        phase="initial",
        running=False,
        completed=False,
        resume_ready=False,
        stop_requested=False,
        started_at_utc=None,
        finished_at_utc=None,
        state_sha256=None,
        ledger_head_sha256=None,
        ledger_record_count=0,
        mode=None,
        error=None,
    )


class ResearchChallengerController:
    """Own at most one Task-29 initialization or public-data resume worker."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._status_callback: StatusCallback | None = None
        self._status = build_initial_research_challenger_ui_status()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def start(
        self,
        task28_decision: CurrentRefitDecision,
        *,
        started_at_utc: datetime,
        current_pipeline_generation: PipelineGeneration,
        exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any] | None = None,
        status_callback: StatusCallback | None = None,
        initializer: ChallengerInitializer = start_research_challenger,
    ) -> tuple[threading.Thread, dict[str, Any]]:
        """Manually initialize one empty Task-29 state asynchronously."""

        if not isinstance(task28_decision, CurrentRefitDecision):
            raise TypeError("typed CurrentRefitDecision is required")
        if not isinstance(current_pipeline_generation, PipelineGeneration):
            raise TypeError("typed PipelineGeneration is required")
        if not isinstance(started_at_utc, datetime):
            raise TypeError("started_at_utc must be datetime")
        if not callable(initializer):
            raise TypeError("initializer must be callable")
        return self._launch(
            phase="starting",
            started_at_utc=started_at_utc,
            status_callback=status_callback,
            operation=lambda _stop, _callback: initializer(
                task28_decision,
                started_at_utc=started_at_utc,
                current_pipeline_generation=current_pipeline_generation,
                exchange_info_snapshot=exchange_info_snapshot,
            ),
        )

    def resume(
        self,
        state: ResearchChallengerState,
        *,
        worker: ChallengerResumeWorker,
        status_callback: StatusCallback | None = None,
    ) -> tuple[threading.Thread, dict[str, Any]]:
        """Resume only through an explicit public-data backend worker."""

        if not isinstance(state, ResearchChallengerState):
            raise TypeError("typed ResearchChallengerState is required")
        validated = validate_research_challenger_state(state)
        if not callable(worker):
            raise TypeError("worker must be callable")
        started = datetime.now(UTC)
        return self._launch(
            phase="running",
            started_at_utc=started,
            status_callback=status_callback,
            operation=lambda stop, callback: worker(validated, stop, callback),
        )

    def stop(self) -> dict[str, Any]:
        """Request cooperative stop; repeated idle calls are state-neutral."""

        with self._lock:
            if not self._running or self._stop_event is None:
                return dict(self._status)
            self._stop_event.set()
            status = _safe_status(
                **{
                    **self._status,
                    "phase": "stopping",
                    "running": True,
                    "completed": False,
                    "stop_requested": True,
                    "error": None,
                }
            )
            self._status = dict(status)
            callback = self._status_callback
        _notify(callback, status)
        return dict(status)

    def _launch(
        self,
        *,
        phase: str,
        started_at_utc: datetime,
        status_callback: StatusCallback | None,
        operation: Callable[
            [threading.Event, StatusCallback | None], ResearchChallengerState
        ],
    ) -> tuple[threading.Thread, dict[str, Any]]:
        if status_callback is not None and not callable(status_callback):
            raise TypeError("status_callback must be callable or None")
        stop_event = threading.Event()
        started_text = _utc_text(started_at_utc)
        running_status = _safe_status(
            phase=phase,
            running=True,
            completed=False,
            resume_ready=False,
            stop_requested=False,
            started_at_utc=started_text,
            finished_at_utc=None,
            state_sha256=None,
            ledger_head_sha256=None,
            ledger_record_count=0,
            mode=None,
            error=None,
        )
        result_container: dict[str, Any] = {"status": dict(running_status)}

        with self._lock:
            if self._running:
                raise RuntimeError("research challenger worker is already running")
            self._running = True
            self._stop_event = stop_event
            self._status_callback = status_callback
            self._status = dict(running_status)

            def run() -> None:
                try:
                    state = validate_research_challenger_state(
                        operation(stop_event, status_callback)
                    )
                    root = state.to_dict()
                    phase_after = "paused" if stop_event.is_set() else "resume_ready"
                    status = _safe_status(
                        phase=phase_after,
                        running=False,
                        completed=False,
                        resume_ready=True,
                        stop_requested=stop_event.is_set(),
                        started_at_utc=started_text,
                        finished_at_utc=_utc_text(datetime.now(UTC)),
                        state_sha256=state.state_sha256,
                        ledger_head_sha256=root["forward_ledger"]["head_sha256"],
                        ledger_record_count=root["forward_ledger"]["record_count"],
                        mode=root["mode"],
                        error=None,
                    )
                    result_container["state"] = state
                except BaseException as exc:
                    status = _safe_status(
                        phase="failed",
                        running=False,
                        completed=False,
                        resume_ready=False,
                        stop_requested=stop_event.is_set(),
                        started_at_utc=started_text,
                        finished_at_utc=_utc_text(datetime.now(UTC)),
                        state_sha256=None,
                        ledger_head_sha256=None,
                        ledger_record_count=0,
                        mode=None,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                result_container["status"] = dict(status)
                with self._lock:
                    self._status = dict(status)
                    self._running = False
                    self._stop_event = None
                    callback = self._status_callback
                    self._status_callback = None
                _notify(callback, status)

            thread = threading.Thread(
                target=run,
                name="ethusdc-protocol-v3-research-challenger",
                daemon=True,
            )
            self._thread = thread

        _notify(status_callback, running_status)
        try:
            thread.start()
        except BaseException:
            with self._lock:
                self._running = False
                self._stop_event = None
                self._status_callback = None
            raise
        return thread, result_container


def _safe_status(**values: Any) -> dict[str, Any]:
    return {
        "schema_version": "protocol_v3_research_challenger_ui_status_v1",
        **values,
        "public_data_only": True,
        "diagnostic_only": True,
        "freshness": "NOT_FRESH",
        "statistically_supported": False,
        "canonical_adoption_eligible": False,
        "protocol_v3_final_status": False,
        "orders_allowed": False,
        "orders_created": 0,
        "paper_allowed": False,
        "testtrade_allowed": False,
        "live_allowed": False,
        "trading_api_allowed": False,
        "private_api_calls": 0,
        "api_keys_used": False,
        "active_config_written": False,
    }


def _notify(callback: StatusCallback | None, status: Mapping[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(dict(status))
    except Exception:
        return


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "ResearchChallengerController",
    "build_initial_research_challenger_ui_status",
]
