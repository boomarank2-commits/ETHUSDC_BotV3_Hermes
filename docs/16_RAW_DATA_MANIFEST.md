# 16 - Raw Data Manifest Template

This document defines the raw-data `manifest.json` template for future local raw-data directories.
It is metadata only and does not create directories, download data, read market data, call Binance,
run a strategy, run a backtest, start UI code, or unlock live/paper/testtrade.

## Purpose

A future downloader may place one manifest next to local raw files below the allowed raw-data root:

```text
C:/TradingBot/data/ETHUSDC_BotV3_Hermes
```

The repository contains only an example template:

```text
config/raw_data_manifest.example.json
```

This template is not evidence that data exists and must not be treated as a report.

## Required template state

A template manifest must stay conservative:

- `schema_version = 1`
- `template = true`
- `download_status = not_downloaded`
- `audit_status = not_audited`
- `quality_status = unknown`
- `files = []`
- `observed_start_utc = null`
- `observed_end_utc = null`
- `observed_rows = 0`
- `complete_utc_days = 0`
- `missing_utc_days = []`
- `duplicate_rows = 0`
- `gap_count = 0`
- `max_gap_seconds = 0`
- `checksum_status = not_checked`

The template must not claim usable data, successful download, completed audit, profit, trades, backtest results, or candidate adoption.

## Safety rules

Forbidden fields include:

- profit/backtest/trade/candidate fields
- API keys, secrets, tokens
- live/paper/testtrade enable flags

BTCUSDC and ETHBTC are context-only. They must not trigger orders.
ETHUSDC remains the only primary trading symbol.

## Explicit non-goals

This manifest work does not implement:

- downloader.py
- binance_client.py
- Binance API calls
- API keys or `.env`
- raw market data files in the repository
- raw data directory creation
- market data reads
- engine
- strategy
- backtest
- UI
- paper trading
- testtrade
- live trading
- fake trades
- fake reports

Live, paper trading, and testtrade remain locked.
