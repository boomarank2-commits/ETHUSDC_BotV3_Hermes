from __future__ import annotations

from pathlib import Path


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label} replacement mismatch: {old[:120]!r}")
    return text.replace(old, new)


state_path = Path("src/ethusdc_bot/ui/protocol_v3_operator_state.py")
state = state_path.read_text(encoding="utf-8")
state = replace_exact(
    state,
    "PROTOCOL_V3_DONE_TASKS: Final = 29",
    "PROTOCOL_V3_DONE_TASKS: Final = 30",
    "operator-state done count",
)
state = replace_exact(
    state,
    '            "active_task": 30,\n            "active_task_status": "IN_PROGRESS",',
    '            "active_task": 31,\n            "active_task_status": "NOT_STARTED",',
    "operator-state active task",
)
state_path.write_text(state, encoding="utf-8")


test_path = Path("tests/unit/test_protocol_v3_operator_state.py")
test = test_path.read_text(encoding="utf-8")
test = replace_exact(
    test,
    '''    assert state["task_progress"] == {
        "done_tasks": 29,
        "total_tasks": 33,
        "progress_pct": 87.88,
        "active_task": 30,
        "active_task_status": "IN_PROGRESS",
    }
''',
    '''    assert state["task_progress"] == {
        "done_tasks": 30,
        "total_tasks": 33,
        "progress_pct": 90.91,
        "active_task": 31,
        "active_task_status": "NOT_STARTED",
    }
''',
    "operator-state progress test",
)
test_path.write_text(test, encoding="utf-8")


