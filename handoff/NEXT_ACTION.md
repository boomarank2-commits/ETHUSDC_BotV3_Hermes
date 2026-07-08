# Next Action

Smallest possible next step:
- Restore or download the missing public ETHUSDC 1m ZIP and CHECKSUM for `2026-07-07` into the external raw-data folder, then re-run the local audit.

Recommended next mini-ticket:
- "Complete ETHUSDC 1m local kline coverage to 1095 audited UTC days"

Acceptance direction for that next ticket:
- Use only local/external raw-data target `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Do not store raw data inside the repository.
- If downloading, use only the existing public downloader and explicit user-approved `--execute`.
- Verify ZIP/CHECKSUM presence and UTC-day coverage honestly via `build_kline_audit_summary`.
- Do not create profit, trade, candidate, or backtest result fields.
- Do not implement engine, strategy, exchange, paper, testtrade, or live trading.
- Keep Live/Paper/Testtrade locked.

Current local audit command shape:
- `PYTHONPATH=src python - <<'PY' ... build_dashboard_snapshot(Path.cwd(), Path('C:/TradingBot/data/ETHUSDC_BotV3_Hermes')) ... PY`

UI start command:
- `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`

Optional Windows helper:
- `./scripts/start_dashboard.ps1`

After 1095 complete UTC days are audited:
- Next safe code step is not strategy optimization.
- Build the smallest read-only backtest input-preparation contract: load audited ETHUSDC 1m klines into deterministic in-memory structures, enforce train/blind split boundaries, and still produce no profit/trade/candidate claims until a real engine exists.

Do not start real backtest, paper trading, testtrade, live trading, strategy, engine, Binance trading API, or order work without explicit approval and required gates.
