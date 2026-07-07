# Last Known Good

Last known safe state:
- Phase 1 skeleton, strict schema validation, data catalog/audit foundation, local data inventory scanner, local inventory status command, and raw-data directory contract were already committed and pushed before this session.
- Raw data manifest template and validation without download has been implemented locally in this session.
- Full local test suite passed before handoff update with `pytest tests/ -q`.
- Raw market data remains outside the repository by contract and template path.
- No raw data directories were created.
- No downloader, Binance client, API keys, engine, strategy, backtest, UI, paper trading, testtrade, live trading, fake trades, or fake reports exist.

Safe continuation rule:
- Read AGENTS.md, PROJECT_CONTRACT.md, this handoff directory, and git status before continuing.
- Continue only after user approval.
- Keep Live/Paper/Testtrade locked unless the explicit project contract gates are satisfied later.
