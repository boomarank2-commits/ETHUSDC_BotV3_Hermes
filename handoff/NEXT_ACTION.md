# Next Action – GPT 1 / neuer Codex-Chat

## Exakt aktive Aufgabe

`Aufgabe 27 – Hindsight-Benchmarks, Capture-Ratios und Bootstrap – IN_PROGRESS`

Kein späterer Punkt darf vorgezogen werden.

## Nächster Implementierungsschritt

Ersetze den derzeitigen allgemeinen `benchmark_evidence`-Zulieferkanal in `src/ethusdc_bot/protocol_v3/historical_diagnostics.py` durch semantisch validierte Solver-Evidenz:

1. `all_candle_one_trade_close_hindsight`
   - vollständige ETHUSDC-Prozessdaten;
   - höchstens ein Roundtrip je UTC-Tag;
   - positive Volumenpunkte;
   - Long-only, ein Lot, echte Binance-Rundung;
   - unveränderte Task-7-/8-Kosten und Fills;
   - ausschließlich optimistische Diagnostik.

2. `candidate_matched_volume_filtered_hindsight`
   - identische maximale Tradezahl und Haltedauer des jeweils eingefrorenen Kandidaten;
   - Long-only, ein Lot;
   - identische Task-24-Exit-only-Handoff-/Flat-State-Maschine;
   - identische Rundung, Fees, Slippage und Prozessend-Liquidation;
   - positive Volumenpunkte und vollständige 365-Tage-Abdeckung.

3. Evidenzbindung
   - Raw-Data-/Snapshot-Hash;
   - Code-/Pipelinegeneration;
   - Task-22-Bundle-Kette und Task-23-Origin-Hashes;
   - Task-24-Rotationszustände;
   - Execution-, Cost- und Exchange-Info-Identitäten;
   - Solver-Input-/Output-Digests;
   - keine Caller-Digest-Behauptungen ohne transitive Neuvalidierung.

4. Negative Tests
   - fehlende oder doppelte Tage;
   - Null-/Negativvolumen;
   - Lookahead;
   - zu viele Trades oder zu lange Haltedauer;
   - falsches Bundle/Handoff/Kostenprofil;
   - manipulierte Benchmarkwerte trotz neuem Hash;
   - Feedback in Auswahl oder Monthly Gate.

5. Abschluss von Aufgabe 27
   - gezielte Tests;
   - vollständige Suite;
   - `docs/41...` auf `DONE_100` und 27/33 aktualisieren;
   - finalen Task-27-Handoff schreiben;
   - Commit und Push auf Branch `codex/research-resume-and-ui-state-v1`;
   - GitHub-CI abwarten und erst danach Aufgabe 28 beginnen.

## Danach verbleibende Aufgaben

- 28 – aktueller 730-Tage-Refit und Champion/Challenger/Cash;
- 29 – strikt orderfreier Research-Challenger-Shadow;
- 30 – vollständige UI-/Bedienzustände;
- 31 – Final-Evaluator für ein wirklich frisches versiegeltes Jahr;
- 32 – End-to-End-Parität, Fehler-Injektion und Abnahme;
- 33 – erster vollständiger Protocol-v3-Research-Lauf und Abschlussbericht.

## Harte Sperren

Keine Gates lockern, keine Fake-Trades/-Reports, kein Audit als Trainingsergebnis, kein Finalclaim aus historischer Diagnostik und keine Aktivierung von Orders, Paper, Testtrade oder Live.
