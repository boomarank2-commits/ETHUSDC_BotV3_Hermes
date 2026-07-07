"""Public ETHUSDC 1m kline downloader tests.

These tests use fake temporary paths and monkeypatched network calls only. They
must not download real data, call private Binance APIs, create repository data
folders, run backtests, or unlock live/paper/testtrade.
"""

from datetime import date
from pathlib import Path
import json

import pytest

from ethusdc_bot.data_pipeline import public_kline_downloader as downloader
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
}


def test_monthly_url_is_built_correctly():
    assert downloader.build_monthly_kline_url("ETHUSDC", "1m", 2024, 1) == (
        "https://data.binance.vision/data/spot/monthly/klines/ETHUSDC/1m/"
        "ETHUSDC-1m-2024-01.zip"
    )


def test_daily_url_is_built_correctly():
    assert downloader.build_daily_kline_url("ETHUSDC", "1m", date(2024, 1, 2)) == (
        "https://data.binance.vision/data/spot/daily/klines/ETHUSDC/1m/"
        "ETHUSDC-1m-2024-01-02.zip"
    )


def test_checksum_url_is_built_correctly():
    zip_url = downloader.build_daily_kline_url("ETHUSDC", "1m", date(2024, 1, 2))

    assert downloader.build_checksum_url(zip_url) == zip_url + ".CHECKSUM"


def test_only_ethusdc_is_accepted():
    plan = downloader.plan_ethusdc_1m_download("2024-01-01", "2024-01-01", ROOT.parent / "data")

    assert plan["symbol"] == "ETHUSDC"
    assert {item["symbol"] for item in plan["downloads"]} == {"ETHUSDC"}


def test_only_1m_is_accepted():
    plan = downloader.plan_ethusdc_1m_download("2024-01-01", "2024-01-01", ROOT.parent / "data")

    assert plan["interval"] == "1m"
    assert {item["interval"] for item in plan["downloads"]} == {"1m"}


@pytest.mark.parametrize("symbol", ["BTCUSDC", "ETHBTC", "ETHUSDT"])
def test_wrong_symbol_is_rejected(symbol):
    with pytest.raises(SchemaValidationError):
        downloader.build_daily_kline_url(symbol, "1m", date(2024, 1, 2))


@pytest.mark.parametrize("interval", ["5m", "1h", "01m"])
def test_wrong_interval_is_rejected(interval):
    with pytest.raises(SchemaValidationError):
        downloader.build_daily_kline_url("ETHUSDC", interval, date(2024, 1, 2))


def test_target_path_inside_repository_is_rejected():
    with pytest.raises(SchemaValidationError):
        downloader.plan_ethusdc_1m_download("2024-01-01", "2024-01-01", ROOT / "data")


def test_target_path_outside_repository_is_accepted(tmp_path):
    plan = downloader.plan_ethusdc_1m_download("2024-01-01", "2024-01-01", tmp_path)
    target_dir = plan["target_dir"].replace("\\", "/")

    assert str(plan["target_dir"]).startswith(str(tmp_path))
    assert target_dir.endswith("raw/binance/spot/ETHUSDC/klines/1m")


def test_dry_run_download_file_does_not_create_file(tmp_path):
    target = tmp_path / "ETHUSDC-1m-2024-01-01.zip"

    result = downloader.download_file("https://example.test/file.zip", target, execute=False)

    assert result["status"] == "planned"
    assert not target.exists()


def test_execute_is_required_for_real_download(monkeypatch, tmp_path):
    def fail_if_called(url, filename):
        raise AssertionError("network should not be called in dry-run")

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fail_if_called)
    exit_code = downloader.run_downloader(
        [
            "--symbol",
            "ETHUSDC",
            "--interval",
            "1m",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-01",
            "--raw-root",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert list(tmp_path.rglob("*.zip")) == []


def test_existing_files_are_skipped(tmp_path):
    target = tmp_path / "ETHUSDC-1m-2024-01-01.zip"
    target.write_bytes(b"already here")

    result = downloader.download_file("https://example.test/file.zip", target, execute=True)

    assert result["status"] == "skipped_existing"
    assert target.read_bytes() == b"already here"


def test_manifest_has_no_profit_backtest_trade_or_candidate_fields(tmp_path):
    plan = downloader.plan_ethusdc_1m_download("2024-01-01", "2024-01-01", tmp_path)
    manifest = downloader.build_download_manifest(plan, [])

    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(manifest)
    for file_entry in manifest["files"]:
        assert FORBIDDEN_RESULT_FIELDS.isdisjoint(file_entry)


def test_manifest_remains_not_audited_without_real_audit(tmp_path):
    plan = downloader.plan_ethusdc_1m_download("2024-01-01", "2024-01-01", tmp_path)
    manifest = downloader.build_download_manifest(plan, [])

    assert manifest["audit_status"] == "not_audited"
    assert manifest["quality_status"] == "unknown"
    assert manifest["observed_start_utc"] is None
    assert manifest["observed_end_utc"] is None


def test_last_days_1095_plan_uses_only_ethusdc_1m_spot_sources(tmp_path):
    plan = downloader.plan_ethusdc_1m_download_for_last_days(1095, tmp_path)

    assert plan["symbol"] == "ETHUSDC"
    assert plan["interval"] == "1m"
    assert plan["market_type"] == "spot"
    assert {item["symbol"] for item in plan["downloads"]} == {"ETHUSDC"}
    assert {item["interval"] for item in plan["downloads"]} == {"1m"}
    assert {item["market_type"] for item in plan["downloads"]} == {"spot"}


def test_execute_writes_manifest_with_fake_public_download(monkeypatch, tmp_path):
    def fake_urlretrieve(url, filename):
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        if str(filename).endswith(".CHECKSUM"):
            path.write_text("not-a-real-checksum  file.zip\n", encoding="utf-8")
        else:
            path.write_bytes(b"fake zip bytes")
        return str(path), None

    monkeypatch.setattr(downloader.urllib.request, "urlretrieve", fake_urlretrieve)

    exit_code = downloader.run_downloader(
        [
            "--symbol",
            "ETHUSDC",
            "--interval",
            "1m",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-01",
            "--raw-root",
            str(tmp_path),
            "--execute",
        ]
    )

    manifest_path = tmp_path / "raw/binance/spot/ETHUSDC/klines/1m/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert manifest["download_status"] == "downloaded"
    assert manifest["audit_status"] == "not_audited"
    assert manifest["quality_status"] == "unknown"
    assert FORBIDDEN_RESULT_FIELDS.isdisjoint(manifest)


def test_forbidden_files_and_directories_do_not_exist():
    forbidden_paths = [
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

    assert [path for path in forbidden_paths if (ROOT / path).exists()] == []
