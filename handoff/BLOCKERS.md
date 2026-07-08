# Blockers

Current blockers:
- Backtest Data Readiness remains blocked.
- ETHUSDC 1m local audit/readiness is incomplete: 1094 complete UTC days found, 1095 required.
- Missing ETHUSDC UTC day previously reported by audit: `2026-07-07`.
- BTCUSDC 1m context klines are missing. Downloader support now exists, but download was not executed.
- ETHBTC 1m context klines are missing. Downloader support now exists, but download was not executed.
- ETHUSDC aggTrades are missing/diagnostic-only. Downloader support now exists, but download was not executed.
- ETHUSDC trades are missing/diagnostic-only. Downloader support now exists, but download was not executed.
- exchange_info fetch/downloader is still not implemented.
- bookTicker live collector is not implemented and has 0/30 days.
- orderbook snapshot live collector is not implemented and has 0/30 days.
- Backtest engine is not implemented and remains intentionally blocked.
- Live trading remains locked by project contract.
- Paper trading remains locked.
- Testtrade remains locked.
- No mutable runtime truth should be created until explicitly approved.
- No raw market data should be stored inside the repository.

Not blockers:
- Local tkinter control UI exists.
- UI starts via `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`.
- UI can show Backtest Data Readiness report and per-source statuses.
- Public downloader can now plan/dry-run supported readiness tasks.
- Public downloader supports ETHUSDC/BTCUSDC/ETHBTC 1m klines and ETHUSDC aggTrades/trades.
- Backtest button is visible and disabled with an honest reason.
- Dry-run remains default.
- `--execute` is required for real downloads.
- Target paths inside the repository are rejected.
