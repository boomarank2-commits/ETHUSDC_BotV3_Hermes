"""Multi-cycle reproducible offline research loop runner for ETHUSDC."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
from typing import Any, Callable

from ethusdc_bot.backtest.data_loader import DEFAULT_RAW_ROOT, Candle, load_ethusdc_1m_candles
from ethusdc_bot.backtest.exit_reason_analysis import analyze_exit_reasons
from ethusdc_bot.backtest.experiment_registry import ExperimentPaths
from ethusdc_bot.backtest.features import build_feature_rows
from ethusdc_bot.backtest.research_protocol import safety_status
from ethusdc_bot.backtest.research_runner import build_candidate_leaderboard, build_candidate_diagnosis, build_family_aggregates, build_family_diagnosis, rank_candidates
from ethusdc_bot.backtest.search_space import SearchSpaceState, generate_search_space, next_search_space_state
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy
from ethusdc_bot.backtest.split import REQUIRED_DAYS, split_train_blind
from ethusdc_bot.backtest.strategy_search import TARGET_USDC_PER_DAY
from ethusdc_bot.backtest.walk_forward import evaluate_walk_forward, rank_with_walk_forward
from ethusdc_bot.data_pipeline.data_readiness import build_data_readiness_report


@dataclass(frozen=True)
class LoopConfig:
    raw_root: str | Path = DEFAULT_RAW_ROOT
    reports_root: str | Path = "reports/research_loop"
    max_cycles: int = 8
    max_candidates_per_cycle: int = 40
    min_cycles: int = 3
    stagnation_cycles: int = 3
    required_days: int | None = REQUIRED_DAYS


@dataclass(frozen=True)
class LoopRunResult:
    loop_run_id: str
    cycles_executed: int
    stop_reason: str
    target_reached: bool
    best_candidate: dict[str, Any] | None
    report_paths: ExperimentPaths


def run_research_loop(
    config: LoopConfig,
    *,
    cycle_runner: Callable[[int, SearchSpaceState], dict[str, Any]] | None = None,
) -> LoopRunResult:
    run_id = datetime.now(UTC).strftime("research_loop_%Y%m%dT%H%M%SZ")
    git_commit = _git_commit()
    state = SearchSpaceState(cycle_index=1, diagnosis={"problem_assessment": "costs_and_insufficient_edge"})
    cycles: list[dict[str, Any]] = []
    best_validation = float("-inf")
    best_candidate: dict[str, Any] | None = None
    no_improvement = 0
    stop_reason = "max_cycles_reached"
    target_reached = False
    runner = cycle_runner or _build_real_cycle_runner(config)

    for cycle_index in range(1, config.max_cycles + 1):
        print(f"cycle {cycle_index}/{config.max_cycles}: starting", flush=True)
        cycle = runner(cycle_index, state)
        cycle["cycle_id"] = cycle_index
        cycles.append(_jsonable_cycle(cycle))
        if not _safety_ok(cycle.get("safety", {})):
            stop_reason = "safety_violation"
            break
        current_validation = _cycle_validation_net(cycle)
        blind = cycle.get("blindtest_audit") or {}
        current_blind = float(blind.get("net_usdc_per_day", float("-inf")))
        print(
            f"cycle {cycle_index}/{config.max_cycles}: candidates tested={cycle.get('tested_candidates', 0)} best validation={current_validation} best blindtest audit={current_blind}",
            flush=True,
        )
        if current_validation > best_validation:
            best_validation = current_validation
            best_candidate = cycle.get("selected_candidate")
            no_improvement = 0
        else:
            no_improvement += 1
        if cycle_index >= config.min_cycles and current_validation >= TARGET_USDC_PER_DAY and current_blind >= TARGET_USDC_PER_DAY:
            stop_reason = "target_reached_clean_validation_candidate"
            target_reached = True
            break
        if cycle_index >= config.min_cycles and no_improvement >= config.stagnation_cycles:
            stop_reason = f"validation_stagnation_{config.stagnation_cycles}_cycles"
            break
        state = next_search_space_state(cycle)
    else:
        stop_reason = "max_cycles_reached"

    report = _loop_report(
        run_id=run_id,
        git_commit=git_commit,
        config=config,
        cycles=cycles,
        stop_reason=stop_reason,
        target_reached=target_reached,
        best_candidate=best_candidate,
    )
    paths = _record_loop_report(report, config.reports_root)
    return LoopRunResult(run_id, len(cycles), stop_reason, target_reached, best_candidate, paths)


def _build_real_cycle_runner(config: LoopConfig) -> Callable[[int, SearchSpaceState], dict[str, Any]]:
    raw_root = Path(config.raw_root)
    if config.required_days == REQUIRED_DAYS:
        readiness = build_data_readiness_report(raw_root)
        if not readiness["data_gate_ready"]:
            raise RuntimeError(f"Data gate blocked: {readiness['overall_status']}")
    candles = load_ethusdc_1m_candles(raw_root)
    split = split_train_blind(candles, required_days=config.required_days)
    build_feature_rows(split.training[: min(len(split.training), 5000)])
    validation_start = max(1, int(len(split.training) * 0.8)) if len(split.training) > 5 else max(1, len(split.training) - 1)
    full_subtrain = split.training[:validation_start]
    subtrain = full_subtrain[-min(len(full_subtrain), 120 * 1440) :]
    validation = split.training[validation_start:] or split.training[-1:]
    subtrain_days = max(1, split.training_days * len(subtrain) // max(1, len(split.training)))
    validation_days = max(1, split.training_days - subtrain_days)

    def runner(cycle_index: int, state: SearchSpaceState) -> dict[str, Any]:
        generated_candidates = generate_search_space(state, max_candidates=config.max_candidates_per_cycle)
        # Keep each offline loop cycle bounded. The search-space generator may
        # propose up to the CLI cap; the loop evaluates a deterministic frontier
        # across families, then deepens WFV only for the validation leaders.
        candidates = generated_candidates[: min(len(generated_candidates), 4)]
        records: list[dict[str, Any]] = []
        for candidate_index, candidate in enumerate(candidates, start=1):
            train_result = simulate_strategy(subtrain, candidate, days=subtrain_days, training_days=split.training_days, blindtest_days=split.blindtest_days)
            validation_result = simulate_strategy(validation, candidate, days=validation_days, training_days=split.training_days, blindtest_days=split.blindtest_days)
            records.append(
                {
                    "candidate_id": f"{candidate.family}_{cycle_index:02d}_{candidate_index:03d}",
                    "candidate": candidate,
                    "training_result": train_result,
                    "validation_result": validation_result,
                    "training_metrics": train_result.metrics,
                    "validation_metrics": validation_result.metrics,
                    "walk_forward_summary": {"ranking_uses_blindtest": False, "not_evaluated_reason": "not_in_top_validation_frontier"},
                }
            )
        validation_ranked = rank_candidates(records)
        for record in validation_ranked[: min(1, len(validation_ranked))]:
            wfv_summary = evaluate_walk_forward(split.training, record["candidate"], fold_count=4, training_days=split.training_days, blindtest_days=split.blindtest_days, max_candles_per_fold=20_000)
            record["walk_forward_summary"] = wfv_summary
        ranked = rank_with_walk_forward(validation_ranked[: min(1, len(validation_ranked))]) + validation_ranked[min(1, len(validation_ranked)) :]
        selected_record = ranked[0]
        selected = selected_record["candidate"]
        blindtest_result = simulate_strategy(split.blindtest, selected, days=split.blindtest_days, training_days=split.training_days, blindtest_days=split.blindtest_days)
        leaderboard = build_candidate_leaderboard(records, selected_candidate_id=selected_record["candidate_id"], blindtest_metrics=blindtest_result.metrics)
        candidate_diagnosis = build_candidate_diagnosis(leaderboard)
        family_aggregates = build_family_aggregates(leaderboard)
        family_diagnosis = build_family_diagnosis(family_aggregates)
        exit_summary = analyze_exit_reasons(selected_record["validation_result"].trades)
        return {
            "generated_candidates": len(generated_candidates),
            "tested_candidates": len(records),
            "best_training_candidate": _best_metric_row(records, "training_metrics"),
            "best_validation_candidate": {
                "candidate_id": selected_record["candidate_id"],
                "family": selected.family,
                "net_usdc_per_day": selected_record["validation_metrics"].net_usdc_per_day,
                "trade_count": selected_record["validation_metrics"].trade_count,
                "profit_factor": selected_record["validation_metrics"].profit_factor,
            },
            "best_validation_metrics": selected_record["validation_metrics"],
            "wfv_summary": selected_record.get("walk_forward_summary", {}),
            "candidate_leaderboard_summary": leaderboard[:10],
            "family_aggregate_summary": family_aggregates,
            "family_diagnosis": family_diagnosis,
            "candidate_diagnosis": candidate_diagnosis,
            "exit_reason_summary": exit_summary,
            "selected_candidate": {"candidate_id": selected_record["candidate_id"], "family": selected.family, "params": dict(selected.params)},
            "blindtest_audit": {**blindtest_result.metrics.to_dict(), "repeated_blindtest_audit": True, "audit_only_not_selection": True},
            "full_training_metrics": selected_record["training_result"].metrics.to_dict(),
            "training_evaluation_note": "cycle subtrain uses a deterministic recent-training frontier for loop throughput; WFV remains chronological inside training and blindtest audit remains out-of-sample",
            "next_search_space_adjustment": _adjustment_reason(candidate_diagnosis, family_diagnosis, exit_summary),
            "safety": safety_status(),
            "selection_source": "training_validation_walk_forward_only",
        }

    return runner


def _best_metric_row(records: list[dict[str, Any]], metric_key: str) -> dict[str, Any]:
    record = max(records, key=lambda row: getattr(row[metric_key], "net_usdc_per_day"))
    metrics = record[metric_key]
    return {"candidate_id": record["candidate_id"], "family": record["candidate"].family, "net_usdc_per_day": metrics.net_usdc_per_day}


def _cycle_validation_net(cycle: dict[str, Any]) -> float:
    best = cycle.get("best_validation_candidate", {})
    if isinstance(best, dict) and "net_usdc_per_day" in best:
        return float(best["net_usdc_per_day"])
    metrics = cycle.get("best_validation_metrics")
    if hasattr(metrics, "net_usdc_per_day"):
        return float(metrics.net_usdc_per_day)
    if isinstance(metrics, dict):
        return float(metrics.get("net_usdc_per_day", 0.0))
    return 0.0


def _adjustment_reason(candidate_diagnosis: dict[str, Any], family_diagnosis: dict[str, Any], exit_summary: dict[str, Any]) -> str:
    if exit_summary.get("stop_loss_share", 0) > 0.45:
        return "stop_loss_dominates: tighten entry trend/volatility filters"
    if exit_summary.get("time_exit_share", 0) > 0.45:
        return "time_exit_dominates: test session/regime and exit timing variants"
    if family_diagnosis.get("problem_assessment") == "costs_and_insufficient_edge":
        return "costs_high: increase expected move thresholds and cooldown, reduce slippage-sensitive setups"
    return str(candidate_diagnosis.get("why_not_profitable_enough", "continue validation-only refinement"))


def _loop_report(**kwargs: Any) -> dict[str, Any]:
    cycles = kwargs["cycles"]
    best_validation_result = max((cycle.get("best_validation_candidate", {}) for cycle in cycles), key=lambda row: row.get("net_usdc_per_day", float("-inf")), default={})
    best_blindtest = max((cycle.get("blindtest_audit", {}) for cycle in cycles), key=lambda row: row.get("net_usdc_per_day", float("-inf")), default={})
    return {
        "schema_version": 1,
        "loop_run_id": kwargs["run_id"],
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "git_commit": kwargs["git_commit"],
        "raw_root": str(kwargs["config"].raw_root),
        "max_cycles": kwargs["config"].max_cycles,
        "max_candidates_per_cycle": kwargs["config"].max_candidates_per_cycle,
        "cycles_executed": len(cycles),
        "stop_reason": kwargs["stop_reason"],
        "target_reached": kwargs["target_reached"],
        "target_usdc_per_day": TARGET_USDC_PER_DAY,
        "best_candidate": kwargs["best_candidate"],
        "best_validation_result": best_validation_result,
        "best_blindtest_audit_result": best_blindtest,
        "cycles": cycles,
        "all_report_paths": {},
        "safety": safety_status(),
        "safety_status": "ok" if all(_safety_ok(cycle.get("safety", {})) for cycle in cycles) else "violation",
        "blindtest_policy": "Top candidates are audit-only repeated blindtest audits; search-space adjustments use training/validation/WFV only.",
        "result_text": "Ziel im Backtest erreicht, keine Live-Freigabe." if kwargs["target_reached"] else "Ziel nicht erreicht.",
    }


def _record_loop_report(report: dict[str, Any], reports_root: str | Path) -> ExperimentPaths:
    root = Path(reports_root)
    root.mkdir(parents=True, exist_ok=True)
    json_path = _unique_path(root / f"{report['loop_run_id']}.json")
    txt_path = json_path.with_suffix(".txt")
    stored = dict(report)
    stored["loop_run_id"] = json_path.stem
    stored["all_report_paths"] = {"json": str(json_path), "txt": str(txt_path), "index": str(root / "index.jsonl")}
    json_path.write_text(json.dumps(stored, indent=2, sort_keys=True), encoding="utf-8")
    txt_path.write_text(_format_loop_text(stored), encoding="utf-8")
    index_path = root / "index.jsonl"
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"loop_run_id": stored["loop_run_id"], "timestamp": stored["timestamp"], "stop_reason": stored["stop_reason"], "target_reached": stored["target_reached"], "json": str(json_path), "txt": str(txt_path)}, sort_keys=True) + "\n")
    return ExperimentPaths(json_path=json_path, txt_path=txt_path, index_path=index_path)


def _format_loop_text(report: dict[str, Any]) -> str:
    lines = [
        "ETHUSDC Offline Research Loop",
        f"Loop-Run-ID: {report.get('loop_run_id')}",
        f"Git commit: {report.get('git_commit')}",
        f"Raw root: {report.get('raw_root')}",
        f"Cycles executed: {report.get('cycles_executed')}/{report.get('max_cycles')}",
        f"Stop reason: {report.get('stop_reason')}",
        f"Target reached: {report.get('target_reached')}",
        f"Best candidate: {report.get('best_candidate')}",
        f"Best validation: {report.get('best_validation_result')}",
        f"Best blindtest audit: {report.get('best_blindtest_audit_result')}",
        str(report.get("result_text")),
        "Live/Paper/Testtrade locked. No orders, no Trading API, no API keys.",
        "Blindtest audits are repeated audits only and not used for search-space adjustment.",
    ]
    for cycle in report.get("cycles", []):
        lines.append(f"Cycle {cycle.get('cycle_id')}: tested={cycle.get('tested_candidates')} best_validation={cycle.get('best_validation_candidate')} blindtest_audit={cycle.get('blindtest_audit', {}).get('net_usdc_per_day')} adjustment={cycle.get('next_search_space_adjustment')}")
    lines.append("")
    return "\n".join(lines)


def _jsonable_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    def convert(value: Any) -> Any:
        if hasattr(value, "to_dict"):
            return value.to_dict()
        if isinstance(value, StrategyCandidate):
            return {"family": value.family, "params": dict(value.params)}
        if isinstance(value, dict):
            return {str(k): convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        return value

    return convert(cycle)


def _safety_ok(safety: dict[str, Any]) -> bool:
    required = {
        "live": "locked",
        "paper": "locked",
        "testtrade": "locked",
        "orders": "not_created",
        "binance_trading_api": "not_used",
        "api_keys": "not_used",
    }
    return all(safety.get(key) == value for key, value in required.items())


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index:03d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("could not allocate unique loop report path")


def _git_commit() -> str:
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
        status = subprocess.run(["git", "status", "--short"], check=True, text=True, capture_output=True).stdout.strip()
        return f"{commit}-dirty" if status else commit
    except Exception:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run multi-cycle offline ETHUSDC research loop. No orders/API/live.")
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT))
    parser.add_argument("--reports-root", default="reports/research_loop")
    parser.add_argument("--max-cycles", type=int, default=8)
    parser.add_argument("--max-candidates-per-cycle", type=int, default=40)
    parser.add_argument("--fixture-smoke", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = LoopConfig(
        raw_root=args.raw_root,
        reports_root=args.reports_root,
        max_cycles=args.max_cycles,
        max_candidates_per_cycle=args.max_candidates_per_cycle,
        required_days=None if args.fixture_smoke else REQUIRED_DAYS,
    )
    result = run_research_loop(config)
    print(f"Research loop run_id: {result.loop_run_id}")
    print(f"Report JSON: {result.report_paths.json_path}")
    print(f"Report TXT: {result.report_paths.txt_path}")
    print(f"Cycles executed: {result.cycles_executed}")
    print(f"Stop reason: {result.stop_reason}")
    print(f"Ziel 3 USDC/Tag: {'erreicht' if result.target_reached else 'nicht erreicht'}")
    print("Live/Paper/Testtrade bleiben gesperrt. Keine Orders/API-Keys/Trading API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
