# Next Action

Smallest possible next step:
- Implement the next safe public-data downloader scope for readiness tasks without adding strategy/backtest logic.

Recommended next mini-ticket:
- "Extend public downloader support for readiness tasks: missing ETHUSDC day, BTCUSDC/ETHBTC 1m context klines, and ETHUSDC aggTrades/trades planning"

Acceptance direction for that next ticket:
- Use only external raw-data target `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Do not store raw data inside the repository.
- Keep dry-run as default and require explicit `--execute` for real public downloads.
- Start with missing ETHUSDC 2026-07-07 and BTCUSDC/ETHBTC 1m context klines.
- Mark aggTrades/trades honestly if downloader support is not completed.
- Re-run readiness and ZIP audits after any downloads.
- Do not create profit, trade, candidate, or backtest result fields.
- Do not implement engine, strategy, exchange, paper, testtrade, or live trading.
- Keep Live/Paper/Testtrade locked.

Current readiness command shape:
- `PYTHONPATH=src python - <<'PY' ... build_data_readiness_report(Path('C:/TradingBot/data/ETHUSDC_BotV3_Hermes')) ... PY`

UI start command:
- `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`

Optional Windows helper:
- `./scripts/start_dashboard.ps1`

After data readiness is green:
- Next safe code step is still not strategy optimization.
- Build the smallest read-only backtest input-preparation contract: load only approved data sources, enforce rolling window, enforce train/blind split boundaries, and still produce no profit/trade/candidate claims until a real engine exists.

Do not start real backtest, paper trading, testtrade, live trading, strategy, engine, Binance trading API, or order work without explicit approval and required gates.
