from __future__ import annotations

from pathlib import Path

from ethusdc_bot.ui import operator_dashboard as dashboard


def test_refresh_gate_waits_until_payload_is_applied() -> None:
    gate = dashboard.RefreshGate()

    first = gate.begin()

    assert first == 1
    assert gate.begin() is None
    assert gate.finish(999) is False
    assert gate.pending is True
    assert gate.finish(first) is True
    assert gate.pending is False
    assert gate.begin() == 2


def test_select_operator_view_uses_one_context_only() -> None:
    assert (
        dashboard.select_operator_view(
            data_running=True, backtest_mode="completed", runtime_phase="downloading"
        )
        == "download"
    )
    assert (
        dashboard.select_operator_view(
            data_running=False, backtest_mode="running", runtime_phase="idle"
        )
        == "backtest_running"
    )
    assert (
        dashboard.select_operator_view(
            data_running=False, backtest_mode="completed", runtime_phase="idle"
        )
        == "backtest_result"
    )


def test_stale_checkpoint_is_exposed_as_interrupted(monkeypatch) -> None:
    monkeypatch.setattr(dashboard, "_run_lock_is_owned", lambda _root: False)

    result = dashboard.normalise_stale_backtest_status(
        {
            "mode": "running",
            "checkpoint_path": "checkpoint.json",
            "status_text": "Backtest läuft",
            "progress_visible": True,
        },
        "reports",
    )

    assert result["mode"] == "interrupted"
    assert result["progress_visible"] is False
    assert result["stale_checkpoint"] is True
    assert result["error"] == "stale_checkpoint_without_active_run_lock"


def test_owned_run_lock_keeps_checkpoint_active(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard,
        "_ORIGINAL_ACTIVE_CHECKPOINT_DISCOVERY",
        lambda _root: {"status": "running", "run_id": "run-1"},
    )
    monkeypatch.setattr(dashboard, "_run_lock_is_owned", lambda _root: True)

    result = dashboard.discover_active_research_checkpoint_lock_aware("reports")

    assert result == {"status": "running", "run_id": "run-1"}


def test_stale_run_lock_file_does_not_block_checkpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard,
        "_ORIGINAL_ACTIVE_CHECKPOINT_DISCOVERY",
        lambda _root: {"status": "running", "run_id": "run-1"},
    )
    monkeypatch.setattr(dashboard, "_run_lock_is_owned", lambda _root: False)

    assert dashboard.discover_active_research_checkpoint_lock_aware("reports") is None


def test_compact_report_change_invalidates_discovery_cache(
    tmp_path: Path, monkeypatch
) -> None:
    report = tmp_path / "research.json"
    report.write_text("{}", encoding="utf-8")
    resolved = str(report.resolve())
    stale_key = (resolved, 2, report.stat().st_mtime_ns)
    dashboard._final_evaluation_controller._DISCOVERY_CACHE.clear()
    dashboard._final_evaluation_controller._DISCOVERY_CACHE[stale_key] = None
    dashboard._COMPACT_DISCOVERY_STAMPS.clear()
    observed_cache_sizes: list[int] = []

    def fake_reader(_path: Path):
        observed_cache_sizes.append(
            sum(
                1
                for key in dashboard._final_evaluation_controller._DISCOVERY_CACHE
                if key[0] == resolved
            )
        )
        return {"freeze_status": "frozen_for_separate_sealed_holdout"}

    monkeypatch.setattr(
        dashboard, "_ORIGINAL_RESEARCH_DISCOVERY_READER", fake_reader
    )

    dashboard.read_research_discovery_fields_compact_aware(report)
    dashboard._final_evaluation_controller._DISCOVERY_CACHE[stale_key] = None
    report.with_suffix(".txt").write_text(
        "Freeze status: frozen_for_separate_sealed_holdout\n", encoding="utf-8"
    )
    dashboard.read_research_discovery_fields_compact_aware(report)

    assert observed_cache_sizes == [0, 0]


def test_download_view_contains_progress_tasks_files_audit_and_time() -> None:
    text = dashboard.format_download_view(
        {
            "data_readiness_report": {"overall_status": "blocked"},
            "kline_audit_status": {
                "audit_status": "partial",
                "observed_start_utc": "2024-01-01",
                "observed_end_utc": "2026-07-07",
                "complete_utc_days": 900,
                "missing_utc_days_count": 10,
                "duplicate_rows": 2,
                "gap_count": 3,
                "max_gap_seconds": 120,
                "backtest_ready": False,
            },
            "data_prep_status": {
                "supported_download_task_count": 5,
                "unsupported_task_count": 1,
                "live_collector_task_count": 2,
            },
            "inventory_status": {"local_root": "C:/TradingBot/data"},
            "operator_data_status_rows": [
                {
                    "label": "ETHUSDC 1m",
                    "files_text": "900/1095",
                    "status": "teilweise",
                    "reason": "195 Tage fehlen",
                }
            ],
            "overall_data_progress_pct": 82.19,
            "backtest_blocker_summary": "Daten fehlen",
        },
        {
            "phase": "downloading",
            "mode": "execute",
            "progress_pct": 42,
            "elapsed_seconds": 3661,
            "started_at": "2026-07-12T20:00:00Z",
            "last_message": "läuft",
            "current_step": "download",
            "current_task_id": "ethusdc_klines_1m",
            "current_symbol": "ETHUSDC",
            "current_data_type": "klines_1m",
            "current_file_name": "2026-01-01.zip",
            "current_file_index": 3,
            "planned_file_count": 10,
            "completed_tasks": 2,
            "total_tasks": 5,
            "skipped_tasks": 1,
            "failed_tasks": 0,
            "completed_file_count": 3,
            "downloaded_file_count": 2,
            "skipped_file_count": 1,
            "failed_file_count": 0,
        },
        {
            "last_run_status": "running",
            "last_run_mode": "execute",
            "last_run_duration_seconds": 3661,
            "last_run_readiness_before": "blocked",
            "last_run_readiness_after": None,
            "last_run_summary_text": "Datenlauf läuft",
            "last_run_next_blocker": "noch aktiv",
            "error": None,
        },
    )

    assert "Fortschritt: 42.0 %" in text
    assert "TASKS UND DATEIEN" in text
    assert "QUALITÄTSPRÜFUNG" in text
    assert "Laufzeit: 01:01:01" in text
    assert "ETHUSDC 1m" in text


