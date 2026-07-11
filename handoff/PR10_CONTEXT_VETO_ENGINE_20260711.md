# PR #10 - Context veto engine v1

Stand: 2026-07-11

## Branch

- Branch: `review/context-veto-engine-v1`
- Base: `review/context-data-alignment-v1`
- Pull request: to be created after this handoff commit

## Implementierter Umfang

Eine neue pure `context_features`-Schicht berechnet trailing-only BTCUSDC- und
ETHBTC-Kontextmerkmale. Der bestehende ETHUSDC-Simulator akzeptiert optional ein
exakt ausgerichtetes `AlignedMarketCandles`-Objekt.

Nur `context_filter` nutzt diesen Kontext. Alle anderen Strategiefamilien
bleiben unverändert.

## Nicht verhandelbare Signalreihenfolge

- Zuerst muss eine bestehende ETHUSDC-Basisstrategie ein Signal liefern.
- Ohne Basissignal darf Kontext niemals einen Trade erzeugen.
- Fehlender Kontext blockiert fail-closed.
- Warmup blockiert fail-closed.
- BTCUSDC-Trend, BTCUSDC-Volatilität und ETHBTC-Relative-Stärke dürfen das
  Basissignal nur bestätigen oder verwerfen.
- Der hypothetische Handel bleibt ausschließlich ETHUSDC LONG.

## Neue Bausteine

- `ContextVetoPolicy`;
- `ContextDecision`;
- `evaluate_context_veto(...)`;
- `validate_context_against_trade_candles(...)`;
- optionaler Simulatorparameter `market_context`;
- zentrale `_entry_decision()` vor der bestehenden Pending-Entry-Logik.

Der direkte `_signal(context_filter)`-Zweig gibt immer `False` zurück. Ein
Kontextfilter kann die zentrale Prüfung daher nicht umgehen.

## Transparente Ablehnungsgründe

- `context_data_missing`;
- `context_warmup`;
- `context_veto_btc_trend`;
- `context_veto_btc_volatility`;
- `context_veto_ethbtc_relative_strength`;
- `context_recursive_base_forbidden`.

## Tests

Bereits ergänzt sind Tests für:

- Policy-Validierung und Unveränderlichkeit;
- Warmup;
- jeden Veto-Grund;
- erlaubte Kontextentscheidung;
- Zukunftsleckage durch nachträglich veränderte spätere Kontextkerzen;
- exakte ETHUSDC-/Kontext-Zeitachse;
- fehlenden Kontext im Simulator;
- bestätigte ETHUSDC-Basissignale;
- blockierten BTC-Abwärtstrend;
- Kontext kann ohne Basissignal keinen Trade erzeugen;
- rekursiven Kontext-Basisfehler;
- nicht ausgerichteten Kontext;
- identische Ergebnisse aller Nicht-Kontextstrategien mit und ohne Kontext;
- weiterhin verbotene Nicht-ETHUSDC-Symbole.

## Aktuelle Grenze

Search Frontier v2 bleibt in diesem PR weiterhin ohne aktive
`context_filter`-Kandidaten. Auch der Production-Research-Loop lädt noch keine
Kontextdaten. Damit ist die neue Engine zunächst isoliert, testbar und ohne
Auswirkung auf bestehende Research-Ergebnisse.

Ein späterer, getrennt getesteter PR muss:

- Kontextfenster gemeinsam mit ETHUSDC laden;
- Training/Validation/WFV identisch schneiden;
- Kontextkandidaten mit eigener Ressourcenrechnung reaktivieren;
- Reports um Kontext-Veto-Statistik und Provenienz ergänzen.

## Sicherheit

Keine Live-, Paper-, Testtrade-, Order-, Account-, Key-, Short-, Margin-,
Futures- oder Leverage-Funktion wurde aktiviert.
