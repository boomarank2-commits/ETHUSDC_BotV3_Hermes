# UI Backtest Start Data Preparation

This document describes the current UI-driven Backtest Start preparation workflow.

The important distinction:

- The UI button is now clickable.
- It does not start a real backtest engine.
- It runs data preparation only.
- The real engine start remains locked because no backtest engine exists yet.
- No fake result is created.

Visible UI wording:

`Backtest start currently runs data preparation only. Real engine start is still locked.`

## Current UI flow

The intended user flow is now:

1. Open the local dashboard.
2. Click `Backtest starten`.
3. The UI logs that Backtest Start currently means data preparation only.
4. The UI checks Data Readiness.
5. The UI builds a data update plan.
6. Supported public download tasks may run through the public downloader.
7. Unsupported tasks and live collector tasks are shown honestly.
8. The UI rebuilds audit/readiness state.
9. The UI shows the refreshed readiness status.
10. The UI logs: `Data preparation finished. Backtest engine not implemented yet.`

The user should not need to manually type public download commands for the supported sources once this UI workflow is used.

## Controller

Module:

- `src/ethusdc_bot/ui/data_update_controller.py`

Functions:

- `build_data_update_plan(local_root)`
- `summarize_data_update_plan(plan)`
- `run_data_update_plan(local_root, execute=False, log_callback=None)`
- `run_data_update_plan_async(local_root, execute=False, log_callback=None)`

The controller uses:

- `build_backtest_start_data_gate` / Data Readiness
- `public_data_downloader` for supported public tasks

It never starts:

- backtest engine
- strategy
- live trading
- paper trading
- testtrade
- Binance trading API
- orders

It never creates:

- fake trades
- fake reports
- profit fields
- candidate adoption
- backtest result reports

## Buttons

The UI now exposes:

- `Refresh Status`
- `Open Data Folder`
- `Daten prüfen / aktualisieren`
- `Backtest starten`

Button behavior:

- `Daten prüfen / aktualisieren` runs the data preparation workflow in dry-run mode.
- `Backtest starten` runs the data preparation workflow with supported public download execution, but still does not start a real engine.

Backtest start button model in the dashboard snapshot:

- visible: true
- enabled: true
- action: `data_preparation_only`
- engine_locked: true
- hint: `Backtest start currently prepares data only. Real engine is not implemented yet.`

## Automatically prepared public data

Supported by the UI data-preparation path through `public_data_downloader`:

- ETHUSDC 1m klines
- BTCUSDC 1m klines
- ETHBTC 1m klines
- ETHUSDC aggTrades
- ETHUSDC trades

Safety roles remain enforced:

- ETHUSDC is the only later trade market.
- BTCUSDC and ETHBTC are context only and must never trigger orders.
- aggTrades/trades are microstructure/tradeflow data only.

## Not yet automatic

Still not implemented by this UI data-preparation workflow:

- exchange_info fetcher/downloader
- bookTicker live collector
- orderbook snapshot live collector
- real backtest engine
- feature build
- strategy
- reports with results
- candidate adoption
- Paper/Testtrade/Live unlocks

Unsupported and live tasks are logged/displayed as unsupported or collector-needed, not silently treated as done.

## No fake result

The UI must not claim success for a backtest until a real engine exists and the data gate is green. Data preparation finishing only means the preparation workflow completed. It does not mean:

- a strategy exists;
- a backtest ran;
- trades exist;
- profit exists;
- a candidate can be adopted;
- Paper/Testtrade/Live can start.
