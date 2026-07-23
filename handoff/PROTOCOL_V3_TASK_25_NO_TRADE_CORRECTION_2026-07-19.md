# Protocol v3 – Aufgabe 25 NO_TRADE-Korrektur

Stand: 2026-07-19

## Befund

Die erste Task-25-Fassung validierte Trade-, Friction- und MTM-Arithmetik, band das Vorhandensein von Tradezeilen aber noch nicht ausdrücklich an die Task-22-Routbarkeit. Dadurch konnte ein synthetischer Test Tradezeilen unter einem als `NO_TRADE` und `research_simulation_routable=false` eingefrorenen Fixture-Bundle einspeisen.

## Korrektur

Ein Origin-Ledger mit Closed Trades wird nun fail-closed abgewiesen, wenn die gebundene Routerentscheidung `NO_TRADE` lautet oder das FrozenCandidateBundle nicht ausdrücklich `research_simulation_routable=true` ist. Damit können Fixture- und Cash-Bundles keine Fake-Trades, keinen Fake-PnL und keine scheinbar bestandene Zeitaggregation erzeugen.

Die eigentliche Trade-/Friction-Arithmetik bleibt für echte routbare Bundles unverändert vorhanden und wird separat getestet. Orders, Trading-API, Paper, Testtrade und Live bleiben gesperrt.
