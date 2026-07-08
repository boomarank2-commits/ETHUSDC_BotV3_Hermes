# Current Status

Status: UI-Datenvorbereitung hat jetzt Datei-Fortschritt und Heartbeat-Anzeige für laufende Datenläufe. Die wahrscheinlichste Nutzerwahrnehmung "eingefroren" wurde adressiert: ein großer Download-Task wird nicht mehr nur als einzelner langer Task dargestellt, sondern liefert ZIP/CHECKSUM-Datei-Events und die UI aktualisiert während aktiver Threads ca. jede Sekunde `elapsed_seconds`.

Completed in latest session:
- Public downloader erweitert:
  - `execute_public_download_task(..., progress_callback=None)`.
  - pro geplantem ZIP und CHECKSUM ein Progress-Event.
  - Statuswerte: `planned`, `skipped_existing`, `downloading`, `downloaded`, `failed`.
  - File-Felder: `planned_file_count`, `current_file_index`, `current_file_name`, `completed_file_count`, `skipped_file_count`, `downloaded_file_count`, `failed_file_count`.
- UI Controller erweitert:
  - leitet Downloader-File-Events an Dashboard weiter.
  - Runtime-Status enthält File-Felder und `elapsed_seconds`.
  - `build_data_prep_heartbeat_status(...)` für sichtbare 1s-Heartbeat-Updates.
  - Dry-run Last Run sagt klar: `Dry-run finished. No downloads executed.`
- Dashboard erweitert:
  - speichert aktuellen Runtime-Status.
  - zeigt Heartbeat während aktivem Thread.
  - zeigt Datei x/y, Dateiname, skipped/downloaded/failed und elapsed seconds.
  - Buttons bleiben während Lauf gesperrt und werden nach Laufende aktiviert.
- Dashboard Snapshot/Text erweitert:
  - Last Data Prep Run zeigt Datei-Zähler.
- Dokumentation aktualisiert.

Local diagnosis:
- Dashboard-Prozess: kein laufender `ethusdc_bot.ui.dashboard` Prozess per `ps` sichtbar.
- Falls beim Nutzer eine UI bereits geöffnet ist, muss sie geschlossen und neu gestartet werden, damit neuer Code geladen wird.
- `Backtest starten / Daten laden` ruft weiterhin `_start_data_preparation(execute=True)` auf.
- `Daten prüfen (Dry-run)` bleibt nicht-downloadend.
- `run_data_update_plan_async` legt Exceptions in `result_container["error"]` ab und loggt sie; Dashboard übernimmt sie in Last Run failed.

External data counts observed before/after this session, read-only:
- ETHUSDC 1m: 1094 ZIP, 1094 CHECKSUM, latest `manifest.json` mtime `2026-07-07T23:05:25`.
- BTCUSDC 1m: folder missing / 0 ZIP / 0 CHECKSUM.
- ETHBTC 1m: folder missing / 0 ZIP / 0 CHECKSUM.
- ETHUSDC aggTrades: folder missing / 0 files.
- ETHUSDC trades: folder missing / 0 files.

Downloads executed in this session:
- No real execute download was run.
- Only dry-run controller smoke was run.

Dry-run smoke:
- `execute False`
- Last status: `finished`
- Last mode: `dry_run`
- Download results count: `0`
- Summary: `Dry-run finished. No downloads executed...`
- Readiness: `blocked -> blocked`

Verification:
- Targeted tests green.
- Full `pytest tests/ -q` green before handoff update.

Safety:
- No Backtest engine.
- No strategy.
- No trades.
- No profit fields.
- No Binance trading API.
- No API keys.
- Live/Paper/Testtrade locked.
