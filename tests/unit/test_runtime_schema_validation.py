"""Strict schema validation tests for runtime templates."""

from copy import deepcopy
from pathlib import Path
import json

import pytest

from ethusdc_bot.runtime.schema import (
    validate_progress_state,
    validate_runtime_locks,
    validate_runtime_state,
)
from ethusdc_bot.validation import SchemaValidationError


ROOT = Path(__file__).resolve().parents[2]


def load_json(relative_path):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def assert_rejected(callable_, data):
    with pytest.raises(SchemaValidationError):
        callable_(data)


def test_default_locks_template_passes_strict_schema_validation():
    validate_runtime_locks(load_json("runtime/default_locks.example.json"))


def test_default_runtime_state_template_passes_strict_schema_validation():
    validate_runtime_state(load_json("runtime/default_runtime_state.example.json"))


def test_default_progress_state_template_passes_strict_schema_validation():
    validate_progress_state(load_json("runtime/default_progress_state.example.json"))


@pytest.mark.parametrize(
    "lock_name",
    ["live_trading", "paper_trading", "testtrade", "shorts_margin_futures_leverage"],
)
def test_runtime_locks_reject_enabled_true(lock_name):
    locks = load_json("runtime/default_locks.example.json")
    locks["locks"][lock_name]["enabled"] = True

    assert_rejected(validate_runtime_locks, locks)


@pytest.mark.parametrize("bad_schema_version", [0, 2, "1"])
def test_runtime_locks_reject_bad_schema_version(bad_schema_version):
    locks = load_json("runtime/default_locks.example.json")
    locks["schema_version"] = bad_schema_version

    assert_rejected(validate_runtime_locks, locks)


def test_runtime_locks_reject_template_false():
    locks = load_json("runtime/default_locks.example.json")
    locks["template"] = False

    assert_rejected(validate_runtime_locks, locks)


def test_runtime_locks_reject_missing_required_fields():
    locks = load_json("runtime/default_locks.example.json")
    del locks["locks"]["live_trading"]["reason"]

    assert_rejected(validate_runtime_locks, locks)


def test_runtime_locks_reject_unknown_keys():
    locks = load_json("runtime/default_locks.example.json")
    locks["locks"]["live_trading"]["unlock_after"] = "soon"

    assert_rejected(validate_runtime_locks, locks)


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("template", False),
        ("schema_version", 2),
        ("symbol", "BTCUSDC"),
        ("quote_asset", "USDT"),
        ("market_type", "binance_futures"),
        ("status", "running"),
        ("live_status", "unlocked"),
        ("paper_status", "unlocked"),
        ("testtrade_status", "unlocked"),
        ("active_candidate", {"id": "fake"}),
        ("last_report_id", "report-1"),
    ],
)
def test_runtime_state_rejects_forbidden_values(key, bad_value):
    state = load_json("runtime/default_runtime_state.example.json")
    state[key] = bad_value

    assert_rejected(validate_runtime_state, state)


def test_runtime_state_rejects_missing_required_fields():
    state = load_json("runtime/default_runtime_state.example.json")
    del state["live_status"]

    assert_rejected(validate_runtime_state, state)


def test_runtime_state_rejects_unknown_keys():
    state = load_json("runtime/default_runtime_state.example.json")
    state["paper_enabled"] = True

    assert_rejected(validate_runtime_state, state)


@pytest.mark.parametrize(
    ("key", "bad_value"),
    [
        ("template", False),
        ("schema_version", 2),
        ("project_phase", "phase_2_data"),
        ("current_ticket", "ticket-1"),
        ("completed_steps", ["fake step"]),
        ("blocked_steps", ["fake blocker"]),
        ("next_smallest_step", ""),
    ],
)
def test_progress_state_rejects_forbidden_values(key, bad_value):
    progress = load_json("runtime/default_progress_state.example.json")
    progress[key] = bad_value

    assert_rejected(validate_progress_state, progress)


def test_progress_state_rejects_unknown_keys():
    progress = load_json("runtime/default_progress_state.example.json")
    progress["engine_progress"] = "started"

    assert_rejected(validate_progress_state, progress)
