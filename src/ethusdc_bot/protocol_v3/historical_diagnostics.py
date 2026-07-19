"""Task-27 hindsight capture diagnostics and deterministic stationary bootstrap."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import random
from typing import Any, Final

from .monthly_quality_gate import (
    MonthlyQualityGateReport,
    validate_monthly_quality_gate_report,
)
from .outer_mtm_ledger import OuterMtmLedger, validate_outer_mtm_ledger
from .outer_origins import OuterOriginProcess, validate_outer_origin_process
from .boundaries import MonthlyProcessBoundaryPlan

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_historical_diagnostics_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_historical_diagnostics_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_hindsight_capture_and_stationary_bootstrap_v1"
REPORT_SCHEMA_VERSION: Final = "protocol_v3_historical_diagnostics_v1"
REPLICATIONS: Final = 10_000
BLOCK_LENGTHS: Final = (5, 10, 20)
TARGET: Final = Decimal("3")
_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_BOOTSTRAP = {
    "days": 365,
    "replications": 10000,
    "expected_block_lengths": [5, 10, 20],
    "restart_probability": "1/L",
    "circular": True,
    "prng": "python_random_mt19937_v1",
    "seed": "uint64_first_16_hex_sha256_canonical_pre_bootstrap_manifest",
    "one_sided_lower_probability": 0.05,
    "order_statistic_one_based": 500,
    "interpolation": False,
    "strict_target_requires_all_three": True,
    "target_usdc_per_day": 3,
}
_BENCHMARK = {
    "all_candle_one_trade_is_optimistic_diagnostic": True,
    "candidate_matched_requires_positive_volume": True,
    "candidate_matched_requires_same_trade_limit_holding_long_only_one_lot_handoff_rounding_costs": True,
    "benchmark_results_never_feed_selection_or_monthly_gate": True,
    "manual_review_all_candle_ratio_min": 0.8,
    "manual_review_all_candle_ratio_max": 0.87,
    "manual_review_candidate_matched_ratio_min": 0.95,
}
_HISTORICAL = {
    "freshness": "NOT_FRESH",
    "diagnostic_only": True,
    "statistically_supported": False,
    "sealed_bootstrap_target_supported": False,
    "canonical_adoption_eligible": False,
}
_CANONICAL_CONTRACT = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "bootstrap_policy": _BOOTSTRAP,
    "benchmark_policy": _BENCHMARK,
    "historical_policy": _HISTORICAL,
    "safety": _SAFETY,
}
_MATCHED_CONSTRAINTS = (
    "positive_volume_only",
    "same_maximum_trade_count",
    "same_holding_period",
    "long_only",
    "one_lot",
    "same_handoff_state_machine",
    "same_rounding",
    "same_costs",
)


class HistoricalDiagnosticsError(ValueError):
    pass


@dataclass(frozen=True)
class HistoricalDiagnostics:
    canonical_json: str
    report_sha256: str

    def to_dict(self):
        value = json.loads(self.canonical_json)
        value["report_sha256"] = self.report_sha256
        return value


def load_historical_diagnostics_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HistoricalDiagnosticsError(
            "historical diagnostics contract is missing or invalid"
        ) from exc
    if value != _CANONICAL_CONTRACT:
        raise HistoricalDiagnosticsError(
            "historical diagnostics contract is not canonical"
        )
    return value


def build_historical_diagnostics(
    *,
    boundary_plan: MonthlyProcessBoundaryPlan,
    outer_process: OuterOriginProcess,
    baseline_ledger: OuterMtmLedger,
    monthly_quality_report: MonthlyQualityGateReport,
    data_identity_sha256: str,
    code_commit: str,
    pipeline_generation_id: str,
    benchmark_evidence: Mapping[str, Any],
) -> HistoricalDiagnostics:
    process = validate_outer_origin_process(outer_process, boundary_plan=boundary_plan)
    ledger = validate_outer_mtm_ledger(
        baseline_ledger, boundary_plan=boundary_plan, outer_process=process
    ).to_dict()
    gate = validate_monthly_quality_gate_report(monthly_quality_report).to_dict()
    if (
        gate["outer_process_sha256"] != process.process_sha256
        or gate["baseline_ledger_sha256"] != ledger["ledger_sha256"]
    ):
        raise HistoricalDiagnosticsError(
            "monthly gate and historical ledger identities differ"
        )
    values = [_dec(row["net_mtm_usdc"]) for row in ledger["daily_mtm"]]
    if len(values) != 365:
        raise HistoricalDiagnosticsError("bootstrap requires exactly 365 daily values")
    pnl_digest = _digest([_text(value) for value in values])
    manifest = {
        "schema_version": "protocol_v3_pre_bootstrap_input_manifest_v1",
        "daily_pnl_sha256": pnl_digest,
        "data_identity_sha256": _sha(data_identity_sha256),
        "code_commit": _sha(code_commit),
        "pipeline_generation_id": _nonempty(
            pipeline_generation_id, "pipeline_generation_id"
        ),
        "outer_process_sha256": process.process_sha256,
        "outer_ledger_sha256": ledger["ledger_sha256"],
        "monthly_gate_report_sha256": gate["report_sha256"],
        "monthly_gate_contract_version": gate["contract_version"],
        "bootstrap_configuration": _BOOTSTRAP,
    }
    manifest_sha = _digest(manifest)
    seed = int(manifest_sha[:16], 16)
    bounds = _stationary_bootstrap(values, seed)
    strict = all(_dec(row["lower_bound_usdc_per_day"]) >= TARGET for row in bounds)
    benchmarks = _benchmarks(
        benchmark_evidence, _dec(ledger["totals"]["net_mtm_usdc"]) / Decimal(365)
    )
    review = (
        benchmarks["all_candle_ratio_interpretable"]
        and benchmarks["all_candle_one_trade_capture_ratio_diagnostic"] is not None
        and Decimal(".8")
        <= _dec(benchmarks["all_candle_one_trade_capture_ratio_diagnostic"])
        <= Decimal(".87")
    ) or (
        benchmarks["candidate_matched_tradeable_capture_ratio"] is not None
        and _dec(benchmarks["candidate_matched_tradeable_capture_ratio"])
        >= Decimal(".95")
    )
    basis = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "outer_process_sha256": process.process_sha256,
        "outer_ledger_sha256": ledger["ledger_sha256"],
        "monthly_gate_report_sha256": gate["report_sha256"],
        "pre_bootstrap_input_manifest": manifest,
        "pre_bootstrap_input_manifest_sha256": manifest_sha,
        "seed_uint64": seed,
        "bootstrap_results": bounds,
        "historical_bootstrap_lower_bound": strict,
        "benchmarks": benchmarks,
        "manual_leakage_overfit_review_required": review,
        "leakage_overfit_lock": review,
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "statistically_supported": False,
        "sealed_bootstrap_target_supported": False,
        "canonical_adoption_eligible": False,
        "selection_or_monthly_gate_feedback_forbidden": True,
        "safety": _SAFETY,
    }
    return validate_historical_diagnostics(
        HistoricalDiagnostics(_canonical(basis), _digest(basis))
    )


def validate_historical_diagnostics(
    value: HistoricalDiagnostics | Mapping[str, Any],
    *,
    boundary_plan: MonthlyProcessBoundaryPlan | None = None,
    outer_process: OuterOriginProcess | None = None,
    baseline_ledger: OuterMtmLedger | None = None,
    monthly_quality_report: MonthlyQualityGateReport | None = None,
    data_identity_sha256: str | None = None,
    code_commit: str | None = None,
    pipeline_generation_id: str | None = None,
    benchmark_evidence: Mapping[str, Any] | None = None,
) -> HistoricalDiagnostics:
    root = (
        value.to_dict()
        if isinstance(value, HistoricalDiagnostics)
        else dict(_map(value, "historical_diagnostics"))
    )
    if not isinstance(value, HistoricalDiagnostics):
        dependencies = (
            boundary_plan,
            outer_process,
            baseline_ledger,
            monthly_quality_report,
            data_identity_sha256,
            code_commit,
            pipeline_generation_id,
            benchmark_evidence,
        )
        if any(item is None for item in dependencies):
            raise HistoricalDiagnosticsError(
                "persisted historical diagnostics require all source evidence"
            )
        expected = build_historical_diagnostics(
            boundary_plan=boundary_plan,
            outer_process=outer_process,
            baseline_ledger=baseline_ledger,
            monthly_quality_report=monthly_quality_report,
            data_identity_sha256=data_identity_sha256,
            code_commit=code_commit,
            pipeline_generation_id=pipeline_generation_id,
            benchmark_evidence=benchmark_evidence,
        ).to_dict()
        if root != expected:
            raise HistoricalDiagnosticsError(
                "persisted historical diagnostics differ from source re-evaluation"
            )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "outer_process_sha256",
        "outer_ledger_sha256",
        "monthly_gate_report_sha256",
        "pre_bootstrap_input_manifest",
        "pre_bootstrap_input_manifest_sha256",
        "seed_uint64",
        "bootstrap_results",
        "historical_bootstrap_lower_bound",
        "benchmarks",
        "manual_leakage_overfit_review_required",
        "leakage_overfit_lock",
        "freshness",
        "diagnostic_only",
        "statistically_supported",
        "sealed_bootstrap_target_supported",
        "canonical_adoption_eligible",
        "selection_or_monthly_gate_feedback_forbidden",
        "safety",
        "report_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != REPORT_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
    ):
        raise HistoricalDiagnosticsError(
            "historical diagnostics fields or versions are invalid"
        )
    manifest = root["pre_bootstrap_input_manifest"]
    if root["pre_bootstrap_input_manifest_sha256"] != _digest(manifest) or root[
        "seed_uint64"
    ] != int(root["pre_bootstrap_input_manifest_sha256"][:16], 16):
        raise HistoricalDiagnosticsError("bootstrap manifest or seed identity mismatch")
    results = root["bootstrap_results"]
    if (
        not isinstance(results, list)
        or [row.get("expected_block_length") for row in results] != list(BLOCK_LENGTHS)
        or any(
            row.get("replications") != REPLICATIONS
            or row.get("order_statistic_one_based") != 500
            for row in results
        )
    ):
        raise HistoricalDiagnosticsError("bootstrap result structure is invalid")
    strict = all(_dec(row["lower_bound_usdc_per_day"]) >= TARGET for row in results)
    if root["historical_bootstrap_lower_bound"] is not strict:
        raise HistoricalDiagnosticsError(
            "historical bootstrap flag contradicts lower bounds"
        )
    if (
        root["freshness"] != "NOT_FRESH"
        or root["diagnostic_only"] is not True
        or root["statistically_supported"] is not False
        or root["sealed_bootstrap_target_supported"] is not False
        or root["canonical_adoption_eligible"] is not False
        or root["selection_or_monthly_gate_feedback_forbidden"] is not True
        or root["safety"] != _SAFETY
    ):
        raise HistoricalDiagnosticsError(
            "historical diagnostics safety/freshness policy is invalid"
        )
    if (
        root["manual_leakage_overfit_review_required"]
        is not root["leakage_overfit_lock"]
    ):
        raise HistoricalDiagnosticsError("manual review and leakage lock mismatch")
    observed = _sha(root["report_sha256"])
    basis = dict(root)
    basis.pop("report_sha256")
    if observed != _digest(basis):
        raise HistoricalDiagnosticsError("historical diagnostics digest mismatch")
    return HistoricalDiagnostics(_canonical(basis), observed)


def _stationary_bootstrap(values: Sequence[Decimal], seed: int) -> list[dict[str, Any]]:
    if len(values) != 365:
        raise HistoricalDiagnosticsError("stationary bootstrap requires 365 values")
    rng = random.Random(seed)
    output = []
    n = len(values)
    for length in BLOCK_LENGTHS:
        means = []
        restart = 1 / length
        for _ in range(REPLICATIONS):
            index = rng.randrange(n)
            total = Decimal(0)
            for draw in range(n):
                if draw and rng.random() < restart:
                    index = rng.randrange(n)
                elif draw:
                    index = (index + 1) % n
                total += values[index]
            means.append(total / Decimal(n))
        means.sort()
        lower = means[499]
        output.append(
            {
                "expected_block_length": length,
                "restart_probability": _text(Decimal(1) / Decimal(length)),
                "replications": REPLICATIONS,
                "order_statistic_one_based": 500,
                "lower_bound_usdc_per_day": _text(lower),
            }
        )
    return output


def _benchmarks(value: Mapping[str, Any], process_daily: Decimal) -> dict[str, Any]:
    root = dict(_map(value, "benchmark_evidence"))
    required = {
        "all_candle_one_trade_close_hindsight_usdc_per_day",
        "candidate_matched_volume_filtered_hindsight_usdc_per_day",
        "candidate_max_roundtrips_per_day",
        "candidate_matched_constraints",
        "evidence_sha256",
    }
    if set(root) != required:
        raise HistoricalDiagnosticsError("benchmark evidence fields are invalid")
    observed = root.pop("evidence_sha256")
    if observed != _digest(root):
        raise HistoricalDiagnosticsError("benchmark evidence digest mismatch")
    constraints = dict(
        _map(root["candidate_matched_constraints"], "candidate_matched_constraints")
    )
    if set(constraints) != set(_MATCHED_CONSTRAINTS) or any(
        constraints[name] is not True for name in _MATCHED_CONSTRAINTS
    ):
        raise HistoricalDiagnosticsError(
            "candidate-matched hindsight constraints are incomplete"
        )
    all_value = _dec(root["all_candle_one_trade_close_hindsight_usdc_per_day"])
    matched = _dec(root["candidate_matched_volume_filtered_hindsight_usdc_per_day"])
    if all_value <= 0 or matched <= 0:
        all_ratio = matched_ratio = None
    else:
        all_ratio = process_daily / all_value
        matched_ratio = process_daily / matched
    max_roundtrips = root["candidate_max_roundtrips_per_day"]
    if type(max_roundtrips) is not int or max_roundtrips < 0:
        raise HistoricalDiagnosticsError("candidate_max_roundtrips_per_day is invalid")
    return {
        **root,
        "evidence_sha256": observed,
        "process_oos_net_usdc_per_day": _text(process_daily),
        "all_candle_one_trade_capture_ratio_diagnostic": _text(all_ratio)
        if all_ratio is not None
        else None,
        "all_candle_ratio_interpretable": max_roundtrips <= 1,
        "candidate_matched_tradeable_capture_ratio": _text(matched_ratio)
        if matched_ratio is not None
        else None,
    }


def _map(v, label):
    if not isinstance(v, Mapping):
        raise HistoricalDiagnosticsError(f"{label} must be an object")
    return v


def _dec(v):
    if isinstance(v, bool):
        raise HistoricalDiagnosticsError("numeric value cannot be boolean")
    try:
        x = Decimal(str(v))
    except (InvalidOperation, ValueError) as exc:
        raise HistoricalDiagnosticsError("numeric value is invalid") from exc
    if not x.is_finite():
        raise HistoricalDiagnosticsError("numeric value must be finite")
    return x


def _text(v):
    return "0" if v == 0 else format(v.normalize(), "f")


def _nonempty(v, label):
    if not isinstance(v, str) or not v.strip():
        raise HistoricalDiagnosticsError(f"{label} must be non-empty")
    return v


def _sha(v):
    if (
        not isinstance(v, str)
        or len(v) != 64
        or any(c not in "0123456789abcdef" for c in v)
    ):
        raise HistoricalDiagnosticsError("identity must be sha256")
    return v


def _canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(v):
    return hashlib.sha256(_canonical(v).encode()).hexdigest()


__all__ = [
    "BLOCK_LENGTHS",
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "REPORT_SCHEMA_VERSION",
    "REPLICATIONS",
    "HistoricalDiagnostics",
    "HistoricalDiagnosticsError",
    "build_historical_diagnostics",
    "load_historical_diagnostics_contract",
    "validate_historical_diagnostics",
]
