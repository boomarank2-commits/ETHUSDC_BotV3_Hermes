# Next Action – Protocol-v3-Blocker-Remediation

Stand: 2026-07-23

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

1. Erledigt: Die historische Trial-Evidenz ist untersucht. Kandidatenparameter sind rekonstruierbar, Seeds und `daily_net_mtm_usdc` fehlen.
2. Erledigt mit ausdrücklicher Nutzerfreigabe und neuer Vertragsgeneration: Die 180 beobachteten Zeilen zählen konservativ ausschließlich für die Multiple-Testing-Strafe. Keine Identitäten, Seeds, PnL-Werte oder Tagesreihen wurden erfunden.
3. Erledigt: Der produktive aktive Lookback-Satz und die exakte `HorizonPolicy` sind versioniert, pipelinegebunden und mit den Specialist-Haltedauern widerspruchsfrei eingefroren. Bericht: `handoff/PROTOCOL_V3_RUNTIME_INPUT_FREEZE_2026-07-22.md`.
4. Offen: Den realen Produktionsadapter vom Drei-Markt-Rohdatenbestand durch Task 15 bis 27, zwölf Origins und Task-13-Resume implementieren. Keine Testfixtures als reale Evidenz verwenden.
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

- aktueller Task-33-Report: `C:\TradingBot\data\ETHUSDC_BotV3_Hermes\runtime\protocol_v3\task33\task33-preflight-58290b6870a9-ea4cb7750cea-f1782ba70088.json`
- aktueller Reportdigest: `298d265436dcd61741e87c36938a5e86dfa335f722d9daf7da116dc2fd445cbf`
- aktuelle Pipelinegeneration: `protocol_v3_pipeline_sha256:2ac531ca85d5dd3b3bb83f070b0c4bb4dbab2cfec5c7d9b0d8803626ce2f27d1`
- Trial-Ledger-Head: `f1782ba7008880e70dd18ffdb48c3c033e732a232f7ccacdbeb72083e337b476`
- technischer Multiplicity-Commit: `58290b6870a9272d25d8641b12dd5dc0df165f7e`
- aktueller Status: `BLOCKED_MISSING_FROZEN_RUNTIME_INPUTS`
- einziger Blocker: `MISSING_PRODUCTION_OUTER_ORIGIN_ADAPTER`
- technische GitHub-CI: nach Push abzuwarten
