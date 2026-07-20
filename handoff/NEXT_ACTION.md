# Next Action – Protocol v3 Aufgabe 30

Stand: 2026-07-20

## Startbedingung

Aufgabe 30 darf erst begonnen werden, wenn der Task-29-Dokumentations-Head mit Abschluss-Handoff, `CURRENT_STATUS.md`, dieser Datei und `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` vollständig gepusht und in GitHub CI grün ist.

Vor der ersten Codeänderung erneut vollständig lesen:

1. `AGENTS.md`
2. `handoff/CURRENT_STATUS.md`
3. `handoff/NEXT_ACTION.md`
4. `handoff/PROTOCOL_V3_TASK_29_2026-07-20.md`
5. `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`
6. `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`
7. `configs/protocol_v3_contract.json`

## Exakter nächster Auftrag

Ausschließlich Aufgabe 30 umsetzen:

`UI und Bedienzustände vollständig anschließen`.

## Bestehende Architektur zuerst prüfen

Vor neuen UI-Dateien oder Controllern vollständig prüfen und bevorzugt erweitern:

- `src/ethusdc_bot/ui/dashboard.py`;
- `src/ethusdc_bot/ui/operator_dashboard.py`;
- `src/ethusdc_bot/ui/dashboard_state.py`;
- `src/ethusdc_bot/ui/backtest_controller.py` und `backtest_display.py`;
- vorhandene Final-, Shadow-, Datenupdate- und Readiness-Controller;
- Task-11-Reportleser und Task-12-Artefaktleser;
- Task-13-Checkpoint-/Resume-Status;
- Task-29-Controller, Evidenz- und Checkpoint-APIs;
- bestehende Startdialog- und Bedienregeln.

Keine zweite Dashboard-, Status-, Controller-, Report-, Checkpoint- oder Runtime-Wahrheit bauen.

## Pflichtumfang Aufgabe 30

Die UI muss:

- genau einen klaren Operatorzustand zur Zeit anzeigen;
- Datenprüfung, Research, historisches Prozess-OOS, aktuellen Refit, Research-Challenger, späteren Finaltest und kanonischen Shadow semantisch getrennt darstellen;
- Aufgabenfortschritt ausschließlich aus `DONE_100/33` anzeigen;
- bei Research Origins, innere Folds, Cycle-/Kandidatenfortschritt und aktuellen Rechenschritt aus kanonischen Checkpoints/Reports anzeigen;
- keine Outer-PnL anzeigen, bevor das jeweilige Outer-Ergebnis vollständig abgeschlossen und publiziert ist;
- Task-27-/28-Historie sichtbar als `NOT_FRESH` und `diagnostic_only` kennzeichnen;
- den Task-29-Research-Challenger klar als orderfreien, nicht adoptionfähigen Diagnosepfad kennzeichnen;
- den manuellen Challenger-Start nur bei vollständig validierter Task-28-Provenienz, passender Pipelinegeneration, öffentlichem Daten-Watermark und gültigem Zeitfenster anbieten;
- bei verspätetem Task-28-Abschluss keinen rückwirkenden Start anbieten, sondern den nächsten Monatsanker anzeigen;
- Start-, Fortsetzen-, Stop-, Refresh- und Öffnen-Aktionen an die vorhandenen Controller weiterreichen;
- nach Neustart den letzten validierten Report-/Checkpointzustand anzeigen, ohne ihn zu verändern;
- jeden deaktivierten Button mit einem konkreten kanonischen Blocker begründen;
- Refresh und wiederholte Darstellung vollständig zustandsneutral halten.

## Bedienzustände

Mindestens getrennt und getestet anzeigen:

