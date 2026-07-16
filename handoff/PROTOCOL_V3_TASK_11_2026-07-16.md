# Protocol v3 – Handoff Aufgabe 11/33

Stand: 2026-07-16

## Status

`Protocol v3: Aufgabe 11/33 – Protocol-v3-Report-Schemas und Evidenzbedeutung – DONE_100`

Dieser Status gilt nach grüner Review CI des Commits, der dieses Handoff und die Fortschrittsdatei enthält.

Gesamtfortschritt: `11/33 = 33,33 %`.

Exakt nächste Aufgabe: `Aufgabe 12 – Kompakte Artefaktarchitektur`.

## Ausgangsstand und vorgeschaltete Prüfung

Verbindlicher Ausgangscommit war:

`a7b7a143a2e303898286ac7266dff45e498a156a`

Vor Aufgabe 11 wurde Aufgabe 10 am aktuellen Code und nicht nur am Handoff adversarial geprüft. Kontrolliert wurden insbesondere:

- konkrete Task-5-Snapshot-Revalidierung statt frei behaupteter Kontextidentität;
- vollständige Markt-/Tag-Provenienz und gemeinsame Drei-Markt-Watermark;
- exakte geschlossene 1m-Bar und fail-closed Verhalten bei fehlendem, versetztem, stale oder zukünftigem Kontext;
- Bindung in Pipelinegeneration, Run-Fingerprint, Cache- und Resume-Identität;
- Wiederverwendung der Task-8-Ausführungsengine;
- ETHUSDC als einziges Handelssymbol sowie BTCUSDC/ETHBTC ausschließlich als Kontext;
- keine vorgezogenen Final-Evaluator- oder Challenger-Controller.

Ergebnis: Es wurde kein offener Task-10-Fehler gefunden, der einen separaten Korrekturcommit erforderte.

## Implementierte Dateien

- `configs/protocol_v3_report_contract.json`
- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/reporting.py`
- `tests/unit/test_protocol_v3_reporting.py`
- `handoff/PROTOCOL_V3_TASK_11_2026-07-16.md`
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`

## Versionierter Reportvertrag

Neu eingefroren wurden:

- Vertrag: `protocol_v3_evidence_reports_v1`
- Report-Schema: `protocol_v3_report_v1`
- Forward-Registrierungsschema: `protocol_v3_evidence_window_registration_v1`
- Protocol-Version: `3.0.0`

Die fünf Reportklassen und festen, voneinander getrennten Roots sind:

| `artifact_kind` | Storage-Root | Evidenzfensterklasse |
|---|---|---|
| `protocol_v3_research` | `reports/protocol_v3/research` | `historical_research` |
| `monthly_process_oos` | `reports/protocol_v3/monthly_process_oos` | `monthly_process_oos` |
| `research_challenger_shadow` | `reports/protocol_v3/research_challenger_shadow` | `retrospective_research_challenger` |
| `forward_shadow_month` | `reports/protocol_v3/forward_shadow_month` | `forward_shadow_month` |
| `protocol_v3_pipeline_final` | `reports/protocol_v3/pipeline_final` | `sealed_final_holdout` |

`sealed_final_holdout` ist damit ausdrücklich eine Evidenzfensterklasse und kein austauschbarer Reporttyp. Der Legacy-Typname `final_evaluation` wird nicht verwendet.

## Evidenzbedeutung

Die öffentliche Builder-Schnittstelle nimmt keine Freshness-, Support- oder Adoptionsbooleans entgegen. Der Validator leitet die Bedeutungen aus Reportklasse, validiertem Fenster und Metriken neu ab.

Für `monthly_process_oos` gilt exakt:

```text
historically_hit = process_oos_net_usdc / 365 >= 3.0
```

Ein historischer Treffer erzeugt niemals automatisch statistische Unterstützung. Bis Aufgabe 27 und Aufgabe 31 existieren keine gültigen Bootstrap- oder Finalattestierungen. Deshalb bleiben zwingend:

