"""Tests for deterministic research search-space generation."""

from dataclasses import fields
import json

from ethusdc_bot.backtest.search_space import (
    SearchSpaceState,
    canonical_candidate_signature,
    generate_search_space,
    next_search_space_state,
    select_candidates_for_testing,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate


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


def test_search_space_state_has_no_audit_or_blindtest_metrics():
    assert "blindtest_metrics" not in {item.name for item in fields(SearchSpaceState)}


def test_search_space_uses_no_audit_metrics_or_target_parameter():
    state = SearchSpaceState(
        cycle_index=2,
        diagnosis={"problem_assessment": "costs_and_insufficient_edge"},
    )

    candidates = generate_search_space(state, max_candidates=40)
    payload = json.dumps([candidate.params for candidate in candidates], sort_keys=True).lower()

    assert "blindtest" not in payload
    assert "target_usdc_per_day" not in payload
    assert "+3" not in payload
    assert all(candidate.params.get("symbol", "ETHUSDC") == "ETHUSDC" for candidate in candidates)


def test_canonical_candidate_signature_is_order_independent_and_normalizes_symbol():
    first = StrategyCandidate("breakout", {"threshold_bps": 20, "lookback": 90})
    second = StrategyCandidate("breakout", {"symbol": "ETHUSDC", "lookback": 90, "threshold_bps": 20})
    different = StrategyCandidate("breakout", {"symbol": "ETHUSDC", "lookback": 120, "threshold_bps": 20})

    assert canonical_candidate_signature(first) == canonical_candidate_signature(second)
    assert canonical_candidate_signature(first) != canonical_candidate_signature(different)
    assert len({canonical_candidate_signature(first), canonical_candidate_signature(second)}) == 1


def test_candidate_selection_returns_all_candidates_in_original_order_within_limit():
    candidates = [
        StrategyCandidate("family_a", {"variant": 1}),
        StrategyCandidate("family_a", {"variant": 2}),
        StrategyCandidate("family_b", {"variant": 1}),
    ]

    assert select_candidates_for_testing(candidates, limit=3) == candidates
    assert select_candidates_for_testing(candidates, limit=10) == candidates


def test_candidate_selection_uses_deterministic_family_round_robin_when_bounded():
    candidates = [
        StrategyCandidate("family_a", {"variant": 1}),
        StrategyCandidate("family_a", {"variant": 2}),
        StrategyCandidate("family_a", {"variant": 3}),
        StrategyCandidate("family_b", {"variant": 1}),
        StrategyCandidate("family_b", {"variant": 2}),
        StrategyCandidate("family_c", {"variant": 1}),
    ]

    selected = select_candidates_for_testing(candidates, limit=5)

    assert [(candidate.family, candidate.params["variant"]) for candidate in selected] == [
        ("family_a", 1),
        ("family_b", 1),
        ("family_c", 1),
        ("family_a", 2),
        ("family_b", 2),
    ]
    assert select_candidates_for_testing(candidates, limit=5) == selected


def test_candidate_selection_rotates_family_and_profile_offsets_when_requested():
    candidates = [
        StrategyCandidate(family, {"variant": variant})
        for family in ("family_a", "family_b", "family_c")
        for variant in (1, 2, 3)
    ]

    selected = select_candidates_for_testing(candidates, limit=5, round_offset=1)

    assert [(candidate.family, candidate.params["variant"]) for candidate in selected] == [
        ("family_b", 2),
        ("family_c", 2),
        ("family_a", 2),
        ("family_b", 3),
        ("family_c", 3),
    ]
    assert select_candidates_for_testing(candidates, limit=5, round_offset=1) == selected
    assert selected != select_candidates_for_testing(candidates, limit=5, round_offset=0)


def test_candidate_selection_with_non_positive_limit_is_empty():
    candidates = [StrategyCandidate("family_a", {"variant": 1})]

    assert select_candidates_for_testing(candidates, limit=0) == []
    assert select_candidates_for_testing(candidates, limit=-1) == []


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


def test_next_search_state_prioritizes_selected_wfv_activity_shortfall_over_cost_pressure():
    cycle = {
        "cycle_id": 6,
        "exit_reason_summary": {"stop_loss_share": 0.4, "time_exit_share": 0.1},
        "family_aggregate_summary": [{"family": "breakout_volatility_filter", "high_cost_count": 1}],
        "best_validation_candidate": {"trade_count": 21, "net_usdc_per_day": -0.02},
        "wfv_summary": {
            "aggregate_metrics": {"trade_count": 27},
            "selection_evidence": {"temporal": {"max_no_trade_gap_days": 136}},
        },
    }

    state = next_search_space_state(cycle)

    assert state.cycle_index == 7
    assert state.diagnosis["problem_assessment"] == "too_few_trades"


def test_too_few_trade_diagnosis_opens_existing_profiles_instead_of_adding_pressure():
    baseline = generate_search_space(SearchSpaceState(cycle_index=0), max_candidates=40)
    opened = generate_search_space(
        SearchSpaceState(cycle_index=7, diagnosis={"problem_assessment": "too_few_trades"}),
        max_candidates=40,
    )

    baseline_threshold = min(float(candidate.params.get("threshold_bps", 0) or 0) for candidate in baseline)
    opened_threshold = min(float(candidate.params.get("threshold_bps", 0) or 0) for candidate in opened)
    baseline_cooldown = min(int(candidate.params.get("cooldown_minutes", 0) or 0) for candidate in baseline)
    opened_cooldown = min(int(candidate.params.get("cooldown_minutes", 0) or 0) for candidate in opened)

    assert opened_threshold < baseline_threshold
    assert opened_cooldown <= baseline_cooldown
