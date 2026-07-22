# Next Action – Protocol v3 Aufgabe 33

Stand: 2026-07-22

## Startbedingung

Aufgabe 33 darf ausschließlich beginnen, wenn der abschließende GitHub-PR-CI-Lauf des Task-32-Dokumentations-Heads vollständig grün ist.

Vor der ersten Task-33-Änderung vollständig lesen:

1. `AGENTS.md`
2. `handoff/CURRENT_STATUS.md`
3. `handoff/NEXT_ACTION.md`
4. `handoff/PROTOCOL_V3_TASK_32_2026-07-22.md`
5. `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
6. `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`
7. `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`
8. `configs/protocol_v3_contract.json`
9. `configs/protocol_v3_pipeline_contract.json`
10. `configs/protocol_v3_acceptance_contract.json`

## Exakter Auftrag

Ausschließlich Aufgabe 33 umsetzen:

`Erster vollständiger Protocol-v3-Research-Lauf und Abschlussbericht`.

## Pflicht-Preflight

Vor einem rechenintensiven Lauf fail-closed und ohne Ergebnisanpassung prüfen:

- aktuellen Git-/Pipeline-/Code-Commit und sauberen Branchstand;
- aktuellen gemeinsamen vollständigen UTC-Stichtag für ETHUSDC, BTCUSDC und ETHBTC;
- exakt vollständiges 1m-Raster, Rohdaten-/Archivdigests und erforderlichen 20-Tage-plus-1-Minute-Warmup aller drei Märkte;
- öffentliche Exchange-Info sowie exakte Gebühren-, Slippage-, Rundungs- und Simulatorverträge;
- permanenten Trial-Ledger-Head und den ehrlichen Status der historischen Trial-Inventur;
- Task-2-Plan mit zwölf Origins, je 730 Entwicklungstagen und exakt 365 OOS-Tagen;
- globales Suchbudget, Seeds und nur verkürzende Stopregeln;
- Task-32-Akzeptanznachweis und weiterhin gesperrte Paper-/Testtrade-/Live-/Orderpfade.

Fehlende reale Daten, Warmup, Exchange-Info oder Trial-Evidenz niemals durch Fixtures, Defaults oder erfundene Digests ersetzen. Öffentliche Marktdaten dürfen nur über die vorhandenen Datenwerkzeuge ergänzt und anschließend vollständig auditiert werden. Keine privaten Endpunkte oder API-Keys.

## Laufanforderungen

- vorhandene Protocol-v3-Kette wiederverwenden; keinen zweiten Researchrunner bauen, sofern ein bestehender Einstieg erweitert werden kann;
- dieselbe eingefrorene Pipeline an exakt zwölf Origins jeweils auf den unmittelbar vorherigen 730 Tagen vollständig refitten;
- 365 OOS-Tage lückenlos und genau einmal ausführen;
- neue Entries erst `T+24h`; alte Position ausschließlich exit-only bis flat;
- No-Trade-Tage mit exakt null MTM erhalten;
- Kontext ETHUSDC/BTCUSDC/ETHBTC exakt geschlossen und ausgerichtet;
- Outer-Ergebnisse bis zum vollständigen Ende nicht in spätere Fits, Parameter, Gates oder menschliche Entscheidungen zurückführen;
- Trial-Ledger, Task-13-Checkpoints, Resume und Cache transaktional verwenden;
- Baseline-, Joint- und Slippage-Stress, Monthly Gate, Hindsight, Capture-Ratios und 10.000er Bootstrap ausführen;
- historischer Lauf bleibt `monthly_process_oos`, `NOT_FRESH`, `diagnostic_only` und nicht adoption-/finalfähig;
- kein echtes `sealed_final_holdout` registrieren oder verbrauchen.

## Ehrlicher Endstatus

Der Abschlussbericht muss genau einen fachlich belegten Status ausweisen:

- `TARGET_REACHED`, wenn der historische Monatsprozess nach allen Kosten und Gates mindestens 3 USDC pro Kalendertag erreicht;
- `TARGET_NOT_REACHED`, wenn der Lauf vollständig ist, aber das Ziel verfehlt;
- `NO_EDGE_FOUND`, wenn die unveränderte Pipeline regelkonform Cash/`NO_TRADE` wählt oder keine robuste Edge besteht;
- einen expliziten `BLOCKED_*`-Status nur dann, wenn der vollständige Lauf aufgrund real fehlender Pflichtdaten oder unvervollständigbarer Evidenz nicht rechtmäßig begonnen beziehungsweise beendet werden kann.

Ein Blocker ist kein Erfolg und darf nicht als 100-Prozent-Projektergebnis, Backtest-Pass oder Botstart bezeichnet werden. Er muss Quelle, betroffenen Zeitraum, reproduzierbaren Nachweis und den kleinsten zulässigen Folgeschritt enthalten.

## Pflichtbericht

Mindestens ausweisen:

- Run-ID und Status;
- exakten Daten-, Trainings- und OOS-Zeitraum;
- Datenquellen und unreife/fehlende Quellen;
- getestete und valide Kandidaten;
- Router-Setups, Signale, Entry-Versuche und echte simulierte Trades;
- Netto-USDC/Tag, Gesamtprofit, Fees, Slippage, Drawdown, Winrate und Profit-Factor;
- aktive/No-Trade-Tage und wichtigste Ablehnungsgründe;
- Deployment-, Kalender-, Konzentrations-, Regime- und Stressmetriken;
- DSR, PBO, Hindsight-Capture und Bootstrap-Untergrenzen;
- `historically_hit`, `freshness`, `statistically_supported` und Adoptionstatus;
- eindeutige Aussage, ob der Bot gestartet werden darf.

## Harte Grenzen

- keine Gate-, Ranking-, Feature-, Kosten-, Suchraum- oder Parameteränderung nach Betrachtung von Outer-Ergebnissen;
- keine Fake-Trades, Fake-Fills, Fake-Reports oder perfekte Fills;
- keine Blindtestdaten als Ergebnisfeedback in spätere Fits;
- keine Umbenennung historischer Evidenz in frisch oder final;
- keine Orders, Trading-API, privaten Endpunkte oder API-Keys;
- kein Paper, Testtrade, Live, `active_config.json`, kanonische Adoption oder Botstart;
- Aufgabe 33 erst `DONE_100`, wenn der vollständige Lauf oder ein vertraglich zulässiger belegter Blocker, vollständige Tests, Handoff, Push und abschließender grüner GitHub-CI vorliegen.
