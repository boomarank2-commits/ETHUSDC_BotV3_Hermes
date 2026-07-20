# Protocol v3 – Aufgabe 30 Abschluss

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
