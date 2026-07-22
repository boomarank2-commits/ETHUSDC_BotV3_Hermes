# Next Action – Protocol v3 Aufgabe 32

Stand: 2026-07-22

## Startbedingung

Die Startbedingung ist erfüllt.

Der Task-31-Dokumentations-Head `bfc379226e1eb69f194790d2fb4e1e2cd210fae9` wurde im normalen GitHub-PR-CI Run `29896580613` vollständig grün geprüft. Der reine Nachweis-Head `1ae2a8124924c1a46694e6347c59446f18eae3e9` wurde zusätzlich in den normalen PR-CI-Runs `29897307921` und `29897330070` vollständig grün geprüft.

Vor der ersten Codeänderung erneut vollständig lesen:

1. `AGENTS.md`
2. `handoff/CURRENT_STATUS.md`
3. `handoff/NEXT_ACTION.md`
4. `handoff/PROTOCOL_V3_TASK_31_2026-07-22.md`
5. `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
6. `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`
7. `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`
8. `configs/protocol_v3_contract.json`
9. `configs/protocol_v3_pipeline_final_contract.json`
10. `configs/protocol_v3_report_contract.json`

## Exakter nächster Auftrag

Ausschließlich Aufgabe 32 umsetzen:

`End-to-End-Parität, Fehler-Injektion und vollständige Abnahme`.

## Bestehende Architektur zuerst prüfen

Keine zweite Pipeline, keinen zweiten Runner und keine zweite Report-/Checkpoint-Wahrheit bauen.

Direkt wiederverwenden und gemeinsam prüfen:

- Task 2 bis 10 für Boundaries, Snapshot, Run-Identity, Execution, Kosten, State und Kontext;
- Task 11 bis 13 für Reports, Artefakte und atomaren HEAD-/Resume-Pfad;
- Task 14 bis 22 für Folds, Kandidaten, Ranking, DSR/PBO und Frozen Bundles;
- Task 23 bis 27 für zwölf Origins, Rotation, Daily MTM, Monthly Gate und Bootstrap;
- Task 28 bis 30 für aktuellen Refit, orderfreien Challenger und UI-Zustände;
- Task 31 für Vorregistrierung, Einmal-Claim, result-blinden Fortschritt, Attestation und genau-einmaliges Report-Opening.

## Pflichtumfang Aufgabe 32

Aufgabe 32 muss fixture-basiert und ohne echtes Finalfenster beweisen:

- einen vollständigen 12-Origin-/365-Tage-Dry-Run über die echte unveränderte Protocol-v3-Kette;
- bitgleiche Ergebnisse bei Erstlauf, Task-13-Resume, Cache-Reuse und deterministischem Replay;
- identische Execution-, Gebühren-, Slippage-, Rundungs-, Kontext-, Boundary-, Seed-, Gate-, Bootstrap- und Reportidentitäten über alle Pfade;
- vollständige Task-31-Vorregistrierungs-, Claim-, Progress-, Checkpoint-, Attestation- und Open-Receipt-Kette auf ausschließlich synthetischen/fixture-basierten Daten;
- keine Outer-Ergebnisrückwirkung in spätere Fits;
- keine Mutation durch UI-Refresh, wiederholte Reads, Restart oder Diagnoseanzeigen;
- eindeutige Fehlerklassifikation und unveränderten letzten atomaren HEAD nach jeder injizierten Störung;
- dass kein Testfixture, Dry-Run oder Fehler-Injektionsobjekt als frischer realer Finalreport, Adoption oder Botstart missverstanden werden kann.

## Pflicht-Fehler-Injektionen

Mindestens systematisch injizieren und fail-closed prüfen:

- Prozessabbruch vor und nach jedem atomaren Write/HEAD-Schritt;
- Teilwrite, fehlendes fsync, fehlendes oder verwaistes Receipt, fremder Temp-Pfad;
- Crash zwischen Finalreport und Open-Receipt sowie zweiter Open-Versuch;
- geänderte Pipelinegeneration, Code-, Snapshot-, Feature-, Kontext-, Exchange-, Execution-, Kosten-, Gate-, Bootstrap-, Seed-, Trial- oder Boundaryidentität;
- fehlender, doppelter, umsortierter oder falscher Origin;
- Datenlücke, Kontextlücke, stale/future/misaligned Watermark und unvollständiger Warmup;
- fremder oder weitergelaufener Trial-Ledger-Head;
- Cache-/Resume-Reuse mit geänderter Registration, Claim, Progress, Checkpoint oder Final-Attestation;
- manipulierte PnL-, Ranking-, Freshness-, Bootstrap-, Support-, Final-, Adoption- oder Sicherheitsclaims;
- Symlink-, Root-Escape-, Duplicate-Key-, NaN-/Infinity- und nichtkanonische-Byte-Angriffe;
- parallele Claim-, Checkpoint-, Attestation- und Open-Races.

## Harte Grenzen

Aufgabe 32 darf nicht:

- ein echtes zukünftiges Finalfenster registrieren oder claimen;
- reale neue 365-Tage-Evidenz verbrauchen;
- den ersten vollständigen Protocol-v3-Research-Lauf starten;
- Task-31-Ergebnisse zur Anpassung von Pipeline, Features, Familien, Ranking, Gates, Kosten, Bootstrap oder Boundaries verwenden;
- Legacy-, Protocol-v2-, Task-27-, Task-28-, Task-29- oder fixture-basierte Evidenz als realen Finalstatus umetikettieren;
- Orders, API-Keys, private Endpunkte, Paper, Testtrade, Live, `active_config.json`, kanonische Adoption oder Botstart öffnen.

## Abnahme

Aufgabe 32 ist erst `DONE_100`, wenn:

1. der fixture-basierte vollständige 12-Origin-/365-Tage-Dry-Run grün ist;
2. Erstlauf, Resume, Cache und Replay bitgleich sind;
3. alle vorgesehenen Fehler-Injektionen fail-closed und reproduzierbar sind;
4. Race-, Teilwrite-, Leakage-, Pfad-, Safety- und Claim-Manipulationen vollständig abgedeckt sind;
5. vollständige Pytest-Suite, Python-Compile, PowerShell-Syntax und Whitespace grün sind;
6. Handoff, `CURRENT_STATUS.md`, `NEXT_ACTION.md` und `docs/41` aktualisiert und gepusht sind;
7. der abschließende GitHub-CI-Lauf des Dokumentations-Heads grün ist.

Aufgabe 33 darf vorher nicht begonnen werden.

## Sicherheitsstatus beim Einstieg

- kein Backtest-, Paper-, Testtrade-, Live- oder Order-Start;
- keine API-Keys, privaten Endpunkte oder Secrets;
- kein echtes Finalfenster registrieren, claimen, ausführen oder öffnen;
- keine kanonische Adoption;
- der Bot darf nicht gestartet werden.
