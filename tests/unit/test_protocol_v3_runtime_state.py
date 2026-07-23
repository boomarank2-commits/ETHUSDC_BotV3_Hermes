"""Protocol v3 task-9 tests for warmup, purge, folds, and outer state."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.protocol_v3.boundaries import build_monthly_process_boundary_plan
from ethusdc_bot.protocol_v3.execution_parity import (
    build_market_execution_rules,
)
from ethusdc_bot.protocol_v3.intrabar_execution import BASELINE_COST_PROFILE
from ethusdc_bot.protocol_v3.run_identity import build_exchange_info_snapshot
from ethusdc_bot.protocol_v3.runtime_state import (
    FoldRuntimeState,
    HorizonPolicy,
    OpenPositionState,
    PendingEntryState,
    RuntimeCarryState,
    RuntimeStateError,
    WarmupWindow,
    assert_inner_fold_starts_flat,
    begin_inner_fold,
    build_information_interval,
    build_outer_rotation_state,
    carry_state_for_next_origin,
    close_retiring_position,
    finalize_inner_fold,
    finalize_outer_process,
    load_runtime_state_contract,
    purge_training_events,
    validate_outer_rotation_state,
    validate_runtime_state_contract,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OLD_BUNDLE = "a" * 64
NEW_BUNDLE = "b" * 64
OTHER_BUNDLE = "c" * 64
SCALER = "d" * 64
MODEL = "e" * 64


def _snapshot():
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
                        {
                            "filterType": "PRICE_FILTER",
                            "minPrice": "0.01",
                            "maxPrice": "1000000",
                            "tickSize": "0.01",
                        },
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.0001",
                            "maxQty": "9000",
                            "stepSize": "0.0001",
                        },
                        {
                            "filterType": "MARKET_LOT_SIZE",
                            "minQty": "0.0001",
                            "maxQty": "1200",
                            "stepSize": "0.0001",
                        },
                        {
                            "filterType": "MIN_NOTIONAL",
                            "minNotional": "5",
                            "applyToMarket": True,
                            "avgPriceMins": 5,
                        },
                    ],
                }
            ]
        },
        snapshot_as_of_utc="2026-07-07T23:59:59Z",
    )


def _rules():
    return build_market_execution_rules(_snapshot())


def _position(*, bundle: str = OLD_BUNDLE, rules_sha: str | None = None):
    rules_sha = rules_sha or _rules().rules_sha256
    return OpenPositionState(
        candidate_bundle_sha256=bundle,
        quantity="0.0499",
        entry_price="100.06",
        accrued_entry_fees="0.004992994",
        stop_price="95.05",
        target_price="110.07",
        trailing_state="active",
        trailing_stop_price="99.5",
        break_even_active=True,
        high_watermark="102",
        time_stop_deadline_ms=1_800_000,
        execution_rules_sha256=rules_sha,
        cost_profile="baseline",
    )


def _bar(open_time: int, *, close: float = 101.0, volume: float = 10.0):
    return Candle(open_time, 100.8, 101.2, 100.5, close, volume)


def test_runtime_contract_is_exact_and_safety_cannot_be_relaxed() -> None:
    contract = load_runtime_state_contract(REPO_ROOT)
    assert contract["purge_policy"]["execution_bar_minutes"] == 1
    assert contract["outer_rotation_policy"]["carry_open_position_only"] is True
    assert contract["outer_rotation_policy"]["carry_pending_entry"] is False
    changed = json.loads(json.dumps(contract))
    changed["outer_rotation_policy"]["carry_pending_entry"] = True
    with pytest.raises(RuntimeStateError, match="not canonical"):
        validate_runtime_state_contract(changed)


def test_purge_formula_and_boundary_touch_are_fail_closed() -> None:
    policy = HorizonPolicy(
        max_label_horizon_minutes=120,
        max_holding_period_minutes=180,
        pending_entry_latency_minutes=2,
    )
    assert policy.purge_duration_minutes == 183
    assert len(policy.policy_sha256) == 64
    assert policy.policy_sha256 == HorizonPolicy(120, 180, 2).policy_sha256
    assert policy.policy_sha256 != HorizonPolicy(120, 180, 3).policy_sha256

    kept = build_information_interval(
        "kept",
        signal_time_ms=0,
        label_horizon_minutes=9,
        holding_period_minutes=5,
        pending_entry_latency_minutes=0,
        policy=policy,
    )
    touching = build_information_interval(
        "touching",
        signal_time_ms=0,
        label_horizon_minutes=10,
        holding_period_minutes=5,
        pending_entry_latency_minutes=0,
        policy=policy,
    )
    result = purge_training_events(
        [touching, kept],
        boundary_start_ms=11 * 60_000,
    )
    assert [event.event_id for event in result.kept] == ["kept"]
    assert [event.event_id for event in result.purged] == ["touching"]

    with pytest.raises(RuntimeStateError, match="holding period exceeds"):
        build_information_interval(
            "too-long",
            signal_time_ms=0,
            label_horizon_minutes=10,
            holding_period_minutes=181,
            pending_entry_latency_minutes=0,
            policy=policy,
        )


def test_training_event_at_or_after_boundary_is_not_silently_accepted() -> None:
    event = build_information_interval(
        "not-training",
        signal_time_ms=60_000,
        label_horizon_minutes=1,
        holding_period_minutes=1,
        pending_entry_latency_minutes=0,
        policy=HorizonPolicy(10, 10, 1),
    )
    with pytest.raises(RuntimeStateError, match="strictly before"):
        purge_training_events([event], boundary_start_ms=60_000)


def test_warmup_allows_only_feature_reads_before_evaluation() -> None:
    window = WarmupWindow(0, 60_000, 180_000)
    window.assert_use(0, "feature_read")
    for purpose in (
        "signal",
        "label",
        "pnl",
        "scaler_fit",
        "quantile_fit",
        "regime_fit",
    ):
        with pytest.raises(RuntimeStateError, match="feature_read only"):
            window.assert_use(0, purpose)
    window.assert_use(60_000, "signal")


def test_inner_fold_starts_completely_flat() -> None:
    clean = begin_inner_fold("origin-01-fold-01")
    assert clean.open_position is None
    assert clean.pending_entry is None
    assert clean.cooldown_until_ms is None

    contaminated = FoldRuntimeState(
        fold_id="origin-01-fold-01",
        pending_entry=PendingEntryState(OLD_BUNDLE, 0),
    )
    with pytest.raises(RuntimeStateError, match="must start flat"):
        assert_inner_fold_starts_flat(contaminated)


def test_fold_end_cancels_pending_and_liquidates_exact_quantity() -> None:
    rules = _rules()
    state = FoldRuntimeState(
        fold_id="origin-01-fold-01",
        open_position=_position(rules_sha=rules.rules_sha256),
        pending_entry=PendingEntryState(OLD_BUNDLE, 60_000),
        cooldown_until_ms=120_000,
        scaler_state_sha256=SCALER,
        runtime_model_state_sha256=MODEL,
    )
    final = finalize_inner_fold(
        state,
        terminal_bar=_bar(120_000, close=101.0),
        rules=rules,
        cost_profile=BASELINE_COST_PROFILE,
    )
    assert final.pending_entry_cancelled is True
    assert final.liquidation is not None
    assert final.liquidation.reason == "fold_end"
    assert final.liquidation.reference_price == "101"
    assert final.liquidation.fill_price == "100.94"
    assert final.liquidation.quantity == "0.0499"
    assert final.liquidation.terminal_liquidation is True
    assert final.final_state == FoldRuntimeState(fold_id=state.fold_id)


def test_fold_end_without_tradable_terminal_bar_blocks() -> None:
    rules = _rules()
    state = FoldRuntimeState(
        fold_id="fold",
        open_position=_position(rules_sha=rules.rules_sha256),
    )
    with pytest.raises(RuntimeStateError, match="positive volume"):
        finalize_inner_fold(
            state,
            terminal_bar=_bar(0, volume=0),
            rules=rules,
            cost_profile=BASELINE_COST_PROFILE,
        )


def test_first_outer_origin_starts_flat_and_waits_exactly_until_valid_from() -> None:
    origin = build_monthly_process_boundary_plan("2026-07-08").origins[0]
    state = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
    )
    assert state.open_position is None
    assert state.flat_time_utc == state.anchor_utc
    assert state.entry_enabled_at_utc == origin.valid_from
    assert state.entry_allowed_at(origin.valid_from - timedelta(microseconds=1)) is False
    assert state.entry_allowed_at(origin.valid_from) is True
    assert state.monthly_boundary_liquidation is False

    with pytest.raises(RuntimeStateError, match="first outer origin"):
        build_outer_rotation_state(
            origin,
            new_candidate_bundle_sha256=NEW_BUNDLE,
            previous_runtime=RuntimeCarryState(
                pending_entry=PendingEntryState(OLD_BUNDLE, 0)
            ),
        )


def test_outer_boundary_carries_only_one_open_position_and_discards_runtime_state() -> None:
    origin = build_monthly_process_boundary_plan("2026-07-08").origins[1]
    position = _position()
    previous = RuntimeCarryState(
        candidate_bundle_sha256=OLD_BUNDLE,
        open_position=position,
        pending_entry=PendingEntryState(OLD_BUNDLE, 0),
        cooldown_until_ms=60_000,
        scaler_state_sha256=SCALER,
        runtime_model_state_sha256=MODEL,
    )
    state = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
        previous_runtime=previous,
    )
    assert state.open_position == position
    assert state.retiring_candidate_bundle_sha256 == OLD_BUNDLE
    assert state.retiring_configuration_mode == "exit_only"
    assert state.new_configuration_mode == "waiting_for_flat_and_valid_from"
    assert state.entry_enabled_at_utc is None
    assert state.entry_allowed_at(origin.valid_from + timedelta(days=1)) is False
    assert state.discarded_pending_entry is True
    assert state.discarded_cooldown is True
    assert state.discarded_scaler_state is True
    assert state.discarded_runtime_model_state is True
    assert state.monthly_boundary_liquidation is False

    carried = carry_state_for_next_origin(state)
    assert carried.open_position == position
    assert carried.pending_entry is None
    assert carried.cooldown_until_ms is None
    assert carried.scaler_state_sha256 is None
    assert carried.runtime_model_state_sha256 is None


def test_new_configuration_waits_for_max_of_valid_from_and_flat_time() -> None:
    origin = build_monthly_process_boundary_plan("2026-07-08").origins[1]
    state = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
        previous_runtime=RuntimeCarryState(
            candidate_bundle_sha256=OLD_BUNDLE,
            open_position=_position(),
        ),
    )

    before_valid = close_retiring_position(
        state,
        exit_time_utc=state.anchor_utc + timedelta(hours=12),
    )
    assert before_valid.entry_enabled_at_utc == state.valid_from_utc
    assert before_valid.new_configuration_mode == "waiting_for_valid_from"
    assert before_valid.entry_allowed_at(state.valid_from_utc) is True

    state = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
        previous_runtime=RuntimeCarryState(
            candidate_bundle_sha256=OLD_BUNDLE,
            open_position=_position(),
        ),
    )
    after_valid_time = state.valid_from_utc + timedelta(hours=6)
    after_valid = close_retiring_position(state, exit_time_utc=after_valid_time)
    assert after_valid.entry_enabled_at_utc == after_valid_time
    assert after_valid.new_configuration_mode == "entry_enabled"
    assert after_valid.entry_allowed_at(after_valid_time) is True


def test_configuration_expiring_before_flat_becomes_no_trade() -> None:
    origin = build_monthly_process_boundary_plan("2026-07-08").origins[1]
    state = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
        previous_runtime=RuntimeCarryState(
            candidate_bundle_sha256=OLD_BUNDLE,
            open_position=_position(),
        ),
    )
    expired = close_retiring_position(
        state,
        exit_time_utc=state.valid_until_utc,
    )
    assert expired.entry_enabled_at_utc is None
    assert expired.new_configuration_mode == "NO_TRADE_EXPIRED"
    assert expired.mode_at(state.valid_until_utc) == "NO_TRADE_EXPIRED"


def test_rotation_state_identity_is_deterministic_and_semantically_validated() -> None:
    origin = build_monthly_process_boundary_plan("2026-07-08").origins[1]
    first = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
        previous_runtime=RuntimeCarryState(
            candidate_bundle_sha256=OLD_BUNDLE,
            open_position=_position(),
        ),
    )
    second = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
        previous_runtime=RuntimeCarryState(
            candidate_bundle_sha256=OLD_BUNDLE,
            open_position=_position(),
        ),
    )
    changed = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=OTHER_BUNDLE,
        previous_runtime=RuntimeCarryState(
            candidate_bundle_sha256=OLD_BUNDLE,
            open_position=_position(),
        ),
    )
    assert first.state_sha256 == second.state_sha256
    assert first.state_sha256 != changed.state_sha256
    assert len(first.state_sha256) == 64
    validate_outer_rotation_state(first, origin=origin)

    with pytest.raises(RuntimeStateError, match="monthly boundaries"):
        replace(first, monthly_boundary_liquidation=True)


def test_only_process_end_liquidates_a_remaining_outer_position() -> None:
    rules = _rules()
    origin = build_monthly_process_boundary_plan("2026-07-08").origins[-1]
    state = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
        previous_runtime=RuntimeCarryState(
            candidate_bundle_sha256=OLD_BUNDLE,
            open_position=_position(rules_sha=rules.rules_sha256)
        ),
    )
    end_ms = int(state.valid_until_utc.timestamp() * 1000)
    terminal = _bar(end_ms - 60_000, close=101.0)
    liquidation = finalize_outer_process(
        state,
        terminal_bar=terminal,
        rules=rules,
        cost_profile=BASELINE_COST_PROFILE,
    )
    assert liquidation is not None
    assert liquidation.reason == "process_end"
    assert liquidation.quantity == "0.0499"
    assert liquidation.execution_time_ms == end_ms - 1

    with pytest.raises(RuntimeStateError, match="exactly at valid_until"):
        finalize_outer_process(
            state,
            terminal_bar=_bar(end_ms - 120_000),
            rules=rules,
            cost_profile=BASELINE_COST_PROFILE,
        )


def test_process_end_finalization_is_forbidden_before_origin_twelve() -> None:
    origin = build_monthly_process_boundary_plan("2026-07-08").origins[1]
    state = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
        previous_runtime=RuntimeCarryState(
            candidate_bundle_sha256=OLD_BUNDLE,
            open_position=_position(),
        ),
    )
    with pytest.raises(RuntimeStateError, match="requires origin 12"):
        finalize_outer_process(
            state,
            terminal_bar=None,
            rules=_rules(),
            cost_profile=BASELINE_COST_PROFILE,
        )

    flat_state = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
    )
    with pytest.raises(RuntimeStateError, match="requires origin 12"):
        finalize_outer_process(
            flat_state,
            terminal_bar=None,
            rules=_rules(),
            cost_profile=BASELINE_COST_PROFILE,
        )

    final_flat_state = build_outer_rotation_state(
        build_monthly_process_boundary_plan("2026-07-08").origins[-1],
        new_candidate_bundle_sha256=NEW_BUNDLE,
    )
    assert (
        finalize_outer_process(
            final_flat_state,
            terminal_bar=None,
            rules=_rules(),
            cost_profile=BASELINE_COST_PROFILE,
        )
        is None
    )


def test_carry_and_rotation_modes_fail_closed_on_contradictory_identity_or_time() -> None:
    with pytest.raises(RuntimeStateError, match="requires its candidate bundle"):
        RuntimeCarryState(open_position=_position())
    with pytest.raises(RuntimeStateError, match="does not match"):
        RuntimeCarryState(
            candidate_bundle_sha256=OTHER_BUNDLE,
            open_position=_position(),
        )

    origin = build_monthly_process_boundary_plan("2026-07-08").origins[1]
    waiting = build_outer_rotation_state(
        origin,
        new_candidate_bundle_sha256=NEW_BUNDLE,
        previous_runtime=RuntimeCarryState(
            candidate_bundle_sha256=OLD_BUNDLE,
            open_position=_position(),
        ),
    )
    with pytest.raises(RuntimeStateError, match="requires waiting_for_flat"):
        replace(waiting, new_configuration_mode="entry_enabled")

    flat = close_retiring_position(
        waiting,
        exit_time_utc=waiting.anchor_utc + timedelta(hours=12),
    )
    with pytest.raises(RuntimeStateError, match="contradicts"):
        replace(flat, new_configuration_mode="entry_enabled")
    with pytest.raises(RuntimeStateError, match="must equal max"):
        replace(
            flat,
            entry_enabled_at_utc=flat.valid_from_utc + timedelta(minutes=1),
        )

    expired = close_retiring_position(
        waiting,
        exit_time_utc=waiting.valid_until_utc,
    )
    assert expired.entry_allowed_at(expired.valid_until_utc) is False
    with pytest.raises(RuntimeStateError, match="expired flat rotation"):
        replace(expired, new_configuration_mode="waiting_for_valid_from")


def test_terminal_liquidation_revalidates_execution_identity() -> None:
    rules = _rules()
    state = FoldRuntimeState(
        fold_id="fold",
        open_position=_position(rules_sha="f" * 64),
    )
    with pytest.raises(RuntimeStateError, match="execution rules"):
        finalize_inner_fold(
            state,
            terminal_bar=_bar(0),
            rules=rules,
            cost_profile=BASELINE_COST_PROFILE,
        )
