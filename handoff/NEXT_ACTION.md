# Next Action

Required user action:
- UI schließen und neu starten erforderlich, falls sie bereits geöffnet ist.
- Start command from repo root:
  - `PYTHONPATH=src python -m ethusdc_bot.ui.dashboard`

Next smoke test:
1. Click `Daten prüfen (Dry-run)`.
2. Confirm it finishes quickly.
3. Confirm Last Run says:
   - status `finished`
   - mode `dry_run`
   - download results count `0`
   - `Dry-run finished. No downloads executed.`
   - Readiness before/after and next blocker visible.
4. Click `Refresh Status`.
5. Confirm Last Run remains visible and is not reset to `never_run`/`idle`.

Only after that UI smoke:
- If user wants real public data download visibility, click `Backtest starten / Daten laden`.
- Observe:
  - mode Execute/Download.
  - elapsed seconds updates every ~1s.
  - current task remains visible.
  - current file name and file x/y counters update.
  - skipped/downloaded/failed counters update.

Do not start real large downloads unless the user explicitly wants to continue data acquisition.

Recommended next mini-ticket after UI smoke:
- Add an operator-safe small execute smoke that can target one explicitly missing day only, without starting the full BTCUSDC/ETHBTC 1095-day download batch.
