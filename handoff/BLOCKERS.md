# Blockers

Current blockers:
- Local ETHUSDC 1m audit is incomplete: 1094 complete UTC days found, 1095 required.
- Missing UTC day currently reported by audit: `2026-07-07`.
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
- UI can start downloader dry-run or explicit `--execute` for public ETHUSDC 1095-day downloads.
- Backtest button is visible and disabled with an honest reason.
- Public ETHUSDC 1m kline downloader remains dry-run by default.
- Real public downloads require explicit `--execute`.
- Target paths are outside the repository.
- Existing files are skipped.
- Optional CHECKSUM files are supported.
- Manifest stays `not_audited` and does not claim profit/trades/backtest/candidate success.
