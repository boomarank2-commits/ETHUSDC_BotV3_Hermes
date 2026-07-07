"""Strict schema validation for Phase 1 runtime templates."""

from collections.abc import Mapping
from typing import Any

from ethusdc_bot.validation import (
    require_empty_list,
    require_exact_keys,
    require_false,
    require_literal,
    require_mapping,
    require_non_empty_string,
    require_none,
)


LOCK_KEYS = {"enabled", "reason"}
LOCK_NAMES = {
    "live_trading",
    "paper_trading",
    "testtrade",
    "shorts_margin_futures_leverage",
}
RUNTIME_LOCKS_KEYS = {"schema_version", "template", "locks"}
RUNTIME_STATE_KEYS = {
    "schema_version",
    "template",
    "phase",
    "symbol",
    "quote_asset",
    "market_type",
    "status",
    "live_status",
    "paper_status",
    "testtrade_status",
    "active_candidate",
    "last_report_id",
    "notes",
}
PROGRESS_STATE_KEYS = {
    "schema_version",
    "template",
    "project_phase",
    "current_ticket",
    "completed_steps",
    "blocked_steps",
    "next_smallest_step",
    "notes",
}


def validate_runtime_locks(data: Mapping[str, Any]) -> None:
    """Validate runtime lock template while keeping every gate locked."""

    root = require_mapping(data, "runtime_locks")
    require_exact_keys(root, RUNTIME_LOCKS_KEYS, "runtime_locks")
    require_literal(root, "schema_version", 1, "runtime_locks")
    require_literal(root, "template", True, "runtime_locks")

    locks = require_mapping(root["locks"], "runtime_locks.locks")
    require_exact_keys(locks, LOCK_NAMES, "runtime_locks.locks")
    for lock_name in sorted(LOCK_NAMES):
        lock = require_mapping(locks[lock_name], f"runtime_locks.locks.{lock_name}")
        require_exact_keys(lock, LOCK_KEYS, f"runtime_locks.locks.{lock_name}")
        require_false(lock, "enabled", f"runtime_locks.locks.{lock_name}")
        require_non_empty_string(lock, "reason", f"runtime_locks.locks.{lock_name}")


def validate_runtime_state(data: Mapping[str, Any]) -> None:
    """Validate runtime state example template only.

    This validator explicitly rejects active candidates and report ids because
    Phase 1 examples are not mutable runtime truth.
    """

    root = require_mapping(data, "runtime_state")
    require_exact_keys(root, RUNTIME_STATE_KEYS, "runtime_state")
    require_literal(root, "schema_version", 1, "runtime_state")
    require_literal(root, "template", True, "runtime_state")
    require_literal(root, "phase", "phase_1_skeleton", "runtime_state")
    require_literal(root, "symbol", "ETHUSDC", "runtime_state")
    require_literal(root, "quote_asset", "USDC", "runtime_state")
    require_literal(root, "market_type", "binance_spot_long_only", "runtime_state")
    require_literal(root, "status", "not_running", "runtime_state")
    require_literal(root, "live_status", "locked", "runtime_state")
    require_literal(root, "paper_status", "locked", "runtime_state")
    require_literal(root, "testtrade_status", "locked", "runtime_state")
    require_none(root, "active_candidate", "runtime_state")
    require_none(root, "last_report_id", "runtime_state")
    require_non_empty_string(root, "notes", "runtime_state")


def validate_progress_state(data: Mapping[str, Any]) -> None:
    """Validate progress state example template only."""

    root = require_mapping(data, "progress_state")
    require_exact_keys(root, PROGRESS_STATE_KEYS, "progress_state")
    require_literal(root, "schema_version", 1, "progress_state")
    require_literal(root, "template", True, "progress_state")
    require_literal(root, "project_phase", "phase_1_skeleton", "progress_state")
    require_none(root, "current_ticket", "progress_state")
    require_empty_list(root, "completed_steps", "progress_state")
    require_empty_list(root, "blocked_steps", "progress_state")
    require_non_empty_string(root, "next_smallest_step", "progress_state")
    require_non_empty_string(root, "notes", "progress_state")
