"""Frozen production inputs shared by Protocol-v3 preflight and execution."""
from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any, Final

from .data_snapshot import build_warmup_plan
from .runtime_state import HorizonPolicy

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_production_runtime_inputs.json")
SCHEMA_VERSION: Final = "protocol_v3_production_runtime_inputs_v1"
CONTRACT_VERSION: Final = "protocol_v3_frozen_production_runtime_inputs_v1"
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_DERIVATION: Final = {
    "lookbacks": "exact_task5_three_market_audited_warmup_set",
    "max_label_horizon": (
        "conservative_upper_bound_equal_to_longest_forward_candidate_outcome"
    ),
    "max_holding_period": (
        "protocol_v3_specialists_contract.multiday_swing_trend_max_hold_minutes.upper"
    ),
    "pending_entry_latency": "task8_task9_shared_horizon_policy",
    "extension_creates_new_pipeline_generation": True,
}


class ProductionRuntimeError(ValueError):
    """Raised when production runtime inputs are missing or contradictory."""


def load_production_runtime_inputs(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve() / CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProductionRuntimeError("production runtime contract is unreadable") from exc
    return validate_production_runtime_inputs(value)


def validate_production_runtime_inputs(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionRuntimeError("production runtime contract must be an object")
    root = dict(value)
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "active_lookbacks",
        "horizon_policy",
        "derivation",
        "safety",
    }
    if set(root) != required:
        raise ProductionRuntimeError("production runtime contract fields are invalid")
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
    ):
        raise ProductionRuntimeError("production runtime contract versions are invalid")
    try:
        warmup = build_warmup_plan(root["active_lookbacks"])
    except Exception as exc:
        raise ProductionRuntimeError("active production lookbacks are invalid") from exc
    lookbacks = [row.to_dict() for row in warmup.active_lookbacks]
    if root["active_lookbacks"] != lookbacks:
        raise ProductionRuntimeError("active production lookbacks are not canonical")
    horizon = root["horizon_policy"]
    if not isinstance(horizon, Mapping) or set(horizon) != {
        "max_label_horizon_minutes",
        "max_holding_period_minutes",
        "pending_entry_latency_minutes",
        "execution_bar_minutes",
    }:
        raise ProductionRuntimeError("production horizon policy fields are invalid")
    try:
        policy = HorizonPolicy(
            max_label_horizon_minutes=horizon["max_label_horizon_minutes"],
            max_holding_period_minutes=horizon["max_holding_period_minutes"],
            pending_entry_latency_minutes=horizon["pending_entry_latency_minutes"],
            execution_bar_minutes=horizon["execution_bar_minutes"],
        )
    except (TypeError, ValueError) as exc:
        raise ProductionRuntimeError("production horizon policy is invalid") from exc
    expected_horizon = {
        "max_label_horizon_minutes": 10_080,
        "max_holding_period_minutes": 10_080,
        "pending_entry_latency_minutes": 2,
        "execution_bar_minutes": 1,
    }
    observed_horizon = policy.basis()
    observed_horizon.pop("contract_version")
    if observed_horizon != expected_horizon:
        raise ProductionRuntimeError("production horizon policy differs from frozen maxima")
    if dict(root["derivation"]) != _DERIVATION or root["safety"] != _SAFETY:
        raise ProductionRuntimeError("production runtime derivation or safety is invalid")
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "active_lookbacks": lookbacks,
        "horizon_policy": expected_horizon,
        "derivation": dict(_DERIVATION),
        "safety": dict(_SAFETY),
    }


def build_task33_runtime_inputs(
    repo_root: str | Path,
    *,
    production_outer_origin_adapter: bool,
) -> dict[str, Any]:
    """Return only the exact runtime fields accepted by the Task-33 preflight."""

    if type(production_outer_origin_adapter) is not bool:
        raise ProductionRuntimeError("adapter availability must be a boolean")
    root = load_production_runtime_inputs(repo_root)
    horizon = root["horizon_policy"]
    return {
        "active_lookbacks": root["active_lookbacks"],
        "horizon_policy": {
            "max_label_horizon_minutes": horizon["max_label_horizon_minutes"],
            "max_holding_period_minutes": horizon["max_holding_period_minutes"],
            "pending_order_latency_minutes": horizon["pending_entry_latency_minutes"],
        },
        "production_outer_origin_adapter": production_outer_origin_adapter,
    }


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_VERSION",
    "ProductionRuntimeError",
    "build_task33_runtime_inputs",
    "load_production_runtime_inputs",
    "validate_production_runtime_inputs",
]
