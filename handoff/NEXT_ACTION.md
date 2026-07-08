# Next Action

Smallest possible next step:
- Run a dedicated data audit ticket for the downloaded/public ETHUSDC 1m files before any backtest-engine work.

Recommended next mini-ticket:
- "Audit ETHUSDC 1m public kline ZIP/CHECKSUM coverage for 1095 UTC days"

Acceptance direction for that next ticket:
- Use only local files under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Do not store raw data inside the repository.
- Verify ZIP/CHECKSUM presence and UTC-day coverage honestly.
- Do not create profit, trade, candidate, or backtest result fields.
- Do not implement engine, strategy, exchange, paper, testtrade, or live trading.
- Keep Live/Paper/Testtrade locked.
- Produce only an audit/status artifact if explicitly approved by the ticket.

UI start command:
- `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`

Optional Windows helper:
- `./scripts/start_dashboard.ps1`

Do not start real backtest, paper trading, testtrade, live trading, strategy, engine, Binance trading API, or order work without explicit approval and required gates.
