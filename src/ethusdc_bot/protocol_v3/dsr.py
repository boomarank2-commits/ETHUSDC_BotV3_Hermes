"""Exact Deflated Sharpe Ratio evidence for Protocol-v3 Task 18."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Any, Final

from .legacy_multiplicity import (
    CONTRACT_VERSION as LEGACY_MULTIPLICITY_CONTRACT_VERSION,
    LegacyMultiplicityError,
    adjusted_n_raw,
    load_legacy_multiplicity_policy,
    validate_ledger_status_for_legacy_floor,
)
from .pbo import (
    CASH_ID,
    COMPLETE as PBO_COMPLETE,
    PBOEvidence,
    validate_pbo_evidence,
    validate_pbo_identity_payload,
)
from .trial_ledger import TrialLedgerSnapshot, read_trial_ledger

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_dsr_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_dsr_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_exact_deflated_sharpe_with_legacy_floor_v2"
EVIDENCE_SCHEMA_VERSION: Final = "protocol_v3_dsr_evidence_v2"
IDENTITY_SCHEMA_VERSION: Final = "protocol_v3_dsr_identity_v2"
COMPLETE: Final = "COMPLETE"
INSUFFICIENT_EVIDENCE: Final = "INSUFFICIENT_EVIDENCE"
INSUFFICIENT_TRIAL_HISTORY: Final = "INSUFFICIENT_TRIAL_HISTORY"
NOT_APPLICABLE_NO_TRADE: Final = "NOT_APPLICABLE_NO_TRADE"
REQUIRED_DAYS: Final = 360
LAG_COUNT: Final = 5
MIN_DSR: Final = 0.95
EULER_GAMMA: Final = 0.5772156649015329

_SAFETY = {"api_keys": "forbidden", "live": "locked", "orders": "locked", "paper": "locked", "testtrade": "locked", "trading_api": "forbidden"}
_CANONICAL_CONTRACT = {
    "schema_version": CONTRACT_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION, "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
    "identity_schema_version": IDENTITY_SCHEMA_VERSION,
    "batch_contract_version": "protocol_v3_shared_statistics_batch_dsr_v1",
    "batch_evidence_schema_version": "protocol_v3_dsr_batch_evidence_v1",
    "batch_identity_schema_version": "protocol_v3_dsr_batch_identity_v1",
    "batch_policy": {
        "shared_trial_inventory_computed_once": True,
        "shared_correlation_matrix_computed_once": True,
        "scalar_dsr_formula_unchanged": True,
        "profile_results_recomputed_during_validation": True,
        "pbo_identity_embedded_once": True,
    },
    "series_policy": {"days": 360, "sample_std_ddof": 1, "annualization": False, "lag_formula": "floor(4*(n/100)^(2/9))", "lag_count_at_360": 5, "autocorrelation": "centered_lag_product_over_full_centered_sum_squares", "vif_floor": 1.0},
    "moment_policy": {"minimum_n": 4, "skew": "adjusted_fisher_pearson_G1", "kurtosis": "unbiased_fisher_excess_G2_plus_3_pearson"},
    "trial_policy": {
        "n_raw_source": "legacy_multiplicity_floor_plus_complete_native_independent_trials",
        "n_eff_trials_is_diagnostic_only": True,
        "legacy_multiplicity_contract": LEGACY_MULTIPLICITY_CONTRACT_VERSION,
        "legacy_daily_series_used": False,
        "sigma_sr": "sample_std_ddof_1_of_complete_same_grid_native_independent_trial_sharpes",
        "correlation": "complete_same_grid_native_independent_daily_series_only",
        "common_complete_daily_grid_required": True,
        "minimum_complete_native_trials": 2,
    },
    "gate_policy": {"minimum_development_dsr": 0.95, "no_trade_state": NOT_APPLICABLE_NO_TRADE, "incomplete_history_state": INSUFFICIENT_TRIAL_HISTORY, "numeric_replacement_forbidden": True},
    "deferred_scope": {"monthly_gate_task": 26, "outer_bootstrap_task": 27}, "safety": _SAFETY,
}


class DSRError(ValueError):
    """Raised for malformed or contradictory DSR evidence."""


class _InsufficientStatistics(RuntimeError):
    """Internal typed path for valid inputs that cannot produce numeric DSR."""


@dataclass(frozen=True)
class DSREvidence:
    canonical_json: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self.canonical_json)
        payload["evidence_sha256"] = self.evidence_sha256
        return payload

    @property
    def identity_payload(self) -> dict[str, Any]:
        return build_dsr_identity_payload(self)


def load_dsr_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        payload = _strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DSRError("DSR contract is missing or invalid") from exc
    if payload != _CANONICAL_CONTRACT:
        raise DSRError("Protocol v3 DSR contract is not canonical")
    return payload


def calculate_dsr(
    *,
    pbo_evidence: PBOEvidence | Mapping[str, Any],
    selected_profile_id: str,
    trial_ledger: TrialLedgerSnapshot,
) -> DSREvidence:
    pbo = validate_pbo_evidence(pbo_evidence)
    profile_id = _text(selected_profile_id, "selected_profile_id")
    ledger = _current_ledger(trial_ledger)
    basis = _dsr_basis(pbo, profile_id, ledger)
    return validate_dsr_evidence({**basis, "evidence_sha256": _digest(basis)})


def calculate_dsr_batch(
    *,
    pbo_evidence: PBOEvidence | Mapping[str, Any],
    selected_profile_ids: Sequence[str],
    trial_ledger: TrialLedgerSnapshot,
) -> dict[str, DSREvidence]:
    """Calculate multiple DSR rows with one shared trial-statistics pass."""

    pbo = validate_pbo_evidence(pbo_evidence)
    profile_ids = [
        _text(value, "selected_profile_id") for value in selected_profile_ids
    ]
    if not profile_ids or len(profile_ids) != len(set(profile_ids)):
        raise DSRError("selected_profile_ids must be non-empty and unique")
    ledger = _current_ledger(trial_ledger)
    prepared = None
    try:
        prepared = _prepare_dsr_inputs(pbo, ledger)
    except (LegacyMultiplicityError, _InsufficientStatistics):
        pass
    result = {}
    for profile_id in profile_ids:
        basis = _dsr_basis(
            pbo,
            profile_id,
            ledger,
            prepared=prepared,
        )
        result[profile_id] = validate_dsr_evidence(
            {**basis, "evidence_sha256": _digest(basis)}
        )
    return result


def validate_dsr_for_ledger(
    evidence: DSREvidence | Mapping[str, Any],
    trial_ledger: TrialLedgerSnapshot,
) -> DSREvidence:
    """Revalidate evidence and prove that its permanent-ledger head is still current."""

    validated = validate_dsr_evidence(evidence)
    current = _current_ledger(trial_ledger)
    if validated.to_dict()["ledger_head_sha256"] != current.status.head_sha256:
        raise DSRError("DSR evidence ledger head is stale")
    return validated


def _dsr_basis(
    pbo: PBOEvidence,
    profile_id: str,
    ledger: TrialLedgerSnapshot,
    *,
    prepared: tuple[Any, list[dict[str, Any]], int, int, dict[str, Any]]
    | None = None,
) -> dict[str, Any]:
    pbo_payload = pbo.to_dict()
    matrix = pbo_payload["matrix_identity"]["matrix"]
    profiles = [profile for cycle in matrix["cycles"] for profile in cycle["profiles"]]
    policy = (
        prepared[0]
        if prepared is not None
        else load_legacy_multiplicity_policy(
            Path(__file__).resolve().parents[3]
        )
    )
    common = {
        "schema_version": EVIDENCE_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION, "pbo_identity": pbo.identity_payload,
        "selected_profile_id": profile_id, "matrix_sha256": matrix["matrix_sha256"],
        "ledger_head_sha256": ledger.status.head_sha256, "day_grid": matrix["day_grid"],
        "day_grid_sha256": matrix["day_grid_sha256"],
        "legacy_multiplicity_policy": policy.to_dict(),
        "legacy_multiplicity_floor": policy.legacy_multiplicity_floor,
        "legacy_daily_series_used": False,
        "safety": _SAFETY,
    }
    if profile_id == CASH_ID:
        return {**common, **_empty_result(NOT_APPLICABLE_NO_TRADE, "cash_no_trade_has_no_dsr")}
    selected = [row for row in profiles if row["profile_id"] == profile_id]
    if len(selected) != 1:
        raise DSRError("selected profile is absent or duplicated in Task-16 matrix")
    common["selected_candidate_id"] = selected[0]["candidate_id"]
    if pbo_payload["state"] != PBO_COMPLETE:
        return {**common, **_empty_result(INSUFFICIENT_EVIDENCE, "PBO_evidence_is_incomplete")}
    if matrix["trial_ledger_head_sha256"] != ledger.status.head_sha256:
        raise DSRError("DSR ledger head differs from Task-16 matrix ledger head")
    try:
        if prepared is None:
            (
                _,
                trial_rows,
                complete_native_trial_count,
                n_raw,
                shared_statistics,
            ) = _prepare_dsr_inputs(pbo, ledger)
        else:
            (
                _,
                trial_rows,
                complete_native_trial_count,
                n_raw,
                shared_statistics,
            ) = prepared
    except LegacyMultiplicityError:
        return {
            **common,
            **_empty_result(
                INSUFFICIENT_TRIAL_HISTORY,
                "legacy_multiplicity_floor_or_native_history_is_incomplete",
            ),
        }
    except _InsufficientStatistics as exc:
        return {**common, **_empty_result(INSUFFICIENT_EVIDENCE, str(exc))}
    if complete_native_trial_count != ledger.status.native_trial_count:
        raise DSRError("native ledger count differs from its complete trial inventory")
    if len(trial_rows) < 2:
        return {**common, **_empty_result(INSUFFICIENT_EVIDENCE, "fewer_than_two_complete_trials")}
    selected_values = [float(row["net_usdc"]) for row in selected[0]["daily_net_mtm_usdc"]]
    selected_trial = next((row for row in trial_rows if row["trial_id"] == selected[0]["trial_id"]), None)
    if selected_trial is None or selected_trial["daily_series_sha256"] != selected[0]["daily_series_sha256"]:
        raise DSRError("selected DSR series is not digest-identical to matrix and ledger")
    try:
        result = _statistics(
            selected_values,
            trial_rows,
            legacy_multiplicity_policy=policy.to_dict(),
            n_raw=n_raw,
            complete_native_trial_count=complete_native_trial_count,
            shared_statistics=shared_statistics,
        )
    except _InsufficientStatistics as exc:
        return {**common, **_empty_result(INSUFFICIENT_EVIDENCE, str(exc))}
    return {**common, "state": COMPLETE, "reason": "complete_deflated_sharpe", **result}


def _empty_result(state: str, reason: str) -> dict[str, Any]:
    return {
        "state": state, "reason": reason, "n": None, "lag_count": None,
        "daily_mean": None, "sample_std": None, "sharpe": None,
        "autocorrelations": [], "vif": None, "n_eff": None, "skew": None,
        "pearson_kurtosis": None, "n_raw": None,
        "complete_native_trial_count": None,
        "same_grid_native_trial_count": None,
        "trial_rows": [],
        "trial_set_sha256": None, "sigma_sr": None, "correlation_matrix": [],
        "correlation_sha256": None, "n_eff_trials": None, "sr0": None,
        "denominator": None, "z": None, "development_dsr": None,
        "passed_minimum_dsr": False,
    }


def _statistics(
    values: list[float],
    trial_rows: list[dict[str, Any]],
    *,
    legacy_multiplicity_policy: Mapping[str, Any],
    n_raw: int,
    complete_native_trial_count: int,
    shared_statistics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    n = len(values)
    if n != REQUIRED_DAYS or int(math.floor(4 * (n / 100) ** (2 / 9))) != LAG_COUNT:
        raise DSRError("DSR requires exactly 360 values and K=5")
    mean, std = _mean_std(values)
    if std <= 0.0:
        raise _InsufficientStatistics("selected_series_zero_variance")
    sharpe = mean / std
    centered = [value - mean for value in values]
    denominator_ac = math.fsum(value * value for value in centered)
    autocorrelations = [math.fsum(centered[index] * centered[index - lag] for index in range(lag, n)) / denominator_ac for lag in range(1, LAG_COUNT + 1)]
    vif = max(1.0, 1.0 + 2.0 * math.fsum((1.0 - lag / (LAG_COUNT + 1)) * autocorrelations[lag - 1] for lag in range(1, LAG_COUNT + 1)))
    n_eff = n / vif
    skew, kurtosis = _moments(centered, std)
    shared = (
        dict(shared_statistics)
        if shared_statistics is not None
        else _shared_statistics(
            trial_rows,
            legacy_multiplicity_policy=legacy_multiplicity_policy,
            n_raw=n_raw,
            complete_native_trial_count=complete_native_trial_count,
        )
    )
    sigma_sr = shared["sigma_sr"]
    correlations = shared["correlation_matrix"]
    n_eff_trials = shared["n_eff_trials"]
    same_grid_native_count = shared["same_grid_native_trial_count"]
    sr0 = shared["sr0"]
    normal = NormalDist()
    denominator = 1.0 - skew * sharpe + ((kurtosis - 1.0) / 4.0) * sharpe * sharpe
    if denominator <= 0.0 or not math.isfinite(denominator) or n_eff <= 1.0:
        raise _InsufficientStatistics("invalid_dsr_denominator_or_effective_sample_size")
    z = (sharpe - sr0) * math.sqrt(n_eff - 1.0) / math.sqrt(denominator)
    dsr = normal.cdf(z)
    return {
        "n": n, "lag_count": LAG_COUNT, "daily_mean": mean, "sample_std": std,
        "sharpe": sharpe, "autocorrelations": autocorrelations, "vif": vif,
        "n_eff": n_eff, "skew": skew, "pearson_kurtosis": kurtosis,
        "n_raw": n_raw,
        "complete_native_trial_count": complete_native_trial_count,
        "same_grid_native_trial_count": same_grid_native_count,
        "trial_rows": trial_rows,
        "trial_set_sha256": shared["trial_set_sha256"],
        "sigma_sr": sigma_sr,
        "correlation_matrix": correlations,
        "correlation_sha256": shared["correlation_sha256"],
        "n_eff_trials": n_eff_trials, "sr0": sr0, "denominator": denominator,
        "z": z, "development_dsr": dsr, "passed_minimum_dsr": dsr >= MIN_DSR,
    }


def _prepare_dsr_inputs(
    pbo: PBOEvidence,
    ledger: TrialLedgerSnapshot,
) -> tuple[Any, list[dict[str, Any]], int, int, dict[str, Any]]:
    matrix = pbo.to_dict()["matrix_identity"]["matrix"]
    policy = load_legacy_multiplicity_policy(
        Path(__file__).resolve().parents[3]
    )
    validate_ledger_status_for_legacy_floor(ledger.status.to_dict(), policy)
    trial_rows, complete_native_trial_count = _native_trial_inventory(
        ledger,
        matrix["day_grid"],
    )
    n_raw = adjusted_n_raw(
        policy,
        complete_native_trial_count=complete_native_trial_count,
    )
    if complete_native_trial_count != ledger.status.native_trial_count:
        raise DSRError(
            "native ledger count differs from its complete trial inventory"
        )
    if len(trial_rows) < 2:
        raise _InsufficientStatistics("fewer_than_two_complete_trials")
    shared = _shared_statistics(
        trial_rows,
        legacy_multiplicity_policy=policy.to_dict(),
        n_raw=n_raw,
        complete_native_trial_count=complete_native_trial_count,
    )
    return policy, trial_rows, complete_native_trial_count, n_raw, shared


def _shared_statistics(
    trial_rows: list[dict[str, Any]],
    *,
    legacy_multiplicity_policy: Mapping[str, Any],
    n_raw: int,
    complete_native_trial_count: int,
) -> dict[str, Any]:
    sharpes = [float(row["sharpe"]) for row in trial_rows]
    _, sigma_sr = _mean_std(sharpes)
    if sigma_sr <= 0.0:
        raise _InsufficientStatistics("trial_sharpe_set_zero_variance")
    correlations = _correlation_matrix(
        [
            [
                float(item["net_usdc"])
                for item in row["daily_net_mtm_usdc"]
            ]
            for row in trial_rows
        ]
    )
    trace = float(len(correlations))
    trace_square = math.fsum(
        value * value for row in correlations for value in row
    )
    n_eff_trials = trace * trace / trace_square
    if (
        n_raw
        != int(
            legacy_multiplicity_policy["legacy_multiplicity_floor"]
            + complete_native_trial_count
        )
    ):
        raise DSRError(
            "DSR n_raw differs from legacy floor plus native trials"
        )
    normal = NormalDist()
    sr0 = sigma_sr * (
        (1.0 - EULER_GAMMA) * normal.inv_cdf(1.0 - 1.0 / n_raw)
        + EULER_GAMMA
        * normal.inv_cdf(1.0 - 1.0 / (n_raw * math.e))
    )
    trial_set_basis = {
        "legacy_multiplicity_policy": dict(legacy_multiplicity_policy),
        "complete_native_trial_count": complete_native_trial_count,
        "native_trials": [
            {
                "trial_id": row["trial_id"],
                "daily_series_sha256": row["daily_series_sha256"],
                "sharpe": row["sharpe"],
            }
            for row in trial_rows
        ],
    }
    return {
        "sigma_sr": sigma_sr,
        "correlation_matrix": correlations,
        "correlation_sha256": _digest(correlations),
        "n_eff_trials": n_eff_trials,
        "same_grid_native_trial_count": len(trial_rows),
        "sr0": sr0,
        "trial_set_sha256": _digest(trial_set_basis),
    }


def _native_trial_inventory(
    ledger: TrialLedgerSnapshot, day_grid: list[str]
) -> tuple[list[dict[str, Any]], int]:
    rows = []
    complete_native_trial_count = 0
    for trial_id in sorted(ledger.trials):
        trial = ledger.trials[trial_id]
        if trial["identity_basis"]["source_kind"] == "historical_import":
            continue
        daily = trial.get("daily_net_mtm_usdc")
        if daily is None and trial_id in ledger.attached_daily_series:
            daily = list(ledger.attached_daily_series[trial_id])
        if not isinstance(daily, list) or len(daily) != REQUIRED_DAYS:
            raise _InsufficientStatistics(
                "native_trial_missing_complete_360_day_grid"
            )
        observed_grid = [row.get("day") for row in daily]
        _validate_complete_daily_grid(observed_grid)
        values = [_finite(row.get("net_usdc"), "trial net_usdc") for row in daily]
        mean, std = _mean_std(values)
        if std <= 0.0:
            raise _InsufficientStatistics("trial_series_zero_variance")
        normalized = [
            {"day": day, "net_usdc": value}
            for day, value in zip(observed_grid, values, strict=True)
        ]
        complete_native_trial_count += 1
        if observed_grid != day_grid:
            continue
        rows.append({"trial_id": trial_id, "daily_net_mtm_usdc": normalized, "daily_series_sha256": _digest(normalized), "sharpe": mean / std})
    return rows, complete_native_trial_count


def _validate_complete_daily_grid(day_grid: Sequence[Any]) -> None:
    try:
        parsed = [date.fromisoformat(day) for day in day_grid]
    except (TypeError, ValueError) as exc:
        raise _InsufficientStatistics(
            "native_trial_daily_grid_has_invalid_utc_day"
        ) from exc
    if len(set(parsed)) != REQUIRED_DAYS:
        raise _InsufficientStatistics("native_trial_daily_grid_is_duplicated")
    expected = [
        parsed[0] + timedelta(days=offset) for offset in range(REQUIRED_DAYS)
    ]
    if parsed != expected:
        raise _InsufficientStatistics(
            "native_trial_daily_grid_is_not_contiguous"
        )


def _mean_std(values: Sequence[float]) -> tuple[float, float]:
    if len(values) < 2:
        raise DSRError("sample standard deviation requires at least two values")
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(variance)


def _moments(centered: list[float], sample_std: float) -> tuple[float, float]:
    n = len(centered)
    if n < 4:
        raise DSRError("adjusted skew and kurtosis require at least four values")
    m2 = math.fsum(value ** 2 for value in centered) / n
    m3 = math.fsum(value ** 3 for value in centered) / n
    m4 = math.fsum(value ** 4 for value in centered) / n
    if m2 <= 0.0 or sample_std <= 0.0:
        raise DSRError("moments require positive variance")
    g1 = m3 / (m2 ** 1.5)
    skew = math.sqrt(n * (n - 1)) / (n - 2) * g1
    excess = m4 / (m2 * m2) - 3.0
    unbiased_excess = (n - 1) / ((n - 2) * (n - 3)) * ((n + 1) * excess + 6.0)
    return skew, unbiased_excess + 3.0


def _correlation_matrix(series: list[list[float]]) -> list[list[float]]:
    centered = []
    norms = []
    for values in series:
        mean = math.fsum(values) / len(values)
        row = [value - mean for value in values]
        norm = math.sqrt(math.fsum(value * value for value in row))
        if norm <= 0.0:
            raise _InsufficientStatistics("correlation_trial_zero_variance")
        centered.append(row)
        norms.append(norm)
    return [[math.fsum(a * b for a, b in zip(centered[i], centered[j], strict=True)) / (norms[i] * norms[j]) for j in range(len(series))] for i in range(len(series))]


def validate_dsr_evidence(value: DSREvidence | Mapping[str, Any]) -> DSREvidence:
    root = value.to_dict() if isinstance(value, DSREvidence) else dict(_mapping(value, "dsr_evidence"))
    required = {"schema_version", "protocol_version", "contract_version", "pbo_identity", "selected_profile_id", "matrix_sha256", "ledger_head_sha256", "day_grid", "day_grid_sha256", "legacy_multiplicity_policy", "legacy_multiplicity_floor", "legacy_daily_series_used", "safety", "state", "reason", "n", "lag_count", "daily_mean", "sample_std", "sharpe", "autocorrelations", "vif", "n_eff", "skew", "pearson_kurtosis", "n_raw", "complete_native_trial_count", "same_grid_native_trial_count", "trial_rows", "trial_set_sha256", "sigma_sr", "correlation_matrix", "correlation_sha256", "n_eff_trials", "sr0", "denominator", "z", "development_dsr", "passed_minimum_dsr", "evidence_sha256"}
    if root.get("selected_profile_id") != CASH_ID:
        required.add("selected_candidate_id")
    if set(root) != required or root["schema_version"] != EVIDENCE_SCHEMA_VERSION or root["protocol_version"] != PROTOCOL_VERSION or root["contract_version"] != CONTRACT_VERSION:
        raise DSRError("DSR evidence fields or versions are invalid")
    pbo_identity = validate_pbo_identity_payload(_mapping(root["pbo_identity"], "pbo_identity"))
    pbo = validate_pbo_evidence(pbo_identity["evidence"])
    if root["pbo_identity"] != pbo_identity:
        raise DSRError("DSR PBO identity is not canonical")
    matrix = pbo.to_dict()["matrix_identity"]["matrix"]
    if root["matrix_sha256"] != matrix["matrix_sha256"] or root["day_grid"] != matrix["day_grid"] or root["day_grid_sha256"] != matrix["day_grid_sha256"]:
        raise DSRError("DSR matrix or day-grid binding mismatch")
    _sha(root["ledger_head_sha256"], "ledger_head_sha256")
    profile_ids = [profile["profile_id"] for cycle in matrix["cycles"] for profile in cycle["profiles"]]
    if root["selected_profile_id"] != CASH_ID and root["selected_profile_id"] not in profile_ids:
        raise DSRError("selected DSR profile is absent from matrix")
    current_policy = load_legacy_multiplicity_policy(
        Path(__file__).resolve().parents[3]
    )
    if (
        root["legacy_multiplicity_policy"] != current_policy.to_dict()
        or root["legacy_multiplicity_floor"]
        != current_policy.legacy_multiplicity_floor
        or root["legacy_daily_series_used"] is not False
    ):
        raise DSRError("DSR legacy multiplicity policy is stale or unsafe")
    if root["state"] == COMPLETE:
        try:
            recomputed = _statistics(
                [float(item["net_usdc"]) for item in next(profile for cycle in matrix["cycles"] for profile in cycle["profiles"] if profile["profile_id"] == root["selected_profile_id"])["daily_net_mtm_usdc"]],
                root["trial_rows"],
                legacy_multiplicity_policy=root["legacy_multiplicity_policy"],
                n_raw=root["n_raw"],
                complete_native_trial_count=root[
                    "complete_native_trial_count"
                ],
            )
        except (_InsufficientStatistics, StopIteration, KeyError, TypeError, ValueError) as exc:
            raise DSRError("complete DSR evidence cannot be exactly recomputed") from exc
        for key, expected in recomputed.items():
            if root[key] != expected:
                raise DSRError("DSR evidence differs from exact recomputation")
    else:
        allowed = {
            NOT_APPLICABLE_NO_TRADE: "cash_no_trade_has_no_dsr",
            INSUFFICIENT_TRIAL_HISTORY: "permanent_trial_history_is_incomplete",
            INSUFFICIENT_EVIDENCE: root["reason"],
        }
        if root["state"] == INSUFFICIENT_TRIAL_HISTORY:
            allowed[INSUFFICIENT_TRIAL_HISTORY] = (
                "legacy_multiplicity_floor_or_native_history_is_incomplete"
            )
        if root["state"] not in allowed or root["reason"] != allowed[root["state"]]:
            raise DSRError("non-complete DSR state or reason is invalid")
        if root["state"] == NOT_APPLICABLE_NO_TRADE and root["selected_profile_id"] != CASH_ID:
            raise DSRError("only cash may use NOT_APPLICABLE_NO_TRADE")
        expected_empty = _empty_result(root["state"], root["reason"])
        for key, expected in expected_empty.items():
            if root[key] != expected:
                raise DSRError("non-complete DSR evidence contains numeric replacement")
    if root["safety"] != _SAFETY:
        raise DSRError("DSR safety locks are invalid")
    observed = _sha(root["evidence_sha256"], "evidence_sha256")
    basis = dict(root)
    basis.pop("evidence_sha256")
    if observed != _digest(basis):
        raise DSRError("DSR evidence digest mismatch")
    return DSREvidence(_canonical(basis), observed)


def build_dsr_identity_payload(evidence: DSREvidence | Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_dsr_evidence(evidence)
    basis = {"identity_schema_version": IDENTITY_SCHEMA_VERSION, "evidence": validated.to_dict(), "evidence_sha256": validated.evidence_sha256}
    return {**basis, "identity_sha256": _digest(basis)}


def validate_dsr_identity_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(_mapping(value, "dsr_identity"))
    if set(root) != {"identity_schema_version", "evidence", "evidence_sha256", "identity_sha256"} or root["identity_schema_version"] != IDENTITY_SCHEMA_VERSION:
        raise DSRError("DSR identity fields or version are invalid")
    evidence = validate_dsr_evidence(root["evidence"])
    expected = build_dsr_identity_payload(evidence)
    if root != expected:
        raise DSRError("DSR identity is not canonical")
    return expected


def _current_ledger(value: TrialLedgerSnapshot) -> TrialLedgerSnapshot:
    if not isinstance(value, TrialLedgerSnapshot):
        raise DSRError("trial_ledger must be a verified snapshot")
    current = read_trial_ledger(value.root)
    if current.status.head_sha256 != value.status.head_sha256:
        raise DSRError("trial ledger advanced after DSR input was frozen")
    return current


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise DSRError(f"{path} must be finite")
    return float(value)


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DSRError(f"{path} must be non-empty text")
    return value.strip()


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DSRError(f"{path} must be an object")
    return value


def _sha(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise DSRError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _canonical(value: Any) -> str: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
def _digest(value: Any) -> str: return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _strict_loads(text: str) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise DSRError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=hook, parse_constant=lambda value: (_ for _ in ()).throw(DSRError(f"non-finite JSON constant: {value}")))


__all__ = ["COMPLETE", "CONTRACT_PATH", "CONTRACT_SCHEMA_VERSION", "CONTRACT_VERSION", "DSRError", "DSREvidence", "EVIDENCE_SCHEMA_VERSION", "IDENTITY_SCHEMA_VERSION", "INSUFFICIENT_EVIDENCE", "INSUFFICIENT_TRIAL_HISTORY", "LAG_COUNT", "MIN_DSR", "NOT_APPLICABLE_NO_TRADE", "build_dsr_identity_payload", "calculate_dsr", "calculate_dsr_batch", "load_dsr_contract", "validate_dsr_evidence", "validate_dsr_for_ledger", "validate_dsr_identity_payload"]
