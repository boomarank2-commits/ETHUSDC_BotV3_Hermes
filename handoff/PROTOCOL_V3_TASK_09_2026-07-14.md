# Protocol v3 – Handoff Aufgabe 9/33

Stand: 2026-07-14

## Status

`Protocol v3: Aufgabe 9/33 – Warmup-, Purge-, Fold-End- und Outer-State-Maschine – DONE_100`

Gesamtfortschritt nach Statusupdate: `9/33 = 27,27 %`

Exakt nächste Aufgabe: `Aufgabe 10 – Kontextparität und Drei-Markt-Watermark`.

## Aufgabe 8 erneut vollständig geprüft

Vor Beginn wurde Aufgabe 8 gegen den finalen PR-Stand geprüft:

- PR #17 war offen, mergebar, Draft und nicht gemerged.
- Kontrollierter Ausgangs-Head: `19640ad368b95c6a279c3eaf1676de0b2e408139`.
- Review-CI Run 393 war vollständig grün.
- Signalbar und Entrybar bleiben getrennt; Entry frühestens am nächsten positiven Volumen-1m-Open.
- Stop gewinnt weiter bei gleichzeitiger Stop-/Target-Berührung.
- Stop-Gaps verwenden den schlechteren Open; günstige Target-Gaps werden auf das Target begrenzt.
- Buy-/Sell-Tick-Rundung, Break-even-/Trailing-Aktivierung und terminale Liquidation blieben unverändert.
- Baseline, Slippage-Stress und Joint Stress verwenden weiterhin denselben Intrabar-Kern.
- Task-7-Mengen-, Notional- und Fee-Parität wird weiterhin direkt wiederverwendet.

Ergebnis: Aufgabe 8 ist fachlich so umgesetzt, wie vorgesehen, und bleibt `DONE_100`.

## Vorhandene Funktionen geprüft und wiederverwendet

Vor der Umsetzung wurden insbesondere geprüft:

- `src/ethusdc_bot/protocol_v3/boundaries.py`
  - exakte zwölf Origins;
  - `valid_from=T+24h`;
  - `valid_until`;
  - vorhandene Methode `resolve_entry_enabled_at(flat_time)` mit `max(valid_from, flat_time)`.
- `src/ethusdc_bot/protocol_v3/intrabar_execution.py`
  - konservativer Task-8-Sell-Fill;
  - adverse Slippage und Tick-Rundung;
  - kanonische Kostenprofile.
- `src/ethusdc_bot/protocol_v3/execution_parity.py`
  - exakte Task-7-Menge;
  - Exit-Notional und Exit-Fee;
  - Exchange-Info-gebundene Mengen-/Notionalprüfung.
- `src/ethusdc_bot/backtest/split.py`
  - bestehende Tages- und Leakage-Prüfungen;
  - nicht als Protocol-v3-Purge-Ersatz umgedeutet.
- `src/ethusdc_bot/backtest/walk_forward.py`
  - vorhandene Fold- und Evaluationspfade;
  - der alte Fold-Planer wurde bewusst nicht auf Protocol v3 umetikettiert, weil der exakte 6×60-Planer erst Aufgabe 14 ist.
- `src/ethusdc_bot/backtest/research_supervisor.py`
  - bestehende Protocol-v2-Resume-/Checkpoint-Prüfungen;
  - nicht als Protocol-v3-Rotation-State wiederverwendet oder erweitert, weil content-addressed Resume erst Aufgabe 13 ist.

Aufgabe 9 ergänzt daher eine getrennte, reine Protocol-v3-Zustands- und Grenzschicht. Es wurde keine zweite Signal-, Fill-, Kosten- oder Strategieengine gebaut.

## Was umgesetzt wurde

### 1. Versionierter Runtime-State-Vertrag

Neue Datei `configs/protocol_v3_runtime_state_contract.json` friert ein:

