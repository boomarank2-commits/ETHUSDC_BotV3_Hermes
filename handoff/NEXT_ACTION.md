# Next Action

User action required:
- Restart the dashboard so the new progress separation is loaded.
- Use `START_DASHBOARD.bat`.

Expected UI behavior after restart:
1. The main progress bar shows the persistent local data state, not the current run counter.
2. The summary shows both:
   - `Gesamtdatenstand: xx%`
   - `Aktueller Lauf: yy% seit Start / ...`
3. With the currently observed local data, the dashboard should show all five public readiness rows complete:
   - ETHUSDC 1m: 1095/1095
   - BTCUSDC 1m: 1095/1095
   - ETHBTC 1m: 1096/1095, effectively complete/capped for progress
   - ETHUSDC aggTrades: 7/7
   - ETHUSDC trades: 1/1
4. If a new execute run starts, the current run may begin at 0%, scan, skip existing files, and download only missing files, but this must not reset the main `Gesamtdatenstand` display.

Recommended next mini-ticket:
- Add a tiny UI smoke/integration check that instantiates `DashboardApp` with a fixture local root and asserts the Tk progress bar uses `overall_data_progress_pct` while `task_var` shows current-run progress separately.

Safety reminder:
- Live/Paper/Testtrade remain locked.
- Do not start trading/API/order functionality.
