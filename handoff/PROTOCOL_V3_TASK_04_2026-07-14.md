# Protocol v3 – Handoff Aufgabe 4/33

Stand: 2026-07-14

## Status

`Protocol v3: Aufgabe 4/33 – Permanentes Trial-Ledger und historischen Import bauen – DONE_100`

Gesamtfortschritt nach Statusupdate: `4/33 = 12,12 %`

Exakt nächste Aufgabe: `Aufgabe 5 – Dynamischen Drei-Markt-Datensnapshot und Warmup herstellen`.

Codex darf Aufgabe 5 erst beginnen, nachdem der Branch lokal auf den finalen PR-Head dieses Handoffs gezogen und ein sauberer Arbeitsbaum bestätigt wurde.

## Vorherige Aufgabe kontrolliert

Vor Beginn wurde Aufgabe 3 gegen den aktuellen PR geprüft:

- PR #17 war offen, mergebar, Draft und nicht gemerged.
- Ausgangs-Head war `7d7d0cb88e865a78bb4a2525a227e0f2cf0ad9e7`.
- Review-CI Run 344 war vollständig grün.
- Pipelinegeneration, timestamp-freies Pre-Run-Manifest, 64-Bit-Seeds, Stagnationsregel und 40/12/3/2-Prozessbudgets waren vorhanden.
- Paper, Testtrade, Live, Orders, Trading-API und API-Keys blieben gesperrt.

## Kontrollfund und enge Korrektur zu Aufgabe 3

Der Blueprint enthält neben den zwölf historischen Monats-Origins genau einen aktuellen 730-Tage-Refit. Der ursprüngliche Task-3-Handoff bezeichnete das reine 12-Origin-Budget `96 / 3.840 / 1.152 / 288 / 192` fälschlich als global.

Korrekte Trennung:

| Ebene | Cycles | generiert | getestet | Walk-forward | Finalisten |
|---|---:|---:|---:|---:|---:|
| 12 historische Origins | 96 | 3.840 | 1.152 | 288 | 192 |
| 1 aktueller Refit | 8 | 320 | 96 | 24 | 16 |
| gesamte Hülle | 104 | 4.160 | 1.248 | 312 | 208 |

Die bestehende reine `SearchBudgetPolicy` wurde nicht umgedeutet. Stattdessen ergänzt `src/ethusdc_bot/protocol_v3/global_budget.py` genau den einen aktuellen Refit und blockiert einen zweiten Refit, Cycle 9 oder jede globale Überschreitung. Die Korrektur ist zusätzlich dokumentiert in `handoff/PROTOCOL_V3_TASK_03_BUDGET_CORRECTION_2026-07-14.md`.

## Was umgesetzt wurde

### 1. Permanentes append-only Ledger

Neue Datei `src/ethusdc_bot/protocol_v3/trial_ledger.py` implementiert:

- unveränderliches Ledger-Manifest;
- generationsübergreifenden Namespace `protocol_v3_permanent_trial_counter_v1`;
- einzeln gespeicherte Eventdateien;
- fortlaufende Sequenz;
- SHA-256-Digest jedes Events;
- SHA-256-Verkettung zum vorherigen Event;
- digest-gebundenes `head.json`;
- atomische Dateierstellung beziehungsweise Head-Ersetzung;
- exklusiven Ledger-Lock; ein vorhandener oder stale Lock blockiert fail-closed;
- keine Delete- oder Update-Funktion für bewertete Trials.

Manipulierte Events, umbenannte Eventdateien, gelöschte Tail-Events, unterbrochene Sequenzen, gebrochene Hashketten und manipulierte Heads werden beim Lesen erkannt.

### 2. Deterministische Trial-Identität

Ein nativer oder nach Ergebnissicht manuell geänderter Trial bindet mindestens:

- `source_kind`;
- Kandidaten-ID;
- Familie;
- vollständige Parameter;
- Featurevariante;
- unsigned 64-Bit-Seed;
- Pipelinegeneration;
- Ranking-Version;
- Gate-Version;
- Simulator-Version;
- Kostenmodell-Version;
- Boundary-Version;
- vollständigen 40-Zeichen-Git-Commit;
- Evaluationsscope;
- kausale, streng aufsteigende tägliche Netto-MTM-Reihe inklusive Nulltage;
- Digest der Tagesreihe;
- Ergebniszusammenfassung.

`trial_id = trial_sha256:<SHA-256 der kanonischen Identitätsbasis>`.

Dieselbe Identität mit demselben Payload ist idempotent. Dieselbe Identität mit nachträglich verändertem Ergebnis oder Beleg blockiert als unzulässige Mutation.

### 3. Manuelle Änderungen nach Ergebnissicht zählen

`source_kind=manual_patch_after_results` ist ein eigenständiger dateninformierter Trial. Eine manuelle Änderung nach Ergebnissicht kann daher nicht still als derselbe Versuch behandelt werden.

### 4. Cache- und Report-Wiederverwendung

