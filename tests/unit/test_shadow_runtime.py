"""Durable public-data-only Shadow runtime tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.portfolio_simulator import simulate_portfolio_strategy
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.portfolio import PortfolioPolicy, canonical_portfolio_signature
from ethusdc_bot.shadow import runtime as runtime_module
from ethusdc_bot.shadow.runtime import (
    ShadowRuntime,
    ShadowRuntimeIntegrityError,
    ShadowRuntimeStateError,
)
from ethusdc_bot.shadow.schema import (
    canonical_signature_payload,
    shadow_safety_status,
)
from ethusdc_bot.shadow.store import (
    GENESIS_HASH,
    append_event,
    canonical_json_bytes,
    read_event_log,
    write_deployment_atomic,
    write_state_atomic,
)


def _candles(closes: list[float], *, start_minute: int = 0) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=start_minute)
    return [
        Candle(
            open_time=int((start + timedelta(minutes=index)).timestamp() * 1000),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1.0,
        )
        for index, close in enumerate(closes)
    ]


def _adopted_dir(
    tmp_path,
    *,
    family: str = "always_long",
    params: dict[str, float | int | str] | None = None,
    budget: int = 100,
):
    """Create the exact three-file output contract of Shadow adoption."""

    candidate_params = {
        "symbol": "ETHUSDC",
        "side": "LONG",
        **(params or {"max_hold_minutes": 99}),
    }
    candidate = {
        "candidate_id": "candidate-runtime-001",
        "family": family,
        "params": candidate_params,
        "candidate_signature": canonical_signature_payload(family, candidate_params),
    }
    report = {
        "schema_version": 1,
        "report_type": "final_evaluation",
        "final_evaluation_id": "final-runtime-001",
        "source_research_run_id": "research-runtime-001",
        "git_commit": "c2b65c8",
        "candidate": candidate,
        # The runtime binds to the already-adopted report; the adoption module
        # owns quality-gate validation, so unrelated report fields are opaque.
        "quality_gate_evidence": {"already_verified_by_adoption": True},
    }
    report_path = tmp_path / "final-runtime-001.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    policy = PortfolioPolicy(budget)
    deployment = {
        "schema_version": 1,
        "deployment_id": "shadow-final-runtime-001",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "mode": "public_data_shadow",
        "status": "adopted",
        "source_report": {
            "path": str(report_path.resolve()),
            "sha256": sha256(report_path.read_bytes()).hexdigest(),
            "final_evaluation_id": report["final_evaluation_id"],
            "source_research_run_id": report["source_research_run_id"],
            "git_commit": report["git_commit"],
        },
        "candidate": candidate,
        "portfolio_policy": {
            "policy": policy.to_dict(),
            "canonical_signature": canonical_portfolio_signature(policy),
        },
        "cost_model": {
            "fee_rate_per_side": 0.001,
            "fee_bps_per_side": 10.0,
            "slippage_bps_per_side": 5.0,
        },
        "assessment": {
            "color": "green",
            "shadow_eligible": True,
            "target_reached": True,
            "live_eligible": False,
            "reason_codes": ["all_quality_gates_passed"],
        },
        "safety": shadow_safety_status(),
    }
    deployment_dir = tmp_path / deployment["deployment_id"]
    deployment_dir.mkdir()
    write_deployment_atomic(deployment_dir / "deployment.json", deployment)
    adopted = append_event(
        deployment_dir / "events.jsonl",
        "deployment_adopted",
        {
            "deployment_id": deployment["deployment_id"],
            "final_evaluation_id": report["final_evaluation_id"],
            "source_report_sha256": deployment["source_report"]["sha256"],
            "candidate_id": candidate["candidate_id"],
            "candidate_signature": candidate["candidate_signature"],
            "assessment_color": "green",
            "deployment_budget_usdc": budget,
            "lot_notional_usdc": 100,
            "orders_enabled": False,
            "trading_api_enabled": False,
            "api_keys_used": False,
        },
        timestamp_utc=deployment["created_at_utc"],
    )
    write_state_atomic(
        deployment_dir / "state.json",
        {
            "schema_version": 1,
            "deployment_id": deployment["deployment_id"],
            "phase": "adopted_stopped",
            "created_at_utc": deployment["created_at_utc"],
            "updated_at_utc": deployment["created_at_utc"],
            "deployment_budget_usdc": budget,
            "lot_notional_usdc": 100.0,
            "max_open_lots": budget // 100,
            "last_processed_candle_open_time_ms": None,
            "open_lots": [],
            "realized_net_usdc": 0.0,
            "unrealized_net_usdc": 0.0,
            "event_count": 1,
            "last_event_hash": adopted["event_hash"],
            "error": None,
            "safety": shadow_safety_status(),
        },
    )
    return deployment_dir, report_path, deployment


def test_adoption_runtime_restart_is_exact_and_every_candle_is_a_full_reduction(tmp_path):
    deployment_dir, _, _ = _adopted_dir(tmp_path)
    candles = _candles([100, 101, 102])
    runtime = ShadowRuntime.open(deployment_dir)

    runtime.start()
    result = runtime.process_closed_candles(candles)
    before_restart = runtime.state
    replay_before = runtime.replay_state
    restarted = ShadowRuntime.open(deployment_dir)

    assert result.processed_candles == 3
    assert restarted.recovered_snapshot is False
    assert restarted.state == before_restart
    assert restarted.replay_state == replay_before
    candle_events = [
        event
        for event in read_event_log(deployment_dir / "events.jsonl")
        if event["event_type"] == "candle_reduced"
    ]
    assert len(candle_events) == 3
    assert set(candle_events[0]["payload"]["candle"]) == {
        "open_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    assert isinstance(candle_events[0]["payload"]["step_events"], list)
    assert isinstance(candle_events[0]["payload"]["trades"], list)
    assert len(candle_events[0]["payload"]["resulting_state_digest"]) == 64
    assert restarted.state["safety"] == shadow_safety_status()


def test_event_fsync_before_snapshot_crash_is_repaired_only_from_exact_prefix(
    tmp_path, monkeypatch
):
    deployment_dir, _, _ = _adopted_dir(tmp_path)
    runtime = ShadowRuntime.open(deployment_dir)
    runtime.start()
    state_before_crash = json.loads(
        (deployment_dir / "state.json").read_text(encoding="utf-8")
    )
    original_writer = runtime_module.write_state_atomic

    def fail_snapshot(*_args, **_kwargs):
        raise OSError("simulated crash after event fsync")

    monkeypatch.setattr(runtime_module, "write_state_atomic", fail_snapshot)
    with pytest.raises(ShadowRuntimeIntegrityError, match="event is durable"):
        runtime.process_closed_candles(_candles([100]))
    assert json.loads(
        (deployment_dir / "state.json").read_text(encoding="utf-8")
    ) == state_before_crash
    assert len(read_event_log(deployment_dir / "events.jsonl")) == 3

    monkeypatch.setattr(runtime_module, "write_state_atomic", original_writer)
    recovered = ShadowRuntime.open(deployment_dir)

    assert recovered.recovered_snapshot is True
    assert recovered.state["event_count"] == 3
    assert recovered.state["last_processed_candle_open_time_ms"] == _candles([100])[0].open_time
    assert json.loads(
        (deployment_dir / "state.json").read_text(encoding="utf-8")
    ) == recovered.state


def test_rehashed_candle_or_state_digest_tamper_still_fails_deterministic_replay(
    tmp_path,
):
    deployment_dir, _, _ = _adopted_dir(tmp_path)
    runtime = ShadowRuntime.open(deployment_dir)
    runtime.start()
    runtime.process_closed_candles(_candles([100, 101]))
    events_path = deployment_dir / "events.jsonl"
    records = read_event_log(events_path)
    records[-1]["payload"]["candle"]["close"] = 777.0
    _rewrite_valid_hash_chain(events_path, records)

    with pytest.raises(ShadowRuntimeIntegrityError, match="determin"):
        ShadowRuntime.open(deployment_dir)


def test_modified_source_report_breaks_deployment_report_hash_binding(tmp_path):
    deployment_dir, report_path, _ = _adopted_dir(tmp_path)
    report_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ShadowRuntimeIntegrityError, match="SHA-256"):
        ShadowRuntime.open(deployment_dir)


def test_duplicate_is_idempotent_but_gap_persists_pause_without_fill(tmp_path):
    deployment_dir, _, _ = _adopted_dir(tmp_path)
    runtime = ShadowRuntime.open(deployment_dir)
    runtime.start()
    first_two = _candles([100, 101])
    runtime.process_closed_candles(first_two)
    event_count = runtime.state["event_count"]

    duplicate = runtime.process_closed_candles([first_two[-1]])
    assert duplicate.ignored_idempotent_candles == 1
    assert runtime.state["event_count"] == event_count

    gap = runtime.process_closed_candles(_candles([103], start_minute=3))
    assert gap.phase == "paused"
    assert gap.processed_candles == 0
    assert gap.trades_emitted == ()
    assert runtime.state["phase"] == "paused"
    assert runtime.state["error"] == "one_minute_gap"
    assert read_event_log(deployment_dir / "events.jsonl")[-1]["event_type"] == "shadow_paused"

    restarted = ShadowRuntime.open(deployment_dir)
    assert restarted.state == runtime.state
    assert restarted.replay_state.trades == runtime.replay_state.trades


def test_stop_retains_open_lot_and_all_order_capabilities_stay_locked(tmp_path):
    deployment_dir, _, _ = _adopted_dir(tmp_path)
    runtime = ShadowRuntime.open(deployment_dir)
    runtime.start()
    runtime.process_closed_candles(_candles([100, 100]))
    lot_before = deepcopy(runtime.state["open_lots"])

    runtime.stop()
    restarted = ShadowRuntime.open(deployment_dir)

    assert len(lot_before) == 1
    assert restarted.state["phase"] == "stopped"
    assert restarted.state["open_lots"] == lot_before
    assert restarted.replay_state.trades == ()
    assert restarted.state["safety"] == shadow_safety_status()
    assert restarted.deployment["safety"] == shadow_safety_status()


def test_runtime_trade_results_match_shared_fixed_lot_backtest_reducer(tmp_path):
    params = {
        "lookback": 1,
        "threshold_bps": 1,
        "max_hold_minutes": 1,
        "take_profit_bps": 10_000,
        "stop_loss_bps": 10_000,
    }
    deployment_dir, _, deployment = _adopted_dir(
        tmp_path, family="momentum", params=params, budget=500
    )
    candles = _candles([100, 110, 90, 90, 90])
    backtest = simulate_portfolio_strategy(
        candles,
        StrategyCandidate("momentum", dict(deployment["candidate"]["params"])),
        days=1,
        policy=PortfolioPolicy(500),
    )
    runtime = ShadowRuntime.open(deployment_dir)
    runtime.start()

    result = runtime.process_closed_candles(candles)

    assert result.trades_emitted == tuple(backtest.trades)
    assert runtime.replay_state.trades == tuple(backtest.trades)
    assert runtime.state["realized_net_usdc"] == backtest.net_profit_usdc


def test_500_budget_reaches_five_fixed_lots_without_exceeding_capacity(tmp_path):
    deployment_dir, _, _ = _adopted_dir(tmp_path, budget=500)
    runtime = ShadowRuntime.open(deployment_dir)
    runtime.start()

    runtime.process_closed_candles(_candles([100] * 7))

    assert runtime.state["max_open_lots"] == 5
    assert len(runtime.state["open_lots"]) == 5
    assert all(lot["notional_usdc"] == 100.0 for lot in runtime.state["open_lots"])
    assert runtime.replay_state.reserved_notional_usdc == 500.0
    assert runtime.replay_state.engine_state.max_reserved_notional_usdc == 500.0


@dataclass
class _Stop:
    stopped: bool = False

    def is_set(self) -> bool:
        return self.stopped


def test_synchronous_run_poller_uses_public_injection_and_stops_without_liquidation(
    tmp_path,
):
    deployment_dir, _, _ = _adopted_dir(tmp_path)
    runtime = ShadowRuntime.open(deployment_dir)
    stop = _Stop()
    candles = _candles([100, 100])

    def fetcher(**_kwargs):
        return candles

    def sleeper(_seconds):
        stop.stopped = True

    runtime.run_poller(
        stop,
        start_time_ms=candles[0].open_time,
        fetcher=fetcher,
        sleeper=sleeper,
        clock=lambda: candles[-1].open_time + 120_000,
    )

    assert runtime.state["phase"] == "stopped"
    assert len(runtime.state["open_lots"]) == 1
    assert runtime.replay_state.trades == ()
    assert [event["event_type"] for event in read_event_log(deployment_dir / "events.jsonl")] == [
        "deployment_adopted",
        "shadow_started",
        "candle_reduced",
        "candle_reduced",
        "shadow_stopped",
    ]


def test_invalid_initial_poller_cursor_is_rejected_before_runtime_start(tmp_path):
    deployment_dir, _, _ = _adopted_dir(tmp_path)
    runtime = ShadowRuntime.open(deployment_dir)
    event_count = runtime.state["event_count"]

    with pytest.raises(ShadowRuntimeStateError, match="forward-only Shadow cursor"):
        runtime.run_poller(
            _Stop(stopped=True),
            start_time_ms=_candles([100], start_minute=1)[0].open_time,
        )

    assert runtime.state["phase"] == "adopted_stopped"
    assert runtime.state["event_count"] == event_count
    assert [
        event["event_type"]
        for event in read_event_log(deployment_dir / "events.jsonl")
    ] == ["deployment_adopted"]


def _rewrite_valid_hash_chain(path, records):
    previous_hash = GENESIS_HASH
    rewritten = []
    for sequence, original in enumerate(records, start=1):
        without_hash = {
            "schema_version": 1,
            "sequence": sequence,
            "timestamp_utc": original["timestamp_utc"],
            "event_type": original["event_type"],
            "payload": original["payload"],
            "previous_hash": previous_hash,
        }
        record = {
            **without_hash,
            "event_hash": sha256(canonical_json_bytes(without_hash)).hexdigest(),
        }
        rewritten.append(record)
        previous_hash = record["event_hash"]
    path.write_bytes(b"".join(canonical_json_bytes(record) + b"\n" for record in rewritten))
