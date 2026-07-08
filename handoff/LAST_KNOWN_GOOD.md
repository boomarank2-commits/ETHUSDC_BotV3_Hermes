# Last Known Good

Last known safe state:
- Phase 1 skeleton, strict schema validation, data catalog/audit foundation, local data inventory scanner, inventory status command, raw-data directory contract, raw-data manifest schema, and public ETHUSDC 1m kline downloader were already committed and pushed before this session.
- First local standard-library tkinter control UI has been implemented locally in this session.
- Full local test suite passed before handoff update with `pytest tests/ -q`.
- Dashboard state and dashboard module import smoke commands succeeded.
- Downloader dry-run command succeeded without writing data.
- Raw market data remains outside the repository by contract and downloader target path.
- No raw data was committed.
- No Binance trading API, API keys, engine, strategy, backtest implementation, paper trading, testtrade, live trading, fake trades, or fake reports exist.
- Backtest button is visible but disabled.
- Live/Paper/Testtrade remain locked.

Safe continuation rule:
- Read AGENTS.md, handoff directory, and git status before continuing.
- Next safe implementation is a data audit ticket, not backtest or trading execution.
- Keep Live/Paper/Testtrade locked unless the explicit project contract gates are satisfied later.
