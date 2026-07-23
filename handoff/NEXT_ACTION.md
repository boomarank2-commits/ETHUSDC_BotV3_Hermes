# Next Action – Protocol-v3-Blocker-Remediation

Stand: 2026-07-23

## Dauerauftrag und Abschlussbedingung

Wenn der Nutzer spaeter nur `mach weiter` schreibt, bedeutet das:

1. am unten dokumentierten kleinsten Protocol-v3-Engpass fortsetzen;
2. beweisen, welche der 33 Aufgaben im echten UI-Backtestpfad ausgefuehrt
   werden, statt nur ihre Dateien oder Tests zu zaehlen;
3. fehlende Produktionsintegration minimal und getestet schliessen;
4. den realistischen monatlichen Research-/Backtestprozess erneut ausfuehren;
5. bei weniger als `+3 USDC/Tag` Reports und Ablehnungsgruende auswerten und
   das naechste kleinste, belegte Folgeticket bearbeiten.

Der Gesamtauftrag ist erst abgeschlossen, wenn mindestens `+3 USDC/Tag` nach
Fees, Slippage und Binance-Regeln im vorgeschriebenen 365-Tage-Prozess kausal
nachgewiesen sind und alle Quality-Gates bestehen. `33/33 DONE_100`, gruene
Tests, ein technisch erfolgreicher Lauf oder ein positiver Trainingswert sind
allein keine Abschlussbedingung.

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
4. Teilweise erledigt: realer Drei-Markt-Pfad, exakte 6x60-Folds,
   permanenter Trial-Ledger, Task-16-Matrix, PBO und DSR laufen produktiv.
   Origin 1 ist über acht Zyklen ausgeführt.
5. Erledigt: Die versionierte, result-unabhängige
   Cross-Cycle-Origin-Auswahl verlangt exakt acht Cycles, vereinigt alle 96
   Profile und berechnet PBO sowie DSR auf der vollständigen Matrix neu.
6. Nächster Engpass: Den Production-Finalistenpfad um die vollständige
   Quality-Evidenz für zwei Finalisten erweitern. Benötigt werden insbesondere
   WFV-Fold-Metriken und Equity, Full-Training/Validation, Joint- und
   Slippage-Stress, Parameterstabilität sowie rollende, zeitliche und
   Regime-Evidenz. Daraus pro Cycle echte Task-15-Entscheidungen erzeugen.
7. Danach Origin 1 genau einmal über alle acht Cycles unter der dann finalen
   Pipelinegeneration neu ausführen und den Cross-Cycle-Selector ausführen.
   Die alten `950c763`-Artefakte nicht umetikettieren oder wiederverwenden.
8. Offen: Task-13-Transaktionscheckpoint für den vollständigen
   Origin-Work-Unit sowie echte Tasks 19 bis 27 und Origins 2 bis 12 anbinden.
   Keine Testfixtures als reale Evidenz verwenden.
9. Vollständige Tests, Handoff, Push und grüne GitHub-CI verlangen.
10. Erst danach den create-only Task-33-Preflight erneut ausführen. Nur
    `READY_FOR_FULL_RESEARCH_RUN` darf den restlichen historischen
    Monatsprozess öffnen.

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
- technische GitHub-CI: Run `29987377105`, grün

## Neuer reproduzierbarer Zwischenstand

- Implementierungs-Head: `950c7633745bbd0583e8b495499df4352eb9d708`
- vollständige lokale Suite: `1.365/1.365` grün
- GitHub Review CI: Run `29993051021`, grün
- Adapterplan:
  `C:\TradingBot\data\ETHUSDC_BotV3_Hermes\runtime\protocol_v3\production_outer_adapter\adapter-plan-54a63a5.json`
- aktuelle Origin-1-Cycles:
  `cycle-o01-c01-950c763.json` bis `cycle-o01-c08-950c763.json`
- permanente native Trials: `107`
- beste Entwicklung: `+0,017724789686 USDC/Tag`, 33 Trades,
  DSR nicht bestanden
- Ziel `+3 USDC/Tag`: nicht erreicht
- vollständiger Bericht:
  `handoff/PROTOCOL_V3_PRODUCTION_ADAPTER_IN_PROGRESS_2026-07-23.md`

## Cross-Cycle-Zwischenstand

- result-unabhängiger Production-Origin-Selector: implementiert
- vollständige lokale Suite: `1.367/1.367` grün
- alte Origin-1-Cycles: wegen alter Code-/Pipelineidentität absichtlich
  unbrauchbar für die neue Generation
- aktueller kleinster Engpass: vollständige Production-Quality-Evidenz und
  daraus gebundene Task-15-Entscheidungen
- Bericht:
  `handoff/PROTOCOL_V3_CROSS_CYCLE_ORIGIN_SELECTION_2026-07-23.md`

## Aktualisierung nach realer Finalisten-Qualität

Der frühere Punkt 6 ist erledigt. Vollständige training-only Quality-Evidenz
für beide Finalisten, die interne Task-15-Neuberechnung nach der vollständigen
96-Profil-Matrix und der kompakte, mathematisch unveränderte DSR-Batch sind in
Commit `c5e9c0997385462148d3b7ba86e51db735edb6f1` implementiert.

Die nächste zulässige Arbeit ist jetzt:

1. den vollständigen Task-13-Origin-Work-Unit mit Registration, Claim,
   Pre-Run-Manifest, Run-Fingerprint, Pipeline-/Code-/Ledger-Bindung,
   acht Cycle-Slots und Origin-Selection-Slot implementieren;
2. Crash-/Resume-, Stale-Identity-, Teilartefakt- und Exactly-once-Tests
   ausführen;
3. Origin 1 unter
   `protocol_v3_pipeline_sha256:9e5e6e9d9491ac7fffd5dc23ce17d7bdf9f78a50cd9c9db587c1dcd924f5fe41`
   neu ausführen;
4. danach Tasks 19 bis 27 und Origins 2 bis 12 anbinden.

Die Artefakte aus `950c763` und `8fcfb6e` niemals wiederverwenden oder
umetikettieren. `+3 USDC/Tag` ist weiterhin nicht nachgewiesen; Bot, Paper,
Testtrade, Live und Adoption bleiben gesperrt.

## Aktualisierung nach Task-13-Origin-Work-Unit

Die Punkte 1 und 2 der vorigen Aktualisierung sind erledigt. Der neue
restartfähige Origin-Controller ist in Commit
`d4ce888a27eaacc57f0a0200e355426688c780e0` implementiert; die reale
Origin-/Fold-Zeitfensterbindung ist in
`bf9587170ab64073190529039619ec11c7dc1313` korrigiert.

Nächste zulässige Reihenfolge:

1. neuen Task-33-Preflight für die Pipelinegeneration
   `protocol_v3_pipeline_sha256:ed966a90c73750a6316d011f239e713d0dcd00669520166bbae8f37275285ebf`
   erzeugen;
2. Origin 1 unter dieser Generation mit
   `scripts/run_protocol_v3_production_origin_work_unit.py` ausführen;
3. Origin-Auswahl, Quality-Gates, DSR, PBO und Abstand zu `3 USDC/Tag`
   diagnostizieren;
4. Tasks 19 bis 27 und Origins 2 bis 12 an denselben transaktionalen
   Work-Unit anbinden;
5. erst danach Task-33-Preflight, UI-Start und vollständigen Monatsprozess
   erneut prüfen.

Alte Cycle-Artefakte niemals umetikettieren. Keine Gate-Lockerung, keine
Fake-Evidenz und keine Paper-/Testtrade-/Live-Freigabe.