Path("handoff/PROTOCOL_V3_TASK_30_2026-07-20.md").write_text(
    '''# Protocol v3 – Aufgabe 30 Abschluss

Stand: 2026-07-20

## Ergebnis

Aufgabe 30 – `UI und Bedienzustände vollständig anschließen` – ist `DONE_100`.

Gesamtfortschritt nach diesem Abschluss: `30/33 = 90,91 % DONE_100`.

Aufgabe 31 bleibt `NOT_STARTED`.

## Repository-Wahrheit

- Repository: `boomarank2-commits/ETHUSDC_BotV3_Hermes`
- Branch: `codex/research-resume-and-ui-state-v1`
- Draft-PR: `#17`
- technischer Task-30-Head vor Dokumentationsabschluss: `228902ec071d6d094ea902a7efd827b3e34db8f5`
- grüner vollständiger GitHub-CI-Lauf: `29770299870`
- vollständige Suite: `1.266 Tests erfolgreich`
- Python-Compile, PowerShell-Syntax und Whitespace: erfolgreich
- gezielte Task-30-Abnahme: sieben UI-/Controller-/Lifecycle-Testgruppen grün

## Umgesetzter Umfang

Das bereits vorhandene `OperatorDashboardApp` bleibt das einzige Hauptfenster und die einzige UI-Wahrheit. Es wurde kein zweites Dashboard und kein paralleler Runtimepfad gebaut.

Umgesetzt wurden:

- ein reiner, kanonisch serialisierter und SHA-256-gehashter Protocol-v3-Operatorzustand;
- eine read-only Evidence-Bridge für ausschließlich typisierte Task-28-/Task-29-/Task-13-Evidenz;
- ein dünner asynchroner Research-Challenger-Controller, der nur die bestehenden Task-29-APIs und einen explizit gelieferten öffentlichen Backend-Worker aufruft;
- ein zusätzlicher Protocol-v3-Aktionsstreifen im bestehenden Dashboard;
- manuelles Starten, checkpoint-gebundenes Fortsetzen, kooperatives Stoppen und read-only Öffnen eines validierten Diagnoseberichts;
- sichtbare, getrennte Lebenszykluszustände für historisches Prozess-OOS, aktuellen Monatsrefit, späteres versiegeltes Finalfenster und kanonischen Shadow;
- Anzeige von Origins, inneren Folds, Cycles, getesteten Kandidaten und tatsächlichem Rechenschritt ohne Zeit- oder PnL-Schätzung;
- konkrete kanonische Blocker für jeden deaktivierten Button;
- exakte Drei-Markt-Watermark-Prüfung auf die zuletzt vollständig geschlossene UTC-Minute;
- Restart-/Refresh-Neutralität: wiederholtes Anzeigen verändert weder State-, Signal-, Fill-, Ledger- noch Checkpointhash;
- sichtbare Sperre konkurrierender Daten-, Research-, Final-, Adoption- und Shadow-Starts in der Protocol-v3-Ansicht;
- reine Navigation zurück zur Übersicht ohne Prozessstart.

## Fail-closed Bedienregeln

`Manuell starten` ist nur aktiv, wenn gleichzeitig vorliegen:

- vollständig validierte Task-28-Provenienz;
- passende aktuelle Pipelinegeneration;
- gültiges `valid_from`-/`valid_until`-Fenster;
- exakt aktueller, vollständig geschlossener ETHUSDC/BTCUSDC/ETHBTC-Watermark;
- bei Trading-Kandidat der bitgleiche öffentliche Exchange-Info-Snapshot;
- ein expliziter öffentlicher Backend-Worker, der den initialen Zustand checkpointen kann;
- keine parallele Datenprüfung, Forschung, Finalauswertung, Adoption oder kanonischer Shadow.

`Aus Checkpoint fortsetzen` verlangt zusätzlich einen validierten Task-29-State, einen bitgleichen Task-29-/Task-13-Checkpoint-Receipt, dieselbe Pipelinegeneration und denselben Ledger-Head. In-Memory-Zustand ohne Checkpoint ist nicht resume-fähig.

`Diagnosebericht öffnen` wird nur durch einen bereits validierten `research_challenger_shadow`-Report und einen read-only Backend-Callback aktiviert. Legacy-, Protocol-v2- oder fremde Reportarten können die Aktion nicht freischalten.

## Ergebnisbedeutung

- Task 27/28 bleibt `NOT_FRESH` und `diagnostic_only`.
- Task 29 bleibt `NOT_FRESH`, `order_free_diagnostic_only`, nicht statistisch unterstützt, nicht adoptionfähig und nicht final.
- Das spätere Finalfenster bleibt `NOT_REGISTERED` beziehungsweise versiegelt, bis Aufgabe 31 einen echten separaten Pfad implementiert.
- Ein Protocol-v3-Finalstatus wird nicht angezeigt.

## Harte Safety

Durchgehend sichtbar und technisch gesperrt:

- `Orders: gesperrt`
- `Paper: gesperrt`
- `Testtrade: gesperrt`
- `Live: gesperrt`
- `Trading-API/private Endpunkte: nicht verwendet`
- `Canonical adoption: nicht zulässig`
- `Botstart: nicht erlaubt`

Es wurden keine API-Keys, privaten Endpunkte, Kontodaten, Orderpfade, handelbaren Configs, Fake-Trades, Fake-Fills oder Fake-Reports eingeführt.

## Relevante Implementierung

- `src/ethusdc_bot/ui/protocol_v3_operator_state.py`
- `src/ethusdc_bot/ui/protocol_v3_lifecycle_status.py`
- `src/ethusdc_bot/ui/research_challenger_controller.py`
- `src/ethusdc_bot/ui/protocol_v3_dashboard_bridge.py`
- `src/ethusdc_bot/ui/protocol_v3_dashboard_mixin.py`
- `src/ethusdc_bot/ui/operator_dashboard.py`

## Testabdeckung

Neue beziehungsweise erweiterte Testgruppen:

- `tests/unit/test_protocol_v3_operator_state.py`
- `tests/unit/test_research_challenger_controller.py`
- `tests/unit/test_protocol_v3_dashboard_bridge.py`
- `tests/unit/test_protocol_v3_operator_dashboard_integration.py`
- `tests/unit/test_protocol_v3_dashboard_fail_closed.py`
- `tests/unit/test_protocol_v3_lifecycle_status.py`
- `tests/unit/test_protocol_v3_report_open_action.py`

Geprüft wurden unter anderem fehlende oder manipulierte Provenienz, stale/future/misaligned Watermarks, abgelaufene Task-28-Fenster, Cross-Generation-Resume, Checkpoint-/Ledger-Mismatch, Doppelstart, Providerfehler, konkurrierende Runtime-Aktionen, Restart/Refresh, Reportart und Safety-Claims.

## Nicht ausgeführt

- kein Backtest;
- kein Paper-, Testtrade-, Live- oder Orderstart;
- kein Research-Challenger-Produktionslauf;
- kein Finalfenster geöffnet oder registriert;
- keine kanonische Adoption;
- der Bot wurde nicht gestartet.

## Nächste Aufgabe

Ausschließlich Aufgabe 31: `Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr`.

Sie darf erst nach grünem CI des vollständigen Task-30-Dokumentations-Heads begonnen werden.
''',
    encoding="utf-8",
)


