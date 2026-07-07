# Next Action

Wait for user review and explicit approval.

Smallest possible next step toward first safe test start:
- Run or supervise a controlled public-data download for a limited date range outside the repository, then inspect inventory status.

Recommended next mini-ticket after approval:
- "Controlled ETHUSDC public data download smoke and inventory check"

Acceptance direction for that next ticket:
- Use only public Binance data URLs.
- Use no API keys and no private/trading Binance API.
- Store data only under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Do not commit raw data.
- Do not read market data contents except for a later explicitly approved audit ticket.
- Do not run a backtest, strategy, engine, or UI.
- Do not create fake reports.
- Keep Live/Paper/Testtrade locked.

Example full 1095-day command, after explicit approval:
- `PYTHONPATH=src python -m ethusdc_bot.data_pipeline.public_kline_downloader --last-days 1095 --execute`

Do not start engine, strategy, backtest, UI, Binance trading API, paper trading, testtrade, or live work without explicit user approval.
