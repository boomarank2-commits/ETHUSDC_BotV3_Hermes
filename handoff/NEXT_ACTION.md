# Next Action

Smallest possible next step:
- Start the UI and run a controlled data-preparation workflow from the UI.

Recommended next mini-ticket:
- "Run UI data preparation smoke and inspect readiness refresh"

Acceptance direction for that next ticket:
- Use only external raw-data target `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Do not store raw data inside the repository.
- Use the UI button flow instead of manual downloader commands where possible.
- Verify logs show readiness check, supported tasks, unsupported tasks, live collector tasks, and final readiness status.
- If executing downloads, keep the first smoke small or explicitly user-approved.
- Re-run ZIP audit and data readiness after any downloads.
- Do not create profit, trade, candidate, or backtest result fields.
- Do not implement engine, strategy, exchange, paper, testtrade, or live trading.
- Keep Live/Paper/Testtrade locked.

UI start command:
- `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`

Current behavior:
- `Daten prüfen / aktualisieren` runs dry-run preparation.
- `Backtest starten` runs data preparation only; real engine remains locked.

Do not start real backtest, paper trading, testtrade, live trading, strategy, engine, Binance trading API, or order work without explicit approval and required gates.
