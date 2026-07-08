# Next Action

Smallest possible next step:
- Close any currently open dashboard window and restart it so the new Python code is loaded.

Required user action if UI is already open:
- UI schließen und neu starten erforderlich.

UI start command:
- `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`

Recommended next mini-ticket:
- "Run UI dry-run last-run smoke and confirm Last Data Prep Run survives Refresh Status"

Acceptance direction for that next ticket:
- Start fresh UI after this commit.
- Confirm top area initially shows `Last data prep run status: never_run`.
- Click `Daten prüfen (Dry-run)`.
- Confirm it shows `running` while active.
- Confirm after completion it shows `finished`, mode `dry_run`, duration, task counts, readiness before/after, and next blocker.
- Click `Refresh Status`.
- Confirm the Last Run display remains `finished` and does not reset to idle/never_run.
- Confirm buttons re-enable after completion.
- Do not execute real downloads unless explicitly approved.
- If executing downloads later, use `Backtest starten / Daten laden`; watch Last Run for mode `execute` and download result count.
- Do not create profit, trade, candidate, or backtest result fields.
- Do not implement engine, strategy, exchange, paper, testtrade, or live trading.
- Keep Live/Paper/Testtrade locked.

Current external data observation:
- ETHUSDC 1m has 1094 ZIP and 1094 CHECKSUM files.
- BTCUSDC/ETHBTC 1m and ETHUSDC aggTrades/trades folders were missing in the read-only check.
- Readiness is expected to remain blocked until those data/source requirements and unimplemented collectors/engine are addressed.

Do not start real backtest, paper trading, testtrade, live trading, strategy, engine, Binance trading API, or order work without explicit approval and required gates.
