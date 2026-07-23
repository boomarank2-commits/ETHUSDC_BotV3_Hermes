# Protocol v3 – Handoff Aufgabe 17/33

Stand: 2026-07-19

## Status

`Protocol v3: Aufgabe 17/33 – PBO/CSCV exakt implementieren – DONE_100`

Gesamtfortschritt: `17/33 = 51,52 %`.

Exakt nächste Aufgabe: `Aufgabe 18 – DSR und Multiple-Testing-Diagnostik implementieren`.

## Ausgangsstand

- Branch: `codex/research-resume-and-ui-state-v1`;
- veröffentlichter Ausgangs-Head: `0584c8f7b1aa2d6579dd4765b25890ccb6087200`;
- Aufgabe 16 und GitHub Review CI waren grün;
- die Task-16-Matrix wurde vor der Implementierung erneut adversarial geprüft.

## Implementierung

Neuer öffentlicher Pfad:

`ethusdc_bot.protocol_v3.pbo_api`

Neue Dateien:

- `configs/protocol_v3_pbo_contract.json`;
- `src/ethusdc_bot/protocol_v3/pbo.py`;
- `src/ethusdc_bot/protocol_v3/pbo_api.py`;
- `tests/unit/test_protocol_v3_pbo.py`.

Fortgeschrieben wurden:

- Pipelinebindung für Vertrag, Modell und öffentliche API;
- produktive Task-17-Unterstützung im reinen Task-15-Selector;
- weiterhin fail-closed fehlender Task-18-DSR-Zustand.

## Eingefrorener CSCV-Vertrag

- `S=12` zusammenhängende Blöcke zu exakt 30 Tagen;
- exakt 924 lexikographische Kombinationen von sechs IS-Blöcken;
- OOS ist immer das exakte Komplement;
- IS/OOS umfassen jeweils 180 Tage;
- IS-Metrik ist die deterministisch summierte mittlere tägliche Netto-MTM-PnL;
- Cash-ID: `protocol_v3_cash_no_trade_v1`;
- Cash nimmt an IS und OOS teil, zählt aber nicht als Trial oder Tradingprofil;
- IS-Tie: Kandidaten-ID aufsteigend, bei wiederverwendeter identischer Kandidaten-ID Profil-ID aufsteigend;
- OOS-Ties: exakter Durchschnittsrang;
- `omega=(r-0.5)/M`;
- `lambda=ln(omega/(1-omega))`;
- `development_pbo=count(lambda<=0)/924`;
- keine Rundung vor Auswahl, Rang oder Gate;
- separater Cash-Vergleich verlangt aggregierten Mittelwert strikt größer null.

Jede Evidenz enthält die 924 Split-Auditzeilen und deren Digest. Die Validierung führt die vollständige CSCV-Berechnung aus der semantisch revalidierten Task-16-Matrix erneut aus und vertraut keinen behaupteten Ergebnis-Hashes.

## Tests

Neue Tests: 8.

Abgedeckt sind:

- Vertrag, Cash-ID, Average-Rank-Regel, öffentliche API und Pipelinebindung;
- konstante Reihen `+1` und `+0,5`: `PBO=0`;
- spiegelbildlich überangepasste Reihen: `PBO=1`;
- identische Nullreihen: Durchschnittsrang, `lambda=0`, `PBO=1`;
- exakt 924 eindeutige IS-Splits und vollständige Komplemente;
- je Split exakt 180 IS-/180 OOS-Tage;
- weniger als zwei Tradingprofile ohne numerischen Ersatzwert;
- produktive PBO-Evidenz bei weiter typisiertem `NO_TRADE` ohne DSR;
- neu gehashte Ergebnismanipulation und permutierte Tagesraster blockieren.

Validierung:

- gezielte Task-15–17-, Pipeline- und Transaktionssuite: grün;
- vollständige Suite: `1.139 Tests erfolgreich`;
- `py -3.12 -m compileall -q src`: erfolgreich;
- `git diff --check`: erfolgreich.

## Unveränderte Sicherheitsgrenzen

- keine Orders, Trading-API oder API-Keys;
- kein Paper-, Testtrade- oder Live-Pfad;
- keine Gate-Lockerung und keine Optimierung auf 3 USDC/Tag;
- keine Full-fit-, Shortlist-, Finalisten- oder Outer-PnL im PBO;
- kein DSR, Outer-Bootstrap oder Monthly Gate;
- Candidate- und Fold-Slot bleiben `BOUND`;
- Transaktionsvertrag bleibt Version 3.

## Exakt nächstes Ticket

`Aufgabe 18 – DSR und Multiple-Testing-Diagnostik implementieren`
