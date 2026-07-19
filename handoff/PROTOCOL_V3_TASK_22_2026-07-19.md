# Protocol v3 – Handoff Aufgabe 22/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 22/33 – Deterministischer NO_TRADE-Router und FrozenCandidateBundle – DONE_100`

Gesamtfortschritt: `22/33 = 66,67 %`.

Exakt nächste Aufgabe: `Aufgabe 23 – Zwölf äußere Monats-Origins orchestrieren`.

## Umsetzung

Der Vertrag `protocol_v3_deterministic_no_trade_router_and_frozen_candidate_bundle_v1` verbindet die vorhandenen Task-15–21-Evidenzen ohne zweite Simulationsengine. `NO_TRADE` bleibt der Default. Eine `SPECIALIST`-Entscheidung benötigt gleichzeitig:

- einen von Task 15 vollständig gewählten Kandidaten;
- ein exakt gegen Store, Kontext, Feature-Fit-State und Regime-Fit-State wiedergespieltes Task-20-Assessment;
- die eindeutige Task-21-Zuordnung zwischen Kandidatenfamilie und Spezialist;
- ein bestandenes Local-Edge-Replay für exakt dieselbe Struktur.

Das Local-Edge-Replay besitzt sechs vollständige 60-Tage-Folds und damit 360 specialist-gefilterte Netto-MTM-Tageszeilen. Fehlende oder verschobene Tage, falsche Fold-IDs, nichtfinite Werte, widersprüchliche Netto-/Bruttowerte, weniger als 20 Trades, Profit-Factor unter 1,05 oder ein nichtpositiver Fold führen fail-closed. Der Replay-Hash wird aus Auswahl, Spezialist und sämtlichen Tageszeilen berechnet; ein behaupteter Hash wird nicht übernommen.

Das `FrozenCandidateBundle` bindet Routerentscheidung, Spezialistenbundle, skalare Parameter, Task-19-Scaler/Quantile und Feature-Identität, Task-20-Schwellen, Kontextpolicy, Kostenmodell, Auswahl-/Local-Edge-Evidenz, Vorgänger, Rotationspolicy und UTC-Gültigkeit. `valid_from` ist exakt `as_of+24h`. Maximal ein Lot, Exit-only-Vorgänger und Flat-Handoff sind eingefroren; der konkrete versionierte Runtime-Rotation-State bleibt Aufgabe 24.

## Tests und Sicherheitsgrenzen

Abgedeckt sind kanonischer Vertrag/API/Pipelinebindung, erfolgreicher eindeutiger Spezialistenpfad, fehlende und nicht bestandene Local-Edge-Evidenz, falsche Familien, manipulierte Tagesraster und neu gehashte Ergebnismanipulation, vollständige Bundle-Rekonstruktion, Kontext-/Kosten-/Fit-State-Bindung, 24h-Gültigkeit, Ein-Lot-Grenze und Fixture-Sperre.

Validierung:

- gezielte Task-15–22-Integrationssuite: erfolgreich;
- vollständige Suite: `1.169 Tests erfolgreich`;
- `py -3.12 -m compileall -q src`: erfolgreich;
- `git diff --check`: erfolgreich.

Synthetische Fixtures können kein routbares Bundle erzeugen. Jede Routerentscheidung enthält `transaction_eligible=false`. Adoption, Orders, Trading-API, API-Keys, Paper, Testtrade und Live bleiben gesperrt.

## Exakt nächstes Ticket

`Aufgabe 23 – Zwölf äußere Monats-Origins orchestrieren`
