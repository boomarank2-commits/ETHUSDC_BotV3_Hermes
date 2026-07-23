# Protocol v3 – Handoff Aufgabe 15/33

Stand: 2026-07-18

## Status

`Protocol v3: Aufgabe 15/33 – Reine innere Auswahlfunktion extrahieren – DONE_100`

Gesamtfortschritt nach grüner Implementierungs-CI: `15/33 = 45,45 %`.

Exakt nächste Aufgabe: `Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets`.

Aufgabe 16 wurde nicht begonnen.

## Ausgangsstand und vorgeschaltete Prüfung von Aufgabe 14

Verbindlicher Ausgangs-Head:

`f87c902ad0309d363f4cff7d6f4d713fee94530c`

PR #17 war offen, Draft und ungemerged.

Vor Aufgabe 15 wurde Aufgabe 14 erneut am tatsächlichen Code adversarial geprüft. Kontrolliert wurden insbesondere:

- exakt sechs chronologische und lückenlose 60-Tage-Validation-Folds;
- Validation-Union exakt auf den letzten 360 Entwicklungstagen;
- Fits mit 370, 430, 490, 550, 610 und 670 Tagen vor Purging;
- `fit_end = validation_start - purge_duration`;
- Task-9-Boundary-Touch-Purge und fester maximaler Purge-Cutoff;
- beidseitige Timestamp-Spies für Fit und Validation;
- gegenseitige Bindung von Fold-Plan und Transaktions-Horizon-Identität;
- Ablehnung alter `task14_not_implemented`-Identitäten;
- kein Vorgriff auf Kandidatenmatrix, PBO, DSR, Router oder Outer-Orchestrierung.

Es wurde kein weiterer Task-14-Produktionsfehler gefunden. Deshalb war vor Aufgabe 15 kein separater Task-14-Korrekturcommit erforderlich.

## Implementierte Dateien

Produktionsdateien:

- `configs/protocol_v3_inner_selection_contract.json`;
- `configs/protocol_v3_pipeline_contract.json`;
- `configs/protocol_v3_transaction_contract.json`;
- `src/ethusdc_bot/protocol_v3/inner_selection.py`;
- `src/ethusdc_bot/protocol_v3/inner_selection_api.py`;
- `src/ethusdc_bot/protocol_v3/transactional_cache.py`.

Tests und gemeinsame Fixtures:

- `tests/unit/test_protocol_v3_inner_selection.py`;
- `tests/unit/test_protocol_v3_inner_selection_missing_evidence.py`;
- `tests/unit/protocol_v3_task13_support.py`.

Dokumentation:

