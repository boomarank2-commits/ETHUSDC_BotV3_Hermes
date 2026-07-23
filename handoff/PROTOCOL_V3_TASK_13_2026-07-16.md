# Protocol v3 – Handoff Aufgabe 13/33

Stand: 2026-07-16

## Status

`Protocol v3: Aufgabe 13/33 – Content-addressed Cache und transaktionales Resume – DONE_100`

Dieser Status gilt nach grüner Review CI des Commits, der dieses Handoff und die aktualisierte Implementierungsreihenfolge enthält.

Gesamtfortschritt: `13/33 = 39,39 %`.

Exakt nächste Aufgabe: `Aufgabe 14 – Exakten inneren 6×60-Tage-Fold-Planer bauen`.

## Ausgangsstand und vorgeschaltete Prüfung

Verbindlicher Ausgangs-Head vor dem Review von Aufgabe 12 war:

`3d7b522b34334c33e98fe2e38feb3bef528bbc1d`

PR #17 blieb offen, Draft und ungemerged.

Vor Aufgabe 13 wurde Aufgabe 12 am echten Code adversarial geprüft. Kontrolliert wurden insbesondere:

- vollständige transitive Revalidierung jedes referenzierten Task-12-Objekts;
- aus tatsächlichen Bytes abgeleitete Digests, Bytegrößen und Kardinalitäten;
- vollständige Elternreport-, Run-Fingerprint-, Pipeline- und Work-Unit-Provenienz;
- create-only Objekt- und Indexpersistenz;
- Deduplikation ohne blindes Vertrauen in vorhandene Digestpfade;
- Root-, Traversal-, Alias- und Symlink-Sperren;
- keine eingebetteten Rohkerzen oder langen Reihen im kompakten Index;
- keine vorgezogene Task-13-Transaktionslogik in Aufgabe 12.

## Separate Task-12-Korrektur

Gefunden wurde ein konkreter Reihenfolgefehler im öffentlichen Task-12-Lesepfad: Ein fremder oder symlinkierter Indexpfad wurde erst nach dem Einlesen gegen seine feste Root geprüft.

Korrekturcommits:

- `4622e71e371399c428306d4517a21df72ea60c3a` – Manipulationstests;
- `ff6751ecda0935f1dd0ce50d1acfd4717be27579` – Pfadprüfung vor dem ersten Read;
- `c656d8c7be965fe86c882780347324f880e839d3` – Korrekturbericht.

Korrekturbericht:

`handoff/PROTOCOL_V3_TASK_12_PATH_GUARD_CORRECTION_2026-07-16.md`

Review CI Run 427 war vollständig grün:

`https://github.com/boomarank2-commits/ETHUSDC_BotV3_Hermes/actions/runs/29514504023`

Erst danach begann Aufgabe 13.

## Implementierte Dateien

Produktionsdateien:

- `configs/protocol_v3_transaction_contract.json`;
- `configs/protocol_v3_pipeline_contract.json`;
- `src/ethusdc_bot/protocol_v3/transactional_cache_model.py`;
- `src/ethusdc_bot/protocol_v3/transactional_cache_store.py`;
- `src/ethusdc_bot/protocol_v3/transactional_cache.py`;
- `src/ethusdc_bot/protocol_v3/transactional_cache_api.py`;
- `.gitignore`.

Tests:

- `tests/unit/protocol_v3_task13_support.py`;
- `tests/unit/test_protocol_v3_transactional_cache.py`.

Dokumentation:

