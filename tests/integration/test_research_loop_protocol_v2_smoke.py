"""End-to-end fixture smoke for the real Protocol-v2 research loop path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import zipfile

import ethusdc_bot.backtest.research_loop_runner as loop_module
import ethusdc_bot.backtest.selection_evidence as selection_evidence_module
import ethusdc_bot.backtest.walk_forward as walk_forward_module
from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.research_loop_runner import LoopConfig, run_research_loop
from ethusdc_bot.backtest.research_protocol import CONSUMED_AUDIT_WINDOWS
from ethusdc_bot.backtest.split import ResearchWindowPlan, SplitResult


def _write_day(root: Path, day: datetime) -> None:
    folder = root / "raw" / "binance" / "spot" / "ETHUSDC" / "klines" / "1m"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"ETHUSDC-1m-{day.date().isoformat()}.zip"
    rows = []
    for minute in range(1440):
        open_time = int((day + timedelta(minutes=minute)).timestamp() * 1000)
        price = 100 + minute / 100_000
        rows.append(f"{open_time},{price},{price + 0.1},{price - 0.1},{price},1.0")
    with zipfile.ZipFile(folder / name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name.replace(".zip", ".csv"), "\n".join(rows) + "\n")
    (folder / f"{name}.CHECKSUM").write_text("fixture checksum\n", encoding="utf-8")


def _minute_candles(start: datetime, days: int) -> list[Candle]:
    return [
        Candle(
            open_time=int((start + timedelta(days=day, minutes=minute)).timestamp() * 1000),
            open=100.0,
            high=100.1,
            low=99.9,
            close=100.0 + minute / 100_000,
            volume=1.0,
        )
        for day in range(days)
        for minute in range(1440)
    ]


def test_real_protocol_v2_loop_reports_stages_without_evaluating_holdout(tmp_path, monkeypatch):
    raw_root = tmp_path / "raw_root"
    start = datetime(2024, 1, 1, tzinfo=UTC)
    for offset in range(6):
        _write_day(raw_root, start + timedelta(days=offset))

    evaluated_open_times: list[int] = []
    original_simulate = loop_module.simulate_strategy

    def simulate_spy(candles, *args, **kwargs):
        evaluated_open_times.extend(candle.open_time for candle in candles)
        return original_simulate(candles, *args, **kwargs)

    monkeypatch.setattr(loop_module, "simulate_strategy", simulate_spy)
    monkeypatch.setattr(walk_forward_module, "simulate_strategy", simulate_spy)
    monkeypatch.setattr(selection_evidence_module, "simulate_strategy", simulate_spy)

    result = run_research_loop(
        LoopConfig(
            raw_root=raw_root,
            reports_root=tmp_path / "reports",
            max_cycles=1,
            min_cycles=1,
            max_candidates_per_cycle=6,
            tested_candidates_per_cycle=4,
            walk_forward_candidates_per_cycle=2,
            finalists_per_cycle=1,
            walk_forward_fold_count=2,
            rolling_origin_limit=0,
            required_days=None,
        )
    )

    report = json.loads(result.report_paths.json_path.read_text(encoding="utf-8"))
    cycle = report["cycles"][0]
    assert report["schema_version"] == 2
    assert report["execution_profile"] == "fixture_smoke_non_production"
    assert report["fixture_data_only"] is True
    assert report["audit_policy"]["evaluated_in_research_loop"] is False
    assert report["target_reached"] is False
    assert cycle["generated_candidates"] == len(cycle["candidate_stage_ids"]["generated"])
    assert cycle["tested_candidates"] == len(cycle["candidate_stage_ids"]["tested"])
    assert cycle["walk_forward_candidates"] == 2
    assert cycle["finalists"] == 1
    assert len(cycle["walk_forward_summaries"]) == cycle["walk_forward_candidates"]
    assert len(cycle["finalist_summaries"]) == cycle["finalists"]
    assert all(item["summary"]["fold_count"] == 2 for item in cycle["walk_forward_summaries"])
    finalist = cycle["finalist_summaries"][0]
    evidence = finalist["quality_gate_evidence"]
    gate = finalist["quality_gate"]
    assert evidence["validation"]["drawdown_method"] == "mark_to_market"
    assert evidence["wfv"]["aggregate"]["drawdown_method"] == "mark_to_market"
    assert evidence["wfv"]["folds"]
    assert all(fold["equity_curve_usdc"][0] == 0.0 for fold in evidence["wfv"]["folds"])
    assert all(
        fold["equity_curve_usdc"][-1] == fold["metrics"]["net_profit_usdc"]
        for fold in evidence["wfv"]["folds"]
    )
    assert gate["passed"] is False
    assert gate["status"] in {"fail_gate", "fail_invalid_evidence"}
    assert gate["missing_evidence"] == []
    assert gate["invalid_evidence"] == [], gate["invalid_evidence"]
    assert gate["stage_readiness"]["research_evidence_complete"] is True
    assert evidence["rolling"]["drawdown_method"] == "mark_to_market"
    assert evidence["stress"]["baseline"]["fee_bps_per_side"] == 10.0
    assert evidence["stress"]["joint"]["fee_bps_per_side"] == 15.0
    assert evidence["parameter_stability"]["uses_audit_or_holdout"] is False
    assert evidence["temporal"]["months_observed"] >= 1
    assert evidence["regime"]["threshold_source"] == "training_only"
    assert evidence["selection_evidence_provenance"] == {
        "selection_data_only": True,
        "uses_audit_or_holdout": False,
        "rolling_temporal_regime_source": "chronological_walk_forward_validation_folds",
        "parameter_source": "internal_validation_only",
        "stress_source": "same_walk_forward_folds_fixed_cost_profiles",
    }
    assert "blindtest_audit" not in cycle
    assert cycle["rolling_origin_summary"]["uses_final_audit"] is False
    assert cycle["rolling_origin_summary"]["eligible_as_quality_gate_evidence"] is False
    assert report["window_plan"]["final_holdout_window"]["evaluated"] is False
    assert report["window_plan"]["final_holdout_window"]["status"] == "sealed_unopened"
    assert report["window_plan"]["final_holdout_window"]["consumed_audit_window"] is False
    assert report["freeze_status"] == "fixture_nonproduction_no_freeze"
    holdout_start = datetime.fromisoformat(
        report["window_plan"]["final_holdout_window"]["start"]
    ).replace(tzinfo=UTC)
    assert evaluated_open_times
    assert max(evaluated_open_times) < int(holdout_start.timestamp() * 1000)


def test_production_orchestration_enforces_defaults_and_never_simulates_planned_holdout(
    tmp_path, monkeypatch
):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    candles = _minute_candles(start, 10)
    training = candles[: 8 * 1440]
    holdout = candles[8 * 1440 :]
    split = SplitResult(
        training=training,
        blindtest=holdout,
        data_start="2024-01-01",
        data_end="2024-01-10",
        training_start="2024-01-01",
        training_end="2024-01-08",
        blind_start="2024-01-09",
        blind_end="2024-01-10",
        training_days=730,
        blindtest_days=365,
    )
    plan = ResearchWindowPlan(
        final_window=split,
        historical_origins=(),
        latest_complete_day="2024-01-10",
        available_complete_days=1095,
    )
    planner_call = {}

    def plan_spy(source, **kwargs):
        planner_call.update(kwargs)
        return plan

    evaluated_open_times: list[int] = []
    original_simulate = loop_module.simulate_strategy

    def simulate_spy(source, *args, **kwargs):
        evaluated_open_times.extend(candle.open_time for candle in source)
        return original_simulate(source, *args, **kwargs)

    monkeypatch.setattr(loop_module, "build_data_readiness_report", lambda root: {"data_gate_ready": True})
    monkeypatch.setattr(loop_module, "load_ethusdc_1m_candles", lambda root: candles)
    monkeypatch.setattr(loop_module, "build_research_window_plan", plan_spy)
    monkeypatch.setattr(loop_module, "simulate_strategy", simulate_spy)
    monkeypatch.setattr(walk_forward_module, "simulate_strategy", simulate_spy)
    monkeypatch.setattr(selection_evidence_module, "simulate_strategy", simulate_spy)

    result = run_research_loop(
        LoopConfig(
            raw_root=tmp_path / "synthetic_production_wiring",
            reports_root=tmp_path / "production_reports",
            max_cycles=1,
            min_cycles=1,
        )
    )

    report = json.loads(result.report_paths.json_path.read_text(encoding="utf-8"))
    cycle = report["cycles"][0]
    assert report["execution_profile"] == "production_protocol"
    assert report["fixture_data_only"] is False
    assert planner_call["expected_candles_per_day"] == 1440
    assert planner_call["excluded_selection_windows"] == CONSUMED_AUDIT_WINDOWS
    assert cycle["resource_budget"]["generated_cap"] == 40
    assert cycle["resource_budget"]["tested_cap"] == 12
    assert cycle["resource_budget"]["walk_forward_cap"] == 3
    assert cycle["resource_budget"]["finalists_cap"] == 2
    assert cycle["resource_budget"]["walk_forward_folds"] == 6
    assert cycle["resource_budget"]["rolling_origin_cap"] == 3
    assert cycle["resource_budget"]["stress_evidence_candidate_days_cap"] == 2920
    assert cycle["resource_budget"]["parameter_evidence_candidate_days_cap"] == 7008
    assert cycle["resource_budget"]["selection_total_candidate_days_cap"] == 24528
    assert cycle["walk_forward_candidates"] == 3
    assert cycle["finalists"] == 2
    assert report["freeze_status"] == "blocked_by_quality_gates"
    assert evaluated_open_times
    assert max(evaluated_open_times) < holdout[0].open_time