- `handoff/PROTOCOL_V3_TASK_15_2026-07-18.md`;
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`.

## Versionierter Auswahlvertrag

Eingefroren wurden:

- Vertragsschema: `protocol_v3_inner_selection_contract_v1`;
- Vertrag: `protocol_v3_pure_inner_candidate_selection_v1`;
- Training-Window-Schema: `protocol_v3_selection_training_window_v1`;
- Kandidatenevidenz: `protocol_v3_candidate_selection_evidence_v1`;
- Entwicklungssupport: `protocol_v3_development_support_v1`;
- Frozen Config: `protocol_v3_frozen_selection_config_v1`;
- Entscheidung: `protocol_v3_inner_selection_decision_v1`;
- Kandidatenidentität: `protocol_v3_candidate_selection_identity_v1`.

Kanonische JSON-Bytes und SHA-256 binden jede Auswahlentscheidung. Unbekannte Felder, Duplicate Keys, nicht endliche Werte, manipulierte Digests oder widersprüchliche Identitäten blockieren fail-closed.

## Reine öffentliche Auswahlfunktion

Der stabile öffentliche Einstieg lautet:

```python
select_candidate(training_window, frozen_pipeline_config)
```

unter:

`ethusdc_bot.protocol_v3.inner_selection_api`.

Die Funktion verwendet ausschließlich ihre beiden expliziten, bereits validierten und immutable Eingaben. Sie liest keine Rohdaten, Dateien, UI-Zustände, Umgebungsvariablen, Uhrzeit, Netzwerkdaten oder Outer-Ergebnisse.

Gleiche kanonische Eingaben erzeugen dieselbe Entscheidung, denselben Entscheidungsdigest und dieselbe Entscheidungs-ID.

## Training-Window- und Task-14-Bindung

Das Auswahlfenster muss:

- exakt 730 UTC-Tage enthalten;
- an UTC-Mitternacht beginnen und enden;
- den vollständigen semantisch revalidierten Task-14-Fold-Plan enthalten;
- exakt dieselben Trainingsgrenzen wie dieser Fold-Plan besitzen.

`SelectionTimestampSpy` blockiert:

- Training-Zugriffe vor `training_start`;
- Training-Zugriffe an oder nach `training_end`;
- Warmup-Zugriffe an oder nach `training_start`;
- jeden Zugriff auf Outer-Ergebnisse.

Warmup bleibt damit ausschließlich kausales Feature-Reading vor dem Fit.

## Vollständige Frozen-Config-Bindung

Die eingefrorene Auswahlkonfiguration bindet:

- Pre-Run-Manifest;
- vollständigen Run-Fingerprint;
- Pipelinegeneration;
- Code-Commit;
- Drei-Markt-Datensnapshot;
- Kontextidentität;
- Kostenmodell;
- Simulator;
- Quality-Gate-Komponente;
- Exchange-Info;
- permanentes Trial-Ledger-HEAD;
- exakten Task-14-Fold-Plan;
- Origin und Zyklus;
- deterministischen `inner_selection`-Seed;
- Kandidateninventare je Stufe;
- Kandidatenevidenz;
- Matrix-/PBO-/DSR-Supportzustand.

Manifest, Run-Fingerprint, Fold-Plan und ausgewählte Origin werden gegenseitig abgeglichen. Ein Mix aus verschiedenen Runs, Origins, Folds, Kontexten oder Pipelinegenerationen blockiert.

## Budgets und Kandidateninventare

Unverändert gelten die bestehenden Grenzen je Zyklus:

```text
generated   <= 40
tested      <= 12
walk_forward <= 3
finalists   <= 2
```

Die Inventare müssen eindeutig, kanonisch sortierbar und echte Teilmengen sein:

```text
finalists ⊆ walk_forward ⊆ tested ⊆ generated
```

Kandidaten-IDs werden aus der vorhandenen kanonischen `StrategyCandidate`-Signatur abgeleitet. Zusätzliche Kandidatenfamilien oder Parameter wurden nicht eingeführt.

## Exakte lexikographische Rangfolge

Ein Kandidat ist erst rangierbar, wenn das bestehende `quality_gate_v1` im Selection-Modus tatsächlich besteht. Eine vom Aufrufer behauptete Freigabe wird ignoriert; die Gates werden aus der gebundenen Evidenz neu berechnet.

Die Rangfolge ist exakt:

1. schlechtester Fold Netto-USDC/Tag – höher besser;
2. Median-Fold Netto-USDC/Tag – höher besser;
3. aggregierter WFV Netto-USDC/Tag – höher besser;
4. Joint-Stress Netto-USDC/Tag – höher besser;
5. maximaler Drawdown – niedriger besser;
6. Friktionsanteil – niedriger besser;
7. Anzahl freier Parameter – niedriger besser;
8. kanonische Kandidaten-ID – lexikographisch aufsteigend.

Der Zielwert `3 USDC/Tag` ist als Ranking-, Loss-, Distanz- oder Stopwert ausdrücklich verboten.

## Typisiertes NO_TRADE

Fehlende oder widersprüchliche Evidenz erzeugt keine Ausnahme und keinen stillen Kandidaten, sondern eine kanonische `NO_TRADE`-Entscheidung mit maschinenlesbaren Blockern.

Bis Aufgaben 16 bis 18 umgesetzt sind, lauten die produktiven Supportzustände weiterhin `INSUFFICIENT_EVIDENCE` für:

- vollständige 360-Tage-Kandidatenmatrix;
- PBO;
- DSR.

Daher ist der einzig produktiv transaktionsfähige Task-15-Zustand aktuell `NO_TRADE`.

Zusätzlich wurde adversarial geschlossen:

- unvollständige Quality-Gate-/Ranking-Evidenz führt zu `NO_TRADE` statt `KeyError` oder `TypeError`;
- gefälschte `claimed_gate_passed`-Felder können die echten Gates nicht umgehen;
- fehlende Kandidaten, fehlende Finalisten, PBO-/DSR-Fehler und Quality-Gate-Fehler bleiben getrennte Blocker;
- Inputreihenfolge und JSON-Serialisierung verändern das Ergebnis nicht.

## Synthetischer Kandidatenpfad

Damit Rangfolge und Tie-Breaks bereits in Aufgabe 15 testbar sind, existiert ein ausdrücklich markierter Modus `SYNTHETIC_TEST_FIXTURE`.

Dieser Modus:

- darf nur Tests vollständig simulieren;
- implementiert keine echte Tagesmatrix, kein PBO und kein DSR;
- wird in der Entscheidung mit `fixture_only=true` gebunden;
- wird am Task-13-/Task-15-Transaktionsrand vollständig abgelehnt;
- kann keinen Cache-, Resume-, Paper-, Testtrade-, Live- oder Orderzustand erzeugen.

Damit wird keine Aufgabe 16 bis 18 vorgezogen.

## Transaktions-, Cache- und Resume-Bindung

Der temporäre Kandidatenzustand `NOT_APPLICABLE/task15_not_implemented` ist nicht mehr zulässig.

Der Kandidatenslot muss jetzt:

- Zustand `BOUND` besitzen;
- Schema `protocol_v3_candidate_selection_identity_v1` verwenden;
- die vollständige revalidierte Auswahlentscheidung enthalten;
- Entscheidung, Digest und ID erneut berechnen;
- dieselben Run-, Kontext-, Kosten-, Gate-, Ledger-, Fold- und Pipelineidentitäten wie die übrigen Transaktionsslots besitzen.

Der Transaktionsvertrag wurde fortgeschrieben zu:

- Vertragsschema: `protocol_v3_transaction_contract_v3`;
- Vertrag: `protocol_v3_content_addressed_cache_and_transactional_resume_with_inner_selection_v3`;
- Transaktionsidentität: `protocol_v3_transaction_identity_v3`.

Die Anzahl und Reihenfolge der 16 Pflichtslots bleibt unverändert. Rotation bleibt `GENESIS`.

Alte Task-14-Cache-/Resume-Identitäten ohne gebundene Task-15-Entscheidung können nicht treffen.

## Während der CI gefundene und korrigierte Befunde

1. Gemeinsames Testfixture exportierte `read_trial_ledger` versehentlich nicht mehr. Nur das Fixture wurde kompatibel repariert.
2. Die Task-15-Transaktionsprüfung griff beim frühen Build-Schritt auf erst später abgeleitete Slots zu. Vorprüfung und abschließende 16-Slot-Cross-Bindung wurden getrennt.
3. Die neue Kandidatensperre verdeckte in zwei Task-14-Negativtests den präziseren Fold-/Horizon-Fehler. Prüfungsreihenfolge wurde auf Fold/Horizon → Kandidat → Rotation gesetzt, ohne eine Regel zu lockern.
4. Adversarialer Zusatzbefund: unvollständige Kandidatenevidenz konnte vor der Rankingprüfung als Python-Fehler enden. Die stabile API wandelt dies jetzt reproduzierbar in typisiertes `NO_TRADE` um; ein eigener Regressionstest belegt den Fall.

## Tests und CI

Neue Task-15-Testfälle: 9.

Abgedeckt sind:

- exakter Vertrag und stabile öffentliche API;
- Pipeline- und Transaction-v3-Bindung;
- produktives `NO_TRADE` bei fehlenden Aufgaben 16 bis 18;
- schlechtester Fold vor besserem Aggregat;
- freie Parameter und Kandidaten-ID als letzte Tie-Breaks;
- Permutations- und Serialisierungsdeterminismus;
- erneute echte Quality-Gate-Auswertung;
- Zielwert-, Outer- und Future-Read-Sperren;
- manipulierte Run-/Kontextidentitäten;
- Ablehnung des alten Candidate-`NOT_APPLICABLE`;
- Ablehnung synthetischer Kandidaten am Transaktionsrand;
- unvollständige Kandidatenevidenz als typisiertes `NO_TRADE`.

CI-Historie:

- Review CI Run 468: Fixture-Exportfehler;
- Review CI Run 469: zu frühe Cross-Slot-Prüfung;
- Review CI Run 470: zwei präzisere Task-14-Fehler wurden verdeckt;
- Review CI Run 471: vollständig grün;
- adversarialer Missing-Evidence-Zusatztest und Fail-closed-Adapter;
- Review CI Run 473: vollständig grün.

Vollständige Suite: `1.111 Tests erfolgreich`.

Python-Kompilierung, PowerShell-Syntax, Whitespace-Prüfung und abschließendes Pytest-Gate waren grün.

## Ehrlicher aktueller Zustand

```text
Task-14-Re-Audit = bestanden, keine weitere Korrektur erforderlich
Task-15-reine Auswahlfunktion = implementiert
Task-15-exakte Rangfolge = implementiert
Task-15-typisiertes NO_TRADE = implementiert
Task-15-Transaktions-/Cache-/Resume-Bindung = implementiert
Task-16-Kandidaten-Tagesmatrix = nicht implementiert
Task-17-PBO = nicht implementiert
Task-18-DSR = nicht implementiert
realer Protocol-v3-Langlauf = weiterhin nicht ausführbar
Performance-/3-USDC-/Final-/Live-Freigabe = nicht behauptet
Paper/Testtrade/Live/Orders/API-Keys = gesperrt
```

## Explizit nicht umgesetzt

Keine Aufgabe 16 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- keine echte vollständige 360-Tage-Kandidatenmatrix;
- keine PBO-/CSCV-Berechnung;
- keine DSR- oder Multiple-Testing-Berechnung;
- kein Multi-Timeframe-Feature-Store;
- kein Opportunity-/Regimemodell;
- keine Spezialisten oder Router;
- kein FrozenCandidateBundle;
- keine Outer-Origin-Orchestrierung;
- keine Rotationspersistenz;
- kein tägliches MTM-Ledger;
- kein Challenger-Controller;
- kein Final-Evaluator;
- keine UI-Erweiterung;
- keine Orders, Trading-API, API-Keys, Paper, Testtrade oder Live.

## Startanweisung für Aufgabe 16

Vor Aufgabe 16 muss Aufgabe 15 am dann aktuellen Code adversarial geprüft werden. Besonders zu kontrollieren sind:

- stabile öffentliche API ohne UI-/Zeit-/Netzwerk-/Outer-Zugriffe;
- identische Eingaben erzeugen bitgleiche Entscheidung;
- exakte Rangfolge und letzte Tie-Breaks;
- `3 USDC/Tag` bleibt aus Ranking und Stoplogik ausgeschlossen;
- fehlende oder widersprüchliche Evidenz bleibt typisiertes `NO_TRADE`;
- synthetische Fixtures bleiben am Transaktionsrand unbrauchbar;
- Task-15-Entscheidung bleibt vollständig an Run, Pipeline, Fold, Kontext, Kosten, Gates und Ledger gebunden;
- keine vorgezogene PBO-, DSR-, Feature-, Router- oder Outer-Logik.

Erst nach eventueller separater Korrektur und grüner CI darf Aufgabe 16 beginnen.

## Exakt nächstes Ticket

`Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets`
