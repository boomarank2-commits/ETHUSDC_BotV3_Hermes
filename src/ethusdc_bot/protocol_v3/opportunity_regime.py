"""Causal fold-fitted opportunity and regime classification for Task 20."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Final

from .context_parity import ContextParityBinding
from .feature_store import (
    CONTRACT_VERSION as FEATURE_STORE_CONTRACT_VERSION,
    FoldFeatureFitState,
    MultiTimeframeFeatureStore,
    feature_snapshot_at,
    validate_feature_store_against_binding,
    validate_fold_feature_state,
)
from .inner_folds import validate_inner_fold_identity_payload

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_opportunity_regime_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_opportunity_regime_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_causal_opportunity_regime_v1"
FIT_STATE_SCHEMA_VERSION: Final = "protocol_v3_opportunity_regime_fit_state_v1"
ASSESSMENT_SCHEMA_VERSION: Final = "protocol_v3_opportunity_regime_assessment_v1"
COMPLETE: Final = "COMPLETE"
INSUFFICIENT_WARMUP: Final = "INSUFFICIENT_WARMUP"
NO_TRADE: Final = "NO_TRADE"
ROUTER_MAY_EVALUATE_LOCAL_EDGE: Final = "ROUTER_MAY_EVALUATE_LOCAL_EDGE"
LEGACY_REGIMES: Final = ("down_low", "down_high", "up_low", "up_high")
METRICS: Final = (
    "realized_volatility_bps", "atr_bps", "expected_range_bps",
    "compression_ratio", "trend_return", "trend_efficiency",
    "anchor_distance_atr", "pullback_depth_atr", "btc_context_return",
    "ethbtc_context_return",
)
QUANTILES: Final = (0.1, 0.25, 0.5, 0.75, 0.9)
_SAFETY: Final = {
    "api_keys": "forbidden", "live": "locked", "orders": "locked",
    "paper": "locked", "testtrade": "locked", "trading_api": "forbidden",
    "may_create_signal": False, "may_create_pnl": False,
    "may_select_strategy": False,
}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION, "fit_state_schema_version": FIT_STATE_SCHEMA_VERSION,
    "assessment_schema_version": ASSESSMENT_SCHEMA_VERSION,
    "source_policy": {"feature_store_contract": FEATURE_STORE_CONTRACT_VERSION, "feature_fit_state_required": True, "task14_fold_identity_required": True, "closed_bars_only": True, "training_only_thresholds": True},
    "metric_policy": {"realized_volatility": "root_mean_square_of_last_24_closed_1h_returns_bps", "atr": "mean_range_bps_of_last_14_closed_1h_bars", "expected_range": "median_range_bps_of_last_20_closed_1h_bars", "compression": "latest_4h_range_bps_over_median_prior_20_closed_4h_ranges", "trend": "compounded_last_24_closed_1h_returns", "efficiency": "absolute_24h_net_return_over_sum_absolute_1h_returns", "trend_anchor": "median_last_20_closed_4h_closes", "pullback": "distance_from_last_12_closed_4h_high_in_1h_ATR_units", "context": "compounded_last_6_closed_4h_returns_for_BTCUSDC_and_ETHBTC"},
    "fit_policy": {"minimum_metric_rows": 60, "quantiles": list(QUANTILES), "quantile_estimator": "linear_type7", "warmup_excluded": True},
    "classification_policy": {"legacy_regimes": list(LEGACY_REGIMES), "opportunity": ["LOW", "MEDIUM", "HIGH"], "range_state": ["COMPRESSED", "NORMAL", "EXPANDED"], "structure": ["TREND", "COMPRESSION", "RANGE", "STRESS", "UNKNOWN"], "unknown_requires": NO_TRADE, "contradictory_context_requires": NO_TRADE, "stress_requires": NO_TRADE, "low_opportunity_requires": NO_TRADE, "opportunity_may_not_determine_direction": True, "may_select_specialist": False},
    "deferred_scope": {"specialists_task": 21, "router_task": 22, "outer_orchestration_task": 23},
    "safety": _SAFETY,
}


class OpportunityRegimeError(ValueError):
    """Raised when a regime fit or assessment would be stale, leaky, or ambiguous."""


@dataclass(frozen=True)
class OpportunityRegimeFitState:
    canonical_json: str
    state_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json); value["state_sha256"] = self.state_sha256
        return value

    @property
    def identity_payload(self) -> dict[str, Any]:
        basis = {"identity_schema_version": "protocol_v3_opportunity_regime_fit_identity_v1", "state_sha256": self.state_sha256, "contract_version": CONTRACT_VERSION}
        return {**basis, "identity_sha256": _digest(basis)}


@dataclass(frozen=True)
class OpportunityRegimeAssessment:
    canonical_json: str
    assessment_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json); value["assessment_sha256"] = self.assessment_sha256
        return value


def load_opportunity_regime_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = _strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OpportunityRegimeError("opportunity/regime contract is missing or invalid") from exc
    if value != _CANONICAL_CONTRACT:
        raise OpportunityRegimeError("Protocol v3 opportunity/regime contract is not canonical")
    return value


def fit_opportunity_regime_state(
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
    *,
    binding: ContextParityBinding,
    feature_fit_state: FoldFeatureFitState | Mapping[str, Any],
    fold_identity: Mapping[str, Any],
    fold_index: int,
) -> OpportunityRegimeFitState:
    feature_store = validate_feature_store_against_binding(store, binding)
    feature_state = validate_fold_feature_state(feature_fit_state, store=feature_store, binding=binding)
    fold = validate_inner_fold_identity_payload(fold_identity)
    index = _positive_int(fold_index, "fold_index")
    rows = [row for row in fold["plan"]["folds"] if row["fold_index"] == index]
    if len(rows) != 1:
        raise OpportunityRegimeError("requested fold is absent")
    boundary = rows[0]
    if feature_state.to_dict()["fold_identity"] != fold or feature_state.to_dict()["fold_index"] != index:
        raise OpportunityRegimeError("Task-19 feature fit-state and Task-20 fold differ")
    fit_start = _utc_ms(boundary["fit_start_inclusive_utc"])
    fit_end = _utc_ms(boundary["fit_end_exclusive_utc"])
    metric_rows = _training_metric_rows(feature_store.to_dict(), fit_start, fit_end)
    if len(metric_rows) < 60:
        raise OpportunityRegimeError("fewer than 60 complete training-only regime observations")
    thresholds = {
        metric: {str(q): _quantile([row[metric] for row in metric_rows], q) for q in QUANTILES}
        for metric in METRICS
    }
    basis = {
        "schema_version": FIT_STATE_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION, "store_identity": feature_store.identity_payload,
        "feature_fit_state_sha256": feature_state.state_sha256, "fold_identity": fold,
        "fold_index": index, "fit_start_inclusive_utc": boundary["fit_start_inclusive_utc"],
        "fit_end_exclusive_utc": boundary["fit_end_exclusive_utc"],
        "metric_row_count": len(metric_rows), "metric_rows_sha256": _digest(metric_rows),
        "thresholds": thresholds, "warmup_excluded": True, "safety": _SAFETY,
    }
    return _fit_state({**basis, "state_sha256": _digest(basis)}, feature_store, feature_state)


def assess_opportunity_regime(
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
    *,
    binding: ContextParityBinding,
    feature_fit_state: FoldFeatureFitState | Mapping[str, Any],
    regime_fit_state: OpportunityRegimeFitState | Mapping[str, Any],
    context_timestamp_ms: int,
) -> OpportunityRegimeAssessment:
    feature_store = validate_feature_store_against_binding(store, binding)
    feature_state = validate_fold_feature_state(feature_fit_state, store=feature_store, binding=binding)
    regime_state = _fit_state(regime_fit_state, feature_store, feature_state)
    timestamp = _minute_ms(context_timestamp_ms, "context_timestamp_ms")
    state_payload = regime_state.to_dict()
    if timestamp < _utc_ms(state_payload["fit_end_exclusive_utc"]):
        raise OpportunityRegimeError("assessment timestamp precedes completed regime fit")
    feature_snapshot = feature_snapshot_at(feature_store, context_timestamp_ms=timestamp)
    metrics = _metrics_at(feature_store.to_dict(), timestamp)
    if feature_snapshot["state"] != COMPLETE or metrics is None:
        result = _incomplete_assessment("required_closed_bar_warmup_is_incomplete")
    else:
        result = _classify(metrics, state_payload["thresholds"])
    basis = {
        "schema_version": ASSESSMENT_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION, "store_identity": feature_store.identity_payload,
        "feature_fit_state_sha256": feature_state.state_sha256,
        "regime_fit_identity": regime_state.identity_payload,
        "context_timestamp_ms": timestamp, "feature_snapshot_sha256": feature_snapshot["snapshot_sha256"],
        **result, "safety": _SAFETY,
    }
    return _assessment({**basis, "assessment_sha256": _digest(basis)}, feature_store, feature_state, regime_state)


def validate_opportunity_regime_fit_state(
    value: OpportunityRegimeFitState | Mapping[str, Any],
    *,
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
    binding: ContextParityBinding,
    feature_fit_state: FoldFeatureFitState | Mapping[str, Any],
) -> OpportunityRegimeFitState:
    feature_store = validate_feature_store_against_binding(store, binding)
    feature_state = validate_fold_feature_state(feature_fit_state, store=feature_store, binding=binding)
    return _fit_state(value, feature_store, feature_state)


def validate_opportunity_regime_assessment(
    value: OpportunityRegimeAssessment | Mapping[str, Any],
    *,
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
    binding: ContextParityBinding,
    feature_fit_state: FoldFeatureFitState | Mapping[str, Any],
    regime_fit_state: OpportunityRegimeFitState | Mapping[str, Any],
) -> OpportunityRegimeAssessment:
    feature_store = validate_feature_store_against_binding(store, binding)
    feature_state = validate_fold_feature_state(feature_fit_state, store=feature_store, binding=binding)
    regime_state = _fit_state(regime_fit_state, feature_store, feature_state)
    return _assessment(value, feature_store, feature_state, regime_state)


def _fit_state(
    value: OpportunityRegimeFitState | Mapping[str, Any],
    store: MultiTimeframeFeatureStore,
    feature_state: FoldFeatureFitState,
) -> OpportunityRegimeFitState:
    root = value.to_dict() if isinstance(value, OpportunityRegimeFitState) else dict(_mapping(value, "regime_fit_state"))
    required = {"schema_version", "protocol_version", "contract_version", "store_identity", "feature_fit_state_sha256", "fold_identity", "fold_index", "fit_start_inclusive_utc", "fit_end_exclusive_utc", "metric_row_count", "metric_rows_sha256", "thresholds", "warmup_excluded", "safety", "state_sha256"}
    if set(root) != required or root["schema_version"] != FIT_STATE_SCHEMA_VERSION or root["protocol_version"] != PROTOCOL_VERSION or root["contract_version"] != CONTRACT_VERSION:
        raise OpportunityRegimeError("regime fit-state fields or versions are invalid")
    if root["store_identity"] != store.identity_payload or root["feature_fit_state_sha256"] != feature_state.state_sha256:
        raise OpportunityRegimeError("regime fit-state source identity mismatch")
    fold = validate_inner_fold_identity_payload(root["fold_identity"])
    index = _positive_int(root["fold_index"], "fold_index")
    rows = [row for row in fold["plan"]["folds"] if row["fold_index"] == index]
    if len(rows) != 1 or root["fit_start_inclusive_utc"] != rows[0]["fit_start_inclusive_utc"] or root["fit_end_exclusive_utc"] != rows[0]["fit_end_exclusive_utc"]:
        raise OpportunityRegimeError("regime fit-state fold boundary mismatch")
    if feature_state.to_dict()["fold_identity"] != fold or feature_state.to_dict()["fold_index"] != index:
        raise OpportunityRegimeError("regime fit-state differs from feature fit fold")
    metric_rows = _training_metric_rows(store.to_dict(), _utc_ms(root["fit_start_inclusive_utc"]), _utc_ms(root["fit_end_exclusive_utc"]))
    if root["metric_row_count"] != len(metric_rows) or root["metric_row_count"] < 60 or root["metric_rows_sha256"] != _digest(metric_rows):
        raise OpportunityRegimeError("regime training metric inventory mismatch")
    expected = {metric: {str(q): _quantile([row[metric] for row in metric_rows], q) for q in QUANTILES} for metric in METRICS}
    if root["thresholds"] != expected or root["warmup_excluded"] is not True:
        raise OpportunityRegimeError("regime thresholds differ from training-only replay")
    if root["safety"] != _SAFETY:
        raise OpportunityRegimeError("regime fit-state safety locks are invalid")
    observed = _sha(root["state_sha256"], "state_sha256"); basis = dict(root); basis.pop("state_sha256")
    if observed != _digest(basis):
        raise OpportunityRegimeError("regime fit-state digest mismatch")
    return OpportunityRegimeFitState(_canonical(basis), observed)


def _assessment(
    value: OpportunityRegimeAssessment | Mapping[str, Any],
    store: MultiTimeframeFeatureStore,
    feature_state: FoldFeatureFitState,
    regime_state: OpportunityRegimeFitState,
) -> OpportunityRegimeAssessment:
    root = value.to_dict() if isinstance(value, OpportunityRegimeAssessment) else dict(_mapping(value, "regime_assessment"))
    required = {"schema_version", "protocol_version", "contract_version", "store_identity", "feature_fit_state_sha256", "regime_fit_identity", "context_timestamp_ms", "feature_snapshot_sha256", "state", "reason", "metrics", "opportunity", "range_state", "structure", "legacy_regime", "stress", "contradictory_context", "eligible_family_hint", "required_action", "routing_allowed", "safety", "assessment_sha256"}
    if set(root) != required or root["schema_version"] != ASSESSMENT_SCHEMA_VERSION or root["protocol_version"] != PROTOCOL_VERSION or root["contract_version"] != CONTRACT_VERSION:
        raise OpportunityRegimeError("regime assessment fields or versions are invalid")
    if root["store_identity"] != store.identity_payload or root["feature_fit_state_sha256"] != feature_state.state_sha256 or root["regime_fit_identity"] != regime_state.identity_payload:
        raise OpportunityRegimeError("regime assessment source identity mismatch")
    timestamp = _minute_ms(root["context_timestamp_ms"], "context_timestamp_ms")
    snapshot = feature_snapshot_at(store, context_timestamp_ms=timestamp)
    if root["feature_snapshot_sha256"] != snapshot["snapshot_sha256"]:
        raise OpportunityRegimeError("regime assessment feature snapshot mismatch")
    metrics = _metrics_at(store.to_dict(), timestamp)
    expected = _incomplete_assessment("required_closed_bar_warmup_is_incomplete") if snapshot["state"] != COMPLETE or metrics is None else _classify(metrics, regime_state.to_dict()["thresholds"])
    for key, expected_value in expected.items():
        if root[key] != expected_value:
            raise OpportunityRegimeError("regime assessment differs from exact replay")
    if root["safety"] != _SAFETY:
        raise OpportunityRegimeError("regime assessment safety locks are invalid")
    observed = _sha(root["assessment_sha256"], "assessment_sha256"); basis = dict(root); basis.pop("assessment_sha256")
    if observed != _digest(basis):
        raise OpportunityRegimeError("regime assessment digest mismatch")
    return OpportunityRegimeAssessment(_canonical(basis), observed)


def _training_metric_rows(store: Mapping[str, Any], fit_start: int, fit_end: int) -> list[dict[str, float]]:
    timestamps = [row["close_time_exclusive_ms"] for row in store["series"]["ETHUSDC"]["4h"] if row["open_time_ms"] >= fit_start and row["close_time_exclusive_ms"] <= fit_end]
    rows = []
    for timestamp in timestamps:
        metrics = _metrics_at(store, timestamp)
        if metrics is not None:
            rows.append({"context_timestamp_ms": timestamp, **metrics})
    return rows


def _metrics_at(store: Mapping[str, Any], timestamp: int) -> dict[str, float] | None:
    eth_1h = _closed(store, "ETHUSDC", "1h", timestamp)
    eth_4h = _closed(store, "ETHUSDC", "4h", timestamp)
    eth_1d = _closed(store, "ETHUSDC", "1d", timestamp)
    btc_4h = _closed(store, "BTCUSDC", "4h", timestamp)
    ratio_4h = _closed(store, "ETHBTC", "4h", timestamp)
    if min(len(eth_1h), len(eth_4h), len(eth_1d), len(btc_4h), len(ratio_4h)) < 2 or len(eth_1h) < 25 or len(eth_4h) < 21 or len(btc_4h) < 7 or len(ratio_4h) < 7:
        return None
    hourly = eth_1h[-24:]
    returns = [float(row["features"]["return_1"]) for row in hourly if row["features"]["return_1"] is not None]
    if len(returns) != 24:
        return None
    realized = math.sqrt(math.fsum(value * value for value in returns) / len(returns)) * 10_000.0
    atr = math.fsum(float(row["features"]["range_bps"]) for row in eth_1h[-14:]) / 14.0
    expected_range = median(float(row["features"]["range_bps"]) for row in eth_1h[-20:])
    prior_ranges = [float(row["features"]["range_bps"]) for row in eth_4h[-21:-1]]
    range_anchor = median(prior_ranges)
    compression = float(eth_4h[-1]["features"]["range_bps"]) / range_anchor if range_anchor > 0 else 1.0
    trend = math.prod(1.0 + value for value in returns) - 1.0
    path = math.fsum(abs(value) for value in returns)
    efficiency = abs(trend) / path if path > 0 else 0.0
    closes_4h = [float(row["close"]) for row in eth_4h[-20:]]
    current = closes_4h[-1]
    atr_price = current * atr / 10_000.0
    anchor_distance = (current - median(closes_4h)) / atr_price if atr_price > 0 else 0.0
    pullback = (max(float(row["high"]) for row in eth_4h[-12:]) - current) / atr_price if atr_price > 0 else 0.0
    return {
        "realized_volatility_bps": realized,
        "atr_bps": atr,
        "expected_range_bps": expected_range,
        "compression_ratio": compression,
        "trend_return": trend,
        "trend_efficiency": efficiency,
        "anchor_distance_atr": anchor_distance,
        "pullback_depth_atr": pullback,
        "btc_context_return": _compounded(btc_4h[-6:]),
        "ethbtc_context_return": _compounded(ratio_4h[-6:]),
    }


def _classify(metrics: Mapping[str, float], thresholds: Mapping[str, Any]) -> dict[str, Any]:
    vol = metrics["realized_volatility_bps"]
    vol_q25 = thresholds["realized_volatility_bps"]["0.25"]
    vol_q50 = thresholds["realized_volatility_bps"]["0.5"]
    vol_q75 = thresholds["realized_volatility_bps"]["0.75"]
    opportunity = "LOW" if vol <= vol_q25 else "HIGH" if vol >= vol_q75 else "MEDIUM"
    compression = metrics["compression_ratio"]
    comp_q25 = thresholds["compression_ratio"]["0.25"]
    comp_q75 = thresholds["compression_ratio"]["0.75"]
    range_state = "COMPRESSED" if compression <= comp_q25 else "EXPANDED" if compression >= comp_q75 else "NORMAL"
    trend = metrics["trend_return"]
    efficiency = metrics["trend_efficiency"]
    magnitude_floor = max(abs(thresholds["trend_return"]["0.25"]), abs(thresholds["trend_return"]["0.75"]))
    stress = metrics["btc_context_return"] <= thresholds["btc_context_return"]["0.1"] or metrics["ethbtc_context_return"] <= thresholds["ethbtc_context_return"]["0.1"]
    context_signs = (metrics["btc_context_return"] >= 0.0, metrics["ethbtc_context_return"] >= 0.0)
    contradictory = abs(trend) >= magnitude_floor and ((trend > 0 and context_signs == (False, False)) or (trend < 0 and context_signs == (True, True)))
    legacy = f"{'up' if trend >= 0 else 'down'}_{'high' if vol > vol_q50 else 'low'}"
    if stress:
        structure, hint, reason = "STRESS", None, "context_stress_requires_no_trade"
    elif contradictory:
        structure, hint, reason = "UNKNOWN", None, "contradictory_context_requires_no_trade"
    elif opportunity == "LOW":
        structure, hint, reason = "UNKNOWN", None, "low_opportunity_requires_no_trade"
    elif efficiency >= thresholds["trend_efficiency"]["0.75"] and abs(trend) >= magnitude_floor:
        structure, hint, reason = "TREND", "trend_pullback_or_multiday_swing", "causal_trend_structure"
    elif range_state == "COMPRESSED":
        structure, hint, reason = "COMPRESSION", "compression_breakout_retest", "causal_compression_structure"
    elif efficiency <= thresholds["trend_efficiency"]["0.25"] and range_state == "NORMAL":
        structure, hint, reason = "RANGE", "range_reversion_confirmed", "causal_range_structure"
    else:
        structure, hint, reason = "UNKNOWN", None, "unresolved_structure_requires_no_trade"
    allowed = structure in {"TREND", "COMPRESSION", "RANGE"}
    return {
        "state": COMPLETE, "reason": reason, "metrics": {key: float(metrics[key]) for key in METRICS},
        "opportunity": opportunity, "range_state": range_state, "structure": structure,
        "legacy_regime": legacy, "stress": stress, "contradictory_context": contradictory,
        "eligible_family_hint": hint, "required_action": ROUTER_MAY_EVALUATE_LOCAL_EDGE if allowed else NO_TRADE,
        "routing_allowed": allowed,
    }


def _incomplete_assessment(reason: str) -> dict[str, Any]:
    return {"state": INSUFFICIENT_WARMUP, "reason": reason, "metrics": None, "opportunity": None, "range_state": None, "structure": "UNKNOWN", "legacy_regime": None, "stress": None, "contradictory_context": None, "eligible_family_hint": None, "required_action": NO_TRADE, "routing_allowed": False}


def _closed(store: Mapping[str, Any], symbol: str, timeframe: str, timestamp: int) -> list[Mapping[str, Any]]:
    rows = store["series"][symbol][timeframe]
    end = bisect_right(rows, timestamp, key=lambda row: row["close_time_exclusive_ms"])
    return rows[:end]


def _compounded(rows: Sequence[Mapping[str, Any]]) -> float:
    values = [float(row["features"]["return_1"]) for row in rows if row["features"]["return_1"] is not None]
    return math.prod(1.0 + value for value in values) - 1.0


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] if lower == upper else ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _utc_ms(value: Any) -> int:
    from datetime import datetime
    if not isinstance(value, str) or not value.endswith("Z"):
        raise OpportunityRegimeError("fold boundary must be canonical UTC text")
    return int(datetime.fromisoformat(value[:-1] + "+00:00").timestamp() * 1000)


def _minute_ms(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value % 60_000:
        raise OpportunityRegimeError(f"{path} must be a nonnegative UTC minute timestamp")
    return value


def _positive_int(value: Any, path: str) -> int:
    if type(value) is not int or value <= 0:
        raise OpportunityRegimeError(f"{path} must be a positive integer")
    return value


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OpportunityRegimeError(f"{path} must be an object")
    return value


def _sha(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise OpportunityRegimeError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _strict_loads(text: str) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise OpportunityRegimeError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=hook, parse_constant=lambda value: (_ for _ in ()).throw(OpportunityRegimeError(f"non-finite JSON constant: {value}")))


__all__ = ["ASSESSMENT_SCHEMA_VERSION", "COMPLETE", "CONTRACT_PATH", "CONTRACT_SCHEMA_VERSION", "CONTRACT_VERSION", "FIT_STATE_SCHEMA_VERSION", "INSUFFICIENT_WARMUP", "LEGACY_REGIMES", "METRICS", "NO_TRADE", "OpportunityRegimeAssessment", "OpportunityRegimeError", "OpportunityRegimeFitState", "ROUTER_MAY_EVALUATE_LOCAL_EDGE", "assess_opportunity_regime", "fit_opportunity_regime_state", "load_opportunity_regime_contract", "validate_opportunity_regime_assessment", "validate_opportunity_regime_fit_state"]
