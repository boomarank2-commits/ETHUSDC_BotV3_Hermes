"""Honest diagnosis for completed ETHUSDC backtest reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def diagnose_backtest_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    training = data.get("training", {}).get("metrics", {})
    blind = data.get("blindtest", {}).get("metrics", {})
    target_reached = bool(data.get("target_reached"))
    cost_load = float(blind.get("fees_usdc", 0) or 0) + float(blind.get("slippage_usdc", 0) or 0)
    blind_abs_loss = abs(float(blind.get("net_profit_usdc", 0) or 0))
    trade_count = int(blind.get("trade_count", 0) or 0)
    blind_days = int(data.get("split", {}).get("blindtest_days", blind.get("blindtest_days", 365)) or 365)
    findings = {
        "target_not_reached": not target_reached,
        "training_negative": float(training.get("net_usdc_per_day", 0) or 0) < 0,
        "blindtest_negative": float(blind.get("net_usdc_per_day", 0) or 0) < 0,
        "similar_training_blindtest_weakness": abs(float(training.get("net_usdc_per_day", 0) or 0) - float(blind.get("net_usdc_per_day", 0) or 0)) < 0.5,
        "profit_factor_below_one": float(blind.get("profit_factor", 0) or 0) < 1,
        "winrate_low": float(blind.get("winrate", 0) or 0) < 0.4,
        "cost_load_high": cost_load > blind_abs_loss,
        "overtrading_suspected": trade_count / max(1, blind_days) > 3,
        "drawdown_high": float(blind.get("max_drawdown_usdc", 0) or 0) > 100,
    }
    findings["no_edge_indicated"] = (
        findings["training_negative"]
        and findings["blindtest_negative"]
        and findings["profit_factor_below_one"]
    )
    if not target_reached and findings["training_negative"] and findings["blindtest_negative"]:
        summary = "Ziel nicht erreicht; Training und Blindtest waren negativ."
    elif not target_reached:
        summary = "Ziel nicht erreicht."
    else:
        summary = "Ziel erreicht im Report; trotzdem nur Backtest, keine Live-Freigabe."
    return {
        "diagnosis_status": "completed",
        "source_report": str(report_path),
        "run_id": data.get("run_id"),
        "symbol": data.get("symbol"),
        "target_reached": target_reached,
        "training_metrics": training,
        "blindtest_metrics": blind,
        "findings": findings,
        "summary": summary,
        "interpretation": (
            "Die Daten zeigen keine belastbare Edge fuer den getesteten Kandidaten. "
            "Kosten, niedrige Winrate und Profit-Factor < 1 belasten das Ergebnis. "
            "Das beweist nicht, dass eine einzelne einfache Aenderung ausreicht."
        ),
    }


def format_diagnosis_text(diagnosis: dict[str, Any]) -> str:
    findings = diagnosis["findings"]
    lines = [
        f"Backtest-Diagnose: {diagnosis['run_id']}",
        diagnosis["summary"],
        f"Training negativ: {findings['training_negative']}",
        f"Blindtest negativ: {findings['blindtest_negative']}",
        f"Profit-Factor < 1: {findings['profit_factor_below_one']}",
        f"Winrate niedrig: {findings['winrate_low']}",
        f"Kostenlast hoch: {findings['cost_load_high']}",
        f"Overtrading-Verdacht: {findings['overtrading_suspected']}",
        f"Drawdown hoch: {findings['drawdown_high']}",
        diagnosis["interpretation"],
    ]
    return "\n".join(lines) + "\n"
