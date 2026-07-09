"""Tests for multi-cycle offline research loop runner."""

import json

from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.research_loop_runner import LoopConfig, run_research_loop
from ethusdc_bot.backtest.simulator import StrategyCandidate


def _cycle(candidate_id: str, validation: float, blindtest: float = -1.0, safety=None):
    return {
        "cycle_id": 1,
        "generated_candidates": 2,
        "tested_candidates": 2,
        "selected_candidate": {"candidate_id": candidate_id, "family": "breakout_volatility_filter", "params": {}},
        "best_training_candidate": {"candidate_id": candidate_id},
        "best_validation_candidate": {"candidate_id": candidate_id, "net_usdc_per_day": validation},
        "best_validation_metrics": BacktestMetrics(validation, validation, 10, 0.5, 1, 1.2, validation / 10, 1, 1, 1, 1),
        "blindtest_audit": {"net_usdc_per_day": blindtest, "repeated_blindtest_audit": True},
        "candidate_leaderboard_summary": [],
        "family_aggregate_summary": [],
        "exit_reason_summary": {},
        "wfv_summary": {},
        "next_search_space_adjustment": "continue",
        "safety": safety or {"live": "locked", "paper": "locked", "testtrade": "locked", "orders": "not_created", "binance_trading_api": "not_used", "api_keys": "not_used"},
    }


def test_research_loop_runner_executes_multiple_cycles(tmp_path):
    calls = []

    def cycle_runner(cycle_index, state):
        calls.append(cycle_index)
        return _cycle(f"candidate_{cycle_index}", validation=-1.0 + cycle_index * 0.1)

    result = run_research_loop(
        LoopConfig(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", reports_root=tmp_path, max_cycles=3, max_candidates_per_cycle=4, min_cycles=3),
        cycle_runner=cycle_runner,
    )

    assert calls == [1, 2, 3]
    assert result.cycles_executed == 3
    assert result.stop_reason == "max_cycles_reached"
    assert result.report_paths.json_path.exists()


def test_research_loop_stops_at_target_reached_after_min_cycles(tmp_path):
    def cycle_runner(cycle_index, state):
        return _cycle(f"candidate_{cycle_index}", validation=3.5 if cycle_index == 3 else 1.0, blindtest=3.2 if cycle_index == 3 else -1)

    result = run_research_loop(
        LoopConfig(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", reports_root=tmp_path, max_cycles=8, max_candidates_per_cycle=4, min_cycles=3),
        cycle_runner=cycle_runner,
    )

    assert result.cycles_executed == 3
    assert result.stop_reason == "target_reached_clean_validation_candidate"
    assert result.target_reached is True


def test_research_loop_stops_on_stagnation_after_three_non_improving_cycles(tmp_path):
    values = {1: 1.0, 2: 0.9, 3: 0.8, 4: 0.7}

    def cycle_runner(cycle_index, state):
        return _cycle(f"candidate_{cycle_index}", validation=values[cycle_index])

    result = run_research_loop(
        LoopConfig(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", reports_root=tmp_path, max_cycles=8, max_candidates_per_cycle=4, min_cycles=3, stagnation_cycles=3),
        cycle_runner=cycle_runner,
    )

    assert result.cycles_executed == 4
    assert result.stop_reason == "validation_stagnation_3_cycles"


def test_loop_report_contains_cycles_stop_reason_target_and_safety_locks(tmp_path):
    result = run_research_loop(
        LoopConfig(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", reports_root=tmp_path, max_cycles=3, max_candidates_per_cycle=4, min_cycles=3),
        cycle_runner=lambda cycle_index, state: _cycle(f"candidate_{cycle_index}", validation=-0.1),
    )

    data = json.loads(result.report_paths.json_path.read_text(encoding="utf-8"))

    assert len(data["cycles"]) == 3
    assert data["stop_reason"]
    assert data["target_reached"] is False
    assert data["safety"]["live"] == "locked"
    assert data["safety"]["paper"] == "locked"
    assert data["safety"]["testtrade"] == "locked"
    assert data["safety"]["orders"] == "not_created"
    assert data["safety"]["binance_trading_api"] == "not_used"
    assert data["safety"]["api_keys"] == "not_used"
    assert "Live/Paper/Testtrade locked" in result.report_paths.txt_path.read_text(encoding="utf-8")


def test_loop_stops_on_safety_violation(tmp_path):
    unsafe = {"live": "unlocked", "paper": "locked", "testtrade": "locked", "orders": "not_created", "binance_trading_api": "not_used", "api_keys": "not_used"}

    result = run_research_loop(
        LoopConfig(raw_root="C:/TradingBot/data/ETHUSDC_BotV3_Hermes", reports_root=tmp_path, max_cycles=8, max_candidates_per_cycle=4, min_cycles=3),
        cycle_runner=lambda cycle_index, state: _cycle(f"candidate_{cycle_index}", validation=-0.1, safety=unsafe),
    )

    assert result.stop_reason == "safety_violation"
    assert result.cycles_executed == 1


def test_context_symbols_cannot_trigger_trades():
    candidate = StrategyCandidate("context_filter", {"context_symbol": "BTCUSDC", "symbol": "ETHUSDC"})

    assert candidate.params["context_symbol"] == "BTCUSDC"
    assert candidate.params["symbol"] == "ETHUSDC"