- `handoff/PROTOCOL_V3_TASK_13_2026-07-16.md`;
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`.

## Versionierter Vertrag

Eingefroren wurden:

- Vertrag: `protocol_v3_content_addressed_cache_and_transactional_resume_v1`;
- Identity-Slot-Schema: `protocol_v3_transaction_identity_slot_v1`;
- Transaktionsidentität: `protocol_v3_transaction_identity_v1`;
- Checkpoint-Schema: `protocol_v3_transaction_checkpoint_v1`;
- Checkpoint-HEAD-Schema: `protocol_v3_checkpoint_head_v1`;
- Cache-Record-Schema: `protocol_v3_cache_record_v1`;
- Lock-Schema: `protocol_v3_transaction_lock_v1`.

Feste generierte Roots:

- `reports/protocol_v3/checkpoints`;
- `reports/protocol_v3/cache`;
- `reports/protocol_v3/transaction_locks`;
- `reports/protocol_v3/recovered_locks`.

Alle vier Roots sind Git-ignoriert.

## Vollständige Transaktionsidentität

Jede Transaktion verlangt exakt diese 16 Identitätsslots in kanonischer Reihenfolge:

1. `three_market_data`;
2. `code_pipeline`;
3. `feature_identity`;
4. `context_identity`;
5. `candidate_identity`;
6. `fold_identity`;
7. `boundary_identity`;
8. `horizon_identity`;
9. `execution_identity`;
10. `simulator_identity`;
11. `cost_identity`;
12. `quality_gate_identity`;
13. `exchange_info_identity`;
14. `trial_ledger_head`;
15. `rotation_state_identity`;
16. `sealed_store_heads`.

Fehlende Slots, `None`, zusätzliche Slots, andere Reihenfolge oder frei behauptete Digests blockieren.

Jeder Slot besitzt ausdrücklich genau einen Zustand:

- `BOUND`;
- `GENESIS`;
- `NOT_APPLICABLE`.

Bis zu den jeweils zuständigen späteren Aufgaben gelten typisierte Übergangszustände:

- Kandidat: `NOT_APPLICABLE`, weil Aufgabe 15 noch nicht implementiert ist;
- Fold: `NOT_APPLICABLE`, weil Aufgabe 14 noch nicht implementiert ist;
- Rotation: `GENESIS`, weil noch kein Task-24-Rotationszustand existiert;
- Task-12-Store-Heads: `BOUND` bei vorhandenen validierten Indizes oder `GENESIS` bei noch keinem committed Index.

Damit werden fehlende Identitäten nicht durch leere oder optionale Felder kaschiert.

## Revalidierung vorhandener Wahrheiten

Die Transaktionsidentität wird nicht aus frei gelieferten Hashes aufgebaut. Sie revalidiert und bindet:

- den vollständigen Run-Fingerprint v2;
- die konkrete `ContextParityBinding` und deren Gleichheit mit dem Fingerprint;
- Task-5-Rohdaten- und Drei-Markt-Identität;
- Codecommit und Pipelinegeneration;
- Feature-, Boundary-, Simulator-, Kosten- und Quality-Gate-Komponenten;
- Exchange-Info-Snapshot;
- den Entscheidungspunkt des permanenten Trial-Ledgers;
- die Task-9-Horizon-Policy;
- Task-7-/Task-8-Ausführungsverträge;
- alle referenzierten Task-12-Indizes und deren vollständige Objekt-/Report-Provenienz.

Ein Cache- oder Resume-Treffer ist nur bei exakt derselben vollständigen Transaktionsidentität zulässig.

## Checkpoint-Transaktion

Jeder Checkpoint enthält und validiert:

- vollständige Transaktionsidentität;
- unverändertes Pre-Run-Manifest;
- deterministischen Seed-Namespace und daraus abgeleiteten Seed;
- reservierte globale Budgetzähler;
- Stop-/Stagnationszustand;
- Ergebniszustand und Ergebnisdigest;
- revalidierte Task-12-Indexköpfe;
- Trial-Ledger-Receipt;
- Safety-Sperren;
- Sequenz, vorherigen Checkpoint-Hash und vollständigen Checkpoint-Hash.

Persistenzfolge:

1. Temp-Datei im selben Zielverzeichnis;
2. Schreiben, Flush und Datei-`fsync`;
3. kanonischer Reload und vollständige semantische Validierung;
4. atomarer Replace auf den immutable Checkpointpfad;
5. erneuter Reload;
6. atomarer Replace des separaten `HEAD.json`;
7. erneute Prüfung, dass `HEAD.json` exakt auf den erwarteten Checkpoint zeigt.

Nur `HEAD.json` macht einen Checkpoint sichtbar. Verwaiste Temp-Dateien oder bereits geschriebene, aber noch nicht durch `HEAD.json` veröffentlichte Checkpoints gelten nicht als committed und werden beim Resume ignoriert.

Die gesamte Checkpoint-Kette wird rückwärts bis zur Genesis auf Sequenz, Hashverkettung und Transaktionsidentität geprüft.

## Resume

Resume verwendet ausschließlich den letzten committed `HEAD.json`-Stand.

Zusätzlich werden vor Fortsetzung erneut geprüft:

- aktuelle vollständige Transaktionsidentität;
- aktuelles Pre-Run-Manifest;
- komplette Checkpoint-Kette;
- alle Task-12-Artefakte und Elternreports;
- Trial-Ledger-Receipt;
- kanonische Bytes und Digests.

Ein geänderter Daten-, Kontext-, Feature-, Kandidaten-, Fold-, Boundary-, Horizon-, Execution-, Simulator-, Kosten-, Code-, Pipeline-, Exchange-, Trial- oder Rotationsbestand blockiert Resume beziehungsweise erzeugt eine andere Transaktionsidentität.

## Exklusive Writer-Locks

Locks werden create-only und exklusiv erstellt.

Blindes Überschreiben eines vorhandenen oder vermeintlich veralteten Locks ist verboten.

Eine Recovery ist nur zulässig, wenn:

- das Lock kanonisch und digestvalid ist;
- es vom selben Host stammt;
- der gebundene Prozess nachweislich nicht mehr existiert.

Ein lebender Prozess oder unklarer Prozess-/Hostzustand blockiert. Erfolgreich geborgene Locks werden nicht gelöscht, sondern als immutable Recovery-Receipt nach `reports/protocol_v3/recovered_locks` verschoben.

Release verlangt exakt denselben Lockdigest, Eigentümer und aktuellen Prozess.

## Content-addressed Cache

Ein Cache-Record darf nur aus dem aktuell committed Checkpoint-HEAD eines abgeschlossenen oder `NO_TRADE`-Ergebnisses veröffentlicht werden.

Ein Cache-Hit revalidiert transitiv:

- Cache-Record und komplette Transaktionsidentität;
- committed Checkpoint und Checkpoint-Kette;
- Ergebnisdigest;
- sämtliche Task-12-Indizes, Objekte und Elternreports;
- Trial-ID im permanenten Trial-Ledger;
- Entscheidungs- beziehungsweise Reuse-Head des Ledgers.

Der Cache-Key ist der SHA-256 der vollständigen Transaktionsidentität. Ändert sich auch nur ein Identitätselement, entsteht ein anderer Key; es gibt keinen toleranten oder partiellen Cache-Hit.

## Permanentes Trial-Ledger und idempotente Cache-Reuse-Heilung

Cache-Wiederverwendung wird über die vorhandene Task-4-Funktion `record_cache_reuse(...)` append-only in das permanente Trial-Ledger geschrieben.

Dabei gilt weiterhin:

- Cache-Reuse zählt nicht als unabhängiger Trial;
- Event-Key wird deterministisch aus Trial-ID und vollständigem Reuse-Scope erzeugt;
- identischer Retry erzeugt kein zweites Event;
- fremder Ledgerfortschritt blockiert.

Der tatsächliche Task-4-Vertrag verwendet `event_sha256`. Der generische Task-13-Checkpoint-Receipt speichert diesen geprüften Wert im Feld `event_hash`. Der Adapter prüft Sequenz, Event-Key, `event_sha256`, Ledger-Eventzahl und Ledger-HEAD gemeinsam.

Ein gezielter Fault-Injection-Test unterbricht unmittelbar nach dem Ledger-Append und vor der Checkpoint-Veröffentlichung. Beim Retry wird genau dasselbe bestehende Reuse-Event erkannt und gebunden; der `cache_reuse_count` bleibt exakt eins.

## Fault-Injection

Getestete Unterbrechungspunkte:

- vor dem Checkpoint-Temp-Write;
- nach Temp-Write und `fsync`;
- nach Temp-Revalidierung;
- nach Checkpoint-Replace;
- nach Checkpoint-Reload;
- nach Ledger-Reuse-Append;
- vor dem `HEAD.json`-Replace;
- nach dem `HEAD.json`-Replace.

Erwartetes Verhalten:

- alle Fehler vor dem HEAD-Replace lassen den vorherigen committed Stand sichtbar;
- ein Fehler nach dem HEAD-Replace gilt als committed und wird beim nächsten Prozess korrekt geladen;
- ein Crash nach Ledger-Reuse-Append erzeugt beim Retry kein doppeltes Ledger-Event.

## Tests und CI

Neue Task-13-Tests: 9.

Abgedeckt sind:

- exakter Vertrag, öffentliche Fassade und Pipelinebindung;
- echte Run-Fingerprint-/ContextParity-/Task-12-Integration;
- alle 16 Identitätsslots sowie Missing-/`None`-Manipulation;
- Checkpoint-Roundtrip und vollständige Hashkette;
- Reload in einem neuen Python-Prozess;
- Fault-Injection vor und nach dem committed HEAD;
- transitive Cache-Revalidierung;
- Identitätsänderung ohne Cache-Hit;
- manipulierte beziehungsweise verkürzte Task-12-Objekte;
- Crash zwischen Ledger-Append und Checkpoint-HEAD;
- exklusive Writer-Locks;
- blockierte Recovery bei lebendem Prozess;
- Recovery eines nachweislich toten Same-Host-Prozesses;
- verkürztes HEAD, Duplicate-JSON und Symlink-Angriffe.

CI-Historie:

1. Review CI Run 436: Testfixture verwendete versehentlich Task-12-Tagesfeldnamen statt der kanonischen Task-4-Felder. Produktionscode, Compile, PowerShell und Whitespace waren nicht betroffen.
2. Review CI Run 437: Testfixture verwendete einen veralteten festen Task-11-Reportzeitpunkt. Die produktive create-only Zeitsperre blieb unverändert.
3. Review CI Run 438: echter Integrationsfehler gefunden – Task 13 las `event_hash`, während das permanente Task-4-Ledger `event_sha256` verwendet.
4. Korrekturcommit: `ab9fee4caa355300a84fad316710ab97e52588d3`.
5. Review CI Run 439: vollständig grün.
6. Vollständige Suite: 1.091 Tests erfolgreich.
7. Python-Kompilierung, PowerShell-Syntax, Whitespace und abschließender Pytest-Gate-Schritt: grün.

Review CI Run 439:

`https://github.com/boomarank2-commits/ETHUSDC_BotV3_Hermes/actions/runs/29517939662`

