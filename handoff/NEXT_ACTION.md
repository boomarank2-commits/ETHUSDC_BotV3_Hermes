# Next Action

Wait for user review and explicit approval.

Smallest possible next step toward first safe test start:
- Add a local-data presence scanner/audit planner that reads only metadata or user-approved local file listings under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- It must still perform no download, no Binance API call, no backtest, no strategy, no engine, and no UI work unless separately approved.

Recommended next mini-ticket after approval:
- "Local data inventory scanner without download"

Acceptance direction for that next ticket:
- Confirm raw data root is outside the repository.
- Detect which required source paths are missing/present.
- Produce an honest local inventory status only, not a fake report.
- Keep Live/Paper/Testtrade locked.

Do not start engine, strategy, backtest, UI, Binance, paper trading, testtrade, or live work without explicit user approval.
