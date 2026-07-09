"""Tests for reproducible offline research runner."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
import zipfile

from ethusdc_bot.backtest.research_runner import generate_research_candidates, rank_candidates, run_research
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
