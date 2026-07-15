# Protocol v3 – Handoff Aufgabe 10/33

Stand: 2026-07-15

## Status

`Protocol v3: Aufgabe 10/33 – Kontextparität und Drei-Markt-Watermark – DONE_100`

Gesamtfortschritt nach finaler Dokumentations-CI: `10/33 = 30,30 %`.

Exakt nächste Aufgabe: `Aufgabe 11 – Protocol-v3-Report-Schemas und Evidenzbedeutung`.

## Aufgabe 9 erneut vollständig geprüft

Vor Beginn von Aufgabe 10 wurde der finale Task-9-Stand erneut geprüft:

- kontrollierter Ausgangs-Head: `84bd2ca2a0d1028a701501df42565dee76e2ef8b`;
- Review-CI Run 403 vollständig grün;
- PR #17 offen, mergebar, Draft und nicht gemerged;
- Warmup bleibt ausschließlich für kausale Feature-Reads erlaubt;
- Purge bleibt `max(max_label_horizon,max_holding_period+pending_entry_latency)+1 Ausführungsbar`;
- innere Folds starten flat;
- Fold-Ende liquidiert konservativ;
- zwischen Origins wird ausschließlich höchstens eine offene Position übernommen;
- Pending Entry, Cooldown, Scaler- und Runtime-Modellzustand werden nicht übernommen;
- alte Konfiguration bleibt `exit_only`;
- neue Entries beginnen erst bei `max(valid_from,flat_time)`.

Ergebnis: Aufgabe 9 ist fachlich und technisch wie vorgesehen umgesetzt und bleibt unverändert `DONE_100`.

## Vorhandene Funktionen geprüft und wiederverwendet

Vor der Umsetzung wurden insbesondere geprüft:

- `src/ethusdc_bot/backtest/context_features.py`
  - bestehendes trailing-only Kontext-Veto;
  - kann nur ein vorhandenes ETHUSDC-Signal bestätigen oder blockieren;
  - kann kein Signal und keine Order erzeugen;
  - BTC-Trend, BTC-Volatilität und ETHBTC-relative Stärke;
  - kausale Lookbacks und Future-Mutation-Test.
- `src/ethusdc_bot/backtest/context_research.py`
  - exakter zusammenhängender Drei-Markt-Slice;
  - kein Nearest-Neighbor, kein Fill, keine Interpolation;
  - ETHUSDC-Kandidaten werden mit vorhandener Kontextpolitik umschlossen.
- `src/ethusdc_bot/backtest/data_loader.py`
  - ETHUSDC ist einziges Handelssymbol;
  - BTCUSDC und ETHBTC sind reine Kontextmärkte;
  - exakte eins-zu-eins UTC-1m-Ausrichtung.
- `src/ethusdc_bot/backtest/simulator.py`
  - Kontext wird erst nach einem vorhandenen Basissignal geprüft;
  - fehlender Kontext blockiert;
  - vorhandene Signalentscheidung wurde nicht dupliziert.
- `src/ethusdc_bot/protocol_v3/data_snapshot.py`
  - Task-5-Watermark, Rohintervall, gemeinsamer Rasterdigest und drei Marktinhaltsdigests.
- `src/ethusdc_bot/protocol_v3/intrabar_execution.py`
  - Task-8-Ausführungsengine bleibt die einzige Fill- und Trade-Engine.

Es wurde keine zweite Kontext-, Signal- oder Ausführungsengine gebaut.

## Was umgesetzt wurde

### 1. Versionierter Kontextparitätsvertrag

Neue Datei `configs/protocol_v3_context_parity_contract.json` friert ein:

- Schema `protocol_v3_context_parity_contract_v1`;
- Vertrag `three_market_closed_bar_context_parity_v1`;
- ETHUSDC als einziges `trade_market`;
- BTCUSDC und ETHBTC ausschließlich `context_only`;
- Kontextmärkte können weder Signal noch Trade erzeugen;
- vier Auswertungspfade:
  - `research`;
  - `replay`;
  - `final_evaluator`;
  - `research_challenger`;
