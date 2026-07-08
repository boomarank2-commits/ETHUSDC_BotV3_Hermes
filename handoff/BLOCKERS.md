# Blockers

Current blockers:
- Backtest Data Readiness is blocked.
- ETHUSDC 1m local audit/readiness is incomplete: 1094 complete UTC days found, 1095 required.
- Missing ETHUSDC UTC day previously reported by audit: `2026-07-07`.
- BTCUSDC 1m context klines are missing.
- ETHBTC 1m context klines are missing.
- ETHUSDC aggTrades downloader/coverage is missing; current status diagnostic-only.
- ETHUSDC trades downloader/coverage is missing; current status diagnostic-only.
- exchange_info fetch/downloader is missing.
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
- UI can refresh status and count existing external ETHUSDC 1m ZIP/CHECKSUM files.
- UI can show real local ETHUSDC 1m ZIP audit status.
- UI can show Backtest Data Readiness report and per-source statuses.
- UI can start downloader dry-run or explicit `--execute` for public ETHUSDC 1095-day downloads.
- Backtest button is visible and disabled with an honest reason.
- Public ETHUSDC 1m kline downloader remains dry-run by default.
- Target paths are outside the repository.
- Fee/slippage currently exist only as conservative/config-model readiness entries, not account-specific claims.
