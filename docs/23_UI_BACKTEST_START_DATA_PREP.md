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
2. Click `Daten prüfen (Dry-run)` to inspect the plan without downloads, or `Backtest starten / Daten laden` to execute supported public downloads.
3. The UI logs that Backtest Start currently means data preparation only.
4. The UI checks Data Readiness.
5. The UI builds a data update plan.
6. The UI shows structured runtime status: phase, mode, percentage, current step, current task, task counts, and engine lock.
7. Supported public download tasks may run through the public downloader only in execute mode.
8. Unsupported tasks and live collector tasks are shown honestly.
9. The UI rebuilds audit/readiness state.
10. The UI shows the refreshed readiness status.
11. The UI logs: `Data preparation finished. Backtest engine not implemented yet.`

The user should not need to manually type public download commands for the supported sources once this UI workflow is used.

## Controller

Module:

- `src/ethusdc_bot/ui/data_update_controller.py`

Functions:

- `build_data_update_plan(local_root)`
- `summarize_data_update_plan(plan)`
- `run_data_update_plan(local_root, execute=False, log_callback=None, progress_callback=None)`
- `run_data_update_plan_async(local_root, execute=False, log_callback=None, progress_callback=None)`
- `build_initial_data_prep_status(mode="dry_run")`
- `update_progress_status(status, progress_callback=None, **updates)`

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

## Last-run visibility

The dashboard keeps a per-UI-session `Last Data Prep Run` status. This is intentionally in memory only:

- Restarting the UI resets it to `never_run`.
- Clicking Refresh Status inside the same UI session does not reset it.
- The last-run status is passed into the dashboard snapshot and displayed at the top of the text area.

Visible last-run fields:

- `last_run_status`: `never_run`, `running`, `finished`, or `failed`
- `last_run_mode`: `dry_run` or `execute`
- `last_run_started_at`
- `last_run_finished_at`
- `last_run_duration_seconds`
- `last_run_supported_tasks`
- `last_run_completed_tasks`
- `last_run_skipped_tasks`
- `last_run_failed_tasks`
- `last_run_download_results_count`
- `last_run_readiness_before`
- `last_run_readiness_after`
- `last_run_backtest_engine_locked=true`
- `last_run_summary_text`
- `last_run_next_blocker`

Completion wording is explicit:

- If readiness remains blocked: `Letzter Datenlauf fertig. Readiness bleibt blocked wegen: ...`
- If the data gate is ready but no engine exists: `Letzter Datenlauf fertig. Data gate ready, aber Engine fehlt.`
- If running: `Datenlauf läuft gerade...`
- If failed: `Datenlauf fehlgeschlagen: ...`

Important operational note: an already-open dashboard process uses the Python code it loaded at startup. After code updates, close and restart the UI with `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard` to get this last-run display.

## File-level progress and heartbeat

The UI now shows a heartbeat while a data-preparation thread is active. Even if a large public task contains many daily files and no byte-progress is available, the top status area updates about once per second with elapsed seconds and the current task/file state.

For public download tasks the downloader emits per-file events for both ZIP and CHECKSUM files:

- planned file count
- current file index
- current file name
- completed/skipped/downloaded/failed file counters
- status such as `planned`, `skipped_existing`, `downloading`, `downloaded`, or `failed`

This is still not fake byte-progress. It is task/file progress only. Large files may still take time while one file is being fetched, but the UI must keep saying that the run is still active and which task/file is current.

Dry-run remains non-writing and non-downloading. It can emit planned-file information only through the plan/result path, and the Last Run text must say: `Dry-run finished. No downloads executed.`

Execute mode means supported public data downloads are enabled. The UI must say that real public data preparation is running and show file-level counters where available.

## Runtime progress status

The dashboard now shows a large status area above the text snapshot:

- Bot-Zustand / last message
- Data Prep Phase
- Mode: Dry-run or Download
- Progress percentage
- Progress bar
- Current task id
- Completed tasks / total tasks
- Backtest-Engine: locked

The structured status contains these fields:

- `phase`: `idle`, `checking_readiness`, `planning`, `dry_run`, `downloading`, `auditing`, `refreshing_readiness`, `finished`, or `failed`
- `mode`: `dry_run` or `execute`
- `progress_pct`: 0..100
- `current_step`
- `current_task_id`, `current_symbol`, `current_data_type`
- `total_tasks`, `completed_tasks`, `skipped_tasks`, `failed_tasks`
- `supported_download_task_count`, `unsupported_task_count`, `live_collector_task_count`
- `engine_start_locked=true`
- `backtest_started=false`
- `backtest_allowed=false`
- `last_message`, `started_at`, `finished_at`, `error`

The percentage is task-progress based, not byte-progress based. The public data downloader does not currently expose reliable byte-level progress for every ZIP/CHECKSUM operation, so the UI only advances when a real workflow step occurs:

1. readiness check starts;
2. update plan is built;
3. each supported public task is dry-run planned or downloaded;
4. readiness/audit is refreshed;
5. workflow finishes at 100%.

This avoids fake progress. If a task takes a long time, the current task id stays visible until that real task completes.

## Buttons

The UI now exposes:

- `Refresh Status`
- `Open Data Folder`
- `Daten prüfen (Dry-run)`
- `Backtest starten / Daten laden`

Button behavior:

- `Daten prüfen (Dry-run)` runs the data preparation workflow in dry-run mode. It checks readiness, builds the plan, shows every supported task that would be handled, refreshes readiness, and downloads nothing.
- `Backtest starten / Daten laden` runs the data preparation workflow with supported public download execution, but still does not start a real engine.
- While either workflow is running, both data-prep buttons are disabled so the same flow cannot be started repeatedly.
- `Open Data Folder` opens the external raw-data folder `C:/TradingBot/data/ETHUSDC_BotV3_Hermes` and does not create repo-local raw data.

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

The UI must not claim success for a backtest until a real engine exists and the data gate is green. Data preparation finishing only means the preparation workflow completed. A finished download can improve local data availability, but it is not a profitability signal and does not mean:

- a strategy exists;
- a backtest ran;
- trades exist;
- profit exists;
- a candidate can be adopted;
- Paper/Testtrade/Live can start.