Path("handoff/CURRENT_STATUS.md").write_text(
    '''# Current Status – GPT 1 / Protocol v3

Stand: 2026-07-20

## Verbindlicher Gesamtstand

`30/33 = 90,91 % DONE_100`.

Abgeschlossene Aufgaben: `1 bis 30`.

Aktive Aufgabe: keine.

Nächste Aufgabe: `31 – Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr` – `NOT_STARTED`.

Aufgaben 32 und 33 bleiben strikt `NOT_STARTED`.

## Repository-Wahrheit

- Repository: `boomarank2-commits/ETHUSDC_BotV3_Hermes`;
- Branch: `codex/research-resume-and-ui-state-v1`;
- Draft-PR: `#17`;
- technischer Task-30-Head vor Dokumentationsabschluss: `228902ec071d6d094ea902a7efd827b3e34db8f5`;
- grüner vollständiger Task-30-CI-Lauf: `29770299870`;
- vollständige Suite: `1.266 Tests erfolgreich`;
- Python-Compile, PowerShell-Syntax und Whitespace: erfolgreich.

## Aufgabe 30 – DONE_100

Abschlussbericht:
`handoff/PROTOCOL_V3_TASK_30_2026-07-20.md`

Das bestehende Dashboard zeigt nun einen einzigen fail-closed Protocol-v3-Operatorzustand, getrennte Lebenszykluszustände, kanonische Blocker und den orderfreien Task-29-Bedienpfad. Refresh und Neustart bleiben zustandsneutral. Paper, Testtrade, Live, Orders, private Endpunkte, Adoption und Botstart bleiben gesperrt.

## Aufgabe 31 – NOT_STARTED

Verbindlicher nächster Umfang:

- einen getrennt versionierten Pipeline-Final-Evaluator für genau ein wirklich neues, vorab registriertes und bis zum Ende versiegeltes 365-Tage-Fenster bauen;
- dieselbe unveränderte monatlich refittende Pipeline mit zwölf Origins und vollständiger Drei-Markt-/Execution-/Kosten-/Boundary-Parität verwenden;
- sichtbare Forward-Monate, verbrauchte Historie und Legacy-/Single-Candidate-Finalpfade strikt ausschließen;
- genau eine Auswertung zulassen und erst danach einen Protocol-v3-Pipeline-Finalreport mit Task-31-Attestation erzeugen;
- keine Orders, keine Adoption, kein Paper, kein Testtrade und kein Live vorziehen.

Aufgabe 31 darf erst nach grünem CI dieses Task-30-Dokumentations-Heads begonnen werden.

## Sicherheitsstatus

- kein Backtest-, Paper-, Testtrade-, Live- oder Order-Start;
- keine API-Keys oder privaten Endpunkte;
- keine Secrets committed;
- keine Quality-Gates gelockert;
- keine Fake-Trades, Fake-Fills oder Fake-Reports;
- kein kanonischer Adoption- oder Finalpfad geöffnet;
- kein Protocol-v3-Finalstatus ohne wirklich neuen `sealed_final_holdout`;
- der Bot darf nicht gestartet werden.

## Nächster Einstieg

Nach grünem Dokumentations-CI ausschließlich `handoff/NEXT_ACTION.md` für Aufgabe 31 ausführen.
''',
    encoding="utf-8",
)


