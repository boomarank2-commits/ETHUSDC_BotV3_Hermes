# Last Known Good

Last known safe state:
- Phase 1 skeleton, strict schema validation, data catalog/audit foundation, local data inventory scanner, inventory status command, raw-data directory contract, raw-data manifest schema, public data downloader, local tkinter control UI, ETHUSDC 1m ZIP audit gate, Backtest Data Requirements catalog, and Backtest Data Readiness gate were already committed and pushed before this session.
- UI Backtest Start data-preparation workflow has been implemented in this session.
- UI Backtest Start is clickable but data-preparation-only.
- Real engine start remains locked.
- Targeted UI/controller tests passed.
- Full local test suite passed with `pytest tests/ -q` before handoff update.
- No real downloads were executed in this session.
- Raw market data remains outside the repository by contract and downloader target path.
- No raw data was committed.
- No Binance trading API, API keys, engine, strategy, backtest implementation, paper trading, testtrade, live trading, fake trades, or fake reports exist.
- Live/Paper/Testtrade remain locked.

Safe continuation rule:
- Read AGENTS.md, handoff directory, and git status before continuing.
- Next safe action is a UI data-preparation smoke, not real backtest execution.
- Keep Live/Paper/Testtrade locked unless the explicit project contract gates are satisfied later.
