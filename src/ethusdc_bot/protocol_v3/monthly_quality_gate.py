"""Task-26 fail-closed monthly process quality gate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from .boundaries import MonthlyProcessBoundaryPlan
from .outer_mtm_ledger import OuterMtmLedger, validate_outer_mtm_ledger
from .outer_origins import OuterOriginProcess, validate_outer_origin_process

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_monthly_quality_gate_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_monthly_quality_gate_contract_v1"
CONTRACT_VERSION: Final = "monthly_quality_gate_v1"
REPORT_SCHEMA_VERSION: Final = "protocol_v3_monthly_quality_gate_report_v1"
GREEN: Final = "GREEN"
YELLOW: Final = "YELLOW"
RED: Final = "RED"
_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_OUTER = {
    "min_trades": 120,
    "min_profit_factor": 1.25,
    "min_average_trade_usdc_exclusive": 0,
    "max_drawdown_usdc": 15,
    "max_underwater_days": 60,
    "min_total_net_usdc_exclusive": 0,
}
_DEPLOYMENT = {
    "required_intervals": 12,
    "min_positive": 9,
    "min_active": 10,
    "min_worst_net_usdc": -5,
    "max_top_interval_positive_pnl_share": 0.25,
}
_CALENDAR = {
    "min_positive_month_fraction": 0.75,
    "min_active_month_fraction": 0.8333333333333334,
    "min_worst_month_net_usdc": -5,
    "max_no_trade_gap_days": 30,
    "min_quarters": 4,
    "all_quarters_positive": True,
    "min_exit_trades_per_quarter": 20,
}
_CONCENTRATION = {
    "max_top1_positive_pnl_share": 0.1,
    "max_top5_positive_pnl_share": 0.35,
    "net_without_top5_positive": True,
    "min_profit_factor_without_top5": 1.05,
}
_STRESS = {
    "baseline_fee_bps_per_side": 10,
    "baseline_slippage_bps_per_side": 5,
    "joint_fee_bps_per_side": 15,
    "joint_slippage_bps_per_side": 10,
    "slippage_fee_bps_per_side": 10,
    "slippage_slippage_bps_per_side": 15,
    "joint_min_net_usdc_exclusive": 0,
    "joint_min_profit_factor": 1.1,
    "joint_min_net_retention": 0.5,
    "joint_max_drawdown_usdc": 20,
    "slippage_min_net_usdc_exclusive": 0,
    "slippage_min_profit_factor": 1.05,
    "max_baseline_friction_share": 0.4,
}
_CANONICAL_CONTRACT = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "outer_thresholds": _OUTER,
    "deployment_thresholds": _DEPLOYMENT,
    "calendar_thresholds": _CALENDAR,
    "concentration_thresholds": _CONCENTRATION,
    "stress_thresholds": _STRESS,
    "integrity_policy": {
        "every_integrity_claim_requires_evidence_sha256": True,
        "regime_evidence_requires_content_digest": True,
        "stress_identity_requires_content_digest": True,
    },
    "development_thresholds": {
        "minimum_dsr": 0.95,
        "maximum_pbo": 0.1,
        "no_trade_is_not_a_trading_gate_pass": True,
    },
    "target_policy": {
        "target_net_usdc_per_calendar_day": 3,
        "green_requires_robustness_and_target": True,
        "yellow_means_robustness_passed_ex_target": True,
        "historical_result_is_diagnostic_only": True,
    },
    "deferred_scope": {
        "hindsight_capture_bootstrap_task": 27,
        "fresh_final_evaluator_task": 31,
    },
    "safety": _SAFETY,
}
_INTEGRITY_FIELDS = (
    "data_complete",
    "no_leakage",
    "fingerprints_match",
    "boundaries_match",
    "execution_parity",
    "costs_match",
    "rotation_chain_valid",
    "ledger_complete",
    "safety_locks_intact",
)


class MonthlyQualityGateError(ValueError):
    """Raised when monthly-gate inputs are malformed or contradictory."""


@dataclass(frozen=True)
class MonthlyQualityGateReport:
    canonical_json: str
    report_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["report_sha256"] = self.report_sha256
        return value


def load_monthly_quality_gate_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MonthlyQualityGateError(
            "monthly quality gate contract is missing or invalid"
        ) from exc
    if value != _CANONICAL_CONTRACT:
        raise MonthlyQualityGateError("monthly quality gate contract is not canonical")
    return value


def evaluate_monthly_quality_gate(
    *,
    boundary_plan: MonthlyProcessBoundaryPlan,
    outer_process: OuterOriginProcess,
    baseline_ledger: OuterMtmLedger,
    joint_stress_ledger: OuterMtmLedger,
    slippage_stress_ledger: OuterMtmLedger,
    stress_identity_evidence: Mapping[str, Any],
    regime_evidence: Mapping[str, Any],
    integrity_evidence: Mapping[str, Any],
) -> MonthlyQualityGateReport:
    process = validate_outer_origin_process(outer_process, boundary_plan=boundary_plan)
    baseline = validate_outer_mtm_ledger(
        baseline_ledger, boundary_plan=boundary_plan, outer_process=process
    ).to_dict()
    joint = validate_outer_mtm_ledger(
        joint_stress_ledger, boundary_plan=boundary_plan, outer_process=process
    ).to_dict()
    slippage = validate_outer_mtm_ledger(
        slippage_stress_ledger, boundary_plan=boundary_plan, outer_process=process
    ).to_dict()
    metrics = _metrics(baseline)
    joint_metrics = _metrics(joint)
    slippage_metrics = _metrics(slippage)
    checks = []
    checks.extend(_inner_checks(process.to_dict()))
    checks.extend(_outer_checks(metrics))
    checks.extend(_deployment_checks(baseline))
    checks.extend(_calendar_checks(baseline, metrics))
    checks.extend(_concentration_checks(metrics))
    checks.extend(_stress_checks(metrics, joint_metrics, slippage_metrics))
    checks.extend(_stress_identity_checks(stress_identity_evidence))
    checks.extend(_regime_checks(regime_evidence))
    checks.extend(_integrity_checks(integrity_evidence))
    robustness_passed = bool(checks) and all(row["passed"] for row in checks)
    net_per_day = metrics["net_usdc"] / Decimal("365")
    historically_hit = net_per_day >= Decimal("3")
    status = (
        GREEN
        if robustness_passed and historically_hit
        else YELLOW
        if robustness_passed
        else RED
    )
    basis = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "outer_process_sha256": process.process_sha256,
        "baseline_ledger_sha256": baseline["ledger_sha256"],
        "joint_stress_ledger_sha256": joint["ledger_sha256"],
        "slippage_stress_ledger_sha256": slippage["ledger_sha256"],
        "status": status,
        "robustness_passed": robustness_passed,
        "robustness_passed_ex_target": robustness_passed and not historically_hit,
        "historically_hit": historically_hit,
        "historical_net_usdc_per_calendar_day": _text(net_per_day),
        "statistically_supported": False,
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "metrics": _json_metrics(metrics, joint_metrics, slippage_metrics),
        "checks": checks,
        "failed_check_codes": [row["code"] for row in checks if not row["passed"]],
        "canonical_adoption_eligible": False,
        "protocol_v3_final_status": False,
        "safety": _SAFETY,
    }
    return validate_monthly_quality_gate_report(
        MonthlyQualityGateReport(_canonical(basis), _digest(basis))
    )


def validate_monthly_quality_gate_report(
    value: MonthlyQualityGateReport | Mapping[str, Any],
    *,
    boundary_plan: MonthlyProcessBoundaryPlan | None = None,
    outer_process: OuterOriginProcess | None = None,
    baseline_ledger: OuterMtmLedger | None = None,
    joint_stress_ledger: OuterMtmLedger | None = None,
    slippage_stress_ledger: OuterMtmLedger | None = None,
    stress_identity_evidence: Mapping[str, Any] | None = None,
    regime_evidence: Mapping[str, Any] | None = None,
    integrity_evidence: Mapping[str, Any] | None = None,
) -> MonthlyQualityGateReport:
    root = (
        value.to_dict()
        if isinstance(value, MonthlyQualityGateReport)
        else dict(_map(value, "report"))
    )
    if not isinstance(value, MonthlyQualityGateReport):
        dependencies = (
            boundary_plan,
            outer_process,
            baseline_ledger,
            joint_stress_ledger,
            slippage_stress_ledger,
            stress_identity_evidence,
            regime_evidence,
            integrity_evidence,
        )
        if any(item is None for item in dependencies):
            raise MonthlyQualityGateError(
                "persisted monthly report requires all source evidence for revalidation"
            )
        expected = evaluate_monthly_quality_gate(
            boundary_plan=boundary_plan,
            outer_process=outer_process,
            baseline_ledger=baseline_ledger,
            joint_stress_ledger=joint_stress_ledger,
            slippage_stress_ledger=slippage_stress_ledger,
            stress_identity_evidence=stress_identity_evidence,
            regime_evidence=regime_evidence,
            integrity_evidence=integrity_evidence,
        ).to_dict()
        if root != expected:
            raise MonthlyQualityGateError(
                "persisted monthly report differs from re-evaluated source evidence"
            )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "outer_process_sha256",
        "baseline_ledger_sha256",
        "joint_stress_ledger_sha256",
        "slippage_stress_ledger_sha256",
        "status",
        "robustness_passed",
        "robustness_passed_ex_target",
        "historically_hit",
        "historical_net_usdc_per_calendar_day",
        "statistically_supported",
        "freshness",
        "diagnostic_only",
        "metrics",
        "checks",
        "failed_check_codes",
        "canonical_adoption_eligible",
        "protocol_v3_final_status",
        "safety",
        "report_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != REPORT_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
    ):
        raise MonthlyQualityGateError(
            "monthly quality report fields or versions are invalid"
        )
    checks = root["checks"]
    if (
        not isinstance(checks, list)
        or not checks
        or any(
            set(row) != {"code", "passed", "actual", "expected"}
            or type(row["passed"]) is not bool
            for row in checks
        )
    ):
        raise MonthlyQualityGateError("monthly quality checks are invalid")
    robust = all(row["passed"] for row in checks)
    hit = root["historically_hit"]
    expected = GREEN if robust and hit else YELLOW if robust else RED
    if (
        root["status"] != expected
        or root["robustness_passed"] is not robust
        or root["robustness_passed_ex_target"] is not (robust and not hit)
    ):
        raise MonthlyQualityGateError("monthly quality status contradicts checks")
    if root["failed_check_codes"] != [
        row["code"] for row in checks if not row["passed"]
    ]:
        raise MonthlyQualityGateError("failed check index mismatch")
    if (
        root["statistically_supported"] is not False
        or root["freshness"] != "NOT_FRESH"
        or root["diagnostic_only"] is not True
        or root["canonical_adoption_eligible"] is not False
        or root["protocol_v3_final_status"] is not False
        or root["safety"] != _SAFETY
    ):
        raise MonthlyQualityGateError(
            "historical gate safety/freshness policy is invalid"
        )
    observed = _sha(root["report_sha256"])
    basis = dict(root)
    basis.pop("report_sha256")
    if observed != _digest(basis):
        raise MonthlyQualityGateError("monthly quality report digest mismatch")
    return MonthlyQualityGateReport(_canonical(basis), observed)


def _metrics(payload: Mapping[str, Any]) -> dict[str, Any]:
    trades = payload["closed_trades"]
    daily = payload["daily_mtm"]
    nets = [_dec(row["net_usdc"]) for row in trades]
    wins = sorted((value for value in nets if value > 0), reverse=True)
    losses = [-value for value in nets if value < 0]
    total = _dec(payload["totals"]["net_mtm_usdc"])
    gp = sum(wins, Decimal(0))
    gl = sum(losses, Decimal(0))
    pf = gp / gl if gl > 0 else None
    closes = [_dec(row["closing_equity_usdc"]) for row in daily]
    peak = Decimal(0)
    draw = Decimal(0)
    underwater = 0
    max_underwater = 0
    for equity in closes:
        peak = max(peak, equity)
        draw = max(draw, peak - equity)
        underwater = underwater + 1 if equity < peak else 0
        max_underwater = max(max_underwater, underwater)
    exit_days = {row["exit_time_utc"][:10] for row in trades}
    gap = 0
    max_gap = 0
    for row in daily:
        gap = 0 if row["day_utc"] in exit_days else gap + 1
        max_gap = max(max_gap, gap)
    top1 = wins[0] / gp if wins and gp > 0 else None
    top5 = sum(wins[:5], Decimal(0)) / gp if gp > 0 else None
    remaining = nets.copy()
    for winner in wins[:5]:
        remaining.remove(winner)
    rgp = sum((x for x in remaining if x > 0), Decimal(0))
    rgl = sum((-x for x in remaining if x < 0), Decimal(0))
    return {
        "net_usdc": total,
        "trade_count": len(trades),
        "profit_factor": pf,
        "average_trade": total / len(trades) if trades else None,
        "drawdown": draw,
        "underwater_days": max_underwater,
        "top1": top1,
        "top5": top5,
        "net_without_top5": sum(remaining, Decimal(0)),
        "pf_without_top5": rgp / rgl if rgl > 0 else None,
        "friction_share": (
            _dec(payload["totals"]["fees_usdc"])
            + _dec(payload["totals"]["slippage_usdc"])
        )
        / sum((max(_dec(row["gross_usdc"]), Decimal(0)) for row in trades), Decimal(0))
        if trades
        and sum(
            (max(_dec(row["gross_usdc"]), Decimal(0)) for row in trades), Decimal(0)
        )
        > 0
        else None,
        "max_no_trade_gap": max_gap,
    }


def _inner_checks(process: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for origin in process["origins"]:
        decision = origin["selection_decision"]
        if decision["outcome"] == "NO_TRADE":
            rows.append(
                _check(
                    f"inner.origin_{origin['origin_index']:02d}.no_trade_integrity",
                    True,
                    "valid NO_TRADE",
                    "NO_TRADE",
                )
            )
            continue
        selected = decision["selected_candidate"]["canonical_candidate_id"]
        matches = [
            row
            for row in decision["ranking_evidence"]
            if row["canonical_candidate_id"] == selected
        ]
        passed = (
            len(matches) == 1
            and matches[0]["quality_gate_passed"] is True
            and matches[0]["development_dsr_passed"] is True
            and matches[0]["development_pbo_passed"] is True
            and matches[0]["development_beats_cash"] is True
        )
        rows.append(
            _check(
                f"inner.origin_{origin['origin_index']:02d}.all_development_gates",
                passed,
                "quality+DSR+PBO+cash pass",
                matches[0] if len(matches) == 1 else None,
            )
        )
    return rows


def _outer_checks(m):
    return [
        _cmp("outer.trade_count", m["trade_count"], ">=120", lambda x: x >= 120),
        _cmp(
            "outer.profit_factor",
            m["profit_factor"],
            ">=1.25",
            lambda x: x is not None and x >= Decimal("1.25"),
        ),
        _cmp(
            "outer.average_trade",
            m["average_trade"],
            ">0",
            lambda x: x is not None and x > 0,
        ),
        _cmp("outer.drawdown", m["drawdown"], "<=15", lambda x: x <= 15),
        _cmp("outer.underwater", m["underwater_days"], "<=60", lambda x: x <= 60),
        _cmp("outer.net", m["net_usdc"], ">0", lambda x: x > 0),
    ]


def _deployment_checks(p):
    rows = p["deployment_intervals"]
    nets = [_dec(x["net_mtm_usdc"]) for x in rows]
    positive = sum(x > 0 for x in nets)
    active = sum(bool(x["active"]) for x in rows)
    total_positive = sum((max(x, Decimal(0)) for x in nets), Decimal(0))
    share = max(nets) / total_positive if total_positive > 0 else None
    return [
        _cmp("deployment.count", len(rows), "==12", lambda x: x == 12),
        _cmp("deployment.positive", positive, ">=9", lambda x: x >= 9),
        _cmp("deployment.active", active, ">=10", lambda x: x >= 10),
        _cmp("deployment.worst", min(nets), ">=-5", lambda x: x >= -5),
        _cmp(
            "deployment.top_share",
            share,
            "<=0.25",
            lambda x: x is not None and x <= Decimal("0.25"),
        ),
    ]


def _calendar_checks(p, m):
    months = p["calendar_months"]
    quarters = p["calendar_quarters"]
    return [
        _cmp(
            "calendar.positive_month_fraction",
            sum(x["positive"] for x in months) / len(months),
            ">=0.75",
            lambda x: x >= 0.75,
        ),
        _cmp(
            "calendar.active_month_fraction",
            sum(x["active"] for x in months) / len(months),
            ">=0.8333333333333334",
            lambda x: x >= 10 / 12,
        ),
        _cmp(
            "calendar.worst_month",
            min(_dec(x["net_mtm_usdc"]) for x in months),
            ">=-5",
            lambda x: x >= -5,
        ),
        _cmp("calendar.no_trade_gap", m["max_no_trade_gap"], "<=30", lambda x: x <= 30),
        _cmp("calendar.quarter_count", len(quarters), ">=4", lambda x: x >= 4),
        _cmp(
            "calendar.all_quarters_positive",
            all(x["positive"] for x in quarters),
            "true",
            lambda x: x is True,
        ),
        _cmp(
            "calendar.min_quarter_trades",
            min(x["exit_trade_count"] for x in quarters),
            ">=20",
            lambda x: x >= 20,
        ),
    ]


def _concentration_checks(m):
    return [
        _cmp(
            "concentration.top1",
            m["top1"],
            "<=0.10",
            lambda x: x is not None and x <= Decimal(".10"),
        ),
        _cmp(
            "concentration.top5",
            m["top5"],
            "<=0.35",
            lambda x: x is not None and x <= Decimal(".35"),
        ),
        _cmp(
            "concentration.net_without_top5",
            m["net_without_top5"],
            ">0",
            lambda x: x > 0,
        ),
        _cmp(
            "concentration.pf_without_top5",
            m["pf_without_top5"],
            ">=1.05",
            lambda x: x is not None and x >= Decimal("1.05"),
        ),
    ]


def _stress_checks(b, j, s):
    return [
        _cmp("stress.joint_net", j["net_usdc"], ">0", lambda x: x > 0),
        _cmp(
            "stress.joint_pf",
            j["profit_factor"],
            ">=1.10",
            lambda x: x is not None and x >= Decimal("1.10"),
        ),
        _cmp(
            "stress.joint_retention",
            j["net_usdc"] / b["net_usdc"] if b["net_usdc"] > 0 else None,
            ">=0.50",
            lambda x: x is not None and x >= Decimal(".5"),
        ),
        _cmp("stress.joint_drawdown", j["drawdown"], "<=20", lambda x: x <= 20),
        _cmp("stress.slippage_net", s["net_usdc"], ">0", lambda x: x > 0),
        _cmp(
            "stress.slippage_pf",
            s["profit_factor"],
            ">=1.05",
            lambda x: x is not None and x >= Decimal("1.05"),
        ),
        _cmp(
            "stress.baseline_friction_share",
            b["friction_share"],
            "<=0.40",
            lambda x: x is not None and x <= Decimal(".4"),
        ),
    ]


def _regime_checks(value):
    v = dict(_map(value, "regime_evidence"))
    req = {
        "definition",
        "threshold_source",
        "assignment_uses_entry_time_trailing_data_only",
        "regime_count",
        "min_trades_per_regime",
        "positive_regime_count",
        "regimes_pf_at_least_1_05",
        "worst_regime_profit_factor",
        "worst_regime_net_usdc",
        "max_positive_pnl_share",
        "evidence_sha256",
    }
    if set(v) != req:
        return [
            _check("regime.complete", False, "all regime evidence fields", sorted(v))
        ]
    observed = v.pop("evidence_sha256")
    return [
        _check(
            "regime.evidence_digest",
            observed == _digest(v),
            "sha256(canonical evidence)",
            observed,
        ),
        _cmp(
            "regime.definition",
            v["definition"],
            "trend_sign_x_training_median_volatility",
            lambda x: x == "trend_sign_x_training_median_volatility",
        ),
        _cmp(
            "regime.threshold_source",
            v["threshold_source"],
            "training_only",
            lambda x: x == "training_only",
        ),
        _cmp(
            "regime.trailing",
            v["assignment_uses_entry_time_trailing_data_only"],
            "true",
            lambda x: x is True,
        ),
        _cmp("regime.count", v["regime_count"], "==4", lambda x: x == 4),
        _cmp(
            "regime.min_trades", v["min_trades_per_regime"], ">=20", lambda x: x >= 20
        ),
        _cmp("regime.positive", v["positive_regime_count"], ">=3", lambda x: x >= 3),
        _cmp("regime.pf_count", v["regimes_pf_at_least_1_05"], ">=3", lambda x: x >= 3),
        _cmp(
            "regime.worst_pf",
            v["worst_regime_profit_factor"],
            ">=0.90",
            lambda x: _dec(x) >= Decimal(".9"),
        ),
        _cmp(
            "regime.worst_net",
            v["worst_regime_net_usdc"],
            ">=-5",
            lambda x: _dec(x) >= -5,
        ),
        _cmp(
            "regime.concentration",
            v["max_positive_pnl_share"],
            "<=0.60",
            lambda x: _dec(x) <= Decimal(".6"),
        ),
    ]


def _integrity_checks(value):
    v = dict(_map(value, "integrity_evidence"))
    checks = []
    for name in _INTEGRITY_FIELDS:
        row = v.get(name)
        passed = (
            isinstance(row, Mapping)
            and set(row) == {"passed", "evidence_sha256"}
            and row.get("passed") is True
            and _is_sha(row.get("evidence_sha256"))
        )
        checks.append(
            _check(
                f"integrity.{name}",
                passed,
                "true with evidence_sha256",
                row,
            )
        )
    return checks


def _stress_identity_checks(value):
    v = dict(_map(value, "stress_identity_evidence"))
    observed = v.pop("evidence_sha256", None)
    expected = {
        "baseline_fee_bps_per_side": 10,
        "baseline_slippage_bps_per_side": 5,
        "joint_fee_bps_per_side": 15,
        "joint_slippage_bps_per_side": 10,
        "slippage_fee_bps_per_side": 10,
        "slippage_slippage_bps_per_side": 15,
        "same_execution_simulator": True,
    }
    return [
        _check("stress.identity_fields", v == expected, str(expected), v),
        _check(
            "stress.identity_digest",
            observed == _digest(v),
            "sha256(canonical evidence)",
            observed,
        ),
    ]


def _cmp(code, actual, expected, predicate):
    try:
        passed = bool(predicate(actual))
    except (TypeError, ValueError, InvalidOperation, ZeroDivisionError):
        passed = False
    return _check(code, passed, expected, actual)


def _check(code, passed, expected, actual):
    return {
        "code": code,
        "passed": passed,
        "actual": _safe(actual),
        "expected": expected,
    }


def _json_metrics(b, j, s):
    return {
        "baseline": {k: _safe(v) for k, v in b.items()},
        "joint_stress": {k: _safe(v) for k, v in j.items()},
        "slippage_stress": {k: _safe(v) for k, v in s.items()},
    }


def _safe(v):
    if isinstance(v, Decimal):
        return _text(v)
    if isinstance(v, (str, int, bool)) or v is None:
        return v
    if isinstance(v, float):
        return v
    return str(v)


def _map(v, label):
    if not isinstance(v, Mapping):
        raise MonthlyQualityGateError(f"{label} must be an object")
    return v


def _dec(v):
    if isinstance(v, bool):
        raise MonthlyQualityGateError("numeric value cannot be boolean")
    try:
        x = Decimal(str(v))
    except (InvalidOperation, ValueError) as exc:
        raise MonthlyQualityGateError("numeric value is invalid") from exc
    if not x.is_finite():
        raise MonthlyQualityGateError("numeric value must be finite")
    return x


def _text(v):
    return "0" if v == 0 else format(v.normalize(), "f")


def _canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(v):
    return hashlib.sha256(_canonical(v).encode()).hexdigest()


def _sha(v):
    if (
        not isinstance(v, str)
        or len(v) != 64
        or any(c not in "0123456789abcdef" for c in v)
    ):
        raise MonthlyQualityGateError("digest must be sha256")
    return v


def _is_sha(v):
    return (
        isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)
    )


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "REPORT_SCHEMA_VERSION",
    "GREEN",
    "YELLOW",
    "RED",
    "MonthlyQualityGateError",
    "MonthlyQualityGateReport",
    "evaluate_monthly_quality_gate",
    "load_monthly_quality_gate_contract",
    "validate_monthly_quality_gate_report",
]
