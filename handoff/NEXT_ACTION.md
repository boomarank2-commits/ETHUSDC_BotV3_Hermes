# Next Action – Protocol-v3-Blocker-Remediation

Stand: 2026-07-22

## Ausgangslage

Die Implementierungssequenz 1 bis 33 ist vollständig abgearbeitet. Aufgabe 33 endete rechtmäßig mit `BLOCKED_INSUFFICIENT_TRIAL_HISTORY`; dies ist kein Backtest-Pass und keine Bot-Freigabe.

Die UI-Integrationsdiagnose ist ebenfalls abgeschlossen: Der Hauptbutton liest den echten Task-33-Preflight, zeigt 33/33 und startet bei Blockern keinen Protocol-v2-Ersatzlauf. Bericht: `handoff/PROTOCOL_V3_UI_BACKTEST_INTEGRATION_2026-07-22.md`.

Vor neuer Arbeit vollständig lesen:

1. `AGENTS.md`
2. `handoff/CURRENT_STATUS.md`
3. `handoff/PROTOCOL_V3_TASK_33_2026-07-22.md`
4. `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
5. `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`
6. `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`
7. `configs/protocol_v3_pipeline_contract.json`
8. `configs/protocol_v3_task33_contract.json`

## Nächster zulässiger Auftrag

Nur nach ausdrücklicher Nutzerfreigabe ein neues Remediation-Issue anlegen. Nicht den blockierten Research-Lauf starten.

Die Remediation muss in dieser Reihenfolge erfolgen:

1. Historische Trial-Evidenz ist untersucht: Kandidatenparameter sind rekonstruierbar, aber Seeds und `daily_net_mtm_usdc` fehlen. Den Lower-Bound-Status nicht entfernen und 180 beobachtete Zeilen niemals automatisch als 180 unabhängige Trials zählen.
2. Nur auf Basis des belegten Ergebnisses eine separate Architekturentscheidung vorbereiten. Keine Änderung der Trial-Multiplicity- oder DSR-Regeln ohne Nutzerfreigabe und neue Vertragsgeneration.
3. Den produktiven aktiven Lookback-Satz und die exakte `HorizonPolicy` für Labelhorizont, maximale Haltedauer und Pending-Latenz versioniert einfrieren; sie muss mit den zulässigen Specialist-Haltedauern widerspruchsfrei sein.
4. Den realen Produktionsadapter vom Drei-Markt-Rohdatenbestand durch Task 15 bis 27, zwölf Origins und Task-13-Resume implementieren. Keine Testfixtures als reale Evidenz verwenden.
5. Vollständige Tests, Handoff, Push und grüne GitHub-CI verlangen.
6. Erst danach den create-only Task-33-Preflight erneut ausführen. Nur `READY_FOR_FULL_RESEARCH_RUN` darf den rechenintensiven historischen Monatsprozess öffnen.

## Unveränderliche Grenzen

- keine Gate-, Ranking-, Feature-, Kosten- oder Suchraumlockerung
- keine erfundenen Trial-Identitäten oder Tagesreihen
- keine Umdeutung des verbrauchten historischen OOS in frische/finale Evidenz
- kein echter `sealed_final_holdout`
- keine Orders, Trading-API, privaten Endpunkte oder API-Keys
- kein Paper, Testtrade, Live, Adoption oder Botstart

## Reproduzierbarer Startnachweis

- Task-33-Report: `C:\TradingBot\data\ETHUSDC_BotV3_Hermes\runtime\protocol_v3\task33\task33-preflight-713ccbaa3b11-ea4cb7750cea-f1782ba70088.json`
- Reportdigest: `846778919948f80019efc19ae131b17604a35f269c3481a07030da08d26cc616`
- Trial-Ledger-Head: `f1782ba7008880e70dd18ffdb48c3c033e732a232f7ccacdbeb72083e337b476`
- technischer Task-33-Commit: `713ccbaa3b11e3ed9d2b5e92325e7c070e3aad6a`
- technische GitHub-CI: `29928845971`, grün
