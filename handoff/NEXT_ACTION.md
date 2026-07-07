# Next Action

Wait for user review and explicit approval.

Smallest possible next step toward first safe test start:
- Add a no-download downloader manifest schema/template for the future raw-data target directories.

Recommended next mini-ticket after approval:
- "Raw data manifest template and validation without download"

Acceptance direction for that next ticket:
- Must still not download data.
- Must not call Binance.
- Must not read market data contents.
- Must not create raw data directories unless explicitly approved.
- Must not run a backtest, strategy, engine, or UI.
- Must not create fake reports.
- Must keep raw market data outside the repository.
- Must keep Live/Paper/Testtrade locked.

Do not start engine, strategy, backtest, UI, Binance, paper trading, testtrade, or live work without explicit user approval.
