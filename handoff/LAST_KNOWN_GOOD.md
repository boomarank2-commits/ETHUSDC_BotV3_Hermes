# Last Known Good

Last known safe state:
- Phase 1 skeleton, strict schema validation, data catalog/audit foundation, local data inventory scanner, inventory status command, raw-data directory contract, raw-data manifest schema, public ETHUSDC 1m kline downloader, and first local tkinter control UI were already committed and pushed before this session.
- Local ETHUSDC 1m ZIP audit gate has been implemented in this session.
- Targeted audit/dashboard tests passed.
- Full local test suite passed with `pytest tests/ -q` before handoff update.
- Real local dashboard snapshot audit command succeeded.
- Real local audit status: 1094 ZIP, 1094 CHECKSUM, 1094 complete UTC days, missing `2026-07-07`, status `incomplete`, `backtest_ready=false`.
- Raw market data remains outside the repository by contract and downloader target path.
- No raw data was committed.
- No Binance trading API, API keys, engine, strategy, backtest implementation, paper trading, testtrade, live trading, fake trades, or fake reports exist.
- Backtest button is visible but disabled.
- Live/Paper/Testtrade remain locked.

Safe continuation rule:
- Read AGENTS.md, handoff directory, and git status before continuing.
- Next safe implementation is completing/auditing data coverage, not backtest or trading execution.
- Keep Live/Paper/Testtrade locked unless the explicit project contract gates are satisfied later.
