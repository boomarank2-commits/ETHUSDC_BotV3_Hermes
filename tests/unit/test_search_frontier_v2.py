"""Tests for the deterministic ETHUSDC Search Frontier v2."""

import json

from ethusdc_bot.backtest.search_space import (
    ACTIVE_SEARCH_FAMILIES,
    CONTEXT_CANDIDATES_ENABLED,
    CONTEXT_DISABLED_REASON,
    SEARCH_FRONTIER_VERSION,
    SearchSpaceState,
    canonical_candidate_signature,
    generate_search_space,
    search_frontier_summary,
    select_candidates_for_testing,
)


def test_production_frontier_fills_all_40_generated_slots_deterministically() -> None:
    state = SearchSpaceState(cycle_index=0, diagnosis={})

    first = generate_search_space(state, max_candidates=40)
    second = generate_search_space(state, max_candidates=40)

    assert first == second
    assert len(first) == 40
    assert len({canonical_candidate_signature(candidate) for candidate in first}) == 40
    assert set(candidate.family for candidate in first) == set(ACTIVE_SEARCH_FAMILIES)
    assert all(candidate.params["symbol"] == "ETHUSDC" for candidate in first)


def test_small_frontier_contributes_every_active_family_before_second_round() -> None:
    candidates = generate_search_space(SearchSpaceState(cycle_index=0), max_candidates=6)

    assert [candidate.family for candidate in candidates] == list(ACTIVE_SEARCH_FAMILIES)


def test_tested_frontier_selects_two_variants_from_each_family() -> None:
    generated = generate_search_space(SearchSpaceState(cycle_index=0), max_candidates=40)

    tested = select_candidates_for_testing(generated, limit=12)

    assert len(tested) == 12
    counts = {family: 0 for family in ACTIVE_SEARCH_FAMILIES}
    for candidate in tested:
        counts[candidate.family] += 1
    assert counts == {family: 2 for family in ACTIVE_SEARCH_FAMILIES}


def test_context_candidates_are_excluded_until_real_context_data_is_integrated() -> None:
    candidates = generate_search_space(SearchSpaceState(cycle_index=3), max_candidates=40)
    payload = json.dumps(
        [{"family": candidate.family, "params": candidate.params} for candidate in candidates],
        sort_keys=True,
    )

    assert CONTEXT_CANDIDATES_ENABLED is False
    assert CONTEXT_DISABLED_REASON == "context_research_must_be_explicitly_enabled"
    assert all(candidate.family != "context_filter" for candidate in candidates)
    assert "BTCUSDC" not in payload
    assert "ETHBTC" not in payload


def test_frontier_metadata_is_explicit_and_uses_no_holdout_or_target() -> None:
    state = SearchSpaceState(
        cycle_index=2,
        diagnosis={"problem_assessment": "costs_and_insufficient_edge"},
    )
    candidates = generate_search_space(state, max_candidates=40)

    summary = search_frontier_summary(candidates, state, requested_cap=40)

    assert summary["generator_version"] == SEARCH_FRONTIER_VERSION
    assert summary["requested_cap"] == 40
    assert summary["generated_count"] == 40
    assert summary["active_families"] == list(ACTIVE_SEARCH_FAMILIES)
    assert sum(summary["family_counts"].values()) == 40
    assert all(count >= 6 for count in summary["family_counts"].values())
    assert summary["context_candidates_enabled"] is False
    assert summary["context_disabled_reason"] == CONTEXT_DISABLED_REASON
    assert summary["uses_audit_or_holdout"] is False
    assert summary["target_used_as_parameter"] is False


def test_diagnosis_adjustment_is_bounded_and_directionally_consistent() -> None:
    baseline = generate_search_space(SearchSpaceState(cycle_index=0), max_candidates=40)
    cost_aware = generate_search_space(
        SearchSpaceState(
            cycle_index=20,
            diagnosis={"problem_assessment": "costs_and_overtrading"},
        ),
        max_candidates=40,
    )
    opened = generate_search_space(
        SearchSpaceState(
            cycle_index=1,
            diagnosis={"problem_assessment": "too_few_trades"},
        ),
        max_candidates=40,
    )

    baseline_expected = max(
        float(candidate.params.get("min_expected_move_bps", 0) or 0)
        for candidate in baseline
    )
    cost_expected = max(
        float(candidate.params.get("min_expected_move_bps", 0) or 0)
        for candidate in cost_aware
    )
    baseline_cooldown = max(
        int(candidate.params.get("cooldown_minutes", 0) or 0)
        for candidate in baseline
    )
    cost_cooldown = max(
        int(candidate.params.get("cooldown_minutes", 0) or 0)
        for candidate in cost_aware
    )
    assert cost_expected > baseline_expected
    assert cost_cooldown > baseline_cooldown

    baseline_min_threshold = min(
        float(candidate.params.get("threshold_bps", 0) or 0)
        for candidate in baseline
    )
    opened_min_threshold = min(
        float(candidate.params.get("threshold_bps", 0) or 0)
        for candidate in opened
    )
    assert opened_min_threshold <= baseline_min_threshold


def test_frontier_contains_no_audit_blindtest_or_target_parameters() -> None:
    candidates = generate_search_space(
        SearchSpaceState(cycle_index=5, diagnosis={"problem_assessment": "validation_refinement"}),
        max_candidates=40,
    )
    payload = json.dumps([candidate.params for candidate in candidates], sort_keys=True).lower()

    assert "audit" not in payload
    assert "blindtest" not in payload
    assert "target_usdc_per_day" not in payload
