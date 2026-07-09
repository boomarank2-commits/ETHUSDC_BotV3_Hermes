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
