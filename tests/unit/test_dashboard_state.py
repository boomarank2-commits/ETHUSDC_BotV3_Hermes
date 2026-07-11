"""Local dashboard state tests.

The dashboard state is status-only. It must not create repository data folders,
reports, API key files, trades, candidates, or backtest results.
"""

from pathlib import Path

from ethusdc_bot.ui import dashboard_state


FORBIDDEN_SNAPSHOT_FIELDS = {
    "profit_usdc",
    "net_usdc_per_day",
    "winrate",
    "profit_factor",
    "trade_count",
    "trades",
    "real_trades",
    "backtest_run_id",
    "candidate_adoptable",
    "adopted_candidate",
    "best_candidate",
    "candidate",
}


def test_project_status_contains_required_contract_values():
    status = dashboard_state.collect_project_status()

    assert status["symbol"] == "ETHUSDC"
    assert status["quote_asset"] == "USDC"
    assert status["exchange"] == "Binance"
    assert status["market_type"] == "Spot"
    assert status["position_mode"] == "LONG-only"
    assert status["start_capital_usdc"] == 100
    assert status["fixed_lot_notional_usdc"] == 100
    assert status["training_days"] == 730
    assert status["blindtest_days"] == 365
    assert status["required_utc_days"] == 1095
    assert status["future_goal"] == (
        "about 3 USDC/day after costs as a guideline, not a guarantee"
    )


def test_safety_status_keeps_trading_modes_locked():
    status = dashboard_state.collect_safety_status()

    assert status["live"] == "locked"
    assert status["paper"] == "locked"
    assert status["testtrade"] == "locked"
    assert status["shorts_margin_futures_leverage"] == "forbidden"


def test_count_download_files_counts_zip_checksum_and_last_ten(tmp_path):
    download_dir = tmp_path / "raw/binance/spot/ETHUSDC/klines/1m"
    download_dir.mkdir(parents=True)
    for day in range(1, 13):
        (download_dir / f"ETHUSDC-1m-2024-01-{day:02d}.zip").write_bytes(b"zip")
    for day in range(1, 4):
        (download_dir / f"ETHUSDC-1m-2024-01-{day:02d}.zip.CHECKSUM").write_text(
            "checksum\n", encoding="utf-8"
        )

    status = dashboard_state.count_download_files(download_dir)

    assert status["zip_count"] == 12
    assert status["checksum_count"] == 3
    assert len(status["last_10_files"]) == 10
    assert status["expected_zip_count_for_1095_days"] == 1095
    assert status["quality_claim"] == "not_audited"


def test_build_snapshot_has_no_profit_backtest_trade_or_candidate_fields(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)

    assert FORBIDDEN_SNAPSHOT_FIELDS.isdisjoint(snapshot)
    assert FORBIDDEN_SNAPSHOT_FIELDS.isdisjoint(snapshot["project_status"])
    assert FORBIDDEN_SNAPSHOT_FIELDS.isdisjoint(snapshot["download_folder_status"])
    assert FORBIDDEN_SNAPSHOT_FIELDS.isdisjoint(snapshot["kline_audit_status"])
    assert FORBIDDEN_SNAPSHOT_FIELDS.isdisjoint(snapshot["data_readiness_report"])
    assert FORBIDDEN_SNAPSHOT_FIELDS.isdisjoint(snapshot["data_prep_status"])
    assert "backtest_start_button" in snapshot["ui_status"]
    assert "enabled" in snapshot["ui_status"]["backtest_start_button"]


def test_build_snapshot_contains_kline_audit_fields(tmp_path, monkeypatch):
    from ethusdc_bot.data_pipeline import kline_zip_audit

    monkeypatch.setattr(kline_zip_audit, "DEFAULT_ALLOWED_RAW_ROOT", tmp_path)

    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    audit_status = snapshot["kline_audit_status"]

    assert audit_status["zip_count"] == 0
    assert audit_status["checksum_count"] == 0
    assert audit_status["audit_status"] == "not_audited"
    assert audit_status["observed_start_utc"] is None
    assert audit_status["observed_end_utc"] is None
    assert audit_status["observed_rows"] == 0
    assert audit_status["complete_utc_days"] == 0
    assert audit_status["missing_utc_days_count"] == 0
    assert audit_status["duplicate_rows"] == 0
    assert audit_status["gap_count"] == 0
    assert audit_status["max_gap_seconds"] == 0
    assert audit_status["backtest_ready"] is False


