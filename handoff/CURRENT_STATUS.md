# Current Status

Status: UI-Datenvorbereitung hat jetzt eine dauerhaft sichtbare Last-Run-Anzeige innerhalb derselben UI-Sitzung. Refresh Status überschreibt diese Anzeige nicht mehr mit `idle`.

Completed in this session:
- Added per-session last-run status helpers in `src/ethusdc_bot/ui/data_update_controller.py`:
  - `build_initial_data_prep_last_run_status()`
  - `build_running_data_prep_last_run_status(runtime_status)`
  - `build_finished_data_prep_last_run_status(result)`
  - `build_failed_data_prep_last_run_status(runtime_status, error)`
- Last-run status fields include:
  - `last_run_status`: `never_run`, `running`, `finished`, `failed`
  - `last_run_mode`
  - `last_run_started_at`
  - `last_run_finished_at`
  - `last_run_duration_seconds`
  - task counts and download result count
  - readiness before/after
  - `last_run_backtest_engine_locked=true`
  - `last_run_summary_text`
  - `last_run_next_blocker`
- Updated `src/ethusdc_bot/ui/dashboard_state.py`:
  - snapshot accepts optional `data_prep_last_run_status`
  - text snapshot now begins with `Last Data Prep Run`
  - refresh callers can pass the existing last-run state so it stays visible
- Updated `src/ethusdc_bot/ui/dashboard.py`:
  - `DashboardApp` stores `self.last_run_status` in memory
  - running status is updated from progress dicts
  - final status is built from the async result container or thread error
  - Refresh Status passes the existing last-run status into the snapshot
  - buttons still re-enable after completion
  - long download status explicitly says progress is task-based, not byte-based
- Updated tests and docs.

Diagnosis from local inspection:
- No running dashboard process was visible from `ps` in this shell session.
- The most likely UI symptom was confirmed in code: `refresh_status()` rebuilt a fresh snapshot with idle runtime status and no persisted last-run state, so after completion/refresh the user could not clearly see what happened.
- Existing open UI processes must be restarted to load new Python code.
- External raw-data counts checked read-only:
  - ETHUSDC 1m: 1094 ZIP, 1094 CHECKSUM, newest manifest timestamp 2026-07-07T23:05:25
  - BTCUSDC 1m: folder missing / 0 ZIP / 0 CHECKSUM
  - ETHBTC 1m: folder missing / 0 ZIP / 0 CHECKSUM
  - ETHUSDC aggTrades: folder missing / 0 ZIP / 0 CHECKSUM
  - ETHUSDC trades: folder missing / 0 ZIP / 0 CHECKSUM
- This strongly suggests the user’s prior UI run did not complete the broad execute downloads, or the currently open UI was old code / progress was lost after refresh. No repo-local raw data was created.

Current UI behavior:
- New UI sessions start with `Last data prep run status: never_run`.
- During a workflow, Last Run shows `running` and current task context.
- After dry-run or execute completion, Last Run shows `finished`, mode, timing, task counts, download result count, readiness before/after, and next blocker.
- On failure, Last Run shows `failed` and the error text.
- Refresh Status no longer clears Last Run inside the same UI session.

Important user action:
- UI schließen und neu starten erforderlich, if the currently open UI was started before this commit.
- Start command: `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`

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
- New tests failed first for missing last-run helpers/snapshot support.
- Targeted tests passed after implementation.
- Full local test suite passed with `pytest tests/ -q` before handoff update.
