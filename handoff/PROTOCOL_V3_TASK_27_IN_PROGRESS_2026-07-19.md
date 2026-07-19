# Protocol v3 – Aufgabe 27 IN_PROGRESS

Stand: 2026-07-19

## Verbindlicher Gesamtstand

`26/33 = 78,79 % DONE_100`.

Aufgabe 27 ist aktiv und ausdrücklich noch nicht `DONE_100`.

## Bereits umgesetzt

- exakt 365 tägliche Task-25-Netto-MTM-Werte einschließlich Nulltagen;
- exakt 10.000 Circular-Stationary-Bootstrap-Replikationen je `L ∈ {5,10,20}`;
- deterministischer PRNG-Vertrag und UInt64-Seed aus dem vorab gebauten Manifesthash;
- einseitige 95-%-Untergrenze als exakt 500. geordneter Wert ohne Interpolation;
- strenges historisches Flag nur, wenn alle drei Untergrenzen mindestens 3 USDC/Tag erreichen;
- optimistische All-Candle- und kandidatengleiche Capture-Ratio-Felder;
- vollständige kandidatengleiche Constraint-Matrix;
- manuelle Leakage-/Overfit-Sperre bei auffällig hoher Capture;
- `NOT_FRESH`, `diagnostic_only`, keine statistische Unterstützung, keine Adoption und kein Finalstatus;
- vollständige Quellen-Neuauswertung für persistierte Diagnostikreports.

## Noch zwingend offen innerhalb Aufgabe 27

Die beiden Hindsight-Benchmarkwerte werden aktuell als content-gehashte Evidenz konsumiert. Vor `DONE_100` muss GPT 1 beziehungsweise der nächste Codex-Chat:

1. den tatsächlichen `all_candle_one_trade_close_hindsight`-Solver auf vollständigen ETHUSDC-Prozessdaten anbinden;
2. den `candidate_matched_volume_filtered_hindsight`-Solver mit identischer maximaler Tradezahl, Haltedauer, Long-only-/Ein-Lot-/Exit-only-Handoff-Zustandsmaschine, Rundung und Kosten anbinden;
3. positive-Volumen- und vollständige 365-Tage-Abdeckung beweisen;
4. Solver-Input, Output, Code, Daten, Bundle-Kette, Execution-/Kostenvertrag und Ergebnis per transitive Hash-Identity binden;
5. manipulierte, unvollständige, Lookahead- oder Caller-Claim-Benchmarkwerte fail-closed ablehnen;
6. gezielte Solvertests, vollständige Suite, Handoff, Commit, Push und GitHub-CI abschließen.

Erst danach darf Aufgabe 27 auf `DONE_100` gesetzt und Aufgabe 28 begonnen werden.

## Sicherheitsstatus

Keine Benchmarkzahl darf Auswahl, Monthly Gate oder Finalstatus beeinflussen. API-Keys, Trading-API, Orders, Paper, Testtrade und Live bleiben gesperrt.

Validierter Zwischenstand:

- gezielte Task-25/26/27-Suite: erfolgreich;
- vollständige Suite: `1.197 Tests erfolgreich`;
- Compile, Ruff und `git diff --check`: erfolgreich.
