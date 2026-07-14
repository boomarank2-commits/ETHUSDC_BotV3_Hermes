"""Protocol v3 task-6 tests for Exchange-Info and complete run identity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import run_identity as identity
from ethusdc_bot.protocol_v3.data_snapshot import FrozenDataSnapshot, build_warmup_plan
from ethusdc_bot.protocol_v3.pipeline import build_pipeline_generation
from ethusdc_bot.protocol_v3.trial_ledger import (
    DEVELOPMENT_DSR_INSUFFICIENT,
    PERMANENT_TRIAL_COUNTER_NAMESPACE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40


def _exchange_info(
    *, include_min_notional: bool = True, include_notional: bool = True
) -> dict[str, object]:
    filters: list[dict[str, object]] = [
        {
            "filterType": "PRICE_FILTER",
            "minPrice": "0.01000000",
            "maxPrice": "1000000.00000000",
            "tickSize": "0.01000000",
        },
        {
            "filterType": "LOT_SIZE",
            "minQty": "0.00010000",
            "maxQty": "9000.00000000",
            "stepSize": "0.00010000",
        },
        {
            "filterType": "MARKET_LOT_SIZE",
            "minQty": "0.00000000",
            "maxQty": "1200.00000000",
            "stepSize": "0.00010000",
        },
    ]
    if include_min_notional:
        filters.append(
            {
                "filterType": "MIN_NOTIONAL",
                "minNotional": "5.00000000",
                "applyToMarket": True,
                "avgPriceMins": 5,
            }
        )
    if include_notional:
        filters.append(
            {
                "filterType": "NOTIONAL",
                "minNotional": "5.00000000",
                "maxNotional": "10000000.00000000",
                "applyMinToMarket": True,
                "applyMaxToMarket": False,
                "avgPriceMins": 5,
            }
        )
    return {
        "timezone": "UTC",
        "serverTime": 1,
        "symbols": [
            {
                "symbol": "ETHUSDC",
                "status": "TRADING",
                "baseAsset": "ETH",
                "quoteAsset": "USDC",
                "isSpotTradingAllowed": True,
                "filters": filters,
            }
        ],
    }


def _fake_data_snapshot() -> FrozenDataSnapshot:
    markets = []
    for index, symbol in enumerate(("ETHUSDC", "BTCUSDC", "ETHBTC"), start=1):
        markets.append(
            {
                "symbol": symbol,
                "timestamp_grid_sha256": "1" * 64,
                "market_content_sha256": str(index + 1) * 64,
                "archive_inventory_sha256": str(index + 4) * 64,
                "complete_utc_days_sha256": str(index + 7) * 64,
            }
        )
    payload = {
        "availability": {"latest_common_complete_day": "2026-07-07"},
        "boundary": {"snapshot_as_of_day": "2026-07-07"},
        "raw_interval": {
            "start_inclusive": "2023-06-18T23:59:00Z",
            "end_exclusive": "2026-07-08T00:00:00Z",
        },
        "market_data": markets,
        "common_minute_grid_sha256": "1" * 64,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return FrozenDataSnapshot(
        canonical, hashlib.sha256(canonical.encode()).hexdigest()
    )


def _trial_identity(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "permanent_trial_counter_namespace": PERMANENT_TRIAL_COUNTER_NAMESPACE,
        "head_sha256": "0" * 64,
        "event_count": 0,
        "historical_trial_count_is_lower_bound": True,
        "development_dsr_status": DEVELOPMENT_DSR_INSUFFICIENT,
    }
    value.update(changes)
    return value


def _fingerprint(monkeypatch: pytest.MonkeyPatch) -> identity.RunFingerprint:
    monkeypatch.setattr(identity, "validate_frozen_data_snapshot", lambda value: None)
    exchange = identity.build_exchange_info_snapshot(
        _exchange_info(), snapshot_as_of_utc="2026-07-07T23:59:59Z"
    )
    return identity.build_run_fingerprint(
        data_snapshot=_fake_data_snapshot(),
        exchange_info_snapshot=exchange,
        pipeline_generation=build_pipeline_generation(REPO_ROOT),
        code_commit=COMMIT,
        trial_ledger=_trial_identity(),
    )


def _refreeze(payload: dict[str, object]) -> identity.RunFingerprint:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return identity.RunFingerprint(
        canonical_payload_json=canonical,
        fingerprint_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
    )


def test_task5_warmup_contract_remains_active_before_task6() -> None:
    plan = build_warmup_plan(
        [
            {
                "name": "eth",
                "market": "ETHUSDC",
                "bars": 20,
                "bar_seconds": 86400,
            },
            {
                "name": "btc",
                "market": "BTCUSDC",
                "bars": 4,
                "bar_seconds": 3600,
            },
            {
                "name": "cross",
                "market": "ETHBTC",
                "bars": 4,
                "bar_seconds": 3600,
            },
        ]
    )
    assert plan.warmup_duration_seconds == 20 * 86400 + 60


def test_run_identity_contract_is_exact_and_safety_locked() -> None:
    contract = identity.load_run_identity_contract(REPO_ROOT)
    identity.validate_run_identity_contract(contract)
    assert contract["exchange_info_policy"]["symbol"] == "ETHUSDC"
    assert contract["exchange_info_policy"]["private_or_account_data_forbidden"] is True
    assert contract["run_fingerprint_policy"]["resume_requires_exact_fingerprint"] is True
    assert contract["run_fingerprint_policy"]["cache_hit_requires_exact_fingerprint"] is True
    changed = json.loads(json.dumps(contract))
    changed["safety"]["paper"] = "unlocked"
    with pytest.raises(identity.RunIdentityError, match="not canonical"):
        identity.validate_run_identity_contract(changed)


def test_exchange_info_snapshot_normalizes_and_binds_all_required_filters() -> None:
    snapshot = identity.build_exchange_info_snapshot(
        _exchange_info(), snapshot_as_of_utc="2026-07-07T23:59:59+00:00"
    )
    identity.validate_exchange_info_snapshot(snapshot)
    payload = snapshot.payload()
    assert payload["snapshot_as_of_utc"] == "2026-07-07T23:59:59Z"
    assert payload["symbol"] == "ETHUSDC"
    assert payload["base_asset"] == "ETH"
    assert payload["quote_asset"] == "USDC"
    assert list(payload["filters"]) == [
        "LOT_SIZE",
        "MARKET_LOT_SIZE",
        "MIN_NOTIONAL",
        "NOTIONAL",
        "PRICE_FILTER",
    ]
    assert payload["filters"]["PRICE_FILTER"]["tick_size"] == "0.01"
    assert payload["filters"]["LOT_SIZE"]["step_size"] == "0.0001"
    assert payload["notional_filter_types"] == ["MIN_NOTIONAL", "NOTIONAL"]
    assert payload["source"]["private_or_account_data_used"] is False


@pytest.mark.parametrize(
    "include_min,include_notional",
    [(True, False), (False, True), (True, True)],
)
def test_exchange_info_accepts_min_notional_or_notional_or_both(
    include_min: bool, include_notional: bool
) -> None:
    snapshot = identity.build_exchange_info_snapshot(
        _exchange_info(
            include_min_notional=include_min,
            include_notional=include_notional,
        ),
        snapshot_as_of_utc="2026-07-07T23:59:59Z",
    )
    assert set(snapshot.payload()["notional_filter_types"]) == {
        name
        for name, enabled in (
            ("MIN_NOTIONAL", include_min),
            ("NOTIONAL", include_notional),
        )
        if enabled
    }


def test_exchange_info_rejects_missing_filters_wrong_market_and_private_fields() -> None:
    missing = _exchange_info()
    missing["symbols"][0]["filters"] = missing["symbols"][0]["filters"][1:]
    with pytest.raises(identity.RunIdentityError, match="required exchange-info filters"):
        identity.build_exchange_info_snapshot(
            missing, snapshot_as_of_utc="2026-07-07T23:59:59Z"
        )

    wrong_quote = _exchange_info()
    wrong_quote["symbols"][0]["quoteAsset"] = "USDT"
    with pytest.raises(identity.RunIdentityError, match="ETH/USDC"):
        identity.build_exchange_info_snapshot(
            wrong_quote, snapshot_as_of_utc="2026-07-07T23:59:59Z"
        )

    private = _exchange_info()
    private["api_key"] = "forbidden"
    with pytest.raises(identity.RunIdentityError, match="private or account"):
        identity.build_exchange_info_snapshot(
            private, snapshot_as_of_utc="2026-07-07T23:59:59Z"
        )


def test_exchange_info_snapshot_is_create_only_and_tamper_evident(
    tmp_path: Path,
) -> None:
    snapshot = identity.build_exchange_info_snapshot(
        _exchange_info(), snapshot_as_of_utc="2026-07-07T23:59:59Z"
    )
    path = tmp_path / "exchange-info.json"
    identity.write_exchange_info_snapshot(snapshot, path)
    assert identity.read_exchange_info_snapshot(path) == snapshot
    with pytest.raises(identity.RunIdentityError, match="cannot be overwritten"):
        identity.write_exchange_info_snapshot(snapshot, path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["filters"]["PRICE_FILTER"]["tick_size"] = "0.02"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(identity.RunIdentityError, match="digest mismatch"):
        identity.read_exchange_info_snapshot(path)


def test_complete_run_fingerprint_is_deterministic_and_binds_all_required_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _fingerprint(monkeypatch)
    second = _fingerprint(monkeypatch)
    assert first == second
    payload = first.payload()
    expected = {
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
    }
    assert expected <= set(payload)
    assert first.resume_key == first.cache_key
    assert first.resume_key == f"protocol_v3_run_sha256:{first.fingerprint_sha256}"
    assert payload["as_of_day"] == "2026-07-07"
    assert (
        payload["pipeline"]["permanent_trial_counter_namespace"]
        == PERMANENT_TRIAL_COUNTER_NAMESPACE
    )
    assert payload["trial_ledger_head"]["historical_trial_count_is_lower_bound"] is True


def test_every_required_identity_change_blocks_resume_and_cache_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _fingerprint(monkeypatch)
    mutations = []

    payload = current.payload()
    payload["raw_data"]["snapshot_sha256"] = "b" * 64
    mutations.append(payload)

    payload = current.payload()
    payload["as_of_day"] = "2026-07-06"
    payload["raw_data"]["snapshot_as_of_day"] = "2026-07-06"
    mutations.append(payload)

    payload = current.payload()
    payload["code"]["git_commit"] = "b" * 40
    mutations.append(payload)

    payload = current.payload()
    payload["pipeline"]["generation_basis_sha256"] = "b" * 64
    payload["pipeline"]["generation_id"] = (
        "protocol_v3_pipeline_sha256:" + "b" * 64
    )
    payload["pipeline"]["forward_ledger_namespace"] = (
        "protocol_v3_forward_generation:protocol_v3_pipeline_sha256:" + "b" * 64
    )
    mutations.append(payload)

    for key in (
        "features",
        "context",
        "quality_gates",
        "cost_model",
        "simulator",
        "boundary",
    ):
        payload = current.payload()
        payload[key]["source_sha256"] = "b" * 64
        mutations.append(payload)

    payload = current.payload()
    payload["trial_ledger_head"]["head_sha256"] = "b" * 64
    mutations.append(payload)

    payload = current.payload()
    payload["exchange_info"]["snapshot_sha256"] = "b" * 64
    mutations.append(payload)

    assert len(mutations) == 12
    for changed_payload in mutations:
        changed = _refreeze(changed_payload)
        identity.validate_run_fingerprint(changed)
        with pytest.raises(identity.RunIdentityError, match="resume blocked"):
            identity.assert_resume_compatible(current, changed)
        with pytest.raises(identity.RunIdentityError, match="cache hit blocked"):
            identity.assert_cache_hit_compatible(current, changed)


def test_tampered_run_fingerprint_without_new_digest_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fingerprint = _fingerprint(monkeypatch)
    value = fingerprint.to_dict()
    value["code"]["git_commit"] = "b" * 40
    with pytest.raises(identity.RunIdentityError, match="digest mismatch"):
        identity.validate_run_fingerprint(value)


def test_trial_namespace_mismatch_blocks_fingerprint_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(identity, "validate_frozen_data_snapshot", lambda value: None)
    exchange = identity.build_exchange_info_snapshot(
        _exchange_info(), snapshot_as_of_utc="2026-07-07T23:59:59Z"
    )
    with pytest.raises(identity.RunIdentityError, match="namespace"):
        identity.build_run_fingerprint(
            data_snapshot=_fake_data_snapshot(),
            exchange_info_snapshot=exchange,
            pipeline_generation=build_pipeline_generation(REPO_ROOT),
            code_commit=COMMIT,
            trial_ledger=_trial_identity(
                permanent_trial_counter_namespace="wrong_namespace"
            ),
        )


def test_run_fingerprint_is_create_only_roundtrips_and_rejects_rewritten_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fingerprint = _fingerprint(monkeypatch)
    path = tmp_path / "run-fingerprint.json"
    identity.write_run_fingerprint(fingerprint, path)
    assert identity.read_run_fingerprint(path) == fingerprint
    with pytest.raises(identity.RunIdentityError, match="cannot be overwritten"):
        identity.write_run_fingerprint(fingerprint, path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["cache_key"] = "forged"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(identity.RunIdentityError, match="reuse keys"):
        identity.read_run_fingerprint(path)
