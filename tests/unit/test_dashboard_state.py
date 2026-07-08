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
    assert status["training_days"] == 730
    assert status["blindtest_days"] == 365
    assert status["required_utc_days"] == 1095
    assert status["future_goal"] == ">= 3 USDC/day after realistic blindtest"


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
    assert snapshot["ui_status"]["backtest_start_button"]["enabled"] is True


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


def test_build_snapshot_contains_runtime_data_prep_status_and_blockers(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)

    assert snapshot["data_prep_runtime_status"]["phase"] == "idle"
    assert snapshot["data_prep_progress_pct"] == 0
    assert snapshot["data_prep_current_task"] is None
    assert snapshot["data_prep_mode"] == "dry_run"
    assert snapshot["can_start_data_prep"] is True
    assert snapshot["can_start_backtest_engine"] is False
    assert "Backtest engine" in snapshot["backtest_blocker_summary"]
    assert "bot_current_status_text" in snapshot


def test_build_snapshot_contains_data_prep_and_clickable_backtest_start_button(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    prep = snapshot["data_prep_status"]
    button = snapshot["ui_status"]["backtest_start_button"]

    assert prep["engine_start_locked"] is True
    assert prep["supported_download_task_count"] >= 5
    assert prep["unsupported_task_count"] >= 1
    assert prep["live_collector_task_count"] >= 2
    assert button == {
        "visible": True,
        "enabled": True,
        "action": "data_preparation_only",
        "engine_locked": True,
        "hint": "Backtest start currently prepares data only. Real engine is not implemented yet.",
    }


def test_format_snapshot_for_display_contains_status_without_backtest_claims(tmp_path):
    snapshot = dashboard_state.build_dashboard_snapshot(Path.cwd(), tmp_path)
    text = dashboard_state.format_snapshot_for_display(snapshot)

    assert "ETHUSDC" in text
    assert "Live: locked" in text
    assert "Backtest Data Readiness:" in text
    assert "Backtest start currently runs data preparation only. Real engine start is still locked." in text
    assert "Backtest waits for data readiness and real engine implementation. No fake result." in text
    assert "Data Audit Status:" in text
    assert "Audit status: not_audited" in text
    assert "not_audited" in text
    assert "profit_usdc" not in text
    assert "net_usdc_per_day" not in text
