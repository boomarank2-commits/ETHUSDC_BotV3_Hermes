# Protocol v3 – Handoff Aufgabe 25/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 25/33 – Tägliches MTM-Ledger und zwei Zeitaggregationen – DONE_100`

Gesamtfortschritt: `25/33 = 75,76 %`.

Exakt nächste Aufgabe: `Aufgabe 26 – Monthly Quality Gate, Stress und Pflichtmetriken`.

## Umsetzung

Der neue Vertrag `protocol_v3_daily_mtm_and_separate_time_aggregations_v1` konsumiert ausschließlich den kanonischen Task-2-Boundaryplan, den Task-23-Outer-Prozess und die zugehörigen Task-24-Rotationszustände. Er erzeugt eine einzige, content-gehashte Prozesswahrheit mit:

- exakt zwölf geordneten Deployment-Ledgern;
- exakt 365 eindeutigen und lückenlosen UTC-Tageswerten einschließlich echter Nulltage;
- fortlaufender Closing-Equity ohne Reset an Origin-Grenzen;
- zwölf Deployment-Aggregaten;
- allen 13 berührten UTC-Kalendermonaten und allen fünf berührten UTC-Kalenderquartalen;
- getrennten, nach UTC-Exit-Zeitpunkt zugeordneten Closed-Trade-Diagnosen;
- konkreten Fee-/Slippage-Ereignissen am tatsächlichen Ausführungstag.

MTM-Gesamt-PnL ist die primäre PnL-Wahrheit. Closed-Trade-Netto wird nicht addiert, sondern ausschließlich separat ausgewiesen und muss am konservativ flach abgeschlossenen Prozessende exakt mit dem MTM-Gesamtwert übereinstimmen. So kann eine grenzüberschreitende Position weder an einer Origin-Grenze realisiert noch doppelt gezählt werden.

Ein Trade mit Entry vor der aktuellen Origin ist nur zulässig, wenn er dem tatsächlich getragenen Task-24-Exit-only-Lot entspricht. Terminal-Liquidation ist nur auf dem letzten Prozesstag erlaubt. Origin-, Selection-, Bundle- und Rotation-Hashes bleiben Bestandteil jeder Origin-Zeile.

## Tests und Sicherheitsgrenzen

Abgedeckt sind Vertrag/API/Pipelinebindung, 365 Nulltage, 12 Deployment-Intervalle, 13 Monate, fünf Quartale, getrennte MTM-/Trade-PnL, Exit-Zeit-Zuordnung, Fee-/Slippage-Abstimmung, fehlender Nulltag, gebrochenes Equity-Delta, falsche Rotation/Bundle-Bindung, falsche Exit-Origin und versteckte MTM-/Trade-Abweichung.

Validierung:

- gezielte Task-12/23/24/25-Integrationssuite: erfolgreich;
- vollständige Suite: `1.185 Tests erfolgreich`;
- `py -3.12 -m compileall -q src`: erfolgreich;
- Ruff für die neuen Implementierungs- und Testdateien: erfolgreich;
- `git diff --check`: erfolgreich.

Task 25 wertet noch keine Quality Gates oder Stressvarianten aus und verändert keine Schwellen. API-Keys, Trading-API, Orders, Paper, Testtrade und Live bleiben gesperrt.

## Exakt nächstes Ticket

`Aufgabe 26 – Monthly Quality Gate, Stress und Pflichtmetriken`
