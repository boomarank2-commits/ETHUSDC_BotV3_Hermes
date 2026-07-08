# Blockers

Current blockers:
- Backtest Data Readiness remains blocked until missing public/context data and required gates are satisfied.
- ETHUSDC 1m local audit/readiness was previously incomplete: 1094 complete UTC days found, 1095 required.
- Missing ETHUSDC UTC day previously reported by audit: `2026-07-07`.
- BTCUSDC 1m context klines are missing unless a UI/execute data prep run downloads them.
- ETHBTC 1m context klines are missing unless a UI/execute data prep run downloads them.
- ETHUSDC aggTrades are missing/diagnostic-only unless a UI/execute data prep run downloads them.
- ETHUSDC trades are missing/diagnostic-only unless a UI/execute data prep run downloads them.
- exchange_info fetch/downloader is still not implemented.
- bookTicker live collector is not implemented and has 0/30 days.
- orderbook snapshot live collector is not implemented and has 0/30 days.
- Backtest engine is not implemented and remains intentionally locked.
- Live trading remains locked by project contract.
- Paper trading remains locked.
- Testtrade remains locked.
- No raw market data should be stored inside the repository.

Not blockers:
- Local tkinter control UI exists.
- UI starts via `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`.
- UI now has a data-preparation workflow.
- Backtest start button is visible and enabled for data preparation only.
- Data preparation runs asynchronously and logs progress.
- Public downloader can plan/dry-run/supported-execute readiness tasks.
- Target paths inside the repository are rejected by the downloader.
