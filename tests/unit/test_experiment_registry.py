"""Tests for durable research experiment registry."""

from ethusdc_bot.backtest.experiment_registry import record_experiment


def _experiment(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "timestamp": "2026-07-09T00:00:00Z",
        "git_commit": "abc123",
        "data_window": {"data_start": "2024-01-01", "data_end": "2024-01-02"},
        "training_window": {},
        "validation_window": {},
        "blindtest_window": {},
        "strategy_families": ["momentum_trend_filter"],
        "parameter_counts": {"total_candidates": 1},
        "selected_candidate": {"family": "momentum_trend_filter", "params": {}},
        "why_selected": "best validation rank",
        "training_metrics": {"net_usdc_per_day": 1.0},
        "validation_metrics": {"net_usdc_per_day": 1.0},
        "blindtest_metrics": {"net_usdc_per_day": 0.0},
        "target_reached": False,
        "target_usdc_per_day": 3.0,
        "safety": {"live": "locked", "paper": "locked", "testtrade": "locked", "orders": "not_created"},
        "report_links": {},
        "candidate_leaderboard": [
            {
                "candidate_id": "momentum_trend_filter_001",
                "family": "momentum_trend_filter",
                "rank_position": 1,
                "validation_metrics": {"net_usdc_per_day": 1.0},
                "weaknesses": [],
            }
        ],
        "candidate_diagnosis": {"best_validation_family": "momentum_trend_filter", "ranking_uses_blindtest": False},
    }


def test_experiment_registry_writes_index_jsonl(tmp_path):
    paths = record_experiment(_experiment("research_test_001"), tmp_path)

    assert paths.json_path.exists()
    assert paths.txt_path.exists()
    assert paths.index_path.exists()
    assert "research_test_001" in paths.index_path.read_text(encoding="utf-8")


def test_experiment_registry_does_not_overwrite_old_runs(tmp_path):
    record_experiment(_experiment("research_test_001"), tmp_path)
    paths = record_experiment(_experiment("research_test_001"), tmp_path)

    assert paths.json_path.stem != "research_test_001"
    assert len(list(tmp_path.glob("research_test_001*.json"))) == 2
