# Blockers

Current blockers:
- Real backtest engine is not implemented and remains locked even though public readiness minimum data is now complete locally.
- Exchange info remains unsupported by current public-data downloader path.
- BookTicker and orderbook snapshot tasks remain live-collector tasks and are not implemented in this UI workflow.

Resolved UI/data-progress blocker:
- The UI no longer uses current-run runtime `progress_pct` as the main `Gesamtfortschritt` after restart.
- The dashboard now has persistent `overall_data_progress_pct` from local file/readiness state.
- The dashboard separately exposes `current_run_progress_pct`/current-run text.
- Refresh/restart should no longer make existing local data look like 0% complete.

Resolved local public-data readiness state observed read-only:
- ETHUSDC 1m: 1095 complete ZIP/CHECKSUM pairs.
- BTCUSDC 1m: 1095 complete ZIP/CHECKSUM pairs.
- ETHBTC 1m: 1096 complete ZIP/CHECKSUM pairs.
- ETHUSDC aggTrades: 7 complete ZIP/CHECKSUM pairs.
- ETHUSDC trades: 1 complete ZIP/CHECKSUM pair.
- No `.tmp/.part` files and no 0-byte files observed.

Operational note:
- Restart the dashboard so the new progress display code is loaded.
- Use `START_DASHBOARD.bat` for the next run.

Safety locks remain:
- Live locked.
- Paper locked.
- Testtrade locked.
- No trading API.
- No keys.
- No orders.
- No strategy/engine/backtest result generation.
