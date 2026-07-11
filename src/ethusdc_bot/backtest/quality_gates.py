"""Fixed, fail-closed quality gates for offline strategy research.

The evaluator consumes already-computed evidence.  It never reads an audit
window, runs a strategy, or changes thresholds from observed results.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from math import isclose, isfinite
from statistics import median, pstdev
from typing import Any, Literal


Stage = Literal["selection", "final"]
_MISSING = object()


@dataclass(frozen=True, init=False)
class QualityGateV1:
    """Immutable, ex-ante thresholds for research and sealed-holdout gates."""

    version: str = "quality_gate_v1"

    baseline_fee_bps_per_side: float = 10.0
    baseline_slippage_bps_per_side: float = 5.0
    joint_stress_fee_bps_per_side: float = 15.0
    joint_stress_slippage_bps_per_side: float = 10.0
    slippage_stress_fee_bps_per_side: float = 10.0
    slippage_stress_slippage_bps_per_side: float = 15.0

    min_validation_trades: int = 50
    min_validation_profit_factor: float = 1.10
    max_validation_drawdown_usdc: float = 15.0

    required_wfv_folds: int = 6
    min_wfv_fold_days: int = 60
    min_wfv_trades_per_fold: int = 30
    min_wfv_total_trades: int = 180
    min_wfv_profit_factor: float = 1.20
    min_positive_wfv_folds: int = 5
    min_wfv_folds_pf_at_least_1_05: int = 5
    min_worst_fold_profit_factor: float = 0.90
    min_worst_fold_net_usdc_per_day: float = -0.10
    max_fold_net_coefficient_of_variation: float = 1.0
    min_wfv_to_training_net_retention: float = 0.60
    max_wfv_drawdown_usdc: float = 15.0

    max_drawdown_usdc: float = 15.0
    max_underwater_days: int = 60
    max_top1_positive_pnl_share: float = 0.10
    max_top5_positive_pnl_share: float = 0.35
    min_profit_factor_without_top5: float = 1.05

    parameter_perturbation_fraction: float = 0.10
    parameter_session_hour_step: int = 1
    min_passing_neighbor_fraction: float = 0.80
    min_neighbor_median_net_retention: float = 0.75
    min_worst_neighbor_net_usdc_per_day: float = -0.10

    min_joint_stress_profit_factor: float = 1.10
    min_joint_stress_net_retention: float = 0.50
    max_joint_stress_drawdown_usdc: float = 20.0
    min_slippage_stress_profit_factor: float = 1.05
    max_friction_share_of_positive_pre_cost_pnl: float = 0.40

    min_months_observed: int = 12
    min_positive_month_fraction: float = 0.75
    min_active_month_fraction: float = 10 / 12
    max_no_trade_gap_days: int = 30
    min_quarters_observed: int = 4
    min_positive_quarter_fraction: float = 1.0
    min_quarter_trade_count: int = 20
    min_worst_month_net_usdc: float = -5.0

    regime_definition: str = "trend_sign_x_training_median_volatility"
    regime_threshold_source: str = "training_only"
    required_regime_count: int = 4
    min_trades_per_regime: int = 20
    min_positive_regime_count: int = 3
    min_regimes_pf_at_least_1_05: int = 3
    min_worst_regime_profit_factor: float = 0.90
    min_worst_regime_net_usdc: float = -5.0
    max_regime_positive_pnl_share: float = 0.60

    required_sealed_holdout_evaluations: int = 1
    min_final_trades: int = 120
    target_net_usdc_per_day: float = 3.0
    min_final_profit_factor: float = 1.25
    max_final_drawdown_usdc: float = 15.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


QUALITY_GATE_V1 = QualityGateV1()


@dataclass(frozen=True)
class GateCheck:
    code: str
    phase: Stage
    passed: bool
    expected: str
    actual: Any
    evidence_paths: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "phase": self.phase,
            "passed": self.passed,
            "expected": self.expected,
            "actual": _json_safe(self.actual),
            "evidence_paths": list(self.evidence_paths),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class QualityGateReport:
    gate: QualityGateV1
    stage: Stage
    status: str
    passed: bool
    checks: tuple[GateCheck, ...]
    missing_evidence: tuple[str, ...]
    invalid_evidence: tuple[str, ...]
    stage_readiness: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "gate_version": self.gate.version,
            "stage": self.stage,
            "status": self.status,
            "passed": self.passed,
            "thresholds": self.gate.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
            "missing_evidence": list(self.missing_evidence),
            "invalid_evidence": list(self.invalid_evidence),
            "stage_readiness": dict(self.stage_readiness),
            "safety": {
                "candidate_adoptable": False,
                "candidate_ready_for_human_adoption_review": self.stage_readiness["candidate_adoption_ready"],
                "live": "locked",
                "paper": "locked",
                "testtrade": "locked",
            },
        }


class _Evaluator:
    def __init__(self, evidence: Mapping[str, Any]):
        self.evidence = evidence
        self.checks: list[GateCheck] = []
        self.missing: set[str] = set()
        self.invalid: set[str] = set()
        self.selection_missing: set[str] = set()
        self.selection_invalid: set[str] = set()

    def value(
        self,
        code: str,
        path: str,
        predicate: Callable[[Any], bool],
        *,
        expected: str,
        phase: Stage = "selection",
    ) -> None:
        value = self._read(path)
        if value is _MISSING or value is None:
            self._missing(code, (path,), expected, phase)
            return
        try:
            passed = bool(predicate(value))
        except (TypeError, ValueError, OverflowError):
            self._invalid(code, (path,), expected, value, phase)
            return
        self.checks.append(
            GateCheck(
                code=code,
                phase=phase,
                passed=passed,
                expected=expected,
                actual=value,
                evidence_paths=(path,),
                reason="passed" if passed else "threshold_not_met",
            )
        )

    def number(
        self,
        code: str,
        path: str,
        predicate: Callable[[float], bool],
        *,
        expected: str,
        phase: Stage = "selection",
    ) -> None:
        value = self._read(path)
        if value is _MISSING or value is None:
            self._missing(code, (path,), expected, phase)
            return
        if not _is_number(value):
            self._invalid(code, (path,), expected, value, phase)
            return
        number = float(value)
        passed = bool(predicate(number))
        self.checks.append(
            GateCheck(
                code=code,
                phase=phase,
                passed=passed,
                expected=expected,
                actual=value,
                evidence_paths=(path,),
                reason="passed" if passed else "threshold_not_met",
            )
        )

    def numbers(
        self,
        code: str,
        paths: tuple[str, ...],
        predicate: Callable[..., bool],
        *,
        expected: str,
        actual: Callable[..., Any] | None = None,
        phase: Stage = "selection",
    ) -> None:
        values = [self._read(path) for path in paths]
        missing = tuple(path for path, value in zip(paths, values) if value is _MISSING or value is None)
        if missing:
            self._missing(code, missing, expected, phase)
            return
        invalid = tuple(path for path, value in zip(paths, values) if not _is_number(value))
        if invalid:
            self._track_invalid(invalid, phase)
            self.checks.append(GateCheck(code, phase, False, expected, None, paths, f"invalid_evidence:{','.join(invalid)}"))
            return
        numeric = [float(value) for value in values]
        passed = bool(predicate(*numeric))
        actual_value = actual(*numeric) if actual is not None else dict(zip(paths, values))
        self.checks.append(
            GateCheck(code, phase, passed, expected, actual_value, paths, "passed" if passed else "threshold_not_met")
        )

    def folds(self, gate: QualityGateV1) -> None:
        path = "wfv.folds"
        value = self._read(path)
        if value is _MISSING or value is None:
            self._missing("wfv.fold_structure", (path,), f"exactly {gate.required_wfv_folds} folds", "selection")
            self._missing("wfv.fold_days", (path,), f"every fold >= {gate.min_wfv_fold_days} days", "selection")
            self._missing("wfv.fold_trades", (path,), f"every fold >= {gate.min_wfv_trades_per_fold} trades", "selection")
            self._missing(
                "wfv.fold_derived_consistency",
                (path,),
                "aggregate WFV values equal values derived from every fold",
                "selection",
            )
            return
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            self._invalid("wfv.fold_structure", (path,), "list of fold mappings", value, "selection")
            return
        folds = list(value)
        structure_ok = len(folds) == gate.required_wfv_folds and all(isinstance(fold, Mapping) for fold in folds)
        self.checks.append(
            GateCheck(
                "wfv.fold_structure",
                "selection",
                structure_ok,
                f"exactly {gate.required_wfv_folds} fold mappings",
                len(folds),
                (path,),
                "passed" if structure_ok else "threshold_not_met",
            )
        )
        if not all(isinstance(fold, Mapping) for fold in folds):
            self._track_invalid((path,), "selection")
            return

        rows: list[dict[str, Any]] = []
        missing_paths: list[str] = []
        invalid_paths: list[str] = []
        for index, fold in enumerate(folds):
            assert isinstance(fold, Mapping)
            metrics = fold.get("metrics", _MISSING)
            metrics_path = f"wfv.folds[{index}].metrics"
            if metrics is _MISSING or metrics is None:
                missing_paths.append(metrics_path)
                continue
            if not isinstance(metrics, Mapping):
                invalid_paths.append(metrics_path)
                continue

            raw_values = {
                "days": fold.get("days", _MISSING),
                "trade_count": metrics.get("trade_count", _MISSING),
                "net_profit_usdc": metrics.get("net_profit_usdc", _MISSING),
                "net_usdc_per_day": metrics.get("net_usdc_per_day", _MISSING),
                "profit_factor": metrics.get("profit_factor", _MISSING),
                "gross_profit_usdc": metrics.get("gross_profit_usdc", _MISSING),
                "gross_loss_usdc": metrics.get("gross_loss_usdc", _MISSING),
                "max_drawdown_usdc": metrics.get("max_drawdown_usdc", _MISSING),
            }
            row: dict[str, Any] = {"fold_index": index}
            for field, raw in raw_values.items():
                field_path = (
                    f"wfv.folds[{index}].days"
                    if field == "days"
                    else f"wfv.folds[{index}].metrics.{field}"
                )
                if raw is _MISSING or raw is None:
                    missing_paths.append(field_path)
                elif not _is_number(raw):
                    invalid_paths.append(field_path)
                else:
                    row[field] = float(raw)
            method = metrics.get("drawdown_method", _MISSING)
            method_path = f"wfv.folds[{index}].metrics.drawdown_method"
            if method is _MISSING or method is None:
                missing_paths.append(method_path)
            elif not isinstance(method, str):
                invalid_paths.append(method_path)
            else:
                row["drawdown_method"] = method

            curve = fold.get("equity_curve_usdc", _MISSING)
            curve_path = f"wfv.folds[{index}].equity_curve_usdc"
            if curve is _MISSING or curve is None:
                missing_paths.append(curve_path)
            elif isinstance(curve, (str, bytes)) or not isinstance(curve, Sequence):
                invalid_paths.append(curve_path)
            elif len(curve) < 2 or any(not _is_number(point) for point in curve):
                invalid_paths.append(curve_path)
            else:
                row["equity_curve_usdc"] = [float(point) for point in curve]

            required_row_fields = len(raw_values) + 3
            if len(row) == required_row_fields:
                rows.append(row)

        self._track_missing(tuple(missing_paths), "selection")
        self._track_invalid(tuple(invalid_paths), "selection")
        days = [row["days"] for row in rows]
        trades = [row["trade_count"] for row in rows]
        days_ok = len(days) == len(folds) and all(value >= gate.min_wfv_fold_days for value in days)
        trades_ok = len(trades) == len(folds) and all(value >= gate.min_wfv_trades_per_fold for value in trades)
        self.checks.append(
            GateCheck(
                "wfv.fold_days",
                "selection",
                days_ok,
                f"every fold >= {gate.min_wfv_fold_days} days",
                min(days) if days else None,
                (path,),
                "passed" if days_ok else "missing_or_invalid_fold_evidence" if len(days) != len(folds) else "threshold_not_met",
            )
        )
        self.checks.append(
            GateCheck(
                "wfv.fold_trades",
                "selection",
                trades_ok,
                f"every fold >= {gate.min_wfv_trades_per_fold} trades",
                min(trades) if trades else None,
                (path,),
                "passed" if trades_ok else "missing_or_invalid_fold_evidence" if len(trades) != len(folds) else "threshold_not_met",
            )
        )

        aggregate_path = "wfv.aggregate"
        aggregate = self._read(aggregate_path)
        aggregate_keys = (
            "trade_count",
            "net_profit_usdc",
            "net_usdc_per_day",
            "profit_factor",
            "max_drawdown_usdc",
            "positive_fold_count",
            "folds_pf_at_least_1_05",
            "worst_fold_profit_factor",
            "median_fold_net_usdc_per_day",
            "worst_fold_net_usdc_per_day",
            "fold_net_coefficient_of_variation",
        )
        aggregate_paths = tuple(f"{aggregate_path}.{key}" for key in aggregate_keys)
        reported: dict[str, float] = {}
        if aggregate is _MISSING or aggregate is None:
            self._track_missing((aggregate_path,), "selection")
        elif not isinstance(aggregate, Mapping):
            self._track_invalid((aggregate_path,), "selection")
        else:
            for key, field_path in zip(aggregate_keys, aggregate_paths):
                raw = aggregate.get(key, _MISSING)
                if raw is _MISSING or raw is None:
                    self._track_missing((field_path,), "selection")
                elif not _is_number(raw):
                    self._track_invalid((field_path,), "selection")
                else:
                    reported[key] = float(raw)

        consistency_paths = (path,) + aggregate_paths
        complete = len(rows) == len(folds) and len(reported) == len(aggregate_keys)
        if not complete:
            self.checks.append(
                GateCheck(
                    "wfv.fold_derived_consistency",
                    "selection",
                    False,
                    "aggregate WFV values equal values derived from every fold",
                    None,
                    consistency_paths,
                    "missing_or_invalid_fold_evidence",
                )
            )
            return

        net_values = [row["net_usdc_per_day"] for row in rows]
        profit_factors = [row["profit_factor"] for row in rows]
        total_days = sum(days)
        total_gross_profit = sum(row["gross_profit_usdc"] for row in rows)
        total_gross_loss = sum(row["gross_loss_usdc"] for row in rows)
        mean_net = sum(net_values) / len(net_values) if net_values else 0.0
        derived_cv = pstdev(net_values) / abs(mean_net) if len(net_values) > 1 and mean_net else None

        chained_equity = [0.0]
        equity_offset = 0.0
        for row in rows:
            curve = row["equity_curve_usdc"]
            chained_equity.extend(equity_offset + point for point in curve[1:])
            equity_offset += row["net_profit_usdc"]

        derived: dict[str, float | None] = {
            "trade_count": sum(trades),
            "net_profit_usdc": sum(row["net_profit_usdc"] for row in rows),
            "net_usdc_per_day": sum(row["net_profit_usdc"] for row in rows) / total_days
            if total_days > 0
            else None,
            "profit_factor": total_gross_profit / total_gross_loss if total_gross_loss > 0 else None,
            "max_drawdown_usdc": _max_drawdown(chained_equity),
            "positive_fold_count": float(sum(1 for value in net_values if value > 0)),
            "folds_pf_at_least_1_05": float(sum(1 for value in profit_factors if value >= 1.05)),
            "worst_fold_profit_factor": min(profit_factors) if profit_factors else None,
            "median_fold_net_usdc_per_day": median(net_values) if net_values else None,
            "worst_fold_net_usdc_per_day": min(net_values) if net_values else None,
            "fold_net_coefficient_of_variation": derived_cv,
        }
        fold_net_mismatches = tuple(
            f"wfv.folds[{int(row['fold_index'])}].metrics.net_usdc_per_day"
            for row in rows
            if row["days"] <= 0
            or not isclose(
                row["net_profit_usdc"] / row["days"],
                row["net_usdc_per_day"],
                rel_tol=1e-8,
                abs_tol=1e-8,
            )
        )
        fold_gross_mismatches = tuple(
            f"wfv.folds[{int(row['fold_index'])}].metrics.gross_profit_usdc"
            for row in rows
            if row["gross_profit_usdc"] < 0
            or row["gross_loss_usdc"] <= 0
            or not isclose(
                row["gross_profit_usdc"] - row["gross_loss_usdc"],
                row["net_profit_usdc"],
                rel_tol=1e-8,
                abs_tol=1e-8,
            )
            or not isclose(
                row["gross_profit_usdc"] / row["gross_loss_usdc"],
                row["profit_factor"],
                rel_tol=1e-8,
                abs_tol=1e-8,
            )
        )
        fold_drawdown_mismatches = tuple(
            f"wfv.folds[{int(row['fold_index'])}].equity_curve_usdc"
            for row in rows
            if row["drawdown_method"] != "mark_to_market"
            or not isclose(row["equity_curve_usdc"][0], 0.0, rel_tol=0.0, abs_tol=1e-8)
            or not isclose(
                row["equity_curve_usdc"][-1],
                row["net_profit_usdc"],
                rel_tol=1e-8,
                abs_tol=1e-8,
            )
            or not isclose(
                _max_drawdown(row["equity_curve_usdc"]),
                row["max_drawdown_usdc"],
                rel_tol=1e-8,
                abs_tol=1e-8,
            )
        )
        trade_shape_mismatches = tuple(
            f"wfv.folds[{int(row['fold_index'])}].metrics.trade_count"
            for row in rows
            if row["trade_count"] < 0 or not row["trade_count"].is_integer()
        )
        aggregate_mismatches = tuple(
            f"{aggregate_path}.{key}"
            for key in aggregate_keys
            if derived[key] is None
            or not isclose(reported[key], float(derived[key]), rel_tol=1e-8, abs_tol=1e-8)
        )
        all_mismatches = (
            aggregate_mismatches
            + fold_net_mismatches
            + fold_gross_mismatches
            + fold_drawdown_mismatches
            + trade_shape_mismatches
        )
        self._track_invalid(all_mismatches, "selection")
        consistency_ok = not all_mismatches
        self.checks.append(
            GateCheck(
                "wfv.fold_derived_consistency",
                "selection",
                consistency_ok,
                "aggregate WFV values equal values derived from every fold",
                {
                    "fold_net_internal_consistency": not fold_net_mismatches,
                    "fold_gross_profit_factor_consistency": not fold_gross_mismatches,
                    "fold_mark_to_market_drawdown_consistency": not fold_drawdown_mismatches,
                    "fold_trade_counts_are_nonnegative_integers": not trade_shape_mismatches,
                    "reported": reported,
                    "derived": derived,
                },
                consistency_paths,
                "passed" if consistency_ok else "aggregate_fold_mismatch",
            )
        )

    def _read(self, path: str) -> Any:
        value: Any = self.evidence
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                return _MISSING
            value = value[part]
        return value

    def _missing(self, code: str, paths: tuple[str, ...], expected: str, phase: Stage) -> None:
        self._track_missing(paths, phase)
        self.checks.append(
            GateCheck(code, phase, False, expected, None, paths, f"missing_evidence:{','.join(paths)}")
        )

    def _invalid(self, code: str, paths: tuple[str, ...], expected: str, actual: Any, phase: Stage) -> None:
        self._track_invalid(paths, phase)
        self.checks.append(
            GateCheck(code, phase, False, expected, actual, paths, f"invalid_evidence:{','.join(paths)}")
        )

    def _track_missing(self, paths: tuple[str, ...], phase: Stage) -> None:
        self.missing.update(paths)
        if phase == "selection":
            self.selection_missing.update(paths)

    def _track_invalid(self, paths: tuple[str, ...], phase: Stage) -> None:
        self.invalid.update(paths)
        if phase == "selection":
            self.selection_invalid.update(paths)


def evaluate_quality_gates(
    evidence: Mapping[str, Any],
    *,
    stage: Stage = "selection",
    gate: QualityGateV1 = QUALITY_GATE_V1,
) -> QualityGateReport:
    """Evaluate fixed gates without reading or deriving any market evidence.

    Missing, null, non-finite, or structurally invalid evidence always fails.
    Selection evaluates training/validation-only readiness.  Final adds a
    single sealed-holdout pass/fail gate and never marks live trading ready.
    """

    if stage not in {"selection", "final"}:
        raise ValueError("stage must be 'selection' or 'final'")
    if not isinstance(evidence, Mapping):
        evidence = {}
    evaluator = _Evaluator(evidence)

    evaluator.value("protocol.version", "protocol.gate_version", lambda value: value == gate.version, expected=gate.version)
    evaluator.value("protocol.gate_frozen", "protocol.gate_frozen_before_evaluation", lambda value: value is True, expected="true")
    evaluator.value("protocol.no_audit_selection", "protocol.selection_uses_audit", lambda value: value is False, expected="false")

    evaluator.number("validation.trades", "validation.trade_count", lambda value: value >= gate.min_validation_trades, expected=f">= {gate.min_validation_trades}")
    evaluator.number("validation.net_positive", "validation.net_usdc_per_day", lambda value: value > 0, expected="> 0")
    evaluator.number("validation.profit_factor", "validation.profit_factor", lambda value: value >= gate.min_validation_profit_factor, expected=f">= {gate.min_validation_profit_factor}")
    evaluator.value(
        "validation.drawdown_method",
        "validation.drawdown_method",
        lambda value: value == "mark_to_market",
        expected="mark_to_market",
    )
    evaluator.number("validation.drawdown", "validation.max_drawdown_usdc", lambda value: value <= gate.max_validation_drawdown_usdc, expected=f"<= {gate.max_validation_drawdown_usdc}")

    evaluator.number("wfv.fold_count", "wfv.fold_count", lambda value: value == gate.required_wfv_folds, expected=f"== {gate.required_wfv_folds}")
    evaluator.folds(gate)
    evaluator.number("wfv.total_trades", "wfv.aggregate.trade_count", lambda value: value >= gate.min_wfv_total_trades, expected=f">= {gate.min_wfv_total_trades}")
    evaluator.number("wfv.net_positive", "wfv.aggregate.net_usdc_per_day", lambda value: value > 0, expected="> 0")
    evaluator.number("wfv.profit_factor", "wfv.aggregate.profit_factor", lambda value: value >= gate.min_wfv_profit_factor, expected=f">= {gate.min_wfv_profit_factor}")
    evaluator.value(
        "wfv.drawdown_method",
        "wfv.aggregate.drawdown_method",
        lambda value: value == "mark_to_market",
        expected="mark_to_market",
    )
    evaluator.number("wfv.drawdown", "wfv.aggregate.max_drawdown_usdc", lambda value: value <= gate.max_wfv_drawdown_usdc, expected=f"<= {gate.max_wfv_drawdown_usdc}")
    evaluator.number("wfv.positive_folds", "wfv.aggregate.positive_fold_count", lambda value: value >= gate.min_positive_wfv_folds, expected=f">= {gate.min_positive_wfv_folds}")
    evaluator.number("wfv.fold_pf_count", "wfv.aggregate.folds_pf_at_least_1_05", lambda value: value >= gate.min_wfv_folds_pf_at_least_1_05, expected=f">= {gate.min_wfv_folds_pf_at_least_1_05}")
    evaluator.number("wfv.worst_fold_pf", "wfv.aggregate.worst_fold_profit_factor", lambda value: value >= gate.min_worst_fold_profit_factor, expected=f">= {gate.min_worst_fold_profit_factor}")
    evaluator.number("wfv.median_fold_positive", "wfv.aggregate.median_fold_net_usdc_per_day", lambda value: value > 0, expected="> 0")
    evaluator.number("wfv.worst_fold_net", "wfv.aggregate.worst_fold_net_usdc_per_day", lambda value: value >= gate.min_worst_fold_net_usdc_per_day, expected=f">= {gate.min_worst_fold_net_usdc_per_day}")
    evaluator.number("wfv.fold_cv", "wfv.aggregate.fold_net_coefficient_of_variation", lambda value: 0 <= value <= gate.max_fold_net_coefficient_of_variation, expected=f"0..{gate.max_fold_net_coefficient_of_variation}")
    evaluator.number("wfv.full_training_positive", "wfv.aggregate.full_training_net_usdc_per_day", lambda value: value > 0, expected="> 0")
    evaluator.numbers(
        "wfv.net_retention",
        ("wfv.aggregate.net_usdc_per_day", "wfv.aggregate.full_training_net_usdc_per_day"),
        lambda wfv, training: training > 0 and wfv / training >= gate.min_wfv_to_training_net_retention,
        expected=f">= {gate.min_wfv_to_training_net_retention} of positive full-training net/day",
        actual=lambda wfv, training: wfv / training if training > 0 else None,
    )

    evaluator.value(
        "rolling.drawdown_method",
        "rolling.drawdown_method",
        lambda value: value == "mark_to_market",
        expected="mark_to_market",
    )
    evaluator.number("rolling.drawdown", "rolling.max_drawdown_usdc", lambda value: value <= gate.max_drawdown_usdc, expected=f"<= {gate.max_drawdown_usdc}")
    evaluator.number("rolling.underwater", "rolling.max_underwater_days", lambda value: value <= gate.max_underwater_days, expected=f"<= {gate.max_underwater_days}")
    evaluator.number("rolling.top1_concentration", "rolling.top1_positive_pnl_share", lambda value: 0 <= value <= gate.max_top1_positive_pnl_share, expected=f"0..{gate.max_top1_positive_pnl_share}")
    evaluator.number("rolling.top5_concentration", "rolling.top5_positive_pnl_share", lambda value: 0 <= value <= gate.max_top5_positive_pnl_share, expected=f"0..{gate.max_top5_positive_pnl_share}")
    evaluator.number("rolling.net_without_top5", "rolling.net_without_top5_usdc", lambda value: value > 0, expected="> 0")
    evaluator.number("rolling.pf_without_top5", "rolling.profit_factor_without_top5", lambda value: value >= gate.min_profit_factor_without_top5, expected=f">= {gate.min_profit_factor_without_top5}")

    evaluator.number("stress.baseline_fee", "stress.baseline.fee_bps_per_side", lambda value: value == gate.baseline_fee_bps_per_side, expected=f"== {gate.baseline_fee_bps_per_side}")
    evaluator.number("stress.baseline_slippage", "stress.baseline.slippage_bps_per_side", lambda value: value == gate.baseline_slippage_bps_per_side, expected=f"== {gate.baseline_slippage_bps_per_side}")
    evaluator.number("stress.baseline_net", "stress.baseline.net_usdc_per_day", lambda value: value > 0, expected="> 0")
    evaluator.number("stress.joint_fee", "stress.joint.fee_bps_per_side", lambda value: value == gate.joint_stress_fee_bps_per_side, expected=f"== {gate.joint_stress_fee_bps_per_side}")
    evaluator.number("stress.joint_slippage", "stress.joint.slippage_bps_per_side", lambda value: value == gate.joint_stress_slippage_bps_per_side, expected=f"== {gate.joint_stress_slippage_bps_per_side}")
    evaluator.number("stress.joint_net_positive", "stress.joint.net_usdc_per_day", lambda value: value > 0, expected="> 0")
    evaluator.number("stress.joint_profit_factor", "stress.joint.profit_factor", lambda value: value >= gate.min_joint_stress_profit_factor, expected=f">= {gate.min_joint_stress_profit_factor}")
    evaluator.value(
        "stress.joint_drawdown_method",
        "stress.joint.drawdown_method",
        lambda value: value == "mark_to_market",
        expected="mark_to_market",
    )
    evaluator.number("stress.joint_drawdown", "stress.joint.max_drawdown_usdc", lambda value: value <= gate.max_joint_stress_drawdown_usdc, expected=f"<= {gate.max_joint_stress_drawdown_usdc}")
    evaluator.numbers(
        "stress.joint_net_retention",
        ("stress.joint.net_usdc_per_day", "stress.baseline.net_usdc_per_day"),
        lambda stressed, baseline: baseline > 0 and stressed / baseline >= gate.min_joint_stress_net_retention,
        expected=f">= {gate.min_joint_stress_net_retention} of positive baseline net/day",
        actual=lambda stressed, baseline: stressed / baseline if baseline > 0 else None,
    )
    evaluator.number("stress.slippage_fee", "stress.slippage.fee_bps_per_side", lambda value: value == gate.slippage_stress_fee_bps_per_side, expected=f"== {gate.slippage_stress_fee_bps_per_side}")
    evaluator.number("stress.slippage_bps", "stress.slippage.slippage_bps_per_side", lambda value: value == gate.slippage_stress_slippage_bps_per_side, expected=f"== {gate.slippage_stress_slippage_bps_per_side}")
    evaluator.number("stress.slippage_net_positive", "stress.slippage.net_usdc_per_day", lambda value: value > 0, expected="> 0")
    evaluator.number("stress.slippage_profit_factor", "stress.slippage.profit_factor", lambda value: value >= gate.min_slippage_stress_profit_factor, expected=f">= {gate.min_slippage_stress_profit_factor}")
    evaluator.number("stress.friction_share", "stress.friction_share_of_positive_pre_cost_pnl", lambda value: 0 <= value <= gate.max_friction_share_of_positive_pre_cost_pnl, expected=f"0..{gate.max_friction_share_of_positive_pre_cost_pnl}")

    evaluator.value("parameter.all_numeric_perturbed", "parameter_stability.all_numeric_parameters_perturbed", lambda value: value is True, expected="true")
    evaluator.numbers(
        "parameter.neighbor_coverage",
        ("parameter_stability.numeric_parameter_count", "parameter_stability.neighbor_count"),
        lambda parameter_count, neighbor_count: parameter_count > 0 and neighbor_count >= parameter_count * 2,
        expected="numeric_parameter_count > 0 and neighbor_count >= 2 * numeric_parameter_count",
    )
    evaluator.number("parameter.perturbation", "parameter_stability.perturbation_fraction", lambda value: value == gate.parameter_perturbation_fraction, expected=f"== {gate.parameter_perturbation_fraction}")
    evaluator.number("parameter.session_step", "parameter_stability.session_hour_step", lambda value: value == gate.parameter_session_hour_step, expected=f"== {gate.parameter_session_hour_step}")
    evaluator.number("parameter.passing_neighbors", "parameter_stability.passing_neighbor_fraction", lambda value: gate.min_passing_neighbor_fraction <= value <= 1, expected=f"{gate.min_passing_neighbor_fraction}..1")
    evaluator.number("parameter.median_retention", "parameter_stability.median_net_retention", lambda value: value >= gate.min_neighbor_median_net_retention, expected=f">= {gate.min_neighbor_median_net_retention}")
    evaluator.number("parameter.worst_neighbor", "parameter_stability.worst_neighbor_net_usdc_per_day", lambda value: value >= gate.min_worst_neighbor_net_usdc_per_day, expected=f">= {gate.min_worst_neighbor_net_usdc_per_day}")

    evaluator.number(
        "temporal.months",
        "temporal.months_observed",
        lambda value: value >= gate.min_months_observed,
        expected=f">= {gate.min_months_observed}",
    )
    evaluator.numbers(
        "temporal.positive_months",
        ("temporal.positive_months", "temporal.months_observed"),
        lambda positive, observed: observed >= gate.min_months_observed
        and 0 <= positive <= observed
        and positive / observed >= gate.min_positive_month_fraction,
        expected=f">= {gate.min_positive_month_fraction:.0%} of observed months",
        actual=lambda positive, observed: positive / observed if observed > 0 else None,
    )
    evaluator.numbers(
        "temporal.active_months",
        ("temporal.active_months", "temporal.months_observed"),
        lambda active, observed: observed >= gate.min_months_observed
        and 0 <= active <= observed
        and active / observed >= gate.min_active_month_fraction,
        expected=f">= {gate.min_active_month_fraction:.2%} of observed months",
        actual=lambda active, observed: active / observed if observed > 0 else None,
    )
    evaluator.number("temporal.no_trade_gap", "temporal.max_no_trade_gap_days", lambda value: value <= gate.max_no_trade_gap_days, expected=f"<= {gate.max_no_trade_gap_days}")
    evaluator.number(
        "temporal.quarters",
        "temporal.quarters_observed",
        lambda value: value >= gate.min_quarters_observed,
        expected=f">= {gate.min_quarters_observed}",
    )
    evaluator.numbers(
        "temporal.positive_quarters",
        ("temporal.positive_quarters", "temporal.quarters_observed"),
        lambda positive, observed: observed >= gate.min_quarters_observed
        and 0 <= positive <= observed
        and positive / observed >= gate.min_positive_quarter_fraction,
        expected=f">= {gate.min_positive_quarter_fraction:.0%} of observed quarters",
        actual=lambda positive, observed: positive / observed if observed > 0 else None,
    )
    evaluator.number("temporal.quarter_trades", "temporal.min_quarter_trade_count", lambda value: value >= gate.min_quarter_trade_count, expected=f">= {gate.min_quarter_trade_count}")
    evaluator.number("temporal.worst_month", "temporal.worst_month_net_usdc", lambda value: value >= gate.min_worst_month_net_usdc, expected=f">= {gate.min_worst_month_net_usdc}")

    evaluator.value("regime.definition", "regime.definition", lambda value: value == gate.regime_definition, expected=gate.regime_definition)
    evaluator.value("regime.threshold_source", "regime.threshold_source", lambda value: value == gate.regime_threshold_source, expected=gate.regime_threshold_source)
    evaluator.value("regime.trailing_only", "regime.assignment_uses_entry_time_trailing_data_only", lambda value: value is True, expected="true")
    evaluator.number("regime.count", "regime.regime_count", lambda value: value == gate.required_regime_count, expected=f"== {gate.required_regime_count}")
    evaluator.number("regime.trade_coverage", "regime.min_trades_per_regime", lambda value: value >= gate.min_trades_per_regime, expected=f">= {gate.min_trades_per_regime}")
    evaluator.number("regime.positive_count", "regime.positive_regime_count", lambda value: value >= gate.min_positive_regime_count, expected=f">= {gate.min_positive_regime_count}")
    evaluator.number("regime.primary_pf_count", "regime.regimes_pf_at_least_1_05", lambda value: value >= gate.min_regimes_pf_at_least_1_05, expected=f">= {gate.min_regimes_pf_at_least_1_05}")
    evaluator.number("regime.worst_pf", "regime.worst_regime_profit_factor", lambda value: value >= gate.min_worst_regime_profit_factor, expected=f">= {gate.min_worst_regime_profit_factor}")
    evaluator.number("regime.worst_net", "regime.worst_regime_net_usdc", lambda value: value >= gate.min_worst_regime_net_usdc, expected=f">= {gate.min_worst_regime_net_usdc}")
    evaluator.number("regime.concentration", "regime.max_positive_pnl_share", lambda value: 0 <= value <= gate.max_regime_positive_pnl_share, expected=f"0..{gate.max_regime_positive_pnl_share}")

    if stage == "final":
        evaluator.number("final.single_sealed_evaluation", "final.sealed_holdout_evaluations", lambda value: value == gate.required_sealed_holdout_evaluations, expected=f"== {gate.required_sealed_holdout_evaluations}", phase="final")
        evaluator.number("final.trades", "final.trade_count", lambda value: value >= gate.min_final_trades, expected=f">= {gate.min_final_trades}", phase="final")
        evaluator.number("final.target", "final.net_usdc_per_day", lambda value: value >= gate.target_net_usdc_per_day, expected=f">= {gate.target_net_usdc_per_day}", phase="final")
        evaluator.number("final.profit_factor", "final.profit_factor", lambda value: value >= gate.min_final_profit_factor, expected=f">= {gate.min_final_profit_factor}", phase="final")
        evaluator.number("final.average_trade", "final.average_trade_usdc", lambda value: value > 0, expected="> 0", phase="final")
        evaluator.value(
            "final.drawdown_method",
            "final.drawdown_method",
            lambda value: value == "mark_to_market",
            expected="mark_to_market",
            phase="final",
        )
        evaluator.number("final.drawdown", "final.max_drawdown_usdc", lambda value: value <= gate.max_final_drawdown_usdc, expected=f"<= {gate.max_final_drawdown_usdc}", phase="final")

    checks = tuple(evaluator.checks)
    passed = bool(checks) and all(check.passed for check in checks)
    selection_checks = tuple(check for check in checks if check.phase == "selection")
    selection_complete = not evaluator.selection_missing and not evaluator.selection_invalid
    selection_passed = bool(selection_checks) and all(check.passed for check in selection_checks)
    if evaluator.missing:
        status = "fail_missing_evidence"
    elif evaluator.invalid:
        status = "fail_invalid_evidence"
    elif passed:
        status = "pass"
    else:
        status = "fail_gate"
    readiness = {
        "research_evidence_complete": selection_complete,
        "sealed_holdout_ready": selection_passed,
        "candidate_adoption_ready": stage == "final" and passed,
        "live_ready": False,
    }
    return QualityGateReport(
        gate=gate,
        stage=stage,
        status=status,
        passed=passed,
        checks=checks,
        missing_evidence=tuple(sorted(evaluator.missing)),
        invalid_evidence=tuple(sorted(evaluator.invalid)),
        stage_readiness=readiness,
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(float(value))


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = float("-inf")
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, float(equity))
        max_drawdown = max(max_drawdown, peak - float(equity))
    return max_drawdown


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if isfinite(value) else str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_safe(item) for item in value]
    return str(value)
