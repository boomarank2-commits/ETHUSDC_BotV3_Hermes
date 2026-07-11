# PR #9 - Context market data alignment

Stand: 2026-07-11

## Branch

- Branch: `review/context-data-alignment-v1`
- Base: `review/windows-production-research-runner-v1`
- Pull request: #9
- Last fully tested implementation commit before this handoff update: `0e5b19201fa716e8bbc93e1854fb89e3ee77c34c`

## Implementierter Umfang

Der bestehende ETHUSDC-ZIP-Loader wurde ohne parallelen Datenlayer auf eine
feste Symbol-Allowlist erweitert:

- ETHUSDC;
- BTCUSDC;
- ETHBTC.

ETHUSDC bleibt der einzige handelbare Markt. Die neuen Kontextfunktionen
akzeptieren ausschließlich BTCUSDC und ETHBTC.

## Neue öffentliche Schnittstellen

- `load_symbol_1m_candles(...)`;
- `load_context_1m_candles(...)`;
- `load_aligned_market_candles(...)`;
- `align_market_candles(...)`;
- `AlignedMarketCandles`.

`load_ethusdc_1m_candles()` und die bestehende Konstante `SYMBOL=ETHUSDC`
bleiben kompatibel erhalten.

## Validierung

Der Loader prüft pro Symbol:

- erlaubtes Symbol;
- externen Rohdatenpfad;
- ZIP-/CHECKSUM-Paar;
- korrektes Symbol-/Intervallpräfix in ZIP und CSV;
- genau eine CSV;
- keine doppelten Kerzen;
- exakt 60-Sekunden-Schritte;
- positive OHLC-Preise;
- nichtnegative Volumenwerte;
- konsistente OHLC-Werte.

Die Ausrichtung verlangt zusätzlich:

- drei nichtleere Sequenzen;
- gleiche Kerzenanzahl;
- exakt identische UTC-Open-Timestamps;
- keine Interpolation, kein Forward-Fill und keine erfundene Kerze.

Die Repository-Pfadprüfung bewertet den ursprünglichen Windows-/POSIX-Pfadtyp
vor nativer Auflösung. Dadurch wird ein absoluter Windows-Datenpfad auf Linux
nicht fälschlich als Repository-Unterordner interpretiert.

## Tests

GitHub Actions, Ubuntu 24.04, Python 3.12 und PowerShell:

- 793 Tests bestanden;
- Python-Source-Kompilierung bestanden;
- PowerShell-Parserprüfung bestanden;
- gestapelte Whitespace-Prüfung bestanden.

Neue Tests decken ab:

- exakte Allowlist und Rollen;
- Laden aller drei öffentlichen Märkte;
- Ablehnung von ETHUSDC im Kontext-Wrapper;
- Ablehnung unbekannter Symbole;
- falsches CSV-Symbol;
- erfolgreiche 1:1-Ausrichtung;
- unterschiedliche Längen;
- verschobene Kontextzeitachse;
- interne Kontextlücke;
- unveränderte Eingabesequenzen.

## Sicherheit

Dieser PR enthält noch keine Kontextstrategie und keinen Kontextkandidaten. Er
aktiviert keine Orders und keine Trading-API.

Unverändert gesperrt:

- Live;
- Paper;
- Testtrade;
- Orders;
- Kontozugriff;
- API-Keys/private Endpunkte;
- Shorts;
- Margin;
- Futures;
- Leverage.

## Nächster Schritt

Ein separater PR ergänzt trailing-only Kontextfeatures und Risiko-Vetos auf
Basis exakt ausgerichteter BTCUSDC-/ETHBTC-Kerzen. `context_filter` bleibt bis
dahin in Search Frontier v2 deaktiviert.
