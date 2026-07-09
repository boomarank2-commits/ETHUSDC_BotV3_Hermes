"""Tests for reproducible offline research runner."""

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import zipfile

from ethusdc_bot.backtest.research_runner import (
    build_candidate_diagnosis,
    build_candidate_leaderboard,
    build_family_aggregates,
    build_family_diagnosis,
    generate_research_candidates,
    rank_candidates,
    run_research,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.backtest.metrics import BacktestMetrics


def _write_day(root: Path, day: datetime, start_price: float) -> None:
    folder = root / "raw" / "binance" / "spot" / "ETHUSDC" / "klines" / "1m"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"ETHUSDC-1m-{day.date().isoformat()}.zip"
    rows = []
    price = start_price
    for minute in range(1440):
        open_time = int((day + timedelta(minutes=minute)).timestamp() * 1000)
        price += 0.01
        rows.append([open_time, f"{price:.4f}", f"{price + 0.1:.4f}", f"{price - 0.1:.4f}", f"{price:.4f}", "1.0"])
    csv_text = "\n".join(",".join(str(value) for value in row) for row in rows) + "\n"
    with zipfile.ZipFile(folder / name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name.replace(".zip", ".csv"), csv_text)
    (folder / f"{name}.CHECKSUM").write_text("fixture checksum\n", encoding="utf-8")


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "raw_root"
    for day in range(6):
        _write_day(root, datetime(2024, 1, 1 + day, tzinfo=UTC), 100 + day)
    return root


def test_research_runner_uses_training_validation_for_selection(tmp_path):
    result = run_research(raw_root=_fixture_root(tmp_path), reports_root=tmp_path / "research", required_days=None)

    assert result.selection_source == "subtrain_validation_only"
    assert result.event_log.index("candidate_selected") < result.event_log.index("blindtest_evaluated")
    assert result.experiment_paths.json_path.exists()


def test_ranking_uses_not_blindtest_metrics():
    weak_blind = {
        "candidate": StrategyCandidate("momentum_trend_filter", {"lookback": 5}),
        "training_metrics": BacktestMetrics(1, 1, 10, 0.5, 1, 1.2, 0.1, 1, 1, 1, 1),
        "validation_metrics": BacktestMetrics(1, 1, 10, 0.5, 1, 1.2, 0.1, 1, 1, 1, 1),
        "blindtest_metrics": BacktestMetrics(-100, -100, 1, 0, 100, 0, -100, 0, 0, 1, 1),
    }
    strong_blind_bad_validation = {
        "candidate": StrategyCandidate("breakout_volatility_filter", {"lookback": 5}),
        "training_metrics": BacktestMetrics(-1, -1, 10, 0.5, 1, 0.8, -0.1, 1, 1, 1, 1),
        "validation_metrics": BacktestMetrics(-1, -1, 10, 0.5, 1, 0.8, -0.1, 1, 1, 1, 1),
        "blindtest_metrics": BacktestMetrics(100, 100, 1, 1, 0, 9, 100, 0, 0, 1, 1),
    }

    ranked = rank_candidates([strong_blind_bad_validation, weak_blind])

    assert ranked[0]["candidate"].family == "momentum_trend_filter"


def test_research_report_contains_parameters_and_selection_reason(tmp_path):
    result = run_research(raw_root=_fixture_root(tmp_path), reports_root=tmp_path / "research", required_days=None)
    data = result.experiment_paths.json_path.read_text(encoding="utf-8")

    assert "parameter_space" in data
    assert "why_selected" in data
    assert "target_usdc_per_day" in data
    assert "api_keys" in data
    assert "not_used" in data


def test_research_report_contains_complete_candidate_leaderboard(tmp_path):
    result = run_research(raw_root=_fixture_root(tmp_path), reports_root=tmp_path / "research", required_days=None)
    data = json.loads(result.experiment_paths.json_path.read_text(encoding="utf-8"))

    leaderboard = data["candidate_leaderboard"]
    assert len(leaderboard) == data["parameter_counts"]["total_candidates"]
    assert [row["rank_position"] for row in leaderboard] == list(range(1, len(leaderboard) + 1))
    assert all("candidate_id" in row for row in leaderboard)
    assert all("training_metrics" in row and "validation_metrics" in row for row in leaderboard)


def test_leaderboard_ranking_uses_no_blindtest_metrics_except_selected(tmp_path):
    result = run_research(raw_root=_fixture_root(tmp_path), reports_root=tmp_path / "research", required_days=None)
    data = json.loads(result.experiment_paths.json_path.read_text(encoding="utf-8"))

    selected_ids = [row["candidate_id"] for row in data["candidate_leaderboard"] if "blindtest_metrics" in row]
    assert selected_ids == [data["selected_candidate"]["candidate_id"]]
    assert data["candidate_diagnosis"]["ranking_uses_blindtest"] is False


def test_research_report_contains_family_aggregates_for_all_families(tmp_path):
    result = run_research(raw_root=_fixture_root(tmp_path), reports_root=tmp_path / "research", required_days=None)
    data = json.loads(result.experiment_paths.json_path.read_text(encoding="utf-8"))

    aggregates = data["family_aggregates"]
    assert {row["family"] for row in aggregates} == set(data["strategy_families"])
    for row in aggregates:
        for key in [
            "candidate_count",
            "best_validation_candidate_id",
            "best_validation_net_usdc_per_day",
            "average_validation_net_usdc_per_day",
            "best_training_net_usdc_per_day",
            "average_training_net_usdc_per_day",
            "average_trade_count",
            "min_trade_count",
            "max_trade_count",
            "average_fees_usdc",
            "average_slippage_usdc",
            "average_cost_load",
            "best_profit_factor",
            "average_profit_factor",
            "best_drawdown",
            "worst_drawdown",
            "overtrading_count",
            "too_few_trades_count",
            "negative_validation_count",
            "high_cost_count",
        ]:
            assert key in row
        assert "blindtest" not in json.dumps(row).lower()


def test_family_diagnosis_uses_validation_and_costs_without_blindtest():
    leaderboard = [
        {
            "candidate_id": "alpha_001",
            "family": "alpha",
            "training_metrics": {"net_usdc_per_day": 1, "trade_count": 10, "fees_usdc": 1, "slippage_usdc": 1, "profit_factor": 1.2, "max_drawdown_usdc": 5},
            "validation_metrics": {"net_usdc_per_day": 0.1, "trade_count": 10, "fees_usdc": 1, "slippage_usdc": 1, "profit_factor": 0.95, "max_drawdown_usdc": 5},
            "weaknesses": [],
        },
        {
            "candidate_id": "beta_001",
            "family": "beta",
            "training_metrics": {"net_usdc_per_day": -1, "trade_count": 2000, "fees_usdc": 20, "slippage_usdc": 20, "profit_factor": 0.5, "max_drawdown_usdc": 50},
            "validation_metrics": {"net_usdc_per_day": -1, "trade_count": 2000, "fees_usdc": 20, "slippage_usdc": 20, "profit_factor": 0.5, "max_drawdown_usdc": 50},
            "weaknesses": ["overtrading", "cost_load_high", "validation_negative"],
            "blindtest_metrics": {"net_usdc_per_day": 999},
        },
    ]

    aggregates = build_family_aggregates(leaderboard)
    diagnosis = build_family_diagnosis(aggregates)

    assert diagnosis["best_validation_family"] == "alpha"
    assert diagnosis["lowest_cost_family"] == "alpha"
    assert diagnosis["overtrading_families"] == ["beta"]
    assert diagnosis["profit_factor_nearest_one_family"] == "alpha"
    assert diagnosis["ranking_uses_blindtest"] is False


def test_candidate_diagnosis_detects_validation_cost_trade_and_overtrading_weaknesses():
    records = [
        {
            "candidate": StrategyCandidate("diagnostic", {}),
            "candidate_id": "diagnostic_001",
            "training_metrics": BacktestMetrics(-1, -1, 2, 0, 1, 0.5, -0.5, 10, 10, 1, 1),
            "validation_metrics": BacktestMetrics(-1, -1, 2, 0, 1, 0.5, -0.5, 10, 10, 1, 1),
        },
        {
            "candidate": StrategyCandidate("overtrade", {}),
            "candidate_id": "overtrade_001",
            "training_metrics": BacktestMetrics(1, 1, 10, 1, 1, 1.2, 0.1, 1, 1, 1, 1),
            "validation_metrics": BacktestMetrics(1, 1, 2000, 1, 1, 1.2, 0.1, 1, 1, 1, 1),
        },
    ]

    leaderboard = build_candidate_leaderboard(
        records,
        selected_candidate_id="diagnostic_001",
        blindtest_metrics=BacktestMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1),
    )
    diagnosis = build_candidate_diagnosis(leaderboard)

    assert "validation_negative" in leaderboard[0]["weaknesses"]
    assert "cost_load_high" in leaderboard[0]["weaknesses"]
    assert "too_few_trades" in leaderboard[0]["weaknesses"]
    assert "overtrading" in leaderboard[1]["weaknesses"]
    assert diagnosis["negative_validation_candidate_count"] >= 1
    assert diagnosis["overtrading_candidate_count"] >= 1


