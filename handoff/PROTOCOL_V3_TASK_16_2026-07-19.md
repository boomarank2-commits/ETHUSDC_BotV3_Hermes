# Protocol v3 – Handoff Aufgabe 16/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 16/33 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets – DONE_100`

Gesamtfortschritt: `16/33 = 48,48 %`.

Exakt nächste Aufgabe: `Aufgabe 17 – PBO/CSCV exakt implementieren`.

## Ausgangsstand und vorgeschaltete Abnahme

- Branch: `codex/research-resume-and-ui-state-v1`;
- veröffentlichter Ausgangs-Head: `abafddbe418be36061e1f2d983a885bca3bc406a`;
- GitHub Review CI für den Ausgangs-Head: grün, Run `29684794097`, Job `88187111946`;
- Task 14: adversarial geprüft, 10 Fold-Tests grün;
- Task 15: adversarial geprüft, Selection-, Missing-Evidence- und Transaktionstests grün;
- zusätzlich korrigierter Befund vor Task 16: Windows erkannte einen beendeten Same-Host-PID bei Stale-Lock-Recovery nicht zuverlässig. Die native read-only Statusprüfung wurde minimal korrigiert, vollständig getestet, separat committed, gepusht und CI-grün abgenommen.

## Implementierung

Neuer öffentlicher Pfad:

`ethusdc_bot.protocol_v3.candidate_matrix_api`

Neue Produktions- und Vertragsdateien:

- `configs/protocol_v3_candidate_matrix_contract.json`;
- `src/ethusdc_bot/protocol_v3/candidate_matrix.py`;
- `src/ethusdc_bot/protocol_v3/candidate_matrix_api.py`.

Fortgeschriebene Bindungen:

- `configs/protocol_v3_pipeline_contract.json` bindet Vertrag, Modell und öffentliche API an die Ranking-Komponente;
- `configs/protocol_v3_inner_selection_contract.json` erlaubt ab Task 16 vollständige produktive Matrixevidenz, hält PBO und DSR aber fail-closed;
- `inner_selection.build_matrix_development_support(matrix, cycle_index=...)` bindet die Origin-Matrix an den ausgewählten Cycle und dessen vollständiges getestetes Inventar.

## Evidenzvertrag

Die Origin-Matrix erzwingt:

- exakt sechs Task-14-Folds zu je 60 Tagen;
- exakt 360 chronologische, lückenlose, gemeinsame UTC-Tage je getesteter Kandidateninstanz;
- tägliche Netto-MTM-Deltas nach Kosten;
- echte No-Trade-Tage als `0.0`;
- fehlende Tage niemals als Null;
- vollständige Aufbewahrung aller getesteten Profile aller Cycles;
- verschachtelte Budgets `tested <= 12`, `promoted <= 3`, `finalists <= 2`;
- keine künstliche Auffüllung kleiner oder leerer legitimer Inventare;
- kanonische Digests für Profile, Folds, Tagesreihen, Tagesraster, Cycles und Matrix;
- exakte Übereinstimmung jeder Reihe mit dem permanenten Trial-Ledger;
- sichtbaren Cache-Reuse pro Origin/Cycle ohne neuen unabhängigen Trial;
- keine Outer-Ergebnisse.

Fold-Equity wird nicht als absolute, je Fold zurückgesetzte Reihe addiert. Der Vertrag akzeptiert ausschließlich tägliche Netto-MTM-Deltas und verkettet diese einmalig; der Regressionstest mit sechs Fold-Anfangsdeltas belegt die Summe ohne doppelte Reset-Zählung.

## Tests

Neue Task-16-Tests: 13.

Abgedeckt sind:

- kanonischer Vertrag, öffentliche API und Pipelinebindung;
- 360 gemeinsame Tage und 354 explizite Nulltage im Reset-Delta-Fixture;
- alle getesteten Profile über mehrere Cycles;
- deterministische Matrix- und Identitätsdigests;
- kleine und leere legitime Testinventare ohne Auffüllung;
- Obergrenze von zwölf getesteten Profilen;
- 359/361 Tage, Duplikate, Reihenfolgefehler und nichtfinite Werte;
- fehlende Profile für deklarierte getestete IDs;
- permanente Trial-Ledger-Bindung;
- sichtbarer Cache-Reuse ohne zusätzlichen Trial;
- produktive Matrixevidenz bei weiterhin typisiertem `NO_TRADE` für fehlendes PBO/DSR;
- manipulierte, neu gehashte Inhalte und Outer-Felder.

Validierung:

- gezielte Task-14–16-, Pipeline- und Transaktionssuite: grün;
- vollständige Suite: `1.131 Tests erfolgreich`;
- `py -3.12 -m compileall -q src`: erfolgreich;
- frische öffentliche API-Imports: erfolgreich;
- `git diff --check`: erfolgreich.

## Unveränderte Sicherheitsgrenzen

- keine Orders, Trading-API oder API-Keys;
- kein Paper-, Testtrade- oder Live-Pfad;
- keine Gate-Lockerung und keine Optimierung auf 3 USDC/Tag;
- keine Outer-PnL, Rankings oder Holdout-Ergebnisse;
- kein PBO/CSCV, kein DSR, keine Task-19-/20-Features oder Regime;
- Candidate- und Fold-Slot bleiben `BOUND`;
- Transaktionsvertrag bleibt Version 3.

## Exakt nächstes Ticket

`Aufgabe 17 – PBO/CSCV exakt implementieren`
