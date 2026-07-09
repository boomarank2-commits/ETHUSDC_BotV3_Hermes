"""Command runner for the first real ETHUSDC backtest strategy search."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from ethusdc_bot.backtest.data_loader import DEFAULT_RAW_ROOT, load_ethusdc_1m_candles
from ethusdc_bot.backtest.reporting import ReportPaths, write_backtest_report
from ethusdc_bot.backtest.split import REQUIRED_DAYS, split_train_blind
from ethusdc_bot.backtest.strategy_search import StrategySearchResult, run_strategy_search
from ethusdc_bot.data_pipeline.data_readiness import build_data_readiness_report


@dataclass(frozen=True)
class BacktestRunResult:
    status: str
    search_result: StrategySearchResult
    report: ReportPaths


def run_backtest(
    *,
    raw_root: str | Path = DEFAULT_RAW_ROOT,
    reports_root: str | Path = "reports/backtests",
    required_days: int | None = REQUIRED_DAYS,
) -> BacktestRunResult:
    raw_root = Path(raw_root)
    print("[1/6] Daten-Gate prüfen")
    if required_days == REQUIRED_DAYS:
        readiness = build_data_readiness_report(raw_root)
        if not readiness["data_gate_ready"]:
            raise RuntimeError(f"Data gate blocked: {readiness['overall_status']}")
    print("[2/6] ETHUSDC 1m Daten laden")
    candles = load_ethusdc_1m_candles(raw_root)
    print(f"      Candles geladen: {len(candles)}")
    print("[3/6] Train/Blind Split prüfen")
    split = split_train_blind(candles, required_days=required_days)
    print(f"      Training: {split.training_days} Tage, Blindtest: {split.blindtest_days} Tage")
    print("[4/6] Strategie-Kandidaten auf Training/Validation suchen")
    search = run_strategy_search(split.training, split.blindtest, training_days=split.training_days, blindtest_days=split.blindtest_days)
    print(f"      Training best: {search.selected_candidate.family} {search.selected_candidate.params}")
    print("[5/6] Blindtest einmalig auswerten")
    print(f"      Blindtest net_usdc_per_day: {search.blindtest_metrics.net_usdc_per_day}")
    print("[6/6] Report schreiben")
    report = write_backtest_report(
        search,
        reports_root,
        split_summary={
            "data_start": split.data_start,
            "data_end": split.data_end,
            "training_start": split.training_start,
            "training_end": split.training_end,
            "training_days": split.training_days,
            "blind_start": split.blind_start,
            "blind_end": split.blind_end,
            "blindtest_days": split.blindtest_days,
            "no_overlap": True,
        },
    )
    print(f"      Report geschrieben: {report.json_path}")
    return BacktestRunResult(status="completed", search_result=search, report=report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run local ETHUSDC backtest strategy search. No orders/API/live.")
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT), help="External raw data root")
    parser.add_argument("--reports-root", default="reports/backtests", help="Backtest report output directory")
    parser.add_argument("--fixture-smoke", action="store_true", help="Allow non-1095-day fixture smoke split")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_backtest(
        raw_root=args.raw_root,
        reports_root=args.reports_root,
        required_days=None if args.fixture_smoke else REQUIRED_DAYS,
    )
    target = "erreicht" if result.search_result.target_reached else "nicht erreicht"
    print(f"Ziel 3 USDC/Tag: {target}")
    print("Live/Paper/Testtrade bleiben gesperrt. Keine Orders/API-Keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
