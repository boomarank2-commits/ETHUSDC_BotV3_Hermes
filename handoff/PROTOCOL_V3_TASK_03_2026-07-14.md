# Protocol v3 – Handoff Aufgabe 3/33

Stand: 2026-07-14

## Status

`Protocol v3: Aufgabe 3/33 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren – DONE_100`

Gesamtfortschritt nach Statusupdate: `3/33 = 9,09 %`

Exakt nächste Aufgabe: `Aufgabe 4 – Permanentes Trial-Ledger und historischen Import bauen`.

Codex darf Aufgabe 4 erst beginnen, nachdem der Branch lokal auf den aktuellen PR-Head gezogen und ein sauberer Arbeitsbaum bestätigt wurde.

## Vorherige Aufgabe kontrolliert

Vor Beginn wurde Aufgabe 2 vollständig kontrolliert:

- PR #17 war offen, mergebar, Draft und nicht gemerged.
- Kontrollierter Ausgangs-Head: `b1da61bb1ff657636d0e662ad07d9b1a8495689e`.
- Review-CI Run 335 war vollständig grün.
- Boundary-Fixtures lieferten weiterhin 12 Origins, 730 Trainingstage je Origin und 365 eindeutige OOS-Tage.
- Die Protocol-v2-Datei `src/ethusdc_bot/backtest/split.py` blieb unverändert und getrennt.

## Was umgesetzt wurde

### 1. Versionierter Pipelinevertrag

Neue Datei `configs/protocol_v3_pipeline_contract.json` friert ein:

- Protocol-Version `3.0.0`;
- Pipelinevertrag `monthly_refit_pipeline_v3.0.0`;
- Feature-, Familien-, Kontext-, Kosten-, Gate-, Ranking-, Suchraum-, Simulator- und Boundary-Verträge;
- die tatsächlich gebundenen Repository-Dateien;
- 12/8/40/12/3/2-Budgets und globale Maxima;
- Stagnations-, Seed-, Ledger-, Ziel- und Safety-Policy.

### 2. Content-addressed Pipelinegeneration

Neue Datei `src/ethusdc_bot/protocol_v3/pipeline.py`:

- liest den Vertrag fail-closed;
- hasht jede gebundene Datei mit SHA-256;
- bildet je Komponente einen kanonischen Digest;
- bindet Vertragsinhalt, Quelldigests, Budgets, Stopregeln, Seeds, Ledgerpolicy, Zielpolicy und Safety;
- erzeugt eine unveränderliche Generation `protocol_v3_pipeline_sha256:<64 hex>`;
- bindet auch den Code der Identitäts-/Seed-/Budgetlogik selbst über `src/ethusdc_bot/protocol_v3/pipeline.py`.

Damit erzeugt jede relevante Änderung an Features, Familien, Suchraum, Ranking, Gates, Kosten, Simulator, Kontext, Boundary oder Pipelineidentität automatisch eine neue Generation.

### 3. Kanonisches Pre-Run-Manifest und Seeds

Das Pre-Run-Manifest:

- enthält keine Wall-Clock-Zeit und kein `created_at`;
- bindet vollständigen Git-Commit, Pipelinegeneration und den exakten Task-2-Boundary-Plan;
- bindet Budget-, Stop-, Ziel-, Seed- und Safety-Policy;
- besitzt einen eigenen SHA-256-Digest;
- wird vor jeder Seedableitung vollständig revalidiert.

Seeds:

- Algorithmus `sha256_canonical_pre_run_manifest_namespace_v1`;
- unsigned 64 Bit;
- deterministisch je Origin, Cycle und Stage;
- gleiche Manifest-/Namespace-Kombination ergibt denselben Seed;
- andere Origin, anderer Cycle oder andere Stage ergeben getrennte Seeds;
- Systemzufall und Zeitstempel sind verboten.

### 4. Budgets technisch erzwungen

Kanonische Limits:

| Ebene | Maximum |
|---|---:|
| Outer Origins | 12 |
| Cycles je Origin | 8 |
| generiert je Cycle | 40 |
| getestet je Cycle | 12 |
| Walk-forward je Cycle | 3 |
| Finalisten je Cycle | 2 |
| globale Cycles | 96 |
| global generiert | 3.840 |
| global getestet | 1.152 |
| global Walk-forward | 288 |
| global Finalisten | 192 |

`BudgetUsage` reserviert immutable immer einen vollständigen Cycle. Ein neunter Cycle einer Origin, ein 97. Cycle global, gefälschte Reservierungen, nicht monotone Stufen oder Überschreitungen blockieren fail-closed.

Tatsächliche Ergebnisse dürfen unter den Caps liegen, müssen aber `finalists <= walk_forward <= tested <= generated` erfüllen.

### 5. Stopregeln

- `selection_stagnation_3_cycles` ist unveränderlich.
- Stagnation darf ausschließlich verkürzen.
- Sie verändert weder per-Origin- noch globale Budgets.
- Das 3-USDC-Ziel ist keine Loss-Funktion und darf den Suchlauf nicht beim ersten Treffer stoppen.
- Der achte Cycle bleibt die harte Obergrenze; ein neunter kann nicht reserviert werden.

