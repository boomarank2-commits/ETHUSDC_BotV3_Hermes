# Last Known Good

Last known safe state:
- Phase 1 skeleton, strict schema validation, data catalog/audit foundation, local data inventory scanner, inventory status command, raw-data directory contract, raw-data manifest schema, public ETHUSDC 1m kline downloader, first local tkinter control UI, ETHUSDC 1m ZIP audit gate, Backtest Data Requirements catalog, and Backtest Data Readiness gate were already committed and pushed before this session.
- Public Data Downloader extension has been implemented in this session.
- Supported public downloader tasks now include ETHUSDC/BTCUSDC/ETHBTC 1m klines and ETHUSDC aggTrades/trades.
- Targeted downloader/readiness tests passed.
- Full local test suite passed with `pytest tests/ -q` before handoff update.
- Real CLI dry-run commands passed without `--execute` and without downloads.
- No real downloads were executed.
- Raw market data remains outside the repository by contract and downloader target path.
- No raw data was committed.
- No Binance trading API, API keys, engine, strategy, backtest implementation, paper trading, testtrade, live trading, fake trades, or fake reports exist.
- Backtest button is visible but disabled.
- Live/Paper/Testtrade remain locked.

Safe continuation rule:
- Read AGENTS.md, handoff directory, and git status before continuing.
- Next safe implementation/action is a user-approved tiny public-data execute smoke for the missing ETHUSDC day, followed by audit/readiness re-check.
- Keep Live/Paper/Testtrade locked unless the explicit project contract gates are satisfied later.