## Ehrlicher aktueller Zustand

```text
Task-12-Pfadkorrektur = implementiert und CI-grün
Task-13-Vertrag und vollständige Identität = implementiert und pipelinegebunden
Task-13-Checkpoints/HEAD/Locks/Cache = implementiert
Task-13-Fault-Injection und Prozess-Reload = grün
Task-13-Ledger-Reuse-Heilung = grün
Task-14-Fold-Planer = nicht implementiert
realer Protocol-v3-Langlauf = weiterhin nicht ausführbar
Performance-/3-USDC-/Final-/Live-Freigabe = nicht behauptet
Paper/Testtrade/Live/Orders/API-Keys = gesperrt
```

## Explizit nicht umgesetzt

Keine Aufgabe 14 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- kein innerer 6×60-Tage-Fold-Planer;
- keine Timestamp-Spies für Task 14;
- keine reine Kandidatenauswahl aus Aufgabe 15;
- keine Kandidaten-Tagesmatrix;
- keine PBO-/DSR-Berechnung;
- kein Multi-Timeframe-Feature-Store;
- kein Opportunity-/Regimemodell;
- kein Router oder FrozenCandidateBundle;
- keine Outer-Origin-Orchestrierung;
- keine Task-24-Rotationspersistenz;
- kein Challenger-Controller;
- kein Final-Evaluator;
- keine UI;
- keine Orders, Trading-API, API-Keys, Paper, Testtrade oder Live.

## Startanweisung für Aufgabe 14

Vor Aufgabe 14 muss Aufgabe 13 am dann aktuellen Code adversarial geprüft werden. Besonders zu kontrollieren sind:

- identische Semantik bei direktem Modulimport und stabiler öffentlicher Fassade;
- keine fehlenden oder frei behauptbaren Identitätsslots;
- vollständige transitive Revalidierung von Cache, Checkpoint und Task-12-Artefakten;
- Resume ausschließlich vom committed HEAD;
- Unsichtbarkeit verwaister Temp- und Checkpointdateien;
- vollständige Checkpoint-Kette bis Genesis;
- Lock-Recovery nur bei eindeutigem Same-Host-Dead-Process-Nachweis;
- kein doppeltes Cache-Reuse-Ledger-Event nach jedem Fault-Injection-Punkt;
- keine vorgezogene Fold-, Auswahl- oder Outer-Orchestrierungslogik.

Erst nach eventueller separater Korrektur und grüner CI darf Aufgabe 14 beginnen.

## Exakt nächstes Ticket

`Aufgabe 14 – Exakten inneren 6×60-Tage-Fold-Planer bauen`