def test_running_backtest_view_contains_one_to_hundred_progress_and_metrics() -> None:
    text = dashboard.format_running_backtest_view(
        {
            "status_text": "Backtest läuft",
            "progress_pct": 37.5,
            "completed_cycles": 3,
            "max_cycles": 8,
            "active_cycle": 4,
            "elapsed_seconds": 7200,
            "started_at_utc": "2026-07-12T18:00:00Z",
            "updated_at_utc": "2026-07-12T20:00:00Z",
            "run_id": "run-1",
            "git_branch": "branch",
            "git_commit": "abcdef",
            "latest_cycle": {
                "cycle": 3,
                "maximum": 8,
                "generated": 40,
                "tested": 12,
                "walk_forward": 3,
                "finalists": 2,
                "wfv_net_usdc_per_day": 0.5,
                "validation_net_usdc_per_day": 0.7,
                "wfv_profit_factor": 1.2,
                "wfv_max_drawdown_usdc": 4.0,
                "worst_fold_net_usdc_per_day": -0.1,
                "positive_fold_count": 4,
                "walk_forward_folds": 6,
                "wfv_cost_load": 8.0,
                "quality_gate_passed": False,
                "context_enabled": True,
                "context_generated": 6,
                "context_tested": 2,
            },
            "context_enabled": True,
            "audit_evaluated": False,
            "final_holdout_evaluated": False,
        }
    )

    assert "Fortschritt: 37.5 %" in text
    assert "40 erzeugt / 12 getestet / 3 Walk-Forward / 2 Finalisten" in text
    assert "WFV netto pro Tag" in text
    assert "Live / Paper / Testtrade / Orders bleiben gesperrt" in text


def test_completed_backtest_view_contains_core_result_sections() -> None:
    text = dashboard.format_backtest_result_view(
        {
            "mode": "completed",
            "run_id": "run-1",
            "git_branch": "branch",
            "git_commit": "abcdef",
            "elapsed_seconds": 3600,
            "report_path": "report.json",
            "audit_evaluated": False,
            "final_holdout_evaluated": False,
            "final_summary": {
                "cycles_executed": 8,
                "max_cycles": 8,
                "stop_reason": "max_cycles",
                "freeze_status": "blocked_no_qualified_finalist",
                "selected_candidate": {
                    "candidate_id": "candidate-1",
                    "family": "momentum",
                    "params": {"lookback": 20},
                },
                "wfv_net_usdc_per_day": 0.5,
                "target_usdc_per_day": 3.0,
                "target_gap_usdc_per_day": -2.5,
                "wfv_net_profit_usdc": 273.0,
                "wfv_trade_count": 50,
                "wfv_trades_per_day": 0.09,
                "wfv_profit_factor": 1.3,
                "wfv_winrate": 0.52,
                "wfv_average_trade_usdc": 0.1,
                "wfv_max_drawdown_usdc": 5.0,
                "wfv_worst_fold_net_usdc_per_day": -0.2,
                "wfv_positive_fold_count": 4,
                "wfv_fees_usdc": 4.0,
                "wfv_slippage_usdc": 2.0,
                "wfv_cost_load_usdc": 6.0,
                "best_validation": {"net_usdc_per_day": 0.7, "trade_count": 20},
                "full_training": {"net_usdc_per_day": 0.8, "trade_count": 80},
                "rolling": {
                    "average_oos_net_usdc_per_day": 0.4,
                    "worst_oos_net_usdc_per_day": -0.1,
                    "positive_origin_count": 2,
                    "origin_count": 3,
                },
                "quality_gate_passed": False,
                "quality_gate_failed_codes": ["activity_floor"],
                "qualified_finalists": 0,
                "context_enabled": True,
                "candidate_stage_totals": {"generated": 320},
                "exit_summary": {"take_profit": 10},
            },
        }
    )

    assert "AUSGEWÄHLTER KANDIDAT" in text
    assert "WALK-FORWARD-ERGEBNIS" in text
    assert "VALIDATION" in text
    assert "VOLLES TRAINING" in text
    assert "ROLLING ORIGINS / ROBUSTHEIT" in text
    assert "QUALITY GATES UND DIAGNOSE" in text
    assert "SICHERHEIT / NÄCHSTER SCHRITT" in text
    assert "activity_floor" in text
