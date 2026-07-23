# Protocol v3 – Handoff Aufgabe 20/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 20/33 – Opportunity- und Regime-Schicht – DONE_100`

Gesamtfortschritt: `20/33 = 60,61 %`.

Exakt nächste Aufgabe: `Aufgabe 21 – Lokale Spezialisten hinter der bestehenden Engine bauen`.

## Implementierung

Neu sind der Vertrag `protocol_v3_causal_opportunity_regime_v1`, die öffentliche API `ethusdc_bot.protocol_v3.opportunity_regime_api`, ein foldgebundener Regime-Fit-State und ein kausales Assessment je gemeinsamem Kontextzeitpunkt.

Die Schicht verwendet ausschließlich den Task-19-Store und berechnet:

- RMS der letzten 24 abgeschlossenen 1h-Returns als realisierte Volatilität;
- mittlere Range der letzten 14 abgeschlossenen 1h-Bars als ATR-Näherung;
- Median-Range der letzten 20 abgeschlossenen 1h-Bars;
- aktuelle 4h-Range relativ zum Median der vorherigen 20 abgeschlossenen 4h-Ranges;
- zusammengesetzten 24h-Trend und Kaufman-ähnliche Effizienz;
- Abstand zum Median der letzten 20 abgeschlossenen 4h-Closes;
- Pullback vom Hoch der letzten 12 abgeschlossenen 4h-Bars in ATR-Einheiten;
- zusammengesetzte BTCUSDC- und ETHBTC-Returns der letzten sechs abgeschlossenen 4h-Bars.

Alle Schwellen sind Type-7-Quantile aus dem exakten Task-14-Fold-Fit. Mindestens 60 vollständige Trainingsbeobachtungen sind erforderlich. Der Fit-State bindet Feature-Store, Task-19-Fit-State, Foldgrenzen, Metrikinventar und Safety Locks.

## Klassifikation

- Opportunity: `LOW`, `MEDIUM`, `HIGH`;
- Rangezustand: `COMPRESSED`, `NORMAL`, `EXPANDED`;
- Struktur: `TREND`, `COMPRESSION`, `RANGE`, `STRESS`, `UNKNOWN`;
- kompatibles Quality-Gate-Regime: `down_low`, `down_high`, `up_low`, `up_high`.

Nur die drei klaren Strukturen dürfen dem späteren Task-22-Router einen unverbindlichen Familienhinweis geben. Es wird keine Strategie ausgewählt. Stress, niedrige Kapazität, Widerspruch zwischen ETH und beiden Kontextmärkten, unklare Struktur oder fehlender Warmup ergeben zwingend `NO_TRADE`.

## Tests

Abgedeckt sind Vertrag/API/Pipelinebindung, training-only Fit und Replay, kausale Assessments, alle fünf Strukturzustände, unabhängige Widerspruchs- und Stresssperren, unveränderte Nichtauswahl-Grenze sowie neu gehashte Schwellen- und Zukunftsmanipulation.

Validierung:

- vollständige Suite: `1.158 Tests erfolgreich`;
- `python -m compileall -q src`: erfolgreich;
- `git diff --check`: erfolgreich.

## Reale Projektlage

Der bekannte Datenbestand bleibt weiterhin `BLOCKED_MISSING_WARMUP`. Die neue Schicht kann daher keine reale Origin freigeben und umgeht diese bestehende Task-5-Sperre nicht.

## Sicherheitsgrenzen

- keine Orders, Trading-API oder API-Keys;
- kein Paper-, Testtrade- oder Live-Pfad;
- Opportunity ist kein Richtungssignal;
- Kontextmärkte handeln niemals;
- keine Spezialisten- oder Routerauswahl vor Aufgabe 21/22;
- keine Gate-Lockerung und keine Optimierung auf 3 USDC/Tag.

## Exakt nächstes Ticket

`Aufgabe 21 – Lokale Spezialisten hinter der bestehenden Engine bauen`
