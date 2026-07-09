"""Reproducible offline strategy research runner for ETHUSDC."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
from typing import Any

from ethusdc_bot.backtest.data_loader import DEFAULT_RAW_ROOT, Candle, load_ethusdc_1m_candles
from ethusdc_bot.backtest.experiment_registry import ExperimentPaths, record_experiment
from ethusdc_bot.backtest.features import build_feature_rows
from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.research_protocol import build_research_protocol, safety_status, validate_research_protocol
from ethusdc_bot.backtest.simulator import SimulationResult, StrategyCandidate, simulate_strategy
from ethusdc_bot.backtest.split import REQUIRED_DAYS, split_train_blind
from ethusdc_bot.backtest.strategy_search import TARGET_USDC_PER_DAY
from ethusdc_bot.data_pipeline.data_readiness import build_data_readiness_report


@dataclass(frozen=True)
class ResearchRunResult:
    run_id: str
    selection_source: str
    candidates_tested: int
    selected_candidate: StrategyCandidate
    why_selected: str
    training_metrics: BacktestMetrics
    validation_metrics: BacktestMetrics
    blindtest_metrics: BacktestMetrics
    target_reached: bool
    event_log: list[str]
    experiment_paths: ExperimentPaths
    strategy_families: list[str]


def generate_research_candidates() -> list[StrategyCandidate]:
    """Return a controlled, explainable parameter grid; not wild brute force."""

    return [
        StrategyCandidate("momentum_trend_filter", {"lookback": 15, "threshold_bps": 12, "trend_lookback": 120, "trend_min_bps": 8, "take_profit_bps": 80, "stop_loss_bps": 55, "max_hold_minutes": 45, "cooldown_minutes": 20}),
        StrategyCandidate("momentum_trend_filter", {"lookback": 60, "threshold_bps": 25, "trend_lookback": 240, "trend_min_bps": 20, "take_profit_bps": 120, "stop_loss_bps": 75, "max_hold_minutes": 120, "cooldown_minutes": 45}),
        StrategyCandidate("breakout_volatility_filter", {"lookback": 30, "threshold_bps": 5, "volatility_lookback": 60, "min_vol_bps": 8, "max_vol_bps": 80, "take_profit_bps": 90, "stop_loss_bps": 60, "max_hold_minutes": 60, "cooldown_minutes": 30}),
        StrategyCandidate("breakout_volatility_filter", {"lookback": 120, "threshold_bps": 10, "volatility_lookback": 240, "min_vol_bps": 10, "max_vol_bps": 120, "take_profit_bps": 140, "stop_loss_bps": 90, "max_hold_minutes": 180, "cooldown_minutes": 90}),
        StrategyCandidate("mean_reversion_regime_filter", {"lookback": 20, "threshold_bps": 35, "trend_lookback": 180, "max_abs_trend_bps": 80, "take_profit_bps": 50, "stop_loss_bps": 45, "max_hold_minutes": 45, "cooldown_minutes": 20}),
        StrategyCandidate("mean_reversion_regime_filter", {"lookback": 60, "threshold_bps": 70, "trend_lookback": 360, "max_abs_trend_bps": 120, "take_profit_bps": 80, "stop_loss_bps": 70, "max_hold_minutes": 120, "cooldown_minutes": 60}),
        StrategyCandidate("pullback_in_trend", {"lookback": 15, "threshold_bps": 18, "trend_lookback": 240, "trend_min_bps": 25, "take_profit_bps": 75, "stop_loss_bps": 55, "max_hold_minutes": 60, "cooldown_minutes": 30}),
        StrategyCandidate("pullback_in_trend", {"lookback": 45, "threshold_bps": 35, "trend_lookback": 480, "trend_min_bps": 40, "take_profit_bps": 110, "stop_loss_bps": 80, "max_hold_minutes": 180, "cooldown_minutes": 90}),
        StrategyCandidate("session_filter", {"base_family": "momentum", "lookback": 30, "threshold_bps": 20, "session_start_hour": 7, "session_end_hour": 20, "take_profit_bps": 90, "stop_loss_bps": 70, "max_hold_minutes": 90, "cooldown_minutes": 60}),
        StrategyCandidate("session_filter", {"base_family": "breakout", "lookback": 60, "threshold_bps": 8, "session_start_hour": 12, "session_end_hour": 22, "take_profit_bps": 120, "stop_loss_bps": 80, "max_hold_minutes": 120, "cooldown_minutes": 90}),
        StrategyCandidate("cooldown_fee_aware", {"base_family": "breakout", "lookback": 90, "threshold_bps": 12, "min_expected_move_bps": 35, "take_profit_bps": 140, "stop_loss_bps": 80, "max_hold_minutes": 180, "cooldown_minutes": 180}),
        StrategyCandidate("cooldown_fee_aware", {"base_family": "momentum", "lookback": 120, "threshold_bps": 40, "min_expected_move_bps": 45, "take_profit_bps": 160, "stop_loss_bps": 100, "max_hold_minutes": 240, "cooldown_minutes": 240}),
        StrategyCandidate("breakout_volatility_filter", {"lookback": 120, "threshold_bps": 10, "volatility_lookback": 240, "min_vol_bps": 12, "max_vol_bps": 110, "take_profit_bps": 160, "stop_loss_bps": 90, "trailing_stop_bps": 70, "break_even_after_bps": 65, "max_hold_minutes": 180, "cooldown_minutes": 120}),
        StrategyCandidate("cooldown_fee_aware", {"base_family": "breakout", "lookback": 120, "threshold_bps": 15, "min_expected_move_bps": 45, "take_profit_bps": 170, "stop_loss_bps": 90, "trailing_stop_bps": 80, "break_even_after_bps": 70, "max_hold_minutes": 240, "cooldown_minutes": 240}),
        StrategyCandidate("cooldown_fee_aware", {"base_family": "breakout", "lookback": 180, "threshold_bps": 20, "min_expected_move_bps": 70, "take_profit_bps": 190, "stop_loss_bps": 95, "trailing_stop_bps": 90, "break_even_after_bps": 80, "max_hold_minutes": 300, "cooldown_minutes": 300}),
        StrategyCandidate("cooldown_fee_aware", {"base_family": "momentum", "lookback": 180, "threshold_bps": 55, "min_expected_move_bps": 85, "take_profit_bps": 220, "stop_loss_bps": 110, "trailing_stop_bps": 100, "break_even_after_bps": 95, "max_hold_minutes": 360, "cooldown_minutes": 360}),
    ]


def rank_candidates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank without consulting blindtest metrics."""

    return sorted(records, key=lambda record: _rank_tuple(record), reverse=True)