- Schema `protocol_v3_runtime_state_contract_v1`;
- Vertrag `warmup_purge_fold_outer_state_v1`;
- UTC und 1m-Ausführungsbar;
- Warmup nur für kausale Feature-Reads;
- Purge-Formel inklusive Pending-Latenz und einer zusätzlichen Ausführungsbar;
- Boundary-Touch purgt;
- innere Folds starten vollständig flat;
- Pending Entries werden am Fold-Ende verworfen;
- offene Fold-Positionen werden konservativ liquidiert;
- zwischen Outer-Origins wird ausschließlich eine offene Position übertragen;
- Pending, Cooldown, Scaler und Runtime-Modellzustand werden nicht übertragen;
- alte Konfiguration ist ausschließlich exit-only;
- neue Konfiguration wartet auf `valid_from` und `flat_time`;
- keine Liquidation an Monatsgrenzen;
- terminale Liquidation nur am Ende des gesamten Prozessfensters;
- Rotation-State ist kanonisch und SHA-256-identifizierbar;
- unveränderte Safety-Locks.

### 2. Warmup-Sperren

`WarmupWindow` trennt:

```text
[warmup_start, evaluation_start) = ausschließlich feature_read
[evaluation_start, evaluation_end) = normaler kausaler Evaluationsbereich
```

Im Warmup sind technisch blockiert:

- Signal;
- Label;
- PnL;
- Scaler-Fit;
- Quantile-Fit;
- Regime-Fit.

Ein Zugriff vor dem eingefrorenen Warmup-Start oder nach dem Evaluationsende blockiert ebenfalls.

### 3. Purge-Vertrag

`HorizonPolicy` erzwingt:

```text
purge_duration_minutes =
    max(max_label_horizon_minutes,
        max_holding_period_minutes + pending_entry_latency_minutes)
    + 1 Ausführungsminute
```

Beispiel:

```text
max_label_horizon = 120
max_holding_period = 180
pending_entry_latency = 2
execution_bar = 1
purge_duration = max(120, 182) + 1 = 183 Minuten
```

Eine spätere tatsächliche Label-, Holding- oder Pending-Dauer darf die eingefrorenen Maxima nicht überschreiten. Eine Verlängerung wäre eine neue Pipelinegeneration.

Die Task-8-Ausführungsengine erhält die eingefrorene `HorizonPolicy` als
Pflichtargument; `policy_sha256` bindet exakt dieselbe Werteidentität. Dadurch
kann ein Pending Entry nicht länger leben als die Latenz, die hier in Purge und
Pipelineidentität gebunden ist.

### 4. Informationsintervalle und Boundary-Touch

Jedes Trainingsevent besitzt:

- eindeutige Event-ID;
- Signalzeitpunkt;
- Informationsende nach Label-/Holding-/Pending-Horizont plus Ausführungsbar.

`purge_training_events` entfernt ein Trainingsevent, wenn:

```text
information_end_ms >= validation_or_test_start_ms
```

Damit wird auch ein Event entfernt, das die Grenze exakt berührt. Ein angebliches Trainingsevent, dessen Signal bereits an oder nach der Validation-/Testgrenze liegt, blockiert statt still sortiert zu werden.

### 5. Innere Folds starten vollständig flat

`begin_inner_fold` erzeugt ausschließlich:

```text
open_position = None
pending_entry = None
cooldown_until = None
scaler_state = None
runtime_model_state = None
```

`assert_inner_fold_starts_flat` blockiert jede Abweichung. Ein vorheriger Fold darf damit weder Position, Pending Entry, Cooldown, Scaler noch Runtime-Modellzustand vererben.

Der exakte Kalenderplan der sechs 60-Tage-Folds wird nicht vorgezogen und bleibt Aufgabe 14.

### 6. Konservatives Fold-Ende

`finalize_inner_fold` behandelt den endlichen Validation-Fold:

- Pending Entry wird verworfen;
- ohne offene Position endet der Fold flat;
- eine offene Position benötigt eine explizite letzte positive Volumenbar;
- Referenzpreis ist deren Close;
- Fill nutzt exakt Task 8: adverse Sell-Slippage und Tick-Rundung nach unten;
- Menge, Notional und Exit-Fee nutzen exakt Task 7;
- Exit-Menge bleibt exakt die gespeicherte Entry-Menge;
- Ergebnis wird als `terminal_liquidation=true`, Grund `fold_end`, ausgewiesen;
- der Folgezustand ist vollständig flat.