- alle vier Pfade verwenden dieselbe Kontextengine und dieselbe Kandidatenpolitik;
- Entscheidung nur auf der vollständig geschlossenen gemeinsamen 1m-Bar;
- fehlender, versetzter, veralteter oder zukünftiger Kontext blockiert;
- Nearest-Neighbor, Forward-Fill und Interpolation sind verboten;
- Task-5-Snapshot, gemeinsamer Rasterdigest, drei Marktinhaltsdigests und Fensterinhalte sind identitätsgebunden;
- Cache-/Resume-Wiederverwendung erfordert exakt dieselbe Kontextidentität;
- Safety-Locks bleiben unverändert.

### 2. Gemeinsame Protocol-v3-Kontextbindung

Neue Datei `src/ethusdc_bot/protocol_v3/context_parity.py` stellt bereit:

- `ContextParityBinding`;
- `build_context_parity_binding`;
- `validate_context_parity_binding`;
- `evaluate_closed_bar_context`;
- `simulate_protocol_v3_context_path`;
- `simulate_protocol_v3_context_portfolio_path`;
- `assert_context_identity_compatible`.

Die Bindung enthält:

- den exakten ETHUSDC/BTCUSDC/ETHBTC-1m-Ausschnitt;
- die eingefrorene `ContextVetoPolicy`;
- Task-5-Snapshot-SHA-256;
- gemeinsamen Snapshot-Rasterdigest;
- drei vollständige Snapshot-Marktinhalt-Digests;
- drei Fenster-Marktinhalt-Digests;
- ersten Timestamp;
- gemeinsame letzte geschlossene 1m-Watermark;
- Candle-Anzahl;
- deterministische Kontextidentität.

### 3. Exakte geschlossene Drei-Markt-Bar

Für Index `i` gilt:

```text
ETHUSDC.open_time[i]
= BTCUSDC.open_time[i]
= ETHBTC.open_time[i]

decision_time
= open_time[i] + 59.999 ms
```

- früherer Entscheidungszeitpunkt: ungeschlossene/zukünftige Daten, blockiert;
- späterer Entscheidungszeitpunkt: veralteter Kontext, blockiert;
- fehlender oder versetzter Marktpunkt: blockiert;
- Lücken oder nicht zusammenhängendes 1m-Raster: blockiert.

Es wird kein vorheriger oder nächster Kontextpunkt ersatzweise verwendet.

### 4. Watermark ist an den Task-5-Snapshot gebunden

Ein Kontextfenster ist nur gültig, wenn:

- der Task-5-Snapshot semantisch und per Digest gültig ist;
- das gesamte Fenster innerhalb des eingefrorenen Rohintervalls liegt;
- die letzte Kontextbar nicht über den letzten gemeinsamen vollständigen UTC-Tag hinausreicht;
- der gemeinsame Minutenrasterdigest gültig ist;
- alle drei Marktinhaltsdigests vorhanden und gültig sind.

Task 10 erzeugt keine zweite Daten-Watermark. Es bindet die Laufzeitentscheidung an die bereits in Aufgabe 5 eingefrorene gemeinsame Datenwahrheit.

### 5. Kontext bleibt reines Veto/Bestätigung

Der gemeinsame Ablauf lautet:

```text
bestehendes ETHUSDC-Basissignal
→ exakt gebundener BTCUSDC-/ETHBTC-Kontext
→ bestätigen oder blockieren
→ bei Bestätigung dieselbe Task-8-Ausführungsengine
```

BTCUSDC und ETHBTC:

- können kein Signal erzeugen;
- können keinen Trade auslösen;
- können nie als Handelssymbol in die Engine gelangen;
- verändern keine Entry-, Exit-, Mengen-, Fee- oder Intrabar-Regel.

### 6. Identische Pfade

Die vier Pfadnamen sind keine vier Simulatoren. Alle rufen dieselbe Funktion, dieselbe Kontextpolitik und dieselbe Task-8-Ausführungsengine auf.

Golden-Tests vergleichen für alle Pfade bitgleich:

