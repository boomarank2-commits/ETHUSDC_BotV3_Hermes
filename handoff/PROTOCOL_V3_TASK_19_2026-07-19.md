# Protocol v3 – Handoff Aufgabe 19/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 19/33 – Kausaler Multi-Timeframe-Feature-Store – DONE_100`

Gesamtfortschritt: `19/33 = 57,58 %`.

Exakt nächste Aufgabe: `Aufgabe 20 – Opportunity- und Regime-Schicht implementieren`.

## Implementierung

Neu sind der Vertrag `protocol_v3_causal_multitimeframe_feature_store_v1`, die öffentliche API `ethusdc_bot.protocol_v3.feature_store_api`, ein deterministischer Drei-Markt-Feature-Store und foldgebundene Feature-Fit-States.

Der Store bindet den vorhandenen Task-10-Kontext statt eine zweite Datenwahrheit zu erzeugen. Er verarbeitet für `ETHUSDC`, `BTCUSDC` und `ETHBTC`:

- feste UTC-Buckets `5m`, `15m`, `30m`, `1h`, `4h`, `1d`;
- Kalenderwochen Montag 00:00 UTC bis Montag 00:00 UTC;
- exakte UTC-Kalendermonate;
- ausschließlich vollständig vorhandene 1m-Quellbuckets;
- Bar-Information erst am exklusiven Bar-Ende.

Teilbuckets am Anfang oder Ende sind unsichtbar. Ein Feature-Snapshot wählt je Markt und Zeitebene ausschließlich die letzte Bar, deren Ende nicht nach dem gemeinsamen Kontextzeitpunkt liegt.

## Feature- und Fit-Vertrag

Task 19 friert eine kleine kausale Grundschicht ein:

- Return gegenüber dem vorherigen vollständig abgeschlossenen Aggregat;
- Range in Basispunkten;
- Kerzenkörper in Basispunkten;
- Close-Position innerhalb der Bar-Range;
- aggregiertes Volumen.

Opportunity, Regime und Routerentscheidungen bleiben Aufgabe 20 beziehungsweise 22.

Je Task-14-Fold werden Mittelwert, Stichprobenstandardabweichung `ddof=1`, Zero-Variance-Skalierung und Type-7-Quantile `0,25/0,50/0,75` nur auf dem exakten Fitintervall berechnet. Warmup darf Features seed-en, geht aber weder in Scaler noch Quantile ein. Store und Fit-State sind kanonisch gehasht; der Fit-State bindet nur die kompakte Store-Identität und dupliziert nicht den gesamten Store.

## Tests

Neue Tests decken ab:

- Vertrag, öffentliche API und Pipelinebindung;
- echten Task-10-Binding-Build und exaktes Source-Replay;
- vollständige 5m-, Wochen- und Monatsbuckets bei gleichzeitig unfertigem Folgebucket;
- identisches Präfix-Replay und Sperre zukünftiger Kontextzeitpunkte;
- foldgenaue Fit-Grenzen, Scaler, Zero-Variance-Regel und Type-7-Quantile;
- strukturell gültige, neu gehashte Quelländerung, die gegen den gebundenen Kontext blockiert;
- neu gehashte Feature- oder Foldgrenzen-Manipulation.

Validierung:

- vollständige Suite: `1.152 Tests erfolgreich`;
- `python -m compileall -q src`: erfolgreich;
- `git diff --check`: erfolgreich.

## Reale Projektlage

Der bekannte reale Drei-Markt-Bestand bleibt wegen des bereits in Aufgabe 5 belegten fehlenden Vorlaufs `BLOCKED_MISSING_WARMUP`. Aufgabe 19 erzeugt keine historischen Rohdaten und umgeht diese Sperre nicht. Warmup besitzt ausdrücklich weder Signal- noch PnL- oder Orderrecht.

## Sicherheitsgrenzen

- keine Orders, Trading-API oder API-Keys;
- kein Paper-, Testtrade- oder Live-Pfad;
- BTCUSDC und ETHBTC bleiben reine Kontextmärkte;
- keine Gate-Lockerung oder Zielwertoptimierung;
- keine Opportunity-/Regimeklassifikation, Spezialisten, Router oder Outer-Ergebnisse vorgezogen.

## Exakt nächstes Ticket

`Aufgabe 20 – Opportunity- und Regime-Schicht implementieren`
