"""Write honest local backtest reports from completed runs only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path

from ethusdc_bot.backtest.strategy_search import StrategySearchResult, TARGET_USDC_PER_DAY


@dataclass(frozen=True)
class ReportPaths:
    json_path: Path
    txt_path: Path


def write_backtest_report(search_result: StrategySearchResult, reports_root: str | Path = "reports/backtests", *, split_summary: dict[str, object]) -> ReportPaths:
    reports_dir = Path(reports_root)
    reports_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("bt_%Y%m%dT%H%M%SZ")
    json_path = _unique_path(reports_dir / f"{run_id}.json")
    txt_path = json_path.with_suffix(".txt")
    data = _build_report(search_result, split_summary, run_id)
    json_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    txt_path.write_text(_format_text(data), encoding="utf-8")
    return ReportPaths(json_path=json_path, txt_path=txt_path)


def _build_report(search: StrategySearchResult, split_summary: dict[str, object], run_id: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "run_id": run_id,
        "status": "completed",
        "symbol": "ETHUSDC",
        "quote": "USDC",
        "market": "Binance Spot LONG-only",
        "trade_usdc": 100,
        "selection_source": search.selection_source,
        "target_usdc_per_day": TARGET_USDC_PER_DAY,
        "target_status": search.target_status,
        "target_reached": search.target_reached,
        "split": dict(split_summary),
        "strategy_families": search.strategy_families,
        "selected_candidate": {"family": search.selected_candidate.family, "params": dict(search.selected_candidate.params)},
        "training": {
            "candle_count": search.training_candle_count,
            "metrics": search.training_metrics.to_dict(),
        },
        "validation": {
            "metrics": search.validation_result.metrics.to_dict(),
        },
        "blindtest": {
            "candle_count": search.blindtest_candle_count,
            "metrics": search.blindtest_metrics.to_dict(),
            "trade_count": search.blindtest_result.trade_count,
        },
        "event_log": list(search.event_log),
        "safety": {
            "live": "locked",
            "paper": "locked",
            "testtrade": "locked",
            "orders": "not_created",
            "binance_trading_api": "not_used",
            "api_keys": "not_used",
            "candidate_adoptable": False,
        },
        "honesty_note": "Real local backtest report. Blindtest evaluated once after training/validation selection. No live, paper, testtrade, orders, or API keys.",
    }


def _format_text(data: dict[str, object]) -> str:
    blind = data["blindtest"]["metrics"]  # type: ignore[index]
    training = data["training"]["metrics"]  # type: ignore[index]
    reached = bool(data["target_reached"])
    target_line = "Ziel erreicht" if reached else "Ziel nicht erreicht"
    return "\n".join(
        [
            "ETHUSDC Backtest / Strategie-Suche",
            f"Run-ID: {data['run_id']}",
            f"Status: {data['status']}",
            f"Symbol: {data['symbol']}",
            f"Split: {data['split']}",
            f"Strategie-Familien: {', '.join(data['strategy_families'])}",  # type: ignore[arg-type]
            f"Auswahlquelle: {data['selection_source']}",
            f"Ausgewählter Kandidat: {data['selected_candidate']}",
            f"Training net_usdc_per_day: {training['net_usdc_per_day']}",
            f"Training net_profit_usdc: {training['net_profit_usdc']}",
            f"Blindtest net_usdc_per_day: {blind['net_usdc_per_day']}",
            f"Blindtest net_profit_usdc: {blind['net_profit_usdc']}",
            f"Blindtest trades: {blind['trade_count']}",
            f"Fees USDC: {blind['fees_usdc']}",
            f"Slippage USDC: {blind['slippage_usdc']}",
            f"Drawdown USDC: {blind['max_drawdown_usdc']}",
            f"Winrate: {blind['winrate']}",
            f"Profit-Factor: {blind['profit_factor']}",
            f"Ziel: >= {data['target_usdc_per_day']} USDC/Tag im Blindtest",
            target_line,
            "Live/Paper/Testtrade bleiben locked. Keine Orders, keine Trading API, keine API-Keys.",
            "",
        ]
    )


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    for index in range(1, 1000):
        candidate = path.with_name(f"{stem}_{index:03d}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError("could not create unique report path")
