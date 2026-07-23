"""Protocol v3 Exchange-Info snapshots and complete run fingerprints.

Task 6 freezes the public Binance Spot ETHUSDC symbol filters and binds every
identity that may affect a Protocol v3 run. It does not call Binance, use
private/account data, calculate order quantities, simulate fills, create orders,
or unlock Paper/Testtrade/Live.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, Mapping

from .data_snapshot import FrozenDataSnapshot, validate_frozen_data_snapshot
from .pipeline import PipelineGeneration, validate_pipeline_generation
from .trial_ledger import (
    PERMANENT_TRIAL_COUNTER_NAMESPACE,
    TrialLedgerSnapshot,
    read_trial_ledger,
)

RUN_IDENTITY_CONTRACT_PATH = Path("configs/protocol_v3_run_identity_contract.json")
RUN_IDENTITY_CONTRACT_SCHEMA = "protocol_v3_run_identity_contract_v2"
EXCHANGE_INFO_CONTRACT_VERSION = "binance_spot_ethusdc_exchange_info_snapshot_v1"
RUN_FINGERPRINT_CONTRACT_VERSION = "protocol_v3_complete_run_fingerprint_v2"
EXCHANGE_INFO_SNAPSHOT_SCHEMA = "protocol_v3_exchange_info_snapshot_v1"
RUN_FINGERPRINT_SCHEMA = "protocol_v3_run_fingerprint_v2"
RUN_FINGERPRINT_PREFIX = "protocol_v3_run_sha256"
CONTEXT_IDENTITY_PREFIX = "protocol_v3_context_sha256"

if TYPE_CHECKING:
    from .context_parity import ContextParityBinding

_COMPONENT_MAP = {
    "features": "feature_contract",
    "context": "context_policy",
    "quality_gates": "quality_gates",
    "cost_model": "cost_model",
    "simulator": "simulator",
    "boundary": "boundary_rules",
}
_REQUIRED_FILTERS = ("PRICE_FILTER", "LOT_SIZE", "MARKET_LOT_SIZE")
_NOTIONAL_FILTERS = ("MIN_NOTIONAL", "NOTIONAL")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_CANONICAL_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: dict[str, Any] = {
    "schema_version": RUN_IDENTITY_CONTRACT_SCHEMA,
    "protocol_version": "3.0.0",
    "exchange_info_contract_version": EXCHANGE_INFO_CONTRACT_VERSION,
    "run_fingerprint_contract_version": RUN_FINGERPRINT_CONTRACT_VERSION,
    "exchange_info_policy": {
        "exchange": "binance",
        "market_type": "spot",
        "symbol": "ETHUSDC",
        "base_asset": "ETH",
        "quote_asset": "USDC",
        "status": "TRADING",
        "spot_trading_allowed_required": True,
        "public_payload_only": True,
        "private_or_account_data_forbidden": True,
        "required_filters": list(_REQUIRED_FILTERS),
        "notional_filter_any_of": list(_NOTIONAL_FILTERS),
        "canonical_decimal_strings": True,
        "immutable_write_only": True,
        "sha256_bound": True,
    },
    "run_fingerprint_policy": {
        "timestamp_free_identity": True,
        "required_identity_keys": [
            "raw_data",
            "as_of_day",
            "code",
            "pipeline",
            "features",
            "context",
            "quality_gates",
            "cost_model",
            "simulator",
            "boundary",
            "trial_ledger_head",
            "exchange_info",
        ],
        "resume_requires_exact_fingerprint": True,
        "cache_hit_requires_exact_fingerprint": True,
        "canonical_json": True,
        "sha256_bound": True,
        "context_runtime_binding": {
            "required": True,
            "requires_concrete_validated_context_parity_binding": True,
            "identity_payload_embedded": True,
            "context_identity_sha256_verified": True,
            "cache_and_resume_key_verified": True,
            "data_snapshot_sha256_must_match_raw_data": True,
        },
    },
    "safety": _CANONICAL_SAFETY,
}


class RunIdentityError(RuntimeError):
    """Raised when Exchange-Info or a run identity is incomplete or contradictory."""


@dataclass(frozen=True)
class FrozenExchangeInfoSnapshot:
    canonical_payload_json: str
    snapshot_sha256: str

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_payload_json)

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        payload["snapshot_sha256"] = self.snapshot_sha256
        return payload


@dataclass(frozen=True)
class RunFingerprint:
    canonical_payload_json: str
    fingerprint_sha256: str

    @property
    def resume_key(self) -> str:
        return f"{RUN_FINGERPRINT_PREFIX}:{self.fingerprint_sha256}"

    @property
    def cache_key(self) -> str:
        return self.resume_key

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_payload_json)

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        payload.update(
            {
                "fingerprint_sha256": self.fingerprint_sha256,
                "resume_key": self.resume_key,
                "cache_key": self.cache_key,
            }
        )
        return payload


def load_run_identity_contract(
    repo_root: str | Path | None = None,
    *,
    contract_path: str | Path | None = None,
) -> dict[str, Any]:
    root = _resolve_repo_root(repo_root)
    path = Path(contract_path) if contract_path is not None else root / RUN_IDENTITY_CONTRACT_PATH
    if not path.is_absolute():
        path = root / path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunIdentityError(f"run identity contract is missing or invalid: {path}") from exc
    validate_run_identity_contract(value)
    return value


def validate_run_identity_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize_json(value) != _CANONICAL_CONTRACT:
        raise RunIdentityError("Protocol v3 run identity contract is not canonical")


def build_exchange_info_snapshot(
    exchange_info_payload: Mapping[str, Any],
    *,
    snapshot_as_of_utc: str | datetime,
    repo_root: str | Path | None = None,
    contract_path: str | Path | None = None,
) -> FrozenExchangeInfoSnapshot:
    """Freeze the public ETHUSDC filter subset without making a network call."""

    contract = load_run_identity_contract(repo_root, contract_path=contract_path)
    symbol = _extract_ethusdc_symbol(exchange_info_payload)
    normalized = _normalize_symbol_exchange_info(symbol)
    payload = {
        "schema_version": EXCHANGE_INFO_SNAPSHOT_SCHEMA,
        "protocol_version": "3.0.0",
        "contract_version": EXCHANGE_INFO_CONTRACT_VERSION,
        "contract_sha256": _sha256_json(contract),
        "snapshot_as_of_utc": _canonical_utc_text(snapshot_as_of_utc),
        "exchange": "binance",
        "market_type": "spot",
        **normalized,
        "source": {
            "kind": "public_binance_exchange_info_payload",
            "network_call_performed_by_module": False,
            "private_or_account_data_used": False,
        },
        "safety": _CANONICAL_SAFETY,
    }
    canonical = _canonical_json(payload)
    snapshot = FrozenExchangeInfoSnapshot(
        canonical_payload_json=canonical,
        snapshot_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )
    validate_exchange_info_snapshot(snapshot, repo_root=repo_root, contract_path=contract_path)
    return snapshot


def validate_exchange_info_snapshot(
    snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    contract_path: str | Path | None = None,
) -> None:
    payload, digest, canonical = _snapshot_parts(snapshot, "snapshot_sha256")
    if digest != hashlib.sha256(canonical.encode("utf-8")).hexdigest():
        raise RunIdentityError("exchange-info snapshot digest mismatch")
    if _canonical_json(payload) != canonical:
        raise RunIdentityError("exchange-info snapshot payload is not canonical")
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "contract_sha256",
        "snapshot_as_of_utc",
        "exchange",
        "market_type",
        "symbol",
        "status",
        "base_asset",
        "quote_asset",
        "spot_trading_allowed",
        "filters",
        "notional_filter_types",
        "source",
        "safety",
    }
    if set(payload) != required:
        raise RunIdentityError("exchange-info snapshot fields are missing or unexpected")
    contract = load_run_identity_contract(repo_root, contract_path=contract_path)
    if payload.get("schema_version") != EXCHANGE_INFO_SNAPSHOT_SCHEMA:
        raise RunIdentityError("exchange-info snapshot schema is invalid")
    if payload.get("protocol_version") != "3.0.0":
        raise RunIdentityError("exchange-info protocol version is invalid")
    if payload.get("contract_version") != EXCHANGE_INFO_CONTRACT_VERSION:
        raise RunIdentityError("exchange-info contract version is invalid")
    if payload.get("contract_sha256") != _sha256_json(contract):
        raise RunIdentityError("exchange-info contract digest mismatch")
    _canonical_utc_text(payload.get("snapshot_as_of_utc"))
    if payload.get("exchange") != "binance" or payload.get("market_type") != "spot":
        raise RunIdentityError("exchange-info market identity is invalid")
    if payload.get("safety") != _CANONICAL_SAFETY:
        raise RunIdentityError("exchange-info safety locks are invalid")
    source = _require_mapping(payload.get("source"), "source")
    if source != {
        "kind": "public_binance_exchange_info_payload",
        "network_call_performed_by_module": False,
        "private_or_account_data_used": False,
    }:
        raise RunIdentityError("exchange-info source provenance is invalid")
    normalized = _normalize_symbol_exchange_info(payload)
    for key, expected in normalized.items():
        if payload.get(key) != expected:
            raise RunIdentityError(f"exchange-info snapshot field is invalid: {key}")


def write_exchange_info_snapshot(snapshot: FrozenExchangeInfoSnapshot, path: str | Path) -> Path:
    validate_exchange_info_snapshot(snapshot)
    return _write_new_json(path, snapshot.to_dict(), "exchange-info snapshot")


def read_exchange_info_snapshot(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
    contract_path: str | Path | None = None,
) -> FrozenExchangeInfoSnapshot:
    value = _read_json_object(Path(path), "exchange-info snapshot")
    digest = value.pop("snapshot_sha256", None)
    if not isinstance(digest, str):
        raise RunIdentityError("exchange-info snapshot digest is missing")
    snapshot = FrozenExchangeInfoSnapshot(_canonical_json(value), digest)
    validate_exchange_info_snapshot(snapshot, repo_root=repo_root, contract_path=contract_path)
    return snapshot


def build_run_fingerprint(
    *,
    data_snapshot: FrozenDataSnapshot | Mapping[str, Any],
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    pipeline_generation: PipelineGeneration,
    context_binding: ContextParityBinding,
    code_commit: str,
    trial_ledger: TrialLedgerSnapshot,
    repo_root: str | Path | None = None,
    contract_path: str | Path | None = None,
) -> RunFingerprint:
    """Bind every Task-6 identity into one timestamp-free resume/cache key."""

    contract = load_run_identity_contract(repo_root, contract_path=contract_path)
    normalized_commit = str(code_commit).strip().lower()
    if not _COMMIT_RE.fullmatch(normalized_commit):
        raise RunIdentityError("code_commit must be a full lowercase 40-character git SHA")
    validate_pipeline_generation(pipeline_generation)
    basis = pipeline_generation.basis()
    components = basis.get("component_source_sha256")
    versions = basis.get("component_contracts")
    if not isinstance(components, Mapping) or not isinstance(versions, Mapping):
        raise RunIdentityError("pipeline generation lacks component identities")

    raw_identity = _data_snapshot_identity(data_snapshot)
    context_runtime_identity = _context_runtime_identity(context_binding)
    if (
        context_runtime_identity["identity_payload"]["data_snapshot_sha256"]
        != raw_identity["snapshot_sha256"]
    ):
        raise RunIdentityError(
            "context binding and raw-data snapshot identities differ"
        )
    exchange_identity = _exchange_snapshot_identity(
        exchange_info_snapshot,
        repo_root=repo_root,
        contract_path=contract_path,
    )
    trial_identity = _trial_ledger_identity(trial_ledger)
    if pipeline_generation.permanent_trial_counter_namespace != trial_identity[
        "permanent_trial_counter_namespace"
    ]:
        raise RunIdentityError("pipeline and trial-ledger permanent namespaces differ")

    explicit_components: dict[str, Any] = {}
    for output_key, pipeline_key in _COMPONENT_MAP.items():
        digest = components.get(pipeline_key)
        version = versions.get(pipeline_key)
        if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
            raise RunIdentityError(f"pipeline component digest is invalid: {pipeline_key}")
        if not _valid_contract_version(version):
            raise RunIdentityError(f"pipeline component version is invalid: {pipeline_key}")
        explicit_components[output_key] = {
            "pipeline_component": pipeline_key,
            "contract_version": _normalize_json(version),
            "source_sha256": digest,
        }
    explicit_components["context"]["runtime_binding"] = context_runtime_identity

    payload = {
        "schema_version": RUN_FINGERPRINT_SCHEMA,
        "protocol_version": "3.0.0",
        "contract_version": RUN_FINGERPRINT_CONTRACT_VERSION,
        "contract_sha256": _sha256_json(contract),
        "raw_data": raw_identity,
        "as_of_day": raw_identity["snapshot_as_of_day"],
        "code": {"git_commit": normalized_commit},
        "pipeline": {
            "generation_id": pipeline_generation.generation_id,
            "contract_sha256": pipeline_generation.contract_sha256,
            "generation_basis_sha256": pipeline_generation.generation_id.rsplit(":", 1)[1],
            "forward_ledger_namespace": pipeline_generation.forward_ledger_namespace,
            "permanent_trial_counter_namespace": pipeline_generation.permanent_trial_counter_namespace,
        },
        **explicit_components,
        "trial_ledger_head": trial_identity,
        "exchange_info": exchange_identity,
        "safety": _CANONICAL_SAFETY,
    }
    canonical = _canonical_json(payload)
    fingerprint = RunFingerprint(
        canonical_payload_json=canonical,
        fingerprint_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )
    validate_run_fingerprint(fingerprint, repo_root=repo_root, contract_path=contract_path)
    return fingerprint


def validate_run_fingerprint(
    value: RunFingerprint | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    contract_path: str | Path | None = None,
) -> None:
    if isinstance(value, RunFingerprint):
        payload = value.payload()
        digest = value.fingerprint_sha256
        canonical = value.canonical_payload_json
        resume_key = value.resume_key
        cache_key = value.cache_key
    elif isinstance(value, Mapping):
        raw = dict(value)
        digest = raw.pop("fingerprint_sha256", None)
        resume_key = raw.pop("resume_key", None)
        cache_key = raw.pop("cache_key", None)
        payload = raw
        canonical = _canonical_json(payload)
    else:
        raise RunIdentityError("run fingerprint must be an object")
    if not isinstance(digest, str) or digest != hashlib.sha256(canonical.encode("utf-8")).hexdigest():
        raise RunIdentityError("run fingerprint digest mismatch")
    expected_key = f"{RUN_FINGERPRINT_PREFIX}:{digest}"
    if resume_key != expected_key or cache_key != expected_key:
        raise RunIdentityError("run fingerprint resume/cache keys are invalid")
    if _canonical_json(payload) != canonical:
        raise RunIdentityError("run fingerprint payload is not canonical")

    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "contract_sha256",
        "raw_data",
        "as_of_day",
        "code",
        "pipeline",
        *set(_COMPONENT_MAP),
        "trial_ledger_head",
        "exchange_info",
        "safety",
    }
    if set(payload) != required:
        raise RunIdentityError("run fingerprint fields are missing or unexpected")
    contract = load_run_identity_contract(repo_root, contract_path=contract_path)
    if payload.get("schema_version") != RUN_FINGERPRINT_SCHEMA:
        raise RunIdentityError("run fingerprint schema is invalid")
    if payload.get("protocol_version") != "3.0.0":
        raise RunIdentityError("run fingerprint protocol version is invalid")
    if payload.get("contract_version") != RUN_FINGERPRINT_CONTRACT_VERSION:
        raise RunIdentityError("run fingerprint contract version is invalid")
    if payload.get("contract_sha256") != _sha256_json(contract):
        raise RunIdentityError("run fingerprint contract digest mismatch")
    if payload.get("safety") != _CANONICAL_SAFETY:
        raise RunIdentityError("run fingerprint safety locks are invalid")

    raw = _require_mapping(payload.get("raw_data"), "raw_data")
    _validate_raw_identity(raw)
    if payload.get("as_of_day") != raw.get("snapshot_as_of_day"):
        raise RunIdentityError("run fingerprint as_of_day conflicts with data snapshot")
    _parse_day(payload.get("as_of_day"), "as_of_day")
    code = _require_mapping(payload.get("code"), "code")
    if set(code) != {"git_commit"} or not isinstance(code.get("git_commit"), str) or not _COMMIT_RE.fullmatch(code["git_commit"]):
        raise RunIdentityError("run fingerprint code identity is invalid")

    pipeline = _require_mapping(payload.get("pipeline"), "pipeline")
    _validate_pipeline_identity(pipeline)
    for output_key, pipeline_key in _COMPONENT_MAP.items():
        row = _require_mapping(payload.get(output_key), output_key)
        expected_fields = {
            "pipeline_component",
            "contract_version",
            "source_sha256",
        }
        if output_key == "context":
            expected_fields.add("runtime_binding")
        if set(row) != expected_fields:
            raise RunIdentityError(f"component identity fields are invalid: {output_key}")
        if row.get("pipeline_component") != pipeline_key:
            raise RunIdentityError(f"component identity name is invalid: {output_key}")
        if not _valid_contract_version(row.get("contract_version")):
            raise RunIdentityError(f"component contract version is invalid: {output_key}")
        if not isinstance(row.get("source_sha256"), str) or not _HEX64_RE.fullmatch(row["source_sha256"]):
            raise RunIdentityError(f"component digest is invalid: {output_key}")

    context_row = _require_mapping(payload.get("context"), "context")
    context_runtime = _require_mapping(
        context_row.get("runtime_binding"), "context.runtime_binding"
    )
    _validate_context_runtime_identity(context_runtime)
    context_payload = _require_mapping(
        context_runtime.get("identity_payload"),
        "context.runtime_binding.identity_payload",
    )
    if context_payload.get("data_snapshot_sha256") != raw.get("snapshot_sha256"):
        raise RunIdentityError(
            "run fingerprint context/raw-data snapshot mismatch"
        )
    if context_payload.get("data_snapshot_common_grid_sha256") != raw.get(
        "common_minute_grid_sha256"
    ):
        raise RunIdentityError(
            "run fingerprint context/raw-data minute-grid mismatch"
        )
    raw_market_content = {
        row["symbol"]: row["market_content_sha256"]
        for row in raw["markets"]
    }
    if context_payload.get("snapshot_market_content_sha256") != raw_market_content:
        raise RunIdentityError(
            "run fingerprint context/raw-data market-content mismatch"
        )
    raw_start_ms = _utc_timestamp_ms(
        raw.get("raw_interval_start_inclusive"), "raw interval start"
    )
    raw_end_ms = _utc_timestamp_ms(
        raw.get("raw_interval_end_exclusive"), "raw interval end"
    )
    if not (
        raw_start_ms <= context_payload["first_open_time_ms"]
        and context_payload["common_watermark_open_time_ms"] + 60_000
        <= raw_end_ms
    ):
        raise RunIdentityError(
            "run fingerprint context window lies outside raw-data interval"
        )
    trial = _require_mapping(payload.get("trial_ledger_head"), "trial_ledger_head")
    _validate_trial_identity(trial)
    if pipeline.get("permanent_trial_counter_namespace") != trial.get(
        "permanent_trial_counter_namespace"
    ):
        raise RunIdentityError("run fingerprint pipeline/trial namespace mismatch")
    exchange = _require_mapping(payload.get("exchange_info"), "exchange_info")
    _validate_exchange_identity(exchange)


def assert_resume_compatible(
    current: RunFingerprint | Mapping[str, Any],
    persisted: RunFingerprint | Mapping[str, Any],
) -> None:
    _assert_exact_reuse(current, persisted, "resume")


def assert_cache_hit_compatible(
    current: RunFingerprint | Mapping[str, Any],
    cached: RunFingerprint | Mapping[str, Any],
) -> None:
    _assert_exact_reuse(current, cached, "cache hit")


def write_run_fingerprint(fingerprint: RunFingerprint, path: str | Path) -> Path:
    validate_run_fingerprint(fingerprint)
    return _write_new_json(path, fingerprint.to_dict(), "run fingerprint")


def read_run_fingerprint(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
    contract_path: str | Path | None = None,
) -> RunFingerprint:
    value = _read_json_object(Path(path), "run fingerprint")
    digest = value.pop("fingerprint_sha256", None)
    resume_key = value.pop("resume_key", None)
    cache_key = value.pop("cache_key", None)
    if not isinstance(digest, str):
        raise RunIdentityError("run fingerprint digest is missing")
    fingerprint = RunFingerprint(_canonical_json(value), digest)
    if resume_key != fingerprint.resume_key or cache_key != fingerprint.cache_key:
        raise RunIdentityError("stored run fingerprint reuse keys are invalid")
    validate_run_fingerprint(fingerprint, repo_root=repo_root, contract_path=contract_path)
    return fingerprint


def _extract_ethusdc_symbol(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise RunIdentityError("exchangeInfo payload must be an object")
    _reject_private_or_account_fields(payload)
    symbols = payload.get("symbols")
    if not isinstance(symbols, list):
        raise RunIdentityError("exchangeInfo payload must contain a symbols list")
    matches = [
        row
        for row in symbols
        if isinstance(row, Mapping) and row.get("symbol") == "ETHUSDC"
    ]
    if len(matches) != 1:
        raise RunIdentityError("exchangeInfo must contain exactly one ETHUSDC symbol row")
    return matches[0]


def _normalize_symbol_exchange_info(symbol: Mapping[str, Any]) -> dict[str, Any]:
    if symbol.get("symbol") != "ETHUSDC":
        raise RunIdentityError("exchange-info symbol must be ETHUSDC")
    if symbol.get("status") != "TRADING":
        raise RunIdentityError("ETHUSDC exchange-info status must be TRADING")
    base = symbol.get("baseAsset", symbol.get("base_asset"))
    quote = symbol.get("quoteAsset", symbol.get("quote_asset"))
    spot = symbol.get("isSpotTradingAllowed", symbol.get("spot_trading_allowed"))
    if base != "ETH" or quote != "USDC":
        raise RunIdentityError("ETHUSDC assets must be ETH/USDC")
    if spot is not True:
        raise RunIdentityError("ETHUSDC Spot trading must be allowed by exchangeInfo")
    raw_filters = symbol.get("filters")
    if isinstance(raw_filters, Mapping):
        by_type = {str(key): value for key, value in raw_filters.items()}
    elif isinstance(raw_filters, list):
        by_type: dict[str, Any] = {}
        for row in raw_filters:
            if not isinstance(row, Mapping) or not isinstance(row.get("filterType"), str):
                raise RunIdentityError("exchange-info filter rows are invalid")
            filter_type = str(row["filterType"])
            if filter_type in by_type:
                raise RunIdentityError(f"duplicate exchange-info filter: {filter_type}")
            by_type[filter_type] = row
    else:
        raise RunIdentityError("exchange-info filters must be a list or object")

    missing = [name for name in _REQUIRED_FILTERS if name not in by_type]
    if missing:
        raise RunIdentityError(f"required exchange-info filters are missing: {missing}")
    present_notional = [name for name in _NOTIONAL_FILTERS if name in by_type]
    if not present_notional:
        raise RunIdentityError("MIN_NOTIONAL or NOTIONAL filter is required")

    filters: dict[str, Any] = {
        "PRICE_FILTER": _normalize_price_filter(by_type["PRICE_FILTER"]),
        "LOT_SIZE": _normalize_quantity_filter(by_type["LOT_SIZE"], "LOT_SIZE"),
        "MARKET_LOT_SIZE": _normalize_quantity_filter(
            by_type["MARKET_LOT_SIZE"], "MARKET_LOT_SIZE"
        ),
    }
    for filter_type in present_notional:
        filters[filter_type] = (
            _normalize_min_notional_filter(by_type[filter_type])
            if filter_type == "MIN_NOTIONAL"
            else _normalize_notional_filter(by_type[filter_type])
        )
    return {
        "symbol": "ETHUSDC",
        "status": "TRADING",
        "base_asset": "ETH",
        "quote_asset": "USDC",
        "spot_trading_allowed": True,
        "filters": filters,
        "notional_filter_types": present_notional,
    }


def _normalize_price_filter(value: Any) -> dict[str, Any]:
    row = _require_mapping(value, "PRICE_FILTER")
    result = {
        "filter_type": "PRICE_FILTER",
        "min_price": _decimal(
            row.get("minPrice", row.get("min_price")),
            "PRICE_FILTER.minPrice",
            allow_zero=True,
        ),
        "max_price": _decimal(
            row.get("maxPrice", row.get("max_price")),
            "PRICE_FILTER.maxPrice",
            allow_zero=True,
        ),
        "tick_size": _decimal(
            row.get("tickSize", row.get("tick_size")), "PRICE_FILTER.tickSize"
        ),
    }
    minimum = Decimal(result["min_price"])
    maximum = Decimal(result["max_price"])
    if maximum and maximum < minimum:
        raise RunIdentityError("PRICE_FILTER maxPrice is below minPrice")
    return result


def _normalize_quantity_filter(value: Any, filter_type: str) -> dict[str, Any]:
    row = _require_mapping(value, filter_type)
    result = {
        "filter_type": filter_type,
        "min_qty": _decimal(
            row.get("minQty", row.get("min_qty")),
            f"{filter_type}.minQty",
            allow_zero=True,
        ),
        "max_qty": _decimal(
            row.get("maxQty", row.get("max_qty")), f"{filter_type}.maxQty"
        ),
        "step_size": _decimal(
            row.get("stepSize", row.get("step_size")),
            f"{filter_type}.stepSize",
            allow_zero=filter_type == "MARKET_LOT_SIZE",
        ),
    }
    if Decimal(result["max_qty"]) < Decimal(result["min_qty"]):
        raise RunIdentityError(f"{filter_type} maxQty is below minQty")
    return result


def _normalize_min_notional_filter(value: Any) -> dict[str, Any]:
    row = _require_mapping(value, "MIN_NOTIONAL")
    return {
        "filter_type": "MIN_NOTIONAL",
        "min_notional": _decimal(
            row.get("minNotional", row.get("min_notional")),
            "MIN_NOTIONAL.minNotional",
        ),
        "apply_to_market": _boolean(
            row.get("applyToMarket", row.get("apply_to_market")),
            "MIN_NOTIONAL.applyToMarket",
        ),
        "avg_price_mins": _nonnegative_int(
            row.get("avgPriceMins", row.get("avg_price_mins")),
            "MIN_NOTIONAL.avgPriceMins",
        ),
    }


def _normalize_notional_filter(value: Any) -> dict[str, Any]:
    row = _require_mapping(value, "NOTIONAL")
    result = {
        "filter_type": "NOTIONAL",
        "min_notional": _decimal(
            row.get("minNotional", row.get("min_notional")),
            "NOTIONAL.minNotional",
        ),
        "max_notional": _decimal(
            row.get("maxNotional", row.get("max_notional")),
            "NOTIONAL.maxNotional",
        ),
        "apply_min_to_market": _boolean(
            row.get("applyMinToMarket", row.get("apply_min_to_market")),
            "NOTIONAL.applyMinToMarket",
        ),
        "apply_max_to_market": _boolean(
            row.get("applyMaxToMarket", row.get("apply_max_to_market")),
            "NOTIONAL.applyMaxToMarket",
        ),
        "avg_price_mins": _nonnegative_int(
            row.get("avgPriceMins", row.get("avg_price_mins")),
            "NOTIONAL.avgPriceMins",
        ),
    }
    if Decimal(result["max_notional"]) < Decimal(result["min_notional"]):
        raise RunIdentityError("NOTIONAL maxNotional is below minNotional")
    return result


def _data_snapshot_identity(snapshot: FrozenDataSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    validate_frozen_data_snapshot(snapshot)
    value = snapshot.to_dict() if isinstance(snapshot, FrozenDataSnapshot) else dict(snapshot)
    digest = value.get("snapshot_sha256")
    if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
        raise RunIdentityError("data snapshot digest is invalid")
    boundary = _require_mapping(value.get("boundary"), "data snapshot boundary")
    raw_interval = _require_mapping(value.get("raw_interval"), "data snapshot raw_interval")
    market_data = value.get("market_data")
    if not isinstance(market_data, list) or len(market_data) != 3:
        raise RunIdentityError("data snapshot must contain exactly three markets")
    markets: list[dict[str, str]] = []
    for row in market_data:
        item = _require_mapping(row, "data snapshot market")
        symbol = item.get("symbol")
        if symbol not in {"ETHUSDC", "BTCUSDC", "ETHBTC"}:
            raise RunIdentityError("data snapshot market symbol is invalid")
        markets.append(
            {
                "symbol": str(symbol),
                "timestamp_grid_sha256": _hex64(
                    item.get("timestamp_grid_sha256"), "timestamp grid"
                ),
                "market_content_sha256": _hex64(
                    item.get("market_content_sha256"), "market content"
                ),
                "archive_inventory_sha256": _hex64(
                    item.get("archive_inventory_sha256"), "archive inventory"
                ),
                "complete_utc_days_sha256": _hex64(
                    item.get("complete_utc_days_sha256"), "complete UTC days"
                ),
            }
        )
    if [row["symbol"] for row in markets] != ["ETHUSDC", "BTCUSDC", "ETHBTC"]:
        raise RunIdentityError("data snapshot markets are not in canonical order")
    availability = _require_mapping(value.get("availability"), "availability")
    return {
        "snapshot_sha256": digest,
        "snapshot_as_of_day": _parse_day(
            boundary.get("snapshot_as_of_day"), "snapshot_as_of_day"
        ).isoformat(),
        "latest_common_complete_day": _parse_day(
            availability.get("latest_common_complete_day"),
            "latest_common_complete_day",
        ).isoformat(),
        "raw_interval_start_inclusive": _required_text(
            raw_interval.get("start_inclusive"), "raw interval start"
        ),
        "raw_interval_end_exclusive": _required_text(
            raw_interval.get("end_exclusive"), "raw interval end"
        ),
        "common_minute_grid_sha256": _hex64(
            value.get("common_minute_grid_sha256"), "common minute grid"
        ),
        "markets": markets,
    }


def _exchange_snapshot_identity(
    snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    *,
    repo_root: str | Path | None,
    contract_path: str | Path | None,
) -> dict[str, Any]:
    validate_exchange_info_snapshot(
        snapshot, repo_root=repo_root, contract_path=contract_path
    )
    value = snapshot.to_dict() if isinstance(snapshot, FrozenExchangeInfoSnapshot) else dict(snapshot)
    filters = _require_mapping(value.get("filters"), "exchange filters")
    return {
        "snapshot_sha256": _hex64(
            value.get("snapshot_sha256"), "exchange-info snapshot"
        ),
        "snapshot_as_of_utc": _canonical_utc_text(value.get("snapshot_as_of_utc")),
        "symbol": "ETHUSDC",
        "filters_sha256": _sha256_json(filters),
        "filter_types": list(filters),
    }


def _trial_ledger_identity(value: TrialLedgerSnapshot) -> dict[str, Any]:
    if not isinstance(value, TrialLedgerSnapshot):
        raise RunIdentityError(
            "trial_ledger must be a verified TrialLedgerSnapshot"
        )
    current = read_trial_ledger(value.root)
    if current.status.head_sha256 != value.status.head_sha256:
        raise RunIdentityError("trial-ledger snapshot is stale")
    status = current.status.to_dict()
    namespace = current.manifest.get("permanent_trial_counter_namespace")
    identity = {
        "permanent_trial_counter_namespace": namespace,
        "head_sha256": status.get("head_sha256"),
        "event_count": status.get("event_count"),
        "historical_trial_count_is_lower_bound": status.get(
            "historical_trial_count_is_lower_bound"
        ),
        "development_dsr_status": status.get("development_dsr_status"),
    }
    _validate_trial_identity(identity)
    return identity


def _context_runtime_identity(value: ContextParityBinding) -> dict[str, Any]:
    """Extract one validated concrete Task-10 binding for the run identity.

    The import is intentionally lazy: ``context_parity`` uses the public
    Exchange-Info snapshot type from this module.  Keeping the dependency here
    avoids a module-import cycle while still rejecting mappings and look-alike
    objects at the construction boundary.
    """

    try:
        from .context_parity import (
            ContextParityBinding,
            validate_context_parity_binding,
        )
    except ImportError as exc:  # pragma: no cover - packaging corruption
        raise RunIdentityError("Protocol v3 context parity module is unavailable") from exc
    if not isinstance(value, ContextParityBinding):
        raise RunIdentityError(
            "context_binding must be a verified ContextParityBinding"
        )
    try:
        validate_context_parity_binding(value)
        identity_payload = _normalize_json(value.identity_payload())
    except Exception as exc:
        raise RunIdentityError(
            f"context_binding is not a valid ContextParityBinding: {exc}"
        ) from exc
    runtime_identity = {
        "context_identity_sha256": value.context_identity_sha256,
        "identity_payload": identity_payload,
        "cache_key": value.cache_key,
        "resume_key": value.resume_key,
    }
    _validate_context_runtime_identity(runtime_identity)
    return runtime_identity


def _validate_context_runtime_identity(value: Mapping[str, Any]) -> None:
    if set(value) != {
        "context_identity_sha256",
        "identity_payload",
        "cache_key",
        "resume_key",
    }:
        raise RunIdentityError("context runtime-binding fields are invalid")
    identity_payload = _require_mapping(
        value.get("identity_payload"), "context identity_payload"
    )
    expected_payload_fields = {
        "contract_version",
        "policy_version",
        "policy",
        "data_snapshot_sha256",
        "data_snapshot_common_grid_sha256",
        "snapshot_market_content_sha256",
        "window_market_content_sha256",
        "first_open_time_ms",
        "common_watermark_open_time_ms",
        "candle_count",
    }
    if set(identity_payload) != expected_payload_fields:
        raise RunIdentityError("context identity_payload fields are invalid")

    try:
        from .context_parity import CONTEXT_PARITY_CONTRACT_VERSION, MARKETS
        from ethusdc_bot.backtest.context_features import (
            CONTEXT_POLICY_VERSION,
            ContextVetoPolicy,
        )
    except ImportError as exc:  # pragma: no cover - packaging corruption
        raise RunIdentityError("Protocol v3 context identity types are unavailable") from exc
    if identity_payload.get("contract_version") != CONTEXT_PARITY_CONTRACT_VERSION:
        raise RunIdentityError("context runtime contract version is invalid")
    if identity_payload.get("policy_version") != CONTEXT_POLICY_VERSION:
        raise RunIdentityError("context runtime policy version is invalid")

    policy_payload = _require_mapping(
        identity_payload.get("policy"), "context policy payload"
    )
    policy_values = dict(policy_payload)
    if policy_values.pop("policy_version", None) != CONTEXT_POLICY_VERSION:
        raise RunIdentityError("context policy payload version is invalid")
    try:
        normalized_policy = ContextVetoPolicy(**policy_values).to_dict()
    except (TypeError, ValueError) as exc:
        raise RunIdentityError("context policy payload is invalid") from exc
    if _normalize_json(policy_payload) != _normalize_json(normalized_policy):
        raise RunIdentityError("context policy payload is not canonical")

    _hex64(identity_payload.get("data_snapshot_sha256"), "context data snapshot")
    _hex64(
        identity_payload.get("data_snapshot_common_grid_sha256"),
        "context common grid",
    )
    expected_symbols = list(MARKETS)
    for field in (
        "snapshot_market_content_sha256",
        "window_market_content_sha256",
    ):
        rows = _require_mapping(identity_payload.get(field), f"context {field}")
        if set(rows) != set(expected_symbols):
            raise RunIdentityError(f"context {field} markets are not canonical")
        for symbol in expected_symbols:
            _hex64(rows.get(symbol), f"context {field}.{symbol}")

    first = identity_payload.get("first_open_time_ms")
    watermark = identity_payload.get("common_watermark_open_time_ms")
    count = identity_payload.get("candle_count")
    if isinstance(first, bool) or not isinstance(first, int) or first < 0:
        raise RunIdentityError("context first_open_time_ms is invalid")
    if isinstance(watermark, bool) or not isinstance(watermark, int) or watermark < 0:
        raise RunIdentityError("context common watermark is invalid")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise RunIdentityError("context candle_count is invalid")
    if watermark != first + (count - 1) * 60_000:
        raise RunIdentityError("context runtime minute window is not contiguous")
    if (
        first % 86_400_000 != 0
        or count % 1440 != 0
        or (watermark + 60_000) % 86_400_000 != 0
    ):
        raise RunIdentityError(
            "context runtime window must contain complete UTC days"
        )

    identity_sha = _hex64(
        value.get("context_identity_sha256"), "context runtime identity"
    )
    if identity_sha != _sha256_json(identity_payload):
        raise RunIdentityError("context runtime identity digest mismatch")
    expected_key = f"{CONTEXT_IDENTITY_PREFIX}:{identity_sha}"
    if value.get("cache_key") != expected_key or value.get("resume_key") != expected_key:
        raise RunIdentityError("context runtime cache/resume keys are invalid")


def _reject_private_or_account_fields(value: Any) -> None:
    """Reject credential/account-shaped keys at every payload depth."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if any(
                marker in normalized_key
                for marker in ("apikey", "secret", "signature", "account")
            ):
                raise RunIdentityError(
                    "private or account data is forbidden in exchangeInfo payload"
                )
            _reject_private_or_account_fields(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _reject_private_or_account_fields(child)


def _validate_raw_identity(value: Mapping[str, Any]) -> None:
    required = {
        "snapshot_sha256",
        "snapshot_as_of_day",
        "latest_common_complete_day",
        "raw_interval_start_inclusive",
        "raw_interval_end_exclusive",
        "common_minute_grid_sha256",
        "markets",
    }
    if set(value) != required:
        raise RunIdentityError("raw-data identity fields are invalid")
    for key in ("snapshot_sha256", "common_minute_grid_sha256"):
        _hex64(value.get(key), key)
    _parse_day(value.get("snapshot_as_of_day"), "snapshot_as_of_day")
    _parse_day(value.get("latest_common_complete_day"), "latest_common_complete_day")
    _required_text(value.get("raw_interval_start_inclusive"), "raw_interval_start_inclusive")
    _required_text(value.get("raw_interval_end_exclusive"), "raw_interval_end_exclusive")
    markets = value.get("markets")
    if not isinstance(markets, list) or [
        row.get("symbol") for row in markets if isinstance(row, Mapping)
    ] != ["ETHUSDC", "BTCUSDC", "ETHBTC"]:
        raise RunIdentityError("raw-data market identities are invalid")
    for row in markets:
        item = _require_mapping(row, "raw-data market")
        if set(item) != {
            "symbol",
            "timestamp_grid_sha256",
            "market_content_sha256",
            "archive_inventory_sha256",
            "complete_utc_days_sha256",
        }:
            raise RunIdentityError("raw-data market identity fields are invalid")
        for key in (
            "timestamp_grid_sha256",
            "market_content_sha256",
            "archive_inventory_sha256",
            "complete_utc_days_sha256",
        ):
            _hex64(item.get(key), key)


def _validate_pipeline_identity(value: Mapping[str, Any]) -> None:
    required = {
        "generation_id",
        "contract_sha256",
        "generation_basis_sha256",
        "forward_ledger_namespace",
        "permanent_trial_counter_namespace",
    }
    if set(value) != required:
        raise RunIdentityError("pipeline identity fields are invalid")
    basis_digest = _hex64(value.get("generation_basis_sha256"), "pipeline basis")
    if value.get("generation_id") != f"protocol_v3_pipeline_sha256:{basis_digest}":
        raise RunIdentityError("pipeline generation id is invalid")
    _hex64(value.get("contract_sha256"), "pipeline contract")
    _required_text(value.get("forward_ledger_namespace"), "forward ledger namespace")
    if value.get("permanent_trial_counter_namespace") != PERMANENT_TRIAL_COUNTER_NAMESPACE:
        raise RunIdentityError("pipeline permanent trial namespace is invalid")


def _validate_trial_identity(value: Mapping[str, Any]) -> None:
    required = {
        "permanent_trial_counter_namespace",
        "head_sha256",
        "event_count",
        "historical_trial_count_is_lower_bound",
        "development_dsr_status",
    }
    if set(value) != required:
        raise RunIdentityError("trial-ledger identity fields are invalid")
    if value.get("permanent_trial_counter_namespace") != PERMANENT_TRIAL_COUNTER_NAMESPACE:
        raise RunIdentityError("trial-ledger namespace is invalid")
    _hex64(value.get("head_sha256"), "trial-ledger head")
    count = value.get("event_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise RunIdentityError("trial-ledger event_count is invalid")
    if type(value.get("historical_trial_count_is_lower_bound")) is not bool:
        raise RunIdentityError("trial-ledger lower-bound flag is invalid")
    _required_text(value.get("development_dsr_status"), "development_dsr_status")


def _validate_exchange_identity(value: Mapping[str, Any]) -> None:
    if set(value) != {
        "snapshot_sha256",
        "snapshot_as_of_utc",
        "symbol",
        "filters_sha256",
        "filter_types",
    }:
        raise RunIdentityError("exchange-info identity fields are invalid")
    _hex64(value.get("snapshot_sha256"), "exchange-info snapshot")
    _canonical_utc_text(value.get("snapshot_as_of_utc"))
    if value.get("symbol") != "ETHUSDC":
        raise RunIdentityError("exchange-info identity symbol is invalid")
    _hex64(value.get("filters_sha256"), "exchange-info filters")
    types = value.get("filter_types")
    if (
        not isinstance(types, list)
        or not set(_REQUIRED_FILTERS).issubset(types)
        or not set(types) & set(_NOTIONAL_FILTERS)
    ):
        raise RunIdentityError("exchange-info filter identity is incomplete")


def _assert_exact_reuse(
    current: RunFingerprint | Mapping[str, Any],
    stored: RunFingerprint | Mapping[str, Any],
    label: str,
) -> None:
    validate_run_fingerprint(current)
    validate_run_fingerprint(stored)
    current_digest = (
        current.fingerprint_sha256
        if isinstance(current, RunFingerprint)
        else current.get("fingerprint_sha256")
    )
    stored_digest = (
        stored.fingerprint_sha256
        if isinstance(stored, RunFingerprint)
        else stored.get("fingerprint_sha256")
    )
    if current_digest != stored_digest:
        raise RunIdentityError(f"{label} blocked: Protocol v3 run fingerprint changed")


def _snapshot_parts(
    value: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    digest_key: str,
) -> tuple[dict[str, Any], Any, str]:
    if isinstance(value, FrozenExchangeInfoSnapshot):
        return value.payload(), value.snapshot_sha256, value.canonical_payload_json
    if isinstance(value, Mapping):
        payload = dict(value)
        digest = payload.pop(digest_key, None)
        return payload, digest, _canonical_json(payload)
    raise RunIdentityError("snapshot must be an object")


def _decimal(value: Any, label: str, *, allow_zero: bool = False) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise RunIdentityError(f"{label} must be a decimal value")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RunIdentityError(f"{label} is not a valid decimal") from exc
    if not parsed.is_finite() or parsed < 0 or (not allow_zero and parsed == 0):
        requirement = "non-negative" if allow_zero else "positive"
        raise RunIdentityError(f"{label} must be {requirement} and finite")
    if parsed == 0:
        return "0"
    text = format(parsed.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise RunIdentityError(f"{label} must be boolean")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RunIdentityError(f"{label} must be a non-negative integer")
    return value


def _canonical_utc_text(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(
                text[:-1] + "+00:00" if text.endswith("Z") else text
            )
        except ValueError as exc:
            raise RunIdentityError(
                "snapshot_as_of_utc must be an ISO-8601 UTC datetime"
            ) from exc
    else:
        raise RunIdentityError("snapshot_as_of_utc must be an ISO-8601 UTC datetime")
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise RunIdentityError("snapshot_as_of_utc must use UTC")
    return parsed.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _valid_contract_version(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _hex64(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise RunIdentityError(f"{label} must be a lowercase SHA-256")
    return value


def _parse_day(value: Any, label: str) -> date:
    if not isinstance(value, str):
        raise RunIdentityError(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RunIdentityError(f"{label} must be an ISO date") from exc


def _utc_timestamp_ms(value: Any, label: str) -> int:
    canonical = _canonical_utc_text(value)
    parsed = datetime.fromisoformat(canonical.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunIdentityError(f"{label} must be a non-empty string")
    return value


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RunIdentityError(f"{label} must be an object")
    return value


def _normalize_json(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RunIdentityError("identity payload is not strict canonical JSON") from exc


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RunIdentityError(f"{label} is missing or invalid: {path}") from exc
    if not isinstance(value, dict):
        raise RunIdentityError(f"{label} root must be an object")
    return value


def _write_new_json(path: str | Path, payload: Mapping[str, Any], label: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False)
        + "\n"
    )
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise RunIdentityError(f"{label} path already exists and cannot be overwritten") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            target.unlink(missing_ok=True)
        finally:
            raise
    return target


def _resolve_repo_root(repo_root: str | Path | None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    return Path(__file__).resolve().parents[3]


__all__ = [
    "EXCHANGE_INFO_CONTRACT_VERSION",
    "EXCHANGE_INFO_SNAPSHOT_SCHEMA",
    "RUN_FINGERPRINT_CONTRACT_VERSION",
    "RUN_FINGERPRINT_PREFIX",
    "RUN_FINGERPRINT_SCHEMA",
    "RUN_IDENTITY_CONTRACT_PATH",
    "FrozenExchangeInfoSnapshot",
    "RunFingerprint",
    "RunIdentityError",
    "assert_cache_hit_compatible",
    "assert_resume_compatible",
    "build_exchange_info_snapshot",
    "build_run_fingerprint",
    "load_run_identity_contract",
    "read_exchange_info_snapshot",
    "read_run_fingerprint",
    "validate_exchange_info_snapshot",
    "validate_run_fingerprint",
    "validate_run_identity_contract",
    "write_exchange_info_snapshot",
    "write_run_fingerprint",
]