def test_build_snapshot_contains_data_readiness_report(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    report = snapshot["data_readiness_report"]

    assert report["overall_status"] in {"blocked", "ready"}
    assert "backtest_window" in report
    assert "requirements_by_id" in report
    assert "ethusdc_klines_1m" in report["requirements_by_id"]
    assert "btcusdc_klines_1m" in report["requirements_by_id"]
    assert "ethbtc_klines_1m" in report["requirements_by_id"]
    assert "ethusdc_aggtrades" in report["requirements_by_id"]
    assert "ethusdc_trades" in report["requirements_by_id"]
    assert "ethusdc_bookticker_live" in report["requirements_by_id"]
    assert report["backtest_button_enabled"] is False
    assert report["backtest_engine_implemented"] is False


def test_build_snapshot_contains_last_run_status_and_refresh_preserves_supplied_last_run(tmp_path):
    last_run = dashboard_state.build_initial_data_prep_last_run_status()
    last_run.update(
        {
            "last_run_status": "finished",
            "last_run_mode": "dry_run",
            "last_run_readiness_before": "blocked",
            "last_run_readiness_after": "blocked",
            "last_run_next_blocker": "Backtest engine is not implemented",
            "last_run_summary_text": "Letzter Datenlauf fertig. Readiness bleibt blocked wegen: Backtest engine is not implemented",
        }
    )

    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path, data_prep_last_run_status=last_run)
    refreshed = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path, data_prep_last_run_status=snapshot["data_prep_last_run_status"])

    assert snapshot["data_prep_last_run_status"]["last_run_status"] == "finished"
    assert refreshed["data_prep_last_run_status"]["last_run_status"] == "finished"
    assert refreshed["data_prep_last_run_status"]["last_run_next_blocker"] == "Backtest engine is not implemented"


def test_build_snapshot_with_existing_files_has_overall_data_progress(tmp_path, monkeypatch):
    download_dir = tmp_path / "raw/binance/spot/ETHUSDC/klines/1m"
    download_dir.mkdir(parents=True)
    for day in range(1, 4):
        (download_dir / f"ETHUSDC-1m-2026-07-0{day}.zip").write_bytes(b"zip")
        (download_dir / f"ETHUSDC-1m-2026-07-0{day}.zip.CHECKSUM").write_text("checksum\n", encoding="utf-8")

    from ethusdc_bot.data_pipeline import kline_zip_audit
    monkeypatch.setattr(kline_zip_audit, "DEFAULT_ALLOWED_RAW_ROOT", tmp_path)

    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)

    assert snapshot["overall_data_progress_pct"] > 0
    assert snapshot["current_run_progress_pct"] == 0
    assert snapshot["data_prep_progress_pct"] == snapshot["overall_data_progress_pct"]


def test_idle_runtime_zero_does_not_overwrite_overall_data_progress(tmp_path, monkeypatch):
    download_dir = tmp_path / "raw/binance/spot/ETHUSDC/klines/1m"
    download_dir.mkdir(parents=True)
    (download_dir / "ETHUSDC-1m-2026-07-01.zip").write_bytes(b"zip")
    (download_dir / "ETHUSDC-1m-2026-07-01.zip.CHECKSUM").write_text("checksum\n", encoding="utf-8")

    from ethusdc_bot.data_pipeline import kline_zip_audit
    monkeypatch.setattr(kline_zip_audit, "DEFAULT_ALLOWED_RAW_ROOT", tmp_path)

    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    refreshed = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path, data_prep_last_run_status=snapshot["data_prep_last_run_status"])

    assert snapshot["data_prep_runtime_status"]["progress_pct"] == 0
    assert refreshed["overall_data_progress_pct"] == snapshot["overall_data_progress_pct"]
    assert refreshed["data_prep_progress_pct"] == snapshot["overall_data_progress_pct"]

def test_format_snapshot_for_display_contains_last_data_prep_run(tmp_path):
    last_run = dashboard_state.build_initial_data_prep_last_run_status()
    last_run.update(
        {
            "last_run_status": "finished",
            "last_run_mode": "execute",
            "last_run_readiness_before": "blocked",
            "last_run_readiness_after": "blocked",
            "last_run_next_blocker": "bookTicker live collector is missing",
            "last_run_summary_text": "Letzter Datenlauf fertig. Readiness bleibt blocked wegen: bookTicker live collector is missing",
        }
    )
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path, data_prep_last_run_status=last_run)
    text = dashboard_state.format_snapshot_for_display(snapshot)

    assert "Last Data Prep Run" in text
    assert "Last status: finished" in text
    assert "Last readiness before/after: blocked -> blocked" in text
    assert "Last next blocker: bookTicker live collector is missing" in text