Nullvolumen-Terminalbar, falsche Execution-Rules-Identität oder anderes Kostenprofil blockieren fail-closed.

### 7. Vollständiger Open-Position-State

`OpenPositionState` enthält mindestens:

- `candidate_bundle_sha256`;
- exakte Menge;
- Entry-Preis;
- bereits angefallene Entry-Fees;
- Stop;
- Target;
- Trailing-State und gegebenenfalls Trailing-Stop;
- Break-even-Status;
- High-Watermark;
- Time-Stop-Deadline;
- Execution-Rules-SHA-256;
- Kostenprofil.

Semantisch geprüft werden unter anderem positive Werte, Stop unter Target, LONG-High-Watermark nicht unter Entry, kanonischer Trailing-State und kanonisches Kostenprofil.

### 8. Outer-Rotation-State

`build_outer_rotation_state` bindet pro Origin:

- Origin-Index;
- alte/retiring Bundle-Identität;
- gegebenenfalls exakt eine offene Position;
- neue Bundle-Identität;
- Anchor;
- `valid_from`;
- `valid_until`;
- `flat_time`;
- `entry_enabled_at`;
- Modus der alten und neuen Konfiguration;
- sichtbare Nachweise, ob Pending/Cooldown/Scaler/Runtime-Modellzustand verworfen wurden.

Die erste Origin startet zwingend vollständig flat. Jeder mitgebrachte Zustand bei Origin 1 blockiert.

### 9. Nur offene Position wird übertragen

Zwischen späteren Origins darf nur `open_position` bestehen bleiben.

Explizit nicht übertragen werden:

- Pending Entry;
- Cooldown;
- Scaler-State;
- Runtime-Modellzustand.

Die offene Position behält ihre ursprüngliche `candidate_bundle_sha256`. Diese alte Konfiguration wird auf `exit_only` gesetzt und kann keinen neuen Entry erzeugen.

Es gibt strukturell höchstens eine offene Position.

### 10. Neue Konfiguration wartet auf valid_from und flat_time

Solange eine alte Position offen ist:

```text
retiring_configuration_mode = exit_only
new_configuration_mode = waiting_for_flat_and_valid_from
entry_enabled_at = None
```

Nach Schließen der Altposition gilt:

```text
entry_enabled_at = max(valid_from, flat_time)
```

Drei Fälle sind getestet:

1. Altposition schließt vor `valid_from` → neue Konfiguration wartet bis `valid_from`.
2. Altposition schließt nach `valid_from` → neue Konfiguration wartet bis zum tatsächlichen `flat_time`.
3. Altposition schließt erst bei `valid_until` → wartende Konfiguration verfällt als `NO_TRADE_EXPIRED` und wird nicht rückwirkend aktiviert.

### 11. Keine künstliche Monatsgrenzen-Liquidation

Jeder Rotation-State erzwingt:

```text
monthly_boundary_liquidation = false
```

Eine offene Altposition darf regulär mit ihrer alten Exitlogik in die nächste Origin hineinreichen. `carry_state_for_next_origin` übernimmt nur diese Position und entfernt alle anderen Runtime-Zustände.

### 12. Terminale Prozessliquidation

`finalize_outer_process` liquidiert nur am Ende des gesamten endlichen 365-Tage-Prozesses:

- `origin_index` muss exakt 12 sein;
- offene Position erforderlich;
- Terminalbar muss exakt bei `valid_until` enden;
- positive Volumenbar erforderlich;
- Task-8-Sell-Fill;
- Task-7-Menge, Notional und Fee;
- Grund `process_end`;
- `terminal_liquidation=true`.

Ein falscher Terminalzeitpunkt blockiert. Monatsgrenzen verwenden diese Funktion ausdrücklich nicht.
Auch ein bereits flacher Zustand darf die Funktion erst für Origin 12 erreichen;
dort ist die Rückgabe `None` zustandsneutral. Bei offener Position muss die
übergebene 1m-Terminalbar zusätzlich exakt bei `valid_until` enden.

### 13. State-Identität

