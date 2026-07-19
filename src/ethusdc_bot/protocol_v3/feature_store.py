"""Causal, replayable three-market multi-timeframe feature store (Task 19)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import calendar
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Final

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle, EXPECTED_STEP_MS
from ethusdc_bot.protocol_v3.context_parity import ContextParityBinding, validate_context_parity_binding
from ethusdc_bot.protocol_v3.inner_folds import validate_inner_fold_identity_payload

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_feature_store_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_feature_store_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_causal_multitimeframe_feature_store_v1"
STORE_SCHEMA_VERSION: Final = "protocol_v3_multitimeframe_feature_store_v1"
FIT_STATE_SCHEMA_VERSION: Final = "protocol_v3_fold_feature_fit_state_v1"
COMPLETE: Final = "COMPLETE"
INSUFFICIENT_WARMUP: Final = "INSUFFICIENT_WARMUP"
MARKETS: Final = ("ETHUSDC", "BTCUSDC", "ETHBTC")
FEATURES: Final = ("return_1", "range_bps", "body_bps", "close_location", "volume")
TIMEFRAMES: Final = (
    ("5m", "fixed_utc", 5),
    ("15m", "fixed_utc", 15),
    ("30m", "fixed_utc", 30),
    ("1h", "fixed_utc", 60),
    ("4h", "fixed_utc", 240),
    ("1d", "fixed_utc", 1440),
    ("1w", "calendar_utc_monday", 10080),
    ("1mo", "calendar_utc_month", None),
)
_SAFETY: Final = {
    "api_keys": "forbidden", "live": "locked", "orders": "locked",
    "paper": "locked", "testtrade": "locked", "trading_api": "forbidden",
    "may_create_signal": False, "may_create_pnl": False,
}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION, "store_schema_version": STORE_SCHEMA_VERSION,
    "fit_state_schema_version": FIT_STATE_SCHEMA_VERSION,
    "source": {"context_binding": "three_market_closed_bar_context_parity_v2", "interval": "1m", "exact_common_three_market_grid_required": True},
    "timeframes": [{"id": name, "kind": kind, "minutes": minutes} for name, kind, minutes in TIMEFRAMES],
    "bar_policy": {"only_exactly_complete_buckets_visible": True, "information_timestamp": "close_time_exclusive_ms", "decision_may_read_close_time_lte_context_timestamp": True, "missing_duplicate_or_nonfinite_source_blocks": True, "first_partial_bucket_is_not_emitted": True, "last_partial_bucket_is_not_emitted": True},
    "feature_policy": {"fields": list(FEATURES), "first_return_is_null": True, "opportunity_and_regime_classification_deferred_to_task20": True},
    "fit_policy": {"source": "exact_task14_fold_fit_interval", "bar_open_gte_fit_start": True, "bar_close_lte_fit_end": True, "warmup_excluded_from_scalers_and_quantiles": True, "scaler": "sample_mean_and_sample_std_ddof_1", "zero_variance_scale": 1.0, "quantiles": [0.25, 0.5, 0.75], "quantile_estimator": "linear_type7", "minimum_observations": 2},
    "identity_policy": {"canonical_json": True, "sha256_bound": True, "context_identity_required": True, "fold_identity_required_for_fit_state": True, "deterministic_replay_required": True},
    "safety": _SAFETY,
}


class FeatureStoreError(ValueError):
    """Raised when feature inputs, bars, fit state, or identity are contradictory."""


@dataclass(frozen=True)
class MultiTimeframeFeatureStore:
    canonical_json: str
    store_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["store_sha256"] = self.store_sha256
        return value

    @property
    def identity_payload(self) -> dict[str, Any]:
        return build_feature_store_identity_payload(self)


@dataclass(frozen=True)
class FoldFeatureFitState:
    canonical_json: str
    state_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["state_sha256"] = self.state_sha256
        return value


def load_feature_store_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = _strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FeatureStoreError("feature-store contract is missing or invalid") from exc
    if value != _CANONICAL_CONTRACT:
        raise FeatureStoreError("Protocol v3 feature-store contract is not canonical")
    return value


def build_feature_store(binding: ContextParityBinding) -> MultiTimeframeFeatureStore:
    """Build only fully closed UTC buckets from a validated Task-10 context binding."""

    try:
        validate_context_parity_binding(binding)
    except Exception as exc:
        raise FeatureStoreError(f"validated context parity binding required: {exc}") from exc
    series: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for symbol, candles in _market_series(binding.context):
        series[symbol] = {
            timeframe: _aggregate(candles, timeframe, kind, minutes)
            for timeframe, kind, minutes in TIMEFRAMES
        }
    basis = {
        "schema_version": STORE_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "context_identity": binding.identity_payload(),
        "context_identity_sha256": binding.context_identity_sha256,
        "source_first_open_time_ms": binding.first_open_time_ms,
        "source_last_open_time_ms": binding.common_watermark_open_time_ms,
        "common_context_timestamp_ms": binding.common_watermark_open_time_ms + EXPECTED_STEP_MS,
        "timeframes": [name for name, _, _ in TIMEFRAMES],
        "feature_fields": list(FEATURES),
        "series": series,
        "safety": _SAFETY,
    }
    digest = _digest(basis)
    return validate_feature_store({**basis, "store_sha256": digest})


def validate_feature_store(
    value: MultiTimeframeFeatureStore | Mapping[str, Any],
) -> MultiTimeframeFeatureStore:
    root = value.to_dict() if isinstance(value, MultiTimeframeFeatureStore) else dict(_mapping(value, "feature_store"))
    required = {"schema_version", "protocol_version", "contract_version", "context_identity", "context_identity_sha256", "source_first_open_time_ms", "source_last_open_time_ms", "common_context_timestamp_ms", "timeframes", "feature_fields", "series", "safety", "store_sha256"}
    if set(root) != required or root["schema_version"] != STORE_SCHEMA_VERSION or root["protocol_version"] != PROTOCOL_VERSION or root["contract_version"] != CONTRACT_VERSION:
        raise FeatureStoreError("feature-store fields or versions are invalid")
    if root["timeframes"] != [name for name, _, _ in TIMEFRAMES] or root["feature_fields"] != list(FEATURES):
        raise FeatureStoreError("feature-store timeframe or feature inventory is invalid")
    context_identity = dict(_mapping(root["context_identity"], "context_identity"))
    if _digest(context_identity) != _sha(root["context_identity_sha256"], "context_identity_sha256"):
        raise FeatureStoreError("feature-store context identity digest mismatch")
    first = _minute_ms(root["source_first_open_time_ms"], "source_first_open_time_ms")
    last = _minute_ms(root["source_last_open_time_ms"], "source_last_open_time_ms")
    if last < first or root["common_context_timestamp_ms"] != last + EXPECTED_STEP_MS:
        raise FeatureStoreError("feature-store source interval is invalid")
    all_series = dict(_mapping(root["series"], "series"))
    if set(all_series) != set(MARKETS):
        raise FeatureStoreError("feature-store market inventory is invalid")
    normalized: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for symbol in MARKETS:
        rows_by_timeframe = dict(_mapping(all_series[symbol], f"series.{symbol}"))
        if set(rows_by_timeframe) != set(root["timeframes"]):
            raise FeatureStoreError("feature-store series timeframe inventory is invalid")
        normalized[symbol] = {}
        for timeframe, kind, minutes in TIMEFRAMES:
            normalized[symbol][timeframe] = _validate_aggregate_rows(
                rows_by_timeframe[timeframe], timeframe, kind, minutes, first, last
            )
    if root["series"] != normalized:
        raise FeatureStoreError("feature-store series is not canonical")
    if root["safety"] != _SAFETY:
        raise FeatureStoreError("feature-store safety locks are invalid")
    observed = _sha(root["store_sha256"], "store_sha256")
    basis = dict(root); basis.pop("store_sha256")
    if observed != _digest(basis):
        raise FeatureStoreError("feature-store digest mismatch")
    return MultiTimeframeFeatureStore(_canonical(basis), observed)


def validate_feature_store_against_binding(
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
    binding: ContextParityBinding,
) -> MultiTimeframeFeatureStore:
    validated = validate_feature_store(store)
    rebuilt = build_feature_store(binding)
    if validated.to_dict() != rebuilt.to_dict():
        raise FeatureStoreError("feature-store replay differs from bound source context")
    return validated


def build_feature_store_identity_payload(
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
) -> dict[str, Any]:
    validated = validate_feature_store(store)
    payload = validated.to_dict()
    basis = {
        "identity_schema_version": "protocol_v3_feature_store_identity_v1",
        "contract_version": CONTRACT_VERSION,
        "store_sha256": validated.store_sha256,
        "context_identity_sha256": payload["context_identity_sha256"],
    }
    return {**basis, "identity_sha256": _digest(basis)}


def feature_snapshot_at(
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
    *,
    context_timestamp_ms: int,
) -> dict[str, Any]:
    validated = validate_feature_store(store).to_dict()
    timestamp = _minute_ms(context_timestamp_ms, "context_timestamp_ms")
    if timestamp > validated["common_context_timestamp_ms"]:
        raise FeatureStoreError("feature snapshot requests future context")
    series: dict[str, dict[str, Any]] = {}
    complete = True
    for symbol in MARKETS:
        series[symbol] = {}
        for timeframe, _, _ in TIMEFRAMES:
            eligible = [row for row in validated["series"][symbol][timeframe] if row["close_time_exclusive_ms"] <= timestamp]
            row = eligible[-1] if eligible else None
            series[symbol][timeframe] = row
            complete = complete and row is not None
    basis = {
        "schema_version": "protocol_v3_feature_snapshot_v1",
        "store_sha256": validated["store_sha256"],
        "context_timestamp_ms": timestamp,
        "state": COMPLETE if complete else INSUFFICIENT_WARMUP,
        "series": series,
        "safety": _SAFETY,
    }
    return {**basis, "snapshot_sha256": _digest(basis)}


def fit_fold_feature_state(
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
    *,
    binding: ContextParityBinding,
    fold_identity: Mapping[str, Any],
    fold_index: int,
) -> FoldFeatureFitState:
    """Fit scalers and Type-7 quantiles on exactly one Task-14 fit interval."""

    feature_store = validate_feature_store_against_binding(store, binding)
    store_payload = feature_store.to_dict()
    fold = validate_inner_fold_identity_payload(fold_identity)
    index = _positive_int(fold_index, "fold_index")
    folds = [row for row in fold["plan"]["folds"] if row["fold_index"] == index]
    if len(folds) != 1:
        raise FeatureStoreError("fold identity does not contain requested fold")
    row = folds[0]
    fit_start = _utc_ms(row["fit_start_inclusive_utc"], "fit_start")
    fit_end = _utc_ms(row["fit_end_exclusive_utc"], "fit_end")
    if store_payload["source_first_open_time_ms"] > fit_start or store_payload["common_context_timestamp_ms"] < fit_end:
        raise FeatureStoreError("feature store does not cover the complete fold fit interval")
    statistics: dict[str, dict[str, dict[str, Any]]] = {}
    for symbol in MARKETS:
        statistics[symbol] = {}
        for timeframe, _, _ in TIMEFRAMES:
            bars = [
                bar for bar in store_payload["series"][symbol][timeframe]
                if bar["open_time_ms"] >= fit_start and bar["close_time_exclusive_ms"] <= fit_end
            ]
            feature_statistics: dict[str, Any] = {}
            for feature in FEATURES:
                values = [float(bar["features"][feature]) for bar in bars if bar["features"][feature] is not None]
                if len(values) < 2:
                    raise FeatureStoreError(f"insufficient fold-fit observations for {symbol}.{timeframe}.{feature}")
                mean = math.fsum(values) / len(values)
                variance = math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)
                sample_std = math.sqrt(variance)
                feature_statistics[feature] = {
                    "count": len(values),
                    "mean": mean,
                    "sample_std": sample_std,
                    "scale": sample_std if sample_std > 0.0 else 1.0,
                    "zero_variance": sample_std == 0.0,
                    "quantiles": {str(q): _quantile_type7(values, q) for q in (0.25, 0.5, 0.75)},
                }
            statistics[symbol][timeframe] = feature_statistics
    basis = {
        "schema_version": FIT_STATE_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "store_identity": feature_store.identity_payload,
        "fold_identity": fold,
        "fold_index": index,
        "fit_start_inclusive_utc": row["fit_start_inclusive_utc"],
        "fit_end_exclusive_utc": row["fit_end_exclusive_utc"],
        "warmup_excluded": True,
        "statistics": statistics,
        "safety": _SAFETY,
    }
    digest = _digest(basis)
    return validate_fold_feature_state(
        {**basis, "state_sha256": digest}, store=feature_store, binding=binding
    )


def validate_fold_feature_state(
    value: FoldFeatureFitState | Mapping[str, Any],
    *,
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
    binding: ContextParityBinding | None = None,
) -> FoldFeatureFitState:
    root = value.to_dict() if isinstance(value, FoldFeatureFitState) else dict(_mapping(value, "feature_fit_state"))
    required = {"schema_version", "protocol_version", "contract_version", "store_identity", "fold_identity", "fold_index", "fit_start_inclusive_utc", "fit_end_exclusive_utc", "warmup_excluded", "statistics", "safety", "state_sha256"}
    if set(root) != required or root["schema_version"] != FIT_STATE_SCHEMA_VERSION or root["protocol_version"] != PROTOCOL_VERSION or root["contract_version"] != CONTRACT_VERSION:
        raise FeatureStoreError("feature fit-state fields or versions are invalid")
    identity = dict(_mapping(root["store_identity"], "store_identity"))
    if set(identity) != {"identity_schema_version", "contract_version", "store_sha256", "context_identity_sha256", "identity_sha256"}:
        raise FeatureStoreError("feature-store identity fields are invalid")
    feature_store = (
        validate_feature_store_against_binding(store, binding)
        if binding is not None
        else validate_feature_store(store)
    )
    if identity != feature_store.identity_payload:
        raise FeatureStoreError("feature-store identity is not canonical")
    fold = validate_inner_fold_identity_payload(root["fold_identity"])
    index = _positive_int(root["fold_index"], "fold_index")
    folds = [row for row in fold["plan"]["folds"] if row["fold_index"] == index]
    if len(folds) != 1 or root["fit_start_inclusive_utc"] != folds[0]["fit_start_inclusive_utc"] or root["fit_end_exclusive_utc"] != folds[0]["fit_end_exclusive_utc"]:
        raise FeatureStoreError("feature fit-state fold boundary binding is invalid")
    if root["warmup_excluded"] is not True:
        raise FeatureStoreError("feature fit-state may not include warmup in fit")
    expected = fit_fold_feature_state_unvalidated(feature_store, fold, index)
    if root["statistics"] != expected:
        raise FeatureStoreError("feature fit-state statistics differ from exact replay")
    if root["safety"] != _SAFETY:
        raise FeatureStoreError("feature fit-state safety locks are invalid")
    observed = _sha(root["state_sha256"], "state_sha256")
    basis = dict(root); basis.pop("state_sha256")
    if observed != _digest(basis):
        raise FeatureStoreError("feature fit-state digest mismatch")
    return FoldFeatureFitState(_canonical(basis), observed)


def fit_fold_feature_state_unvalidated(
    store: MultiTimeframeFeatureStore,
    fold_identity: Mapping[str, Any],
    fold_index: int,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Internal replay without recursive public validation."""

    payload = store.to_dict()
    row = next(item for item in fold_identity["plan"]["folds"] if item["fold_index"] == fold_index)
    fit_start = _utc_ms(row["fit_start_inclusive_utc"], "fit_start")
    fit_end = _utc_ms(row["fit_end_exclusive_utc"], "fit_end")
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for symbol in MARKETS:
        result[symbol] = {}
        for timeframe, _, _ in TIMEFRAMES:
            bars = [bar for bar in payload["series"][symbol][timeframe] if bar["open_time_ms"] >= fit_start and bar["close_time_exclusive_ms"] <= fit_end]
            feature_rows: dict[str, Any] = {}
            for feature in FEATURES:
                values = [float(bar["features"][feature]) for bar in bars if bar["features"][feature] is not None]
                if len(values) < 2:
                    raise FeatureStoreError(f"insufficient fold-fit observations for {symbol}.{timeframe}.{feature}")
                mean = math.fsum(values) / len(values)
                std = math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1))
                feature_rows[feature] = {"count": len(values), "mean": mean, "sample_std": std, "scale": std if std > 0 else 1.0, "zero_variance": std == 0.0, "quantiles": {str(q): _quantile_type7(values, q) for q in (0.25, 0.5, 0.75)}}
            result[symbol][timeframe] = feature_rows
    return result


