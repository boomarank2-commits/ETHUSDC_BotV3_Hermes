"""Backtest data readiness gate tests."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from ethusdc_bot.data_pipeline.data_readiness import (
    build_backtest_start_data_gate,
    build_data_readiness_report,
    build_expected_backtest_window,
    compute_rolling_utc_window,
    list_missing_download_tasks,
    list_outdated_download_tasks,
)
from ethusdc_bot.data_pipeline.data_requirements import build_backtest_data_requirements, get_requirement_by_id


FORBIDDEN_RESULT_FIELDS = {
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


def _kline_dir(root: Path, symbol: str) -> Path:
    return root / "raw" / "binance" / "spot" / symbol / "klines" / "1m"


def _write_daily_zip_names(root: Path, symbol: str, start: date, days: int) -> None:
    directory = _kline_dir(root, symbol)
    directory.mkdir(parents=True, exist_ok=True)
    for offset in range(days):
        day = start + timedelta(days=offset)
        (directory / f"{symbol}-1m-{day.isoformat()}.zip").write_bytes(b"placeholder")
        (directory / f"{symbol}-1m-{day.isoformat()}.zip.CHECKSUM").write_text("checksum\n", encoding="utf-8")


def _write_daily_data_names(root: Path, symbol: str, data_type: str, start: date, days: int) -> None:
    directory = root / "raw" / "binance" / "spot" / symbol / data_type
    directory.mkdir(parents=True, exist_ok=True)
    for offset in range(days):
        day = start + timedelta(days=offset)
        (directory / f"{symbol}-{data_type}-{day.isoformat()}.zip").write_bytes(b"placeholder")


def test_rolling_window_uses_latest_available_day_and_has_exactly_1095_days():
    window = compute_rolling_utc_window(available_data_end=date(2026, 7, 6), required_days=1095)

    assert window["data_start"] == "2023-07-08"
    assert window["data_end"] == "2026-07-06"
    assert window["days"] == 1095


def test_expected_backtest_window_splits_training_730_and_blind_365():
    window = build_expected_backtest_window(date(2026, 7, 6), required_days=1095)

    assert window["data_start"] == "2023-07-08"
    assert window["data_end"] == "2026-07-06"
    assert window["training_start"] == "2023-07-08"
    assert window["training_end"] == "2025-07-06"
    assert window["training_days"] == 730
    assert window["blind_start"] == "2025-07-07"
    assert window["blind_end"] == "2026-07-06"
    assert window["blind_days"] == 365


def test_missing_ethusdc_klines_block_backtest(tmp_path):
    gate = build_backtest_start_data_gate(tmp_path, reference_date=date(2026, 7, 8))

    eth = gate["requirements_by_id"]["ethusdc_klines_1m"]
    assert eth["status"] == "missing"
    assert eth["blocking_backtest"] is True
    assert gate["data_gate_ready"] is False
    assert gate["backtest_button_enabled"] is False


def test_1094_of_1095_ethusdc_days_block_backtest(tmp_path):
    _write_daily_zip_names(tmp_path, "ETHUSDC", date(2023, 7, 9), 1094)

    gate = build_backtest_start_data_gate(tmp_path, reference_date=date(2026, 7, 8))
    eth = gate["requirements_by_id"]["ethusdc_klines_1m"]

    assert eth["available_days"] == 1094
    assert eth["status"] == "partial"
    assert eth["blocking_backtest"] is True
    assert gate["data_gate_ready"] is False


def test_1095_ethusdc_days_allow_data_gate_but_not_backtest_without_engine(tmp_path):
    _write_daily_zip_names(tmp_path, "ETHUSDC", date(2023, 7, 8), 1095)

    gate = build_backtest_start_data_gate(tmp_path, reference_date=date(2026, 7, 8))
    eth = gate["requirements_by_id"]["ethusdc_klines_1m"]

    assert eth["available_days"] == 1095
    assert eth["status"] == "current"
    assert eth["blocking_backtest"] is False
    assert gate["data_gate_ready"] is True
    assert gate["backtest_engine_implemented"] is False
    assert gate["backtest_button_enabled"] is False


def test_data_older_than_7_days_requires_update(tmp_path):
    _write_daily_zip_names(tmp_path, "ETHUSDC", date(2023, 6, 30), 1095)

    report = build_data_readiness_report(tmp_path, reference_date=date(2026, 7, 8))
    eth = report["requirements_by_id"]["ethusdc_klines_1m"]
    outdated = list_outdated_download_tasks(report, max_age_days=7)

    assert eth["status"] == "outdated"
    assert eth["update_required"] is True
    assert any(task["requirement_id"] == "ethusdc_klines_1m" for task in outdated)


def test_missing_context_data_is_shown_but_cannot_confirm_positive_candidate(tmp_path):
    _write_daily_zip_names(tmp_path, "ETHUSDC", date(2023, 7, 8), 1095)

    report = build_data_readiness_report(tmp_path, reference_date=date(2026, 7, 8))
    btc = report["requirements_by_id"]["btcusdc_klines_1m"]
    ethbtc = report["requirements_by_id"]["ethbtc_klines_1m"]

    for status in [btc, ethbtc]:
        assert status["status"] == "missing"
        assert status["context_only"] is True
        assert status["blocking_backtest"] is False
        assert status["positive_candidate_influence_allowed"] is False


def test_live_data_under_30_days_remains_diagnostic_only(tmp_path):
    live_dir = tmp_path / "raw" / "binance" / "spot" / "ETHUSDC" / "bookTicker"
    live_dir.mkdir(parents=True)
    for offset in range(5):
        day = date(2026, 7, 1) + timedelta(days=offset)
        (live_dir / f"ETHUSDC-bookTicker-{day.isoformat()}.jsonl").write_text("{}\n", encoding="utf-8")

    report = build_data_readiness_report(tmp_path, reference_date=date(2026, 7, 8))
    bookticker = report["requirements_by_id"]["ethusdc_bookticker_live"]

    assert bookticker["available_days"] == 5
    assert bookticker["status"] == "diagnostic_only"
    assert bookticker["included_in_backtest"] is False
    assert bookticker["diagnostic_only"] is True
    assert bookticker["positive_candidate_influence_allowed"] is False


def test_missing_download_tasks_include_klines_and_tradeflow_but_live_tasks_are_collectors(tmp_path):
    report = build_data_readiness_report(tmp_path, reference_date=date(2026, 7, 8))
    tasks = list_missing_download_tasks(report)
    by_id = {task["task_id"]: task for task in tasks}

    assert by_id["download_ethusdc_klines_1m"]["source_kind"] == "public_binance_data"
    assert by_id["download_btcusdc_klines_1m"]["execute_allowed"] is True
    assert by_id["download_ethbtc_klines_1m"]["execute_allowed"] is True
    assert by_id["download_ethusdc_aggtrades"]["execute_allowed"] is True
    assert by_id["download_ethusdc_trades"]["execute_allowed"] is True
    assert by_id["collect_ethusdc_bookticker_live"]["source_kind"] == "live_collection"
    assert by_id["collect_ethusdc_orderbook_snapshots_live"]["execute_allowed"] is False


def test_readiness_report_has_no_profit_trade_candidate_or_backtest_result_fields(tmp_path):
    report = build_data_readiness_report(tmp_path, reference_date=date(2026, 7, 8))

    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(report)
    for status in report["requirements"]:
        assert FORBIDDEN_RESULT_FIELDS.isdisjoint(status)