```text
historical_bootstrap_lower_bound = false
fresh_pre_registered_sealed_365 = false
sealed_bootstrap_target_supported = false
statistically_supported = false
canonical_adoption_eligible = false
diagnostic_only = true
```

Weitere feste Bedeutungen:

- `protocol_v3_research`: `NOT_FRESH`, diagnostisch, nicht adoptierbar;
- `monthly_process_oos`: immer `NOT_FRESH`, diagnostisch, nicht adoptierbar;
- `research_challenger_shadow`: immer orderfrei, diagnostisch und nicht kanonisch adoptierbar;
- `forward_shadow_month`: `FRESH_FORWARD_OBSERVATION`, aber niemals alleiniger Finalnachweis;
- `protocol_v3_pipeline_final`: in Aufgabe 11 nur als `PENDING_TASK_31` reserviertes Schema ohne ausführbares Finalfenster.

## Forward-Registrierung und Finalfenstersperre

Forward-Monate benötigen eine eigene create-only Registrierung unter:

`reports/protocol_v3/evidence_windows/forward_shadow_month`

Technisch erzwungen werden:

- Registrierung vor Beginn des vollständigen UTC-Kalendermonats;
- aktueller Registrierungszeitpunkt innerhalb enger Uhrtoleranz;
- vollständiger UTC-Monat;
- Bindung an Pipelinegeneration und Run-Fingerprint;
- SHA-256 über den kanonischen Registrierungsinhalt;
- persistieren, reloaden und semantisch erneut validieren;
- Forward-Report erst nach vollständigem Monatsende;
- exakte Übereinstimmung mit der persistierten Registrierung.

Die Sperre für einen späteren `sealed_final_holdout` liest alle tatsächlich persistierten und revalidierten Forward-Registrierungen selbst aus der festen Root. Ein Aufrufer kann einen sichtbaren Monat nicht durch Weglassen aus einer übergebenen Liste verstecken. Jede Überlappung blockiert.

## Striktes JSON und Storage-Sicherheit

Report und Registrierung erzwingen:

- exakte Schlüssel und Versionen;
- Duplicate-Key-Ablehnung beim Parsen;
- Ablehnung von `NaN` und Infinity;
- keine unbekannten Safety- oder Evidenzfelder;
- endliche numerische Werte;
- kanonische JSON-Serialisierung;
- create-only Schreiben;
- unmittelbaren Reload und erneute semantische Validierung;
- exakte Report-ID/Dateinamen-Zuordnung;
- feste Report-Root pro Klasse;
- Ablehnung falscher Root, Traversal, Symlink und Alias-Verwechslung.

Die Persistenz ist bewusst nur die für Aufgabe 11 notwendige create-only Schema-Persistenz. Content-addressed Großartefakte, Deduplizierung und kompakte Indexarchitektur bleiben Aufgabe 12; transaktionales Resume bleibt Aufgabe 13.

## Legacy-Trennung

Für jede der fünf Protocol-v3-Reportklassen wurde geprüft:

- `validate_final_evaluation_report(...)` lehnt den Report ab;
- `adopt_for_shadow(...)` lehnt den Report ab;
- es entsteht kein Legacy-Shadow-State.

Damit können Protocol-v2- oder Single-Candidate-Consumer keinen Protocol-v3-Finalstatus oder eine Adoption auslösen.

## Pipeline- und Fingerprintbindung

Der Vertrag `protocol_v3_evidence_reports_v1` wurde als zusätzliche versionierte Quality-Gate-/Evidenzkomponente in `configs/protocol_v3_pipeline_contract.json` gebunden.

Gebundene Quellen umfassen mindestens:

- `configs/protocol_v3_report_contract.json`
- `src/ethusdc_bot/protocol_v3/reporting.py`
- `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`
- bestehende Quality-Gates und Trial-History-Quellen
- `src/ethusdc_bot/shadow/adoption.py` als Legacy-Abgrenzung

Dadurch ändern Reportvertrag oder Implementierung die Pipelinegeneration und damit den vollständigen Run-Fingerprint sowie dessen Cache-/Resume-Identität.