Path("handoff/NEXT_ACTION.md").write_text(
    '''# Next Action – Protocol v3 Aufgabe 31

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
''',
    encoding="utf-8",
)


docs_path = Path("docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md")
docs = docs_path.read_text(encoding="utf-8")
docs = replace_exact(
    docs,
    "Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 29/33 abgeschlossen",
    "Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 30/33 abgeschlossen",
    "docs/41 header",
)
docs = replace_exact(
    docs,
    '''### Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Status:** `NOT_STARTED`

Origins, Folds, Fortschritt, Safety, Ergebnisbedeutung und manuelle Challenger-Aktion werden korrekt angezeigt; keine vorzeitige Outer-PnL, Paper/Testtrade/Live/Orders bleiben gesperrt.
''',
    '''### Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Status:** `DONE_100`

Das bestehende Operator-Dashboard zeigt genau einen fail-closed Protocol-v3-Zustand. Origins, Folds, Cycles, Kandidatenfortschritt, aktueller Rechenschritt, Drei-Markt-Watermark, Monatsrefit, Research-Challenger, Finalfenster und kanonischer Shadow sind semantisch getrennt.

**Abnahme:**

- Task-28-/29-/13-Evidenz wird nur typisiert und transitiv validiert in die read-only UI-Bridge übernommen; rohe JSON-, Bool- oder Dateifund-Claims können keinen Button aktivieren.
- Manueller Start verlangt aktuelle geschlossene Drei-Markt-Daten, passende Pipelinegeneration, gültiges Task-28-Fenster, Exchange-Info-Parität und einen öffentlichen checkpointfähigen Backend-Worker.
- Resume verlangt bitgleichen State, Checkpoint-Receipt, Ledger-Head und dieselbe Generation. Uncheckpointed In-Memory-State ist nicht resume-fähig.
- Der Task-29-Controller bleibt asynchron, kooperativ stoppbar, orderfrei und strikt von kanonischer Adoption getrennt.
- Restart, Refresh und wiederholtes Öffnen verändern keine Research-, Signal-, Fill-, Ledger-, Report- oder Checkpointidentität.
- Historisches Prozess-OOS, aktueller Refit, späteres Finalfenster und kanonischer Shadow besitzen getrennte sichtbare Lebenszykluszustände.
- Outer-PnL bleibt bis zu einem vollständig publizierten Ergebnis verborgen. Task 27 bis 29 bleiben `NOT_FRESH`, `diagnostic_only`, nicht statistisch unterstützt, nicht adoptionfähig und nicht final.
- Paper, Testtrade, Live, Orders, private Endpunkte, API-Keys, `active_config.json`, kanonische Adoption und Botstart bleiben sichtbar und technisch gesperrt.

**Bericht:** `handoff/PROTOCOL_V3_TASK_30_2026-07-20.md`
''',
    "docs/41 task30 block",
)
docs = replace_exact(
    docs,
    '''Protocol v3: Aufgabe 29/33 – Orderfreier Research-Challenger-Shadow – DONE_100
Gesamt: 29/33 DONE_100 = 87,88 %''',
    '''Protocol v3: Aufgabe 29/33 – Orderfreier Research-Challenger-Shadow – DONE_100
Protocol v3: Aufgabe 30/33 – UI und Bedienzustände vollständig anschließen – DONE_100
Gesamt: 30/33 DONE_100 = 90,91 %''',
    "docs/41 progress",
)
docs_path.write_text(docs, encoding="utf-8")
