"""Tests for deterministic research search-space generation."""

import json

from ethusdc_bot.backtest.search_space import SearchSpaceState, generate_search_space


def test_search_space_generates_deterministic_controlled_candidates():
    state = SearchSpaceState(cycle_index=1, diagnosis={"problem_assessment": "costs_and_insufficient_edge"})

    first = generate_search_space(state, max_candidates=40)
    second = generate_search_space(state, max_candidates=40)

    assert first == second
    assert 6 <= len(first) <= 40
    assert {candidate.family for candidate in first} >= {
        "breakout_volatility_filter",
        "cooldown_fee_aware",
        "momentum_trend_filter",
        "pullback_in_trend",
        "session_filter",
    }


def test_search_space_uses_no_blindtest_metrics_or_target_parameter():
    state = SearchSpaceState(
        cycle_index=2,
        diagnosis={"problem_assessment": "costs_and_insufficient_edge"},
        blindtest_metrics={"net_usdc_per_day": 9999.0},
    )

    candidates = generate_search_space(state, max_candidates=40)
    payload = json.dumps([candidate.params for candidate in candidates], sort_keys=True).lower()

    assert "blindtest" not in payload
    assert "target_usdc_per_day" not in payload
    assert "+3" not in payload
    assert all(candidate.params.get("symbol", "ETHUSDC") == "ETHUSDC" for candidate in candidates)


def test_search_space_cost_diagnosis_tightens_expected_move_and_cooldown():
    baseline = generate_search_space(SearchSpaceState(cycle_index=0, diagnosis={}), max_candidates=40)
    cost_aware = generate_search_space(
        SearchSpaceState(cycle_index=1, diagnosis={"problem_assessment": "costs_and_insufficient_edge"}),
        max_candidates=40,
    )

    assert max(float(c.params.get("min_expected_move_bps", 0) or 0) for c in cost_aware) >= max(
        float(c.params.get("min_expected_move_bps", 0) or 0) for c in baseline
    )
    assert max(int(c.params.get("cooldown_minutes", 0) or 0) for c in cost_aware) >= max(
        int(c.params.get("cooldown_minutes", 0) or 0) for c in baseline
    )