def build_candidate_leaderboard(
    records: list[dict[str, Any]],
    *,
    selected_candidate_id: str,
    blindtest_metrics: BacktestMetrics,
) -> list[dict[str, Any]]:
    """Build a full training/validation leaderboard without blindtest ranking leakage."""

    ranked = rank_candidates(records)
    leaderboard: list[dict[str, Any]] = []
    for position, record in enumerate(ranked, start=1):
        candidate = record["candidate"]
        training = record["training_metrics"]
        validation = record["validation_metrics"]
        row = {
            "candidate_id": record["candidate_id"],
            "family": candidate.family,
            "params": dict(candidate.params),
            "training_metrics": training.to_dict(),
            "validation_metrics": validation.to_dict(),
            "rank_score": round(_rank_score(record), 10),
            "rank_position": position,
            "why_ranked_here": _why_ranked_here(position, validation),
            "weaknesses": _candidate_weaknesses(training, validation),
        }
        if record["candidate_id"] == selected_candidate_id:
            row["blindtest_metrics"] = blindtest_metrics.to_dict()
        leaderboard.append(row)
    return leaderboard


def build_candidate_diagnosis(leaderboard: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize family-level candidate behavior from training/validation only."""

    best_training = max(leaderboard, key=lambda row: row["training_metrics"]["net_usdc_per_day"])
    best_validation = min(leaderboard, key=lambda row: row["rank_position"])
    least_cost = min(leaderboard, key=lambda row: row["validation_metrics"]["fees_usdc"] + row["validation_metrics"]["slippage_usdc"])
    overtrading = [row["family"] for row in leaderboard if "overtrading" in row["weaknesses"]]
    too_few = [row["family"] for row in leaderboard if "too_few_trades" in row["weaknesses"]]
    near_one = [row["family"] for row in leaderboard if 0.85 <= row["validation_metrics"].get("profit_factor", 0) < 1.15]
    negative_validation = [row for row in leaderboard if "validation_negative" in row["weaknesses"]]
    cost_high = [row for row in leaderboard if "cost_load_high" in row["weaknesses"]]
    return {
        "ranking_uses_blindtest": False,
        "best_training_family": best_training["family"],
        "best_training_candidate_id": best_training["candidate_id"],
        "best_validation_family": best_validation["family"],
        "best_validation_candidate_id": best_validation["candidate_id"],
        "lowest_cost_family": least_cost["family"],
        "lowest_cost_candidate_id": least_cost["candidate_id"],
        "overtrading_families": sorted(set(overtrading)),
        "too_few_trades_families": sorted(set(too_few)),
        "profit_factor_near_one_families": sorted(set(near_one)),
        "negative_validation_candidate_count": len(negative_validation),
        "high_cost_candidate_count": len(cost_high),
        "overtrading_candidate_count": len(overtrading),
        "too_few_trades_candidate_count": len(too_few),
        "why_not_profitable_enough": _why_not_profitable_enough(best_validation),
    }


def build_family_aggregates(leaderboard: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate candidate leaderboard by family using training/validation only."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in leaderboard:
        grouped.setdefault(str(row["family"]), []).append(row)
    aggregates: list[dict[str, Any]] = []
    for family in sorted(grouped):
        rows = grouped[family]
        best_validation = max(rows, key=lambda row: row["validation_metrics"]["net_usdc_per_day"])
        training_values = [row["training_metrics"]["net_usdc_per_day"] for row in rows]
        validation_values = [row["validation_metrics"]["net_usdc_per_day"] for row in rows]
        trade_counts = [row["validation_metrics"]["trade_count"] for row in rows]
        fees = [row["validation_metrics"].get("fees_usdc", 0.0) for row in rows]
        slippage = [row["validation_metrics"].get("slippage_usdc", 0.0) for row in rows]
        cost_loads = [fee + slip for fee, slip in zip(fees, slippage)]
        profit_factors = [row["validation_metrics"].get("profit_factor", 0.0) for row in rows]
        drawdowns = [row["validation_metrics"].get("max_drawdown_usdc", 0.0) for row in rows]
        aggregates.append(
            {
                "family": family,
                "candidate_count": len(rows),
                "best_validation_candidate_id": best_validation["candidate_id"],
                "best_validation_net_usdc_per_day": round(best_validation["validation_metrics"]["net_usdc_per_day"], 10),
                "average_validation_net_usdc_per_day": round(_average(validation_values), 10),
                "best_training_net_usdc_per_day": round(max(training_values), 10),
                "average_training_net_usdc_per_day": round(_average(training_values), 10),
                "average_trade_count": round(_average(trade_counts), 4),
                "min_trade_count": min(trade_counts),
                "max_trade_count": max(trade_counts),
                "average_fees_usdc": round(_average(fees), 10),
                "average_slippage_usdc": round(_average(slippage), 10),
                "average_cost_load": round(_average(cost_loads), 10),
                "best_profit_factor": round(max(profit_factors), 10),
                "average_profit_factor": round(_average(profit_factors), 10),
                "best_drawdown": round(min(drawdowns), 10),
                "worst_drawdown": round(max(drawdowns), 10),
                "overtrading_count": sum(1 for row in rows if "overtrading" in row.get("weaknesses", [])),
                "too_few_trades_count": sum(1 for row in rows if "too_few_trades" in row.get("weaknesses", [])),
                "negative_validation_count": sum(1 for row in rows if "validation_negative" in row.get("weaknesses", [])),
                "high_cost_count": sum(1 for row in rows if "cost_load_high" in row.get("weaknesses", [])),
            }
        )
    return aggregates


def build_family_diagnosis(family_aggregates: list[dict[str, Any]]) -> dict[str, Any]:
    """Diagnose family-level behavior without blindtest metrics."""

    best_training = max(family_aggregates, key=lambda row: row["best_training_net_usdc_per_day"])
    best_validation = max(family_aggregates, key=lambda row: row["best_validation_net_usdc_per_day"])
    lowest_cost = min(family_aggregates, key=lambda row: row["average_cost_load"])
    nearest_one = min(family_aggregates, key=lambda row: abs(row["best_profit_factor"] - 1.0))
    overtrading = [row["family"] for row in family_aggregates if row["overtrading_count"] > 0]
    too_few = [row["family"] for row in family_aggregates if row["too_few_trades_count"] > 0]
    high_cost = [row["family"] for row in family_aggregates if row["high_cost_count"] >= row["candidate_count"]]
    return {
        "ranking_uses_blindtest": False,
        "best_training_family": best_training["family"],
        "best_validation_family": best_validation["family"],
        "lowest_cost_family": lowest_cost["family"],
        "overtrading_families": sorted(overtrading),
        "too_few_trades_families": sorted(too_few),
        "profit_factor_nearest_one_family": nearest_one["family"],
        "high_cost_families": sorted(high_cost),
        "problem_assessment": _family_problem_assessment(family_aggregates),
    }


def _average(values: list[float | int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _family_problem_assessment(family_aggregates: list[dict[str, Any]]) -> str:
    if all(row["high_cost_count"] == row["candidate_count"] for row in family_aggregates):
        return "costs_and_insufficient_edge"
    if any(row["overtrading_count"] for row in family_aggregates):
        return "trade_frequency_and_costs"
    if all(row["best_validation_net_usdc_per_day"] < 0 for row in family_aggregates):
        return "missing_edge"
    return "entry_exit_refinement_needed"


def _rank_tuple(record: dict[str, Any]) -> tuple[float, float, float, float, float]:
    validation = record["validation_metrics"]
    return (
        _rank_score(record),
        validation.net_usdc_per_day,
        validation.profit_factor,
        -validation.max_drawdown_usdc,
        -validation.trade_count,
    )


def _rank_score(record: dict[str, Any]) -> float:
    training = record["training_metrics"]
    validation = record["validation_metrics"]
    stability = -abs(validation.net_usdc_per_day - training.net_usdc_per_day)
    overtrade_penalty = -max(0, validation.trade_count - 1000) / 100
    undertrade_penalty = -max(0, 20 - validation.trade_count) / 20
    cost_penalty = -(validation.fees_usdc + validation.slippage_usdc) / 100
    drawdown_penalty = -validation.max_drawdown_usdc / 100
    return validation.net_usdc_per_day + validation.profit_factor * 0.2 + stability * 0.5 + cost_penalty + drawdown_penalty + overtrade_penalty + undertrade_penalty


def _candidate_weaknesses(training: BacktestMetrics, validation: BacktestMetrics) -> list[str]:
    weaknesses: list[str] = []
    if training.net_usdc_per_day < 0:
        weaknesses.append("training_negative")
    if validation.net_usdc_per_day < 0:
        weaknesses.append("validation_negative")
    if validation.profit_factor < 1:
        weaknesses.append("profit_factor_below_one")
    if validation.trade_count < 20:
        weaknesses.append("too_few_trades")
    if validation.trade_count > 1000:
        weaknesses.append("overtrading")
    cost_load = validation.fees_usdc + validation.slippage_usdc
    if cost_load > max(1.0, abs(validation.net_profit_usdc)) * 2:
        weaknesses.append("cost_load_high")
    if validation.max_drawdown_usdc > max(25.0, abs(validation.net_profit_usdc) * 1.5):
        weaknesses.append("drawdown_high")
    if abs(validation.net_usdc_per_day - training.net_usdc_per_day) > max(0.25, abs(training.net_usdc_per_day) * 2):
        weaknesses.append("unstable_train_validation")
    return weaknesses


def _why_ranked_here(position: int, validation: BacktestMetrics) -> str:
    if position == 1:
        return "best conservative validation-only rank; blindtest not used"
    return f"ranked {position} by validation-only score; net/day={validation.net_usdc_per_day}, pf={validation.profit_factor}, trades={validation.trade_count}"


def _why_not_profitable_enough(best_validation: dict[str, Any]) -> str:
    validation = best_validation["validation_metrics"]
    weaknesses = best_validation.get("weaknesses", [])
    if validation["net_usdc_per_day"] < 0:
        return "best validation candidate is still negative before blindtest; no sufficient edge shown"
    if validation["profit_factor"] < 1:
        return "best validation candidate has profit factor below one"
    if "cost_load_high" in weaknesses:
        return "cost load remains high relative to net result"
    return "validation result is below the strategic target and still needs independent blindtest confirmation"


def run_research(
    *,
    raw_root: str | Path = DEFAULT_RAW_ROOT,
    reports_root: str | Path = "reports/research",
    required_days: int | None = REQUIRED_DAYS,
) -> ResearchRunResult:
    event_log = ["data_gate_check_started"]
    raw_root = Path(raw_root)
    if required_days == REQUIRED_DAYS:
        readiness = build_data_readiness_report(raw_root)
        if not readiness["data_gate_ready"]:
            raise RuntimeError(f"Data gate blocked: {readiness['overall_status']}")
    event_log.append("data_gate_ready")
    candles = load_ethusdc_1m_candles(raw_root)
    event_log.append("ethusdc_loaded")
    split = split_train_blind(candles, required_days=required_days)
    event_log.append("split_built")
    # Build features once for auditability/no-lookahead checks. Current simulator uses candles directly.
    feature_sample = build_feature_rows(split.training[: min(len(split.training), 5000)])
    event_log.append("features_prepared")
    validation_start = max(1, int(len(split.training) * 0.8)) if len(split.training) > 5 else max(1, len(split.training) - 1)
    subtrain = split.training[:validation_start]
    validation = split.training[validation_start:] or split.training[-1:]
    candidates = generate_research_candidates()
    records: list[dict[str, Any]] = []
    subtrain_days = max(1, split.training_days * len(subtrain) // max(1, len(split.training)))
    validation_days = max(1, split.training_days - subtrain_days)
    for candidate_index, candidate in enumerate(candidates, start=1):
        train_result = simulate_strategy(subtrain, candidate, days=subtrain_days, training_days=split.training_days, blindtest_days=split.blindtest_days)
        validation_result = simulate_strategy(validation, candidate, days=validation_days, training_days=split.training_days, blindtest_days=split.blindtest_days)
        records.append(
            {
                "candidate_id": f"{candidate.family}_{candidate_index:03d}",
                "candidate": candidate,
                "training_result": train_result,
                "validation_result": validation_result,
                "training_metrics": train_result.metrics,
                "validation_metrics": validation_result.metrics,
            }
        )
    event_log.append("candidates_evaluated_on_subtrain_validation")
    ranked = rank_candidates(records)
    selected_record = ranked[0]
    selected = selected_record["candidate"]
    selected_candidate_id = selected_record["candidate_id"]
    why_selected = "highest conservative validation rank using validation net/day, profit factor, drawdown, stability, trade frequency and cost load; blindtest not used"
    event_log.append("candidate_selected")
    full_training_result = simulate_strategy(split.training, selected, days=split.training_days, training_days=split.training_days, blindtest_days=split.blindtest_days)
    blindtest_result = simulate_strategy(split.blindtest, selected, days=split.blindtest_days, training_days=split.training_days, blindtest_days=split.blindtest_days)
    event_log.append("blindtest_evaluated")
    target_reached = blindtest_result.metrics.net_usdc_per_day >= TARGET_USDC_PER_DAY
    git_commit = _git_commit()
    run_id = datetime.now(UTC).strftime("research_%Y%m%dT%H%M%SZ")
    protocol = build_research_protocol(
        raw_root=raw_root,
        git_commit=git_commit,
        run_id=run_id,
        data_window={"data_start": split.data_start, "data_end": split.data_end},
        parameter_space=_parameter_space(candidates),
    )
    validation_protocol = validate_research_protocol(protocol)
    if not validation_protocol["valid"]:
        raise RuntimeError(f"Invalid research protocol: {validation_protocol['errors']}")
    candidate_leaderboard = build_candidate_leaderboard(records, selected_candidate_id=selected_candidate_id, blindtest_metrics=blindtest_result.metrics)
    candidate_diagnosis = build_candidate_diagnosis(candidate_leaderboard)
    family_aggregates = build_family_aggregates(candidate_leaderboard)
    family_diagnosis = build_family_diagnosis(family_aggregates)
    experiment = _experiment_record(
        run_id=run_id,
        git_commit=git_commit,
        raw_root=raw_root,
        split=split,
        candidates=candidates,
        selected=selected,
        why_selected=why_selected,
        full_training_result=full_training_result,
        selected_validation_result=selected_record["validation_result"],
        blindtest_result=blindtest_result,
        target_reached=target_reached,
        event_log=event_log,
        feature_sample_count=len(feature_sample),
        protocol=protocol,
        candidate_leaderboard=candidate_leaderboard,
        candidate_diagnosis=candidate_diagnosis,
        family_aggregates=family_aggregates,
        family_diagnosis=family_diagnosis,
        selected_candidate_id=selected_candidate_id,
    )
    paths = record_experiment(experiment, reports_root)
    return ResearchRunResult(
        run_id=paths.json_path.stem,
        selection_source="subtrain_validation_only",
        candidates_tested=len(candidates),
        selected_candidate=selected,
        why_selected=why_selected,
        training_metrics=full_training_result.metrics,
        validation_metrics=selected_record["validation_result"].metrics,
        blindtest_metrics=blindtest_result.metrics,
        target_reached=target_reached,
        event_log=event_log,
        experiment_paths=paths,
        strategy_families=sorted({candidate.family for candidate in candidates}),
    )


def _experiment_record(**kwargs: Any) -> dict[str, Any]:
    split = kwargs["split"]
    candidates = kwargs["candidates"]
    selected = kwargs["selected"]
    return {
        "schema_version": 1,
        "run_id": kwargs["run_id"],
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_commit": kwargs["git_commit"],
        "raw_root": str(kwargs["raw_root"]),
        "data_window": {"data_start": split.data_start, "data_end": split.data_end},
        "training_window": {"training_start": split.training_start, "training_end": split.training_end, "training_days": split.training_days},
        "validation_window": {"source": "last_20_percent_of_training", "selection_only": True},
        "blindtest_window": {"blind_start": split.blind_start, "blind_end": split.blind_end, "blindtest_days": split.blindtest_days, "final_evaluation_only": True},
        "strategy_families": sorted({candidate.family for candidate in candidates}),
        "parameter_space": _parameter_space(candidates),
        "parameter_counts": {"total_candidates": len(candidates), "families": len({candidate.family for candidate in candidates})},
        "selected_candidate": {"candidate_id": kwargs["selected_candidate_id"], "family": selected.family, "params": dict(selected.params)},
        "why_selected": kwargs["why_selected"],
        "candidate_leaderboard": kwargs["candidate_leaderboard"],
        "candidate_diagnosis": kwargs["candidate_diagnosis"],
        "family_aggregates": kwargs["family_aggregates"],
        "family_diagnosis": kwargs["family_diagnosis"],
        "training_metrics": kwargs["full_training_result"].metrics.to_dict(),
        "validation_metrics": kwargs["selected_validation_result"].metrics.to_dict(),
        "blindtest_metrics": kwargs["blindtest_result"].metrics.to_dict(),
        "target_reached": kwargs["target_reached"],
        "target_usdc_per_day": TARGET_USDC_PER_DAY,
        "selection_source": "subtrain_validation_only",
        "event_log": list(kwargs["event_log"]),
        "feature_sample_count": kwargs["feature_sample_count"],
        "research_protocol": kwargs["protocol"],
        "safety": safety_status(),
        "report_links": {},
        "comparison_to_previous_report": {
            "previous_run_id": "bt_20260709T151036Z",
            "previous_blindtest_net_usdc_per_day": -1.3459078771,
        },
    }


def _parameter_space(candidates: list[StrategyCandidate]) -> dict[str, Any]:
    by_family: dict[str, int] = {}
    for candidate in candidates:
        by_family[candidate.family] = by_family.get(candidate.family, 0) + 1
    return {"candidate_count": len(candidates), "by_family": by_family, "candidates": [{"family": c.family, "params": dict(c.params)} for c in candidates]}


def _git_commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], check=True, text=True, capture_output=True)
        commit = result.stdout.strip()
        status = subprocess.run(["git", "status", "--short"], check=True, text=True, capture_output=True)
        return f"{commit}-dirty" if status.stdout.strip() else commit
    except Exception:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run reproducible offline ETHUSDC strategy research. No orders/API/live.")
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    parser.add_argument("--reports-root", default="reports/research")
    parser.add_argument("--fixture-smoke", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_research(raw_root=args.raw_root, reports_root=args.reports_root, required_days=None if args.fixture_smoke else REQUIRED_DAYS)
    print(f"Research run_id: {result.run_id}")
    print(f"Report JSON: {result.experiment_paths.json_path}")
    print(f"Report TXT: {result.experiment_paths.txt_path}")
    print(f"Families: {', '.join(result.strategy_families)}")
    print(f"Candidates tested: {result.candidates_tested}")
    print(f"Selected: {result.selected_candidate.family} {json.dumps(result.selected_candidate.params, sort_keys=True)}")
    print(f"Why selected: {result.why_selected}")
    print(f"Training net_usdc_per_day: {result.training_metrics.net_usdc_per_day}")
    print(f"Validation net_usdc_per_day: {result.validation_metrics.net_usdc_per_day}")
    print(f"Blindtest net_usdc_per_day: {result.blindtest_metrics.net_usdc_per_day}")
    print(f"Ziel 3 USDC/Tag: {'erreicht' if result.target_reached else 'nicht erreicht'}")
    print("Live/Paper/Testtrade bleiben gesperrt. Keine Orders/API-Keys/Trading API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
