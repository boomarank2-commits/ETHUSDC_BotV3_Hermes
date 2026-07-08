# Last Known Good

Last known safe state:
- UI data preparation workflow exists and is status-only / data-preparation-only.
- Runtime progress and Last Run status are visible in the dashboard.
- Last Run survives Refresh Status within the same UI session.
- Public downloader emits file-level progress events for planned/skipped/downloading/downloaded/failed ZIP and CHECKSUM files.
- Dashboard shows heartbeat during active data-prep threads so long tasks do not look frozen.
- Dry-run remains non-downloading and reports `Dry-run finished. No downloads executed.`
- Backtest/data-load button still starts data preparation only; real engine remains locked.
- Tests pass with `pytest tests/ -q`.

Last verified local counts, read-only:
- ETHUSDC 1m: 1094 ZIP / 1094 CHECKSUM.
- BTCUSDC 1m: 0 / missing folder.
- ETHBTC 1m: 0 / missing folder.
- ETHUSDC aggTrades: 0 / missing folder.
- ETHUSDC trades: 0 / missing folder.

Safety:
- No live/paper/testtrade unlock.
- No orders.
- No API keys.
- No trading API.
- No profit/trade/candidate/backtest result fields.
