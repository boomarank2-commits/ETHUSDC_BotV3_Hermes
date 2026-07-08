# Last Known Good

Last known safe state:
- Dashboard is operator-first and data-preparation-only.
- Primary button `Daten prüfen & fehlende Daten laden` calls execute=True.
- Secondary button `Nur prüfen ohne Download` calls execute=False.
- Visible UI shows concise fields: Bot-Status, Datenstatus, Gesamtfortschritt, aktueller Vorgang, Dateien, Laufzeit, Letzter Lauf, Nächster Blocker, Backtest lock.
- Long raw diagnostic snapshot is not the dominant visible UI anymore.
- Active run heartbeat shows no-file-event warnings at 10/60 seconds.
- Refresh does not overwrite active runtime with idle and does not erase Last Run.
- Dry-run UI smoke passed through DashboardApp button invocation.
- `START_DASHBOARD.bat` exists and starts only the local dashboard.
- Tests pass with `pytest tests/ -q`.

Last verified local counts, read-only:
- ETHUSDC 1m: 1094 ZIP / 1094 CHECKSUM.
- BTCUSDC 1m: 0 / missing folder.
- ETHBTC 1m: 0 / missing folder.
- ETHUSDC aggTrades: 0 / missing folder.
- ETHUSDC trades: 0 / missing folder.

Safety:
- No live/paper/testtrade unlock.
- No orders.
- No API keys.
- No trading API.
- No profit/trade/candidate/backtest result fields.
