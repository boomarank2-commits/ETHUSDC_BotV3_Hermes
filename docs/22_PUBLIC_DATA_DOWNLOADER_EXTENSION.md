# Public Data Downloader Extension

This document describes the readiness-oriented public Binance data downloader extension.

Module:

- `src/ethusdc_bot/data_pipeline/public_data_downloader.py`

The module is for public data only. It does not use API keys, does not call Binance trading/private APIs, does not place orders, does not run strategies or backtests, and does not create profit/trade/candidate fields.

## Supported public data

The downloader now supports planning and optional execution for:

1. `ETHUSDC` spot klines `1m`
2. `BTCUSDC` spot klines `1m`
3. `ETHBTC` spot klines `1m`
4. `ETHUSDC` `aggTrades`
5. `ETHUSDC` `trades`

Safety roles:

- `ETHUSDC` klines are the only later `trade_market` source.
- `BTCUSDC` and `ETHBTC` are always `market_context`, `context_only=true`, `trade_market=false`, `may_trigger_orders=false`.
- `ETHUSDC aggTrades` and `ETHUSDC trades` are `microstructure_tradeflow` only.

## Public functions

- `build_public_data_url(symbol, data_type, interval, day_or_month, frequency)`
- `build_public_checksum_url(zip_url)`
- `plan_public_download_task(task)`
- `execute_public_download_task(task, execute=False)`
- `execute_readiness_download_tasks(readiness_report, execute=False)`
- `run_public_data_downloader(argv=None)`

## CLI examples

Dry-run from readiness:

```bash
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_data_downloader --from-readiness
```

Execute from readiness, only after explicit user approval:

```bash
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_data_downloader --from-readiness --execute
```

Dry-run BTCUSDC 1m klines:

```bash
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_data_downloader --symbol BTCUSDC --data-type klines --interval 1m --last-days 1095
```

Dry-run ETHBTC 1m klines:

```bash
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_data_downloader --symbol ETHBTC --data-type klines --interval 1m --last-days 1095
```

Dry-run ETHUSDC aggTrades:

```bash
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_data_downloader --symbol ETHUSDC --data-type aggTrades --last-days 7
```

Dry-run ETHUSDC trades:

```bash
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_data_downloader --symbol ETHUSDC --data-type trades --last-days 1
```

## Dry-run and execute behavior

- Dry-run is the default.
- Dry-run returns planned file and CHECKSUM targets and does not call network.
- `--execute` is required before any download writes.
- Existing files are skipped.
- Targets inside the repository are rejected.
- Raw data targets must remain under the external raw-data root, normally `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.

## Current readiness dry-run shape

At the time this extension was added, `--from-readiness` dry-run produced public tasks for:

- missing ETHUSDC 1m kline day
- BTCUSDC 1m context klines, 1095 planned files
- ETHBTC 1m context klines, 1095 planned files
- ETHUSDC aggTrades, 7 planned files
- ETHUSDC trades, 1 planned file

It skipped non-download public-data tasks that are not supported by this module, such as exchange_info, and live collection tasks such as bookTicker/orderbook snapshots.

No real downloads were executed in this session.
