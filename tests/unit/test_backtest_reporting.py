"""Tests for the retained historical report formatter using synthetic results."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.reporting import write_backtest_report
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy
from ethusdc_bot.backtest.strategy_search import (
    TARGET_USDC_PER_DAY,
    StrategySearchResult,
)


def _candles(closes: list[float]) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Candle(
            open_time=int((start + timedelta(minutes=index)).timestamp() * 1000),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1,
        )
        for index, close in enumerate(closes)
    ]


def _synthetic_search(training_closes: list[float], blind_closes: list[float]) -> StrategySearchResult:
    candidate = StrategyCandidate(
        "breakout",
        {
            "lookback": 2,
            "threshold_bps": 1,
            "take_profit_bps": 80,
            "stop_loss_bps": 55,
            "max_hold_minutes": 25,
        },
    )
    training_candles = _candles(training_closes)
    blind_candles = _candles(blind_closes)
    training_result = simulate_strategy(training_candles, candidate, days=730)
    blind_result = simulate_strategy(blind_candles, candidate, days=365)
    reached = blind_result.metrics.net_usdc_per_day >= TARGET_USDC_PER_DAY
    return StrategySearchResult(
        candidates=[candidate],
        selected_candidate=candidate,
        training_results=[training_result],
        validation_result=training_result,
        blindtest_result=blind_result,
        training_metrics=training_result.metrics,
        blindtest_metrics=blind_result.metrics,
        target_reached=reached,
        target_status="target_reached" if reached else "target_not_reached",
        selection_source="synthetic_formatter_fixture",
        event_log=["synthetic_fixture_only"],
        training_candle_count=len(training_candles),
        blindtest_candle_count=len(blind_candles),
        strategy_families=[candidate.family],
    )


def test_report_contains_training_and_blindtest_separately(tmp_path):
    search = _synthetic_search([100, 101, 102, 103, 104, 105], [105, 104, 103])

    report = write_backtest_report(search, tmp_path, split_summary={"training_days": 730, "blindtest_days": 365})
    data = json.loads(report.json_path.read_text(encoding="utf-8"))

    assert "training" in data
    assert "blindtest" in data
    assert data["split"]["training_days"] == 730
    assert data["split"]["blindtest_days"] == 365


def test_report_contains_target_reached_or_not(tmp_path):
    search = _synthetic_search([100, 101, 102, 103, 104, 105], [100, 100, 100])

    report = write_backtest_report(search, tmp_path, split_summary={"training_days": 730, "blindtest_days": 365})
    text = report.txt_path.read_text(encoding="utf-8")

    assert "Ziel erreicht" in text or "Ziel nicht erreicht" in text


def test_report_contains_fees_and_slippage(tmp_path):
    search = _synthetic_search([100, 101, 102, 103, 104, 105], [105, 106, 107])

    report = write_backtest_report(search, tmp_path, split_summary={"training_days": 730, "blindtest_days": 365})
    data = json.loads(report.json_path.read_text(encoding="utf-8"))

    assert "fees_usdc" in data["blindtest"]["metrics"]
    assert "slippage_usdc" in data["blindtest"]["metrics"]


def test_report_contains_no_live_paper_testtrade_release(tmp_path):
    search = _synthetic_search([100, 101, 102, 103, 104, 105], [105, 106, 107])

    report = write_backtest_report(search, tmp_path, split_summary={"training_days": 730, "blindtest_days": 365})
    text = report.txt_path.read_text(encoding="utf-8").lower()
    data = json.loads(report.json_path.read_text(encoding="utf-8"))

    assert data["safety"]["live"] == "locked"
    assert data["safety"]["paper"] == "locked"
    assert data["safety"]["testtrade"] == "locked"
    assert "freigabe" not in text
    assert "unlocked" not in text


def test_report_has_no_fake_success_message(tmp_path):
    search = _synthetic_search([100, 100, 100, 100, 100, 100], [100, 100, 100])

    report = write_backtest_report(search, tmp_path, split_summary={"training_days": 730, "blindtest_days": 365})
    text = report.txt_path.read_text(encoding="utf-8")

    assert "garantiert" not in text.lower()
    assert "fake" not in text.lower()
    assert "Ziel erreicht" not in text or search.target_reached
