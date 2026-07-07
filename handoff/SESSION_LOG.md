# Session Log

## 2026-07-07 - Downloader input contract and local raw-data directory contract

Timebox: max 60 minutes.

Actions:
- Verified clean git status before starting.
- Read existing catalog, inventory, inventory status, and handoff context.
- Followed strict TDD.
- Wrote failing tests first for:
  - raw root inside repository rejected,
  - expected raw root outside repository accepted,
  - ETHUSDC 1m klines target path,
  - BTCUSDC/ETHBTC context-only preservation,
  - all catalog sources receiving expected paths,
  - no expected paths inside repository,
  - no profit/backtest/trade/candidate fields,
  - locked live/paper/testtrade execution modes,
  - absence of forbidden downloader/engine/backtest/UI/data paths.
- Implemented `src/ethusdc_bot/data_pipeline/raw_data_contract.py` with path-only contract functions.
- Added `docs/15_RAW_DATA_CONTRACT.md` documenting the allowed raw root, path shape, future manifest intent, and explicit non-goals.
- Ran targeted tests successfully.
- Ran full local tests successfully before handoff update.

Files changed/created:
- `src/ethusdc_bot/data_pipeline/raw_data_contract.py`
- `tests/unit/test_raw_data_contract.py`
- `docs/15_RAW_DATA_CONTRACT.md`
- `handoff/CURRENT_STATUS.md`
- `handoff/SESSION_LOG.md`
- `handoff/NEXT_ACTION.md`
- `handoff/BLOCKERS.md`
- `handoff/LAST_KNOWN_GOOD.md`

Tests executed:
- `pytest tests/unit/test_raw_data_contract.py -q`
- `pytest tests/ -q`

Not done:
- No downloader.
- No Binance API or client.
- No API keys or `.env`.
- No real market data.
- No raw data directories created.
- No market data file reads.
- No trading engine.
- No strategy.
- No backtest code.
- No UI.
- No reports with real or invented results.
- No live/paper/testtrade activation.
