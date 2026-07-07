# Next Action

Wait for user review and explicit approval.

Smallest possible next step toward first safe test start:
- Add a user-approved local data presence command or diagnostic wrapper that loads `config/data_catalog.example.toml`, points at `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`, and prints/saves an honest inventory status.

Recommended next mini-ticket after approval:
- "Local data inventory status command without download"

Acceptance direction for that next ticket:
- Must not download data.
- Must not call Binance.
- Must not read market data contents.
- Must not run a backtest, strategy, engine, or UI.
- Must not create fake reports.
- May only report which expected source paths are missing/present/blocked.
- Must keep raw market data outside the repository.
- Must keep Live/Paper/Testtrade locked.

Do not start engine, strategy, backtest, UI, Binance, paper trading, testtrade, or live work without explicit user approval.
