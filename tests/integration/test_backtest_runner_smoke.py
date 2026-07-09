"""Integration smoke for the real backtest runner on fixture data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import zipfile

from ethusdc_bot.backtest.runner import run_backtest


def _write_kline_zip(root: Path, symbol: str, day: datetime, minutes: int = 3) -> None:
    folder = root / "raw" / "binance" / "spot" / symbol / "klines" / "1m"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{symbol}-1m-{day.date().isoformat()}.zip"
    rows = []
    for index in range(minutes):
        open_time = int((day.timestamp() * 1000) + index * 60_000)
        rows.append([open_time, "100.0", "101.0", "99.0", str(100 + index), "1.0"])
    csv_text = "\n".join(",".join(str(value) for value in row) for row in rows) + "\n"
    with zipfile.ZipFile(folder / name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name.replace(".zip", ".csv"), csv_text)
    (folder / f"{name}.CHECKSUM").write_text("fixture checksum\n", encoding="utf-8")


def test_backtest_runner_smoke_writes_report_from_fixture(tmp_path):
    _write_kline_zip(tmp_path / "raw_root", "ETHUSDC", datetime(2024, 1, 1, tzinfo=UTC), minutes=1440)
    _write_kline_zip(tmp_path / "raw_root", "ETHUSDC", datetime(2024, 1, 2, tzinfo=UTC), minutes=1440)
    report_root = tmp_path / "reports"

    result = run_backtest(raw_root=tmp_path / "raw_root", reports_root=report_root, required_days=None)

    assert result.status == "completed"
    assert result.report.json_path.exists()
    assert result.report.txt_path.exists()
    assert result.search_result.selection_source == "training_validation_only"
