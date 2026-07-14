# Protocol v3 – verbindliche Implementierungsreihenfolge

Stand: 2026-07-14
Quelle: `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 2/33 abgeschlossen

## Arbeitsregel

Es ist immer genau eine Aufgabe aktiv. Eine spätere Aufgabe beginnt erst, wenn die vorherige Aufgabe den Status `DONE_100` besitzt.

`DONE_100` bedeutet ohne Ausnahme:

1. Ziel und Grenzen der Aufgabe sind vollständig umgesetzt.
2. Vorhandene vergleichbare Funktionen wurden geprüft und möglichst wiederverwendet.
3. Unit-, Integrations-, Negativ- und Fail-closed-Tests sind grün.
4. Python-Kompilierung, PowerShell-Syntax und Whitespace-Prüfung sind grün.
5. Erforderliche lokale Daten- oder Langlauftests sind dokumentiert; irrelevante Langläufe werden nicht vorgezogen.
6. Keine spätere Aufgabe wurde heimlich vorgezogen.
7. Ein GitHub-Handoff nennt Dateien, Tests, Ergebnis, offene Grenzen und exakt die nächste Aufgabe.
8. PR-Branch und GitHub-Stand sind nachvollziehbar; Paper, Testtrade, Live, Orders, private Endpunkte und API-Keys bleiben gesperrt.

## Aufgabe 1 – Protocol-v3-Vertrag versioniert übernehmen

**Status:** `DONE_100`

**Ziel:** Blueprint, Projektvertrag, Agentenregeln und Portfolio-/Shadow-Vertrag widerspruchsfrei als Vertragsgeneration 3.0.0 übernehmen.

**Abnahme:**

- Evidenzklassen und Rolling-Reuse-Regel sind eindeutig und maschinenlesbar.
- Verbrauchter Auditblock bleibt `NOT_FRESH` und `diagnostic_only`.
- Protocol v2 und Single-Candidate-Finalpfad können keinen Protocol-v3-Finalstatus erzeugen.
- Widersprüche und fehlende Versionen blockieren fail-closed.

**Bericht:** `handoff/PROTOCOL_V3_TASK_01_2026-07-13.md`

## Aufgabe 2 – Monatskalender und Boundary-Vertrag implementieren

**Status:** `DONE_100`

**Ziel:** Exakt zwölf äußere Origins, 730 Entwicklungstage je Origin, 365 lückenlose Prozess-OOS-Tage und feste `T+24h`-Aktivierung als reine Boundary-Schicht implementieren.

**Abnahme:**

- UTC, Ankertag 8, synthetisches `b0`, `as_of_day`, `valid_from`, `valid_until`, `manual_decision_deadline` und `entry_enabled_at` sind modelliert.
- Fixtures für Enden `2024-03-08`, `2025-03-08` und `2026-07-08` liefern jeweils exakt zwölf Intervalle und 365 eindeutige OOS-Tage.
- Jeder Origin besitzt exakt 730 Trainingstage; kein OOS-Tag liegt in seinem eigenen Training.
- Ein Button vor der Frist zielt auf den aktuellen Anker; exakt ab `T+24h` nur auf den nächsten Anker. Rückdatierung ist immer verboten.
- Doppelte, lückenhafte, nicht monotone oder falsche Grenzen sowie naive/nicht-UTC-Zeitpunkte blockieren fail-closed.
- Bestehende Protocol-v2-Split-Logik wurde nicht umgedeutet oder verändert.

**Bericht:** `handoff/PROTOCOL_V3_TASK_02_2026-07-14.md`

## Aufgabe 3 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren

**Status:** `NOT_STARTED` – exakt nächste Aufgabe

**Ziel:** Jede inhaltliche Pipelineversion besitzt eine unveränderliche Identität und vorab festgelegte Suchgrenzen.

**DONE_100:**

- Pipelinegeneration bindet Features, Familien, Suchraum, Ranking, Gates, Kosten, Simulator und Boundary-Regeln.
- Seeds entstehen deterministisch aus einem kanonischen Pre-Run-Manifest.
- Grenzen 12 Origins, 8 Zyklen, 40/12/3/2 sowie globale Maximalbudgets sind technisch erzwungen.
- `selection_stagnation_3_cycles` kann nur verkürzen und niemals Budgets erweitern.
- Änderungen erzeugen eine neue Generation; der permanente Trial-Zähler wird nie zurückgesetzt.

## Aufgabe 4 – Permanentes Trial-Ledger und historischen Import bauen

**Status:** `NOT_STARTED`

**Ziel:** Jeden dateninformierten Versuch append-only und generationsübergreifend erfassen.

**DONE_100:**

- Deterministische Trial-ID, Kandidat, Parameter, Features, Seed, Versionen, Codehash und Tagesreihe werden gespeichert.
- Cache-Hits bleiben sichtbare Wiederverwendung und werden nicht als unabhängiger Test gezählt.
- Historischer Import ist als Untergrenze markiert.
- Unvollständige Trial-Historie erzwingt `DSR=INSUFFICIENT_TRIAL_HISTORY` und `NO_TRADE`.

## Aufgabe 5 – Dynamischen Drei-Markt-Datensnapshot und Warmup herstellen

**Status:** `NOT_STARTED`

**Ziel:** Gemeinsamen letzten vollständigen UTC-Tag und erforderlichen Warmup für ETHUSDC, BTCUSDC und ETHBTC dynamisch bestimmen und einfrieren.

**DONE_100:**

- Kein Produktions-Hardcode auf `2026-07-07` bleibt.
- Watermark, 1.440-Minuten-Raster, Duplikate, Lücken, OHLC und Nullvolumen werden geprüft.
- `warmup_duration` folgt allen aktiven Lookbacks plus einer Quellbar.
- Fehlender Warmup oder ein unvollständiger Markt blockiert.

## Aufgabe 6 – Exchange-Info-Snapshot und vollständige Run-Fingerprints bauen

**Status:** `NOT_STARTED`

**Ziel:** Binance-Filter und sämtliche Laufidentitäten versioniert und resume-sicher binden.

**DONE_100:**

- PRICE_FILTER, LOT_SIZE/MARKET_LOT_SIZE und MIN_NOTIONAL/NOTIONAL sind versioniert.
- Fingerprints binden Rohdaten, Stichtag, Code, Pipeline, Features, Kontext, Gates, Kosten, Simulator, Boundary, Trial-Head und Exchange Info.
- Jede gebundene Änderung verhindert Resume und Cache-Hit.

## Aufgabe 7 – Notional-, Mengen-, Gebühren- und Rundungsparität herstellen

**Status:** `NOT_STARTED`

**Ziel:** Das 100-USDC-Lot realistisch gemäß Produktvertrag und Exchange-Filtern simulieren.

**DONE_100:**

- Angefordertes, reserviertes und tatsächlich ausgeführtes Entry-Notional werden getrennt gespeichert.
- Menge wird auf Step Size abgerundet; Gebühren werden auf tatsächlichem Notional zusätzlich verbucht.
- Verkauf verwendet exakt die gekaufte Menge; maximal ein Lot.
- Golden Trades prüfen Menge, Notional, Gebühren, Slippage und PnL bitgleich.

## Aufgabe 8 – Next-Tradable-Price und pessimistische Intrabar-Ausführung

**Status:** `NOT_STARTED`

**Ziel:** Signal-, Entry-, Stop-, TP-, Trail-, Gap- und Time-Exit-Reihenfolge realistisch festlegen.

**DONE_100:**

- Entry frühestens nach abgeschlossener Signalbar am nächsten handelbaren Preis.
- Stop vor TP bei Berührung in derselben 1m-Kerze.
- Gaps füllen zum schlechteren Preis; perfekte High-/Low-Fills sind unmöglich.
- Basis- und Stressprofile verwenden dieselbe Execution-Engine.

## Aufgabe 9 – Warmup-, Purge-, Fold-End- und Outer-State-Maschine

**Status:** `NOT_STARTED`

**Ziel:** Informationsintervalle, Pending Entry, Cooldown, offene Position und Modellwechsel kausal behandeln.

**DONE_100:**

- Purge folgt maximalem Label-/Holding-Horizont plus Latenz und Ausführungsbar.
- Innere Folds starten flat und liquidieren am Fold-Ende konservativ.
- Zwischen Origins wird nur eine offene Altposition mit alter Exitlogik übertragen.
- Alte Konfiguration ist exit-only; neue wartet auf `valid_from` und `flat_time`.

## Aufgabe 10 – Kontextparität und Drei-Markt-Watermark

**Status:** `NOT_STARTED`

**Ziel:** Kontext in Research, Replay, Finalpfad und Challenger identisch als reines Veto/Bestätigung verwenden.

**DONE_100:**

- Zeitpunkt `t` wird nur bei drei exakt ausgerichteten geschlossenen Bars verarbeitet.
- Fehlende, versetzte oder stale Daten blockieren.
- BTCUSDC und ETHBTC können nie handeln.
- Kontextidentität ist Bestandteil aller Fingerprints und Cache-Keys.

## Aufgabe 11 – Protocol-v3-Report-Schemas und Evidenzbedeutung

**Status:** `NOT_STARTED`

**Ziel:** Research-, Monatsprozess-, Challenger-, Forward- und Pipeline-Finalberichte getrennt versionieren.

**DONE_100:**

- Eigene Schemas und Storage-Roots verhindern Verwechslung mit Legacy-Finalreports.
- Freshness, historische Zielerreichung, statistische Unterstützung und Adoption können nicht falsch gesetzt werden.
- Sichtbare Forward-Monate können nicht nachträglich in ein Finalfenster gelangen.

## Aufgabe 12 – Kompakte Artefaktarchitektur

**Status:** `NOT_STARTED`

**Ziel:** Zwölf Monatsrefits ohne mehrfach eingebettete Großartefakte speicher- und lesbar machen.

**DONE_100:**

- Kleiner JSON-Index und getrennte deduplizierte Trade-, Daily-PnL-, Equity- und Diagnostikartefakte.
- Referenzen besitzen Digest, Schema und Provenienz.
- Größenbudgets werden geprüft; UI liest nur kleine Statusartefakte.

## Aufgabe 13 – Content-addressed Cache und transaktionales Resume

**Status:** `NOT_STARTED`

**Ziel:** Abbruch, Neustart und Cache-Wiederverwendung dürfen keine Entscheidung verändern.

**DONE_100:**

- Cache-Key bindet alle Daten-, Kontext-, Feature-, Kandidaten-, Fold-, Boundary-, Execution-, Simulator- und Kostenidentitäten.
- Checkpoints binden Code, Snapshot, Exchange Info, Pipelinegeneration, Trial-Head, Origin-Digests, Rotation und Store-Head.
- Atomic Replace, Lock und Digestprüfung verhindern Teilstände und doppelte Origins.

## Aufgabe 14 – Exakten inneren 6×60-Tage-Fold-Planer bauen

**Status:** `NOT_STARTED`

**Ziel:** Sechs nicht überlappende Validation-Folds auf den letzten 360 Entwicklungstagen bilden.

**DONE_100:**

- Boundary-Objekte entsprechen exakt Blueprint Abschnitt 6.3.
- Fits wachsen ab 370 Tagen vor Purging in 60-Tage-Schritten.
- Timestamp-Spies beweisen, dass kein Fit Validation oder Outer-Test sieht.

## Aufgabe 15 – Reine innere Auswahlfunktion extrahieren

**Status:** `NOT_STARTED`

**Ziel:** `select_candidate(training_window, frozen_pipeline_config)` deterministisch und ohne UI-/Laufzeitabhängigkeit bereitstellen.

**DONE_100:**

- Kein Zugriff nach `training_end` und kein Outer-Ergebnis als Input.
- Gleiche Inputs und Hashes erzeugen dieselbe Auswahl.
- Bestehende Engine und 40/12/3/2-Stufen werden wiederverwendet.
- Fehler oder fehlende Evidenz liefern `NO_TRADE`.

## Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets

**Status:** `NOT_STARTED`

**Ziel:** Allen zwölf getesteten Profilen dieselbe 360-Tage-OOS-Basisreihe geben.

**DONE_100:**

- Tägliche Netto-MTM-Reihe inklusive Nulltage je Profil.
- Cash ist feste Nullbaseline.
- Promotion 12 Basisreihen → 3 Full-WFV → 2 Finalisten ist budgetfest und nachvollziehbar.

## Aufgabe 17 – PBO/CSCV exakt implementieren

**Status:** `NOT_STARTED`

**Ziel:** `development_pbo` nach 12 Blöcken und 924 Splits berechnen.

**DONE_100:**

- IS-Ties, OOS-Ränge, Omega, Lambda und PBO entsprechen dem Vertrag.
- Unvollständige oder ungleiche Reihen liefern `INSUFFICIENT_EVIDENCE`.
- Outer-Ergebnisse werden niemals zurückgespielt.

## Aufgabe 18 – DSR und Multiple-Testing-Diagnostik implementieren

**Status:** `NOT_STARTED`

**Ziel:** DSR mit permanenten Trials, Autokorrelation, Schiefe und Kurtosis berechnen.

**DONE_100:**

- N, K, VIF, effektive Stichprobe, SR0, z und Phi sind reportierbar.
- Das Gate nutzt `N_raw`.
- Unvollständige Historie oder ungültige Statistik blockiert.

## Aufgabe 19 – Kausalen Multi-Timeframe-Feature-Store bauen

**Status:** `NOT_STARTED`

**Ziel:** Abgeschlossene 5m/15m/30m/1h/4h/1d-Features und Wochen-/Monatskontext fold-sicher bereitstellen.

**DONE_100:**

- Unfertige Bars sind unsichtbar.
- Normalisierung und Quantile werden ausschließlich im Fold-Training fitten.
- Warmup erzeugt kein Signal, Label oder PnL.

## Aufgabe 20 – Opportunity- und Regime-Schicht implementieren

**Status:** `NOT_STARTED`

**Ziel:** Bewegungskapazität, Trend, Range, Kompression und Stress kausal erkennen.

**DONE_100:**

- Regimegrenzen werden je Fold nur auf Training gelernt.
- Keine zukünftige MFE/MAE wird Feature.
- Unbekanntes oder widersprüchliches Regime führt zu `NO_TRADE`.

## Aufgabe 21 – Lokale Spezialisten hinter der bestehenden Engine bauen

**Status:** `NOT_STARTED`

**Ziel:** Pullback/Reclaim, Breakout/Retest, bestätigte Range-Reversion und Mehrtagesswing als kleine Challenger-Familien integrieren.

**DONE_100:**

- Vorhandene Familien und dieselbe Simulationsengine werden wiederverwendet.
- Entry, Stop, TP, Trail, Time-Exit, Tradezahl und Haltedauer sind vorab begrenzt.
- Jeder Spezialist hat klare Ablehnungsgründe und lokale Development-Evidenz.

## Aufgabe 22 – Router, NO_TRADE und FrozenCandidateBundle verbinden

**Status:** `NOT_STARTED`

**Ziel:** Router, Spezialisten, Fit-State und Ausführungsvertrag als gehashtes Bundle einfrieren.

**DONE_100:**

- Router wählt einen Spezialisten oder `NO_TRADE`.
- Maximal ein Lot insgesamt.
- Bundle enthält Parameter, Quantile, Scaler, Features, Kontext, Kosten, Rotation und Gültigkeit.

## Aufgabe 23 – Zwölf äußere Monats-Origins orchestrieren

**Status:** `NOT_STARTED`

**Ziel:** Die unveränderte Auswahlpipeline an jeder Origin vollständig auf den vorherigen 730 Tagen neu ausführen.

**DONE_100:**

- Zwölf unterschiedliche Fit-Stichtage und genau ein Bundle oder `NO_TRADE` je Origin.
- OOS-Ergebnisse bleiben für spätere Fits unsichtbar.
- 365 Tage werden lückenlos und duplikatfrei verkettet.

## Aufgabe 24 – 24h-Aktivierung und Outer-Rotation-State

**Status:** `NOT_STARTED`

**Ziel:** Alte Exitlogik und neue wartende Entrylogik deterministisch über Monatsgrenzen führen.

**DONE_100:**

- Neue Entries frühestens `T+24h` und nach `flat_time`.
- Altes Bundle ist exit-only.
- Rotation-State ist versioniert, hashbar und resume-fähig.

## Aufgabe 25 – Tägliches MTM-Ledger und zwei Zeitaggregationen

**Status:** `NOT_STARTED`

**Ziel:** Deployment-Intervalle und UTC-Kalenderperioden ohne Doppelzählung getrennt auswerten.

**DONE_100:**

- Tägliche Netto-MTM-Reihe enthält alle Nulltage.
- Closed-Trade-PnL wird dem Exit, Kosten dem Ausführungstag zugeordnet.
- Deployment-Intervalle, Monate und Quartale werden getrennt reportiert.

## Aufgabe 26 – Monthly Quality Gate, Stress und Pflichtmetriken

**Status:** `NOT_STARTED`

**Ziel:** `monthly_quality_gate_v1` ergänzend zum unveränderten Quality-Gate-v1 umsetzen.

**DONE_100:**

- Innere, Outer-, Kalender-, Konzentrations-, Stress-, Nachbarschafts-, Regime-, DSR/PBO- und Integritätsgates sind vollständig.
- Fehlende Evidenz besteht kein Trading-Gate.
- Gates sind vor dem Lauf eingefroren und nicht aus Outer-Ergebnissen änderbar.

## Aufgabe 27 – Hindsight-Benchmarks, Capture-Ratios und Bootstrap

**Status:** `NOT_STARTED`

**Ziel:** Historische Zielerreichung ehrlich von frischer statistischer Unterstützung trennen.

**DONE_100:**

- Hindsight-Solver bleibt reine nachgelagerte Diagnostik.
- Capture-Ratios und Overfit-Sperren sind umgesetzt.
- Stationary Bootstrap 5/10/20 mit 10.000 Replikationen ist reproduzierbar.
- Verbrauchte Historie kann nie `statistically_supported=true` setzen.

## Aufgabe 28 – Aktuellen 730-Tage-Refit und Champion/Challenger/Cash-Entscheidung

**Status:** `NOT_STARTED`

**Ziel:** Für den nächsten Anker deterministisch Bundle oder `NO_TRADE` einfrieren.

**DONE_100:**

- Fenster exakt `[T-730,T)`.
- Report enthält Gültigkeit, Hashes, Bundle, Vorgänger, Wechselgrund und Stressstatus.
- Bis zur frischen Evidenz bleibt das Ergebnis `diagnostic_only`.

## Aufgabe 29 – Orderfreien Research-Challenger-Shadow bauen

**Status:** `NOT_STARTED`

**Ziel:** Retrospektive Challenger strikt getrennt vom kanonischen Adoption-Shadow virtuell beobachten.

**DONE_100:**

- Eigener Reporttyp, Storage-Root, Controller, Aktion und Forward-Ledger.
- Keine Orders, Trading-API, privaten Endpunkte, Kontodaten oder API-Keys.
- `adopt_for_shadow` kann den Challenger nicht annehmen.

## Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Status:** `NOT_STARTED`

**Ziel:** Origins, Folds, Fortschritt, Safety, Ergebnisbedeutung und manuelle Challenger-Aktion korrekt anzeigen.

**DONE_100:**

- Keine vorzeitig sichtbare Outer-PnL.
- Bestehende Start/Pause/Fortsetzen/Abbruch/Neustart/Reset/Datenprüfung bleiben funktionsfähig.
- Paper, Testtrade, Live und Orders bleiben sichtbar gesperrt.

## Aufgabe 31 – Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr

**Status:** `NOT_STARTED`

**Ziel:** Die monatlich refittende Pipeline in einem vorab registrierten neuen 365-Tage-Fenster genau einmal final prüfen.

**DONE_100:**

- Alle zwölf Refits verwenden nur damals bekannte Daten.
- Zwischenresultate bleiben bis Tag 365 verborgen.
- Sichtbare Forward-Monate können nicht nachregistriert werden.
- Nur dieser Pfad kann einen Protocol-v3-Finalreport erzeugen.

## Aufgabe 32 – End-to-End-Parität, Fehler-Injektion und vollständige Abnahme

**Status:** `NOT_STARTED`

**Ziel:** Die gesamte Pipeline vor dem langen Lauf technisch beweisen.

**DONE_100:**

- Research, Replay, Cache, Resume und Challenger entscheiden bitgleich.
- Fehler-Injektionen decken Datenlücken, Hashmismatch, Abbruch, Lock, beschädigte Artefakte, Kontextversatz, Boundary und Rotation ab.
- Fixture-basierter 12-Origin-Dry-Run ist vollständig reproduzierbar.

## Aufgabe 33 – Erster vollständiger Protocol-v3-Research-Lauf und Abschlussbericht

**Status:** `NOT_STARTED`

**Ziel:** Erst nach Aufgaben 1–32 den realen historischen Monatsprozess unverändert ausführen und auswerten.

**DONE_100:**

- Alle zwölf Origins und 365 OOS-Tage sind ehrlich und einmalig verarbeitet.
- Lauf ist reproduzierbar fortsetzbar und erzeugt kompakte digest-gebundene Artefakte.
- Bericht beantwortet die sieben Erfolgsfragen des Blueprints.
- Ergebnis lautet ehrlich `TARGET_REACHED`, `TARGET_NOT_REACHED` oder `NO_EDGE_FOUND`.

## Fortschrittsführung

Kanonische Statuszeile:

```text
Protocol v3: Aufgabe X/33 – <Titel> – NOT_STARTED | IN_PROGRESS | BLOCKED | DONE_100
```

Aktueller Stand:

```text
Protocol v3: Aufgabe 2/33 – Monatskalender und Boundary-Vertrag implementieren – DONE_100
Protocol v3: Aufgabe 3/33 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren – NOT_STARTED
Gesamt: 2/33 DONE_100 = 6,06 %
```

Nach jeder Aufgabe werden ausschließlich der abgeschlossene Schritt und die exakt nächste Aufgabe freigegeben. Fortschritt wird nicht nach Zeit oder Token geschätzt, sondern als `DONE_100 / 33` ausgewiesen.
