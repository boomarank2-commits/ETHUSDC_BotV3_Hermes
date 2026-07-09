"""Safety tests for the backtest foundation."""

from pathlib import Path
from datetime import UTC, datetime, timedelta

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy


def _candles(closes: list[float]) -> list[Candle]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [
        Candle(open_time=int((start + timedelta(minutes=i)).timestamp() * 1000), open=close, high=close + 1, low=close - 1, close=close, volume=1)
        for i, close in enumerate(closes)
    ]

ROOT = Path(__file__).resolve().parents[2]


def test_context_symbols_cannot_trigger_orders():
    strategy = StrategyCandidate(family="always_long", params={"symbol": "BTCUSDC"})

    result = simulate_strategy(_candles([100, 101, 102]), strategy, days=1)

    assert result.trade_count == 0
    assert result.rejection_reasons["context_symbol_not_tradeable"] == 1


def test_no_binance_trading_api_module_exists():
    assert not (ROOT / "src/ethusdc_bot/data_pipeline/binance_client.py").exists()
    assert not (ROOT / "src/ethusdc_bot/exchange/binance_client.py").exists()


def test_no_api_keys_or_secret_files_exist():
    assert not (ROOT / ".env").exists()
    assert not (ROOT / "api_keys").exists()
    assert not (ROOT / "secrets.json").exists()


def test_no_live_paper_testtrade_folders_exist():
    assert not (ROOT / "src/ethusdc_bot/live").exists()
    assert not (ROOT / "src/ethusdc_bot/paper").exists()
    assert not (ROOT / "src/ethusdc_bot/testtrade").exists()


def test_no_exchange_or_forbidden_binance_client_exists():
    assert not (ROOT / "src/ethusdc_bot/exchange").exists()
    assert not (ROOT / "src/ethusdc_bot/binance_client.py").exists()


def test_no_raw_data_in_repository():
    assert not (ROOT / "data").exists()
    assert not (ROOT / "raw").exists()
    assert not (ROOT / "market_data").exists()
