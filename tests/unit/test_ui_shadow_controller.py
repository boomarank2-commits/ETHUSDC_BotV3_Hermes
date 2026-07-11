"""Tests for the explicit order-free Shadow UI controller."""

from __future__ import annotations

from types import SimpleNamespace
import threading

import pytest

from ethusdc_bot.ui.shadow_controller import (
    ShadowController,
    build_initial_shadow_status,
)


_LOCKED_FLAGS = (
    "may_trigger_orders",
    "may_submit_orders",
    "orders_created",
    "trading_api_used",
    "api_keys_used",
    "live_enabled",
    "live_eligible",
    "live_trading_enabled",
    "paper_eligible",
    "testtrade_eligible",
)


def _assert_order_and_live_paths_locked(status):
    assert status["public_data_only"] is True
    assert status["hypothetical"] is True
    for field in _LOCKED_FLAGS:
        assert status[field] is False


def test_initial_controller_is_inert_and_does_not_open_runtime():
    calls = []
    controller = ShadowController()

    # Merely constructing or inspecting the controller cannot invoke a hook.
    def opener(_path):
        calls.append("opened")

    status = controller.status_snapshot()

    assert calls == []
    assert controller.is_running is False
    assert status == build_initial_shadow_status()
    assert status["phase"] == "initial"
    assert status["running"] is False
    assert status["completed"] is False
    assert status["error"] is None
    _assert_order_and_live_paths_locked(status)
    assert callable(opener)


def test_start_uses_injected_hooks_and_publishes_running_then_completed(tmp_path):
    callbacks = []
    calls = []
    runtime = SimpleNamespace(state={"deployment_id": "shadow-123"})
    controller = ShadowController()

    def opener(path):
        calls.append(("open", path))
        return runtime

    def poller(opened_runtime, stop_event):
        calls.append(("poll", opened_runtime, stop_event.is_set()))

    thread, container = controller.start(
        tmp_path / "shadow-123",
        status_callback=callbacks.append,
        runtime_opener=opener,
        poller=poller,
    )

    assert thread.daemon is True
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert calls[0] == ("open", tmp_path / "shadow-123")
    assert calls[1][0:2] == ("poll", runtime)
    assert calls[1][2] is False
    assert callbacks[0]["phase"] == "running"
    assert callbacks[0]["running"] is True
    assert callbacks[-1]["phase"] == "completed"
    assert callbacks[-1]["completed"] is True
    assert callbacks[-1]["error"] is None
    status = container["status"]
    assert status["deployment_id"] == "shadow-123"
    assert status == controller.status_snapshot()
    assert controller.is_running is False
    _assert_order_and_live_paths_locked(callbacks[0])
    _assert_order_and_live_paths_locked(status)


def test_overlap_is_rejected_and_stop_is_cooperative_and_idempotent(tmp_path):
    entered = threading.Event()
    stop_observed = threading.Event()
    allow_return = threading.Event()
    callbacks = []
    controller = ShadowController()

    def poller(_runtime, stop_event):
        entered.set()
        assert stop_event.wait(timeout=5)
        stop_observed.set()
        assert allow_return.wait(timeout=5)

    thread, container = controller.start(
        tmp_path,
        status_callback=callbacks.append,
        runtime_opener=lambda _path: SimpleNamespace(state={}),
        poller=poller,
    )
    assert entered.wait(timeout=5)

    with pytest.raises(RuntimeError, match="already running"):
        controller.start(
            tmp_path,
            runtime_opener=lambda _path: SimpleNamespace(state={}),
            poller=poller,
        )

    first = controller.stop()
    second = controller.stop()
    assert stop_observed.wait(timeout=5)
    assert first["phase"] == "stopping"
    assert second["phase"] == "stopping"
    assert first["stop_requested"] is True
    assert second["stop_requested"] is True
    _assert_order_and_live_paths_locked(first)

    allow_return.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    status = container["status"]
    assert status["phase"] == "completed"
    assert status["running"] is False
    assert status["completed"] is True
    assert status["stop_requested"] is True
    assert callbacks[-1] == status

    # Once idle, another stop preserves the completed snapshot.
    assert controller.stop() == status


def test_worker_failure_is_reported_without_unlocking_external_actions(tmp_path):
    controller = ShadowController()
    callbacks = []

    def poller(_runtime, _stop_event):
        raise RuntimeError("public feed unavailable")

    thread, container = controller.start(
        tmp_path,
        status_callback=callbacks.append,
        runtime_opener=lambda _path: SimpleNamespace(state={}),
        poller=poller,
    )
    thread.join(timeout=5)

    status = container["status"]
    assert status["phase"] == "failed"
    assert status["running"] is False
    assert status["completed"] is False
    assert status["error"] == "RuntimeError: public feed unavailable"
    assert callbacks[-1] == status
    assert controller.is_running is False
    _assert_order_and_live_paths_locked(status)


def test_idle_stop_is_idempotent_and_callback_failure_is_isolated(tmp_path):
    controller = ShadowController()
    assert controller.stop() == build_initial_shadow_status()
    assert controller.stop() == build_initial_shadow_status()

    def broken_callback(_status):
        raise RuntimeError("UI is closing")

    thread, container = controller.start(
        tmp_path,
        status_callback=broken_callback,
        runtime_opener=lambda _path: SimpleNamespace(state={}),
        poller=lambda _runtime, _stop: None,
    )
    thread.join(timeout=5)
    assert container["status"]["phase"] == "completed"


@pytest.mark.parametrize("field", ["runtime_opener", "poller", "status_callback"])
def test_start_rejects_non_callable_hooks(field, tmp_path):
    controller = ShadowController()
    kwargs = {
        "runtime_opener": lambda _path: SimpleNamespace(state={}),
        "poller": lambda _runtime, _stop: None,
        "status_callback": lambda _status: None,
    }
    kwargs[field] = object()

    with pytest.raises(TypeError, match=field):
        controller.start(tmp_path, **kwargs)
    assert controller.is_running is False
