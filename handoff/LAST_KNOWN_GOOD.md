# Last Known Good

Last known safe state:
- Dashboard is operator-first and data-preparation-only.
- Main dashboard progress represents persistent local data state via `overall_data_progress_pct`.
- Current run progress is separately represented via `current_run_progress_pct` and operator text.
- Restart/refresh does not overwrite local data progress with idle runtime 0%.
- Primary button `Daten prüfen & fehlende Daten laden` calls execute=True.
- Secondary button `Nur prüfen ohne Download` calls execute=False.
- Visible UI shows concise fields including Bot-Status, Datenstatus, Gesamtdatenstand/Gesamtfortschritt, Aktueller Lauf, Dateien, Laufzeit, Letzter Lauf, Nächster Blocker, Backtest lock.
- Active run heartbeat still shows no-file-event warnings at 10/60 seconds.
- Public readiness counts only non-empty ZIP/CHECKSUM pairs as complete public data.
- `.tmp`, `.part`, ZIP-only, CHECKSUM-only, and 0-byte files are not counted as complete local public data.
- Downloader does not skip 0-byte existing files as complete.
- `START_DASHBOARD.bat` exists and starts only the local dashboard.

Last verified local counts, read-only:
- Total files: 6589.
- `.tmp/.part`: 0.
- 0-byte files: 0.
- Latest mtime: `2026-07-09T15:49:55.882725`.
- ETHUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- BTCUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- ETHBTC 1m: 1096 ZIP / 1096 CHECKSUM / 1096 complete pairs.
- ETHUSDC aggTrades: 7 ZIP / 7 CHECKSUM / 7 complete pairs.
- ETHUSDC trades: 1 ZIP / 1 CHECKSUM / 1 complete pair.
- Dashboard snapshot smoke: `overall_data_progress_pct = 100.0`, `current_run_progress_pct = 0`.

Verification:
- `pytest tests/ -q` passed before handoff update.

Safety:
- No live/paper/testtrade unlock.
- No orders.
- No API keys.
- No trading API.
- No profit/trade/candidate/backtest result fields.
