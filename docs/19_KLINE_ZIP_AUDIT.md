# ETHUSDC 1m Kline ZIP Audit

This document describes the local-only kline ZIP audit gate added before any real backtest work.

## Scope

Module:

- `src/ethusdc_bot/data_pipeline/kline_zip_audit.py`

Default audited external data root:

- `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`

Expected ETHUSDC 1m ZIP folder:

- `C:/TradingBot/data/ETHUSDC_BotV3_Hermes/raw/binance/spot/ETHUSDC/klines/1m`

The audit is intentionally read-only. It does not download files, call Binance APIs, create repository data folders, create reports, run a strategy, run a backtest, place orders, or unlock Live/Paper/Testtrade.

## Public functions

- `find_kline_zip_files(download_dir)`
- `find_checksum_files(download_dir)`
- `parse_kline_open_time_from_row(row)`
- `audit_ethusdc_1m_zip_file(zip_path)`
- `audit_ethusdc_1m_zip_directory(download_dir)`
- `build_kline_audit_summary(download_dir, required_utc_days=1095)`

## What is checked

For local ETHUSDC 1m ZIP files the audit checks:

- ZIP filename shape: `ETHUSDC-1m-*.zip`
- exactly one CSV inside the ZIP
- CSV filename/path identifies ETHUSDC 1m data
- Binance kline `open_time` column is parseable as integer milliseconds
- observed start/end UTC timestamps
- observed row count
- duplicate `open_time` rows
- unsorted `open_time` rows
- gaps between unique sorted `open_time` values
- maximum observed gap in seconds
- complete UTC days with exactly 1440 contiguous 1-minute rows from 00:00 through 23:59 UTC
- missing UTC days for the required window
- ZIP and CHECKSUM file counts

## Honest statuses

The audit uses these statuses:

- `not_audited`: no ZIP files were present in the audited directory.
- `blocked`: one or more ZIP files were missing, corrupt, malformed, or had invalid CSV structure.
- `incomplete`: ZIPs were readable but the required day coverage or cleanliness checks failed.
- `usable_for_backtest_candidate`: only when required UTC days are present, every complete day is clean, no duplicates exist, no gaps exist, no unsorted rows exist, and no blocked files exist.

`usable_for_backtest_candidate` does not mean a profitable strategy exists. It only means the local ETHUSDC 1m kline data passed this audit gate and could be considered by a future backtest candidate pipeline.

## Forbidden output

The audit does not emit profit, winrate, trade, backtest-run, or candidate-adoption fields. In particular it must not create or claim:

- `profit_usdc`
- `net_usdc_per_day`
- `winrate`
- `profit_factor`
- `trade_count`
- `trades`
- `real_trades`
- `backtest_run_id`
- `candidate_adoptable`
- `adopted_candidate`
- `best_candidate`
- `candidate`

## UI integration

`src/ethusdc_bot/ui/dashboard_state.py` now adds a `kline_audit_status` section to the dashboard snapshot and display output.

The UI shows:

- ZIP count
- CHECKSUM count
- audit status
- observed start/end UTC
- observed rows
- complete UTC days
- missing UTC days count
- duplicate rows
- gap count
- max gap seconds
- backtest readiness boolean

The backtest button remains disabled with:

`Backtest engine not implemented yet. Data audit is the next gate.`

## What still does not exist

- no backtest engine
- no strategy
- no trade generation
- no reports with backtest results
- no paper trading
- no testtrade
- no live trading
- no Binance trading API client
- no API keys

Next safe step after this audit gate is to inspect the audit output on real local data and define the smallest read-only preparation step for a future backtest engine, without any fake results or gate loosening.
