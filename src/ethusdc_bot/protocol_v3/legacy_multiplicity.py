"""Conservative multiplicity floor for irrecoverable Protocol-v2 evaluations.

The legacy rows affect only the multiple-testing penalty.  They never become
trial identities and never supply returns, PnL, rankings, gates, or fit data.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from .trial_ledger import validate_historical_lower_bound_manifest

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_legacy_multiplicity_contract.json")
SOURCE_MANIFEST_PATH: Final = Path(
    "configs/protocol_v3_historical_trial_lower_bound.json"
)
SCHEMA_VERSION: Final = "protocol_v3_legacy_multiplicity_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_conservative_legacy_multiplicity_floor_v1"
LEGACY_MULTIPLICITY_FLOOR: Final = 180
MINIMUM_COMPLETE_NATIVE_TRIALS: Final = 2
_POLICY: Final = {
    "legacy_observed_rows_treated_as_independent_for_multiplicity_only": True,
    "legacy_identity_claimed": False,
    "legacy_daily_series_used": False,
    "legacy_pnl_used": False,
    "legacy_rankings_or_gates_used": False,
    "n_raw_formula": (
        "legacy_multiplicity_floor+complete_native_independent_trials"
    ),
    "sigma_sr_source": (
        "complete_same_grid_native_independent_trial_sharpes_only"
    ),
    "correlation_source": (
        "complete_same_grid_native_independent_daily_series_only"
    ),
    "minimum_complete_native_trials": MINIMUM_COMPLETE_NATIVE_TRIALS,
    "cache_reuse_counts_as_trial": False,
    "historical_lower_bound_may_remain_true": True,
    "floor_alone_may_release_candidate": False,
}
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class LegacyMultiplicityError(ValueError):
    """Raised when the conservative legacy floor cannot be proven exactly."""


@dataclass(frozen=True)
class LegacyMultiplicityPolicy:
    legacy_multiplicity_floor: int
    source_manifest_sha256: str
    contract_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "legacy_multiplicity_floor": self.legacy_multiplicity_floor,
            "source_manifest_sha256": self.source_manifest_sha256,
            "contract_sha256": self.contract_sha256,
            "legacy_identity_claimed": False,
            "legacy_daily_series_used": False,
            "legacy_pnl_used": False,
            "legacy_rankings_or_gates_used": False,
            "minimum_complete_native_trials": MINIMUM_COMPLETE_NATIVE_TRIALS,
        }


def load_legacy_multiplicity_policy(
    repo_root: str | Path,
) -> LegacyMultiplicityPolicy:
    root = Path(repo_root).resolve()
    contract = _read_json(root / CONTRACT_PATH, "legacy multiplicity contract")
    source = _read_json(root / SOURCE_MANIFEST_PATH, "historical lower-bound manifest")
    return validate_legacy_multiplicity_policy(contract, source)


def validate_legacy_multiplicity_policy(
    contract: Mapping[str, Any],
    source_manifest: Mapping[str, Any],
) -> LegacyMultiplicityPolicy:
    if not isinstance(contract, Mapping) or not isinstance(source_manifest, Mapping):
        raise LegacyMultiplicityError("legacy multiplicity inputs must be objects")
    root = dict(contract)
    expected = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "source_manifest": SOURCE_MANIFEST_PATH.as_posix(),
        "legacy_multiplicity_floor": LEGACY_MULTIPLICITY_FLOOR,
        "policy": _POLICY,
        "safety": _SAFETY,
    }
    if root != expected:
        raise LegacyMultiplicityError("legacy multiplicity contract is not canonical")
    try:
        validate_historical_lower_bound_manifest(source_manifest)
    except Exception as exc:
        raise LegacyMultiplicityError(
            "historical lower-bound manifest is invalid"
        ) from exc
    source = dict(source_manifest)
    observed = source["known_observed_evaluation_rows"]
    source_sum = sum(row["observed_evaluation_rows"] for row in source["sources"])
    if observed != LEGACY_MULTIPLICITY_FLOOR or source_sum != observed:
        raise LegacyMultiplicityError(
            "legacy floor differs from the complete observed-row inventory"
        )
    if (
        source["identity_inventory_complete"] is not False
        or source["daily_series_complete"] is not False
        or source["independent_trial_count_resolved"] != 0
    ):
        raise LegacyMultiplicityError("legacy uncertainty is understated")
    return LegacyMultiplicityPolicy(
        legacy_multiplicity_floor=LEGACY_MULTIPLICITY_FLOOR,
        source_manifest_sha256=_digest(source),
        contract_sha256=_digest(root),
    )


def validate_ledger_status_for_legacy_floor(
    status: Mapping[str, Any], policy: LegacyMultiplicityPolicy
) -> None:
    if not isinstance(status, Mapping):
        raise LegacyMultiplicityError("trial-ledger status must be an object")
    if (
        status.get("canonical_historical_import_present") is not True
        or not isinstance(
            status.get("historical_trial_count_is_lower_bound"), bool
        )
        or status.get("known_observed_historical_evaluation_rows")
        != policy.legacy_multiplicity_floor
        or status.get("historical_resolved_trial_count") != 0
    ):
        raise LegacyMultiplicityError(
            "trial ledger does not match the conservative legacy floor"
        )


def adjusted_n_raw(
    policy: LegacyMultiplicityPolicy, *, complete_native_trial_count: int
) -> int:
    if (
        isinstance(complete_native_trial_count, bool)
        or not isinstance(complete_native_trial_count, int)
        or complete_native_trial_count < MINIMUM_COMPLETE_NATIVE_TRIALS
    ):
        raise LegacyMultiplicityError("insufficient complete native trials")
    return policy.legacy_multiplicity_floor + complete_native_trial_count


def _read_json(path: Path, name: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LegacyMultiplicityError(f"{name} is unreadable") from exc
    if not isinstance(value, dict):
        raise LegacyMultiplicityError(f"{name} must be an object")
    return value


def _digest(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_VERSION",
    "LEGACY_MULTIPLICITY_FLOOR",
    "LegacyMultiplicityError",
    "LegacyMultiplicityPolicy",
    "MINIMUM_COMPLETE_NATIVE_TRIALS",
    "adjusted_n_raw",
    "load_legacy_multiplicity_policy",
    "validate_ledger_status_for_legacy_floor",
    "validate_legacy_multiplicity_policy",
]
