"""Tests for the read-only backtest display model used by the existing UI."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

from ethusdc_bot.ui.backtest_display import (
    collect_backtest_display_status,
    format_backtest_log_for_display,
    format_backtest_summary_for_display,
)


def _checkpoint(
    root: Path,
    *,
    status: str = "running",
    active_cycle: int | None = 2,
    report_json: str | None = None,
) -> Path:
    path = root / "production_research_supervisor_20260712T081650Z.checkpoint.json"
    payload = {
        "schema_version": 1,
        "artifact_kind": "research_supervisor_checkpoint",
        "run_id": "production_research_supervisor_20260712T081650Z",
        "timestamp_utc": "2026-07-12T08:32:15Z",
        "started_at_utc": "2026-07-12T08:16:50Z",
        "status": status,
        "git_commit": "c4b9254",
        "git_branch": "codex/pr12-final-local-run",
        "max_cycles": 8,
        "completed_cycle_count": 1,
        "active_cycle": active_cycle,
        "cycles": [
            {
                "cycle": 1,
                "maximum": 8,
                "generated": 40,
                "tested": 12,
                "walk_forward": 3,
                "finalists": 2,
                "selected_rank_text": "(0.0, 0.125, 1.25, -0.75, -0.02, 4.0, 0.15, -2.5)",
                "runtime_proof": {
                    "context_research": {"enabled": True},
                    "context_generated": 6,
                    "context_tested": 2,
                    "walk_forward_folds": 6,
                    "rolling_origin_limit": 3,
                    "audit_evaluated": False,
                    "final_holdout_evaluated": False,
                },
            }
        ],
        "child_exit_code": 0 if status == "completed" else None,
        "report_json": report_json,
        "audit_evaluated": False,
        "final_holdout_evaluated": False,
        "safety": {
            "live": "locked",
            "paper": "locked",
            "testtrade": "locked",
            "orders": "not_created",
            "trading_api": "not_used",
            "api_keys": "not_used",
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_idle_status_does_not_invent_backtest_results(tmp_path: Path) -> None:
    status = collect_backtest_display_status(tmp_path)

    assert status["mode"] == "idle"
    assert status["progress_pct"] == 0.0
    assert status["final_summary"] is None
    assert status["audit_evaluated"] is False
    assert status["final_holdout_evaluated"] is False


def test_running_checkpoint_drives_progress_and_current_metrics(tmp_path: Path) -> None:
    _checkpoint(tmp_path)
    log = tmp_path / "production_research_20260712T081625Z.console.log"
    log.write_text("cycle 1/8: starting\ncycle 1/8: generated=40 tested=12 walk_forward=3 finalists=2\ncycle 2/8: starting\n", encoding="utf-8")

    status = collect_backtest_display_status(
        tmp_path,
        now_utc=datetime(2026, 7, 12, 8, 36, 50, tzinfo=UTC),
    )

    assert status["mode"] == "running"
    assert status["progress_pct"] == 12.5
    assert status["completed_cycles"] == 1
    assert status["active_cycle"] == 2
    assert status["context_enabled"] is True
    assert status["best_cycle"]["wfv_net_usdc_per_day"] == 0.125
    assert status["best_cycle"]["wfv_max_drawdown_usdc"] == 0.75
    assert status["best_cycle"]["wfv_cost_load"] == 2.5
    assert status["elapsed_seconds"] == 1200
    assert status["recent_log_lines"][-1] == "cycle 2/8: starting"

    summary = format_backtest_summary_for_display(status)
    assert "Zyklus 2/8" in summary
    assert "40 erzeugt / 12 getestet / 3 WFV / 2 Finalisten" in summary
    assert "0.125000 USDC" in summary
    assert "Audit ausgewertet: False" in summary


def test_controller_start_is_visible_before_first_checkpoint(tmp_path: Path) -> None:
    status = collect_backtest_display_status(
        tmp_path,
        controller_status={
            "running": True,
            "started_at": "2026-07-12T08:16:50Z",
            "context_research_enabled": True,
        },
    )

    assert status["mode"] == "running"
    assert status["status_text"] == "Backtest wird gestartet"
    assert status["progress_visible"] is True


def test_completed_report_is_streamed_into_operator_result(tmp_path: Path) -> None:
    report = tmp_path / "research_loop_20260712T120000Z.json"
    report_payload = {
        "candidate_stage_totals": {"finalists": 2, "generated": 40, "tested": 12, "walk_forward": 3},
        "cycles": [
            {
                "best_validation_candidate": {
                    "candidate_id": "momentum_01",
                    "family": "momentum_trend_filter",
                    "net_usdc_per_day": 0.2,
                    "profit_factor": 1.1,
                    "trade_count": 146,
                },
                "context_research": {"enabled": True},
                "exit_reason_summary": {"trade_count": 146},
                "full_training_metrics": {
                    "average_trade_usdc": 0.03,
                    "blindtest_days": 365,
                    "fees_usdc": 4.0,
                    "max_drawdown_usdc": 1.5,
                    "net_profit_usdc": 73.0,
                    "net_usdc_per_day": 0.1,
                    "profit_factor": 1.15,
                    "slippage_usdc": 2.0,
                    "trade_count": 365,
                    "training_days": 730,
                    "winrate": 0.52,
                },
                "quality_gate": {
                    "checks": [
                        {"code": "wfv_target", "passed": False},
                        {"code": "safety", "passed": True},
                    ],
                    "passed": False,
                },
                "qualified_finalists": 0,
                "rolling_origin_summary": {
                    "average_oos_net_usdc_per_day": 0.08,
                    "cost_load": 2.0,
                    "max_drawdown_usdc": 1.1,
                    "origin_count": 3,
                    "positive_origin_count": 2,
                    "trade_count": 300,
                    "worst_oos_net_usdc_per_day": -0.01,
                },
                "selected_candidate": {
                    "candidate_id": "momentum_01",
                    "family": "momentum_trend_filter",
                    "params": {},
                },
                "selected_candidate_score": {
                    "positive_fold_count": 4,
                    "quality_gate_passed": False,
                    "validation_net_usdc_per_day": 0.2,
                    "wfv_cost_load": 9.0,
                    "wfv_max_drawdown_usdc": 1.25,
                    "wfv_net_usdc_per_day": 0.15,
                    "wfv_profit_factor": 1.2,
                    "worst_fold_net_usdc_per_day": -0.02,
                },
                "wfv_summary": {
                    "aggregate_metrics": {
                        "average_trade_usdc": 0.025,
                        "blindtest_days": 365,
                        "fees_usdc": 6.0,
                        "max_drawdown_usdc": 1.25,
                        "net_profit_usdc": 81.9,
                        "net_usdc_per_day": 0.15,
                        "profit_factor": 1.2,
                        "slippage_usdc": 3.0,
                        "trade_count": 273,
                        "training_days": 730,
                        "winrate": 0.55,
                    },
                    "fold_count": 6,
                },
            }
        ],
        "cycles_executed": 1,
        "freeze_status": "blocked_by_quality_gates",
        "git_commit": "c4b9254",
        "loop_run_id": "research_loop_20260712T120000Z",
        "max_cycles": 8,
        "safety_status": "ok",
        "stop_reason": "selection_stagnation_3_cycles",
        "target_usdc_per_day": 3.0,
    }
    report.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")
    report.with_suffix(".txt").write_text(
        "\n".join(
            [
                "ETHUSDC Offline Research Loop - Protocol v2",
                "Loop-Run-ID: research_loop_20260712T120000Z",
                "Git commit: c4b9254",
                "Cycles executed: 1/8",
                "Stop reason: selection_stagnation_3_cycles",
                "Freeze status: blocked_by_quality_gates",
                "Cycle 1: generated=40 tested=12 walk_forward=3 finalists=2 best_validation={'candidate_id': 'momentum_01', 'family': 'momentum_trend_filter', 'net_usdc_per_day': 0.2, 'trade_count': 146, 'profit_factor': 1.1}",
            ]
        ),
        encoding="utf-8",
    )
    _checkpoint(tmp_path, status="completed", active_cycle=None, report_json=str(report))

    status = collect_backtest_display_status(tmp_path)
    final = status["final_summary"]

    assert status["mode"] == "completed"
    assert status["progress_pct"] == 100.0
    assert status["progress_visible"] is False
    assert final["selected_candidate"]["family"] == "momentum_trend_filter"
    assert final["wfv_net_usdc_per_day"] == 0.15
    assert final["wfv_trade_count"] == 273
    assert final["wfv_trades_per_day"] == 0.5
    assert final["wfv_fees_usdc"] == 6.0
    assert final["wfv_slippage_usdc"] == 3.0
    assert final["target_gap_usdc_per_day"] == -2.85
    assert final["validation_trades_per_day"] == 1.0
    assert final["full_training_trades_per_day"] == 0.5
    assert final["rolling_trades_per_day"] == round(300 / 1095, 10)
    assert final["quality_gate_failed_codes"] == ["wfv_target"]

    summary = format_backtest_summary_for_display(status)
    assert "ERGEBNIS DES ABGESCHLOSSENEN RESEARCH-BACKTESTS" in summary
    assert "0.150000 USDC" in summary
    assert "0.5000 pro Tag" in summary
    assert "Gebühren: 6.000000 USDC" in summary
    assert "Slippage: 3.000000 USDC" in summary
    assert "wfv_target" in summary
    assert "noch kein neuer versiegelter Final-Blindtest" in summary


def test_short_log_falls_back_to_checkpoint_paths(tmp_path: Path) -> None:
    _checkpoint(tmp_path)
    status = collect_backtest_display_status(tmp_path)

    text = format_backtest_log_for_display({**status, "recent_log_lines": []})

    assert "Checkpoint:" in text
    assert "Report:" in text


def test_malformed_checkpoint_fails_closed_without_crashing_ui(tmp_path: Path) -> None:
    path = tmp_path / "production_research_supervisor_bad.checkpoint.json"
    path.write_text("not json", encoding="utf-8")

    status = collect_backtest_display_status(tmp_path)

    assert status["mode"] == "idle"
    assert "Checkpoint nicht lesbar" in status["error"]
    assert status["audit_evaluated"] is False
    assert status["final_holdout_evaluated"] is False
