# Blockers

Current blockers:
- Backtest Data Readiness remains blocked until missing public/context data and required gates are satisfied.
- ETHUSDC 1m local audit/readiness was previously incomplete: 1094 complete UTC days found, 1095 required.
- Missing ETHUSDC UTC day previously reported by audit: `2026-07-07`.
- Read-only check in this session saw ETHUSDC 1m 1094 ZIP and 1094 CHECKSUM files.
- Read-only check saw BTCUSDC 1m folder missing / 0 ZIP / 0 CHECKSUM.
- Read-only check saw ETHBTC 1m folder missing / 0 ZIP / 0 CHECKSUM.
- Read-only check saw ETHUSDC aggTrades folder missing / 0 ZIP / 0 CHECKSUM.
- Read-only check saw ETHUSDC trades folder missing / 0 ZIP / 0 CHECKSUM.
- exchange_info fetch/downloader is still not implemented.
- bookTicker live collector is not implemented and has 0/30 days.
- orderbook snapshot live collector is not implemented and has 0/30 days.
- Backtest engine is not implemented and remains intentionally locked.
- A completed data-prep workflow or completed download is not a backtest result and is not evidence of profit.
- Live trading remains locked by project contract.
- Paper trading remains locked.
- Testtrade remains locked.
- No raw market data should be stored inside the repository.

Operational blocker for current open UI:
- If the dashboard window was opened before the latest commit, it is running old Python code. UI schließen und neu starten erforderlich.

Not blockers:
- Local tkinter control UI exists.
- UI starts via `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`.
- UI now has a data-preparation workflow.
- UI now has structured progress status and a visible progressbar.
- UI now keeps an in-session Last Data Prep Run status that survives Refresh Status.
- Backtest start button is visible and enabled for data preparation only when no workflow is running.
- Data preparation runs asynchronously and reports structured progress.
- Public downloader can plan/dry-run/supported-execute readiness tasks.
- Target paths inside the repository are rejected by the downloader.
