# 17 - Public ETHUSDC 1m Kline Downloader

This downloader fetches only public Binance Spot kline ZIP files from `data.binance.vision`.
It is limited to `ETHUSDC` and interval `1m`.

## Safety boundaries

Implemented:

- Public Binance data URLs only.
- No API key.
- No private Binance API.
- No orders.
- No trading engine.
- No strategy.
- No backtest.
- No UI.
- No paper trading, testtrade, or live trading.
- Dry-run by default.
- Real downloads only with `--execute`.
- Target root outside the repository:

```text
C:/TradingBot/data/ETHUSDC_BotV3_Hermes/raw/binance/spot/ETHUSDC/klines/1m
```

The repository must never contain raw ZIP, CSV, Parquet, JSONL, or market data directories.

## URL shape

Daily ZIP:

```text
https://data.binance.vision/data/spot/daily/klines/ETHUSDC/1m/ETHUSDC-1m-YYYY-MM-DD.zip
```

Monthly ZIP:

```text
https://data.binance.vision/data/spot/monthly/klines/ETHUSDC/1m/ETHUSDC-1m-YYYY-MM.zip
```

Checksum URL:

```text
<ZIP_URL>.CHECKSUM
```

## Usage

Dry-run date range:

```text
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_kline_downloader --symbol ETHUSDC --interval 1m --start 2024-01-01 --end 2024-01-03
```

Execute a small date range:

```text
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_kline_downloader --symbol ETHUSDC --interval 1m --start 2024-01-01 --end 2024-01-03 --execute
```

Plan the full current 1095-day target:

```text
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_kline_downloader --last-days 1095
```

Execute the full current 1095-day target:

```text
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_kline_downloader --last-days 1095 --execute
```

## Manifest behavior

When `--execute` is used, the downloader writes/updates a `manifest.json` in the download target directory.
The manifest records only download metadata and remains `not_audited` with `quality_status = unknown`.
It must not claim profit, trades, backtest success, candidate adoption, or audit success.