- Trades;
- Metriken;
- Signal-Funnel;
- Ablehnungsgründe.

Der orderfreie Portfolio-/Shadow-Ausgabepfad nutzt ebenfalls dieselbe Kontextbindung und dieselbe Intrabar-Engine.

### 7. Deterministische Kontextidentität

Die Kontextidentität bindet mindestens:

```text
context contract version
context policy version und vollständige Policy
Task-5 data snapshot SHA-256
gemeinsamer Snapshot-Rasterdigest
drei Snapshot-Marktinhalt-Digests
drei konkrete Fenster-Marktinhalt-Digests
erster Timestamp
gemeinsame letzte geschlossene Watermark
Candle-Anzahl
```

`cache_key` und `resume_key` sind identisch. Jede Änderung an BTCUSDC, ETHBTC, ETHUSDC, Policy, Zeitfenster oder Snapshot blockiert Wiederverwendung.

### 8. Pipeline- und Run-Fingerprintbindung

`configs/protocol_v3_pipeline_contract.json` verwendet jetzt:

```text
context_policy = three_market_closed_bar_context_parity_v1
simulator = next_tradable_price_pessimistic_intrabar_with_fold_outer_state_and_context_parity_v1
```

Gebunden sind unter anderem:

- `configs/protocol_v3_context_parity_contract.json`;
- `src/ethusdc_bot/protocol_v3/context_parity.py`;
- Task-5-Datensnapshot-Vertrag und Implementierung;
- bestehende Kontextfeatures und Research-Adapter;
- Task-8-Intrabar-Engine;
- Task-9-Runtime-State.

Der bestehende Run-Fingerprint führt `context` ausdrücklich als Identitätsklasse. Eine Änderung am Kontextvertrag oder an der Kontextimplementierung ändert die Pipelinegeneration, den Run-Fingerprint sowie Cache-/Resume-Key.

## Tests

Die Suite prüft mindestens:

- exakten Vertrag und Safety-Locks;
- BTCUSDC/ETHBTC niemals handelbar;
- gültige Task-5-Snapshotbindung;
- Fenster vollständig innerhalb des Snapshot-Rohintervalls;
- gemeinsame Watermark nicht nach dem Snapshot-Ende;
- geschlossene Bar exakt bei `open_time+59.999 ms`;
- ungeschlossene Zukunftsdaten blockieren;
- stale Kontextdaten blockieren;
- fehlende Kontextzeile blockiert;
- versetzte Kontextzeile blockiert;
- keine Lücken oder nicht zusammenhängende Minuten;
- Kontext kann ein vorhandenes ETHUSDC-Signal vetoen;
- Kontext erzeugt nie ein eigenes Signal;
- alle vier Auswertungspfade bitgleich;
- veränderte Marktwerte erzeugen neue Kontextidentität;
- unterschiedliche Kontextidentität blockiert Cache/Resume;
- BTCUSDC-Kandidat kann die Trade-Engine nicht betreten;
- manipulierte Snapshot-Watermark blockiert;
- unbekannter oder gesperrter Pfad wie `paper` blockiert;
- Task-8- und Task-9-Verträge bleiben separat und weiterhin gebunden;
- öffentliche Protocol-v3-Schnittstelle und Run-Fingerprint-Kontextklasse vorhanden.

## CI-Historie

1. Review-CI Run 406 war technisch bis auf einen Test rot. Ursache war ausschließlich ein zu enger erwarteter Fehlermeldungstext: Die bestehende Validierung meldete bei verkürztem BTCUSDC-Kontext korrekt `timestamps differ`, der Test erwartete nur `equal length`.
2. Es wurde ausschließlich die Testregex an beide korrekten fail-closed-Diagnosen angepasst. Produktionscode und Kontextregel wurden nicht gelockert.
3. Review-CI Run 407 war vollständig grün.
4. Review-CI Run 410 nach Pipelinebindung und aktualisierten Task-8-/Task-9-Regressionsassertionen war vollständig grün.
5. Review-CI Run 412 nach öffentlicher Schnittstelle und eigener Fingerprint-Regressionsprüfung war vollständig grün.
6. Der finale Dokumentations-/Handoff-Head wird nochmals durch dieselbe vollständige Review-CI geprüft.

