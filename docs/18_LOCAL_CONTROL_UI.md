# Local Control UI

This is the first local status/control dashboard for `ETHUSDC_BotV3_Hermes`.
It uses only the Python standard library, primarily `tkinter`.

## Start command

From the repository root:

```bash
PYTHONPATH=src python -m ethusdc_bot.ui.dashboard
```

Windows helper:

```powershell
./scripts/start_dashboard.ps1
```

## What the UI can do

- Show the fixed project contract:
  - ETHUSDC
  - USDC quote
  - Binance Spot
  - LONG-only
  - 100 USDC start capital
  - 730 training days
  - 365 blindtest days
  - 1095 required UTC days
  - later target: at least 3 USDC/day after a realistic audited blindtest
- Show safety locks:
  - Live locked
  - Paper locked
  - Testtrade locked
  - Shorts/Margin/Futures/Leverage forbidden
- Show path-only data inventory status:
  - `local_root`
  - `repository_root`
  - total/missing/present/blocked counts
  - ETHUSDC 1m kline source status
  - BTCUSDC 1m context source status
  - ETHBTC 1m context source status
- Count existing files in the ETHUSDC 1m kline download folder:
  - ZIP count
  - CHECKSUM count
  - last 10 file names
  - rough 1095-day target count: about 1095 ZIP + 1095 CHECKSUM
- Show the local ETHUSDC 1m ZIP audit gate:
  - audit status
  - observed start/end UTC
  - observed row count
  - complete UTC day count
  - missing UTC day count
  - duplicate row count
  - gap count
  - max gap seconds
  - backtest-ready boolean
- Show the Backtest Data Readiness gate:
  - rolling data/training/blindtest window
  - per-source readiness status
  - available days and required/minimum days
  - included_in_backtest
  - update_required
  - blocking_backtest
  - reason
- Refresh the snapshot.
- Open the local data root in Explorer when it already exists.
- Start the public downloader in dry-run mode for the last 1095 days.
- Start the public downloader with `--execute` for the last 1095 days.
- Display downloader stdout/stderr in the log window when started by the UI.

## What the UI explicitly cannot do yet

- No trading engine.
- No strategy.
- No real or fake backtest.
- No paper trading.
- No testtrade.
- No live trading.
- No Binance trading API.
- No API keys or `.env` files.
- No orders.
- No fake trades.
- No fake reports.
- No candidate adoption.
- No backtest result or trading-quality claim. The data audit is a local file-quality gate only.

The dashboard now inspects local ETHUSDC 1m ZIP contents when the expected folder
exists under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`. It does not inspect
repository raw-data folders, download data during audit, or claim any profit,
trade, backtest, or candidate result.

## Why the backtest button is still locked

The button is visible so the planned workflow is obvious, but it is disabled with
this hint:

`Backtest waits for data readiness and real engine implementation. No fake result.`

A real backtest must wait until a separate backtest engine exists and the data
audit is complete. The UI must not fake backtest output or unlock later trading
stages.

## Download commands used by the UI

Dry-run plan:

```bash
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_kline_downloader --last-days 1095 --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes
```

Execute public download:

```bash
PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_kline_downloader --last-days 1095 --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --execute
```

The downloader uses Binance public data URLs only and skips existing files.

## Data location

Default external data root:

`C:/TradingBot/data/ETHUSDC_BotV3_Hermes`

ETHUSDC 1m kline target folder:

`C:/TradingBot/data/ETHUSDC_BotV3_Hermes/raw/binance/spot/ETHUSDC/klines/1m`

Raw market data must remain outside the repository. The UI state helpers do not
create `data/`, `raw/`, or `market_data/` directories inside the repository.

## Safety status

Live, Paper, and Testtrade remain locked. Shorts, margin, futures, and leverage
remain forbidden.
