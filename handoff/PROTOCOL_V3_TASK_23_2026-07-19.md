# Protocol v3 – Handoff Aufgabe 23/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 23/33 – Zwölf kausale äußere Monats-Origins – DONE_100`

Gesamtfortschritt: `23/33 = 69,70 %`.

Exakt nächste Aufgabe: `Aufgabe 24 – 24h-Aktivierung und Outer-Rotation-State`.

## Umsetzung

Der Vertrag `protocol_v3_twelve_causal_outer_origin_orchestrator_v1` führt die unveränderte Auswahlpipeline genau zwölfmal auf dem kanonischen Task-2-Boundaryplan aus. Jede Origin besitzt:

- exakt 730 vorherige UTC-Entwicklungstage;
- einen eigenen, chronologischen Fit-/Testanker;
- den semantisch validierten Task-14-Foldplan;
- einen internen Aufruf von `select_candidate(training_window, frozen_pipeline_config)`;
- einen Feature-Store- und Regime-Assessment-Cutoff exakt am Anker;
- genau eine Task-22-Routerentscheidung und ein vollständiges FrozenCandidateBundle;
- eine Bundle-Gültigkeit exakt für das folgende Deployment-Intervall.

Der Prozess bindet eine unveränderte Pipelinegeneration und denselben Code-Commit über alle Origins. Die OOS-Vereinigung wird als vollständiges gehashtes Tagesraster mit exakt 365 eindeutigen, lückenlosen Tagen gespeichert.

Der Orchestrator hat absichtlich keinen Eingabekanal für Outer-PnL, Rankings, Reports, Gate-Ergebnisse oder menschliche Ergebnisinterpretationen. Ein `OuterIsolationSpy` beweist gleichzeitig die erlaubte Ausnahme: Eine frühere reine Rohmarktbeobachtung darf in einer späteren Origin als kausale Historie gelesen werden, wenn sie innerhalb deren 730-Tage-Fenster liegt. Outer-Ergebnisse bleiben für spätere Fits unerreichbar.

## Tests und Sicherheitsgrenzen

Abgedeckt sind Vertrag/API/Pipelinebindung, exakt zwölf Neufits, 730-Tage-Fenster, 365-Tage-OOS-Vereinigung, Determinismus, chronologische Fit-Cutoffs, exakte Anchor-Cutoffs, erlaubte spätere Rohmarktgeschichte, gesperrte Outer-Ergebnisse, fehlende/regeordnete/falsch gebundene Requests sowie neu gehashte OOS- und Bundle-Manipulation.

Validierung:

- gezielte Task-2/14/15/22/23-Integrationssuite: erfolgreich;
- vollständige Suite: `1.174 Tests erfolgreich`;
- `py -3.12 -m compileall -q src`: erfolgreich;
- `git diff --check`: erfolgreich.

Task 23 erzeugt keine Orders und führt noch keine Outer-Trades oder PnL-Aggregation aus. Rotation und `flat_time` bleiben Aufgabe 24; tägliches MTM und zwei Zeitaggregationen bleiben Aufgabe 25. API-Keys, Trading-API, Paper, Testtrade und Live bleiben gesperrt.

## Exakt nächstes Ticket

`Aufgabe 24 – 24h-Aktivierung und Outer-Rotation-State`