def test_build_operator_data_status_rows_are_short_and_user_facing(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)

    rows = snapshot["operator_data_status_rows"]
    labels = [row["label"] for row in rows]

    assert labels == ["ETHUSDC 1m", "BTCUSDC 1m", "ETHBTC 1m", "ETHUSDC aggTrades", "ETHUSDC trades"]
    assert all(row["status"] in {"fehlt", "teilweise", "vollständig", "wird geladen"} for row in rows)
    assert all("files_text" in row for row in rows)


def test_format_operator_summary_is_concise_and_hides_raw_readiness_lists(tmp_path):
    last_run = dashboard_state.build_initial_data_prep_last_run_status()
    last_run.update(
        {
            "last_run_status": "finished",
            "last_run_mode": "dry_run",
            "last_run_summary_text": "Prüfung fertig. Keine Downloads ausgeführt.",
            "last_run_next_blocker": "ETHUSDC 1m fehlt ein Tag",
        }
    )
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path, data_prep_last_run_status=last_run)

    text = dashboard_state.format_operator_summary_for_display(snapshot)

    assert "ETHUSDC Bot V3 Hermes" in text
    assert "Bot-Status:" in text
    assert "Datenstatus:" in text
    assert "Gesamtfortschritt:" in text
    assert "Aktueller Lauf:" in text
    assert "Nächster Blocker: ETHUSDC 1m fehlt ein Tag" in text
    assert "requirements_by_id" not in text
    assert "available_days" not in text
    assert "Project Status:" not in text


def test_build_snapshot_contains_runtime_data_prep_status_and_blockers(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)

    assert snapshot["data_prep_runtime_status"]["phase"] == "idle"
    assert snapshot["data_prep_progress_pct"] == 0
    assert snapshot["data_prep_current_task"] is None
    assert snapshot["data_prep_mode"] == "dry_run"
    assert snapshot["can_start_data_prep"] is True
    assert snapshot["can_start_backtest_engine"] is False
    assert "backtest_status" in snapshot
    assert "bot_current_status_text" in snapshot


def test_build_snapshot_contains_wired_training_wfv_button_but_missing_data_blocks_it(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    prep = snapshot["data_prep_status"]
    button = snapshot["ui_status"]["backtest_start_button"]

    assert prep["engine_start_locked"] is True
    assert prep["supported_download_task_count"] >= 5
    assert prep["unsupported_task_count"] >= 1
    assert prep["live_collector_task_count"] >= 2
    assert button["visible"] is True
    assert button["action"] == "training_validation_wfv_protocol_v2"
    assert button["enabled"] is False
    assert button["engine_locked"] is True
    assert button["final_holdout_evaluated"] is False
    assert button["uses_trading_api"] is False
    assert button["live_paper_testtrade_locked"] is True


def test_format_snapshot_for_display_contains_honest_backtest_and_shadow_status(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    text = dashboard_state.format_snapshot_for_display(snapshot)

    assert "ETHUSDC" in text
    assert "Live: locked" in text
    assert "Backtest Data Readiness:" in text
    assert "Protocol-v2 training/validation/WFV is wired" in text
    assert "sealed final evaluation remains separate" in text
    assert "Data Audit Status:" in text
    assert "Audit status: not_audited" in text
    assert "not_audited" in text
    assert "profit_usdc" not in text
    assert "Final evaluation: {'status': 'not_found'" in text


def test_snapshot_exposes_fixed_lot_budget_and_order_free_shadow_controls(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(
        Path.cwd(), tmp_path, deployment_budget_usdc=500
    )

    portfolio = snapshot["portfolio_status"]
    adopt = snapshot["ui_status"]["shadow_adopt_button"]
    shadow = snapshot["shadow_runtime_status"]
    assert portfolio["deployment_budget_usdc"] == 500
    assert portfolio["lot_notional_usdc"] == 100.0
    assert portfolio["max_concurrent_lots"] == 5
    assert portfolio["compounding_enabled"] is False
    assert adopt["enabled"] is False
    assert adopt["orders_enabled"] is False
    assert adopt["trading_api_enabled"] is False
    assert adopt["live_enabled"] is False
    assert shadow["status"] == "not_adopted"
    assert shadow["orders_enabled"] is False


def test_final_status_is_read_only_and_reports_no_final_evaluation(tmp_path):
    before = list(tmp_path.rglob("*"))

    status = dashboard_state.collect_final_evaluation_status(tmp_path / "final")

    assert status["status"] == "not_found"
    assert status["color"] == "none"
    assert status["shadow_eligible"] is False
    assert list(tmp_path.rglob("*")) == before
