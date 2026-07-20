# Next Action – Protocol v3 Aufgabe 31

Stand: 2026-07-20

## Startbedingung

Aufgabe 31 darf erst begonnen werden, wenn der Task-30-Dokumentations-Head mit Abschluss-Handoff, `CURRENT_STATUS.md`, dieser Datei und `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` vollständig gepusht und in GitHub CI grün ist.

Vor der ersten Codeänderung erneut vollständig lesen:

1. `AGENTS.md`
2. `handoff/CURRENT_STATUS.md`
3. `handoff/NEXT_ACTION.md`
4. `handoff/PROTOCOL_V3_TASK_30_2026-07-20.md`
5. `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
6. `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`
7. `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`
8. `configs/protocol_v3_contract.json`
9. `configs/protocol_v3_report_contract.json`

## Exakter nächster Auftrag

Ausschließlich Aufgabe 31 umsetzen:

`Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr`.

## Bestehende Architektur zuerst prüfen

Vor neuen Dateien oder Evaluatoren vollständig prüfen und bevorzugt erweitern:

- Task-2-Monatskalender und Boundaryplan;
- Task-5-Drei-Markt-Snapshot/Warmup;
- Task-6-Run-Fingerprint und öffentliche Exchange Info;
- Task-7-/8-Execution-, Kosten- und Intrabarparität;
- Task-9-/10-Outer-State und Kontextparität;
- Task-11-Reportart `protocol_v3_pipeline_final` und Evidence-Window-Registrierung;
- Task-12-Artefakte und feste Storage-Roots;
- Task-13-Checkpoint/HEAD/Resume;
- Task-15-Auswahlpipeline sowie Task 22 bis 28;
- bestehende Sealed-Holdout- und Final-Evaluation-Pfade nur als technische Referenz, niemals als Protocol-v3-Freigabe.

Keine zweite Pipeline-, Report-, Window-, Checkpoint-, Bootstrap-, Adoption- oder Runtime-Wahrheit bauen.

## Pflichtumfang Aufgabe 31

Der Final-Evaluator muss:

- ein vollständig neues 365-Tage-Fenster vor dessen Start registrieren;
- Registrierung, Pipelinegeneration, Code, Daten-, Feature-, Kontext-, Exchange-, Execution-, Kosten-, Gate-, Seed-, Trial- und Boundaryidentitäten unveränderlich binden;
- jede Überschneidung mit bereits sichtbaren Forward-Monaten oder verbrauchter historischer Evidenz vor dem ersten Datenlesen blockieren;
- das Fenster bis zum vollständigen Ende versiegelt halten;
- die unveränderte monatlich refittende Pipeline mit exakt zwölf Origins, 730 Entwicklungstagen je Origin, T+24h, Exit-only-/Flat-Handoff und lückenlosen 365 OOS-Tagen genau einmal ausführen;
- während des Laufs keine Outer-PnL, Rankings, Strategiewechsel oder Zwischenresultate öffnen;
- nach Abschluss dieselben Task-25-/26-/27-Metriken, Stressläufe und den 10.000er Stationary Bootstrap reproduzierbar auswerten;
- genau einen `protocol_v3_pipeline_final`-Report mit einer neuen, transitiv validierten Task-31-Attestation erzeugen;
- klar zwischen `historically_hit`, `fresh_pre_registered_sealed_365`, `sealed_bootstrap_target_supported` und `statistically_supported` unterscheiden;
- eine zweite Auswertung, nachträgliche Registrierung, Ergebnisfeedback oder Gate-/Pipelineänderung fail-closed verhindern.

## Harte Grenzen

Aufgabe 31 darf nicht:

- das bereits verbrauchte 3-Jahres-Fenster oder Task-27-/28-/29-Evidenz als frischen Final-Holdout umetikettieren;
- sichtbare Forward-Monate nachträglich in das Finalfenster aufnehmen;
- den bestehenden Legacy- oder Single-Candidate-`final_evaluation`-Pfad als Protocol-v3-Finalreport akzeptieren;
- die Pipeline, Features, Familien, Ranking-, Gate-, Kosten-, Bootstrap- oder Boundaryregeln anhand irgendeines Finalergebnisses verändern;
- ein teilweise abgeschlossenes oder vorzeitig geöffnetes Fenster bewerten;
- mehr als eine Finalauswertung zulassen;
- Orders, API-Keys, private Endpunkte, Paper, Testtrade, Live, `active_config.json` oder kanonische Adoption öffnen;
- statistische Unterstützung oder Finalstatus aus nackten Bool-Claims ableiten.

## Pflicht-Negativtests

Mindestens testen:

- Registrierung nach Fensterstart, fehlende Registrierung oder manipulierte Registrierungszeit blockiert;
- Fenster ist nicht exakt 365 vollständige UTC-Tage oder überlappt sichtbare Forward-/historische Evidenz;
- Pipeline-, Code-, Gate-, Kosten-, Bootstrap-, Seed-, Trial-, Snapshot-, Exchange- oder Boundaryhash ändert sich;
- ein Origin fehlt, ist doppelt, umsortiert oder sieht frühere Outer-Ergebnisse;
- Daten-/Kontextlücke, stale/future/misaligned Watermark oder unvollständiger Warmup blockiert;
- Zwischenreport, UI-Refresh oder Teilwrite öffnet keine Outer-PnL und verändert keinen State;
- Prozessabbruch kann nur aus dem letzten atomaren HEAD reproduzierbar fortsetzen;
- zweiter Evaluationsversuch, Replay nach geöffnetem Ergebnis oder nachträgliches Gate-Tuning blockiert;
- Legacy-, Protocol-v2-, Task-27-, Task-28-, Task-29- oder sichtbarer Forward-Report erzeugt keine Task-31-Attestation;
- manipulierte Freshness-, Bootstrap-, Support-, Final- oder Adoptionclaims werden neu abgeleitet und abgewiesen.

## Abnahme

Aufgabe 31 ist erst `DONE_100`, wenn:

1. der getrennt versionierte Pipeline-Final-Evaluator und die Task-31-Attestation vollständig implementiert sind;
2. Vorregistrierung, Versiegelung, Einmaligkeit, zwölf Origins, 365 Tage und kein Outer-Feedback technisch bewiesen sind;
3. Report-/Artefakt-/Checkpoint-/Bootstrap-Provenienz transitiv revalidiert wird;
4. vollständige Unit-, Integrations-, Resume-, Leakage-, Race-, Teilwrite- und Safety-Negativtests grün sind;
5. vollständige Pytest-Suite, Python-Compile, PowerShell-Syntax und Whitespace grün sind;
6. Handoff, `CURRENT_STATUS.md`, `NEXT_ACTION.md` und `docs/41` aktualisiert und gepusht sind;
7. der abschließende GitHub-CI-Lauf des Dokumentations-Heads grün ist.

Aufgabe 32 darf vorher nicht begonnen werden.

## Sicherheitsstatus beim Einstieg

- kein Backtest-, Paper-, Testtrade-, Live- oder Order-Start;
- keine API-Keys, privaten Endpunkte oder Secrets;
- kein Finalfenster tatsächlich ausführen oder öffnen;
- keine kanonische Adoption;
- der Bot darf nicht gestartet werden.