`OuterRotationState.basis()` erzeugt kanonisches JSON mit:

- allen Bundle- und Positionsfeldern;
- Anchor und Gültigkeitszeiten;
- Flat-/Entry-Freigabezeit;
- Modi;
- Discard-Nachweisen;
- Monatsliquidationssperre.

`state_sha256` ist deterministisch. Gleiche Zustände erzeugen denselben Digest; eine andere neue Bundle-Identität erzeugt einen anderen Digest.

Dies ist noch kein persistenter Resume-Store. Speicherung, Locking und transaktionales Resume bleiben Aufgabe 13 beziehungsweise die vollständige Rotation-Persistenz Aufgabe 24.

### 14. Pipeline- und Fingerprintbindung

`configs/protocol_v3_pipeline_contract.json` bindet jetzt Runtime-Vertrag und Implementierung sowohl an:

- `boundary_rules`;
- `simulator`.

Aktuelle Komponentenverträge:

```text
boundary_rules = protocol_v3_monthly_boundary_and_runtime_state_v1
simulator      = next_tradable_price_pessimistic_intrabar_with_fold_outer_state_v1
cost_model     = protocol_v3_actual_notional_baseline_and_stress_costs_v1
```

Der eigenständige Task-8-Vertrag `next_tradable_price_pessimistic_intrabar_v1` bleibt als Quelle unverändert gebunden. Das Kostenmodell wurde nicht geändert.

Jede Änderung an Warmup-, Purge-, Fold-End- oder Rotation-State-Regeln erzeugt eine neue Pipelinegeneration und damit über den Task-6-Fingerprint eine neue Run-Identität.

## Tests

Die Suite prüft mindestens:

- exakten Runtime-State-Vertrag und Safety-Locks;
- Purge-Formel;
- Boundary-Touch purgt;
- Eventsignal an/nach Grenze blockiert;
- Überschreitung eingefrorener Horizonte blockiert;
- Warmup nur für Feature-Reads;
- Flat-Fold-Start ohne Position, Pending, Cooldown, Scaler oder Runtime-Modellzustand;
- Pending-Cancel am Fold-Ende;
- konservative Fold-End-Liquidation;
- exakte Task-7-Exit-Menge;
- Task-8-Sell-Fill und Tick-Rundung;
- Nullvolumen-Terminalbar blockiert;
- erste Origin startet flat;
- spätere Origin übernimmt ausschließlich offene Position;
- alte Konfiguration exit-only;
- neue Konfiguration vor `valid_from` gesperrt;
- neue Konfiguration bis `flat_time` gesperrt;
- Verfall bei `valid_until` als `NO_TRADE_EXPIRED`;
- keine Monatsgrenzen-Liquidation;
- exakte Prozessend-Liquidation;
- Prozessend-Liquidation vor Origin 12 blockiert;
- widersprüchliche Rotation-Modi, Flat-/Freigabezeiten und offene
  Candidate-Identitäten blockieren;
- falscher Terminalzeitpunkt blockiert;
- Execution-Rules-Abweichung blockiert;
- deterministischer State-Digest;
- öffentliche Protocol-v3-Schnittstelle;
- Runtime-State in Boundary- und Simulator-Digest;
- Task-8-Intrabar-Vertrag bleibt separat gebunden.

## CI-Historie

1. Vor der ersten CI fand der interne Review einen verschachtelten Dataclass-Revalidierungsfehler. Die Rekonstruktion wurde auf eine echte Dataclass-Revalidierung korrigiert; keine Zustandsregel wurde gelockert.
2. Review-CI Run 397 auf dem vollständigen Runtime-State- und Golden-Teststand war vollständig grün.
3. Nach Pipelinebindung meldete Review-CI Run 398 genau einen veralteten Task-8-Test, der noch den Simulatornamen vor Task 9 erwartete. Implementation, Kompilierung, PowerShell und Whitespace waren grün.
4. Der Test wurde ausschließlich auf die neue zusammengesetzte Simulatoridentität aktualisiert und prüft zusätzlich, dass Task 8 weiterhin separat gebunden ist. Keine Runtime-, Fill- oder Kostenregel wurde geändert.
5. Review-CI Run 399 war vollständig grün.
6. Review-CI Run 400 nach öffentlichem Protocol-v3-Export war vollständig grün.
7. Review-CI Run 401 nach eigenem Task-9-Identitätstest war vollständig grün:
   - komplette Pytest-Suite;
   - Python-Kompilierung;
   - PowerShell-Syntax;
   - Whitespace-Prüfung;
   - finaler Pytest-Status.
