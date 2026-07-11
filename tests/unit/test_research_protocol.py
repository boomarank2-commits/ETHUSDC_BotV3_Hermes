"""Tests for the offline research protocol guardrails."""

from copy import deepcopy

import pytest

from ethusdc_bot.backtest.research_protocol import (
    CANDIDATE_STAGE_BUDGETS,
    CONSUMED_AUDIT_WINDOWS,
    DYNAMIC_WINDOW_POLICY,
    SELECTION_DATA,
    build_research_protocol,
    safety_status,
    validate_research_protocol,
)


def test_canonical_ledger_budgets_and_window_policy_are_runtime_immutable():
    with pytest.raises(TypeError):
        CONSUMED_AUDIT_WINDOWS[0]["start"] = "2099-01-01"  # type: ignore[index]
    with pytest.raises(TypeError):
        CANDIDATE_STAGE_BUDGETS["tested_candidates"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        DYNAMIC_WINDOW_POLICY["training_days"] = 1  # type: ignore[index]


def test_research_protocol_v2_forbids_consumed_audit_evaluation_and_selection():
    protocol = build_research_protocol(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123")

    assert protocol["schema_version"] == 2
    assert protocol["selection_data"] == ["subtrain", "validation", "walk_forward"]
    assert protocol["consumed_audit_policy"]["consumed"] is True
    assert protocol["consumed_audit_policy"]["evaluate_during_research"] is False
    assert protocol["consumed_audit_policy"]["use_for_selection"] is False
    assert protocol["consumed_audit_policy"]["use_for_ranking"] is False
    assert protocol["consumed_audit_policy"]["windows"] == [
        {
            "start": "2025-07-08",
            "end": "2026-07-07",
            "reason": "repeatedly viewed during pre-Protocol-v2 research",
        }
    ]
    assert validate_research_protocol(protocol)["valid"] is True


def test_research_protocol_contains_required_reproducibility_fields():
    protocol = build_research_protocol(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123")

    for key in [
        "run_id",
        "git_commit",
        "raw_root",
        "data_window",
        "dynamic_window_policy",
        "candidate_stage_budgets",
        "consumed_audit_policy",
        "strategy_families",
        "parameter_space",
        "ranking_rules",
        "required_report_paths",
        "safety",
    ]:
        assert key in protocol
    assert protocol["safety"]["live"] == "locked"
    assert protocol["safety"]["orders"] == "not_created"


def test_research_protocol_has_bounded_candidate_stages_and_dynamic_utc_windows():
    protocol = build_research_protocol(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123")

    expected_budgets = {
        "generated_candidates": 40,
        "tested_candidates": 12,
        "walk_forward_candidates": 3,
        "finalists": 2,
    }
    assert dict(CANDIDATE_STAGE_BUDGETS) == expected_budgets
    assert protocol["candidate_stage_budgets"] == expected_budgets
    assert protocol["dynamic_window_policy"] == {
        "timezone": "UTC",
        "end_anchor": "latest_complete_utc_day",
        "training_days": 730,
        "holdout_days": 365,
        "minimum_complete_days": 1095,
        "rolling_origin_when_extra_history": True,
        "fixed_calendar_years": False,
    }


def test_research_protocol_requires_the_exact_canonical_selection_sources():
    baseline = build_research_protocol(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123")

    assert baseline["selection_data"] == list(SELECTION_DATA)
    invalid_selection_sources = [
        ["subtrain", "validation"],
        ["subtrain", "walk_forward", "validation"],
        ["subtrain", "validation", "walk_forward", "historical_rolling_origin"],
        ["subtrain", "validation", "walk_forward", "holdout"],
        tuple(SELECTION_DATA),
    ]

    for selection_data in invalid_selection_sources:
        protocol = deepcopy(baseline)
        protocol["selection_data"] = selection_data
        result = validate_research_protocol(protocol)
        assert result["valid"] is False
        assert any("selection_data must be exactly" in error for error in result["errors"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ranking_rules", ["holdout_rank"]),
        ("required_report_paths", []),
        ("strategy_families", ["context_filter"]),
        ("parameter_space", []),
    ],
)
def test_research_protocol_rejects_mutated_reproducibility_contract(field, value):
    protocol = build_research_protocol(
        raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123"
    )
    protocol[field] = value

    assert validate_research_protocol(protocol)["valid"] is False


def test_research_protocol_rejects_invalid_candidate_stage_caps():
    baseline = build_research_protocol(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123")
    invalid_budgets = [
        {"generated_candidates": 0, "tested_candidates": 0, "walk_forward_candidates": 0, "finalists": 0},
        {"generated_candidates": 10, "tested_candidates": 11, "walk_forward_candidates": 4, "finalists": 1},
        {"generated_candidates": 10, "tested_candidates": 8, "walk_forward_candidates": 9, "finalists": 1},
        {"generated_candidates": 10, "tested_candidates": 8, "walk_forward_candidates": 4, "finalists": 5},
        {"generated_candidates": 41, "tested_candidates": 12, "walk_forward_candidates": 3, "finalists": 2},
        {"generated_candidates": True, "tested_candidates": 1, "walk_forward_candidates": 1, "finalists": 1},
    ]

    for budgets in invalid_budgets:
        protocol = deepcopy(baseline)
        protocol["candidate_stage_budgets"] = budgets
        result = validate_research_protocol(protocol)
        assert result["valid"] is False
        assert any("candidate_stage_budgets" in error for error in result["errors"])

    explicitly_empty = build_research_protocol(
        raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes",
        git_commit="abc123",
        candidate_stage_budgets={},
    )
    assert validate_research_protocol(explicitly_empty)["valid"] is False


def test_research_protocol_rejects_audit_policy_relaxation():
    baseline = build_research_protocol(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123")

    for key in ["evaluate_during_research", "use_for_selection", "use_for_ranking"]:
        protocol = deepcopy(baseline)
        protocol["consumed_audit_policy"][key] = True
        result = validate_research_protocol(protocol)
        assert result["valid"] is False
        assert any("consumed audit" in error for error in result["errors"])

    removed_ledger = deepcopy(baseline)
    removed_ledger["consumed_audit_policy"]["windows"] = []
    assert validate_research_protocol(removed_ledger)["valid"] is False

    optimization_allowed = deepcopy(baseline)
    optimization_allowed["consumed_audit_policy"]["allowed_uses"].append("optimization")
    assert validate_research_protocol(optimization_allowed)["valid"] is False


def test_research_protocol_rejects_dynamic_window_or_safety_relaxation():
    baseline = build_research_protocol(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123")

    bad_window = deepcopy(baseline)
    bad_window["dynamic_window_policy"]["end_anchor"] = "fixed_2026"
    assert validate_research_protocol(bad_window)["valid"] is False

    for key, expected in safety_status().items():
        protocol = deepcopy(baseline)
        protocol["safety"][key] = not expected if isinstance(expected, bool) else "unsafe"
        result = validate_research_protocol(protocol)
        assert result["valid"] is False
        assert any(key in error for error in result["errors"])
