# 36 - Context market data alignment

Stand: 2026-07-11

## Zweck

Der bestehende read-only Binance-1m-ZIP-Loader unterstützt jetzt eine feste
Allowlist:

- `ETHUSDC` – einziger handelbarer Markt;
- `BTCUSDC` – ausschließlich Gesamtmarkt-/Risikokontext;
- `ETHBTC` – ausschließlich relative Stärke und Entkopplung.

Diese Erweiterung lädt nur öffentliche Marktdaten. Sie enthält keine Strategie,
keinen Orderpfad, keine API-Schlüssel und keine Kontodaten.

## Kompatibilität

`load_ethusdc_1m_candles()` bleibt als bestehende öffentliche Funktion erhalten
und verwendet intern den neuen generischen Loader mit `symbol=ETHUSDC`.

Neue Funktionen:

- `load_symbol_1m_candles(...)` – nur für die feste Allowlist;
- `load_context_1m_candles(...)` – akzeptiert ausschließlich BTCUSDC/ETHBTC;
- `load_aligned_market_candles(...)` – lädt alle drei Märkte und verlangt
  identische Zeitstempel;
- `align_market_candles(...)` – prüft bereits geladene Sequenzen.

## Fail-closed-Ausrichtung

Eine Kontextserie wird niemals vorwärts aufgefüllt, interpoliert oder erfunden.
Die Ausrichtung verlangt:

- nichtleere Sequenzen;
- ausschließlich `Candle`-Werte;
- keine doppelten Zeitstempel;
- exakt 60 Sekunden zwischen allen Kerzen;
- gleiche Kerzenanzahl in allen drei Märkten;
- exakt dieselben UTC-Open-Timestamps an jedem Index.

Eine fehlende Minute, ein späterer Beginn, ein früheres Ende oder eine
verschobene Zeitachse beendet die Ausrichtung mit `DataLoadError`.

## Dateivertrag

Für jedes Symbol gilt unverändert:

`<raw_root>/raw/binance/spot/<SYMBOL>/klines/1m/<SYMBOL>-1m-YYYY-MM-DD.zip`

Jede ZIP-Datei benötigt eine nichtleere `.CHECKSUM`-Begleitdatei und darf genau
eine CSV mit demselben Symbol-/Intervallpräfix enthalten.

## Rollen und Sicherheit

Das Symbol im Loader bestimmt ausschließlich den öffentlichen Datenpfad. Es
erteilt keine Handelsberechtigung.

Verbindlich:

- nur ETHUSDC darf später Signale in hypothetische Trades umsetzen;
- BTCUSDC und ETHBTC dürfen niemals selbst einen Trade oder eine Order öffnen;
- Kontextdaten bleiben trailing-only und dürfen keine zukünftigen Kerzen
  verwenden;
- Live, Paper, Testtrade und Orders bleiben gesperrt.

## Aktueller Umfang

Dieser PR baut nur die Daten- und Ausrichtungsgrundlage. Kontextfeatures,
Kontext-Vetos und neue Kontextkandidaten werden erst in einem separaten PR
implementiert. Bis dahin bleibt `context_filter` in Search Frontier v2 bewusst
deaktiviert.
