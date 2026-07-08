# Current Status

Status: UI-gesteuerter Backtest-Start-Vorbereitungsablauf wurde implementiert. Der Button `Backtest starten` ist jetzt klickbar, startet aber weiterhin keine echte Backtest-Engine, sondern nur die Datenvorbereitung.

Completed in this session:
- Added `src/ethusdc_bot/ui/data_update_controller.py` with:
  - `build_data_update_plan(local_root)`
  - `summarize_data_update_plan(plan)`
  - `run_data_update_plan(local_root, execute=False, log_callback=None)`
  - `run_data_update_plan_async(local_root, execute=False, log_callback=None)`
- The controller:
  - builds Data Readiness before preparation,
  - separates supported public download tasks,
  - separates unsupported tasks such as `exchange_info`,
  - separates live collector tasks such as bookTicker/orderbook,
  - runs supported public downloads only when `execute=True`,
  - rebuilds readiness after the preparation workflow,
  - never starts a real backtest engine.
- Updated `src/ethusdc_bot/ui/dashboard_state.py`:
  - added `data_prep_status`,
  - added `data_prep_button`,
  - added `backtest_start_button`,
  - backtest start button is visible/enabled but action is `data_preparation_only`,
  - `engine_start_locked=true`.
- Updated `src/ethusdc_bot/ui/dashboard.py`:
  - visible buttons now include `Daten prüfen / aktualisieren` and `Backtest starten`,
  - data prep runs asynchronously to avoid freezing the UI,
  - log window receives readiness, task, unsupported-task, live-collector, and completion messages.
- Added `tests/unit/test_ui_data_update_controller.py`.
- Updated dashboard state/side-effect tests.
- Added `docs/23_UI_BACKTEST_START_DATA_PREP.md`.

Current UI behavior:
- `Daten prüfen / aktualisieren` runs a dry-run data preparation workflow.
- `Backtest starten` runs data preparation with supported public downloads enabled.
- It logs: `Backtest start currently runs data preparation only. Real engine start is still locked.`
- It does not start a real backtest engine.
- It does not create result reports.

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
- New controller tests failed first because `data_update_controller` did not exist.
- Targeted UI/controller tests passed.
- Full local test suite passed with `pytest tests/ -q` before handoff update.

Current safe project direction:
- Next safe action is to run the UI or a small explicitly-approved data-prep execute smoke and then re-run audit/readiness.
- Backtest engine work remains a separate future step after data readiness is green.
