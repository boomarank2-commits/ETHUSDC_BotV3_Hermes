"""Explicit asynchronous UI boundary for the order-free Shadow runtime.

Constructing this controller has no side effects.  A caller must explicitly
start an adopted deployment, and stopping is cooperative through a private
``threading.Event``.  The default worker opens :class:`ShadowRuntime` and runs
only its public-data poller; dependency hooks keep the boundary deterministic
and network-free in tests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
import threading
from typing import Any, Protocol

from ethusdc_bot.shadow.runtime import ShadowRuntime


StatusCallback = Callable[[dict[str, Any]], None]


class RuntimeOpener(Protocol):
    def __call__(self, deployment_dir: str | Path) -> Any: ...


class RuntimePoller(Protocol):
    def __call__(self, runtime: Any, stop_event: threading.Event) -> Any: ...


def build_initial_shadow_status() -> dict[str, Any]:
    """Return the inert, fail-closed status before an explicit start."""

    return _safe_status(
        phase="initial",
        running=False,
        completed=False,
        stop_requested=False,
        started_at=None,
        finished_at=None,
        deployment_dir=None,
        deployment_id=None,
        error=None,
    )


class ShadowController:
    """Own at most one daemon worker for public-data Shadow consumption."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._status_callback: StatusCallback | None = None
        self._status = build_initial_shadow_status()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def start(
        self,
        deployment_dir: str | Path,
        *,
        status_callback: StatusCallback | None = None,
        runtime_opener: RuntimeOpener = ShadowRuntime.open,
        poller: RuntimePoller | None = None,
    ) -> tuple[threading.Thread, dict[str, Any]]:
        """Explicitly start one order-free Shadow worker.

        ``runtime_opener`` and ``poller`` are injection boundaries.  The
        production default calls ``runtime.run_poller(stop_event)``; tests may
        replace both without touching the network or deployment files.
        """

        if not callable(runtime_opener):
            raise TypeError("runtime_opener must be callable")
        if poller is not None and not callable(poller):
            raise TypeError("poller must be callable or None")
        if status_callback is not None and not callable(status_callback):
            raise TypeError("status_callback must be callable or None")

        root = Path(deployment_dir)
        started_at = _utc_now()
        stop_event = threading.Event()
        running_status = _safe_status(
            phase="running",
            running=True,
            completed=False,
            stop_requested=False,
            started_at=started_at,
            finished_at=None,
            deployment_dir=str(root),
            deployment_id=None,
            error=None,
        )
        result_container: dict[str, Any] = {"status": dict(running_status)}

        with self._lock:
            if self._running:
                raise RuntimeError("Shadow runtime is already running")
            self._running = True
            self._stop_event = stop_event
            self._status_callback = status_callback
            self._status = dict(running_status)

            def worker() -> None:
                try:
                    runtime = runtime_opener(root)
                    deployment_id = _runtime_deployment_id(runtime)
                    effective_poller = poller or _run_runtime_poller
                    effective_poller(runtime, stop_event)
                    status = _safe_status(
                        phase="completed",
                        running=False,
                        completed=True,
                        stop_requested=stop_event.is_set(),
                        started_at=started_at,
                        finished_at=_utc_now(),
                        deployment_dir=str(root),
                        deployment_id=deployment_id,
                        error=None,
                    )
                except BaseException as exc:  # publish the background boundary
                    status = _safe_status(
                        phase="failed",
                        running=False,
                        completed=False,
                        stop_requested=stop_event.is_set(),
                        started_at=started_at,
                        finished_at=_utc_now(),
                        deployment_dir=str(root),
                        deployment_id=None,
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
                target=worker,
                name="ethusdc-shadow-public-poller",
                daemon=True,
            )
            self._thread = thread

        _notify(status_callback, running_status)
        try:
            thread.start()
        except BaseException as exc:
            failed_status = _safe_status(
                phase="failed",
                running=False,
                completed=False,
                stop_requested=False,
                started_at=started_at,
                finished_at=_utc_now(),
                deployment_dir=str(root),
                deployment_id=None,
                error=f"{type(exc).__name__}: {exc}",
            )
            result_container["status"] = dict(failed_status)
            with self._lock:
                self._running = False
                self._stop_event = None
                self._status_callback = None
                self._status = dict(failed_status)
            _notify(status_callback, failed_status)
            raise
        return thread, result_container

    def stop(self) -> dict[str, Any]:
        """Request a cooperative stop; repeated or idle calls are harmless."""

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


def _run_runtime_poller(runtime: Any, stop_event: threading.Event) -> Any:
    run_poller = getattr(runtime, "run_poller", None)
    if not callable(run_poller):
        raise TypeError("opened Shadow runtime must provide run_poller()")
    return run_poller(stop_event)


def _runtime_deployment_id(runtime: Any) -> str | None:
    state = getattr(runtime, "state", None)
    if not isinstance(state, Mapping):
        return None
    value = state.get("deployment_id")
    return value if isinstance(value, str) and value else None


def _safe_status(**values: Any) -> dict[str, Any]:
    status = {
        "schema_version": 1,
        **values,
        "public_data_only": True,
        "hypothetical": True,
        "may_trigger_orders": False,
        "may_submit_orders": False,
        "orders_created": False,
        "trading_api_used": False,
        "api_keys_used": False,
        "live_enabled": False,
        "live_eligible": False,
        "live_trading_enabled": False,
        "paper_eligible": False,
        "testtrade_eligible": False,
    }
    return status


def _notify(callback: StatusCallback | None, status: Mapping[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(dict(status))
    except Exception:
        # UI callback failures must not relaunch or interrupt Shadow replay.
        return


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "ShadowController",
    "build_initial_shadow_status",
]
