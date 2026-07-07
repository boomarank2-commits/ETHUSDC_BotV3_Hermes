# Next Action

Wait for user review and explicit approval.

Smallest possible next step toward first safe test start:
- Decide whether to add a no-download local data directory bootstrap plan or proceed to a controlled downloader design ticket.

Recommended next mini-ticket after approval:
- "Plan downloader inputs and local raw-data directory contract"

Acceptance direction for that next ticket:
- Must still not download data unless the user explicitly approves a later download ticket.
- Must not call Binance yet unless explicitly approved.
- Must not read market data contents yet unless explicitly approved for audit.
- Must not run a backtest, strategy, engine, or UI.
- Must not create fake reports.
- Must keep raw market data outside the repository.
- Must keep Live/Paper/Testtrade locked.

Current user-facing command for local inventory status from the repository source tree:
- `PYTHONPATH=src python -m ethusdc_bot.data_pipeline.inventory_status`
- `PYTHONPATH=src python -m ethusdc_bot.data_pipeline.inventory_status --json`

Do not start engine, strategy, backtest, UI, Binance, paper trading, testtrade, or live work without explicit user approval.