def test_generate_research_candidates_is_controlled_not_wild_bruteforce():
    candidates = generate_research_candidates()

    assert 5 <= len(candidates) <= 30
    assert {candidate.family for candidate in candidates} >= {
        "momentum_trend_filter",
        "breakout_volatility_filter",
        "mean_reversion_regime_filter",
        "pullback_in_trend",
        "session_filter",
    }
    assert all(candidate.params.get("symbol", "ETHUSDC") == "ETHUSDC" for candidate in candidates)


def test_controlled_exit_improvement_is_deterministic_and_not_target_hardcoded():
    first = generate_research_candidates()
    second = generate_research_candidates()

    assert first == second
    assert any("trailing_stop_bps" in candidate.params or "break_even_after_bps" in candidate.params for candidate in first)
    assert all("target_usdc_per_day" not in candidate.params for candidate in first)


def test_controlled_cost_filter_improvement_is_deterministic_and_not_target_hardcoded():
    candidates = generate_research_candidates()
    strict_cost_filters = [
        candidate for candidate in candidates if float(candidate.params.get("min_expected_move_bps", 0) or 0) >= 70
    ]

    assert strict_cost_filters
    assert len(candidates) <= 30
    assert all("target_usdc_per_day" not in candidate.params for candidate in strict_cost_filters)