def normalize_feature(
    fit_state: FoldFeatureFitState | Mapping[str, Any],
    *,
    store: MultiTimeframeFeatureStore | Mapping[str, Any],
    binding: ContextParityBinding | None = None,
    symbol: str,
    timeframe: str,
    feature: str,
    value: float,
) -> float:
    state = validate_fold_feature_state(fit_state, store=store, binding=binding).to_dict()
    if symbol not in MARKETS or timeframe not in {row[0] for row in TIMEFRAMES} or feature not in FEATURES:
        raise FeatureStoreError("normalization key is outside the frozen feature inventory")
    number = _finite(value, "feature value")
    stats = state["statistics"][symbol][timeframe][feature]
    return (number - stats["mean"]) / stats["scale"]


def _aggregate(candles: Sequence[Candle], timeframe: str, kind: str, minutes: int | None) -> list[dict[str, Any]]:
    buckets: list[tuple[int, int, list[Candle]]] = []
    current_key: tuple[int, int] | None = None
    current: list[Candle] = []
    for candle in candles:
        start, end = _bucket_bounds(candle.open_time, kind, minutes)
        key = (start, end)
        if current_key is not None and key != current_key:
            buckets.append((current_key[0], current_key[1], current))
            current = []
        current_key = key
        current.append(candle)
    if current_key is not None:
        buckets.append((current_key[0], current_key[1], current))
    rows: list[dict[str, Any]] = []
    previous_close: float | None = None
    for start, end, source in buckets:
        expected = (end - start) // EXPECTED_STEP_MS
        if len(source) != expected or source[0].open_time != start or source[-1].open_time + EXPECTED_STEP_MS != end:
            continue
        opens = [float(row.open) for row in source]
        highs = [float(row.high) for row in source]
        lows = [float(row.low) for row in source]
        closes = [float(row.close) for row in source]
        volumes = [float(row.volume) for row in source]
        open_value, close_value = opens[0], closes[-1]
        high_value, low_value = max(highs), min(lows)
        span = high_value - low_value
        features = {
            "return_1": None if previous_close is None else close_value / previous_close - 1.0,
            "range_bps": (span / open_value) * 10_000.0,
            "body_bps": ((close_value - open_value) / open_value) * 10_000.0,
            "close_location": (close_value - low_value) / span if span > 0.0 else 0.5,
            "volume": math.fsum(volumes),
        }
        rows.append({"open_time_ms": start, "close_time_exclusive_ms": end, "source_minute_count": len(source), "open": open_value, "high": high_value, "low": low_value, "close": close_value, "volume": features["volume"], "features": features})
        previous_close = close_value
    return rows


