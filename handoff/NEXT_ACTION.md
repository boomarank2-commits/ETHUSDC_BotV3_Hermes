# Next Action

Smallest possible next step:
- With explicit user approval, run a small public-data execute smoke for only the missing ETHUSDC 1m day, then re-run ETHUSDC ZIP audit and readiness.

Recommended next mini-ticket:
- "Execute one-day ETHUSDC public kline download smoke for 2026-07-07 and re-audit"

Acceptance direction for that next ticket:
- Use only external raw-data target `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Do not store raw data inside the repository.
- Use the public downloader only with explicit `--execute`.
- Limit the smoke to the missing ETHUSDC 2026-07-07 day unless the user explicitly approves broader downloads.
- Re-run ZIP audit and data readiness after the smoke.
- Do not create profit, trade, candidate, or backtest result fields.
- Do not implement engine, strategy, exchange, paper, testtrade, or live trading.
- Keep Live/Paper/Testtrade locked.

Useful dry-run command:
- `PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_data_downloader --from-readiness`

Possible small execute smoke, only after user approval:
- `PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_data_downloader --symbol ETHUSDC --data-type klines --interval 1m --start 2026-07-07 --end 2026-07-07 --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --execute`

Large context downloads should remain separate user-approved steps:
- BTCUSDC 1095-day klines
- ETHBTC 1095-day klines

Do not start real backtest, paper trading, testtrade, live trading, strategy, engine, Binance trading API, or order work without explicit approval and required gates.
