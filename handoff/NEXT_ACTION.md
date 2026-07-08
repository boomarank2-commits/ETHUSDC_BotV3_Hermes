# Next Action

Smallest possible next step:
- Start the UI and visually smoke-test the new data-prep progress status in dry-run mode.

Recommended next mini-ticket:
- "Run UI dry-run progress smoke and inspect readiness blocker wording"

Acceptance direction for that next ticket:
- Use only external raw-data target `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Do not store raw data inside the repository.
- Start UI with `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`.
- Click `Daten prüfen (Dry-run)` first.
- Verify the top status area shows phase/mode/progress/current task/tasks/engine lock.
- Verify buttons are disabled while the workflow is running and re-enabled after completion.
- Verify logs show readiness check, supported tasks, unsupported tasks, live collector tasks, and final readiness status.
- Verify `Backtest-Engine: locked` remains visible.
- Do not execute real downloads unless explicitly approved.
- If executing downloads later, use `Backtest starten / Daten laden` and re-run ZIP audit/readiness after completion.
- Do not create profit, trade, candidate, or backtest result fields.
- Do not implement engine, strategy, exchange, paper, testtrade, or live trading.
- Keep Live/Paper/Testtrade locked.

UI start command:
- `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`

Current behavior:
- `Daten prüfen (Dry-run)` runs dry-run preparation with task-progress status.
- `Backtest starten / Daten laden` runs supported data preparation only; real engine remains locked and no real backtest starts.

Do not start real backtest, paper trading, testtrade, live trading, strategy, engine, Binance trading API, or order work without explicit approval and required gates.