def _validate_aggregate_rows(
    value: Any,
    timeframe: str,
    kind: str,
    minutes: int | None,
    source_first: int,
    source_last: int,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise FeatureStoreError(f"{timeframe} series must be a list")
    normalized: list[dict[str, Any]] = []
    previous_end: int | None = None
    previous_close: float | None = None
    for raw in value:
        row = dict(_mapping(raw, f"{timeframe} bar"))
        expected_keys = {"open_time_ms", "close_time_exclusive_ms", "source_minute_count", "open", "high", "low", "close", "volume", "features"}
        if set(row) != expected_keys:
            raise FeatureStoreError(f"{timeframe} bar fields are invalid")
        start = _minute_ms(row["open_time_ms"], "bar open")
        end = _minute_ms(row["close_time_exclusive_ms"], "bar close")
        expected_start, expected_end = _bucket_bounds(start, kind, minutes)
        if (start, end) != (expected_start, expected_end):
            raise FeatureStoreError(f"{timeframe} bar is not on its exact UTC bucket")
        count = _positive_int(row["source_minute_count"], "source_minute_count")
        if count != (end - start) // EXPECTED_STEP_MS:
            raise FeatureStoreError(f"{timeframe} bar is not a complete minute bucket")
        if start < source_first or end > source_last + EXPECTED_STEP_MS:
            raise FeatureStoreError(f"{timeframe} bar lies outside source context")
        if previous_end is not None and start <= previous_end - 1:
            raise FeatureStoreError(f"{timeframe} bars overlap or are unsorted")
        prices = {key: _finite(row[key], key) for key in ("open", "high", "low", "close")}
        volume = _finite(row["volume"], "volume")
        if (
            min(prices.values()) <= 0.0
            or volume < 0.0
            or prices["high"] < max(prices["open"], prices["low"], prices["close"])
            or prices["low"] > min(prices["open"], prices["high"], prices["close"])
        ):
            raise FeatureStoreError(f"{timeframe} OHLCV is invalid")
        features = dict(_mapping(row["features"], "features"))
        if set(features) != set(FEATURES):
            raise FeatureStoreError(f"{timeframe} feature fields are invalid")
        span = prices["high"] - prices["low"]
        expected_features = {
            "return_1": None if previous_close is None else prices["close"] / previous_close - 1.0,
            "range_bps": span / prices["open"] * 10_000.0,
            "body_bps": (prices["close"] - prices["open"]) / prices["open"] * 10_000.0,
            "close_location": (prices["close"] - prices["low"]) / span if span > 0.0 else 0.5,
            "volume": volume,
        }
        if features != expected_features:
            raise FeatureStoreError(f"{timeframe} features differ from exact bar recomputation")
        normalized.append({"open_time_ms": start, "close_time_exclusive_ms": end, "source_minute_count": count, **prices, "volume": volume, "features": expected_features})
        previous_end = end
        previous_close = prices["close"]
    return normalized


def _bucket_bounds(timestamp_ms: int, kind: str, minutes: int | None) -> tuple[int, int]:
    timestamp = _minute_ms(timestamp_ms, "source candle open_time")
    if kind == "fixed_utc":
        assert minutes is not None
        width = minutes * EXPECTED_STEP_MS
        start = timestamp - timestamp % width
        return start, start + width
    dt = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
    if kind == "calendar_utc_monday":
        start_dt = datetime(dt.year, dt.month, dt.day, tzinfo=UTC) - timedelta(days=dt.weekday())
        return _timestamp_ms(start_dt), _timestamp_ms(start_dt + timedelta(days=7))
    if kind == "calendar_utc_month":
        start_dt = datetime(dt.year, dt.month, 1, tzinfo=UTC)
        if dt.month == 12:
            end_dt = datetime(dt.year + 1, 1, 1, tzinfo=UTC)
        else:
            end_dt = datetime(dt.year, dt.month + 1, 1, tzinfo=UTC)
        return _timestamp_ms(start_dt), _timestamp_ms(end_dt)
    raise FeatureStoreError("unsupported timeframe bucket kind")


def _quantile_type7(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise FeatureStoreError("quantile requires observations")
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _market_series(context: AlignedMarketCandles) -> tuple[tuple[str, tuple[Candle, ...]], ...]:
    return (("ETHUSDC", context.ethusdc), ("BTCUSDC", context.btcusdc), ("ETHBTC", context.ethbtc))


def _utc_ms(value: Any, path: str) -> int:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FeatureStoreError(f"{path} must be canonical UTC text")
    try:
        dt = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FeatureStoreError(f"{path} must be canonical UTC text") from exc
    if dt.tzinfo != UTC:
        dt = dt.astimezone(UTC)
    return _timestamp_ms(dt)


def _timestamp_ms(value: datetime) -> int:
    return calendar.timegm(value.utctimetuple()) * 1000 + value.microsecond // 1000


def _minute_ms(value: Any, path: str) -> int:
    if type(value) is not int or value < 0 or value % EXPECTED_STEP_MS:
        raise FeatureStoreError(f"{path} must be a nonnegative UTC minute timestamp")
    return value


def _positive_int(value: Any, path: str) -> int:
    if type(value) is not int or value <= 0:
        raise FeatureStoreError(f"{path} must be a positive integer")
    return value


def _finite(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise FeatureStoreError(f"{path} must be finite")
    return float(value)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FeatureStoreError(f"{path} must be an object")
    return value


def _sha(value: Any, path: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise FeatureStoreError(f"{path} must be a lowercase SHA-256 digest")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _strict_loads(text: str) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise FeatureStoreError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=hook, parse_constant=lambda value: (_ for _ in ()).throw(FeatureStoreError(f"non-finite JSON constant: {value}")))


__all__ = [
    "COMPLETE", "CONTRACT_PATH", "CONTRACT_SCHEMA_VERSION", "CONTRACT_VERSION",
    "FEATURES", "FIT_STATE_SCHEMA_VERSION", "FeatureStoreError", "FoldFeatureFitState",
    "INSUFFICIENT_WARMUP", "MARKETS", "MultiTimeframeFeatureStore",
    "STORE_SCHEMA_VERSION", "TIMEFRAMES", "build_feature_store",
    "build_feature_store_identity_payload", "feature_snapshot_at", "fit_fold_feature_state",
    "load_feature_store_contract", "normalize_feature", "validate_feature_store",
    "validate_feature_store_against_binding", "validate_fold_feature_state",
]