8. Der finale Dokumentations-/Handoff-Head wird erneut durch dieselbe Review-CI geprüft.

## Aktueller ehrlicher Laufzustand

```text
Task-9-Implementierung = bereit und getestet
Task-8-Ausführung = erneut geprüft und unverändert
synthetische Warmup-/Purge-/Fold-/Outer-State-Tests = grün
realer Protocol-v3-Langlauf = weiterhin nicht ausführbar
```

Der reale Lauf bleibt blockiert, weil:

- kein realer Task-6-Exchange-Info-Snapshot versiegelt ist;
- der reale Task-5-Datensnapshot weiterhin `BLOCKED_MISSING_WARMUP` ist;
- Kontextparität, exakter Fold-Planer, Kandidatenauswahl und Outer-Orchestrierung erst in späteren Aufgaben entstehen.

Das ist keine Performance-, Zielerreichungs- oder Freigabebehauptung.

## Neue und geänderte Dateien

- `configs/protocol_v3_runtime_state_contract.json`
- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/runtime_state.py`
- `src/ethusdc_bot/protocol_v3/__init__.py`
- `tests/unit/test_protocol_v3_runtime_state.py`
- `tests/unit/test_protocol_v3_runtime_state_binding.py`
- `tests/unit/test_protocol_v3_intrabar_execution_binding.py`
- `handoff/PROTOCOL_V3_TASK_09_2026-07-14.md`
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` – wird im Abschlussstand auf 9/33 aktualisiert

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 10 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- keine vollständige Drei-Markt-Kontextparität;
- keine Stale-/Missing-Kontextentscheidung;
- keine neue Context-Watermark;
- kein exakter 6×60-Tage-Fold-Planer aus Aufgabe 14;
- keine reine Kandidatenauswahl aus Aufgabe 15;
- keine PBO-/DSR-Arbeit;
- kein Multi-Timeframe-Feature-Store;
- keine Router-/Spezialistenlogik;
- keine zwölf-Origin-Orchestrierung;
- keine persistente Rotation oder transaktionales Resume;
- keine Reports, UI oder Challenger-Aktivierung;
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
- finaler Holdout.

BTCUSDC und ETHBTC bleiben reine Kontextmärkte und können nie handeln.

## Codex-Startanweisung für Aufgabe 10

1. Branch `codex/research-resume-and-ui-state-v1` auf den finalen PR-Head ziehen.
2. `git status` muss sauber sein und lokaler `HEAD` muss GitHub entsprechen.
3. Dieses Handoff, Dokument 41, Task-5-Datensnapshot, Task-8-Intrabar-Vertrag und Task-9-Runtime-State vollständig lesen.
4. Vorhandene Context-Features, Context-Research, AlignedMarketCandles und Drei-Markt-Snapshotfunktionen inventarisieren und wiederverwenden.
5. Danach ausschließlich Aufgabe 10 umsetzen.
6. Zeitpunkt `t` darf nur verarbeitet werden, wenn ETHUSDC, BTCUSDC und ETHBTC denselben vollständig geschlossenen Informationsstand besitzen.
7. Fehlende, versetzte oder stale Kontextdaten müssen fail-closed blockieren.
8. BTCUSDC und ETHBTC bleiben reine Veto-/Bestätigungsmärkte und dürfen nie handeln.
9. Research, Replay, Finalpfad und Challenger müssen dieselbe Context-Entscheidung verwenden.
10. Keine Report-, Cache-, Fold-Planer-, Router-, Feature-Store- oder UI-Arbeit vorziehen.

## Exakt nächstes Ticket

`Aufgabe 10 – Kontextparität und Drei-Markt-Watermark`
