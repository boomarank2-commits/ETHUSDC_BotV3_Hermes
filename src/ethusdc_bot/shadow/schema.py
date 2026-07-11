"""Strict schemas for order-free Shadow deployments and runtime state."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import json
from math import isfinite
import re
from typing import Any

from ethusdc_bot.backtest.search_space import canonical_candidate_signature
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.portfolio import PortfolioPolicy, canonical_portfolio_signature


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

DEPLOYMENT_KEYS = {
    "schema_version",
    "deployment_id",
    "created_at_utc",
    "mode",
    "status",
    "source_report",
    "candidate",
    "portfolio_policy",
    "cost_model",
    "assessment",
    "safety",
}
SOURCE_REPORT_KEYS = {
    "path",
    "sha256",
    "final_evaluation_id",
    "source_research_run_id",
    "git_commit",
}
CANDIDATE_KEYS = {"candidate_id", "family", "params", "candidate_signature"}
SIGNATURE_KEYS = {"family", "params"}
PORTFOLIO_POLICY_KEYS = {"policy", "canonical_signature"}
COST_MODEL_KEYS = {
    "fee_rate_per_side",
    "fee_bps_per_side",
    "slippage_bps_per_side",
}
ASSESSMENT_KEYS = {
    "color",
    "shadow_eligible",
    "target_reached",
    "live_eligible",
    "reason_codes",
}
SAFETY_KEYS = {
    "public_data_only",
    "orders_enabled",
    "trading_api_enabled",
    "api_keys_used",
    "live",
    "paper",
    "testtrade",
    "short_margin_futures_leverage",
}
STATE_KEYS = {
    "schema_version",
    "deployment_id",
    "phase",
    "created_at_utc",
    "updated_at_utc",
    "deployment_budget_usdc",
    "lot_notional_usdc",
    "max_open_lots",
    "last_processed_candle_open_time_ms",
    "open_lots",
    "realized_net_usdc",
    "unrealized_net_usdc",
    "event_count",
    "last_event_hash",
    "error",
    "safety",
}
LOT_KEYS = {
    "lot_id",
    "signal_time_ms",
    "entry_time_ms",
    "entry_mid_price",
    "entry_price",
    "quantity",
    "notional_usdc",
    "best_close",
}


class ShadowSchemaError(ValueError):
    """Raised when Shadow state fails its strict safety contract."""


def canonical_signature_payload(
    family: str, params: Mapping[str, float | int | str]
) -> dict[str, Any]:
    """Return the JSON representation of the canonical candidate identity."""

    signature = canonical_candidate_signature(StrategyCandidate(family, dict(params)))
    return {
        "family": signature[0],
        "params": [[key, value] for key, value in signature[1]],
    }


def shadow_safety_status() -> dict[str, str | bool]:
    """Return the immutable order-free Shadow safety declaration."""

    return {
        "public_data_only": True,
        "orders_enabled": False,
        "trading_api_enabled": False,
        "api_keys_used": False,
        "live": "locked",
        "paper": "locked",
        "testtrade": "locked",
        "short_margin_futures_leverage": "forbidden",
    }


def validate_shadow_deployment(data: Mapping[str, Any]) -> None:
    """Validate an immutable Shadow adoption receipt, failing on unknown keys."""

    root = _mapping(data, "shadow_deployment")
    _exact_keys(root, DEPLOYMENT_KEYS, "shadow_deployment")
    _literal(root, "schema_version", 1, "shadow_deployment")
    _string(root, "deployment_id", "shadow_deployment")
    _timestamp(root.get("created_at_utc"), "shadow_deployment.created_at_utc")
    _literal(root, "mode", "public_data_shadow", "shadow_deployment")
    _literal(root, "status", "adopted", "shadow_deployment")

    source = _mapping(root["source_report"], "shadow_deployment.source_report")
    _exact_keys(source, SOURCE_REPORT_KEYS, "shadow_deployment.source_report")
    for key in {"path", "final_evaluation_id", "source_research_run_id", "git_commit"}:
        _string(source, key, "shadow_deployment.source_report")
    _sha256(source.get("sha256"), "shadow_deployment.source_report.sha256")

    candidate = _validate_candidate(root["candidate"], "shadow_deployment.candidate")

    policy_wrapper = _mapping(root["portfolio_policy"], "shadow_deployment.portfolio_policy")
    _exact_keys(policy_wrapper, PORTFOLIO_POLICY_KEYS, "shadow_deployment.portfolio_policy")
    policy_payload = _mapping(
        policy_wrapper["policy"], "shadow_deployment.portfolio_policy.policy"
    )
    try:
        policy = PortfolioPolicy(
            deployment_budget_usdc=policy_payload.get("deployment_budget_usdc"),
            lot_notional_usdc=policy_payload.get("lot_notional_usdc"),
            compounding_enabled=policy_payload.get("compounding_enabled"),
            baseline_fee_bps_per_side=policy_payload.get("baseline_fee_bps_per_side"),
            baseline_slippage_bps_per_side=policy_payload.get("baseline_slippage_bps_per_side"),
            soft_drawdown_fraction=policy_payload.get("soft_drawdown_fraction"),
        )
    except (TypeError, ValueError) as exc:
        raise ShadowSchemaError(
            f"shadow_deployment.portfolio_policy.policy is invalid: {exc}"
        ) from exc
    expected_policy = policy.to_dict()
    if not _json_identical(policy_payload, expected_policy):
        raise ShadowSchemaError(
            "shadow_deployment.portfolio_policy.policy is not the canonical PortfolioPolicy payload"
        )
    _literal(
        policy_wrapper,
        "canonical_signature",
        canonical_portfolio_signature(policy),
        "shadow_deployment.portfolio_policy",
    )

    costs = _mapping(root["cost_model"], "shadow_deployment.cost_model")
    _exact_keys(costs, COST_MODEL_KEYS, "shadow_deployment.cost_model")
    _literal(costs, "fee_rate_per_side", 0.001, "shadow_deployment.cost_model")
    _literal(costs, "fee_bps_per_side", 10.0, "shadow_deployment.cost_model")
    _literal(costs, "slippage_bps_per_side", 5.0, "shadow_deployment.cost_model")

    assessment = _mapping(root["assessment"], "shadow_deployment.assessment")
    _exact_keys(assessment, ASSESSMENT_KEYS, "shadow_deployment.assessment")
    color = assessment.get("color")
    if color not in {"green", "yellow"}:
        raise ShadowSchemaError("shadow_deployment.assessment.color must be green or yellow")
    _literal(assessment, "shadow_eligible", True, "shadow_deployment.assessment")
    _literal(assessment, "live_eligible", False, "shadow_deployment.assessment")
    _literal(assessment, "target_reached", color == "green", "shadow_deployment.assessment")
    reasons = assessment.get("reason_codes")
    if not isinstance(reasons, list) or not reasons or any(not isinstance(item, str) or not item for item in reasons):
        raise ShadowSchemaError("shadow_deployment.assessment.reason_codes must be a non-empty string list")

    _validate_safety(root["safety"], "shadow_deployment.safety")
    if not _json_identical(
        candidate["candidate_signature"],
        canonical_signature_payload(candidate["family"], candidate["params"]),
    ):
        raise ShadowSchemaError("shadow_deployment.candidate.candidate_signature is not canonical")


def validate_shadow_state(data: Mapping[str, Any]) -> None:
    """Validate persisted Shadow state without permitting a live-capable mode."""

    root = _mapping(data, "shadow_state")
    _exact_keys(root, STATE_KEYS, "shadow_state")
    _literal(root, "schema_version", 1, "shadow_state")
    _string(root, "deployment_id", "shadow_state")
    if root.get("phase") not in {"adopted_stopped", "running", "paused", "stopped", "error"}:
        raise ShadowSchemaError("shadow_state.phase is invalid")
    _timestamp(root.get("created_at_utc"), "shadow_state.created_at_utc")
    _timestamp(root.get("updated_at_utc"), "shadow_state.updated_at_utc")
    budget = _positive_int(root.get("deployment_budget_usdc"), "shadow_state.deployment_budget_usdc")
    try:
        policy = PortfolioPolicy(deployment_budget_usdc=budget)
    except ValueError as exc:
        raise ShadowSchemaError(f"shadow_state.deployment_budget_usdc is invalid: {exc}") from exc
    _literal(root, "lot_notional_usdc", 100.0, "shadow_state")
    _literal(root, "max_open_lots", policy.max_concurrent_lots, "shadow_state")
    last_candle = root.get("last_processed_candle_open_time_ms")
    if last_candle is not None and (type(last_candle) is not int or last_candle < 0):
        raise ShadowSchemaError("shadow_state.last_processed_candle_open_time_ms must be null or a non-negative integer")
    lots = root.get("open_lots")
    if not isinstance(lots, list):
        raise ShadowSchemaError("shadow_state.open_lots must be a list")
    if len(lots) > policy.max_concurrent_lots:
        raise ShadowSchemaError("shadow_state.open_lots exceeds max_open_lots")
    seen_lot_ids: set[str] = set()
    for index, lot in enumerate(lots):
        lot_path = f"shadow_state.open_lots[{index}]"
        value = _mapping(lot, lot_path)
        _exact_keys(value, LOT_KEYS, lot_path)
        _string(value, "lot_id", lot_path)
        if value["lot_id"] in seen_lot_ids:
            raise ShadowSchemaError("shadow_state.open_lots contains duplicate lot_id")
        seen_lot_ids.add(value["lot_id"])
        for key in {"signal_time_ms", "entry_time_ms"}:
            if type(value.get(key)) is not int or value[key] < 0:
                raise ShadowSchemaError(f"{lot_path}.{key} must be a non-negative integer")
        for key in {"entry_mid_price", "entry_price", "quantity", "notional_usdc", "best_close"}:
            number = _finite_number(value.get(key), f"{lot_path}.{key}")
            if number <= 0:
                raise ShadowSchemaError(f"{lot_path}.{key} must be positive")
        if float(value["notional_usdc"]) != 100.0:
            raise ShadowSchemaError(f"{lot_path}.notional_usdc must be 100")
    _finite_number(root.get("realized_net_usdc"), "shadow_state.realized_net_usdc")
    _finite_number(root.get("unrealized_net_usdc"), "shadow_state.unrealized_net_usdc")
    event_count = root.get("event_count")
    if type(event_count) is not int or event_count < 1:
        raise ShadowSchemaError("shadow_state.event_count must be an integer >= 1")
    _sha256(root.get("last_event_hash"), "shadow_state.last_event_hash")
    error = root.get("error")
    if error is not None and (not isinstance(error, str) or not error.strip()):
        raise ShadowSchemaError("shadow_state.error must be null or a non-empty string")
    if root.get("phase") == "error" and error is None:
        raise ShadowSchemaError("shadow_state.error is required when phase is error")
    _validate_safety(root["safety"], "shadow_state.safety")


def _validate_candidate(value: object, path: str) -> dict[str, Any]:
    candidate = dict(_mapping(value, path))
    _exact_keys(candidate, CANDIDATE_KEYS, path)
    _string(candidate, "candidate_id", path)
    _string(candidate, "family", path)
    params = _mapping(candidate["params"], f"{path}.params")
    normalized: dict[str, float | int | str] = {}
    for key, raw in params.items():
        if not isinstance(key, str) or not key:
            raise ShadowSchemaError(f"{path}.params keys must be non-empty strings")
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ShadowSchemaError(f"{path}.params.{key} has an unsupported value type")
        if isinstance(raw, float) and not isfinite(raw):
            raise ShadowSchemaError(f"{path}.params.{key} must be finite")
        normalized[key] = raw
    candidate["params"] = normalized
    signature = _mapping(candidate["candidate_signature"], f"{path}.candidate_signature")
    _exact_keys(signature, SIGNATURE_KEYS, f"{path}.candidate_signature")
    _string(signature, "family", f"{path}.candidate_signature")
    pairs = signature.get("params")
    if not isinstance(pairs, list) or any(not isinstance(pair, list) or len(pair) != 2 for pair in pairs):
        raise ShadowSchemaError(f"{path}.candidate_signature.params must be a list of key/value pairs")
    candidate["candidate_signature"] = {"family": signature["family"], "params": pairs}
    return candidate


def _validate_safety(value: object, path: str) -> None:
    safety = _mapping(value, path)
    _exact_keys(safety, SAFETY_KEYS, path)
    expected = shadow_safety_status()
    for key, expected_value in expected.items():
        _literal(safety, key, expected_value, path)


def _mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ShadowSchemaError(f"{path} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing:
        raise ShadowSchemaError(f"{path} missing required keys: {sorted(missing)}")
    if extra:
        raise ShadowSchemaError(f"{path} contains unknown keys: {sorted(extra)}")


def _literal(value: Mapping[str, Any], key: str, expected: object, path: str) -> None:
    actual = value.get(key)
    if actual != expected or type(actual) is not type(expected):
        raise ShadowSchemaError(f"{path}.{key} must be {expected!r}")


def _string(value: Mapping[str, Any], key: str, path: str) -> str:
    actual = value.get(key)
    if not isinstance(actual, str) or not actual.strip():
        raise ShadowSchemaError(f"{path}.{key} must be a non-empty string")
    return actual


def _positive_int(value: object, path: str) -> int:
    if type(value) is not int or value <= 0:
        raise ShadowSchemaError(f"{path} must be a positive integer")
    return value


def _finite_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ShadowSchemaError(f"{path} must be a finite number")
    return float(value)


def _sha256(value: object, path: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ShadowSchemaError(f"{path} must be a lowercase SHA-256 hex digest")
    return value


def _timestamp(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ShadowSchemaError(f"{path} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ShadowSchemaError(f"{path} must be a valid ISO-8601 UTC timestamp") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ShadowSchemaError(f"{path} must be UTC")


def _json_identical(left: object, right: object) -> bool:
    """Compare JSON values without Python's bool/int or int/float coercion."""

    try:
        return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(
            right, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError):
        return False
