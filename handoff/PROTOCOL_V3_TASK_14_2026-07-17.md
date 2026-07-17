# Protocol v3 – Handoff Aufgabe 14/33

Stand: 2026-07-17

## Status

`Protocol v3: Aufgabe 14/33 – Exakten inneren 6×60-Tage-Fold-Planer bauen – DONE_100`

Gesamtfortschritt nach finaler grüner CI: `14/33 = 42,42 %`.

Exakt nächste Aufgabe: `Aufgabe 15 – Reine innere Auswahlfunktion extrahieren`.

Aufgabe 15 wurde nicht begonnen.

## Ausgangsstand und vorgeschaltete Prüfung von Aufgabe 13

Verbindlicher Ausgangs-Head:

`a4a48c226da4992575f9dd01bfc8d993859ec629`

PR #17 war offen, Draft und ungemerged.

Vor Aufgabe 14 wurde Aufgabe 13 adversarial geprüft. Kontrolliert wurden insbesondere:

- vollständige 16-Slot-Identitätsbindung;
- Resume ausschließlich vom committed `HEAD.json`;
- Unsichtbarkeit verwaister Temp- und Checkpointdateien;
- vollständige Checkpoint-Kette bis Genesis;
- transitive Task-12-Revalidierung;
- create-only Writer-Locks und Same-Host-Dead-Process-Recovery;
- idempotentes Cache-Reuse im permanenten Task-4-Trial-Ledger;
- Verhalten nach einem Crash zwischen Ledger-Append und Checkpoint-HEAD;
- keine vorgezogene Fold-, Auswahl- oder Outer-Orchestrierungslogik.

## Separate Task-13-Korrektur

Gefunden wurde ein realer Integrationsfehler: Das permanente Task-4-Ledger speichert `event_sha256`, während der produktive Task-13-Adapter weiterhin auf `event_hash` des Ledger-Events zugriff.

Zusätzlich musste die Receipt-Prüfung sicher blockieren, wenn nach dem einzigen idempotenten Cache-Reuse-Ereignis ein fremdes weiteres Ledger-Ereignis angehängt wurde.

Korrekturcommits:

- `1acdeeabf65b46944785160e67c35bded5dd1121` – produktiver Ledger-Adapter;
- `7c3d3b9d3d0d62adc2ae4f369526a803ba47e710` – Regressionstest;
- `01d989c424fcdd866671cf7d6f3f3b7dbc7a8363` – separater Korrekturbericht.

Korrekturbericht:

`handoff/PROTOCOL_V3_TASK_13_LEDGER_EVENT_ADAPTER_CORRECTION_2026-07-17.md`

Review CI Run 443 und Run 444 waren vollständig grün. Erst danach begann Aufgabe 14.

## Implementierte Dateien

Produktionsdateien:

- `configs/protocol_v3_inner_fold_contract.json`;
- `configs/protocol_v3_transaction_contract.json`;
- `configs/protocol_v3_pipeline_contract.json`;
- `src/ethusdc_bot/protocol_v3/inner_folds.py`;
- `src/ethusdc_bot/protocol_v3/inner_folds_api.py`;
- `src/ethusdc_bot/protocol_v3/transactional_cache_model.py`.

Tests und Fixtures:

- `tests/unit/test_protocol_v3_inner_folds.py`;
- `tests/unit/test_protocol_v3_fold_horizon_identity.py`;
- `tests/unit/protocol_v3_task13_support.py`;
- `tests/unit/test_protocol_v3_runtime_state_binding.py`.

Dokumentation:

- `handoff/PROTOCOL_V3_TASK_14_2026-07-17.md`;
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`.

## Versionierter Fold-Vertrag

Eingefroren wurden:

- Vertrag: `protocol_v3_exact_inner_6x60_day_folds_v1`;
- Vertragsschema: `protocol_v3_inner_fold_contract_v1`;
- Planschema: `protocol_v3_inner_fold_plan_v1`;
- Fold-Identität: `protocol_v3_inner_fold_identity_v1`.

Der Plan ist kanonisches JSON und SHA-256-gebunden. Unbekannte Felder, Duplicate Keys, nicht endliche Werte, nichtkanonische Intervalle oder ein neu gehashter, aber semantisch veränderter Plan blockieren.

## Exakter 6×60-Tage-Plan

Für jedes exakt 730 Tage große Entwicklungsfenster entstehen sechs strikt chronologische, nicht überlappende und lückenlos aneinandergrenzende 60-Tage-Validation-Folds auf den letzten 360 Entwicklungstagen.

Für den nullbasierten Foldindex `k = 0..5` gilt exakt:

```text
validation_start_k = training_end - (6-k) * 60 Tage
validation_end_k   = training_end - (5-k) * 60 Tage
fit_start_k        = training_start
fit_end_k          = validation_start_k - purge_duration
```

Die Fit-Spannen vor Purging betragen exakt:

```text
370, 430, 490, 550, 610, 670 Tage
```

Alle Intervalle sind UTC und halboffen. `training_start` und `training_end` müssen UTC-Mitternacht sein. Ein Entwicklungsfenster mit 729 oder 731 Tagen blockiert.

## Task-2-Boundary-Parität

Der Planer besitzt einen direkten Adapter für `MonthlyOriginBoundary` und verlangt:

- exakt 730 Entwicklungstage;
- `training_end_exclusive == test_start_inclusive`;
- sechs Folds mit identischer Struktur an jeder Origin.

Getestet wurden alle zwölf Origins für die Boundary-Fixtures mit Prozessenden:

- `2024-03-08`;
- `2025-03-08`;
- `2026-07-08`.

Damit wurden 36 reale Task-2-Origin-Fenster gegen dieselben Fold-Invarianten geprüft.

## Purging

Die Purge-Dauer wird ausschließlich aus der bestehenden Task-9-`HorizonPolicy` abgeleitet:

```text
max(max_label_horizon_minutes,
    max_holding_period_minutes + pending_entry_latency_minutes)
