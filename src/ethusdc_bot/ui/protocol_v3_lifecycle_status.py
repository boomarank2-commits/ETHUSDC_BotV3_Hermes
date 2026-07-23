"""Typed display-only lifecycle states for the Protocol-v3 operator view.

These states describe where existing canonical backends are in their lifecycle.
They never unlock a runtime, claim freshness, calculate a result, or replace a
report/registration/checkpoint validator.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Final

PROCESS_OOS_STATES: Final = {
    "NOT_STARTED",
    "RUNNING",
    "PAUSED",
    "INTERRUPTED",
    "FAILED",
    "COMPLETED_DIAGNOSTIC",
}
CURRENT_REFIT_STATES: Final = {
    "NOT_STARTED",
    "RUNNING",
    "FAILED",
}
FINAL_WINDOW_STATES: Final = {
    "NOT_REGISTERED",
    "SEALED",
    "CONSUMED",
    "FINAL_EVALUATED",
}
CANONICAL_SHADOW_STATES: Final = {
    "NOT_ALLOWED",
    "ELIGIBLE_FROM_VALID_FINAL_REPORT",
    "RUNNING",
    "STOPPED",
}


class ProtocolV3LifecycleStatusError(ValueError):
    """Raised for a non-canonical display lifecycle state."""


@dataclass(frozen=True)
class ProtocolV3LifecycleStatus:
    canonical_json: str
    status_sha256: str

    def to_dict(self) -> dict[str, Any]:
        root = json.loads(self.canonical_json)
        root["status_sha256"] = self.status_sha256
        return root


def build_protocol_v3_lifecycle_status(
    *,
    process_oos: str = "NOT_STARTED",
    current_refit: str = "NOT_STARTED",
    final_window: str = "NOT_REGISTERED",
    canonical_shadow: str = "NOT_ALLOWED",
    reason_codes: Sequence[str] = (),
) -> ProtocolV3LifecycleStatus:
    """Build one immutable, display-only lifecycle snapshot."""

    process = _member(process_oos, PROCESS_OOS_STATES, "process_oos")
    refit = _member(current_refit, CURRENT_REFIT_STATES, "current_refit")
    final = _member(final_window, FINAL_WINDOW_STATES, "final_window")
    shadow = _member(
        canonical_shadow, CANONICAL_SHADOW_STATES, "canonical_shadow"
    )
    reasons = _strings(reason_codes)
    if final != "FINAL_EVALUATED" and shadow != "NOT_ALLOWED":
        raise ProtocolV3LifecycleStatusError(
            "canonical shadow cannot be eligible before a final evaluation state"
        )
    basis = {
        "schema_version": "protocol_v3_ui_lifecycle_status_v1",
        "process_oos": process,
        "current_refit": refit,
        "final_window": final,
        "canonical_shadow": shadow,
        "reason_codes": reasons,
        "display_only": True,
        "freshness_claimed": False,
        "runtime_permission_claimed": False,
    }
    return ProtocolV3LifecycleStatus(_canonical(basis), _digest(basis))


def validate_protocol_v3_lifecycle_status(
    value: ProtocolV3LifecycleStatus,
) -> ProtocolV3LifecycleStatus:
    if not isinstance(value, ProtocolV3LifecycleStatus):
        raise ProtocolV3LifecycleStatusError(
            "typed ProtocolV3LifecycleStatus is required"
        )
    root = value.to_dict()
    observed = root.pop("status_sha256")
    rebuilt = build_protocol_v3_lifecycle_status(
        process_oos=root.get("process_oos"),
        current_refit=root.get("current_refit"),
        final_window=root.get("final_window"),
        canonical_shadow=root.get("canonical_shadow"),
        reason_codes=root.get("reason_codes", ()),
    )
    if root != json.loads(rebuilt.canonical_json) or observed != rebuilt.status_sha256:
        raise ProtocolV3LifecycleStatusError("lifecycle status digest mismatch")
    return rebuilt


def _member(value: Any, allowed: set[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ProtocolV3LifecycleStatusError(f"{name} is invalid")
    return value


def _strings(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ProtocolV3LifecycleStatusError("reason_codes must be a sequence")
    rows: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ProtocolV3LifecycleStatusError(
                "reason_codes must contain non-empty strings"
            )
        rows.append(value.strip())
    return sorted(set(rows))


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


__all__ = [
    "CANONICAL_SHADOW_STATES",
    "CURRENT_REFIT_STATES",
    "FINAL_WINDOW_STATES",
    "PROCESS_OOS_STATES",
    "ProtocolV3LifecycleStatus",
    "ProtocolV3LifecycleStatusError",
    "build_protocol_v3_lifecycle_status",
    "validate_protocol_v3_lifecycle_status",
]
