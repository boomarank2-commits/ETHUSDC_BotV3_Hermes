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


def _exchange_info(min_filter: bool = True, notional_filter: bool = True) -> dict:
    filters = [
        {"filterType": "PRICE_FILTER", "minPrice": "0.01000000", "maxPrice": "1000000", "tickSize": "0.01000000"},
        {"filterType": "LOT_SIZE", "minQty": "0.00010000", "maxQty": "9000", "stepSize": "0.00010000"},
        {"filterType": "MARKET_LOT_SIZE", "minQty": "0", "maxQty": "1200", "stepSize": "0.00010000"},
    ]
    if min_filter:
        filters.append({"filterType": "MIN_NOTIONAL", "minNotional": "5", "applyToMarket": True, "avgPriceMins": 5})
    if notional_filter:
        filters.append({"filterType": "NOTIONAL", "minNotional": "5", "maxNotional": "10000000", "applyMinToMarket": True, "applyMaxToMarket": False, "avgPriceMins": 5})
    return {"symbols": [{"symbol": "ETHUSDC", "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "USDC", "isSpotTradingAllowed": True, "filters": filters}]}


def _data_snapshot() -> FrozenDataSnapshot:
    chars = (("2", "5", "8"), ("3", "6", "9"), ("4", "7", "a"))
    markets = [
        {
            "symbol": symbol,
            "timestamp_grid_sha256": "1" * 64,
            "market_content_sha256": content * 64,
            "archive_inventory_sha256": archive * 64,
            "complete_utc_days_sha256": days * 64,
        }
        for symbol, (content, archive, days) in zip(("ETHUSDC", "BTCUSDC", "ETHBTC"), chars)
    ]
    payload = {
        "availability": {"latest_common_complete_day": "2026-07-07"},
        "boundary": {"snapshot_as_of_day": "2026-07-07"},
        "raw_interval": {"start_inclusive": "2023-06-18T23:59:00Z", "end_exclusive": "2026-07-08T00:00:00Z"},
        "market_data": markets,
        "common_minute_grid_sha256": "1" * 64,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return FrozenDataSnapshot(canonical, hashlib.sha256(canonical.encode()).hexdigest())


def _trial(**changes: object) -> dict:
    value = {
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
    exchange = identity.build_exchange_info_snapshot(_exchange_info(), snapshot_as_of_utc="2026-07-07T23:59:59Z")
    return identity.build_run_fingerprint(
        data_snapshot=_data_snapshot(),
        exchange_info_snapshot=exchange,
        pipeline_generation=build_pipeline_generation(REPO_ROOT),
        code_commit=COMMIT,
        trial_ledger=_trial(),
    )


def _refreeze(payload: dict) -> identity.RunFingerprint:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return identity.RunFingerprint(canonical, hashlib.sha256(canonical.encode()).hexdigest())


def test_task5_and_task6_contracts_remain_fail_closed() -> None:
    warmup = build_warmup_plan([
        {"name": "eth", "market": "ETHUSDC", "bars": 20, "bar_seconds": 86400},
        {"name": "btc", "market": "BTCUSDC", "bars": 4, "bar_seconds": 3600},
        {"name": "cross", "market": "ETHBTC", "bars": 4, "bar_seconds": 3600},
    ])
    assert warmup.warmup_duration_seconds == 20 * 86400 + 60
    contract = identity.load_run_identity_contract(REPO_ROOT)
    assert contract["run_fingerprint_policy"]["resume_requires_exact_fingerprint"] is True
    changed = json.loads(json.dumps(contract))
    changed["safety"]["paper"] = "unlocked"
    with pytest.raises(identity.RunIdentityError, match="not canonical"):
        identity.validate_run_identity_contract(changed)


def test_exchange_info_snapshot_binds_filters_and_normalizes_decimals() -> None:
    snapshot = identity.build_exchange_info_snapshot(_exchange_info(), snapshot_as_of_utc="2026-07-07T23:59:59+00:00")
    payload = snapshot.payload()
    assert payload["snapshot_as_of_utc"] == "2026-07-07T23:59:59Z"
    assert payload["filters"]["PRICE_FILTER"]["tick_size"] == "0.01"
    assert payload["filters"]["LOT_SIZE"]["step_size"] == "0.0001"
    assert set(payload["notional_filter_types"]) == {"MIN_NOTIONAL", "NOTIONAL"}
    assert payload["source"]["private_or_account_data_used"] is False


@pytest.mark.parametrize("minimum,notional", [(True, False), (False, True), (True, True)])
def test_exchange_info_accepts_min_notional_or_notional(minimum: bool, notional: bool) -> None:
    snapshot = identity.build_exchange_info_snapshot(_exchange_info(minimum, notional), snapshot_as_of_utc="2026-07-07T23:59:59Z")
    assert bool(snapshot.payload()["notional_filter_types"])


def test_exchange_info_rejects_missing_filter_wrong_quote_and_private_data() -> None:
    missing = _exchange_info()
    missing["symbols"][0]["filters"] = missing["symbols"][0]["filters"][1:]
    with pytest.raises(identity.RunIdentityError, match="required exchange-info"):
        identity.build_exchange_info_snapshot(missing, snapshot_as_of_utc="2026-07-07T23:59:59Z")
    wrong = _exchange_info()
    wrong["symbols"][0]["quoteAsset"] = "USDT"
    with pytest.raises(identity.RunIdentityError, match="ETH/USDC"):
        identity.build_exchange_info_snapshot(wrong, snapshot_as_of_utc="2026-07-07T23:59:59Z")
    private = _exchange_info()
    private["api_key"] = "forbidden"
    with pytest.raises(identity.RunIdentityError, match="private or account"):
        identity.build_exchange_info_snapshot(private, snapshot_as_of_utc="2026-07-07T23:59:59Z")


def test_exchange_snapshot_is_create_only_and_tamper_evident(tmp_path: Path) -> None:
    snapshot = identity.build_exchange_info_snapshot(_exchange_info(), snapshot_as_of_utc="2026-07-07T23:59:59Z")
    path = tmp_path / "exchange.json"
    identity.write_exchange_info_snapshot(snapshot, path)
    assert identity.read_exchange_info_snapshot(path) == snapshot
    with pytest.raises(identity.RunIdentityError, match="cannot be overwritten"):
        identity.write_exchange_info_snapshot(snapshot, path)
    value = json.loads(path.read_text())
    value["filters"]["PRICE_FILTER"]["tick_size"] = "0.02"
    path.write_text(json.dumps(value))
    with pytest.raises(identity.RunIdentityError, match="digest mismatch"):
        identity.read_exchange_info_snapshot(path)


def test_run_fingerprint_is_deterministic_and_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    first = _fingerprint(monkeypatch)
    assert first == _fingerprint(monkeypatch)
    required = {"raw_data", "as_of_day", "code", "pipeline", "features", "context", "quality_gates", "cost_model", "simulator", "boundary", "trial_ledger_head", "exchange_info"}
    assert required <= set(first.payload())
    assert first.resume_key == first.cache_key == f"protocol_v3_run_sha256:{first.fingerprint_sha256}"


def test_each_required_identity_change_blocks_resume_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    current = _fingerprint(monkeypatch)
    mutations = []
    payload = current.payload(); payload["raw_data"]["snapshot_sha256"] = "b" * 64; mutations.append(payload)
    payload = current.payload(); payload["as_of_day"] = payload["raw_data"]["snapshot_as_of_day"] = "2026-07-06"; mutations.append(payload)
    payload = current.payload(); payload["code"]["git_commit"] = "b" * 40; mutations.append(payload)
    payload = current.payload(); payload["pipeline"]["generation_basis_sha256"] = "b" * 64; payload["pipeline"]["generation_id"] = "protocol_v3_pipeline_sha256:" + "b" * 64; payload["pipeline"]["forward_ledger_namespace"] = "changed"; mutations.append(payload)
    for key in ("features", "context", "quality_gates", "cost_model", "simulator", "boundary"):
        payload = current.payload(); payload[key]["source_sha256"] = "b" * 64; mutations.append(payload)
    payload = current.payload(); payload["trial_ledger_head"]["head_sha256"] = "b" * 64; mutations.append(payload)
    payload = current.payload(); payload["exchange_info"]["snapshot_sha256"] = "b" * 64; mutations.append(payload)
    assert len(mutations) == 12
    for payload in mutations:
        changed = _refreeze(payload)
        identity.validate_run_fingerprint(changed)
        with pytest.raises(identity.RunIdentityError, match="resume blocked"):
            identity.assert_resume_compatible(current, changed)
        with pytest.raises(identity.RunIdentityError, match="cache hit blocked"):
            identity.assert_cache_hit_compatible(current, changed)


def test_tamper_namespace_and_rewritten_keys_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fingerprint = _fingerprint(monkeypatch)
    tampered = fingerprint.to_dict(); tampered["code"]["git_commit"] = "b" * 40
    with pytest.raises(identity.RunIdentityError, match="digest mismatch"):
        identity.validate_run_fingerprint(tampered)
    monkeypatch.setattr(identity, "validate_frozen_data_snapshot", lambda value: None)
    exchange = identity.build_exchange_info_snapshot(_exchange_info(), snapshot_as_of_utc="2026-07-07T23:59:59Z")
    with pytest.raises(identity.RunIdentityError, match="namespace"):
        identity.build_run_fingerprint(data_snapshot=_data_snapshot(), exchange_info_snapshot=exchange, pipeline_generation=build_pipeline_generation(REPO_ROOT), code_commit=COMMIT, trial_ledger=_trial(permanent_trial_counter_namespace="wrong"))
    path = tmp_path / "fingerprint.json"
    identity.write_run_fingerprint(fingerprint, path)
    assert identity.read_run_fingerprint(path) == fingerprint
    value = json.loads(path.read_text()); value["cache_key"] = "forged"; path.write_text(json.dumps(value))
    with pytest.raises(identity.RunIdentityError, match="reuse keys"):
        identity.read_run_fingerprint(path)
