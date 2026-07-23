"""Task-30 asynchronous UI boundary for the Task-29 research challenger.

The controller contains no market-data loader and no trading logic. Manual start
only creates the validated empty Task-29 state. Resume requires an explicit
public-data worker and a bit-identical Task-13 checkpoint receipt. No method can
adopt a candidate, write active_config, access private endpoints, or create an
order.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import threading
from typing import Any, Protocol

from ethusdc_bot.protocol_v3.current_refit import CurrentRefitDecision
from ethusdc_bot.protocol_v3.pipeline import PipelineGeneration
from ethusdc_bot.protocol_v3.research_challenger import (
    ResearchChallengerState,
    start_research_challenger,
    validate_research_challenger_state,
)
from ethusdc_bot.protocol_v3.research_challenger_checkpoint import (
    ResearchChallengerCheckpointReceipt,
    validate_research_challenger_checkpoint_receipt,
    verify_replayed_research_challenger_checkpoint,
)
from ethusdc_bot.protocol_v3.run_identity import FrozenExchangeInfoSnapshot

StatusCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ResearchChallengerUiRunResult:
    """Typed backend result returned to the UI boundary."""

    state: ResearchChallengerState
    checkpoint_receipt: ResearchChallengerCheckpointReceipt | None


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
    ) -> ResearchChallengerUiRunResult: ...


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
        checkpoint_receipt_sha256=None,
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
        self._state: ResearchChallengerState | None = None
        self._checkpoint_receipt: ResearchChallengerCheckpointReceipt | None = None

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def state_snapshot(self) -> ResearchChallengerState | None:
        with self._lock:
            return self._state

    def checkpoint_snapshot(self) -> ResearchChallengerCheckpointReceipt | None:
        with self._lock:
            return self._checkpoint_receipt

    def start(
        self,
        task28_decision: CurrentRefitDecision,
        *,
        started_at_utc: datetime,
        current_pipeline_generation: PipelineGeneration,
        exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any] | None = None,
        worker: ChallengerResumeWorker | None = None,
        status_callback: StatusCallback | None = None,
        initializer: ChallengerInitializer = start_research_challenger,
    ) -> tuple[threading.Thread, dict[str, Any]]:
        """Initialize Task 29 and optionally run a checkpointing backend."""

        if not isinstance(task28_decision, CurrentRefitDecision):
            raise TypeError("typed CurrentRefitDecision is required")
        if not isinstance(current_pipeline_generation, PipelineGeneration):
            raise TypeError("typed PipelineGeneration is required")
        _require_utc(started_at_utc, "started_at_utc")
        if not callable(initializer):
            raise TypeError("initializer must be callable")
        if worker is not None and not callable(worker):
            raise TypeError("worker must be callable or None")

        def operation(
            stop_event: threading.Event,
            callback: StatusCallback | None,
        ) -> ResearchChallengerUiRunResult:
            initial = validate_research_challenger_state(
                initializer(
                    task28_decision,
                    started_at_utc=started_at_utc,
                    current_pipeline_generation=current_pipeline_generation,
                    exchange_info_snapshot=exchange_info_snapshot,
                )
            )
            if worker is None:
                return ResearchChallengerUiRunResult(initial, None)
            result = worker(initial, stop_event, callback)
            if not isinstance(result, ResearchChallengerUiRunResult):
                raise TypeError(
                    "challenger backend worker must return ResearchChallengerUiRunResult"
                )
            current = validate_research_challenger_state(result.state)
            if not isinstance(
                result.checkpoint_receipt, ResearchChallengerCheckpointReceipt
            ):
                raise TypeError("challenger backend must return a checkpoint receipt")
            receipt = validate_research_challenger_checkpoint_receipt(
                result.checkpoint_receipt
            )
            verify_replayed_research_challenger_checkpoint(receipt, current)
            return ResearchChallengerUiRunResult(current, receipt)

        return self._launch(
            phase="starting",
            started_at_utc=started_at_utc,
            status_callback=status_callback,
            checkpoint_required=worker is not None,
            operation=operation,
        )

    def resume(
        self,
        state: ResearchChallengerState,
        checkpoint_receipt: ResearchChallengerCheckpointReceipt,
        *,
        worker: ChallengerResumeWorker,
        status_callback: StatusCallback | None = None,
    ) -> tuple[threading.Thread, dict[str, Any]]:
        """Resume only from a bit-identical checkpoint through a backend worker."""

        if not isinstance(state, ResearchChallengerState):
            raise TypeError("typed ResearchChallengerState is required")
        if not isinstance(
            checkpoint_receipt, ResearchChallengerCheckpointReceipt
        ):
            raise TypeError("typed ResearchChallengerCheckpointReceipt is required")
        validated = validate_research_challenger_state(state)
        receipt = validate_research_challenger_checkpoint_receipt(checkpoint_receipt)
        verify_replayed_research_challenger_checkpoint(receipt, validated)
        if not callable(worker):
            raise TypeError("worker must be callable")
        started = datetime.now(UTC)

        def operation(
            stop_event: threading.Event,
            callback: StatusCallback | None,
        ) -> ResearchChallengerUiRunResult:
            result = worker(validated, stop_event, callback)
            if not isinstance(result, ResearchChallengerUiRunResult):
                raise TypeError(
                    "challenger backend worker must return ResearchChallengerUiRunResult"
                )
            current = validate_research_challenger_state(result.state)
            if not isinstance(
                result.checkpoint_receipt, ResearchChallengerCheckpointReceipt
            ):
                raise TypeError("challenger backend must return a checkpoint receipt")
            current_receipt = validate_research_challenger_checkpoint_receipt(
                result.checkpoint_receipt
            )
            verify_replayed_research_challenger_checkpoint(current_receipt, current)
            return ResearchChallengerUiRunResult(current, current_receipt)

        return self._launch(
            phase="running",
            started_at_utc=started,
            status_callback=status_callback,
            checkpoint_required=True,
            operation=operation,
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
        checkpoint_required: bool,
        operation: Callable[
            [threading.Event, StatusCallback | None], ResearchChallengerUiRunResult
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
            checkpoint_receipt_sha256=None,
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
                    result = operation(stop_event, status_callback)
                    if not isinstance(result, ResearchChallengerUiRunResult):
                        raise TypeError("invalid research challenger UI run result")
                    state = validate_research_challenger_state(result.state)
                    receipt = result.checkpoint_receipt
                    if checkpoint_required and receipt is None:
                        raise TypeError("checkpointed challenger result is required")
                    if receipt is not None:
                        receipt = validate_research_challenger_checkpoint_receipt(receipt)
                        verify_replayed_research_challenger_checkpoint(receipt, state)
                    root = state.to_dict()
                    resume_ready = receipt is not None
                    if stop_event.is_set():
                        phase_after = (
                            "paused" if resume_ready else "paused_uncheckpointed"
                        )
                    else:
                        phase_after = "resume_ready" if resume_ready else "initialized"
                    status = _safe_status(
                        phase=phase_after,
                        running=False,
                        completed=False,
                        resume_ready=resume_ready,
                        stop_requested=stop_event.is_set(),
                        started_at_utc=started_text,
                        finished_at_utc=_utc_text(datetime.now(UTC)),
                        state_sha256=state.state_sha256,
                        ledger_head_sha256=root["forward_ledger"]["head_sha256"],
                        ledger_record_count=root["forward_ledger"]["record_count"],
                        checkpoint_receipt_sha256=(
                            None if receipt is None else receipt.receipt_sha256
                        ),
                        mode=root["mode"],
                        error=None,
                    )
                    result_container["state"] = state
                    result_container["checkpoint_receipt"] = receipt
                except BaseException as exc:
                    state = None
                    receipt = None
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
                        checkpoint_receipt_sha256=None,
                        mode=None,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                result_container["status"] = dict(status)
                with self._lock:
                    if state is not None:
                        self._state = state
                        self._checkpoint_receipt = receipt
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


def _require_utc(value: Any, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return _require_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


__all__ = [
    "ResearchChallengerController",
    "ResearchChallengerUiRunResult",
    "build_initial_research_challenger_ui_status",
]
