"""Public data downloader extension tests.

These tests use fake paths and monkeypatched network calls only. They must not
call Binance private/trading APIs, create repo data folders, run backtests,
create trades/profit/candidates, or unlock live/paper/testtrade.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import json

import pytest

from ethusdc_bot.data_pipeline import public_data_downloader as downloader
from ethusdc_bot.data_pipeline.data_readiness import build_data_readiness_report
from ethusdc_bot.validation import SchemaValidationError


ROOT = Path(__file__).resolve().parents[2]
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


def test_btcusdc_1m_kline_url_is_built_correctly():
    assert downloader.build_public_data_url("BTCUSDC", "klines", "1m", "2024-01-02", "daily") == (
        "https://data.binance.vision/data/spot/daily/klines/BTCUSDC/1m/"
        "BTCUSDC-1m-2024-01-02.zip"
    )


def test_ethbtc_1m_kline_url_is_built_correctly():
    assert downloader.build_public_data_url("ETHBTC", "klines", "1m", "2024-01-02", "daily") == (
        "https://data.binance.vision/data/spot/daily/klines/ETHBTC/1m/"
        "ETHBTC-1m-2024-01-02.zip"
    )


def test_ethusdc_aggtrades_url_is_built_correctly():
    assert downloader.build_public_data_url("ETHUSDC", "aggTrades", None, "2024-01-02", "daily") == (
        "https://data.binance.vision/data/spot/daily/aggTrades/ETHUSDC/"
        "ETHUSDC-aggTrades-2024-01-02.zip"
    )


def test_ethusdc_trades_url_is_built_correctly():
    assert downloader.build_public_data_url("ETHUSDC", "trades", None, "2024-01-02", "daily") == (
        "https://data.binance.vision/data/spot/daily/trades/ETHUSDC/"
        "ETHUSDC-trades-2024-01-02.zip"
    )


def test_checksum_url_is_built_correctly():
    zip_url = downloader.build_public_data_url("ETHUSDC", "trades", None, "2024-01-02", "daily")

    assert downloader.build_public_checksum_url(zip_url) == zip_url + ".CHECKSUM"


@pytest.mark.parametrize("symbol", ["BTCUSDC", "ETHBTC"])
def test_context_symbols_are_context_only_and_never_order_triggers(tmp_path, symbol):
    task = {
        "symbol": symbol,
        "data_type": "klines_1m",
        "interval": "1m",
        "start_date": "2024-01-01",
        "end_date": "2024-01-01",
        "target_path": str(tmp_path / "raw" / "binance" / "spot" / symbol / "klines" / "1m"),
        "source_kind": "public_binance_data",
    }

    plan = downloader.plan_public_download_task(task)

    assert plan["role"] == "market_context"
    assert plan["context_only"] is True
    assert plan["trade_market"] is False
    assert plan["may_trigger_orders"] is False


def test_dry_run_download_task_does_not_call_network_or_create_files(monkeypatch, tmp_path):
    def fail_if_called(url, filename):
        raise AssertionError("network must not be called in dry-run")

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fail_if_called)
    task = _task(tmp_path, "BTCUSDC", "klines_1m", "1m", "2024-01-01", "2024-01-01")

    result = downloader.execute_public_download_task(task, execute=False)

    assert result["execute"] is False
    assert {item["status"] for item in result["file_results"]} == {"planned"}
    assert list(tmp_path.rglob("*.zip")) == []


def test_execute_is_required_for_real_download(monkeypatch, tmp_path):
    calls = []

    def fake_urlretrieve(url, filename):
        calls.append((url, filename))
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        Path(filename).write_bytes(b"downloaded")
        return filename, None

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fake_urlretrieve)
    task = _task(tmp_path, "ETHBTC", "klines_1m", "1m", "2024-01-01", "2024-01-01")

    dry = downloader.execute_public_download_task(task, execute=False)
    executed = downloader.execute_public_download_task(task, execute=True)

    assert calls
    assert dry["file_results"][0]["status"] == "planned"
    assert executed["file_results"][0]["status"] == "downloaded"


def test_target_path_inside_repository_is_rejected():
    task = _task(ROOT, "BTCUSDC", "klines_1m", "1m", "2024-01-01", "2024-01-01")

    with pytest.raises(SchemaValidationError):
        downloader.plan_public_download_task(task)


def test_target_path_outside_repository_is_accepted(tmp_path):
    task = _task(tmp_path, "BTCUSDC", "klines_1m", "1m", "2024-01-01", "2024-01-01")

    plan = downloader.plan_public_download_task(task)

    assert str(plan["target_dir"]).startswith(str(tmp_path))
    assert plan["downloads"][0]["target_path"].endswith("BTCUSDC-1m-2024-01-01.zip")


def test_progress_events_are_sent_for_each_planned_zip_and_checksum_in_dry_run(tmp_path):
    events = []
    task = _task(tmp_path, "BTCUSDC", "klines_1m", "1m", "2024-01-01", "2024-01-02")

    result = downloader.execute_public_download_task(task, execute=False, progress_callback=events.append)

    assert result["planned_files"] == 2
    assert len(events) == 4
    assert {event["status"] for event in events} == {"planned"}
    assert events[0]["planned_file_count"] == 4
    assert events[0]["current_file_index"] == 1
    assert events[-1]["current_file_index"] == 4
    assert events[0]["current_file_name"].endswith(".zip")
    assert events[1]["current_file_name"].endswith(".zip.CHECKSUM")


def test_existing_files_emit_skipped_progress_events(monkeypatch, tmp_path):
    def fail_if_called(url, filename):
        raise AssertionError("existing files should not be downloaded")

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fail_if_called)
    task = _task(tmp_path, "ETHUSDC", "trades", None, "2024-01-01", "2024-01-01")
    plan = downloader.plan_public_download_task(task)
    target = Path(plan["downloads"][0]["target_path"])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"already here")
    Path(str(target) + ".CHECKSUM").write_text("checksum\n", encoding="utf-8")
    events = []

    downloader.execute_public_download_task(task, execute=True, progress_callback=events.append)

    assert [event["status"] for event in events] == ["skipped_existing", "skipped_existing"]
    assert events[-1]["skipped_file_count"] == 2
    assert events[-1]["completed_file_count"] == 2


def test_execute_download_emits_downloading_and_downloaded_progress_events(monkeypatch, tmp_path):
    def fake_urlretrieve(url, filename):
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
        Path(filename).write_bytes(b"downloaded")
        return filename, None

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fake_urlretrieve)
    task = _task(tmp_path, "ETHBTC", "klines_1m", "1m", "2024-01-01", "2024-01-01")
    events = []

    downloader.execute_public_download_task(task, execute=True, progress_callback=events.append)

    statuses = [event["status"] for event in events]
    assert statuses == ["downloading", "downloaded", "downloading", "downloaded"]
    assert all(event["current_file_name"] for event in events)
    assert events[-1]["downloaded_file_count"] == 2
    assert events[-1]["completed_file_count"] == 2


def test_existing_files_are_skipped(monkeypatch, tmp_path):
    def fail_if_called(url, filename):
        raise AssertionError("existing files should not be downloaded")

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fail_if_called)
    task = _task(tmp_path, "ETHUSDC", "aggTrades", None, "2024-01-01", "2024-01-01")
    plan = downloader.plan_public_download_task(task)
    target = Path(plan["downloads"][0]["target_path"])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"already here")
    Path(str(target) + ".CHECKSUM").write_text("checksum\n", encoding="utf-8")

    result = downloader.execute_public_download_task(task, execute=True)

    assert result["file_results"][0]["status"] == "skipped_existing"
    assert result["checksum_results"][0]["status"] == "skipped_existing"


def test_zero_byte_existing_file_is_not_skipped_as_complete(monkeypatch, tmp_path):
    calls = []

    def fake_urlretrieve(url, filename):
        calls.append((url, filename))
        Path(filename).write_bytes(b"downloaded")
        return filename, None

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fake_urlretrieve)
    task = _task(tmp_path, "ETHUSDC", "trades", None, "2024-01-01", "2024-01-01")
    plan = downloader.plan_public_download_task(task)
    target = Path(plan["downloads"][0]["target_path"])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"")

    result = downloader.execute_public_download_task(task, execute=True)

    assert calls
    assert result["file_results"][0]["status"] == "downloaded"


def test_zip_without_checksum_pair_is_not_treated_as_fully_skipped(monkeypatch, tmp_path):
    calls = []

    def fake_urlretrieve(url, filename):
        calls.append((url, filename))
        Path(filename).write_bytes(b"downloaded")
        return filename, None

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fake_urlretrieve)
    task = _task(tmp_path, "ETHUSDC", "trades", None, "2024-01-01", "2024-01-01")
    plan = downloader.plan_public_download_task(task)
    target = Path(plan["downloads"][0]["target_path"])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"zip-only")

    result = downloader.execute_public_download_task(task, execute=True)

    assert result["file_results"][0]["status"] == "skipped_existing"
    assert result["checksum_results"][0]["status"] == "downloaded"
    assert calls

def test_from_readiness_executes_public_tasks_as_dry_run(tmp_path):
    report = build_data_readiness_report(tmp_path, reference_date=date(2026, 7, 8))

    result = downloader.execute_readiness_download_tasks(report, execute=False)
    task_ids = {entry["task_id"] for entry in result["task_results"]}

    assert "download_ethusdc_klines_1m" in task_ids
    assert "download_btcusdc_klines_1m" in task_ids
    assert "download_ethbtc_klines_1m" in task_ids
    assert "download_ethusdc_aggtrades" in task_ids
    assert "download_ethusdc_trades" in task_ids
    assert "collect_ethusdc_bookticker_live" not in task_ids
    assert result["execute"] is False


def test_result_has_no_profit_backtest_trade_or_candidate_fields(tmp_path):
    task = _task(tmp_path, "ETHUSDC", "trades", None, "2024-01-01", "2024-01-01")
    result = downloader.execute_public_download_task(task, execute=False)

    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(result)
    for entry in result["file_results"] + result["checksum_results"]:
        assert FORBIDDEN_RESULT_FIELDS.isdisjoint(entry)


def test_cli_dry_run_outputs_json_without_downloading(monkeypatch, tmp_path, capsys):
    def fail_if_called(url, filename):
        raise AssertionError("network must not be called in CLI dry-run")

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fail_if_called)
    exit_code = downloader.run_public_data_downloader(
        [
            "--symbol",
            "BTCUSDC",
            "--data-type",
            "klines",
            "--interval",
            "1m",
            "--last-days",
            "1",
            "--raw-root",
            str(tmp_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["execute"] is False
    assert output["task_results"][0]["symbol"] == "BTCUSDC"
    assert list(tmp_path.rglob("*.zip")) == []


def test_forbidden_files_and_directories_do_not_exist():
    forbidden_paths = [
        "src/ethusdc_bot/data_pipeline/binance_client.py",
        "src/ethusdc_bot/exchange",
        "src/ethusdc_bot/engine",
        "src/ethusdc_bot/strategy",
        "src/ethusdc_bot/backtest",
        "data",
        "raw",
        "market_data",
    ]

    assert [path for path in forbidden_paths if (ROOT / path).exists()] == []


def _task(tmp_path: Path, symbol: str, data_type: str, interval: str | None, start: str, end: str) -> dict[str, object]:
    folder = "klines/1m" if data_type == "klines_1m" else data_type
    return {
        "task_id": f"download_{symbol.lower()}_{data_type}",
        "requirement_id": f"{symbol.lower()}_{data_type}",
        "symbol": symbol,
        "data_type": data_type,
        "interval": interval,
        "start_date": start,
        "end_date": end,
        "target_path": str(tmp_path / "raw" / "binance" / "spot" / symbol / folder),
        "source_kind": "public_binance_data",
        "execute_allowed": True,
        "reason": "test",
    }