## Tests und CI

Task-11-Tests decken ab:

- exakten Vertrag und eindeutige Roots;
- Pipelinebindung;
- unabhängig berechnete 3-USDC/365-Tage-Schwelle;
- manipulierte Freshness-, Treffer-, Statistik-, Adoption- und Diagnostic-Felder;
- unerlaubte Task-27-/Task-31-Attestierungen;
- Forward-Registrierung, Persistenz, Reload und Abschlusszeit;
- Forward frisch, aber niemals final oder adoptierbar;
- Challenger orderfrei und nicht adoptierbar;
- nur reserviertes Pipeline-Final-Schema;
- persistierte Forward-Monate gegen späteres Finalfenster;
- deterministische Eingabereihenfolge;
- falsche Root und Symlinks;
- Duplicate Keys, `NaN`, unbekannte Felder und nichtkanonische Bytes;
- Inhaltsmanipulation der Registrierung;
- Ablehnung aller Protocol-v3-Reports durch den Legacy-Final-/Adoptionspfad.

CI-Historie:

1. Implementierungscommit: `fad3e7d959d1b3aa554251b415558104e65cdfd2`.
2. Review CI Run 417: ein Test rot, ausschließlich weil die korrekte Fehlermeldung `next UTC month boundary` nicht von der zu engen Testregex akzeptiert wurde. Compile, PowerShell und Whitespace waren bereits grün.
3. Separater Testkorrekturcommit: `bbef090816aa9591a7188e485625940645311781`. Produktionscode und Sicherheitsregel wurden nicht gelockert.
4. Review CI Run 418: vollständig grün.
5. Vollständige Suite: 1.063 Tests erfolgreich.
6. Python-Kompilierung, PowerShell-Syntax, Whitespace und abschließender Pytest-Gate-Schritt: grün.

## Ehrlicher aktueller Zustand

```text
Task-11-Reportvertrag = implementiert und pipelinegebunden
Task-11-Persistenz-/Reload-/Manipulationstests = grün
Task-10 = vorgeschaltet kritisch geprüft, keine Korrektur erforderlich
Protocol-v3-Final-Evaluator = nicht implementiert
reales versiegeltes Finaljahr = nicht geöffnet
kanonische Adoption = gesperrt
Paper/Testtrade/Live/Orders/API-Keys = gesperrt
```

Es gibt keine Performance-, statistische Unterstützungs-, Final- oder Live-Freigabebehauptung.

## Explizit nicht umgesetzt

Keine Aufgabe 12 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- keine kompakte Artefaktarchitektur oder Deduplizierung;
- kein content-addressed Artefaktstore;
- kein transaktionales Cache-/Resume-System;
- kein Fold-Planer;
- keine Kandidatenauswahl;
- keine PBO-/DSR-Berechnung;
- kein Multi-Timeframe-Feature-Store;
- kein Regimemodell;
- kein Challenger-Controller;
- kein Final-Evaluator;
- keine UI;
- keine Orders, Trading-API, API-Keys, Paper, Testtrade oder Live.

## Startanweisung für Aufgabe 12

Vor Aufgabe 12 muss Aufgabe 11 anhand des dann aktuellen Codes adversarial geprüft werden. Besonders zu kontrollieren sind:

- tatsächliche öffentliche Verkabelung statt bloßer Schemaexistenz;
- keine vom Aufrufer behauptbare Evidenz;
- vollständige semantische Revalidierung persistierter Registrierungen und Reports;
- feste Root-/Symlink-/Traversal-Sperren;
- automatische Berücksichtigung aller sichtbaren Forward-Monate;
- Pipeline-/Fingerprintbindung;
- Legacy-Ablehnung;
- keine vorgezogene Final- oder Adoptionslogik.

Erst nach eventueller separater Korrektur und grüner CI darf Aufgabe 12 beginnen.

## Exakt nächstes Ticket

`Aufgabe 12 – Kompakte Artefaktarchitektur`
