"""Fail-closed compatibility entrypoint for the legacy backtest runner."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from ethusdc_bot.backtest.data_loader import DEFAULT_RAW_ROOT
from ethusdc_bot.backtest.reporting import ReportPaths
from ethusdc_bot.backtest.split import REQUIRED_DAYS
from ethusdc_bot.backtest.strategy_search import StrategySearchResult


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
    """Reject the old path before it can load, select, evaluate, or write."""

    raise RuntimeError(
        "Legacy backtest execution is disabled by Research Protocol v2 because it repeatedly evaluates the holdout; "
        "use ethusdc_bot.backtest.research_loop_runner"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Legacy ETHUSDC backtest runner (disabled by Research Protocol v2)."
    )
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT), help="External raw data root")
    parser.add_argument("--reports-root", default="reports/backtests", help="Backtest report output directory")
    parser.add_argument("--fixture-smoke", action="store_true", help="Compatibility flag; does not bypass the guard")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_backtest(
        raw_root=args.raw_root,
        reports_root=args.reports_root,
        required_days=None if args.fixture_smoke else REQUIRED_DAYS,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
