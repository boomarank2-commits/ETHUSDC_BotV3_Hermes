"""Pure data audit rule tests using artificial kline records only."""

from ethusdc_bot.data_pipeline.audit import audit_kline_records


def kline(open_time_utc, symbol="ETHUSDC", interval_seconds=60):
    return {
        "symbol": symbol,
        "open_time_utc": open_time_utc,
        "interval_seconds": interval_seconds,
    }


def test_ethusdc_1m_kline_audit_marks_clean_artificial_data_usable():
    result = audit_kline_records(
        [kline(1_700_000_000), kline(1_700_000_060), kline(1_700_000_120)],
        symbol="ETHUSDC",
        interval_seconds=60,
    )

    assert result["symbol_validated"] is True
    assert result["interval_validated"] is True
    assert result["sorted_ascending"] is True
    assert result["has_gaps"] is False
    assert result["gap_count"] == 0
    assert result["max_gap_seconds"] == 0
    assert result["duplicate_rows"] == 0
    assert result["quality_status"] == "usable"


def test_kline_audit_detects_duplicate_open_times():
    result = audit_kline_records(
        [kline(1_700_000_000), kline(1_700_000_000)],
        symbol="ETHUSDC",
        interval_seconds=60,
    )

    assert result["duplicate_rows"] == 1
    assert result["quality_status"] == "blocked"


def test_kline_audit_detects_unsorted_timestamps():
    result = audit_kline_records(
        [kline(1_700_000_060), kline(1_700_000_000)],
        symbol="ETHUSDC",
        interval_seconds=60,
    )

    assert result["sorted_ascending"] is False
    assert result["quality_status"] == "blocked"


def test_kline_audit_detects_gaps():
    result = audit_kline_records(
        [kline(1_700_000_000), kline(1_700_000_120), kline(1_700_000_180)],
        symbol="ETHUSDC",
        interval_seconds=60,
    )

    assert result["has_gaps"] is True
    assert result["gap_count"] == 1
    assert result["max_gap_seconds"] == 120
    assert result["quality_status"] == "incomplete"


def test_kline_audit_rejects_wrong_symbol():
    result = audit_kline_records(
        [kline(1_700_000_000, symbol="BTCUSDC")],
        symbol="ETHUSDC",
        interval_seconds=60,
    )

    assert result["symbol_validated"] is False
    assert result["quality_status"] == "blocked"


def test_kline_audit_rejects_wrong_interval():
    result = audit_kline_records(
        [kline(1_700_000_000, interval_seconds=300)],
        symbol="ETHUSDC",
        interval_seconds=60,
    )

    assert result["interval_validated"] is False
    assert result["quality_status"] == "blocked"


def test_forbidden_engine_backtest_ui_and_downloader_files_do_not_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    forbidden_paths = [
        "src/ethusdc_bot/data_pipeline/downloader.py",
        "src/ethusdc_bot/data_pipeline/binance_client.py",
        "src/ethusdc_bot/exchange",
        "src/ethusdc_bot/engine",
        "src/ethusdc_bot/strategy",
        "src/ethusdc_bot/backtest",
        "src/ethusdc_bot/ui",
        "data",
        "raw",
        "market_data",
    ]

    assert [path for path in forbidden_paths if (root / path).exists()] == []
