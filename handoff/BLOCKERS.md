# Blockers

Current blockers:
- User approval required before any next implementation step.
- No complete 1095-day public data download has been run as part of committed code work.
- Downloaded ZIP contents have not been audited.
- Inventory status shows path presence only; it does not validate kline completeness from real files.
- Manifest records download metadata only; it does not prove data quality.
- Live trading remains locked by project contract.
- Paper trading remains locked.
- Testtrade remains locked.
- No mutable runtime truth should be created until explicitly approved.
- No raw market data should be stored inside the repository.

Not blockers:
- Public ETHUSDC 1m kline downloader exists and is dry-run by default.
- Real public downloads require explicit `--execute`.
- Target paths are outside the repository.
- Existing files are skipped.
- Optional CHECKSUM files are supported.
- Manifest stays `not_audited` and does not claim profit/trades/backtest/candidate success.