- Cache-Wiederverwendung wird als eigenes Event gespeichert.
- `counts_as_independent_trial=false` ist fest erzwungen.
- Gleiches Trial plus gleicher Reuse-Scope ist idempotent.
- Byte-identische historische Reportkopien werden als Wiederverwendung erkannt und erzeugen keinen neuen unabhängigen Trial.
- Ein Cache-Hit auf eine unbekannte Trial-ID blockiert.

### 5. Historischer Import

Der Importer unterstützt vorhandene Reportformen:

- Protocol-v2-Research-Loop mit Cycles, Stage-IDs und Candidate-Inventory;
- ältere Single-Research-Reports mit Candidate-Leaderboard.

Nur Kandidaten mit rekonstruierbarer Identität werden als historische Trial-Zeilen angelegt. Fehlende Identitäten werden gezählt und nicht erfunden. Historische Records tragen dauerhaft:

- `source_kind=historical_import`;
- `historical_trial_count_is_lower_bound=true`;
- explizite Missing-Fields;
- keine erfundenen Seeds, Versionen oder Tagesreihen.

Später rekonstruierte kausale Tagesreihen können genau einmal digest- und provenance-gebunden angehängt werden. Eine abweichende zweite Reihe blockiert.

### 6. Kanonischer derzeitiger Altbestand

Neue Datei `configs/protocol_v3_historical_trial_lower_bound.json` dokumentiert ehrlich den derzeit belegbaren Mindeststand:

- bekannter Supervisor-Lauf vom 12.07.2026: 8 Cycles × 12 getestete Zeilen = 96;
- jüngster Protocol-v2-Lauf vom 13.07.2026: 7 Cycles × 12 getestete Zeilen = 84;
- insgesamt 180 bekannte Bewertungszeilen;
- `independent_trial_count_resolved=0`, weil vollständige Kandidatenidentitäten, Duplikat-/Cache-Zuordnung und kausale Tagesreihen für diese beiden Altbestände nicht vollständig vorliegen;
- die 180 Zeilen werden ausdrücklich nicht als 180 unabhängige Trials ausgegeben.

Das ist eine Untergrenze und keine Freigabezahl.

### 7. DSR- und Freigabesperre

Solange mindestens eine Bedingung gilt,

- kanonischer historischer Import fehlt;
- `historical_trial_count_is_lower_bound=true`;
- weniger als zwei vollständige Trials vorhanden;
- mindestens eine kausale Tagesreihe fehlt;

meldet das Ledger:

- `development_dsr_status=INSUFFICIENT_TRIAL_HISTORY`;
- `only_release_decision_allowed=NO_TRADE`.

Ein Trading-Kandidat blockiert in diesem Zustand. Es wurde keine DSR-Formel implementiert; die Berechnung bleibt ausschließlich Aufgabe 18.

### 8. Reconciled Completion Gate

Neue Datei `src/ethusdc_bot/protocol_v3/trial_history_gate.py` verhindert, dass eine bloße Zählbehauptung die Untergrenze entfernt. Für eine spätere vollständige Attestierung sind erforderlich:

- jede bekannte historische Bewertungszeile ist gemappt;
- `resolved_historical_trial_count + duplicate_or_cache_row_count = observed_evaluation_rows`;
- alle historischen Tagesreihen sind vollständig;
- ein SHA-256 der Observation-Mapping-Datei;
- ein digest-gebundenes vollständiges Trial-Inventar;
- passende Ledger-Anzahl.

Der kombinierte Inventar-/Reconciliation-Digest wird im append-only Event gespeichert. Erst danach kann der Status auf `READY_FOR_DSR_IMPLEMENTATION` wechseln. Dieser Status berechnet noch keinen DSR und erzeugt keine Adoption.

### 9. Pipelinebindung

`configs/protocol_v3_pipeline_contract.json` bindet jetzt per Quelldigest:

- den historischen Lower-Bound-Vertrag;
- das permanente Trial-Ledger;
- das Reconciliation-Gate;
- die globale 12+1-Budgethülle.

Änderungen an diesen Regeln erzeugen damit eine neue Pipelinegeneration. Der permanente Trial-Counter selbst bleibt generationsübergreifend und wird nicht zurückgesetzt.

## Neue und geänderte Dateien

- `configs/protocol_v3_historical_trial_lower_bound.json`
- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/global_budget.py`
- `src/ethusdc_bot/protocol_v3/trial_ledger.py`
- `src/ethusdc_bot/protocol_v3/trial_history_gate.py`
- `src/ethusdc_bot/protocol_v3/__init__.py`
- `tests/unit/test_protocol_v3_trial_ledger.py`
- `handoff/PROTOCOL_V3_TASK_03_BUDGET_CORRECTION_2026-07-14.md`
- `handoff/PROTOCOL_V3_TASK_04_2026-07-14.md`
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` – wird im Abschlussstand auf 4/33 aktualisiert

## Tests und Review

Die neue Suite prüft mindestens:

