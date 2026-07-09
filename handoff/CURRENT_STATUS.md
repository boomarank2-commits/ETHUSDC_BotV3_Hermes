# Current Status

Status: Dashboard restart/progress issue fixed. The UI now separates persistent local data coverage from the current run progress so restart/refresh no longer presents runtime 0% as the overall data state.

Latest completed changes:
- Added persistent `overall_data_progress_pct` to dashboard snapshots, computed from local readiness/public data requirements.
- Added separate `current_run_progress_pct` for the current UI data-preparation run.
- `data_prep_progress_pct` now mirrors overall data progress for the main UI progress bar.
- Operator summary now shows:
  - `Gesamtdatenstand: xx%`
  - `Aktueller Lauf: yy% seit Start / ...`
  - per-source rows for ETHUSDC 1m, BTCUSDC 1m, ETHBTC 1m, ETHUSDC aggTrades, ETHUSDC trades.
- Tk dashboard main progress bar is bound to overall data progress, not runtime progress.
- Current-run progress remains visible as text and does not overwrite the main data-state bar.
- Public readiness now counts only complete public ZIP/CHECKSUM pairs as available days.
- `.tmp`, `.part`, missing ZIP/CHECKSUM partners, and 0-byte files are not counted as complete local data.
- Downloader skip logic no longer treats 0-byte existing files as complete.

Read-only local data state observed under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`:
- Total files: 6589.
- `.tmp/.part`: 0.
- 0-byte files: 0.
- Latest mtime: `2026-07-09T15:49:55.882725`.
- ETHUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- BTCUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- ETHBTC 1m: 1096 ZIP / 1096 CHECKSUM / 1096 complete pairs; UI caps required progress at 1095/1095.
- ETHUSDC aggTrades: 7 ZIP / 7 CHECKSUM / 7 complete pairs.
- ETHUSDC trades: 1 ZIP / 1 CHECKSUM / 1 complete pair.
- Public readiness minimum data progress is now 100.0% locally.
- If all five sources are naively treated as 1095-day streams, raw pair coverage is 3294/5475 = 60.16%; UI readiness correctly uses the requirement/minimum-day plan instead.

Diagnosis:
- The old visible `Gesamtfortschritt` came from `runtime_status["progress_pct"]`.
- `build_dashboard_snapshot()` created a fresh idle runtime after restart with `progress_pct = 0`.
- `refresh_status()` applied that idle runtime to the UI and progress bar when no active thread existed.
- Therefore restart/refresh could show 0% even though valid files existed on disk.

Downloads executed in this session:
- No real downloads.
- Only read-only local data inspection, dashboard snapshot smoke, and tests.

Verification before handoff update:
- Targeted regression tests green.
- `pytest tests/ -q` green.

Safety unchanged:
- No Backtest engine.
- No strategy.
- No trades.
- No profit fields.
- No Binance trading API.
- No API keys.
- No orders.
- Live/Paper/Testtrade locked.
