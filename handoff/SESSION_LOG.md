# Session Log

## 2026-07-09 - Show persistent overall data progress after restart

Timebox: max 120 minutes.

Goal:
- Fix misleading dashboard restart behavior where the main progress could jump to 0% even though local files already existed.
- Keep total local data state separate from current-run progress.

Initial guard:
- `git status --short` was clean before work.
- Work stayed inside the allowed file list.
- No raw data, reports, engine, strategy, exchange, backtest, live, paper, API-key, or order code was created.

Read-only local data inspection:
- Root: `C:/TradingBot/data/ETHUSDC_BotV3_Hermes` exists.
- Total files: 6589.
- `.tmp/.part`: 0.
- 0-byte files: 0.
- Latest mtime: `2026-07-09T15:49:55.882725`.
- ETHUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- BTCUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- ETHBTC 1m: 1096 ZIP / 1096 CHECKSUM / 1096 complete pairs.
- ETHUSDC aggTrades: 7 ZIP / 7 CHECKSUM / 7 complete pairs.
- ETHUSDC trades: 1 ZIP / 1 CHECKSUM / 1 complete pair.
- No broken/half files were found by name/size checks.

Root cause:
- `format_operator_summary_for_display()` and the Tk progress area used runtime `progress_pct` as `Gesamtfortschritt`.
- On restart, `build_dashboard_snapshot()` built a new idle runtime with `progress_pct = 0`.
- With no active data thread, `refresh_status()` applied that idle runtime to the main progress bar.
- The UI had task/run progress but no persistent overall local-data progress field.

Tests added/extended first:
- Existing local files produce `overall_data_progress_pct > 0`.
- Idle runtime 0 does not overwrite overall data progress.
- Operator summary shows `Gesamtdatenstand` and `Aktueller Lauf` separately.
- ZIP without CHECKSUM is not counted as a complete day.
- CHECKSUM without ZIP is not counted as a complete day.
- `.part`, `.tmp`, and 0-byte files are not counted as complete days.
- 0-byte existing downloader target is not skipped as complete.
- ZIP-only existing file is not treated as a fully skipped pair; missing CHECKSUM is still downloaded/planned in execute path.

Implementation:
- `dashboard_state.build_overall_data_progress()` computes persistent progress from readiness requirements for the five operator-visible public sources.
- Dashboard snapshot includes:
  - `overall_data_progress_pct`
  - `overall_data_progress`
  - `current_run_progress_pct`
- Main `data_prep_progress_pct` now maps to overall data progress for the main bar.
- Tk dashboard keeps the main bar on overall data state and displays current-run progress as text.
- Readiness public-data availability now requires non-empty `.zip` plus matching non-empty `.zip.CHECKSUM` for a day.
- `.tmp`, `.part`, and 0-byte files are excluded from availability counts.
- Downloader skip check now requires an existing non-empty final file.

Local smoke:
- `PYTHONPATH=src` dashboard snapshot against the real local data root returned:
  - `overall_data_progress_pct 100.0`
  - `current_run_progress_pct 0`
  - all five operator rows complete against their configured requirements/minimums.
- Summary shows `Gesamtdatenstand: 100.0%` and `Aktueller Lauf: 0% seit Start / Idle` separately.

Verification:
- Targeted tests failed before implementation for the intended cases.
- Targeted tests passed after implementation.
- `pytest tests/ -q` passed before handoff update.

No real downloads were started.
No reports/backtests were created.
No forbidden directories/files were created.

## 2026-07-09 - Add deterministic ETHUSDC backtest strategy search foundation

Timebox: max 180 minutes.

Goal:
- Start the real backtest section without live, paper, testtrade, API keys, Trading API, or fake results.
- Build a reproducible ETHUSDC 1m data loader, 730/365 split, conservative LONG-only simulator, strategy search, runner, and honest report.

Initial guard:
- `git status --short` was clean before work.
- Handoff files were read first.
- Local data readiness was checked read-only before implementation.
- Existing full suite passed before implementation.

Data/UI Abschlussprüfung:
- `START_DASHBOARD.bat` exists.
- External root `C:/TradingBot/data/ETHUSDC_BotV3_Hermes` exists.
- Total files: 6589.
- `.tmp/.part`: 0.
- 0-byte files: 0.
- Data gate: ready.
- ETHUSDC 1m 1095/1095, BTCUSDC 1m 1095/1095, ETHBTC 1m 1096/1095, ETHUSDC aggTrades 7/7, ETHUSDC trades 1/1.
- ZIP/CHECKSUM pairs matched for all checked public sources.

TDD:
- New backtest tests were written first and failed with missing `ethusdc_bot.backtest` package.
- Implemented only after RED.

Implementation:
- Added `src/ethusdc_bot/backtest/` package.
- Loader reads ETHUSDC 1m ZIP/CHECKSUM pairs read-only, validates symbol, UTC order, 1m spacing, duplicates, gaps, and normalizes Binance microsecond timestamps to milliseconds.
- Split enforces 1095 UTC days for real runs: first 730 training, last 365 blindtest.
- Simulator is ETHUSDC Spot LONG-only with fees/slippage and no parallel positions.
- Search uses a small deterministic grid over momentum, mean-reversion, and breakout families; selection is training/validation only.
- Runner writes real JSON/TXT reports only after successful completion.
- Dashboard state now has a separate backtest-mode status/button model; full background UI execution remains next-step work.

Real backtest:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Loaded 1,576,800 ETHUSDC candles.
- Split: training 2023-07-09..2025-07-07; blindtest 2025-07-08..2026-07-07.
- Selected candidate: breakout lookback 60 / threshold 10 bps / TP 120 bps / SL 80 bps / max hold 90 minutes.
- Blindtest: -491.2563751241 USDC total, -1.3459078771 USDC/day, 1623 trades.
- Target 3 USDC/day: not reached.
- Report: `reports/backtests/bt_20260709T151036Z.json` and `.txt`.

Verification:
- Targeted tests passed.
- Real CLI runner passed.
- `pytest tests/ -q` passed before handoff update.

Safety:
- No API keys.
- No Binance Trading API.
- No orders.
- No live/paper/testtrade activation.
- Reports keep live/paper/testtrade locked and candidate_adoptable false.
