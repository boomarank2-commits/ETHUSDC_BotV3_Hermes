# Current Status

Status: Downloader input contract and local raw-data directory contract implemented and verified locally.

Completed in this session:
- Added a raw-data directory contract module for future downloader target paths.
- Defined the only planned raw-data root: `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Added repository guard rejecting raw roots inside the repository.
- Added functions to compute expected per-source raw target paths from the catalog.
- Added validation that expected target paths stay outside the repository.
- Added context-only safety checks for BTCUSDC and ETHBTC.
- Added ETHUSDC-only primary trading symbol check.
- Added locked live/paper/testtrade status in the contract output.
- Added docs describing allowed raw root, path shape, expected future manifest intent, and explicit non-goals.
- Added unit tests for raw root validation, ETHUSDC 1m kline path, context-only sources, all catalog sources, no repository paths, no forbidden result fields, locked execution modes, and forbidden file paths.

Explicitly not completed:
- No downloader.
- No Binance client or API integration.
- No API keys or `.env`.
- No real market data files.
- No raw data directories created.
- No market data file reads.
- No trading engine.
- No strategy.
- No backtest code.
- No UI.
- No Paper-Trading.
- No Testtrade.
- No Live-Trading.
- No fake trades.
- No fake reports.
- No candidate adoption.

Validation performed:
- Initial git status was clean.
- New TDD tests failed first because `raw_data_contract` module did not exist.
- Targeted raw-data contract tests passed.
- Full local test suite passed before handoff update with `pytest tests/ -q`.

Current safe project direction:
- The project now has a strict local target path contract for future raw data without creating directories, downloading data, reading market data, calling Binance, or running a backtest.
