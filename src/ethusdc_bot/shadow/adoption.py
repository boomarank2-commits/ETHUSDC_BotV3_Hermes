"""Fail-closed adoption of one verified final evaluation into Shadow mode.

Expected ``final_evaluation`` report schema version 1::

    {
      "schema_version": 1,
      "report_type": "final_evaluation",
      "final_evaluation_id": "final_...",
      "created_at_utc": "...Z",
      "git_commit": "...",
      "source_research_run_id": "research_loop_...",
      "candidate": {
        "candidate_id": "...",
        "family": "...",
        "params": {"symbol": "ETHUSDC", ...},
        "candidate_signature": {
          "family": "...",
          "params": [["key", "value"], ...]
        }
      },
      "quality_gate_evidence": {"protocol": {...}, ..., "final": {...}},
      "quality_gate": { ... evaluate_quality_gates(evidence, stage="final") ... },
      "safety": { ... research_protocol.safety_status() ... }
    }

Unknown fields fail closed. The stored gate is never trusted: it must exactly
match a fresh evaluation of the embedded evidence. Candidate identity is bound
to the canonical signature used by the research loop. A yellow result is
eligible only when ``final.target`` is the sole failed check and final net/day
is positive. Neither green nor yellow enables live trading.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
import shutil
from typing import Any, Literal
from uuid import uuid4

from ethusdc_bot.backtest.quality_gates import evaluate_quality_gates
from ethusdc_bot.backtest.research_protocol import safety_status
from ethusdc_bot.portfolio import PortfolioPolicy, canonical_portfolio_signature
from ethusdc_bot.shadow.schema import (
    CANDIDATE_KEYS,
    canonical_signature_payload,
    shadow_safety_status,
    validate_shadow_deployment,
    validate_shadow_state,
)
from ethusdc_bot.shadow.store import (
    append_event,
    canonical_json_bytes,
    utc_now,
    write_deployment_atomic,
    write_state_atomic,
)


ResultColor = Literal["green", "yellow", "red"]
FINAL_REPORT_KEYS = {
    "schema_version",
    "report_type",
    "final_evaluation_id",
    "created_at_utc",
    "git_commit",
    "source_research_run_id",
    "candidate",
    "quality_gate_evidence",
    "quality_gate",
    "safety",
}
SAFE_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class ShadowAdoptionError(ValueError):
    """Raised when a report or budget is not eligible for Shadow adoption."""


@dataclass(frozen=True)
class AdoptionAssessment:
    color: ResultColor
    shadow_eligible: bool
    target_reached: bool
    live_eligible: bool
    reason_codes: tuple[str, ...]
    final_evaluation_id: str | None = None
    candidate_id: str | None = None
    candidate_signature: dict[str, Any] | None = None
    final_net_usdc_per_day: float | None = None
    report_sha256: str | None = None
    recomputed_quality_gate: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "color": self.color,
            "shadow_eligible": self.shadow_eligible,
            "target_reached": self.target_reached,
            "live_eligible": False,
            "reason_codes": list(self.reason_codes),
            "final_evaluation_id": self.final_evaluation_id,
            "candidate_id": self.candidate_id,
            "candidate_signature": self.candidate_signature,
            "final_net_usdc_per_day": self.final_net_usdc_per_day,
            "report_sha256": self.report_sha256,
            "recomputed_quality_gate": self.recomputed_quality_gate,
        }


@dataclass(frozen=True)
class ShadowAdoptionResult:
    deployment: dict[str, Any]
    state: dict[str, Any]
    deployment_dir: Path
    deployment_path: Path
    state_path: Path
    events_path: Path


def assess_final_report(path: str | Path) -> AdoptionAssessment:
    """Return green/yellow/red after strict parsing and fresh gate evaluation."""

    try:
        _, _, assessment = _read_and_assess(Path(path))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ShadowAdoptionError, ValueError):
        return _red("invalid_final_evaluation_report")
    return assessment


def adopt_for_shadow(
    final_report_path: str | Path,
    deployment_budget_usdc: int,
    state_root: str | Path,
) -> ShadowAdoptionResult:
    """Create an immutable, order-free Shadow deployment below ``state_root``.

    The source report is read once, hashed, fully validated, and re-evaluated.
    Files are assembled in a private directory and the completed directory is
    renamed into place so observers never see a half-created deployment.
    """

    if type(deployment_budget_usdc) is not int:
        raise ShadowAdoptionError("deployment_budget_usdc must be an integer")
    try:
        portfolio_policy = PortfolioPolicy(
            deployment_budget_usdc=deployment_budget_usdc
        )
    except (TypeError, ValueError) as exc:
        raise ShadowAdoptionError(str(exc)) from exc

    source_path = Path(final_report_path)
    report_bytes, report, assessment = _read_and_assess(source_path)
    if not assessment.shadow_eligible or assessment.color == "red":
        raise ShadowAdoptionError(
            "final evaluation is not Shadow-eligible: " + ",".join(assessment.reason_codes)
        )

    created_at = utc_now()
    final_id = str(report["final_evaluation_id"])
    safe_final_id = SAFE_IDENTIFIER_RE.sub("_", final_id).strip("._-") or "final"
    deployment_id = f"shadow_{safe_final_id}_{uuid4().hex[:12]}"
    candidate = json.loads(json.dumps(report["candidate"], allow_nan=False))
    deployment = {
        "schema_version": 1,
        "deployment_id": deployment_id,
        "created_at_utc": created_at,
        "mode": "public_data_shadow",
        "status": "adopted",
        "source_report": {
            "path": str(source_path.resolve()),
            "sha256": sha256(report_bytes).hexdigest(),
            "final_evaluation_id": final_id,
            "source_research_run_id": report["source_research_run_id"],
            "git_commit": report["git_commit"],
        },
        "candidate": candidate,
        "portfolio_policy": {
            "policy": portfolio_policy.to_dict(),
            "canonical_signature": canonical_portfolio_signature(portfolio_policy),
        },
        "cost_model": {
            "fee_rate_per_side": 0.001,
            "fee_bps_per_side": 10.0,
            "slippage_bps_per_side": 5.0,
        },
        "assessment": {
            "color": assessment.color,
            "shadow_eligible": True,
            "target_reached": assessment.target_reached,
            "live_eligible": False,
            "reason_codes": list(assessment.reason_codes),
        },
        "safety": shadow_safety_status(),
    }
    validate_shadow_deployment(deployment)

    root = Path(state_root)
    root.mkdir(parents=True, exist_ok=True)
    final_dir = root / deployment_id
    temporary_dir = root / f".{deployment_id}.tmp"
    if final_dir.exists() or temporary_dir.exists():
        raise FileExistsError(f"Shadow deployment path already exists: {final_dir}")
    temporary_dir.mkdir()
    try:
        temporary_deployment_path = temporary_dir / "deployment.json"
        temporary_events_path = temporary_dir / "events.jsonl"
        temporary_state_path = temporary_dir / "state.json"
        write_deployment_atomic(temporary_deployment_path, deployment)
        event = append_event(
            temporary_events_path,
            "deployment_adopted",
            {
                "deployment_id": deployment_id,
                "final_evaluation_id": final_id,
                "source_report_sha256": deployment["source_report"]["sha256"],
                "candidate_id": candidate["candidate_id"],
                "candidate_signature": candidate["candidate_signature"],
                "assessment_color": assessment.color,
                "deployment_budget_usdc": deployment_budget_usdc,
                "lot_notional_usdc": 100,
                "orders_enabled": False,
                "trading_api_enabled": False,
                "api_keys_used": False,
            },
            timestamp_utc=created_at,
        )
        state = {
            "schema_version": 1,
            "deployment_id": deployment_id,
            "phase": "adopted_stopped",
            "created_at_utc": created_at,
            "updated_at_utc": created_at,
            "deployment_budget_usdc": deployment_budget_usdc,
            "lot_notional_usdc": portfolio_policy.lot_notional_usdc,
            "max_open_lots": portfolio_policy.max_concurrent_lots,
            "last_processed_candle_open_time_ms": None,
            "open_lots": [],
            "realized_net_usdc": 0.0,
            "unrealized_net_usdc": 0.0,
            "event_count": 1,
            "last_event_hash": event["event_hash"],
            "error": None,
            "safety": shadow_safety_status(),
        }
        validate_shadow_state(state)
        write_state_atomic(temporary_state_path, state)
        temporary_dir.rename(final_dir)
    except Exception:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)
        raise

    return ShadowAdoptionResult(
        deployment=deployment,
        state=state,
        deployment_dir=final_dir,
        deployment_path=final_dir / "deployment.json",
        state_path=final_dir / "state.json",
        events_path=final_dir / "events.jsonl",
    )


def validate_final_evaluation_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the exact producer contract required by Shadow adoption."""

    if not isinstance(report, Mapping):
        raise ShadowAdoptionError("final evaluation report must be an object")
    missing = FINAL_REPORT_KEYS - set(report)
    extra = set(report) - FINAL_REPORT_KEYS
    if missing or extra:
        raise ShadowAdoptionError(
            f"final evaluation report keys are invalid; missing={sorted(missing)} extra={sorted(extra)}"
        )
    _literal(report, "schema_version", 1)
    _literal(report, "report_type", "final_evaluation")
    for key in {"final_evaluation_id", "git_commit", "source_research_run_id"}:
        _non_empty_string(report.get(key), key)
    _utc_timestamp(report.get("created_at_utc"), "created_at_utc")

    candidate = report.get("candidate")
    if not isinstance(candidate, Mapping) or set(candidate) != CANDIDATE_KEYS:
        raise ShadowAdoptionError("candidate must use the exact final-evaluation candidate schema")
    for key in {"candidate_id", "family"}:
        _non_empty_string(candidate.get(key), f"candidate.{key}")
    params = candidate.get("params")
    if not isinstance(params, Mapping):
        raise ShadowAdoptionError("candidate.params must be an object")
    normalized_params: dict[str, float | int | str] = {}
    for key, value in params.items():
        if not isinstance(key, str) or not key:
            raise ShadowAdoptionError("candidate.params keys must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ShadowAdoptionError(f"candidate.params.{key} has an unsupported type")
        if isinstance(value, float) and not isfinite(value):
            raise ShadowAdoptionError(f"candidate.params.{key} must be finite")
        normalized_params[key] = value
    if normalized_params.get("symbol", "ETHUSDC") != "ETHUSDC":
        raise ShadowAdoptionError("candidate symbol must be ETHUSDC")
    if normalized_params.get("side", "LONG") != "LONG":
        raise ShadowAdoptionError("candidate side must be LONG")
    expected_signature = canonical_signature_payload(str(candidate["family"]), normalized_params)
    if canonical_json_bytes(candidate.get("candidate_signature")) != canonical_json_bytes(expected_signature):
        raise ShadowAdoptionError("candidate_signature does not match the canonical candidate identity")

    evidence = report.get("quality_gate_evidence")
    if not isinstance(evidence, Mapping):
        raise ShadowAdoptionError("quality_gate_evidence must be an object")
    final = evidence.get("final")
    if not isinstance(final, Mapping):
        raise ShadowAdoptionError("quality_gate_evidence.final must be an object")
    if final.get("sealed_holdout_evaluations") != 1 or type(final.get("sealed_holdout_evaluations")) is not int:
        raise ShadowAdoptionError("sealed_holdout_evaluations must be exactly 1")
    stored_gate = report.get("quality_gate")
    if not isinstance(stored_gate, Mapping):
        raise ShadowAdoptionError("quality_gate must be an object")
    if canonical_json_bytes(report.get("safety")) != canonical_json_bytes(safety_status()):
        raise ShadowAdoptionError("final evaluation safety declaration is not canonical")
    return {
        **dict(report),
        "candidate": {
            "candidate_id": candidate["candidate_id"],
            "family": candidate["family"],
            "params": normalized_params,
            "candidate_signature": expected_signature,
        },
    }


def _read_and_assess(path: Path) -> tuple[bytes, dict[str, Any], AdoptionAssessment]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ShadowAdoptionError("final evaluation report must contain one JSON object")
    report = validate_final_evaluation_report(value)
    evidence = report["quality_gate_evidence"]
    recomputed = evaluate_quality_gates(evidence, stage="final").to_dict()
    if canonical_json_bytes(report["quality_gate"]) != canonical_json_bytes(recomputed):
        raise ShadowAdoptionError("stored quality_gate does not match fresh evaluation")
    failed_codes = {
        str(check.get("code"))
        for check in recomputed["checks"]
        if isinstance(check, Mapping) and check.get("passed") is not True
    }
    final_net = report["quality_gate_evidence"]["final"].get("net_usdc_per_day")
    if isinstance(final_net, bool) or not isinstance(final_net, (int, float)) or not isfinite(float(final_net)):
        raise ShadowAdoptionError("final.net_usdc_per_day must be finite")
    report_hash = sha256(raw).hexdigest()
    common = {
        "final_evaluation_id": report["final_evaluation_id"],
        "candidate_id": report["candidate"]["candidate_id"],
        "candidate_signature": report["candidate"]["candidate_signature"],
        "final_net_usdc_per_day": float(final_net),
        "report_sha256": report_hash,
        "recomputed_quality_gate": recomputed,
    }
    if recomputed.get("passed") is True and not failed_codes:
        return raw, report, AdoptionAssessment(
            color="green",
            shadow_eligible=True,
            target_reached=True,
            live_eligible=False,
            reason_codes=("all_quality_gates_passed",),
            **common,
        )
    missing = recomputed.get("missing_evidence")
    invalid = recomputed.get("invalid_evidence")
    if (
        failed_codes == {"final.target"}
        and not missing
        and not invalid
        and float(final_net) > 0
    ):
        return raw, report, AdoptionAssessment(
            color="yellow",
            shadow_eligible=True,
            target_reached=False,
            live_eligible=False,
            reason_codes=("target_guideline_not_reached",),
            **common,
        )
    reasons = tuple(sorted(f"gate_failed:{code}" for code in failed_codes)) or (
        "quality_gate_not_passed",
    )
    return raw, report, AdoptionAssessment(
        color="red",
        shadow_eligible=False,
        target_reached=False,
        live_eligible=False,
        reason_codes=reasons,
        **common,
    )


def _red(reason: str) -> AdoptionAssessment:
    return AdoptionAssessment(
        color="red",
        shadow_eligible=False,
        target_reached=False,
        live_eligible=False,
        reason_codes=(reason,),
    )


def _literal(report: Mapping[str, Any], key: str, expected: object) -> None:
    value = report.get(key)
    if value != expected or type(value) is not type(expected):
        raise ShadowAdoptionError(f"{key} must be {expected!r}")


def _non_empty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ShadowAdoptionError(f"{path} must be a non-empty string")
    return value


def _utc_timestamp(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ShadowAdoptionError(f"{path} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ShadowAdoptionError(f"{path} is invalid") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ShadowAdoptionError(f"{path} must be UTC")
