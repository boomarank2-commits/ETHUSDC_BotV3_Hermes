"""Task-27 tests for real, hash-bound hindsight solver implementations."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.protocol_v3 import boundaries
from ethusdc_bot.protocol_v3 import hindsight_solvers as solver
from ethusdc_bot.protocol_v3.run_identity import build_exchange_info_snapshot

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESS_END = date(2026, 7, 8)
PROCESS_START = PROCESS_END - timedelta(days=365)


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
        repo_root=REPO_ROOT,
    )


@pytest.fixture(scope="module")
def process_candles() -> tuple[Candle, ...]:
    start_ms = int(datetime(2025, 7, 8, tzinfo=UTC).timestamp() * 1000)
    rows = []
    for index in range(365 * 1440):
        minute = index % 1440
        close = 100.0
        if minute in (11, 21):
            close = 104.0 if minute == 11 else 103.0
        rows.append(
            Candle(
                open_time=start_ms + index * 60_000,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1.0,
            )
        )
    return tuple(rows)


def _policies(*, trades: int = 2, hold: int = 1, entry_allowed: bool = True):
    plan = boundaries.build_monthly_process_boundary_plan(PROCESS_END)
    return plan, tuple(
        solver.HindsightOriginPolicy(
            origin_index=origin.origin_index,
            start_inclusive_utc=datetime.combine(
                origin.test_start_inclusive, datetime.min.time(), UTC
            ),
            end_exclusive_utc=datetime.combine(
                origin.test_end_exclusive, datetime.min.time(), UTC
            ),
            valid_from_utc=origin.valid_from,
            origin_selection_sha256=f"{origin.origin_index:064x}",
            candidate_bundle_sha256=f"{origin.origin_index + 20:064x}",
            rotation_state_sha256=f"{origin.origin_index + 40:064x}",
            max_roundtrips_per_utc_day=trades if entry_allowed else 0,
            max_holding_minutes=hold if entry_allowed else 0,
            entry_allowed=entry_allowed,
        )
        for origin in plan.origins
    )


def _rehash(payload: dict) -> None:
    basis = dict(payload)
    basis.pop("evidence_sha256", None)
    payload["evidence_sha256"] = solver._digest(basis)


@pytest.fixture(scope="module")
def all_candle_result(process_candles):
    return solver.solve_all_candle_one_trade_close_hindsight(
        process_candles,
        process_start_inclusive=PROCESS_START,
        process_end_exclusive=PROCESS_END,
        exchange_info_snapshot=_exchange(),
    )


@pytest.fixture(scope="module")
def candidate_result(process_candles):
    plan, policies = _policies(trades=2, hold=1)
    result = solver.solve_candidate_matched_volume_filtered_hindsight(
        process_candles,
        boundary_plan=plan,
        origin_policies=policies,
        exchange_info_snapshot=_exchange(),
    )
    return plan, policies, result


def test_all_candle_solver_is_real_positive_volume_one_trade_per_day(
    all_candle_result,
) -> None:
    payload = all_candle_result.to_dict()
    assert payload["solver"] == solver.ALL_CANDLE_SOLVER
    assert payload["output"]["calendar_days"] == 365
    assert payload["output"]["trade_count"] == 365
    assert all(
        row["trade_count"] == 1 for row in payload["output"]["daily_net_usdc"]
    )
    assert all(
        trade["entry_time_utc"][:10] == trade["exit_time_utc"][:10]
        for trade in payload["output"]["trades"]
    )
    assert payload["lookahead_safe"] is False
    assert payload["diagnostic_only"] is True


def test_candidate_solver_matches_trade_hold_t_plus_24_and_nonoverlap(
    candidate_result,
) -> None:
    plan, _, result = candidate_result
    payload = result.to_dict()
    entries = Counter(
        trade["entry_time_utc"][:10] for trade in payload["output"]["trades"]
    )
    assert entries
    assert max(entries.values()) <= 2
    assert all(
        trade["holding_minutes"] <= 1 for trade in payload["output"]["trades"]
    )
    assert all(
        int(current["entry_index"]) > int(previous["exit_index"])
        for previous, current in zip(
            payload["output"]["trades"], payload["output"]["trades"][1:]
        )
    )
    blocked_first_days = {
        origin.test_start_inclusive.isoformat() for origin in plan.origins
    }
    assert not blocked_first_days.intersection(entries)


def test_missing_duplicate_minute_and_invalid_volume_fail_closed(
    process_candles,
) -> None:
    duplicate = list(process_candles)
    row = duplicate[100]
    duplicate[100] = Candle(
        open_time=duplicate[99].open_time,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=row.volume,
    )
    with pytest.raises(solver.HindsightSolverError, match="missing, duplicate"):
        solver.solve_all_candle_one_trade_close_hindsight(
            duplicate,
            process_start_inclusive=PROCESS_START,
            process_end_exclusive=PROCESS_END,
            exchange_info_snapshot=_exchange(),
        )

    invalid = list(process_candles)
    row = invalid[0]
    invalid[0] = Candle(
        open_time=row.open_time,
        open=row.open,
        high=row.high,
        low=row.low,
        close=row.close,
        volume=-1.0,
    )
    with pytest.raises(solver.HindsightSolverError, match="non-negative"):
        solver.solve_all_candle_one_trade_close_hindsight(
            invalid,
            process_start_inclusive=PROCESS_START,
            process_end_exclusive=PROCESS_END,
            exchange_info_snapshot=_exchange(),
        )


def test_missing_reordered_policy_and_invalid_no_trade_limits_fail_closed(
    process_candles,
) -> None:
    plan, policies = _policies()
    with pytest.raises(solver.HindsightSolverError, match="twelve"):
        solver.solve_candidate_matched_volume_filtered_hindsight(
            process_candles,
            boundary_plan=plan,
            origin_policies=policies[:-1],
            exchange_info_snapshot=_exchange(),
        )
    with pytest.raises(solver.HindsightSolverError, match="NO_TRADE"):
        solver.HindsightOriginPolicy(
            origin_index=1,
            start_inclusive_utc=policies[0].start_inclusive_utc,
            end_exclusive_utc=policies[0].end_exclusive_utc,
            valid_from_utc=policies[0].valid_from_utc,
            origin_selection_sha256="1" * 64,
            candidate_bundle_sha256="2" * 64,
            rotation_state_sha256="3" * 64,
            max_roundtrips_per_utc_day=1,
            max_holding_minutes=1,
            entry_allowed=False,
        )


def test_rehashed_lookahead_feedback_trade_hold_cost_and_hash_tampering_fail_closed(
    candidate_result,
) -> None:
    _, _, result = candidate_result
    payload = result.to_dict()

    lookahead = deepcopy(payload)
    lookahead["lookahead_safe"] = True
    _rehash(lookahead)
    with pytest.raises(solver.HindsightSolverError, match="lookahead"):
        solver.validate_hindsight_solver_evidence(lookahead)

    feedback = deepcopy(payload)
    feedback["selection_feedback_allowed"] = True
    _rehash(feedback)
    with pytest.raises(solver.HindsightSolverError, match="feedback"):
        solver.validate_hindsight_solver_evidence(feedback)

    cost = deepcopy(payload)
    cost["input_identity"]["cost_profile"]["fee_bps_per_side"] = "0"
    _rehash(cost)
    with pytest.raises(solver.HindsightSolverError, match="cost"):
        solver.validate_hindsight_solver_evidence(cost)

    wrong_bundle = deepcopy(payload)
    wrong_bundle["input_identity"]["policy_chain"][0][
        "candidate_bundle_sha256"
    ] = "f" * 64
    wrong_bundle["input_identity"]["policy_chain_sha256"] = solver._digest(
        wrong_bundle["input_identity"]["policy_chain"]
    )
    _rehash(wrong_bundle)
    with pytest.raises(solver.HindsightSolverError, match="bundle"):
        solver.validate_hindsight_solver_evidence(wrong_bundle)

    too_many = deepcopy(payload)
    first = too_many["output"]["trades"][0]
    too_many["output"]["trades"].extend([deepcopy(first), deepcopy(first)])
    too_many["output"]["trade_count"] = len(too_many["output"]["trades"])
    too_many["output"]["solver_output_sha256"] = solver._digest(
        {
            "daily_net_usdc": too_many["output"]["daily_net_usdc"],
            "trades": too_many["output"]["trades"],
        }
    )
    _rehash(too_many)
    with pytest.raises(solver.HindsightSolverError, match="overlap|trade count"):
        solver.validate_hindsight_solver_evidence(too_many)

    too_long = deepcopy(payload)
    too_long["output"]["trades"][0]["holding_minutes"] = 2
    too_long["output"]["solver_output_sha256"] = solver._digest(
        {
            "daily_net_usdc": too_long["output"]["daily_net_usdc"],
            "trades": too_long["output"]["trades"],
        }
    )
    _rehash(too_long)
    with pytest.raises(solver.HindsightSolverError, match="holding"):
        solver.validate_hindsight_solver_evidence(too_long)

    broken_hash = deepcopy(payload)
    broken_hash["output"]["net_usdc"] = "999"
    with pytest.raises(solver.HindsightSolverError):
        solver.validate_hindsight_solver_evidence(broken_hash)
