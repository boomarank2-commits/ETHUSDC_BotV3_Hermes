# Current Status

Status: UI-Datenvorbereitung hat jetzt einen echten sichtbaren Runtime-Fortschritt. Der Button `Backtest starten / Daten laden` bleibt daten-vorbereitend und startet weiterhin keine echte Backtest-Engine.

Completed in this session:
- Added structured data-prep status in `src/ethusdc_bot/ui/data_update_controller.py`:
  - `build_initial_data_prep_status(mode="dry_run")`
  - `update_progress_status(status, progress_callback=None, **updates)`
  - `run_data_update_plan(..., progress_callback=None)`
  - `run_data_update_plan_async(..., progress_callback=None)`
- Runtime status now reports:
  - phase, mode, progress_pct, current_step, current_task_id, current_symbol, current_data_type
  - total/completed/skipped/failed task counts
  - supported/unsupported/live collector task counts
  - engine_start_locked=true, backtest_started=false, backtest_allowed=false
  - started_at, finished_at, last_message, error
- Progress is based on real workflow steps, not fake byte progress:
  - readiness check
  - plan build
  - each supported public task in dry-run or execute mode
  - readiness/audit refresh
  - finished=100
- Updated `src/ethusdc_bot/ui/dashboard_state.py` snapshot with:
  - `data_prep_runtime_status`
  - `data_prep_progress_pct`
  - `data_prep_current_task`
  - `data_prep_mode`
  - `bot_current_status_text`
  - `can_start_data_prep=true`
  - `can_start_backtest_engine=false`
  - `backtest_blocker_summary`
- Updated `src/ethusdc_bot/ui/dashboard.py`:
  - large top status area for bot state, phase, mode, percentage, progressbar, current task, task counts, engine lock
  - button text: `Daten prüfen (Dry-run)`
  - button text: `Backtest starten / Daten laden`
  - data-prep buttons disabled while a workflow is running
  - status refresh runs automatically after completion
  - Open Data Folder log explains external raw-data folder `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Updated tests:
  - initial idle status/progress
  - dry-run phase sequence
  - execute downloading statuses
  - progress clamps 0..100 and reaches 100 on finished
  - failed status captures error
  - backtest_started remains false
  - engine_start_locked remains true
  - snapshot contains runtime status and blockers
  - no forbidden profit/trade/candidate/backtest-result fields
  - no forbidden repo paths/reports created
- Updated `docs/23_UI_BACKTEST_START_DATA_PREP.md`.

Current UI behavior:
- `Daten prüfen (Dry-run)` checks readiness, builds the plan, walks supported tasks as dry-run status, refreshes readiness, and downloads nothing.
- `Backtest starten / Daten laden` runs supported public downloads only, refreshes readiness, and still does not start a real backtest engine.
- The UI distinguishes data-prep completion from true backtest execution.
- The snapshot and UI state make clear why backtest remains blocked.

Supported UI-prep public data sources:
- ETHUSDC 1m klines
- BTCUSDC 1m klines
- ETHBTC 1m klines
- ETHUSDC aggTrades
- ETHUSDC trades

Still unsupported/blocked:
- exchange_info downloader/fetcher
- bookTicker live collector
- orderbook snapshot live collector
- real backtest engine
- strategy
- feature build
- backtest reports/results
- candidate adoption
- Paper/Testtrade/Live

Validation performed:
- Initial git status was clean.
- Targeted new tests failed first, then passed after implementation.
- Targeted UI/controller/dashboard tests passed.
- Full local test suite passed with `pytest tests/ -q` before handoff update.

Current safe project direction:
- Next safe action is to start the UI and visually smoke-test dry-run progress.
- A real data download execute smoke should be user-approved because it can fetch external raw data.
- Backtest engine work remains a separate future step after data readiness is green.
