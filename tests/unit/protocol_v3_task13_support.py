"""Shared real Protocol-v3 fixtures for Task-13 through Task-15 tests."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import hashlib
import os
from pathlib import Path
import shutil

import pytest

import ethusdc_bot.protocol_v3.data_snapshot as snapshot_module
from ethusdc_bot.backtest.context_features import ContextVetoPolicy
from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
from ethusdc_bot.protocol_v3 import transactional_cache as tx
from ethusdc_bot.protocol_v3 import transactional_cache_api
from ethusdc_bot.protocol_v3.artifact_store_api import (
    DIAGNOSTICS,
    build_artifact_payload,
    persist_compact_artifact_bundle,
)
from ethusdc_bot.protocol_v3.boundaries import build_monthly_process_boundary_plan
from ethusdc_bot.protocol_v3.context_parity import build_context_parity_binding
from ethusdc_bot.protocol_v3.data_snapshot import (
    FrozenDataSnapshot,
    MarketDayAudit,
    build_three_market_data_snapshot,
    compute_utc_day_content_sha256,
    validate_frozen_data_snapshot,
)
from ethusdc_bot.protocol_v3.inner_folds import (
    INNER_FOLD_CONTRACT_PATH,
    build_inner_fold_plan_for_origin,
)
from ethusdc_bot.protocol_v3.inner_selection_api import (
    build_frozen_selection_config,
    build_incomplete_development_support,
    build_selection_training_window,
    select_candidate,
)
from ethusdc_bot.protocol_v3.pipeline import (
    BudgetUsage,
    build_pipeline_generation,
    build_pre_run_manifest,
)
from ethusdc_bot.protocol_v3.reporting_api import (
    PROTOCOL_V3_RESEARCH,
    build_protocol_v3_report,
    write_protocol_v3_report,
)
from ethusdc_bot.protocol_v3.run_identity import (
    build_exchange_info_snapshot,
    build_run_fingerprint,
)
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy
from ethusdc_bot.protocol_v3.trial_ledger import (
    append_trial,
    build_trial_record,
    initialize_trial_ledger,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40
HORIZON = HorizonPolicy(10, 10, 2)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _fake_audit(symbol: str, day: date) -> MarketDayAudit:
    start = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)
    return MarketDayAudit(
        symbol=symbol,
        day=day,
        candle_count=1440,
        first_open_time_ms=start,
        last_open_time_ms=start + 1439 * 60_000,
        zero_volume_candles=0,
        timestamp_grid_sha256=_digest(f"grid:{day}"),
        content_sha256=_digest(f"content:{symbol}:{day}"),
        zip_sha256=_digest(f"zip:{symbol}:{day}"),
        checksum_sha256=_digest(f"checksum:{symbol}:{day}"),
    )


class _FakeInspector:
    latest_day = date(2025, 3, 7)
    first_day = latest_day - timedelta(days=1200)

    def __init__(self, raw_root: Path) -> None:
        self.raw_root = raw_root

    def files_by_day(self, symbol: str) -> dict[date, Path]:
        result: dict[date, Path] = {}
        current = self.first_day
        while current <= self.latest_day:
            result[current] = Path(f"/{symbol}-1m-{current}.zip")
            current += timedelta(days=1)
        return result

    def audit_day(self, symbol: str, day: date, zip_path: Path) -> MarketDayAudit:
        return _fake_audit(symbol, day)


def _series(base: float) -> tuple[Candle, ...]:
    start = int(datetime(2025, 3, 1, tzinfo=UTC).timestamp() * 1000)
    return tuple(
        Candle(
            open_time=start + index * 60_000,
            open=base + index * 0.0001,
            high=base + index * 0.0001 + 0.01,
            low=base + index * 0.0001 - 0.01,
            close=base + index * 0.0001,
            volume=10.0,
        )
        for index in range(1440)
    )


def _context() -> AlignedMarketCandles:
    return AlignedMarketCandles(
        ethusdc=_series(100.0),
        btcusdc=_series(200.0),
        ethbtc=_series(1.0),
    )


def _snapshot(
    monkeypatch: pytest.MonkeyPatch,
    context: AlignedMarketCandles,
) -> FrozenDataSnapshot:
    monkeypatch.setattr(snapshot_module, "_ZipMarketInspector", _FakeInspector)
    snapshot = build_three_market_data_snapshot(
        Path("/external/protocol-v3-data"),
        [
            {"name": "eth", "market": "ETHUSDC", "bars": 3, "bar_seconds": 60},
            {"name": "btc", "market": "BTCUSDC", "bars": 3, "bar_seconds": 60},
            {"name": "ratio", "market": "ETHBTC", "bars": 3, "bar_seconds": 60},
        ],
        repo_root=REPO_ROOT,
    )
    payload = snapshot.payload()
    target_day = date(2025, 3, 1)
    for (symbol, candles), market in zip(
        (
            ("ETHUSDC", context.ethusdc),
            ("BTCUSDC", context.btcusdc),
            ("ETHBTC", context.ethbtc),
        ),
        payload["market_data"],
        strict=True,
    ):
        row = next(
            item
            for item in market["utc_day_content_sha256"]
            if item["day"] == str(target_day)
        )
        row["content_sha256"] = compute_utc_day_content_sha256(symbol, target_day, candles)
        market["market_content_sha256"] = snapshot_module._sha256_json(
            market["utc_day_content_sha256"]
        )
    canonical = snapshot_module._canonical_json(payload)
    frozen = FrozenDataSnapshot(canonical, hashlib.sha256(canonical.encode()).hexdigest())
    validate_frozen_data_snapshot(frozen, repo_root=REPO_ROOT)
    return frozen


def _exchange():
    return build_exchange_info_snapshot(
        {
            "symbols": [
                {
                    "symbol": "ETHUSDC",
                    "status": "TRADING",
                    "baseAsset": "ETH",
                    "quoteAsset": "USDC",
                    "isSpotTradingAllowed": True,
                    "filters": [
                        {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                        {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "9000", "stepSize": "0.0001"},
                        {"filterType": "MARKET_LOT_SIZE", "minQty": "0.0001", "maxQty": "1200", "stepSize": "0.0001"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "5", "applyToMarket": True, "avgPriceMins": 5},
                    ],
                }
            ]
        },
        snapshot_as_of_utc="2026-07-07T23:59:59Z",
    )


def _trial(ledger_root: Path):
    initialize_trial_ledger(
        ledger_root,
        required_historical_import_sha256="0" * 64,
    )
    record = build_trial_record(
        source_kind="native_evaluation",
        candidate_id="candidate_01",
        family="fixture",
        parameters={"x": 1},
        feature_variant="fixture",
        seed=1,
        versions={
            "pipeline_generation": "fixture",
            "ranking_version": "fixture",
            "gate_version": "fixture",
            "simulator_version": "fixture",
            "cost_model_version": "fixture",
            "boundary_version": "fixture",
        },
        code_commit=COMMIT,
        evaluation_scope={"origin": 1, "cycle": 1},
        daily_net_mtm_usdc=[{"day": "2025-03-01", "net_usdc": 0.0}],
        result_summary={"net_usdc": 0.0},
    )
    ledger = append_trial(ledger_root, record)
    return ledger, record


def _report_and_index(repo: Path, run_key: str, pipeline_key: str) -> Path:
    report = build_protocol_v3_report(
        artifact_kind=PROTOCOL_V3_RESEARCH,
        report_id="task13_parent",
        created_at_utc="2026-07-16T00:00:00Z",
        run_fingerprint=run_key,
        pipeline_generation=pipeline_key,
        window_id="historical_window",
        start_inclusive_utc="2024-01-01T00:00:00Z",
        end_exclusive_utc="2025-01-01T00:00:00Z",
        process_oos_net_usdc=None,
        producer="task13_fixture",
        producer_status="completed_diagnostic",
    )
    report_path = write_protocol_v3_report(report, repo)
    artifact = build_artifact_payload(
        DIAGNOSTICS,
        [{"record_id": "fixture", "category": "task13", "data": {"ok": True}}],
    )
    return persist_compact_artifact_bundle(
        parent_report_path=report_path,
        repository_root=repo,
        work_unit_id="origin_01_cycle_01",
        work_unit_identity={"origin": 1, "cycle": 1},
        artifacts={"diagnostics": artifact},
    )


def build_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    contract_target = tmp_path / INNER_FOLD_CONTRACT_PATH
    contract_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / INNER_FOLD_CONTRACT_PATH, contract_target)

    context = _context()
    snapshot = _snapshot(monkeypatch, context)
    binding = build_context_parity_binding(
        context,
        ContextVetoPolicy(
            btc_trend_lookback=3,
            btc_min_trend_bps=-20,
            btc_volatility_lookback=3,
            btc_max_volatility_bps=100,
            ethbtc_trend_lookback=3,
            ethbtc_min_trend_bps=-20,
        ),
        snapshot,
        repo_root=REPO_ROOT,
    )
    generation = build_pipeline_generation(REPO_ROOT)
    ledger_root = tmp_path / "ledger"
    ledger, record = _trial(ledger_root)
    fingerprint = build_run_fingerprint(
        data_snapshot=snapshot,
        exchange_info_snapshot=_exchange(),
        pipeline_generation=generation,
        context_binding=binding,
        code_commit=COMMIT,
        trial_ledger=ledger,
        repo_root=REPO_ROOT,
    )
    boundary_plan = build_monthly_process_boundary_plan("2026-07-08")
    manifest = build_pre_run_manifest(generation, boundary_plan, code_commit=COMMIT)
    inner_fold_plan = build_inner_fold_plan_for_origin(
        boundary_plan.origins[0], HORIZON, repo_root=REPO_ROOT
    )
    training_window = build_selection_training_window(inner_fold_plan)
    development_support = build_incomplete_development_support(
        "tasks16_17_18_not_implemented"
    )
    selection_config = build_frozen_selection_config(
        pre_run_manifest=manifest,
        run_fingerprint=fingerprint,
        fold_identity=inner_fold_plan.identity_payload,
        origin_index=1,
        cycle_index=1,
        generated_candidate_ids=[],
        tested_candidate_ids=[],
        walk_forward_candidate_ids=[],
        finalist_candidate_ids=[],
        candidate_evidence=[],
        development_support=development_support,
    )
    selection_decision = select_candidate(training_window, selection_config)
    assert selection_decision.outcome == "NO_TRADE"

    index_path = _report_and_index(tmp_path, fingerprint.resume_key, generation.generation_id)
    identity = tx.build_transaction_identity(
        run_fingerprint=fingerprint,
        context_binding=binding,
        horizon_policy=HORIZON,
        work_unit_id="origin_01_cycle_01",
        candidate_identity=tx.build_bound_identity_slot(
            tx.CANDIDATE_SLOT,
            tx.CANDIDATE_SELECTION_IDENTITY_SCHEMA,
            selection_decision.candidate_identity_payload,
        ),
        fold_identity=tx.build_bound_identity_slot(
            tx.FOLD_SLOT,
            tx.FOLD_IDENTITY_SCHEMA,
            inner_fold_plan.identity_payload,
        ),
        rotation_state_identity=tx.build_genesis_identity_slot(
            tx.ROTATION_SLOT,
            "protocol_v3_rotation_identity_genesis_v1",
            "no_rotation_state",
        ),
        sealed_store_heads=tx.build_sealed_store_heads_slot([index_path], tmp_path),
        repository_root=tmp_path,
    )
    return {
        "repo": tmp_path,
        "ledger_root": ledger_root,
        "record": record,
        "fingerprint": fingerprint,
        "binding": binding,
        "manifest": manifest,
        "identity": identity,
        "inner_fold_plan": inner_fold_plan,
        "training_window": training_window,
        "selection_config": selection_config,
        "selection_decision": selection_decision,
        "development_support": development_support,
        "index_path": index_path,
        "budget": BudgetUsage().reserve_next_cycle(1),
        "seed": tx.build_seed_state(manifest, origin_index=1, cycle_index=1),
        "stop": tx.build_stop_state(completed_cycles=0, consecutive_non_improving_cycles=0),
    }


def _commit(state, *, status="COMPLETED", payload=None, cache_record=None, fault=None):
    lock = tx.acquire_transaction_lock(
        state["identity"].transaction_id,
        state["repo"],
        owner_id="test_owner",
    )
    try:
        return tx.commit_checkpoint(
            identity=state["identity"],
            pre_run_manifest=state["manifest"],
            seed_state=state["seed"],
            budget_usage=state["budget"],
            stop_state=state["stop"],
            result_status=status,
            result_payload=payload or {"decision": "NO_TRADE"},
            repository_root=state["repo"],
            trial_ledger_root=state["ledger_root"],
            lock=lock,
            cache_record=cache_record,
            fault_injector=fault,
        )
    finally:
        current = tx.inspect_transaction_lock(
            state["identity"].transaction_id,
            state["repo"],
        )
        if current is not None and current.to_dict()["process_id"] == os.getpid():
            tx.release_transaction_lock(current, state["repo"])