- ehrlichen kanonischen Lower-Bound-Import;
- deterministische Trial-ID;
- idempotentes Append;
- blockierte Mutation gleicher Trial-Identität;
- Zählung manueller Änderungen nach Ergebnissicht;
- sichtbare Cache-Wiederverwendung ohne neuen Trial;
- unbekannten Cache-Hit als Fehler;
- Pflicht, Reihenfolge, Eindeutigkeit und Endlichkeit der Tagesreihe;
- deterministischen Protocol-v2-Import;
- identische Reportkopien als Wiederverwendung;
- append-only Attachment historischer Tagesreihen;
- NO_TRADE-Sperre bei unvollständiger Historie;
- blockierte Completion ohne Tagesreihen oder vollständiges Mapping;
- erfolgreiche, digest-gebundene Completion nur mit vollständiger Reconciliation;
- Eventmanipulation, Tail-Löschung, Headmanipulation und stale Lock;
- unveränderlichen Lower-Bound-Vertrag;
- vollständige 12+1-Budgetreservierung bis exakt 104/4.160/1.248/312/208;
- blockierten zweiten aktuellen Refit und blockierte Budgetfälschung.

CI-Historie:

1. Ein erster Testlauf fand ausschließlich eine Provenienz-Kollision bei denselben Report-Bytes unter einem zweiten Dateinamen. Die Trial-Identitäten wurden bereits korrekt wiederverwendet.
2. Der Import-Gate wurde präzisiert: identische Bytes sind sichtbare Wiederverwendung und erzeugen weder ein neues Importevent noch einen unabhängigen Trial.
3. Review-CI Run 356 war danach vollständig grün: komplette Pytest-Suite, Python-Kompilierung, PowerShell-Syntax und Whitespace.
4. Der finale Dokumentations-/Handoff-Head wird erneut durch dieselbe Review-CI geprüft.

Ein Marktdaten-, Backtest- oder Langlauf ist für die reine Ledger-/Importaufgabe fachlich nicht erforderlich und wurde nicht vorgezogen.

## Aktueller ehrlicher Laufzustand

Nach Import des kanonischen Altbestands gilt weiterhin:

```text
historical_trial_count_is_lower_bound = true
known_observed_historical_evaluation_rows = 180
independent_trial_count_resolved = 0
development_dsr_status = INSUFFICIENT_TRIAL_HISTORY
only_release_decision_allowed = NO_TRADE
```

Das Ledger behauptet damit ausdrücklich keine statistische Unterstützung und keine Zielerreichung.

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 5 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- kein Drei-Markt-Datensnapshot;
- kein Warmup-Download oder Watermark;
- keine Exchange-Info;
- keine Notional-/Step-Size-Änderung;
- keine Execution- oder Simulatoränderung;
- keine DSR- oder PBO-Berechnung;
- keine Feature-, Strategie-, Router-, Gate-, Shadow- oder UI-Änderung;
- keine Orders, Trading-API, API-Keys, Paper, Testtrade oder Live;
- kein finaler Holdout.

## Safety

Unverändert gesperrt:

- Orders;
- Trading-API;
- API-Keys und Kontodaten;
- Paper;
- Testtrade;
- Live;
- finaler Holdout;
- automatische Kandidatenadoption.

## Codex-Startanweisung für Aufgabe 5

1. Branch `codex/research-resume-and-ui-state-v1` auf den finalen PR-Head ziehen.
2. `git status` muss sauber sein; lokaler `HEAD` muss GitHub entsprechen.
3. Dieses Handoff, Dokument 41, `configs/protocol_v3_pipeline_contract.json`, `src/ethusdc_bot/protocol_v3/global_budget.py` und `src/ethusdc_bot/protocol_v3/trial_ledger.py` vollständig lesen.
4. Vorhandene Data-Readiness-, Downloader-, Catalog-, Raw-Path- und Drei-Markt-Auditfunktionen inventarisieren und wiederverwenden.
5. Danach ausschließlich Aufgabe 5 umsetzen.
6. Den Trial-Ledger-Head in Aufgabe 5 höchstens als spätere Fingerprint-Vorbereitung lesen; vollständige Run-Fingerprints gehören erst zu Aufgabe 6.
7. Keine Exchange-Info-, Simulator-, Cache-, Router-, Shadow- oder UI-Arbeit vorziehen.
8. Keine historische Trial-Vollständigkeit behaupten und keine DSR-Berechnung vorziehen.

## Exakt nächstes Ticket

`Aufgabe 5 – Dynamischen Drei-Markt-Datensnapshot und Warmup herstellen`

Ziel ist, den gemeinsamen letzten vollständigen UTC-Tag und den erforderlichen kausalen Warmup für ETHUSDC, BTCUSDC und ETHBTC dynamisch zu bestimmen, als unveränderlichen Snapshot einzufrieren und bei Lücken, Duplikaten, ungültigem OHLC, unvollständigem 1.440-Minuten-Raster oder fehlendem Warmup fail-closed zu blockieren.
