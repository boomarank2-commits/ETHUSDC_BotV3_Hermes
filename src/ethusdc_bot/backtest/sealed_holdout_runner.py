"""One-shot evaluator for a frozen Protocol-v2 sealed holdout.

This module is deliberately separate from the research loop.  It accepts only
an already-frozen production report, claims that exact report before touching
the sealed candles, evaluates the frozen candidate once, and emits the strict
``final_evaluation`` document consumed by :mod:`ethusdc_bot.shadow.adoption`.

There is no Binance account access, order path, or live-trading capability in
this runner.  A claim survives every failure after it is created: an operator
must never retry a viewed holdout after a crash or partial evaluation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from ethusdc_bot.backtest.data_loader import (
    Candle,
    EXPECTED_STEP_MS,
    load_ethusdc_1m_candles,
)
from ethusdc_bot.backtest.quality_gates import (
    QUALITY_GATE_V1,
    evaluate_quality_gates,
)
from ethusdc_bot.backtest.research_protocol import (
    CANDIDATE_STAGE_BUDGETS,
    CONSUMED_AUDIT_WINDOWS,
    STRATEGY_FAMILIES,
    safety_status,
    validate_research_protocol,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy
from ethusdc_bot.shadow.adoption import (
    FINAL_REPORT_KEYS,
    validate_final_evaluation_report,
)
from ethusdc_bot.shadow.schema import CANDIDATE_KEYS, canonical_signature_payload
from ethusdc_bot.shadow.store import canonical_json_bytes


HOLDOUT_DAYS = 365
EXPECTED_CANDLES_PER_DAY = 1_440
BASELINE_TRADE_USDC = 100.0
BASELINE_FEE_RATE = 0.001
BASELINE_SLIPPAGE_BPS = 5.0

_SOURCE_REPORT_KEYS = {
    "schema_version",
    "loop_run_id",
    "timestamp",
    "git_commit",
    "raw_root",
    "execution_profile",
    "fixture_data_only",
    "max_cycles",
    "cycles_executed",
    "stop_reason",
    "target_reached",
    "target_status",
    "target_usdc_per_day",
    "best_candidate",
    "best_validation_result",
    "frozen_candidate",
    "freeze_status",
    "candidate_stage_totals",
    "resource_budget",
    "loop_resource_budget",
    "cycles",
    "window_plan",
    "audit_policy",
    "quality_gate_version",
    "research_protocol",
    "all_report_paths",
    "safety",
    "safety_status",
    "result_text",
}
_PROTOCOL_KEYS = {
    "schema_version",
    "run_id",
    "created_at",
    "git_commit",
    "raw_root",
    "data_window",
    "dynamic_window_policy",
    "candidate_stage_budgets",
    "selection_data",
    "consumed_audit_policy",
    "strategy_families",
    "parameter_space",
    "ranking_rules",
    "required_report_paths",
    "safety",
}
_HOLDOUT_WINDOW_KEYS = {
    "start",
    "end",
    "days",
    "status",
    "consumed_audit_window",
    "evaluated",
}
_AUDIT_POLICY_KEYS = {
    "consumed_audit_window",
    "evaluated_in_research_loop",
    "affects_selection",
    "allowed_uses",
    "freeze_eligible",
    "freeze_blocker",
}
_FINALIST_SUMMARY_KEYS = {
    "candidate_id",
    "family",
    "walk_forward_summary",
    "historical_replay_summary",
    "quality_gate_evidence",
    "quality_gate",
}


class SealedHoldoutError(ValueError):
    """Raised when a sealed-holdout input or result fails closed."""


class SealedHoldoutAlreadyClaimedError(SealedHoldoutError):
    """Raised when the exact source report has already been claimed."""


@dataclass(frozen=True)
class SealedHoldoutRunResult:
    """Paths and immutable identities produced by one successful evaluation."""

    final_report: dict[str, Any]
    final_report_path: Path
    registry_path: Path
    source_report_sha256: str
    claim_identity_sha256: str


@dataclass(frozen=True)
class _FrozenSource:
    report: dict[str, Any]
    candidate: dict[str, Any]
    selection_evidence: dict[str, Any]
    holdout_start: date
    holdout_end: date


def run_sealed_holdout(
    frozen_research_report_path: str | Path,
    raw_root: str | Path,
    reports_root: str | Path,
) -> SealedHoldoutRunResult:
    """Evaluate one frozen ETHUSDC candidate on one sealed 365-day window.

    Validation of the source report is completed before a claim is written.
    The claim itself is created with ``O_EXCL`` before any candle loader or
    simulator call.  It is never removed, including when loading or simulation
    fails, so a viewed holdout cannot be retried.
    """

    source_path = Path(frozen_research_report_path)
    source_bytes = _read_source_bytes(source_path)
    source_sha256 = sha256(source_bytes).hexdigest()
    source_report = _parse_strict_json_object(source_bytes)
    frozen = _validate_frozen_source(source_report, raw_root=Path(raw_root))
    claim_identity = _claim_identity(frozen)
    claim_identity_sha256 = sha256(canonical_json_bytes(claim_identity)).hexdigest()

    root = Path(reports_root)
    registry_dir = root / "sealed_holdout_registry"
    final_dir = root / "sealed_holdout_final"
    registry_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    registry_path = registry_dir / f"{claim_identity_sha256}.json"
    final_report_path = final_dir / f"final_{claim_identity_sha256}.json"
    claimed_at = _utc_now()
    claim = {
        "schema_version": 1,
        "status": "claimed",
        "claim_identity": claim_identity,
        "claim_identity_sha256": claim_identity_sha256,
        "source_report_path": str(source_path.resolve()),
        "source_report_sha256": source_sha256,
        "source_research_run_id": frozen.report["loop_run_id"],
        "candidate_id": frozen.candidate["candidate_id"],
        "holdout_start": frozen.holdout_start.isoformat(),
        "holdout_end": frozen.holdout_end.isoformat(),
        "claimed_at_utc": claimed_at,
        "completed_at_utc": None,
        "final_report_path": None,
        "final_report_sha256": None,
    }
    _create_claim_exclusive(registry_path, claim)

    candles = load_ethusdc_1m_candles(
        raw_root,
        start_day=frozen.holdout_start,
        end_day=frozen.holdout_end,
    )
    _validate_exact_candle_window(
        candles,
        start_day=frozen.holdout_start,
        end_day=frozen.holdout_end,
    )

    candidate = StrategyCandidate(
        family=str(frozen.candidate["family"]),
        params=dict(frozen.candidate["params"]),
    )
    simulation = simulate_strategy(
        candles,
        candidate,
        days=HOLDOUT_DAYS,
        trade_usdc=BASELINE_TRADE_USDC,
        fee_rate=BASELINE_FEE_RATE,
        slippage_bps=BASELINE_SLIPPAGE_BPS,
        training_days=0,
        blindtest_days=HOLDOUT_DAYS,
    )

    final_evidence = _deep_json_copy(frozen.selection_evidence)
    final_evidence["final"] = _final_metrics(simulation)
    final_gate = evaluate_quality_gates(final_evidence, stage="final").to_dict()
    created_at = _utc_now()
    final_report = {
        "schema_version": 1,
        "report_type": "final_evaluation",
        "final_evaluation_id": f"final_{claim_identity_sha256[:24]}",
        "created_at_utc": created_at,
        "git_commit": frozen.report["git_commit"],
        "source_research_run_id": frozen.report["loop_run_id"],
        "candidate": {
            "candidate_id": frozen.candidate["candidate_id"],
            "family": frozen.candidate["family"],
            "params": _deep_json_copy(frozen.candidate["params"]),
            "candidate_signature": canonical_signature_payload(
                str(frozen.candidate["family"]), frozen.candidate["params"]
            ),
        },
        "quality_gate_evidence": final_evidence,
        "quality_gate": final_gate,
        "safety": safety_status(),
    }
    if set(final_report) != FINAL_REPORT_KEYS:
        raise SealedHoldoutError("internal final report schema does not match Shadow adoption")
    try:
        validate_final_evaluation_report(final_report)
    except ValueError as exc:
        raise SealedHoldoutError(f"final report failed the Shadow adoption schema: {exc}") from exc
    _write_json_atomic(final_report_path, final_report, replace=False)
    final_bytes = final_report_path.read_bytes()

    completed_at = _utc_now()
    completed = {
        **claim,
        "status": "completed",
        "completed_at_utc": completed_at,
        "final_report_path": str(final_report_path.resolve()),
        "final_report_sha256": sha256(final_bytes).hexdigest(),
    }
    _write_json_atomic(registry_path, completed, replace=True)
    return SealedHoldoutRunResult(
        final_report=final_report,
        final_report_path=final_report_path,
        registry_path=registry_path,
        source_report_sha256=source_sha256,
        claim_identity_sha256=claim_identity_sha256,
    )


def _claim_identity(frozen: _FrozenSource) -> dict[str, Any]:
    """Return a formatting-independent identity for the irreversible run.

    Byte-level source hashing remains provenance, but must not define one-shot
    semantics: re-indenting or reordering the same JSON object changes bytes.
    This identity deliberately excludes the source path, JSON formatting, and
    candidate display ID so those cannot be used to bypass a prior claim.
    """

    return {
        "schema_version": 1,
        "source_research_run_id": frozen.report["loop_run_id"],
        "candidate_signature": canonical_signature_payload(
            str(frozen.candidate["family"]), frozen.candidate["params"]
        ),
        "holdout_start": frozen.holdout_start.isoformat(),
        "holdout_end": frozen.holdout_end.isoformat(),
        "quality_gate_version": frozen.report["quality_gate_version"],
    }


def _read_source_bytes(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SealedHoldoutError(f"frozen research report cannot be read: {exc}") from exc
    if not raw:
        raise SealedHoldoutError("frozen research report is empty")
    return raw


def _parse_strict_json_object(raw: bytes) -> dict[str, Any]:
    def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SealedHoldoutError(f"duplicate JSON key is forbidden: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise SealedHoldoutError(f"non-finite JSON constant is forbidden: {value}")

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SealedHoldoutError(f"frozen research report is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SealedHoldoutError("frozen research report must contain one JSON object")
    return value


def _validate_frozen_source(report: dict[str, Any], *, raw_root: Path) -> _FrozenSource:
    _exact_keys(report, _SOURCE_REPORT_KEYS, "research_report")
    _literal(report, "schema_version", 2, "research_report")
    _literal(report, "execution_profile", "production_protocol", "research_report")
    _literal(report, "fixture_data_only", False, "research_report")
    _literal(
        report,
        "freeze_status",
        "frozen_for_separate_sealed_holdout",
        "research_report",
    )
    _literal(report, "safety_status", "ok", "research_report")
    _literal(report, "quality_gate_version", QUALITY_GATE_V1.version, "research_report")
    _require_non_empty_string(report.get("loop_run_id"), "research_report.loop_run_id")
    _require_non_empty_string(report.get("git_commit"), "research_report.git_commit")
    _require_utc_timestamp(report.get("timestamp"), "research_report.timestamp")
    if not _json_identical(report.get("safety"), safety_status()):
        raise SealedHoldoutError("research_report.safety is not canonical")

    try:
        reported_raw_root = Path(_require_non_empty_string(
            report.get("raw_root"), "research_report.raw_root"
        )).resolve()
        supplied_raw_root = raw_root.resolve()
    except OSError as exc:
        raise SealedHoldoutError(f"raw_root cannot be resolved: {exc}") from exc
    if reported_raw_root != supplied_raw_root:
        raise SealedHoldoutError("supplied raw_root does not match the frozen research report")

    protocol = _require_mapping(report.get("research_protocol"), "research_report.research_protocol")
    _exact_keys(protocol, _PROTOCOL_KEYS, "research_report.research_protocol")
    validation = validate_research_protocol(dict(protocol))
    if validation.get("valid") is not True:
        raise SealedHoldoutError(
            "research_report.research_protocol is not canonical: "
            + "; ".join(str(item) for item in validation.get("errors", []))
        )
    if not _json_identical(protocol.get("candidate_stage_budgets"), dict(CANDIDATE_STAGE_BUDGETS)):
        raise SealedHoldoutError("research protocol must use the canonical production stage budgets")
    for protocol_key, report_key in (
        ("run_id", "loop_run_id"),
        ("git_commit", "git_commit"),
        ("raw_root", "raw_root"),
    ):
        if protocol.get(protocol_key) != report.get(report_key):
            raise SealedHoldoutError(
                f"research protocol {protocol_key} is not bound to research_report.{report_key}"
            )
    if not _json_identical(protocol.get("safety"), safety_status()):
        raise SealedHoldoutError("research protocol safety is not canonical")
    if not _json_identical(protocol.get("data_window"), report.get("window_plan")):
        raise SealedHoldoutError("research protocol data_window is not bound to window_plan")

    window_plan = _require_mapping(report.get("window_plan"), "research_report.window_plan")
    holdout = _require_mapping(
        window_plan.get("final_holdout_window"),
        "research_report.window_plan.final_holdout_window",
    )
    start_day, end_day = _validate_holdout_window(holdout)

    audit_policy = _require_mapping(report.get("audit_policy"), "research_report.audit_policy")
    _exact_keys(audit_policy, _AUDIT_POLICY_KEYS, "research_report.audit_policy")
    expected_audit = {
        "consumed_audit_window": False,
        "evaluated_in_research_loop": False,
        "affects_selection": False,
        "allowed_uses": ["historical_reference", "defect_analysis"],
        "freeze_eligible": True,
        "freeze_blocker": None,
    }
    if not _json_identical(audit_policy, expected_audit):
        raise SealedHoldoutError("research_report.audit_policy is not freeze-eligible")

    cycles = report.get("cycles")
    if not isinstance(cycles, list) or not cycles:
        raise SealedHoldoutError("research_report.cycles must be a non-empty list")
    if type(report.get("cycles_executed")) is not int or report["cycles_executed"] != len(cycles):
        raise SealedHoldoutError("research_report.cycles_executed must match cycles")
    if type(report.get("max_cycles")) is not int or not 1 <= report["max_cycles"] <= 8:
        raise SealedHoldoutError("research_report.max_cycles must be an integer in 1..8")
    if len(cycles) > report["max_cycles"]:
        raise SealedHoldoutError("research_report cycles exceed max_cycles")

    frozen_candidate = _validate_source_candidate(
        report.get("frozen_candidate"), "research_report.frozen_candidate"
    )
    eligible: list[tuple[tuple[float, ...], dict[str, Any], dict[str, Any]]] = []
    for index, value in enumerate(cycles):
        cycle_path = f"research_report.cycles[{index}]"
        cycle = _require_mapping(value, cycle_path)
        if not _json_identical(cycle.get("safety"), safety_status()):
            raise SealedHoldoutError(f"{cycle_path}.safety is not canonical")
        cycle_window = _require_mapping(cycle.get("window_plan"), f"{cycle_path}.window_plan")
        if not _json_identical(cycle_window.get("final_holdout_window"), holdout):
            raise SealedHoldoutError(f"{cycle_path} is not bound to the sealed holdout window")
        selected, evidence = _validate_cycle_selection(cycle, cycle_path)
        gate = cycle["quality_gate"]
        if gate.get("passed") is True:
            eligible.append((_selection_rank(cycle, cycle_path), selected, evidence))
    if not eligible:
        raise SealedHoldoutError("research report has no freshly verified passing finalist")
    _, selected_candidate, selection_evidence = max(eligible, key=lambda item: item[0])
    if not _json_identical(frozen_candidate, selected_candidate):
        raise SealedHoldoutError("frozen_candidate is not the highest-ranked passing selected finalist")
    if "final" in selection_evidence:
        raise SealedHoldoutError("selection quality-gate evidence already contains final evidence")
    return _FrozenSource(
        report=report,
        candidate=selected_candidate,
        selection_evidence=selection_evidence,
        holdout_start=start_day,
        holdout_end=end_day,
    )


def _validate_cycle_selection(
    cycle: Mapping[str, Any], path: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    selected = _validate_source_candidate(cycle.get("selected_candidate"), f"{path}.selected_candidate")
    stage_ids = _require_mapping(cycle.get("candidate_stage_ids"), f"{path}.candidate_stage_ids")
    finalists = stage_ids.get("finalists")
    if not isinstance(finalists, list) or any(not isinstance(item, str) for item in finalists):
        raise SealedHoldoutError(f"{path}.candidate_stage_ids.finalists must be a string list")
    if selected["candidate_id"] not in finalists:
        raise SealedHoldoutError(f"{path}.selected_candidate is not a finalist")

    evidence_value = cycle.get("quality_gate_evidence")
    if not isinstance(evidence_value, dict):
        raise SealedHoldoutError(f"{path}.quality_gate_evidence must be an object")
    evidence = _deep_json_copy(evidence_value)
    recomputed = evaluate_quality_gates(evidence, stage="selection").to_dict()
    recomputed["candidate_id"] = selected["candidate_id"]
    recomputed["candidate_signature"] = selected["candidate_signature"]
    if not _json_identical(cycle.get("quality_gate"), recomputed):
        raise SealedHoldoutError(f"{path}.quality_gate does not match a fresh selection evaluation")

    summaries = cycle.get("finalist_summaries")
    if not isinstance(summaries, list):
        raise SealedHoldoutError(f"{path}.finalist_summaries must be a list")
    summary_ids = [
        item.get("candidate_id") for item in summaries if isinstance(item, Mapping)
    ]
    if summary_ids != finalists or len(summaries) != len(finalists):
        raise SealedHoldoutError(f"{path}.finalist_summaries must exactly follow finalist ids")
    selected_summaries = [
        item
        for item in summaries
        if isinstance(item, Mapping) and item.get("candidate_id") == selected["candidate_id"]
    ]
    if len(selected_summaries) != 1:
        raise SealedHoldoutError(f"{path} must contain exactly one selected finalist summary")
    summary = selected_summaries[0]
    _exact_keys(summary, _FINALIST_SUMMARY_KEYS, f"{path}.selected_finalist_summary")
    if summary.get("family") != selected["family"]:
        raise SealedHoldoutError(f"{path}.selected finalist family is not bound")
    if not _json_identical(summary.get("quality_gate_evidence"), evidence):
        raise SealedHoldoutError(f"{path}.selected finalist evidence is not bound")
    if not _json_identical(summary.get("quality_gate"), recomputed):
        raise SealedHoldoutError(f"{path}.selected finalist gate is not bound")
    return selected, evidence


def _validate_source_candidate(value: object, path: str) -> dict[str, Any]:
    candidate = _require_mapping(value, path)
    _exact_keys(candidate, CANDIDATE_KEYS, path)
    candidate_id = _require_non_empty_string(candidate.get("candidate_id"), f"{path}.candidate_id")
    family = _require_non_empty_string(candidate.get("family"), f"{path}.family")
    if family not in STRATEGY_FAMILIES:
        raise SealedHoldoutError(f"{path}.family is not a canonical research strategy family")
    params_value = _require_mapping(candidate.get("params"), f"{path}.params")
    params: dict[str, float | int | str] = {}
    for key, value in params_value.items():
        if not isinstance(key, str) or not key:
            raise SealedHoldoutError(f"{path}.params keys must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise SealedHoldoutError(f"{path}.params.{key} has an unsupported type")
        if isinstance(value, float) and not isfinite(value):
            raise SealedHoldoutError(f"{path}.params.{key} must be finite")
        params[key] = value
    if params.get("symbol", "ETHUSDC") != "ETHUSDC":
        raise SealedHoldoutError(f"{path} must trade ETHUSDC")
    if params.get("side", "LONG") != "LONG":
        raise SealedHoldoutError(f"{path} must be LONG-only")
    expected_signature = _research_signature(family, params)
    if candidate.get("candidate_signature") != expected_signature:
        raise SealedHoldoutError(f"{path}.candidate_signature is not canonical")
    return {
        "candidate_id": candidate_id,
        "family": family,
        "params": params,
        "candidate_signature": expected_signature,
    }


def _selection_rank(cycle: Mapping[str, Any], path: str) -> tuple[float, ...]:
    score = _require_mapping(cycle.get("selected_candidate_score"), f"{path}.selected_candidate_score")
    selected = cycle["selected_candidate"]
    if score.get("candidate_id") != selected["candidate_id"]:
        raise SealedHoldoutError(f"{path}.selected_candidate_score candidate is not bound")
    if score.get("candidate_signature") != selected["candidate_signature"]:
        raise SealedHoldoutError(f"{path}.selected_candidate_score signature is not bound")
    if score.get("quality_gate_passed") is not cycle["quality_gate"].get("passed"):
        raise SealedHoldoutError(f"{path}.selected_candidate_score gate status is not bound")
    if score.get("ranking_rule") != "quality_gate_then_wfv_aggregate_pf_drawdown_then_fold_tiebreakers":
        raise SealedHoldoutError(f"{path}.selected_candidate_score ranking rule is not canonical")
    fields = (
        "wfv_net_usdc_per_day",
        "wfv_profit_factor",
        "wfv_max_drawdown_usdc",
        "worst_fold_net_usdc_per_day",
        "positive_fold_count",
        "validation_net_usdc_per_day",
        "wfv_cost_load",
    )
    numbers: list[float] = []
    for field in fields:
        value = score.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise SealedHoldoutError(f"{path}.selected_candidate_score.{field} must be finite")
        numbers.append(float(value))
    if numbers[2] < 0 or numbers[4] < 0 or numbers[6] < 0:
        raise SealedHoldoutError(f"{path}.selected_candidate_score contains an invalid non-negative metric")
    return (
        1.0 if score["quality_gate_passed"] is True else 0.0,
        numbers[0],
        numbers[1],
        -numbers[2],
        numbers[3],
        numbers[4],
        numbers[5],
        -numbers[6],
    )


def _validate_holdout_window(holdout: Mapping[str, Any]) -> tuple[date, date]:
    path = "research_report.window_plan.final_holdout_window"
    _exact_keys(holdout, _HOLDOUT_WINDOW_KEYS, path)
    _literal(holdout, "days", HOLDOUT_DAYS, path)
    _literal(holdout, "status", "sealed_unopened", path)
    _literal(holdout, "consumed_audit_window", False, path)
    _literal(holdout, "evaluated", False, path)
    try:
        start_day = date.fromisoformat(_require_non_empty_string(holdout.get("start"), f"{path}.start"))
        end_day = date.fromisoformat(_require_non_empty_string(holdout.get("end"), f"{path}.end"))
    except ValueError as exc:
        raise SealedHoldoutError(f"{path} start/end must be ISO calendar days") from exc
    if end_day - start_day != timedelta(days=HOLDOUT_DAYS - 1):
        raise SealedHoldoutError(f"{path} must span exactly {HOLDOUT_DAYS} inclusive UTC days")
    for consumed in CONSUMED_AUDIT_WINDOWS:
        consumed_start = date.fromisoformat(str(consumed["start"]))
        consumed_end = date.fromisoformat(str(consumed["end"]))
        if not (end_day < consumed_start or start_day > consumed_end):
            raise SealedHoldoutError(
                f"{path} overlaps the immutable consumed-audit ledger"
            )
    return start_day, end_day


def _validate_exact_candle_window(
    candles: list[Candle], *, start_day: date, end_day: date
) -> None:
    expected_count = HOLDOUT_DAYS * EXPECTED_CANDLES_PER_DAY
    if len(candles) != expected_count:
        raise SealedHoldoutError(
            f"sealed holdout must contain exactly {expected_count} candles, got {len(candles)}"
        )
    start_ms = int(datetime.combine(start_day, datetime.min.time(), tzinfo=UTC).timestamp() * 1000)
    end_exclusive_ms = int(
        datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=UTC).timestamp()
        * 1000
    )
    if candles[0].open_time != start_ms:
        raise SealedHoldoutError("sealed candles do not start at 00:00 UTC on the sealed start day")
    if candles[-1].open_time != end_exclusive_ms - EXPECTED_STEP_MS:
        raise SealedHoldoutError("sealed candles do not end at 23:59 UTC on the sealed end day")
    per_day: dict[date, int] = {}
    previous: int | None = None
    for candle in candles:
        if candle.open_time < start_ms or candle.open_time >= end_exclusive_ms:
            raise SealedHoldoutError("candle outside the sealed UTC range is forbidden")
        if previous is not None and candle.open_time - previous != EXPECTED_STEP_MS:
            raise SealedHoldoutError("sealed holdout candles must be gapless 1m data")
        day = datetime.fromtimestamp(candle.open_time / 1000, tz=UTC).date()
        per_day[day] = per_day.get(day, 0) + 1
        previous = candle.open_time
    expected_days = {start_day + timedelta(days=index) for index in range(HOLDOUT_DAYS)}
    if set(per_day) != expected_days or any(
        per_day[day] != EXPECTED_CANDLES_PER_DAY for day in expected_days
    ):
        raise SealedHoldoutError("every sealed UTC day must contain exactly 1440 one-minute candles")


def _final_metrics(simulation: Any) -> dict[str, Any]:
    metrics = simulation.metrics
    if simulation.drawdown_method != "mark_to_market":
        raise SealedHoldoutError("final simulation must provide mark-to-market drawdown")
    values = {
        "sealed_holdout_evaluations": 1,
        "trade_count": metrics.trade_count,
        "net_usdc_per_day": metrics.net_usdc_per_day,
        "profit_factor": metrics.profit_factor,
        "average_trade_usdc": metrics.average_trade_usdc,
        "max_drawdown_usdc": metrics.max_drawdown_usdc,
        "drawdown_method": simulation.drawdown_method,
    }
    for key in {
        "trade_count",
        "net_usdc_per_day",
        "average_trade_usdc",
        "max_drawdown_usdc",
    }:
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
            raise SealedHoldoutError(f"final metric {key} must be finite")
    profit_factor = values["profit_factor"]
    if isinstance(profit_factor, bool) or not isinstance(profit_factor, (int, float)):
        raise SealedHoldoutError("final metric profit_factor must be numeric")
    if not isfinite(float(profit_factor)):
        # Strict JSON and the quality gate both fail closed on an undefined or
        # infinite PF.  Preserve the diagnostic without inventing a number.
        values["profit_factor"] = "inf" if float(profit_factor) > 0 else "-inf"
    return values


def _create_claim_exclusive(path: Path, claim: Mapping[str, Any]) -> None:
    payload = _json_document_bytes(claim)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise SealedHoldoutAlreadyClaimedError(
            f"sealed holdout source report already claimed: {path.name}"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        # Never remove a claim.  A partial/crashed claim remains a permanent
        # fail-closed marker and therefore cannot permit another evaluation.
        raise


def _write_json_atomic(path: Path, value: Mapping[str, Any], *, replace: bool) -> None:
    payload = _json_document_bytes(value)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if not replace and path.exists():
            raise FileExistsError(f"final report path already exists: {path}")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _json_document_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SealedHoldoutError(f"value is not strict JSON: {exc}") from exc


def _deep_json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise SealedHoldoutError(f"embedded evidence is not strict JSON: {exc}") from exc


def _research_signature(family: str, params: Mapping[str, float | int | str]) -> str:
    normalized = dict(params)
    normalized.setdefault("symbol", "ETHUSDC")
    try:
        return json.dumps(
            {"family": family, "params": normalized},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SealedHoldoutError(f"candidate identity is not strict JSON: {exc}") from exc


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        raise SealedHoldoutError(
            f"{path} keys are invalid; missing={sorted(missing)} extra={sorted(extra)}"
        )


def _literal(value: Mapping[str, Any], key: str, expected: object, path: str) -> None:
    actual = value.get(key)
    if actual != expected or type(actual) is not type(expected):
        raise SealedHoldoutError(f"{path}.{key} must be {expected!r}")


def _require_mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SealedHoldoutError(f"{path} must be an object")
    return value


def _require_non_empty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SealedHoldoutError(f"{path} must be a non-empty string")
    return value


def _require_utc_timestamp(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SealedHoldoutError(f"{path} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise SealedHoldoutError(f"{path} is not a valid timestamp") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise SealedHoldoutError(f"{path} must be UTC")


def _json_identical(left: object, right: object) -> bool:
    try:
        return canonical_json_bytes(left) == canonical_json_bytes(right)
    except (TypeError, ValueError):
        return False


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
