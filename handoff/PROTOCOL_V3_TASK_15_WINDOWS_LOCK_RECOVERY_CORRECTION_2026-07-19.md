# Protocol v3 – Task-15 Windows-Lock-Recovery-Korrektur

Stand: 2026-07-19

## Ausgangsstand

- Branch: `codex/research-resume-and-ui-state-v1`
- geprüfter veröffentlichter Head: `10a8823951dc77b02ac362701e209903e0d85c43`
- exakt nächste Implementierungsaufgabe bleibt Task 16.

## Reproduzierter Befund

Vor der Task-16-Freigabe scheiterte der bestehende Regressionstest
`test_dead_same_host_lock_can_be_recovered_with_receipt` reproduzierbar unter
Windows. `os.kill(pid, 0)` meldete für den bereits beendeten Kindprozess
`EINVAL`. Die generische Prüfung ordnete das korrekt konservativ als unklar
ein, konnte dadurch aber einen nachweislich verendeten Same-Host-Lock nicht
über das immutable Recovery-Receipt bergen.

## Minimale Korrektur

`transactional_cache_store._process_alive` verwendet unter Windows jetzt die
native, read-only Prozessstatusabfrage `OpenProcess` plus
`GetExitCodeProcess`:

- ein nicht vorhandener PID (`ERROR_INVALID_PARAMETER`) gilt als beendet;
- ein erreichbarer Prozess mit `STILL_ACTIVE` gilt als aktiv;
- ein beendeter erreichbarer Prozess gilt als beendet;
- Zugriffsfehler und jeder sonst unklare Zustand bleiben fail-closed `None`;
- ein zwischenzeitlich wiederverwendeter aktiver PID blockiert die Recovery
  weiterhin konservativ.

Andere Plattformen behalten unverändert die bisherige `os.kill(pid, 0)`-
Prüfung. Transaktionsidentität, Cache, Ledger, Fold- und Kandidatenbindung
wurden nicht verändert.

## Validierung

- Task-14 Fold-Suite: 10 Tests erfolgreich;
- Task-15 Selection-Suite: 9 Tests erfolgreich;
- Task-15 Missing-Evidence-Suite: 1 Test erfolgreich;
- vollständige Transaktionsdatei: 11 Tests erfolgreich;
- zuvor fehlschlagender Dead-PID-Test separat: erfolgreich;
- aktive Prozesssperre separat: erfolgreich;
- vollständige Pytest-Suite: 100 % erfolgreich (unveränderter Bestand von
  1.118 Tests);
- `py -3.12 -m compileall -q src`: erfolgreich;
- `git diff --check`: erfolgreich.

## Unveränderte Sicherheitsgrenzen

- keine Orders, Trading-API oder API-Keys;
- kein Paper-, Testtrade- oder Live-Pfad;
- keine Gate-, Ranking-, Strategie-, PnL- oder 3-USDC-Optimierung;
- Candidate- und Fold-Slot bleiben `BOUND`;
- Transaktionsvertrag bleibt Version 3;
- PBO, DSR, Outer-Orchestrierung und Task-17+-Funktionen bleiben unberührt.

## Nächster Schritt

Nach Push und grüner GitHub Review CI ist ausschließlich
`Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets`
zulässig.