- `NOT_STARTED` / keine geeignete Evidenz;
- Daten fehlen, sind stale, zukünftig, versetzt oder noch nicht vollständig geschlossen;
- Research läuft, pausiert, unterbrochen, fehlgeschlagen oder abgeschlossen;
- aktueller Monatsrefit fehlt, läuft, ist verspätet, ergibt `CHAMPION`, `CHALLENGER` oder `CASH`;
- Research-Challenger nicht startbar, startbereit, läuft, pausiert, resume-fähig oder blockiert;
- Finalfenster nicht registriert, noch versiegelt, verbraucht oder final ausgewertet;
- kanonische Adoption nicht erlaubt beziehungsweise später nur aus gültigem Finalreport möglich.

## Harte UI-Sperren

Die UI darf niemals:

- aus Darstellung oder Buttonzustand Orders erzeugen;
- Binance-Private-/Account-Endpunkte oder API-Keys verwenden;
- Paper-, Testtrade- oder Live-Pfade freischalten;
- Task-29-Evidenz an `adopt_for_shadow` übergeben;
- `active_config.json` oder eine handelbare Konfiguration schreiben;
- historische oder sichtbare Forward-Evidenz als frisch beziehungsweise statistisch unterstützt darstellen;
- einen Protocol-v3-Finalstatus ohne neuen versiegelten Finalreport anzeigen;
- Ergebnisse, Trades, PnL, Fortschritt oder Readiness erfinden;
- einen Button allein aufgrund eines nackten Bool-Claims aktivieren.

Pflichtanzeigen bleiben mindestens:

- `Orders: gesperrt`;
- `Paper: gesperrt`;
- `Testtrade: gesperrt`;
- `Live: gesperrt`;
- `Trading-API/private Endpunkte: nicht verwendet`;
- `Canonical adoption: nicht zulässig`, solange kein späterer gültiger Finalpfad vorliegt;
- `Botstart: nicht erlaubt`.

## Pflicht-Negativtests

Mindestens testen:

- fehlende, manipulierte oder falsche Task-28-/Task-29-Provenienz aktiviert keinen Button;
- stale, zukünftiger, versetzter oder lückenhafter Drei-Markt-Watermark blockiert Challenger-Start;
- abgelaufenes Bundle oder verspäteter Refit zeigt den nächsten Anker statt rückwirkender Aktivierung;
- unvollständiger Report, Teilwrite, falscher Root, Symlink oder falscher Checkpoint-Head blockiert vor dem Lesen beziehungsweise Anzeigen;
- Task-29-Refresh oder mehrfaches Öffnen verändert weder State-, Signal-, Fill- noch Ledgerhash;
- UI-Neustart rekonstruiert ausschließlich den letzten validierten Zustand;
- laufende Worker verhindern Doppelstart und Race zwischen Workerende und UI-Apply;
- vorzeitig angezeigte Outer-PnL, Fake-Fortschritt oder Fake-Ergebnis wird verhindert;
- manipulierte Freshness-, Support-, Adoption-, Final-, Paper-, Live- oder Orderclaims bleiben gesperrt;
- alte Protocol-v2-/Legacy-Reports können keine Protocol-v3-Freigabe erzeugen.

## Abnahme

Aufgabe 30 ist erst `DONE_100`, wenn:

1. alle verbindlichen Zustände und Blocker im bestehenden Dashboard angeschlossen sind;
2. Task-29 manuell und orderfrei über vorhandene Controller bedienbar ist;
3. Anzeige und Refresh keine Research-/Runtime-Wahrheit verändern;
4. vollständige UI-, Controller-, Restart-, Race- und Safety-Negativtests grün sind;
5. vollständige Pytest-Suite, Python-Compile, PowerShell-Syntax und Whitespace grün sind;
6. Handoff, `CURRENT_STATUS.md`, `NEXT_ACTION.md` und `docs/41` aktualisiert und gepusht sind;
7. der abschließende GitHub-CI-Lauf des Dokumentations-Heads grün ist.

Aufgabe 31 darf vorher nicht begonnen werden.

## Sicherheitsstatus beim Einstieg

- kein Backtest-, Paper-, Testtrade-, Live- oder Order-Start;
- keine API-Keys, privaten Endpunkte oder Secrets;
- kein neuer Finalstatus;
- der Bot darf nicht gestartet werden.
