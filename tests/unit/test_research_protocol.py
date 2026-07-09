"""Tests for the offline research protocol guardrails."""

from ethusdc_bot.backtest.research_protocol import build_research_protocol, validate_research_protocol


def test_research_protocol_forbids_blindtest_selection():
    protocol = build_research_protocol(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123")

    assert protocol["selection_data"] == ["subtrain", "validation"]
    assert protocol["blindtest_usage"] == "final_evaluation_only"
    assert validate_research_protocol(protocol)["valid"] is True


def test_research_protocol_contains_required_reproducibility_fields():
    protocol = build_research_protocol(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", git_commit="abc123")

    for key in [
        "run_id",
        "git_commit",
        "raw_root",
        "data_window",
        "strategy_families",
        "parameter_space",
        "ranking_rules",
        "safety",
    ]:
        assert key in protocol
    assert protocol["safety"]["live"] == "locked"
    assert protocol["safety"]["orders"] == "not_created"