+ execution_bar_minutes
```

Der Planer verwendet die vorhandene Task-9-Funktion `purge_training_events(...)` und ergänzt den fest eingefrorenen maximalen Purge-Cutoff:

- ein Informationsintervall, das die Validation-Grenze berührt oder überschreitet, wird entfernt;
- ein Signal an oder nach `validation_start` ist als Trainingsevent unzulässig;
- auch ein kurz endendes Event mit Signalzeit `>= fit_end` wird entfernt;
- nur Events mit Signalzeit `< fit_end` und Informationsende `< validation_start` dürfen im Fit verbleiben.

Damit hängt die tatsächliche Fitmenge nicht optimistisch vom zufällig kürzeren realisierten Horizont einzelner Events ab.

## Timestamp-Spies

`FoldTimestampSpy` blockiert fail-closed:

- Fit-Zugriffe außerhalb `[fit_start, fit_end)`;
- Scaler-, Quantile-, Regime- oder Feature-Selection-Fits an oder nach `fit_end`;
- Validation-Signal, Label, PnL oder Execution außerhalb des jeweiligen 60-Tage-Folds;
- Featurequellen, deren Zeitstempel nach dem zugehörigen Entscheidungszeitpunkt liegt;
- Warmup-Zugriffe für andere Zwecke als kausales Feature-Reading vor `fit_start`;
- Validation-Informationsintervalle, die `validation_end` berühren oder überschreiten.

Die Spies sind reine Zugriffswächter. Sie implementieren keine Auswahl-, PnL- oder Handelslogik.

## Fold-Runtime-Parität

Der neue Planer ersetzt nicht die bereits vorhandene Task-9-State-Maschine.

Unverändert gelten:

- jeder innere Fold startet `flat`;
- keine Pending Entry, kein Cooldown, kein Scaler-State und kein Runtime-Model-State werden übernommen;
- eine Restposition wird am Fold-Ende über die bestehende Task-9-/Task-8-/Task-7-Kette konservativ finalisiert.

Aufgabe 14 definiert ausschließlich, wo Fit, Purge und Validation zeitlich liegen.

## Transaktions-, Cache- und Resume-Bindung

Der temporäre Fold-Zustand `NOT_APPLICABLE/task14_not_implemented` ist nicht mehr zulässig.

Der Fold-Slot der Transaktionsidentität muss jetzt:

- Zustand `BOUND` besitzen;
- Schema `protocol_v3_inner_fold_identity_v1` verwenden;
- den vollständigen kanonischen Plan enthalten;
- dessen Digest und Plan-ID revalidieren;
- semantisch exakt den sechs Fold-Formeln entsprechen.

Dafür wurde der Task-13-Vertrag versioniert fortgeschrieben zu:

- Vertragsschema: `protocol_v3_transaction_contract_v2`;
- Vertrag: `protocol_v3_content_addressed_cache_and_transactional_resume_with_inner_folds_v2`;
- Transaktionsidentität: `protocol_v3_transaction_identity_v2`.

Die Anzahl und Reihenfolge der 16 Pflichtslots bleibt unverändert. Kandidat bleibt bis Aufgabe 15 typisiert `NOT_APPLICABLE`; Rotation bleibt `GENESIS`.

## Horizon-Cross-Binding

Eine zusätzliche adversariale Prüfung fand eine mögliche Inkonsistenz: Ein intern gültiger Fold-Plan hätte mit einer anderen Task-9-HorizonPolicy als der separaten Transaktions-Horizon-Identität gebaut werden können.

Dies wurde geschlossen. Der eingebettete Planhorizont muss jetzt exakt der separaten Horizon-Identität entsprechen, einschließlich:

- maximalem Label-Horizont;
- maximaler Haltedauer;
- Pending-Entry-Latenz;
- Ausführungsbar;
- Policy-Digest;
- daraus berechneter Purge-Dauer.

Ein gültiger Plan mit einem abweichenden Horizont blockiert am Transaktionsrand.

## Pipelinegeneration und alte Cache-Stände

Der Fold-Vertrag sowie Planermodul und öffentliche API sind in die Pipelinekomponente `boundary_rules` aufgenommen.

Die Boundary-Komponentenversion lautet jetzt:

`protocol_v3_monthly_boundary_runtime_and_inner_6x60_folds_v2`

Der fortgeschriebene Transaktionsvertrag ist ebenfalls pipelinegebunden.

Dadurch ändern sich Pipelinegeneration, Run-Fingerprint und Transaktionsidentität. Alte Task-13-Checkpoints oder Cache-Records ohne gebundenen Fold-Plan können nicht als Treffer für Task 14 gelten.

## Tests und CI

Neue Task-14-Testfälle: 10.

Abgedeckt sind:

- exakter Vertrag und stabile öffentliche API;
- vollständige Pipelinebindung;
- sechs 60-Tage-Folds und 360-Tage-Union;
- Fit-Spannen 370/430/490/550/610/670;
- alle 36 Task-2-Origin-Fixtures;
- falsche Fensterlänge, Nicht-Mitternacht und semantisch manipulierte Pläne;
- Task-9-Boundary-Touch-Purge;
- fester maximaler Purge-Cutoff;
- Fit-, Validation-, Feature- und Label-Timestamp-Spies;
- Ablehnung des alten Fold-`NOT_APPLICABLE`-Zustands;
- Ablehnung eines neu gehashten, aber semantisch veränderten Plans;
- Ablehnung eines gültigen Plans mit abweichender HorizonPolicy.

CI-Historie:

1. Review CI Run 452: zwei enge Testbefunde – ein früherer korrekter semantischer Fehlertext und ein veralteter Task-9-Erwartungswert für die Boundary-Komponentenversion. Produktionslogik, Kompilierung, PowerShell und Whitespace waren grün.
2. Review CI Run 454: vollständig grün.
3. Adversarialer Zusatzbefund: Fold-Plan und separate Horizon-Identität mussten gegenseitig gebunden werden.
4. Korrekturcommit: `dfd4e8681ba318b45e96c3abcea4f7b72e9088cb`.
5. Regressionstest-Commit: `010be590b68ec9b21721c1488848100501c37b02`.
6. Review CI Run 456: vollständig grün.
7. Vollständige Suite: 1.102 Tests erfolgreich.
8. Python-Kompilierung, PowerShell-Syntax, Whitespace und abschließendes Pytest-Gate: grün.

## Ehrlicher aktueller Zustand

```text
Task-13-Ledger-Adapterkorrektur = implementiert und CI-grün
Task-14-Vertrag und 6x60-Fold-Plan = implementiert
Task-14-Task2-/Task9-Parität = implementiert
Task-14-Timestamp-Spies = implementiert
Task-14-Transaktions-/Cache-/Resume-Bindung = implementiert
Task-14-Horizon-Cross-Binding = implementiert
Task-15-Auswahlfunktion = nicht implementiert
realer Protocol-v3-Langlauf = weiterhin nicht ausführbar
Performance-/3-USDC-/Final-/Live-Freigabe = nicht behauptet
Paper/Testtrade/Live/Orders/API-Keys = gesperrt
```

## Explizit nicht umgesetzt

Keine Aufgabe 15 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- keine reine Kandidatenauswahl;
- keine vollständige Kandidaten-Tagesmatrix;
- keine PBO-/DSR-Berechnung;
- kein Multi-Timeframe-Feature-Store;
- kein Opportunity-/Regimemodell;
- keine Spezialisten oder Router;
- kein FrozenCandidateBundle;
- keine Outer-Origin-Orchestrierung;
- keine Rotationspersistenz aus Aufgabe 24;
- kein tägliches MTM-Ledger;
- kein Challenger-Controller;
- kein Final-Evaluator;
- keine UI;
- keine Orders, Trading-API, API-Keys, Paper, Testtrade oder Live.

## Startanweisung für Aufgabe 15

Vor Aufgabe 15 muss Aufgabe 14 am dann aktuellen Code adversarial geprüft werden. Besonders zu kontrollieren sind:

- exakt sechs lückenlose 60-Tage-Folds auf den letzten 360 Entwicklungstagen;
- keine Abweichung von den Fit-Spannen 370 bis 670 Tage vor Purging;
- Planhorizont und Transaktions-Horizon-Identität bleiben identisch;
- fixed-max Purge und Task-9-Boundary-Touch bleiben gemeinsam aktiv;
- Timestamp-Spies blockieren jeden Zugriff nach der jeweiligen Grenze;
- alte `task14_not_implemented`-Identitäten bleiben unbrauchbar;
- keine vorgezogene Kandidatenmatrix, PBO, Router- oder Outer-Logik.

Erst nach eventueller separater Korrektur und grüner CI darf Aufgabe 15 beginnen.

## Exakt nächstes Ticket

`Aufgabe 15 – Reine innere Auswahlfunktion extrahieren`
