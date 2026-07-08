# Last Known Good

Last known safe state:
- Phase 1 skeleton, strict schema validation, data catalog/audit foundation, local data inventory scanner, inventory status command, raw-data directory contract, raw-data manifest schema, public ETHUSDC 1m kline downloader, first local tkinter control UI, and ETHUSDC 1m ZIP audit gate were already committed and pushed before this session.
- Backtest Data Requirements catalog has been implemented in this session.
- Backtest Data Readiness gate has been implemented in this session.
- UI dashboard snapshot includes `data_readiness_report`.
- Targeted data/UI tests passed.
- Full local test suite passed with `pytest tests/ -q` before handoff update.
- Real local readiness command succeeded.
- Real local readiness status: blocked, ETHUSDC 1094/1095 days, BTCUSDC/ETHBTC context missing, aggTrades/trades missing/diagnostic, bookTicker/orderbook live 0/30 days.
- Raw market data remains outside the repository by contract and downloader target path.
- No raw data was committed.
- No Binance trading API, API keys, engine, strategy, backtest implementation, paper trading, testtrade, live trading, fake trades, or fake reports exist.
- Backtest button is visible but disabled.
- Live/Paper/Testtrade remain locked.

Safe continuation rule:
- Read AGENTS.md, handoff directory, and git status before continuing.
- Next safe implementation is public-data downloader extension or external data completion, not backtest or trading execution.
- Keep Live/Paper/Testtrade locked unless the explicit project contract gates are satisfied later.
