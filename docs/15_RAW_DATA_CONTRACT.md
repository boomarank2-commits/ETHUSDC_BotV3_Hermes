# 15 - Raw Data Directory Contract

This document defines the local raw-data target contract for future downloader work.
It is a contract only: it does not create folders, download data, read market data,
call Binance, run a strategy, run a backtest, start UI code, or unlock live/paper/testtrade.

## Allowed raw-data root

The only planned local raw-data root is:

```text
C:/TradingBot/data/ETHUSDC_BotV3_Hermes
```

Raw data must never be stored inside this repository:

```text
C:/TradingBot/hermes-agent/ETHUSDC_BotV3_Hermes
```

## Planned path shape

Future raw files for each catalog source must live below:

```text
C:/TradingBot/data/ETHUSDC_BotV3_Hermes/raw/binance/spot/<SYMBOL>/<DATA_TYPE>/...
```

Kline sources include their interval:

```text
C:/TradingBot/data/ETHUSDC_BotV3_Hermes/raw/binance/spot/ETHUSDC/klines/1m
C:/TradingBot/data/ETHUSDC_BotV3_Hermes/raw/binance/spot/BTCUSDC/klines/1m
C:/TradingBot/data/ETHUSDC_BotV3_Hermes/raw/binance/spot/ETHBTC/klines/1m
```

The ETHUSDC 1m kline path is the primary required path for the later 1095 full UTC-day data goal.
BTCUSDC and ETHBTC are context-only and must not trigger orders.

## Expected manifest

Each future source target directory may contain a `manifest.json` describing downloaded files and metadata.
The contract names this path only; it does not create the manifest.

Required manifest intent for a future ticket:

- source_id
- symbol
- role
- data_type
- interval_seconds
- exchange = binance
- market_type = spot
- local files list
- observed start/end UTC if actually audited later
- status that does not claim success before audit

## Explicit non-goals

This contract does not implement:

- downloader.py
- binance_client.py
- Binance API calls
- API keys or `.env`
- raw market data files in the repository
- engine
- strategy
- backtest
- UI
- paper trading
- testtrade
- live trading
- fake trades
- fake reports
- profit/backtest/candidate fields

Live, paper trading, and testtrade remain locked.
