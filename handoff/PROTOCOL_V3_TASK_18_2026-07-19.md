# Protocol v3 – Handoff Aufgabe 18/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 18/33 – DSR und Multiple-Testing-Diagnostik – DONE_100`

Gesamtfortschritt: `18/33 = 54,55 %`.

Exakt nächste Aufgabe: `Aufgabe 19 – Kausalen Multi-Timeframe-Feature-Store bauen`.

## Implementierung

Neu sind der versionierte Vertrag `protocol_v3_exact_deflated_sharpe_v1`, die öffentliche API `ethusdc_bot.protocol_v3.dsr_api`, die exakte DSR-Evidenz und ihre produktive Einbindung in die reine Task-15-Auswahl.

Der DSR bindet unveränderlich:

- die vollständige Task-17-PBO-Identität;
- Task-16-Matrix, Profil, Kandidat und geordnetes 360-Tage-Raster;
- jede verwendete permanente Trial-Reihe samt Digest;
- `N_raw` und den erneut gelesenen aktuellen Ledger-Head;
- alle Statistik-Zwischenwerte und Safety Locks.

## Eingefrorene Statistik

- `n=360`, keine Annualisierung, Stichprobenstandardabweichung `ddof=1`;
- `K=floor(4*(n/100)^(2/9))=5`;
- zentrierte Stichprobenautokorrelation mit vollständiger zentrierter Quadratsumme im Nenner;
- Bartlett-Gewichte, `VIF>=1`, `n_eff=n/VIF`;
- adjustierter Fisher-Pearson `G1` und unverzerrter Fisher-Exzess `G2+3`;
- `sigma_SR` als Stichprobenstandardabweichung aller kausal gebundenen Trial-Sharpes;
- `N_eff_trials=(trace(C)^2)/trace(C@C)` nur als Diagnose;
- Gate-Benchmark `SR0` verwendet unverändert den vollständigen permanenten `N_raw`;
- `development_dsr=Phi(z)` und Mindestwert `0,95`.

Nullvarianz, ungültiger Nenner, fehlendes gemeinsames Raster und zu wenige vollständige Trials liefern `INSUFFICIENT_EVIDENCE` ohne Ersatzwert. Cash liefert `NOT_APPLICABLE_NO_TRADE` ohne Zahl.

## Reale Projektlage

Die historische Trial-Inventur ist weiterhin ausdrücklich nur eine Untergrenze. Deshalb liefert der reale Pfad korrekt `INSUFFICIENT_TRIAL_HISTORY`; Task 18 erfindet weder Trial-Reihen noch einen DSR. Bis zu einer belegbar vollständigen Inventur bleibt ausschließlich `NO_TRADE` zulässig.

## Tests

Neue Task-18-Tests decken ab:

- Vertrag, öffentliche API und Pipelinebindung;
- reale unvollständige Trial-Historie;
- Cash ohne numerischen Ersatzwert;
- vollständiges synthetisches Zwei-Trial-Inventar mit Golden-Werten für Sharpe, VIF, `n_eff`, Schiefe, Kurtosis, `sigma_SR`, `SR0`, Nenner, `z` und DSR;
- produktive Task-15-Unterstützung mit exakten DSR-Identitäten;
- Nullvarianz als typisierte unzureichende Evidenz;
- neu gehashte Manipulation und veralteter Ledger-Head als harte Sperren.

Validierung:

- vollständige Suite: `1.145 Tests erfolgreich`;
- `python -m compileall -q src`: erfolgreich;
- `git diff --check`: erfolgreich;
- Ruff war in der lokalen Projektumgebung nicht installiert und daher kein zusätzlich ausführbares Gate.

## Sicherheitsgrenzen

- keine Orders, Trading-API oder API-Keys;
- kein Paper-, Testtrade- oder Live-Pfad;
- keine Gate-Lockerung und keine Optimierung auf den Zielwert;
- kein Outer-Ergebnis, Bootstrap, Monthly Gate, Feature Store oder Regime vorgezogen.

## Exakt nächstes Ticket

`Aufgabe 19 – Kausalen Multi-Timeframe-Feature-Store bauen`
