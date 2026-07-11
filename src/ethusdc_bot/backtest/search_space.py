"""Deterministic controlled search-space generation for offline research loops."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Final

from ethusdc_bot.backtest.simulator import StrategyCandidate


SEARCH_FRONTIER_VERSION: Final = "ethusdc_frontier_v2"
ACTIVE_SEARCH_FAMILIES: Final = (
    "breakout_volatility_filter",
    "cooldown_fee_aware",
    "momentum_trend_filter",
    "pullback_in_trend",
    "mean_reversion_regime_filter",
    "session_filter",
)
CONTEXT_CANDIDATES_ENABLED: Final = False
CONTEXT_DISABLED_REASON: Final = "real_context_market_data_not_integrated"
_MAX_DIAGNOSIS_PRESSURE: Final = 6
_PROFILE_COUNT: Final = 7


@dataclass(frozen=True)
class SearchSpaceState:
    cycle_index: int
    diagnosis: dict[str, Any] = field(default_factory=dict)
    previous_best_validation: float | None = None


CandidateSignature = tuple[str, tuple[tuple[str, float | int | str], ...]]


def canonical_candidate_signature(candidate: StrategyCandidate) -> CandidateSignature:
    """Return a stable, hashable identity for a candidate.

    ETHUSDC is the only tradable symbol, so an omitted symbol and an explicit
    ``symbol=ETHUSDC`` represent the same candidate.
    """

    params = dict(candidate.params)
    params.setdefault("symbol", "ETHUSDC")
    return candidate.family, tuple(sorted(params.items()))


def select_candidates_for_testing(
    candidates: list[StrategyCandidate], limit: int
) -> list[StrategyCandidate]:
    """Select a deterministic family-balanced testing frontier.

    A candidate list that already fits the budget is returned unchanged. When
    it exceeds the budget, families retain first-seen order and contribute one
    candidate per round until the limit is reached.
    """

    if limit <= 0:
        return []
    if len(candidates) <= limit:
        return list(candidates)

    family_order: list[str] = []
    candidates_by_family: dict[str, list[StrategyCandidate]] = {}
    for candidate in candidates:
        if candidate.family not in candidates_by_family:
            family_order.append(candidate.family)
            candidates_by_family[candidate.family] = []
        candidates_by_family[candidate.family].append(candidate)

    selected: list[StrategyCandidate] = []
    family_offsets = {family: 0 for family in family_order}
    while len(selected) < limit:
        added_in_round = False
        for family in family_order:
            offset = family_offsets[family]
            family_candidates = candidates_by_family[family]
            if offset >= len(family_candidates):
                continue
            selected.append(family_candidates[offset])
            family_offsets[family] = offset + 1
            added_in_round = True
            if len(selected) >= limit:
                break
        if not added_in_round:
            break
    return selected


def generate_search_space(
    state: SearchSpaceState, *, max_candidates: int = 40
) -> list[StrategyCandidate]:
    """Generate a bounded, deterministic ETHUSDC candidate frontier.

    The frontier is fixed ex ante. Validation diagnosis may only apply the
    existing pressure/opening adjustment; no audit, holdout or target result is
    accepted as input. Context-labelled candidates remain disabled until real
    aligned context-market data is part of the simulation contract.
    """

    if max_candidates <= 0:
        return []
    problem = _problem_assessment(state)
    pressure, opening_bias = _diagnosis_adjustments(state, problem)
    candidates = _frontier_candidates(pressure, opening_bias)

    unique: list[StrategyCandidate] = []
    seen: set[CandidateSignature] = set()
    for candidate in candidates:
        params = {
            key: value
            for key, value in candidate.params.items()
            if "blindtest" not in key and key != "target_usdc_per_day"
        }
        params.setdefault("symbol", "ETHUSDC")
        normalized_candidate = StrategyCandidate(candidate.family, params)
        signature = canonical_candidate_signature(normalized_candidate)
        if signature not in seen:
            seen.add(signature)
            unique.append(normalized_candidate)
        if len(unique) >= max_candidates:
            break
    return unique


def search_frontier_summary(
    candidates: list[StrategyCandidate],
    state: SearchSpaceState,
    *,
    requested_cap: int,
) -> dict[str, Any]:
    """Return transparent metadata for one generated frontier."""

    problem = _problem_assessment(state)
    pressure, opening_bias = _diagnosis_adjustments(state, problem)
    counts = Counter(candidate.family for candidate in candidates)
    return {
        "generator_version": SEARCH_FRONTIER_VERSION,
        "requested_cap": max(0, int(requested_cap)),
        "generated_count": len(candidates),
        "active_families": list(ACTIVE_SEARCH_FAMILIES),
        "family_counts": {
            family: counts.get(family, 0) for family in ACTIVE_SEARCH_FAMILIES
        },
        "problem_assessment": problem,
        "diagnosis_pressure": pressure,
        "opening_bias": opening_bias,
        "context_candidates_enabled": CONTEXT_CANDIDATES_ENABLED,
        "context_disabled_reason": CONTEXT_DISABLED_REASON,
        "uses_audit_or_holdout": False,
        "target_used_as_parameter": False,
    }


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


def _problem_assessment(state: SearchSpaceState) -> str:
    return str(
        state.diagnosis.get("problem_assessment")
        or state.diagnosis.get("dominant_issue")
        or "baseline"
    )


def _diagnosis_adjustments(
    state: SearchSpaceState, problem: str
) -> tuple[int, int]:
    pressure = max(0, int(state.cycle_index))
    if "cost" in problem or "overtrading" in problem:
        pressure += 2
    if "stop_loss" in problem:
        pressure += 1
    opening_bias = 0
    if "too_few" in problem:
        pressure = max(0, pressure - 1)
        opening_bias = 2
    return min(_MAX_DIAGNOSIS_PRESSURE, pressure), opening_bias


def _frontier_candidates(
    pressure: int, opening_bias: int
) -> list[StrategyCandidate]:
    candidates: list[StrategyCandidate] = []
    for profile in range(_PROFILE_COUNT):
        candidates.extend(
            (
                _breakout_candidate(profile, pressure, opening_bias),
                _cooldown_candidate(profile, pressure, opening_bias),
                _momentum_candidate(profile, pressure, opening_bias),
                _pullback_candidate(profile, pressure, opening_bias),
                _mean_reversion_candidate(profile, pressure, opening_bias),
                _session_candidate(profile, pressure, opening_bias),
            )
        )
    return candidates


def _opened(value: float | int, opening_bias: int, step: float | int) -> float | int:
    adjusted = value - opening_bias * step
    if isinstance(value, int) and isinstance(step, int):
        return max(1, int(adjusted))
    return max(0.0, float(adjusted))


def _cooldown(value: int, pressure: int, opening_bias: int) -> int:
    return max(30, value + pressure * 20 - opening_bias * 30)


def _breakout_candidate(
    profile: int, pressure: int, opening_bias: int
) -> StrategyCandidate:
    lookback = (60, 90, 120, 180, 240, 360, 480)[profile]
    threshold = (10, 12, 14, 16, 18, 22, 26)[profile] + pressure * 2
    return StrategyCandidate(
        "breakout_volatility_filter",
        {
            "lookback": lookback,
            "threshold_bps": _opened(threshold, opening_bias, 2),
            "volatility_lookback": (120, 180, 240, 360, 480, 720, 960)[profile],
            "min_vol_bps": _opened(
                (8, 10, 12, 14, 16, 18, 20)[profile] + pressure,
                opening_bias,
                1,
            ),
            "max_vol_bps": (140, 125, 115, 105, 95, 85, 75)[profile],
            "take_profit_bps": (130, 150, 170, 190, 220, 250, 290)[profile]
            + pressure * 10,
            "stop_loss_bps": (80, 85, 90, 95, 105, 115, 125)[profile],
            "trailing_stop_bps": (60, 70, 75, 85, 95, 105, 120)[profile],
            "break_even_after_bps": (55, 65, 70, 80, 90, 105, 120)[profile],
            "max_hold_minutes": (120, 150, 180, 240, 300, 360, 480)[profile],
            "cooldown_minutes": _cooldown(
                (60, 90, 120, 180, 240, 300, 420)[profile],
                pressure,
                opening_bias,
            ),
        },
    )


def _cooldown_candidate(
    profile: int, pressure: int, opening_bias: int
) -> StrategyCandidate:
    base_family = "breakout" if profile % 2 == 0 else "momentum"
    threshold = (12, 18, 24, 32, 42, 55, 70)[profile] + pressure * 3
    expected = (35, 45, 55, 70, 85, 105, 130)[profile] + pressure * 8
    return StrategyCandidate(
        "cooldown_fee_aware",
        {
            "base_family": base_family,
            "lookback": (60, 90, 120, 180, 240, 360, 480)[profile],
            "threshold_bps": _opened(threshold, opening_bias, 3),
            "min_expected_move_bps": _opened(expected, opening_bias, 5),
            "take_profit_bps": (130, 150, 180, 210, 240, 280, 330)[profile]
            + pressure * 10,
            "stop_loss_bps": (80, 85, 90, 100, 110, 120, 135)[profile],
            "trailing_stop_bps": (60, 70, 80, 90, 100, 115, 130)[profile],
            "break_even_after_bps": (55, 65, 75, 85, 100, 115, 135)[profile],
            "max_hold_minutes": (120, 180, 240, 300, 360, 480, 600)[profile],
            "cooldown_minutes": _cooldown(
                (90, 150, 210, 270, 330, 420, 540)[profile],
                pressure,
                opening_bias,
            ),
        },
    )


def _momentum_candidate(
    profile: int, pressure: int, opening_bias: int
) -> StrategyCandidate:
    threshold = (18, 24, 30, 36, 45, 55, 70)[profile] + pressure * 3
    trend_min = (15, 25, 35, 45, 60, 75, 95)[profile] + pressure * 4
    return StrategyCandidate(
        "momentum_trend_filter",
        {
            "lookback": (45, 60, 90, 120, 180, 240, 360)[profile],
            "threshold_bps": _opened(threshold, opening_bias, 3),
            "trend_lookback": (180, 240, 360, 480, 720, 960, 1440)[profile],
            "trend_min_bps": _opened(trend_min, opening_bias, 4),
            "take_profit_bps": (120, 140, 160, 185, 215, 250, 300)[profile]
            + pressure * 10,
            "stop_loss_bps": (75, 80, 85, 95, 105, 115, 130)[profile],
            "max_hold_minutes": (120, 150, 180, 240, 300, 360, 480)[profile],
            "cooldown_minutes": _cooldown(
                (60, 90, 120, 180, 240, 300, 420)[profile],
                pressure,
                opening_bias,
            ),
        },
    )


def _pullback_candidate(
    profile: int, pressure: int, opening_bias: int
) -> StrategyCandidate:
    threshold = (18, 22, 28, 34, 42, 52, 65)[profile] + pressure * 2
    trend_min = (25, 35, 45, 55, 70, 90, 115)[profile] + pressure * 5
    return StrategyCandidate(
        "pullback_in_trend",
        {
            "lookback": (30, 45, 60, 90, 120, 180, 240)[profile],
            "threshold_bps": _opened(threshold, opening_bias, 2),
            "trend_lookback": (180, 240, 360, 480, 720, 960, 1440)[profile],
            "trend_min_bps": _opened(trend_min, opening_bias, 4),
            "take_profit_bps": (110, 125, 140, 160, 190, 225, 270)[profile]
            + pressure * 10,
            "stop_loss_bps": (70, 75, 80, 90, 100, 110, 125)[profile],
            "max_hold_minutes": (120, 150, 180, 240, 300, 360, 480)[profile],
            "cooldown_minutes": _cooldown(
                (60, 90, 120, 180, 240, 300, 420)[profile],
                pressure,
                opening_bias,
            ),
        },
    )


def _mean_reversion_candidate(
    profile: int, pressure: int, opening_bias: int
) -> StrategyCandidate:
    threshold = (12, 15, 18, 22, 28, 35, 45)[profile] + pressure * 2
    return StrategyCandidate(
        "mean_reversion_regime_filter",
        {
            "lookback": (20, 30, 45, 60, 90, 120, 180)[profile],
            "threshold_bps": _opened(threshold, opening_bias, 2),
            "trend_lookback": (120, 180, 240, 360, 480, 720, 960)[profile],
            "max_abs_trend_bps": (160, 140, 120, 100, 85, 70, 55)[profile]
            + pressure * 3,
            "take_profit_bps": (80, 90, 100, 115, 130, 150, 180)[profile]
            + pressure * 8,
            "stop_loss_bps": (65, 70, 75, 80, 90, 100, 115)[profile],
            "max_hold_minutes": (60, 90, 120, 150, 180, 240, 300)[profile],
            "cooldown_minutes": _cooldown(
                (30, 45, 60, 90, 120, 180, 240)[profile],
                pressure,
                opening_bias,
            ),
        },
    )


def _session_candidate(
    profile: int, pressure: int, opening_bias: int
) -> StrategyCandidate:
    sessions = ((0, 24), (7, 16), (12, 21), (13, 22), (6, 14), (15, 23), (21, 6))
    start_hour, end_hour = sessions[profile]
    threshold = (12, 16, 20, 25, 32, 40, 50)[profile] + pressure * 2
    return StrategyCandidate(
        "session_filter",
        {
            "base_family": "breakout" if profile % 2 == 0 else "momentum",
            "lookback": (45, 60, 90, 120, 180, 240, 360)[profile],
            "threshold_bps": _opened(threshold, opening_bias, 2),
            "session_start_hour": start_hour,
            "session_end_hour": end_hour,
            "take_profit_bps": (110, 130, 150, 175, 205, 240, 285)[profile]
            + pressure * 10,
            "stop_loss_bps": (70, 75, 80, 90, 100, 110, 125)[profile],
            "max_hold_minutes": (90, 120, 150, 180, 240, 300, 420)[profile],
            "cooldown_minutes": _cooldown(
                (45, 60, 90, 120, 180, 240, 360)[profile],
                pressure,
                opening_bias,
            ),
        },
    )


__all__ = [
    "ACTIVE_SEARCH_FAMILIES",
    "CONTEXT_CANDIDATES_ENABLED",
    "CONTEXT_DISABLED_REASON",
    "SEARCH_FRONTIER_VERSION",
    "SearchSpaceState",
    "canonical_candidate_signature",
    "generate_search_space",
    "next_search_space_state",
    "search_frontier_summary",
    "select_candidates_for_testing",
]
