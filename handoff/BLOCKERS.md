# Blockers

Current blockers:
- Backtest Data Readiness remains blocked.
- ETHUSDC 1m is still incomplete: local count observed as 1094 ZIP / 1094 CHECKSUM, not the required 1095 complete UTC days.
- BTCUSDC 1m context folder is missing/empty.
- ETHBTC 1m context folder is missing/empty.
- ETHUSDC aggTrades folder is missing/empty.
- ETHUSDC trades folder is missing/empty.
- Exchange info remains unsupported by current public-data downloader path.
- BookTicker and orderbook snapshot tasks remain live-collector tasks and are not implemented in this UI workflow.
- Real backtest engine is not implemented and remains locked even if data readiness eventually becomes ready.

Resolved UI blocker:
- Long public download tasks no longer have to appear frozen solely because task-level progress is coarse. The downloader now emits per-file progress events and the dashboard emits a heartbeat during active threads.

Operational blocker:
- Any already-open UI must be restarted to load the new Python code.

Strict safety locks remain:
- Live locked.
- Paper locked.
- Testtrade locked.
- No Binance trading API.
- No API keys.
- No orders.
- No strategy/engine/backtest result generation.
