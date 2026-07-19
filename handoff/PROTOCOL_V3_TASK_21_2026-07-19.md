# Protocol v3 – Handoff Aufgabe 21/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 21/33 – Lokale Spezialisten hinter bestehender Engine – DONE_100`

Gesamtfortschritt: `21/33 = 63,64 %`.

Exakt nächste Aufgabe: `Aufgabe 22 – Deterministischen NO_TRADE-Router und FrozenCandidateBundle bauen`.

## Umsetzung

Der Vertrag `protocol_v3_bounded_local_specialists_v1` führt keine zweite Handels- oder Simulationsengine ein. Er bindet vier lokale Hypothesen an bereits vorhandene `StrategyCandidate`-Familien:

- `trend_pullback_reclaim` → `pullback_in_trend`;
- `compression_breakout_retest` → `breakout_volatility_filter`;
- `range_reversion_confirmed` → `mean_reversion_regime_filter`;
- `multiday_swing_trend` → `momentum_trend_filter`;
- `no_trade` besitzt bewusst keinen Basiskandidaten.

Jedes Bundle ist ETHUSDC-LONG-only, besitzt begrenzte Haltezeiten und bindet exakt den unveränderten Basiskandidaten. Die Spezialistenprüfung darf ein vorhandenes Engine-Rohsignal nur zusätzlich bestätigen. Sie kann niemals selbst ein Signal erzeugen.

Bestätigungen verwenden ausschließlich abgeschlossene Task-19-Bars und ein vorab validiertes Task-20-Assessment: 15m Pullback/Reclaim, 15m Breakout/Retest, 15m Range-Wiedereintritt oder ausgerichteten 1d-/4h-Mehrtagstrend.

## Tests und Sicherheitsgrenzen

Abgedeckt sind Vertrag/API/Pipelinebindung, exakte Zuordnung zu den vier vorhandenen Engine-Familien, Kandidatenidentität, Haltezeit- und LONG-only-Grenzen, dominantes `no_trade`, fehlendes Rohsignal, Regime-Mismatch, Mehrtagstrend-Bestätigung, manipulierte Bundles und zukünftiger Feature-Zugriff.

Validierung:

- vollständige Suite: `1.163 Tests erfolgreich`;
- `python -m compileall -q src`: erfolgreich;
- `git diff --check`: erfolgreich.

Keine Orders, Trading-API, API-Keys, Paper-, Testtrade- oder Live-Freigabe. Die Auswahl und der lokale Edge-Nachweis bleiben Aufgabe 22.

## Exakt nächstes Ticket

`Aufgabe 22 – Deterministischen NO_TRADE-Router und FrozenCandidateBundle bauen`
