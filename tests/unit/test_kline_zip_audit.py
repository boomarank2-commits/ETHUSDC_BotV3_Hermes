"""ETHUSDC 1m kline ZIP audit tests.

The audit reads only local ZIP files in the approved external raw-data tree.
It must not download data, create repo data folders, run backtests, or emit
profit/trade/candidate fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import zipfile

import pytest

from ethusdc_bot.data_pipeline import kline_zip_audit as audit
from ethusdc_bot.validation import SchemaValidationError


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


def _allow_tmp_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    allowed_root = tmp_path / "external_data"
    monkeypatch.setattr(audit, "DEFAULT_ALLOWED_RAW_ROOT", allowed_root)
    return allowed_root


def _download_dir(root: Path) -> Path:
    return root / "raw" / "binance" / "spot" / "ETHUSDC" / "klines" / "1m"


def _ms(value: str) -> int:
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)


def _row(open_time_ms: int) -> list[str]:
    close_time_ms = open_time_ms + 59_999
    return [
        str(open_time_ms),
        "2000.0",
        "2001.0",
        "1999.0",
        "2000.5",
        "1.0",
        str(close_time_ms),
        "2000.5",
        "1",
        "0.5",
        "1000.25",
        "0",
    ]


def _write_zip(path: Path, rows: list[list[str]], inner_name: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    csv_text = "\n".join(",".join(row) for row in rows) + "\n"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(inner_name or path.with_suffix(".csv").name, csv_text)


def _one_complete_day_rows() -> list[list[str]]:
    start = _ms("2024-01-01T00:00:00")
    return [_row(start + minute * 60_000) for minute in range(1440)]


def test_parse_kline_open_time_from_row_returns_first_column_as_integer_ms():
    assert audit.parse_kline_open_time_from_row(_row(_ms("2024-01-01T00:00:00"))) == _ms(
        "2024-01-01T00:00:00"
    )


def test_parse_kline_open_time_from_row_normalizes_microseconds_to_ms():
    row = _row(_ms("2025-01-01T00:00:00"))
    row[0] = str(_ms("2025-01-01T00:00:00") * 1000)

    assert audit.parse_kline_open_time_from_row(row) == _ms("2025-01-01T00:00:00")


def test_clean_daily_zip_is_usable_when_required_day_is_present(monkeypatch, tmp_path):
    root = _allow_tmp_root(monkeypatch, tmp_path)
    zip_path = _download_dir(root) / "ETHUSDC-1m-2024-01-01.zip"
    _write_zip(zip_path, _one_complete_day_rows())

    result = audit.build_kline_audit_summary(_download_dir(root), required_utc_days=1)

    assert result["audit_status"] == "usable_for_backtest_candidate"
    assert result["backtest_ready"] is True
    assert result["zip_count"] == 1
    assert result["observed_rows"] == 1440
    assert result["observed_start_utc"] == "2024-01-01T00:00:00Z"
    assert result["observed_end_utc"] == "2024-01-01T23:59:00Z"
    assert result["complete_utc_days"] == 1
    assert result["missing_utc_days"] == []
    assert result["duplicate_rows"] == 0
    assert result["gap_count"] == 0
    assert result["max_gap_seconds"] == 0


def test_audit_detects_duplicate_open_time(monkeypatch, tmp_path):
    root = _allow_tmp_root(monkeypatch, tmp_path)
    rows = _one_complete_day_rows()
    rows.append(rows[10])
    zip_path = _download_dir(root) / "ETHUSDC-1m-2024-01-01.zip"
    _write_zip(zip_path, rows)

    result = audit.audit_ethusdc_1m_zip_file(zip_path)

    assert result["audit_status"] == "incomplete"
    assert result["duplicate_rows"] == 1
    assert result["backtest_ready"] is False


def test_audit_detects_gap(monkeypatch, tmp_path):
    root = _allow_tmp_root(monkeypatch, tmp_path)
    rows = _one_complete_day_rows()
    del rows[30]
    zip_path = _download_dir(root) / "ETHUSDC-1m-2024-01-01.zip"
    _write_zip(zip_path, rows)

    result = audit.audit_ethusdc_1m_zip_file(zip_path)

    assert result["audit_status"] == "incomplete"
    assert result["gap_count"] == 1
    assert result["max_gap_seconds"] == 120
    assert result["complete_utc_days"] == 0


def test_audit_detects_unsorted_open_time(monkeypatch, tmp_path):
    root = _allow_tmp_root(monkeypatch, tmp_path)
    rows = _one_complete_day_rows()
    rows[10], rows[11] = rows[11], rows[10]
    zip_path = _download_dir(root) / "ETHUSDC-1m-2024-01-01.zip"
    _write_zip(zip_path, rows)

    result = audit.audit_ethusdc_1m_zip_file(zip_path)

    assert result["audit_status"] == "incomplete"
    assert result["unsorted_rows"] == 1
    assert result["backtest_ready"] is False


def test_audit_detects_broken_zip(monkeypatch, tmp_path):
    root = _allow_tmp_root(monkeypatch, tmp_path)
    zip_path = _download_dir(root) / "ETHUSDC-1m-2024-01-01.zip"
    zip_path.parent.mkdir(parents=True)
    zip_path.write_bytes(b"not a zip")

    result = audit.audit_ethusdc_1m_zip_file(zip_path)

    assert result["audit_status"] == "blocked"
    assert result["error"]
    assert result["backtest_ready"] is False


def test_directory_audit_counts_zip_and_checksum(monkeypatch, tmp_path):
    root = _allow_tmp_root(monkeypatch, tmp_path)
    directory = _download_dir(root)
    _write_zip(directory / "ETHUSDC-1m-2024-01-01.zip", _one_complete_day_rows())
    (directory / "ETHUSDC-1m-2024-01-01.zip.CHECKSUM").write_text("checksum\n", encoding="utf-8")

    result = audit.audit_ethusdc_1m_zip_directory(directory)

    assert result["zip_count"] == 1
    assert result["checksum_count"] == 1
    assert result["observed_rows"] == 1440


def test_summary_is_not_usable_when_required_days_are_missing(monkeypatch, tmp_path):
    root = _allow_tmp_root(monkeypatch, tmp_path)
    directory = _download_dir(root)
    _write_zip(directory / "ETHUSDC-1m-2024-01-01.zip", _one_complete_day_rows())

    result = audit.build_kline_audit_summary(directory, required_utc_days=2)

    assert result["audit_status"] == "incomplete"
    assert result["backtest_ready"] is False
    assert result["complete_utc_days"] == 1
    assert result["missing_utc_days"] == ["2024-01-02"]


def test_audit_summary_has_no_profit_backtest_trade_or_candidate_fields(monkeypatch, tmp_path):
    root = _allow_tmp_root(monkeypatch, tmp_path)
    result = audit.build_kline_audit_summary(_download_dir(root), required_utc_days=1095)

    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(result)
    for file_result in result["files"]:
        assert FORBIDDEN_RESULT_FIELDS.isdisjoint(file_result)


def test_audit_rejects_paths_outside_allowed_raw_root(monkeypatch, tmp_path):
    _allow_tmp_root(monkeypatch, tmp_path)

    with pytest.raises(SchemaValidationError):
        audit.find_kline_zip_files(tmp_path / "repo" / "raw" / "binance")
