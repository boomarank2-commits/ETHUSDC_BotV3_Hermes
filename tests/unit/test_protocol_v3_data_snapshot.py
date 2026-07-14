"""Protocol v3 task-5 tests for dynamic three-market snapshots and warmup."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

import ethusdc_bot.protocol_v3.data_snapshot as snapshot_module
from ethusdc_bot.protocol_v3.data_snapshot import (
    ActiveLookback,
    DataSnapshotError,
    FrozenDataSnapshot,
    MarketDayAudit,
    _ZipMarketInspector,
    build_three_market_data_snapshot,
    build_warmup_plan,
    load_data_snapshot_contract,
    read_frozen_data_snapshot,
    validate_data_snapshot_contract,
    validate_frozen_data_snapshot,
    write_frozen_data_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MARKETS = ("ETHUSDC", "BTCUSDC", "ETHBTC")


def _lookbacks() -> list[dict[str, object]]:
    return [
        {"name": "eth_range_20d", "market": "ETHUSDC", "bars": 20, "bar_seconds": 86400},
        {"name": "btc_return_168h", "market": "BTCUSDC", "bars": 168, "bar_seconds": 3600},
        {"name": "ethbtc_return_72h", "market": "ETHBTC", "bars": 72, "bar_seconds": 3600},
    ]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fake_audit(symbol: str, day: date, *, zero_volume: int = 0) -> MarketDayAudit:
    start_ms = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    return MarketDayAudit(
        symbol=symbol,
        day=day,
        candle_count=1440,
        first_open_time_ms=start_ms,
        last_open_time_ms=start_ms + 1439 * 60_000,
        zero_volume_candles=zero_volume,
        timestamp_grid_sha256=_digest(f"grid:{day.isoformat()}"),
        content_sha256=_digest(f"content:{symbol}:{day.isoformat()}"),
        zip_sha256=_digest(f"zip:{symbol}:{day.isoformat()}"),
        checksum_sha256=_digest(f"checksum:{symbol}:{day.isoformat()}"),
    )


class FakeInspector:
    latest_day = date(2025, 3, 7)
    first_day = latest_day - timedelta(days=1200)
    invalid: dict[tuple[str, date], str] = {}
    missing: dict[str, set[date]] = {symbol: set() for symbol in MARKETS}
    zero_day: date | None = None

    def __init__(self, raw_root: Path) -> None:
        self.raw_root = raw_root

    def files_by_day(self, symbol: str) -> dict[date, Path]:
        result: dict[date, Path] = {}
        current = self.first_day
        while current <= self.latest_day:
            if current not in self.missing.get(symbol, set()):
                result[current] = Path(f"/{symbol}-1m-{current.isoformat()}.zip")
            current += timedelta(days=1)
        return result

    def audit_day(self, symbol: str, day: date, zip_path: Path) -> MarketDayAudit:
        reason = self.invalid.get((symbol, day))
        if reason:
            raise DataSnapshotError(reason)
        zero = 1 if symbol == "ETHUSDC" and day == self.zero_day else 0
        return _fake_audit(symbol, day, zero_volume=zero)


def _install_fake(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> type[FakeInspector]:
    class ConfiguredFake(FakeInspector):
        pass

    ConfiguredFake.latest_day = overrides.get("latest_day", FakeInspector.latest_day)  # type: ignore[assignment]
    ConfiguredFake.first_day = overrides.get(
        "first_day", ConfiguredFake.latest_day - timedelta(days=1200)
    )  # type: ignore[assignment]
    ConfiguredFake.invalid = dict(overrides.get("invalid", {}))  # type: ignore[arg-type]
    ConfiguredFake.missing = {
        symbol: set(dict(overrides.get("missing", {})).get(symbol, set())) for symbol in MARKETS
    }
    ConfiguredFake.zero_day = overrides.get("zero_day")  # type: ignore[assignment]
    monkeypatch.setattr(snapshot_module, "_ZipMarketInspector", ConfiguredFake)
    return ConfiguredFake


def test_task4_final_state_remains_fail_closed() -> None:
    manifest = json.loads(
        (REPO_ROOT / "configs/protocol_v3_historical_trial_lower_bound.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["historical_trial_count_is_lower_bound"] is True
    assert manifest["known_observed_evaluation_rows"] == 180
    assert manifest["independent_trial_count_resolved"] == 0
    assert manifest["interpretation"]["development_dsr_status"] == "INSUFFICIENT_TRIAL_HISTORY"
    assert manifest["interpretation"]["only_release_decision_allowed"] == "NO_TRADE"


def test_data_snapshot_contract_is_exact_and_safety_locked() -> None:
    contract = load_data_snapshot_contract(REPO_ROOT)
    validate_data_snapshot_contract(contract)
    assert contract["fit_process_days"] == 1095
    assert [row["symbol"] for row in contract["markets"]] == list(MARKETS)
    assert contract["quality_policy"]["all_zero_volume_day_blocks"] is True
    assert contract["safety"] == {
        "api_keys": "forbidden",
        "live": "locked",
        "orders": "locked",
        "paper": "locked",
        "testtrade": "locked",
        "trading_api": "forbidden",
    }

    changed = json.loads(json.dumps(contract))
    changed["quality_policy"]["gaps_allowed"] = True
    with pytest.raises(DataSnapshotError, match="not canonical"):
        validate_data_snapshot_contract(changed)


def test_warmup_is_max_active_lookback_plus_one_1m_source_bar() -> None:
    plan = build_warmup_plan(_lookbacks())
    assert plan.max_lookback_seconds == 20 * 86400
    assert plan.smallest_source_bar_seconds == 60
    assert plan.warmup_duration_seconds == 20 * 86400 + 60
    assert plan.warmup_source_bars == 28_801
    assert [row.market for row in plan.active_lookbacks] == ["BTCUSDC", "ETHBTC", "ETHUSDC"]


def test_warmup_requires_all_three_markets_and_exact_1m_alignment() -> None:
    with pytest.raises(DataSnapshotError, match="active_lookback_set_required"):
        build_warmup_plan([])
    with pytest.raises(DataSnapshotError, match="represent"):
        build_warmup_plan(_lookbacks()[:2])
    invalid = _lookbacks()
    invalid[0] = {"name": "bad", "market": "ETHUSDC", "bars": 3, "bar_seconds": 100}
    with pytest.raises(DataSnapshotError, match="align"):
        build_warmup_plan(invalid)
    duplicate = _lookbacks() + [_lookbacks()[0]]
    with pytest.raises(DataSnapshotError, match="unique"):
        build_warmup_plan(duplicate)


def test_dynamic_snapshot_uses_latest_common_day_and_task2_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    latest = date(2025, 3, 7)
    _install_fake(monkeypatch, latest_day=latest, zero_day=date(2022, 2, 16))

    snapshot = build_three_market_data_snapshot(
        tmp_path / "external-data",
        _lookbacks(),
        repo_root=REPO_ROOT,
    )
    validate_frozen_data_snapshot(snapshot, repo_root=REPO_ROOT)
    payload = snapshot.payload()

    assert payload["availability"]["latest_common_complete_day"] == "2025-03-07"
    assert payload["boundary"]["process_end_exclusive"] == "2025-03-08"
    assert payload["boundary"]["fit_process_start_inclusive"] == "2022-03-09"
    assert payload["boundary"]["fit_process_days"] == 1095
    assert payload["warmup"]["warmup_start_inclusive"] == "2022-02-16T23:59:00Z"
    assert payload["raw_interval"]["audited_full_day_start"] == "2022-02-16"
    assert payload["raw_interval"]["audited_full_day_count"] == 1116
    assert payload["raw_interval"]["extra_leading_audited_minutes"] == 1439
    assert payload["quality_status"] == "usable_for_protocol_v3_snapshot"
    assert len(snapshot.snapshot_sha256) == 64
    assert len(payload["market_data"]) == 3
    assert payload["market_data"][0]["may_trigger_orders"] is True
    assert payload["market_data"][1]["may_trigger_orders"] is False
    assert payload["market_data"][2]["may_trigger_orders"] is False
    assert len({row["timestamp_grid_sha256"] for row in payload["market_data"]}) == 1


def test_snapshot_has_no_fixed_2026_07_07_watermark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake(monkeypatch, latest_day=date(2024, 3, 7))
    snapshot = build_three_market_data_snapshot(tmp_path / "raw", _lookbacks(), repo_root=REPO_ROOT)
    assert snapshot.payload()["availability"]["latest_common_complete_day"] == "2024-03-07"
    assert snapshot.payload()["boundary"]["process_end_exclusive"] == "2024-03-08"


def test_trailing_incomplete_common_day_is_recorded_and_previous_complete_day_is_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid_day = date(2025, 3, 8)
    _install_fake(
        monkeypatch,
        latest_day=invalid_day,
        invalid={("ETHUSDC", invalid_day): "ETHUSDC trailing day has only 1,439 rows"},
    )
    snapshot = build_three_market_data_snapshot(tmp_path / "raw", _lookbacks(), repo_root=REPO_ROOT)
    payload = snapshot.payload()
    assert payload["availability"]["latest_common_complete_day"] == "2025-03-07"
    assert payload["trailing_incomplete_common_days"][0]["day"] == "2025-03-08"
    assert "1,439" in payload["trailing_incomplete_common_days"][0]["reason"]


def test_missing_warmup_in_one_market_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    latest = date(2025, 3, 7)
    process_end = date(2025, 3, 8)
    fit_start = process_end - timedelta(days=1095)
    warmup_start = datetime(fit_start.year, fit_start.month, fit_start.day, tzinfo=UTC) - timedelta(
        seconds=build_warmup_plan(_lookbacks()).warmup_duration_seconds
    )
    _install_fake(
        monkeypatch,
        latest_day=latest,
        missing={"ETHBTC": {warmup_start.date()}},
    )
    with pytest.raises(DataSnapshotError, match="ETHBTC is missing required warmup"):
        build_three_market_data_snapshot(tmp_path / "raw", _lookbacks(), repo_root=REPO_ROOT)


def test_gap_or_invalid_required_day_in_any_market_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_day = date(2023, 1, 15)
    _install_fake(
        monkeypatch,
        latest_day=date(2025, 3, 7),
        invalid={("BTCUSDC", bad_day): "gap after minute 720"},
    )
    with pytest.raises(DataSnapshotError, match="gap after minute 720"):
        build_three_market_data_snapshot(tmp_path / "raw", _lookbacks(), repo_root=REPO_ROOT)


def test_snapshot_is_immutable_roundtrip_and_tampering_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake(monkeypatch, latest_day=date(2025, 3, 7))
    snapshot = build_three_market_data_snapshot(tmp_path / "raw", _lookbacks(), repo_root=REPO_ROOT)
    path = write_frozen_data_snapshot(snapshot, tmp_path / "snapshots" / "snapshot.json")
    loaded = read_frozen_data_snapshot(path, repo_root=REPO_ROOT)
    assert loaded == snapshot
    with pytest.raises(DataSnapshotError, match="cannot be overwritten"):
        write_frozen_data_snapshot(snapshot, path)

    value = json.loads(path.read_text(encoding="utf-8"))
    value["boundary"]["process_end_exclusive"] = "2025-04-08"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(DataSnapshotError, match="digest mismatch"):
        read_frozen_data_snapshot(path, repo_root=REPO_ROOT)


def test_semantic_tampering_blocks_even_with_recomputed_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake(monkeypatch, latest_day=date(2025, 3, 7))
    snapshot = build_three_market_data_snapshot(tmp_path / "raw", _lookbacks(), repo_root=REPO_ROOT)
    payload = snapshot.payload()
    payload["market_data"][1]["may_trigger_orders"] = True
    canonical = snapshot_module._canonical_json(payload)
    tampered = FrozenDataSnapshot(canonical, hashlib.sha256(canonical.encode("utf-8")).hexdigest())
    with pytest.raises(DataSnapshotError, match="market role"):
        validate_frozen_data_snapshot(tampered, repo_root=REPO_ROOT)


def _write_daily_zip(
    raw_root: Path,
    symbol: str,
    day: date,
    *,
    zero_volume_minute: int | None = None,
    all_zero: bool = False,
    gap_minute: int | None = None,
    invalid_ohlc_minute: int | None = None,
) -> Path:
    folder = raw_root / "raw" / "binance" / "spot" / symbol / "klines" / "1m"
    folder.mkdir(parents=True, exist_ok=True)
    zip_path = folder / f"{symbol}-1m-{day.isoformat()}.zip"
    rows: list[str] = []
    start_ms = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    for minute in range(1440):
        if minute == gap_minute:
            continue
        open_time = start_ms + minute * 60_000
        open_price = 100.0
        high = 101.0
        low = 99.0
        close = 100.5
        if minute == invalid_ohlc_minute:
            high = 99.5
        volume = 0.0 if all_zero or minute == zero_volume_minute else 1.0
        rows.append(f"{open_time},{open_price},{high},{low},{close},{volume}\n")
    inner = f"{symbol}-1m-{day.isoformat()}.csv"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(inner, "".join(rows))
    zip_path.with_name(zip_path.name + ".CHECKSUM").write_text("fixture-checksum\n", encoding="utf-8")
    return zip_path


def test_real_zip_day_audit_checks_1440_grid_ohlc_and_zero_volume(tmp_path: Path) -> None:
    day = date(2025, 1, 2)
    zip_path = _write_daily_zip(tmp_path, "ETHUSDC", day, zero_volume_minute=17)
    inspector = _ZipMarketInspector(tmp_path)
    audit = inspector.audit_day("ETHUSDC", day, zip_path)
    assert audit.candle_count == 1440
    assert audit.zero_volume_candles == 1
    assert len(audit.content_sha256) == 64
    assert len(audit.zip_sha256) == 64


def test_real_zip_day_audit_blocks_gap_bad_ohlc_and_all_zero(tmp_path: Path) -> None:
    day = date(2025, 1, 2)
    gap = _write_daily_zip(tmp_path / "gap", "ETHUSDC", day, gap_minute=700)
    with pytest.raises(DataSnapshotError, match="gap|1,439"):
        _ZipMarketInspector(tmp_path / "gap").audit_day("ETHUSDC", day, gap)

    bad_ohlc = _write_daily_zip(
        tmp_path / "ohlc", "ETHUSDC", day, invalid_ohlc_minute=10
    )
    with pytest.raises(DataSnapshotError, match="OHLC|inconsistent"):
        _ZipMarketInspector(tmp_path / "ohlc").audit_day("ETHUSDC", day, bad_ohlc)

    all_zero = _write_daily_zip(tmp_path / "zero", "ETHUSDC", day, all_zero=True)
    with pytest.raises(DataSnapshotError, match="zero volume in every candle"):
        _ZipMarketInspector(tmp_path / "zero").audit_day("ETHUSDC", day, all_zero)
