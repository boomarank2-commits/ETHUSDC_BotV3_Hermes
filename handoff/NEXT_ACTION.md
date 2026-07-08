# Next Action

User action required:
- Close any currently open dashboard window.
- Start the dashboard using the new double-click file:
  - `START_DASHBOARD.bat`

Expected UI behavior:
1. The primary button is now `Daten prüfen & fehlende Daten laden`.
   - This is the real public-data preparation path with `execute=True`.
2. The secondary button is `Nur prüfen ohne Download`.
   - This is dry-run only with `execute=False`.
3. First smoke should be dry-run:
   - click `Nur prüfen ohne Download`.
   - expect Bot-Status to move to checking/running and then `Fertig`.
   - expect Last Run to show finished/dry_run.
   - expect summary: no downloads executed.
   - click Refresh and confirm Last Run remains visible.
4. Only after dry-run UI is clear, use `Daten prüfen & fehlende Daten laden` if the user wants real downloads.

Do not start large BTCUSDC/ETHBTC downloads unless the user explicitly wants to continue data acquisition.

Recommended next mini-ticket:
- Add a safe small execute-smoke mode that can target exactly one missing ETHUSDC day or one controlled file, instead of starting the full data acquisition plan.
