"""Deterministic controlled search-space generation for offline research loops."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ethusdc_bot.backtest.simulator import StrategyCandidate


@dataclass(frozen=True)
class SearchSpaceState:
    cycle_index: int
    diagnosis: dict[str, Any] = field(default_factory=dict)
    previous_best_validation: float | None = None
    blindtest_metrics: dict[str, Any] | None = None


def generate_search_space(state: SearchSpaceState, *, max_candidates: int = 40) -> list[StrategyCandidate]:
    """Generate a deterministic bounded candidate list from validation diagnosis only."""

    if max_candidates <= 0:
        return []
    problem = str(state.diagnosis.get("problem_assessment") or state.diagnosis.get("dominant_issue") or "baseline")
    pressure = max(0, state.cycle_index)
    if "cost" in problem or "overtrading" in problem:
        pressure += 2
    if "stop_loss" in problem:
        pressure += 1
    if "too_few" in problem:
        pressure = max(0, pressure - 1)
    candidates = _base_candidates(pressure)
    if "too_few" in problem:
        candidates.extend(_opened_candidates(pressure))
    else:
        candidates.extend(_strict_candidates(pressure))
    candidates.extend(_context_candidates(pressure))
    unique: list[StrategyCandidate] = []
    seen: set[tuple[str, tuple[tuple[str, float | int | str], ...]]] = set()
    for candidate in candidates:
        params = {key: value for key, value in candidate.params.items() if "blindtest" not in key and key != "target_usdc_per_day"}
        params.setdefault("symbol", "ETHUSDC")
        signature = (candidate.family, tuple(sorted(params.items())))
        if signature not in seen:
            seen.add(signature)
            unique.append(StrategyCandidate(candidate.family, params))
        if len(unique) >= max_candidates:
            break
    return unique


def next_search_space_state(cycle_summary: dict[str, Any]) -> SearchSpaceState:
    exit_summary = cycle_summary.get("exit_reason_summary", {})
    family = cycle_summary.get("family_aggregate_summary", [])
    best = cycle_summary.get("best_validation_candidate", {})
    if exit_summary.get("stop_loss_share", 0) > 0.45:
        problem = "stop_loss_dominates"
    elif exit_summary.get("time_exit_share", 0) > 0.45:
        problem = "time_exit_dominates"
    elif any(row.get("high_cost_count", 0) for row in family):
        problem = "costs_and_insufficient_edge"
    elif best.get("trade_count", 0) and best.get("trade_count", 0) < 20:
        problem = "too_few_trades"
    else:
        problem = "validation_refinement"
    return SearchSpaceState(
        cycle_index=int(cycle_summary.get("cycle_id", 0)) + 1,
        diagnosis={"problem_assessment": problem},
        previous_best_validation=best.get("net_usdc_per_day"),
    )


def _base_candidates(pressure: int) -> list[StrategyCandidate]:
    return [
        StrategyCandidate("breakout_volatility_filter", {"lookback": 90, "threshold_bps": 12 + pressure * 2, "volatility_lookback": 240, "min_vol_bps": 12 + pressure, "max_vol_bps": 110, "take_profit_bps": 150 + pressure * 10, "stop_loss_bps": 85 + pressure * 2, "trailing_stop_bps": 70, "break_even_after_bps": 65, "max_hold_minutes": 180, "cooldown_minutes": 90 + pressure * 20}),
        StrategyCandidate("breakout_volatility_filter", {"lookback": 180, "threshold_bps": 16 + pressure * 2, "volatility_lookback": 360, "min_vol_bps": 14 + pressure, "max_vol_bps": 95, "take_profit_bps": 190 + pressure * 10, "stop_loss_bps": 95, "trailing_stop_bps": 85, "break_even_after_bps": 80, "max_hold_minutes": 240, "cooldown_minutes": 180 + pressure * 20}),
        StrategyCandidate("cooldown_fee_aware", {"base_family": "breakout", "lookback": 120, "threshold_bps": 18 + pressure * 2, "min_expected_move_bps": 50 + pressure * 8, "take_profit_bps": 180 + pressure * 10, "stop_loss_bps": 95, "trailing_stop_bps": 90, "break_even_after_bps": 75, "max_hold_minutes": 240, "cooldown_minutes": 240 + pressure * 30}),
        StrategyCandidate("cooldown_fee_aware", {"base_family": "momentum", "lookback": 180, "threshold_bps": 45 + pressure * 3, "min_expected_move_bps": 70 + pressure * 8, "take_profit_bps": 220 + pressure * 10, "stop_loss_bps": 110, "trailing_stop_bps": 100, "break_even_after_bps": 95, "max_hold_minutes": 360, "cooldown_minutes": 300 + pressure * 30}),
        StrategyCandidate("momentum_trend_filter", {"lookback": 90, "threshold_bps": 30 + pressure * 3, "trend_lookback": 360, "trend_min_bps": 35 + pressure * 4, "take_profit_bps": 150 + pressure * 10, "stop_loss_bps": 85, "max_hold_minutes": 180, "cooldown_minutes": 120 + pressure * 20}),
        StrategyCandidate("pullback_in_trend", {"lookback": 60, "threshold_bps": 35 + pressure * 2, "trend_lookback": 480, "trend_min_bps": 55 + pressure * 5, "take_profit_bps": 140 + pressure * 10, "stop_loss_bps": 90, "max_hold_minutes": 240, "cooldown_minutes": 180 + pressure * 20}),
        StrategyCandidate("session_filter", {"base_family": "breakout", "lookback": 120, "threshold_bps": 14 + pressure * 2, "session_start_hour": 12, "session_end_hour": 21, "take_profit_bps": 170 + pressure * 10, "stop_loss_bps": 90, "max_hold_minutes": 180, "cooldown_minutes": 150 + pressure * 20}),
    ]


def _strict_candidates(pressure: int) -> list[StrategyCandidate]:
    return [
        StrategyCandidate("cooldown_fee_aware", {"base_family": "breakout", "lookback": 240, "threshold_bps": 25 + pressure * 2, "min_expected_move_bps": 95 + pressure * 10, "take_profit_bps": 260 + pressure * 15, "stop_loss_bps": 120, "trailing_stop_bps": 110, "break_even_after_bps": 100, "max_hold_minutes": 480, "cooldown_minutes": 420 + pressure * 30}),
        StrategyCandidate("breakout_volatility_filter", {"lookback": 240, "threshold_bps": 24 + pressure * 2, "volatility_lookback": 480, "min_vol_bps": 18 + pressure, "max_vol_bps": 80, "take_profit_bps": 240 + pressure * 15, "stop_loss_bps": 115, "trailing_stop_bps": 100, "break_even_after_bps": 95, "max_hold_minutes": 360, "cooldown_minutes": 300 + pressure * 30}),
    ]


def _opened_candidates(pressure: int) -> list[StrategyCandidate]:
    return [
        StrategyCandidate("breakout_volatility_filter", {"lookback": 60, "threshold_bps": max(6, 10 - pressure), "volatility_lookback": 120, "min_vol_bps": 8, "max_vol_bps": 130, "take_profit_bps": 130, "stop_loss_bps": 80, "max_hold_minutes": 150, "cooldown_minutes": 60}),
        StrategyCandidate("session_filter", {"base_family": "momentum", "lookback": 60, "threshold_bps": max(15, 25 - pressure), "session_start_hour": 7, "session_end_hour": 22, "take_profit_bps": 130, "stop_loss_bps": 80, "max_hold_minutes": 150, "cooldown_minutes": 75}),
    ]


def _context_candidates(pressure: int) -> list[StrategyCandidate]:
    return [
        StrategyCandidate("context_filter", {"base_family": "breakout_volatility_filter", "context_symbol": "BTCUSDC", "context_rule": "btc_60m_trend_not_strong_negative", "lookback": 120, "threshold_bps": 16 + pressure * 2, "volatility_lookback": 240, "min_vol_bps": 14, "max_vol_bps": 100, "take_profit_bps": 190, "stop_loss_bps": 95, "max_hold_minutes": 240, "cooldown_minutes": 180}),
        StrategyCandidate("context_filter", {"base_family": "momentum_trend_filter", "context_symbol": "ETHBTC", "context_rule": "ethbtc_relative_strength_non_negative", "lookback": 120, "threshold_bps": 35 + pressure * 2, "trend_lookback": 360, "trend_min_bps": 40, "take_profit_bps": 190, "stop_loss_bps": 100, "max_hold_minutes": 240, "cooldown_minutes": 180}),
    ]
