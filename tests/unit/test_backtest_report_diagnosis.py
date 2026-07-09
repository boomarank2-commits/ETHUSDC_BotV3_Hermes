"""Tests for diagnosing completed backtest reports honestly."""

from pathlib import Path

from ethusdc_bot.backtest.report_diagnosis import diagnose_backtest_report, format_diagnosis_text

REPORT = Path("reports/backtests/bt_20260709T151036Z.json")


def test_report_diagnosis_reads_existing_backtest_report():
    diagnosis = diagnose_backtest_report(REPORT)

    assert diagnosis["run_id"] == "bt_20260709T151036Z"
    assert diagnosis["symbol"] == "ETHUSDC"
    assert diagnosis["diagnosis_status"] == "completed"


def test_diagnosis_detects_target_not_reached_and_negative_windows():
    diagnosis = diagnose_backtest_report(REPORT)

    assert diagnosis["target_reached"] is False
    assert diagnosis["findings"]["training_negative"] is True
    assert diagnosis["findings"]["blindtest_negative"] is True
    assert diagnosis["summary"] == "Ziel nicht erreicht; Training und Blindtest waren negativ."


def test_diagnosis_flags_profit_factor_winrate_costs_overtrading_and_drawdown():
    diagnosis = diagnose_backtest_report(REPORT)
    findings = diagnosis["findings"]

    assert findings["profit_factor_below_one"] is True
    assert findings["winrate_low"] is True
    assert findings["cost_load_high"] is True
    assert findings["overtrading_suspected"] is True
    assert findings["drawdown_high"] is True
    assert findings["no_edge_indicated"] is True


def test_diagnosis_text_is_honest_not_prescriptive():
    text = format_diagnosis_text(diagnose_backtest_report(REPORT))

    assert "Ziel nicht erreicht" in text
    assert "keine belastbare Edge" in text
    assert "sicher" not in text.lower()
