# Current Status

Status: Dashboard operator visibility was fixed in the third UI-debug pass. The likely user-facing freeze was not only missing file-progress fields; the UI still presented a diagnostic-heavy screen, the obvious user button was the dry-run/check path, and Refresh/finish could make the top status look idle again. The dashboard is now operator-first.

Latest completed changes:
- Primary user button is now `Daten prüfen & fehlende Daten laden` and calls `execute=True`.
- Secondary user button is now `Nur prüfen ohne Download` and calls `execute=False`.
- Top UI simplified to:
  - Bot-Status
  - Datenstatus
  - Gesamtfortschritt
  - Aktueller Vorgang
  - Dateien
  - Laufzeit
  - Letzter Lauf
  - Nächster Blocker
  - Backtest lock message
- Long raw diagnostic status is no longer dominant in the visible UI. UI uses concise `format_operator_summary_for_display()`.
- Refresh no longer overwrites active runtime display with idle.
- After a finished/failed run, top status remains `Fertig` or `Fehler`.
- Heartbeat remains visible during active thread and warns after 10/60 seconds without file events.
- START_DASHBOARD.bat created for double-click startup.

Local UI smoke performed:
- Tkinter root started successfully.
- DashboardApp instantiated locally.
- `Nur prüfen ohne Download` button invoked through the UI object.
- UI transitioned to finished.
- Last Run showed `finished / dry_run`.
- Summary contained `Dry-run finished. No downloads executed.`
- Refresh preserved the finished Last Run display.

External data counts observed read-only:
- ETHUSDC 1m: 1094 ZIP / 1094 CHECKSUM / 2189 files; newest `manifest.json`, mtime `2026-07-07T23:05:25`.
- BTCUSDC 1m: missing / 0.
- ETHBTC 1m: missing / 0.
- ETHUSDC aggTrades: missing / 0.
- ETHUSDC trades: missing / 0.

Downloads executed in this session:
- No real downloads.
- Only dry-run UI/controller smoke.

Verification before handoff update:
- Targeted tests green.
- `pytest tests/ -q` green.

Safety unchanged:
- No Backtest engine.
- No strategy.
- No trades.
- No profit fields.
- No Binance trading API.
- No API keys.
- No orders.
- Live/Paper/Testtrade locked.