## Ehrlicher aktueller Laufzustand

```text
Task-10-Implementierung = bereit und getestet
Task-9-State = erneut geprüft und unverändert
synthetische Drei-Markt-/Watermark-/Paritätstests = grün
realer Protocol-v3-Langlauf = weiterhin nicht ausführbar
```

Der reale Lauf bleibt blockiert, weil:

- noch kein realer Task-6-Exchange-Info-Snapshot versiegelt ist;
- der reale Task-5-Datensnapshot weiterhin `BLOCKED_MISSING_WARMUP` ist;
- Report-Schemas, exakter Fold-Planer und Outer-Orchestrierung erst in späteren Aufgaben entstehen.

Das ist keine Performance-, Zielerreichungs- oder Freigabebehauptung.

## Neue und geänderte Dateien

- `configs/protocol_v3_context_parity_contract.json`
- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/context_parity.py`
- `src/ethusdc_bot/protocol_v3/__init__.py`
- `tests/unit/test_protocol_v3_context_parity.py`
- `tests/unit/test_protocol_v3_context_parity_binding.py`
- `tests/unit/test_protocol_v3_intrabar_execution_binding.py`
- `tests/unit/test_protocol_v3_runtime_state_binding.py`
- `handoff/PROTOCOL_V3_TASK_10_2026-07-15.md`
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 11 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- keine neuen Report-Schemas oder Storage-Roots;
- keine Freshness-/Adoption-/Evidenzreportlogik;
- keine kompakte Artefaktarchitektur;
- kein content-addressed Cache-Store oder transaktionales Resume;
- kein Multi-Timeframe-Feature-Store;
- kein Router oder FrozenCandidateBundle;
- keine Outer-Origin-Orchestrierung;
- kein Research-Challenger-Controller;
- kein Pipeline-Final-Evaluator;
- keine UI-Arbeit;
- keine Orders, Trading-API, API-Keys, Paper, Testtrade oder Live;
- kein finaler Holdout.

Die Pfadnamen `final_evaluator` und `research_challenger` beweisen nur, dass spätere Controller dieselbe Kontextfunktion verwenden müssen. Die Controller selbst bleiben Aufgabe 29 beziehungsweise Aufgabe 31.

## Safety

Unverändert gesperrt:

- Orders;
- Trading-API;
- API-Keys und Kontodaten;
- Paper;
- Testtrade;
- Live;
- finaler Holdout.

BTCUSDC und ETHBTC bleiben reine Kontextmärkte und können nie handeln.

## Codex-Startanweisung für Aufgabe 11

1. Branch `codex/research-resume-and-ui-state-v1` auf den finalen PR-Head ziehen.
2. `git status` muss sauber sein und lokaler `HEAD` muss GitHub entsprechen.
3. Dieses Handoff, Dokument 41, den Protocol-v3-Vertrag und vorhandene Report-/Schemafunktionen vollständig lesen.
4. Bestehende Research-, Monatsprozess-, Challenger-, Forward- und Finalreportstrukturen inventarisieren und wiederverwenden.
5. Danach ausschließlich Aufgabe 11 umsetzen.
6. Eigene versionierte Schemas und getrennte Storage-Roots müssen Legacy-Verwechslung verhindern.
7. Freshness, historische Zielerreichung, statistische Unterstützung und Adoption müssen semantisch fail-closed sein.
8. Sichtbare Forward-Monate dürfen niemals nachträglich als Finalfenster registriert werden.
9. Keine kompakte Artefaktarchitektur aus Aufgabe 12 und keinen Cache-/Resume-Store aus Aufgabe 13 vorziehen.
10. Paper, Testtrade, Live, Orders, private Endpunkte und API-Keys bleiben gesperrt.

## Exakt nächstes Ticket

`Aufgabe 11 – Protocol-v3-Report-Schemas und Evidenzbedeutung`
