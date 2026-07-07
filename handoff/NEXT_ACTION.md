# Next Action

Wait for user review and explicit approval.

Smallest possible next step toward first safe test start:
- Add a dry-run raw data directory readiness command that combines catalog, raw-data contract, manifest template validation, and inventory status without creating directories or downloading data.

Recommended next mini-ticket after approval:
- "Raw data readiness dry-run command without download"

Acceptance direction for that next ticket:
- Must not download data.
- Must not call Binance.
- Must not read market data contents.
- Must not create raw data directories unless explicitly approved.
- Must not run a backtest, strategy, engine, or UI.
- Must not create fake reports.
- Must keep raw market data outside the repository.
- Must keep Live/Paper/Testtrade locked.

Do not start engine, strategy, backtest, UI, Binance, paper trading, testtrade, or live work without explicit user approval.
