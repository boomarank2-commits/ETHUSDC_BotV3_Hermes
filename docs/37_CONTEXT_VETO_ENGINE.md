# 37 - Trailing-only context veto engine

Stand: 2026-07-11

## Zweck

Der Kontextpfad darf ausschließlich ein bereits vorhandenes ETHUSDC-
Basissignal bestätigen oder ablehnen. BTCUSDC und ETHBTC erzeugen niemals selbst
einen Einstieg und besitzen keine Handels- oder Orderrolle.

## Datenvertrag

Die Engine akzeptiert ausschließlich `AlignedMarketCandles` aus dem strikten
Kontextdaten-Layer:

- ETHUSDC, BTCUSDC und ETHBTC haben dieselbe Kerzenanzahl;
- alle UTC-Open-Timestamps stimmen exakt überein;
- keine Lücke, Interpolation oder erfundene Kerze ist erlaubt.

Der Simulator prüft die Identität seiner ETHUSDC-Zeitachse mit dem übergebenen
Kontext erneut, bevor eine Kontextstrategie ausgewertet wird.

## Entscheidungsreihenfolge

Für `context_filter` gilt:

1. Die vorhandene ETHUSDC-Basisstrategie muss am aktuellen geschlossenen
   Kerzenindex ein Signal liefern.
2. Ohne Basissignal wird kein Kontext geprüft und kein Trade erzeugt.
3. Fehlende Kontextdaten blockieren das Basissignal mit
   `context_data_missing`.
4. Während der notwendigen Warmup-Zeit blockiert
   `context_warmup` fail-closed.
5. Danach werden nacheinander geprüft:
   - BTCUSDC-Trailing-Trend;
   - BTCUSDC-Trailing-Volatilität;
   - ETHBTC-Trailing-Relative-Stärke.
6. Nur `context_allowed` bestätigt das bereits vorhandene Basissignal.
7. Der tatsächliche hypothetische ETHUSDC-Einstieg bleibt unverändert am Open
   der folgenden Kerze.

## Policy v1

`ContextVetoPolicy` ist unveränderlich und verwendet ausschließlich
namensräumlich getrennte Parameter:

- `context_btc_trend_lookback`;
- `context_btc_min_trend_bps`;
- `context_btc_volatility_lookback`;
- `context_btc_max_volatility_bps`;
- `context_ethbtc_trend_lookback`;
- `context_ethbtc_min_trend_bps`.

Standardwerte:

- BTC-Trendlookback: 240 Minuten;
- BTC-Mindesttrend: -25 bps;
- BTC-Volatilitätslookback: 120 Minuten;
- BTC-Maximalvolatilität: 80 bps;
- ETHBTC-Trendlookback: 240 Minuten;
- ETHBTC-Mindesttrend: -15 bps.

Diese Werte sind noch keine optimierten Gewinnerparameter. Sie definieren nur
einen nachvollziehbaren ersten Kontextvertrag und werden nicht anhand eines
Holdouts angepasst.

## Leakage-Schutz

Jede Entscheidung an Index `i` verwendet ausschließlich Kerzen bis einschließlich
Index `i`. Änderungen an späteren BTCUSDC-/ETHBTC-Kerzen dürfen eine bereits
getroffene Entscheidung nicht verändern. Dies wird explizit getestet.

## Simulatorintegration

Nur `context_filter` verwendet `market_context`. Alle anderen
Strategiefamilien liefern mit oder ohne übergebenes Kontextobjekt identische
Ergebnisse.

Der direkte `_signal()`-Zweig für `context_filter` liefert immer `False`.
Dadurch kann der Kontextpfad die zentrale `_entry_decision()` nicht umgehen.
Ein rekursiver `base_family=context_filter` wird blockiert.

## Reporting

Abgelehnte Basissignale erscheinen in den vorhandenen Simulator-Rejections:

- `context_data_missing`;
- `context_warmup`;
- `context_veto_btc_trend`;
- `context_veto_btc_volatility`;
- `context_veto_ethbtc_relative_strength`;
- `context_recursive_base_forbidden`.

Damit lässt sich später getrennt messen, ob Kontext wirklich verbessert oder
nur zu viele Signale entfernt.

## Aktuelle Grenze

Dieser PR integriert die pure Entscheidung und den Simulatorpfad. Er aktiviert
noch keine Kontextkandidaten im Search Frontier und verändert noch nicht den
Production-Research-Loader. Die Reaktivierung erfolgt erst in einem getrennten
Schritt mit vollständiger Datenfenster- und Ressourcenrechnung.

## Sicherheit

Unverändert gesperrt bleiben:

- Live;
- Paper;
- Testtrade;
- echte Orders;
- Kontozugriff;
- API-Keys und private Endpunkte;
- Shorts;
- Margin;
- Futures;
- Leverage.
