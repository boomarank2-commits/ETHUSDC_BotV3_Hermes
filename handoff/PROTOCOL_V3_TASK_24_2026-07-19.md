# Protocol v3 – Handoff Aufgabe 24/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 24/33 – 24h-Aktivierung und Outer-Rotation-State – DONE_100`

Gesamtfortschritt: `24/33 = 72,73 %`.

Exakt nächste Aufgabe: `Aufgabe 25 – Tägliches MTM-Ledger und zwei Zeitaggregationen`.

## Umsetzung

Der bestehende Task-9-`OuterRotationState` bleibt die einzige Runtime-Wahrheit. Task 24 ergänzt keine konkurrierende Zustandsmaschine, sondern macht diesen Zustand sicher persistierbar und bindet ihn an die bereits abgeschlossenen Prozessschichten:

- kanonische Rekonstruktion und erneute semantische Validierung des vollständigen Rotationszustands;
- exakte Bindung an Task-23-Prozesshash, Origin-Auswahl und Selection-Entscheidung;
- exakte Bindung an das Task-22-`FrozenCandidateBundle` der jeweiligen Origin;
- Aufnahme des vollständigen Zustands samt Zustandshash in den Task-13-Transaktionsslot;
- dadurch neue Transaction-/Cache-/Resume-Identity bei jedem relevanten Origin-, Bundle-, Selection- oder Zustandswechsel.

Die vorhandenen Regeln bleiben unverändert: erste Origin flat, Aktivierung exakt `T+24h`, danach zusätzlich Warten bis `flat_time`, maximal ein offenes Lot, Vorgänger ausschließlich `exit_only`, keine monatliche Zwangsliquidation und kein Carry von Pending Entry, Cooldown, Scaler oder Runtime-Modellzustand. Der kanonische Genesis-Slot bleibt ausschließlich für vorgelagerte Inner-Transaktionen zulässig.

## Tests und Sicherheitsgrenzen

Abgedeckt sind Task-22-/23-Bindung, exakte 24h-Aktivierung, kanonischer Restore, anderer Origin-/Bundle-Pfad, geänderte Transaktionsnamespace, nichtkanonische Persistenz sowie neu gehashte semantische Manipulation. Die vorhandenen Task-9-Tests decken zusätzlich Exit-only-Carry, Flat-Handoff, Ablauf zu `NO_TRADE`, Prozessend-Liquidation und widersprüchliche Zustände ab.

Validierung:

- gezielte Task-9/13/22/23/24-Integrationssuite: erfolgreich;
- vollständige Suite: `1.179 Tests erfolgreich`;
- `py -3.12 -m compileall -q src`: erfolgreich;
- Ruff für alle geänderten Python-Dateien: erfolgreich;
- `git diff --check`: erfolgreich.

Task 24 erzeugt keine Orders, Trades oder PnL. Tägliches MTM inklusive Nulltagen sowie Deployment- und UTC-Kalenderaggregation bleiben Aufgabe 25. API-Keys, Trading-API, Paper, Testtrade und Live bleiben gesperrt.

## Exakt nächstes Ticket

`Aufgabe 25 – Tägliches MTM-Ledger und zwei Zeitaggregationen`
