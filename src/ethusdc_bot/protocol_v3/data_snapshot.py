"""Dynamic three-market Protocol v3 data snapshot and warmup contract.

Task 5 reuses the existing read-only Binance Spot ZIP loader and adds the
fail-closed layer needed by Protocol v3: a common fully audited UTC-day
watermark, the exact 1,095-day fit/process interval, dynamic feature warmup,
three-market parity, zero-volume accounting, and an immutable SHA-256-bound
snapshot.  It does not download data, call Binance, calculate features, run a
backtest, create orders, or unlock Paper/Testtrade/Live.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
from typing import Any, Mapping, Sequence
import zipfile

from ethusdc_bot.backtest.data_loader import (
    Candle,
    DataLoadError,
    _day_from_name,
    _paired_zip_files,
    _read_zip,
    _validate_raw_root,
)
from ethusdc_bot.protocol_v3.boundaries import (
    PROCESS_OOS_DAYS,
    TRAINING_DAYS_PER_ORIGIN,
    build_monthly_process_boundary_plan,
    resolve_process_end_exclusive,
    validate_monthly_process_boundary_plan,
)

DATA_SNAPSHOT_CONTRACT_PATH = Path("configs/protocol_v3_data_snapshot_contract.json")
DATA_SNAPSHOT_CONTRACT_SCHEMA = "protocol_v3_data_snapshot_contract_v1"
DATA_SNAPSHOT_CONTRACT_VERSION = "dynamic_three_market_snapshot_v1"
DATA_SNAPSHOT_SCHEMA_VERSION = "protocol_v3_three_market_data_snapshot_v1"
SOURCE_BAR_SECONDS = 60
MINUTES_PER_DAY = 1440
FIT_PROCESS_DAYS = TRAINING_DAYS_PER_ORIGIN + PROCESS_OOS_DAYS
MARKETS = ("ETHUSDC", "BTCUSDC", "ETHBTC")
MARKET_ROLES = {
    "ETHUSDC": ("trade_market", True),
    "BTCUSDC": ("context_only", False),
    "ETHBTC": ("context_only", False),
}
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

_CANONICAL_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: dict[str, Any] = {
    "schema_version": DATA_SNAPSHOT_CONTRACT_SCHEMA,
    "protocol_version": "3.0.0",
    "contract_version": DATA_SNAPSHOT_CONTRACT_VERSION,
    "timezone": "UTC",
    "source_interval": "1m",
    "source_bar_seconds": SOURCE_BAR_SECONDS,
    "full_utc_day_minutes": MINUTES_PER_DAY,
    "fit_process_days": FIT_PROCESS_DAYS,
    "markets": [
        {"symbol": "ETHUSDC", "role": "trade_market", "may_trigger_orders": True},
        {"symbol": "BTCUSDC", "role": "context_only", "may_trigger_orders": False},
        {"symbol": "ETHBTC", "role": "context_only", "may_trigger_orders": False},
    ],
    "watermark_policy": {
        "rule": "latest_common_fully_audited_utc_day",
        "process_end_rule": "task2_latest_supported_monthly_anchor",
        "required_complete_markets": 3,
        "trailing_incomplete_days_may_be_ignored": True,
        "incomplete_day_inside_snapshot_blocks": True,
    },
    "warmup_policy": {
        "rule": "max_active_lookback_seconds_plus_one_smallest_source_bar",
        "active_lookback_set_required": True,
        "all_three_markets_must_be_represented": True,
        "warmup_may_feed_features_only": True,
        "warmup_may_feed_scalers_quantiles_labels_or_pnl": False,
        "missing_warmup_blocks": True,
    },
    "quality_policy": {
        "exact_minute_grid_required": True,
        "duplicate_minutes_allowed": False,
        "gaps_allowed": False,
        "positive_prices_required": True,
        "ohlc_consistency_required": True,
        "negative_volume_allowed": False,
        "zero_volume_bars": "count_and_expose",
        "all_zero_volume_day_blocks": True,
    },
    "snapshot_policy": {
        "canonical_json": True,
        "sha256_bound": True,
        "archive_inventory_digest_required": True,
        "market_content_digest_required": True,
        "immutable_write_only": True,
    },
    "safety": _CANONICAL_SAFETY,
}


class DataSnapshotError(RuntimeError):
    """Raised when a Protocol v3 market snapshot is incomplete or contradictory."""


@dataclass(frozen=True)
class ActiveLookback:
    """One already-approved causal lookback used by a market feature/context row."""

    name: str
    market: str
    bars: int
    bar_seconds: int

    @property
    def duration_seconds(self) -> int:
        return self.bars * self.bar_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "market": self.market,
            "bars": self.bars,
            "bar_seconds": self.bar_seconds,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class WarmupPlan:
    """Exact Protocol v3 warmup computed from the frozen active lookback set."""

    active_lookbacks: tuple[ActiveLookback, ...]
    max_lookback_seconds: int
    smallest_source_bar_seconds: int
    warmup_duration_seconds: int

    @property
    def warmup_source_bars(self) -> int:
        return self.warmup_duration_seconds // self.smallest_source_bar_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": "max_active_lookback_seconds_plus_one_smallest_source_bar",
            "active_lookbacks": [lookback.to_dict() for lookback in self.active_lookbacks],
            "max_lookback_seconds": self.max_lookback_seconds,
            "smallest_source_bar_seconds": self.smallest_source_bar_seconds,
            "warmup_duration_seconds": self.warmup_duration_seconds,
            "warmup_source_bars": self.warmup_source_bars,
            "warmup_may_feed_features_only": True,
            "warmup_may_feed_scalers_quantiles_labels_or_pnl": False,
        }


@dataclass(frozen=True)
class MarketDayAudit:
    symbol: str
    day: date
    candle_count: int
    first_open_time_ms: int
    last_open_time_ms: int
    zero_volume_candles: int
    timestamp_grid_sha256: str
    content_sha256: str
    zip_sha256: str
    checksum_sha256: str

    def to_digest_row(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "candle_count": self.candle_count,
            "first_open_time_ms": self.first_open_time_ms,
            "last_open_time_ms": self.last_open_time_ms,
            "zero_volume_candles": self.zero_volume_candles,
            "timestamp_grid_sha256": self.timestamp_grid_sha256,
            "content_sha256": self.content_sha256,
            "zip_sha256": self.zip_sha256,
            "checksum_sha256": self.checksum_sha256,
        }


@dataclass(frozen=True)
class FrozenDataSnapshot:
    canonical_payload_json: str
    snapshot_sha256: str

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_payload_json)

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        payload["snapshot_sha256"] = self.snapshot_sha256
        return payload


def load_data_snapshot_contract(
    repo_root: str | Path | None = None,
    *,
    contract_path: str | Path | None = None,
) -> dict[str, Any]:
    root = _resolve_repo_root(repo_root)
    path = Path(contract_path) if contract_path is not None else root / DATA_SNAPSHOT_CONTRACT_PATH
    if not path.is_absolute():
        path = root / path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataSnapshotError(f"data snapshot contract is missing or invalid: {path}") from exc
    validate_data_snapshot_contract(value)
    return value


def validate_data_snapshot_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize_json(value) != _CANONICAL_CONTRACT:
        raise DataSnapshotError("Protocol v3 data snapshot contract is not canonical")


def build_warmup_plan(active_lookbacks: Sequence[Mapping[str, Any] | ActiveLookback]) -> WarmupPlan:
    if not isinstance(active_lookbacks, Sequence) or isinstance(active_lookbacks, (str, bytes)):
        raise DataSnapshotError("active_lookbacks must be a non-empty sequence")
    normalized = tuple(sorted((_normalize_lookback(value) for value in active_lookbacks), key=lambda row: (row.market, row.name)))
    if not normalized:
        raise DataSnapshotError("active_lookback_set_required")
    keys = [(row.market, row.name) for row in normalized]
    if len(set(keys)) != len(keys):
        raise DataSnapshotError("active lookback names must be unique within each market")
    represented = {row.market for row in normalized}
    if represented != set(MARKETS):
        raise DataSnapshotError("active lookbacks must represent ETHUSDC, BTCUSDC, and ETHBTC")
    maximum = max(row.duration_seconds for row in normalized)
    warmup = maximum + SOURCE_BAR_SECONDS
    if warmup % SOURCE_BAR_SECONDS != 0:
        raise DataSnapshotError("warmup duration must align to the 1m source grid")
    return WarmupPlan(
        active_lookbacks=normalized,
        max_lookback_seconds=maximum,
        smallest_source_bar_seconds=SOURCE_BAR_SECONDS,
        warmup_duration_seconds=warmup,
    )


def build_three_market_data_snapshot(
    raw_root: str | Path,
    active_lookbacks: Sequence[Mapping[str, Any] | ActiveLookback],
    *,
    repo_root: str | Path | None = None,
    contract_path: str | Path | None = None,
) -> FrozenDataSnapshot:
    """Audit local ZIP pairs and freeze the newest supported three-market snapshot."""

    contract = load_data_snapshot_contract(repo_root, contract_path=contract_path)
    warmup = build_warmup_plan(active_lookbacks)
    try:
        validated_root = _validate_raw_root(Path(raw_root))
    except DataLoadError as exc:
        raise DataSnapshotError(str(exc)) from exc
    inspector = _ZipMarketInspector(validated_root)
    files_by_market = {symbol: inspector.files_by_day(symbol) for symbol in MARKETS}
    common_file_days = set.intersection(*(set(rows) for rows in files_by_market.values()))
    if not common_file_days:
        raise DataSnapshotError("no common paired 1m UTC day exists across all three markets")

    audit_cache: dict[tuple[str, date], MarketDayAudit] = {}
    trailing_rejections: list[dict[str, str]] = []
    latest_common_complete_day: date | None = None
    for candidate in sorted(common_file_days, reverse=True):
        candidate_errors: dict[str, str] = {}
        for symbol in MARKETS:
            try:
                _audit_cached(inspector, files_by_market, audit_cache, symbol, candidate)
            except DataSnapshotError as exc:
                candidate_errors[symbol] = str(exc)
        if not candidate_errors:
            latest_common_complete_day = candidate
            break
        trailing_rejections.append(
            {
                "day": candidate.isoformat(),
                "reason": "; ".join(f"{symbol}: {candidate_errors[symbol]}" for symbol in sorted(candidate_errors)),
            }
        )
    if latest_common_complete_day is None:
        raise DataSnapshotError("no fully audited common UTC day exists across all three markets")

    try:
        process_end = resolve_process_end_exclusive(latest_common_complete_day)
        boundary_plan = build_monthly_process_boundary_plan(process_end)
        validate_monthly_process_boundary_plan(boundary_plan)
    except ValueError as exc:
        raise DataSnapshotError(f"latest common day cannot support Task-2 boundaries: {exc}") from exc

    fit_process_start = boundary_plan.origins[0].training_start_inclusive
    if (process_end - fit_process_start).days != FIT_PROCESS_DAYS:
        raise DataSnapshotError("Task-2 boundary plan does not expose exactly 1,095 fit/process days")
    warmup_start = _utc_midnight(fit_process_start) - timedelta(seconds=warmup.warmup_duration_seconds)
    audited_start_day = warmup_start.date()
    required_days = tuple(_iter_days(audited_start_day, process_end))
    if not required_days:
        raise DataSnapshotError("required raw-data interval is empty")

    audits_by_market: dict[str, tuple[MarketDayAudit, ...]] = {}
    for symbol in MARKETS:
        missing = [day for day in required_days if day not in files_by_market[symbol]]
        if missing:
            preview = ", ".join(day.isoformat() for day in missing[:3])
            raise DataSnapshotError(
                f"{symbol} is missing required warmup/fit/process UTC days: {preview}"
            )
        rows = tuple(
            _audit_cached(inspector, files_by_market, audit_cache, symbol, day)
            for day in required_days
        )
        audits_by_market[symbol] = rows

    return _assemble_snapshot(
        contract=contract,
        warmup=warmup,
        latest_common_complete_day=latest_common_complete_day,
        process_end=process_end,
        fit_process_start=fit_process_start,
        warmup_start=warmup_start,
        audited_start_day=audited_start_day,
        audits_by_market=audits_by_market,
        trailing_rejections=tuple(trailing_rejections),
    )


def validate_frozen_data_snapshot(
    snapshot: FrozenDataSnapshot | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    contract_path: str | Path | None = None,
) -> None:
    if isinstance(snapshot, FrozenDataSnapshot):
        payload = snapshot.payload()
        snapshot_sha256 = snapshot.snapshot_sha256
        canonical = snapshot.canonical_payload_json
    elif isinstance(snapshot, Mapping):
        raw = dict(snapshot)
        snapshot_sha256 = raw.pop("snapshot_sha256", None)
        payload = raw
        canonical = _canonical_json(payload)
    else:
        raise DataSnapshotError("frozen data snapshot must be an object")
    if not isinstance(snapshot_sha256, str) or snapshot_sha256 != hashlib.sha256(canonical.encode("utf-8")).hexdigest():
        raise DataSnapshotError("data snapshot digest mismatch")
    if _canonical_json(payload) != canonical:
        raise DataSnapshotError("data snapshot payload is not canonical")

    contract = load_data_snapshot_contract(repo_root, contract_path=contract_path)
    required_top = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "contract_sha256",
        "timezone",
        "availability",
        "boundary",
        "warmup",
        "raw_interval",
        "market_data",
        "common_minute_grid_sha256",
        "trailing_incomplete_common_days",
        "quality_status",
        "safety",
    }
    if set(payload) != required_top:
        raise DataSnapshotError("data snapshot fields are missing or unexpected")
    if payload.get("schema_version") != DATA_SNAPSHOT_SCHEMA_VERSION:
        raise DataSnapshotError("data snapshot schema is invalid")
    if payload.get("protocol_version") != "3.0.0" or payload.get("contract_version") != DATA_SNAPSHOT_CONTRACT_VERSION:
        raise DataSnapshotError("data snapshot protocol/contract version is invalid")
    if payload.get("contract_sha256") != _sha256_json(contract):
        raise DataSnapshotError("data snapshot contract digest mismatch")
    if payload.get("timezone") != "UTC" or payload.get("safety") != _CANONICAL_SAFETY:
        raise DataSnapshotError("data snapshot timezone or safety locks are invalid")
    if payload.get("quality_status") != "usable_for_protocol_v3_snapshot":
        raise DataSnapshotError("data snapshot is not marked usable")

    availability = _require_mapping(payload.get("availability"), "availability")
    latest = _parse_day(availability.get("latest_common_complete_day"), "latest_common_complete_day")
    if availability.get("complete_market_count") != len(MARKETS):
        raise DataSnapshotError("availability must contain all three complete markets")

    boundary = _require_mapping(payload.get("boundary"), "boundary")
    process_end = _parse_day(boundary.get("process_end_exclusive"), "process_end_exclusive")
    if process_end != resolve_process_end_exclusive(latest):
        raise DataSnapshotError("process_end_exclusive is not derived from the common watermark")
    plan = build_monthly_process_boundary_plan(process_end)
    validate_monthly_process_boundary_plan(plan)
    fit_start = _parse_day(boundary.get("fit_process_start_inclusive"), "fit_process_start_inclusive")
    if fit_start != plan.origins[0].training_start_inclusive:
        raise DataSnapshotError("fit/process start conflicts with Task-2 boundaries")
    if boundary.get("fit_process_days") != FIT_PROCESS_DAYS:
        raise DataSnapshotError("fit/process day count must equal 1,095")
    if boundary.get("snapshot_as_of_day") != (process_end - timedelta(days=1)).isoformat():
        raise DataSnapshotError("snapshot_as_of_day is invalid")

    warmup_payload = _require_mapping(payload.get("warmup"), "warmup")
    lookbacks_raw = warmup_payload.get("active_lookbacks")
    if not isinstance(lookbacks_raw, list):
        raise DataSnapshotError("snapshot active_lookbacks must be a list")
    warmup = build_warmup_plan(lookbacks_raw)
    expected_warmup = warmup.to_dict()
    for key, value in expected_warmup.items():
        if warmup_payload.get(key) != value:
            raise DataSnapshotError(f"snapshot warmup field conflicts with active lookbacks: {key}")
    warmup_start = _parse_utc(warmup_payload.get("warmup_start_inclusive"), "warmup_start_inclusive")
    if warmup_start != _utc_midnight(fit_start) - timedelta(seconds=warmup.warmup_duration_seconds):
        raise DataSnapshotError("warmup_start_inclusive is invalid")

    raw_interval = _require_mapping(payload.get("raw_interval"), "raw_interval")
    if raw_interval.get("start_inclusive") != _utc_text(warmup_start):
        raise DataSnapshotError("raw interval start is invalid")
    if raw_interval.get("end_exclusive") != _utc_text(_utc_midnight(process_end)):
        raise DataSnapshotError("raw interval end is invalid")
    audited_start_day = _parse_day(raw_interval.get("audited_full_day_start"), "audited_full_day_start")
    expected_full_days = (process_end - audited_start_day).days
    if expected_full_days <= FIT_PROCESS_DAYS:
        raise DataSnapshotError("snapshot has no complete warmup day envelope")
    if raw_interval.get("audited_full_day_count") != expected_full_days:
        raise DataSnapshotError("audited full-day count is inconsistent")
    expected_required_minutes = int((_utc_midnight(process_end) - warmup_start).total_seconds() // SOURCE_BAR_SECONDS)
    if raw_interval.get("required_interval_minutes") != expected_required_minutes:
        raise DataSnapshotError("required raw interval minute count is inconsistent")
    expected_envelope_minutes = expected_full_days * MINUTES_PER_DAY
    if raw_interval.get("audited_envelope_minutes") != expected_envelope_minutes:
        raise DataSnapshotError("audited envelope minute count is inconsistent")

    market_data = payload.get("market_data")
    if not isinstance(market_data, list) or len(market_data) != len(MARKETS):
        raise DataSnapshotError("data snapshot must contain exactly three market rows")
    observed_symbols = [row.get("symbol") for row in market_data if isinstance(row, dict)]
    if observed_symbols != list(MARKETS):
        raise DataSnapshotError("market rows must be ordered ETHUSDC, BTCUSDC, ETHBTC")
    grid_digests: set[str] = set()
    for row in market_data:
        market = _require_mapping(row, "market_data[]")
        symbol = str(market.get("symbol"))
        role, may_trigger = MARKET_ROLES[symbol]
        if market.get("role") != role or market.get("may_trigger_orders") is not may_trigger:
            raise DataSnapshotError(f"market role is invalid for {symbol}")
        if market.get("source_interval") != "1m" or market.get("source_bar_seconds") != SOURCE_BAR_SECONDS:
            raise DataSnapshotError(f"source interval is invalid for {symbol}")
        if market.get("audited_full_day_count") != expected_full_days:
            raise DataSnapshotError(f"audited day count is invalid for {symbol}")
        if market.get("candle_count") != expected_envelope_minutes:
            raise DataSnapshotError(f"candle count is invalid for {symbol}")
        if market.get("first_complete_day") != audited_start_day.isoformat():
            raise DataSnapshotError(f"first complete day is invalid for {symbol}")
        if market.get("last_complete_day") != (process_end - timedelta(days=1)).isoformat():
            raise DataSnapshotError(f"last complete day is invalid for {symbol}")
        zero_count = market.get("zero_volume_candles")
        if isinstance(zero_count, bool) or not isinstance(zero_count, int) or not 0 <= zero_count < expected_envelope_minutes:
            raise DataSnapshotError(f"zero-volume count is invalid for {symbol}")
        zero_days = market.get("zero_volume_days")
        if not isinstance(zero_days, list) or any(not isinstance(day, str) for day in zero_days):
            raise DataSnapshotError(f"zero-volume day list is invalid for {symbol}")
        for digest_key in (
            "timestamp_grid_sha256",
            "market_content_sha256",
            "archive_inventory_sha256",
            "complete_utc_days_sha256",
        ):
            digest = market.get(digest_key)
            if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
                raise DataSnapshotError(f"{digest_key} is invalid for {symbol}")
        grid_digests.add(str(market["timestamp_grid_sha256"]))
    if len(grid_digests) != 1 or payload.get("common_minute_grid_sha256") not in grid_digests:
        raise DataSnapshotError("three markets do not share one exact minute grid digest")

    trailing = payload.get("trailing_incomplete_common_days")
    if not isinstance(trailing, list):
        raise DataSnapshotError("trailing incomplete day diagnostics must be a list")
    for row in trailing:
        item = _require_mapping(row, "trailing_incomplete_common_days[]")
        if set(item) != {"day", "reason"}:
            raise DataSnapshotError("trailing incomplete day diagnostics are invalid")
        _parse_day(item["day"], "trailing incomplete day")
        _required_text(item.get("reason"), "trailing incomplete reason")


def write_frozen_data_snapshot(snapshot: FrozenDataSnapshot, path: str | Path) -> Path:
    validate_frozen_data_snapshot(snapshot)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot.to_dict(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(target, flags, 0o600)
    except FileExistsError as exc:
        raise DataSnapshotError("frozen data snapshot path already exists and cannot be overwritten") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise
    return target


def read_frozen_data_snapshot(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
    contract_path: str | Path | None = None,
) -> FrozenDataSnapshot:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DataSnapshotError(f"frozen data snapshot is missing or invalid: {source}") from exc
    if not isinstance(value, dict):
        raise DataSnapshotError("frozen data snapshot root must be an object")
    digest = value.pop("snapshot_sha256", None)
    if not isinstance(digest, str):
        raise DataSnapshotError("frozen data snapshot digest is missing")
    snapshot = FrozenDataSnapshot(_canonical_json(value), digest)
    validate_frozen_data_snapshot(snapshot, repo_root=repo_root, contract_path=contract_path)
    return snapshot


class _ZipMarketInspector:
    def __init__(self, raw_root: Path) -> None:
        self.raw_root = raw_root

    def files_by_day(self, symbol: str) -> dict[date, Path]:
        folder = self.raw_root / "raw" / "binance" / "spot" / symbol / "klines" / "1m"
        if not folder.is_dir():
            raise DataSnapshotError(f"{symbol} 1m kline folder missing: {folder}")
        try:
            paired = _paired_zip_files(folder, symbol)
        except DataLoadError as exc:
            raise DataSnapshotError(str(exc)) from exc
        if not paired:
            raise DataSnapshotError(f"no paired {symbol} 1m ZIP/CHECKSUM files found")
        result: dict[date, Path] = {}
        for path in paired:
            day = _day_from_name(path.name)
            if day is None:
                raise DataSnapshotError(f"{symbol} ZIP filename has no exact UTC day: {path.name}")
            if day in result:
                raise DataSnapshotError(f"duplicate {symbol} daily ZIP for {day.isoformat()}")
            result[day] = path
        return result

    def audit_day(self, symbol: str, day: date, zip_path: Path) -> MarketDayAudit:
        try:
            candles = _read_zip(zip_path, symbol)
        except (DataLoadError, OSError, UnicodeError, zipfile.BadZipFile) as exc:
            raise DataSnapshotError(f"invalid {symbol} day {day.isoformat()}: {exc}") from exc
        if len(candles) != MINUTES_PER_DAY:
            raise DataSnapshotError(
                f"{symbol} day {day.isoformat()} has {len(candles)} candles instead of 1,440"
            )
        day_start_ms = int(_utc_midnight(day).timestamp() * 1000)
        expected_times = tuple(day_start_ms + minute * SOURCE_BAR_SECONDS * 1000 for minute in range(MINUTES_PER_DAY))
        observed_times = tuple(candle.open_time for candle in candles)
        if observed_times != expected_times:
            raise DataSnapshotError(f"{symbol} day {day.isoformat()} is not the exact 1,440-minute UTC grid")
        zero_count = sum(1 for candle in candles if candle.volume == 0.0)
        if zero_count == MINUTES_PER_DAY:
            raise DataSnapshotError(f"{symbol} day {day.isoformat()} has zero volume in every candle")
        timestamp_hasher = hashlib.sha256()
        content_hasher = hashlib.sha256()
        for candle in candles:
            _validate_candle_again(candle, symbol, day)
            timestamp_hasher.update(struct.pack(">q", candle.open_time))
            content_hasher.update(
                struct.pack(">qddddd", candle.open_time, candle.open, candle.high, candle.low, candle.close, candle.volume)
            )
        checksum_path = zip_path.with_name(zip_path.name + ".CHECKSUM")
        if not checksum_path.is_file() or checksum_path.stat().st_size <= 0:
            raise DataSnapshotError(f"matching non-empty CHECKSUM missing for {zip_path.name}")
        return MarketDayAudit(
            symbol=symbol,
            day=day,
            candle_count=len(candles),
            first_open_time_ms=observed_times[0],
            last_open_time_ms=observed_times[-1],
            zero_volume_candles=zero_count,
            timestamp_grid_sha256=timestamp_hasher.hexdigest(),
            content_sha256=content_hasher.hexdigest(),
            zip_sha256=_sha256_file(zip_path),
            checksum_sha256=_sha256_file(checksum_path),
        )


def _assemble_snapshot(
    *,
    contract: Mapping[str, Any],
    warmup: WarmupPlan,
    latest_common_complete_day: date,
    process_end: date,
    fit_process_start: date,
    warmup_start: datetime,
    audited_start_day: date,
    audits_by_market: Mapping[str, tuple[MarketDayAudit, ...]],
    trailing_rejections: tuple[dict[str, str], ...],
) -> FrozenDataSnapshot:
    expected_days = tuple(_iter_days(audited_start_day, process_end))
    if len(expected_days) <= FIT_PROCESS_DAYS:
        raise DataSnapshotError("warmup does not extend before the 1,095-day fit/process interval")
    market_rows: list[dict[str, Any]] = []
    grid_digests: set[str] = set()
    for symbol in MARKETS:
        audits = audits_by_market.get(symbol)
        if audits is None or tuple(row.day for row in audits) != expected_days:
            raise DataSnapshotError(f"{symbol} audit days are missing, duplicated, or out of order")
        if any(row.symbol != symbol or row.candle_count != MINUTES_PER_DAY for row in audits):
            raise DataSnapshotError(f"{symbol} day audit is inconsistent")
        day_rows = [row.to_digest_row() for row in audits]
        timestamp_grid_sha256 = _sha256_json(
            [{"day": row.day.isoformat(), "timestamp_grid_sha256": row.timestamp_grid_sha256} for row in audits]
        )
        grid_digests.add(timestamp_grid_sha256)
        role, may_trigger = MARKET_ROLES[symbol]
        market_rows.append(
            {
                "symbol": symbol,
                "role": role,
                "may_trigger_orders": may_trigger,
                "source_interval": "1m",
                "source_bar_seconds": SOURCE_BAR_SECONDS,
                "first_complete_day": expected_days[0].isoformat(),
                "last_complete_day": expected_days[-1].isoformat(),
                "audited_full_day_count": len(expected_days),
                "candle_count": len(expected_days) * MINUTES_PER_DAY,
                "zero_volume_candles": sum(row.zero_volume_candles for row in audits),
                "zero_volume_days": [row.day.isoformat() for row in audits if row.zero_volume_candles > 0],
                "timestamp_grid_sha256": timestamp_grid_sha256,
                "market_content_sha256": _sha256_json(
                    [{"day": row.day.isoformat(), "content_sha256": row.content_sha256} for row in audits]
                ),
                "archive_inventory_sha256": _sha256_json(
                    [
                        {
                            "day": row.day.isoformat(),
                            "zip_sha256": row.zip_sha256,
                            "checksum_sha256": row.checksum_sha256,
                        }
                        for row in audits
                    ]
                ),
                "complete_utc_days_sha256": _sha256_json([row.day.isoformat() for row in audits]),
                "day_audit_digest": _sha256_json(day_rows),
            }
        )
    if len(grid_digests) != 1:
        raise DataSnapshotError("three markets do not share the exact same audited minute grid")

    raw_end = _utc_midnight(process_end)
    required_minutes = int((raw_end - warmup_start).total_seconds() // SOURCE_BAR_SECONDS)
    envelope_minutes = len(expected_days) * MINUTES_PER_DAY
    payload = {
        "schema_version": DATA_SNAPSHOT_SCHEMA_VERSION,
        "protocol_version": "3.0.0",
        "contract_version": DATA_SNAPSHOT_CONTRACT_VERSION,
        "contract_sha256": _sha256_json(contract),
        "timezone": "UTC",
        "availability": {
            "latest_common_complete_day": latest_common_complete_day.isoformat(),
            "complete_market_count": len(MARKETS),
            "markets": list(MARKETS),
            "rule": "latest_common_fully_audited_utc_day",
        },
        "boundary": {
            "process_end_exclusive": process_end.isoformat(),
            "snapshot_as_of_day": (process_end - timedelta(days=1)).isoformat(),
            "fit_process_start_inclusive": fit_process_start.isoformat(),
            "fit_process_days": FIT_PROCESS_DAYS,
            "training_days_per_origin": TRAINING_DAYS_PER_ORIGIN,
            "process_oos_days": PROCESS_OOS_DAYS,
            "process_end_rule": "task2_latest_supported_monthly_anchor",
        },
        "warmup": {
            **warmup.to_dict(),
            "warmup_start_inclusive": _utc_text(warmup_start),
            "warmup_start_day": warmup_start.date().isoformat(),
        },
        "raw_interval": {
            "start_inclusive": _utc_text(warmup_start),
            "end_exclusive": _utc_text(raw_end),
            "audited_full_day_start": audited_start_day.isoformat(),
            "audited_full_day_end_inclusive": (process_end - timedelta(days=1)).isoformat(),
            "audited_full_day_count": len(expected_days),
            "required_interval_minutes": required_minutes,
            "audited_envelope_minutes": envelope_minutes,
            "extra_leading_audited_minutes": envelope_minutes - required_minutes,
        },
        "market_data": market_rows,
        "common_minute_grid_sha256": next(iter(grid_digests)),
        "trailing_incomplete_common_days": list(trailing_rejections),
        "quality_status": "usable_for_protocol_v3_snapshot",
        "safety": _CANONICAL_SAFETY,
    }
    canonical = _canonical_json(payload)
    snapshot = FrozenDataSnapshot(
        canonical_payload_json=canonical,
        snapshot_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )
    validate_frozen_data_snapshot(snapshot)
    return snapshot


def _audit_cached(
    inspector: _ZipMarketInspector,
    files_by_market: Mapping[str, Mapping[date, Path]],
    cache: dict[tuple[str, date], MarketDayAudit],
    symbol: str,
    day: date,
) -> MarketDayAudit:
    key = (symbol, day)
    if key not in cache:
        path = files_by_market[symbol].get(day)
        if path is None:
            raise DataSnapshotError(f"{symbol} has no paired archive for {day.isoformat()}")
        cache[key] = inspector.audit_day(symbol, day, path)
    return cache[key]


def _normalize_lookback(value: Mapping[str, Any] | ActiveLookback) -> ActiveLookback:
    if isinstance(value, ActiveLookback):
        row = value
    elif isinstance(value, Mapping):
        if set(value) not in ({"name", "market", "bars", "bar_seconds"}, {"name", "market", "bars", "bar_seconds", "duration_seconds"}):
            raise DataSnapshotError("active lookback fields are missing or unexpected")
        row = ActiveLookback(
            name=_required_text(value.get("name"), "lookback name"),
            market=_required_text(value.get("market"), "lookback market").upper(),
            bars=value.get("bars"),  # type: ignore[arg-type]
            bar_seconds=value.get("bar_seconds"),  # type: ignore[arg-type]
        )
        if "duration_seconds" in value and value.get("duration_seconds") != row.duration_seconds:
            raise DataSnapshotError("lookback duration_seconds is inconsistent")
    else:
        raise DataSnapshotError("active lookback must be an object")
    if row.market not in MARKETS:
        raise DataSnapshotError(f"lookback market must be one of {MARKETS}")
    if isinstance(row.bars, bool) or not isinstance(row.bars, int) or row.bars <= 0:
        raise DataSnapshotError("lookback bars must be a positive integer")
    if isinstance(row.bar_seconds, bool) or not isinstance(row.bar_seconds, int) or row.bar_seconds < SOURCE_BAR_SECONDS:
        raise DataSnapshotError("lookback bar_seconds must be at least 60")
    if row.bar_seconds % SOURCE_BAR_SECONDS != 0:
        raise DataSnapshotError("lookback bar_seconds must align to the 1m source grid")
    if not math.isfinite(float(row.duration_seconds)) or row.duration_seconds <= 0:
        raise DataSnapshotError("lookback duration is invalid")
    return row


def _validate_candle_again(candle: Candle, symbol: str, day: date) -> None:
    values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
    if any(not math.isfinite(value) for value in values):
        raise DataSnapshotError(f"{symbol} day {day.isoformat()} contains non-finite OHLCV")
    if min(candle.open, candle.high, candle.low, candle.close) <= 0:
        raise DataSnapshotError(f"{symbol} day {day.isoformat()} contains non-positive price")
    if candle.volume < 0:
        raise DataSnapshotError(f"{symbol} day {day.isoformat()} contains negative volume")
    if candle.high < max(candle.open, candle.close) or candle.low > min(candle.open, candle.close) or candle.high < candle.low:
        raise DataSnapshotError(f"{symbol} day {day.isoformat()} contains inconsistent OHLC")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DataSnapshotError(f"snapshot source file is unreadable: {path}") from exc
    return digest.hexdigest()


def _resolve_repo_root(repo_root: str | Path | None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[3]
    try:
        return root.resolve(strict=True)
    except OSError as exc:
        raise DataSnapshotError(f"repository root is missing or unreadable: {root}") from exc


def _iter_days(start: date, end_exclusive: date):
    current = start
    while current < end_exclusive:
        yield current
        current += timedelta(days=1)


def _utc_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _utc_text(value: datetime) -> str:
    if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
        raise DataSnapshotError("snapshot datetime is not UTC")
    return value.isoformat().replace("+00:00", "Z")


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise DataSnapshotError(f"{field} must be an ISO UTC datetime")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataSnapshotError(f"{field} must be an ISO UTC datetime") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise DataSnapshotError(f"{field} must be UTC")
    return parsed.astimezone(UTC)


def _parse_day(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise DataSnapshotError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DataSnapshotError(f"{field} must be an ISO date") from exc


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataSnapshotError(f"{field} must be a non-empty string")
    return value.strip()


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DataSnapshotError(f"{field} must be an object")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _normalize_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise DataSnapshotError("non-finite number is forbidden in snapshot JSON")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise DataSnapshotError("snapshot JSON object keys must be strings")
            result[key] = _normalize_json(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    raise DataSnapshotError(f"unsupported snapshot JSON value: {type(value).__name__}")


__all__ = [
    "DATA_SNAPSHOT_CONTRACT_PATH",
    "DATA_SNAPSHOT_CONTRACT_SCHEMA",
    "DATA_SNAPSHOT_CONTRACT_VERSION",
    "DATA_SNAPSHOT_SCHEMA_VERSION",
    "FIT_PROCESS_DAYS",
    "MARKETS",
    "MINUTES_PER_DAY",
    "SOURCE_BAR_SECONDS",
    "ActiveLookback",
    "DataSnapshotError",
    "FrozenDataSnapshot",
    "MarketDayAudit",
    "WarmupPlan",
    "build_three_market_data_snapshot",
    "build_warmup_plan",
    "load_data_snapshot_contract",
    "read_frozen_data_snapshot",
    "validate_data_snapshot_contract",
    "validate_frozen_data_snapshot",
    "write_frozen_data_snapshot",
]
