# Blockers

Current blockers:
- Backtest Data Readiness remains blocked.
- ETHUSDC 1m is still partial: local count observed as 1094 ZIP / 1094 CHECKSUM, not the required 1095 complete UTC days.
- BTCUSDC 1m context folder is missing/empty.
- ETHBTC 1m context folder is missing/empty.
- ETHUSDC aggTrades folder is missing/empty.
- ETHUSDC trades folder is missing/empty.
- Exchange info remains unsupported by current public-data downloader path.
- BookTicker and orderbook snapshot tasks remain live-collector tasks and are not implemented in this UI workflow.
- Real backtest engine is not implemented and remains locked even if data readiness eventually becomes ready.

Resolved UI/operator blocker:
- The UI no longer centers the operator workflow around long diagnostic text.
- The primary button now executes supported public data preparation.
- The dry-run button is explicitly labeled as no-download.
- Refresh no longer makes an active/finished run look idle.
- The top UI now shows clear running/finished/error status and no-file-event heartbeat messages.

Operational note:
- Restart the dashboard so the new button labels and display code are loaded.
- Use `START_DASHBOARD.bat` for the next run.

Safety locks remain:
- Live locked.
- Paper locked.
- Testtrade locked.
- No trading API.
- No keys.
- No orders.
- No strategy/engine/backtest result generation.