### 6. Generation und Ledgergrenzen

- neue Pipelinegeneration → eigener Forward-Ledger-Namespace;
- permanenter Trial-Counter-Namespace bleibt generationsübergreifend gleich;
- `new_generation_resets_forward_ledger=true`;
- `new_generation_resets_permanent_trial_counter=false`.

Dies implementiert noch kein Trial-Ledger. Die eigentliche append-only Speicherung ist ausschließlich Aufgabe 4.

## Geänderte und neue Dateien

- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/pipeline.py`
- `src/ethusdc_bot/protocol_v3/__init__.py`
- `tests/unit/test_protocol_v3_pipeline.py`
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` – wird im Abschlusscommit auf 3/33 aktualisiert
- `handoff/PROTOCOL_V3_TASK_03_2026-07-14.md`

## Tests und Review

Die Tests decken ab:

- Task-2-Boundary bleibt gültig;
- identische Quellen erzeugen identische Generation;
- Änderung einer gebundenen Quelldatei erzeugt eine neue Generation;
- fehlende Quelldatei blockiert;
- Budget-, Stop-, Target- oder Ledger-Lockerung blockiert;
- Pfadflucht und fehlende Komponente blockieren;
- vollständige 96-Cycle-Reservierung erreicht exakt die globalen Maxima;
- Cycle 97 beziehungsweise Cycle 9 einer Origin blockiert;
- gefälschte Budgetstände und falsche Stage-Reihenfolge blockieren;
- Stagnation ändert keine Budgets;
- Pre-Run-Manifest ist deterministisch und timestamp-frei;
- Commit-, Digest-, Boundary- und Zeitfeld-Manipulation blockiert;
- Seedwerte sind stabil, gescoped und 64 Bit;
- Manipulation von Generation oder Ledger-Namespace blockiert.

CI-Historie:

1. Erster Lauf fand ausschließlich einen zu groben Test, der das zulässige Policy-Feld `timestamps_forbidden=true` als Zeichenfolge missdeutete. Produktionslogik unverändert.
2. Test wurde auf rekursive verbotene Schlüssel umgestellt.
3. Abschlussreview band zusätzlich die Pipelineidentitätsdatei selbst in die Generation ein.
4. Finale Review-CI auf Implementierungscommit `b59f7c54ea491b6c221b36f03ae93f7919f86dac` vollständig grün:
   - komplette Pytest-Suite;
   - Python-Kompilierung;
   - PowerShell-Syntax;
   - Whitespace-Prüfung;
   - finaler Pytest-Status.

Ein Rohdaten- oder Backtestlauf war für diese reine Identitäts-/Budget-/Seed-Aufgabe nicht fachlich erforderlich und wurde nicht vorgezogen.

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 4 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- persistentes oder append-only Trial-Ledger;
- historische Trial-Rekonstruktion;
- DSR/PBO;
- Daten- oder Exchange-Info-Snapshot;
- Cache oder Resume für Protocol v3;
- Simulator-, Strategie-, Router-, Gate-, Shadow- oder UI-Änderung;
- Orders, Trading-API, API-Keys, Paper, Testtrade oder Live.

## Safety

Unverändert gesperrt:

- Orders;
- Trading-API;
- API-Keys und Kontodaten;
- Paper;
- Testtrade;
- Live;
- finaler Holdout.

## Codex-Startanweisung für Aufgabe 4

1. Branch `codex/research-resume-and-ui-state-v1` auf den aktuellen PR-Head ziehen.
2. `git status` muss sauber sein und lokaler `HEAD` muss GitHub entsprechen.
3. Dieses Handoff, Dokument 41, `configs/protocol_v3_pipeline_contract.json` und `src/ethusdc_bot/protocol_v3/pipeline.py` vollständig lesen.
4. Vorhandene Experiment-, Report-, Resume- und Registry-Funktionen inventarisieren und wiederverwenden.
5. Danach ausschließlich Aufgabe 4 umsetzen.
6. Der permanente Trial-Counter muss den hier eingefrorenen Namespace verwenden und darf bei Generationswechsel nicht zurückgesetzt werden.
7. Der Forward-Ledger-Namespace darf in Aufgabe 4 höchstens referenziert, aber nicht als Challenger-/Shadow-Feature vorgezogen werden.
8. Keine Daten-, Simulator-, PBO/DSR-, Router-, Shadow- oder UI-Arbeit vorziehen.

## Exakt nächstes Ticket

`Aufgabe 4 – Permanentes Trial-Ledger und historischen Import bauen`

Ziel ist eine append-only, generationsübergreifende Erfassung jedes dateninformierten Versuchs mit deterministischer Trial-ID, Kandidat, Parametern, Featurevariante, Seed, Versionsbindungen, Codehash und kausaler Tagesreihe. Cache-Hits bleiben als Wiederverwendung sichtbar, historische Rekonstruktion wird ehrlich als Untergrenze markiert und unvollständige Historie erzwingt `INSUFFICIENT_TRIAL_HISTORY` sowie `NO_TRADE`.
