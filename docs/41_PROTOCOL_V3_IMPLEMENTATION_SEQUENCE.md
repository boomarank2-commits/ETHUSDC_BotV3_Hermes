# Protocol v3 – verbindliche Implementierungsreihenfolge

Stand: 2026-07-14
Quelle: `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 3/33 abgeschlossen

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

**Abnahme:** Evidenzklassen und Rolling-Reuse sind eindeutig; verbrauchter Audit bleibt `NOT_FRESH`; Legacy-Pfade können keinen Protocol-v3-Finalstatus erzeugen; Widersprüche blockieren fail-closed.

**Bericht:** `handoff/PROTOCOL_V3_TASK_01_2026-07-13.md`

## Aufgabe 2 – Monatskalender und Boundary-Vertrag implementieren

**Status:** `DONE_100`

**Ziel:** Exakt zwölf äußere Origins, 730 Entwicklungstage je Origin, 365 lückenlose Prozess-OOS-Tage und feste `T+24h`-Aktivierung als reine Boundary-Schicht implementieren.

**Abnahme:** UTC, Ankertag 8, synthetisches `b0`, `as_of_day`, `valid_from`, `valid_until`, Late-Button-Regel und Fail-closed-Grenzprüfung sind umgesetzt; Leap-/Non-Leap-Fixtures sind grün; Protocol v2 blieb unverändert.

**Bericht:** `handoff/PROTOCOL_V3_TASK_02_2026-07-14.md`

## Aufgabe 3 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren

**Status:** `DONE_100`

**Ziel:** Jede inhaltliche Pipelineversion besitzt eine unveränderliche Identität und vorab festgelegte Suchgrenzen.

**Abnahme:**

- Pipelinegeneration bindet Feature-, Familien-, Kontext-, Suchraum-, Ranking-, Gate-, Kosten-, Simulator-, Boundary- und Identitätsquellen per SHA-256.
- Ein timestamp-freies kanonisches Pre-Run-Manifest bindet Git-Commit, Pipelinegeneration und Task-2-Boundary-Plan.
- Seeds entstehen deterministisch als unsigned 64 Bit aus Manifest plus Origin/Cycle/Stage-Namespace.
- Grenzen 12 Origins, 8 Cycles, 40/12/3/2 und globale Maxima 96/3840/1152/288/192 sind technisch unüberschreitbar.
- `selection_stagnation_3_cycles` kann nur verkürzen und niemals Budgets erweitern; das 3-USDC-Ziel ist keine Stopregel.
- Eine neue Generation erhält nur einen neuen Forward-Ledger-Namespace; der permanente Trial-Counter bleibt generationsübergreifend.

**Bericht:** `handoff/PROTOCOL_V3_TASK_03_2026-07-14.md`

## Aufgabe 4 – Permanentes Trial-Ledger und historischen Import bauen

**Status:** `NOT_STARTED` – exakt nächste Aufgabe

**Ziel:** Jeden dateninformierten Versuch append-only und generationsübergreifend erfassen.

**DONE_100:**

- Deterministische Trial-ID, Kandidat, Parameter, Featurevariante, Seed, Ranking-/Gate-Version, Codehash und kausale Tagesreihe werden gespeichert.
- Cache-Hits bleiben als Wiederverwendung sichtbar und werden nicht als unabhängiger neuer Versuch gezählt.
- Rekonstruierbare historische Trials werden importiert und mit `historical_trial_count_is_lower_bound=true` markiert.
- Unvollständige Trial-Historie oder fehlende Tagesreihen erzwingen `DSR=INSUFFICIENT_TRIAL_HISTORY`; nur `NO_TRADE` ist dann freigabefähig.
- Ein bewerteter Trial kann weder gelöscht noch unprotokolliert verändert werden.

## Aufgabe 5 – Dynamischen Drei-Markt-Datensnapshot und Warmup herstellen

**Status:** `NOT_STARTED`

**Ziel:** Gemeinsamen letzten vollständigen UTC-Tag und erforderlichen Warmup für ETHUSDC, BTCUSDC und ETHBTC dynamisch bestimmen und einfrieren.

**DONE_100:** Kein Produktions-Hardcode auf `2026-07-07`; Watermark, 1.440-Minuten-Raster, Duplikate, Lücken, OHLC und Nullvolumen geprüft; Warmup aus aktiven Lookbacks; fehlender Markt blockiert.

## Aufgabe 6 – Exchange-Info-Snapshot und vollständige Run-Fingerprints bauen

**Status:** `NOT_STARTED`

**Ziel:** Binance-Filter und sämtliche Laufidentitäten versioniert und resume-sicher binden.

**DONE_100:** PRICE_FILTER, LOT_SIZE/MARKET_LOT_SIZE und MIN_NOTIONAL/NOTIONAL versioniert; Fingerprints binden alle Daten-, Code-, Pipeline-, Feature-, Kontext-, Gate-, Kosten-, Simulator-, Boundary-, Trial- und Exchange-Info-Identitäten; Änderungen verhindern Resume/Cache-Hit.

## Aufgabe 7 – Notional-, Mengen-, Gebühren- und Rundungsparität herstellen

**Status:** `NOT_STARTED`

**Ziel:** Das 100-USDC-Lot realistisch gemäß Produktvertrag und Exchange-Filtern simulieren.

**DONE_100:** Angefordertes, reserviertes und ausgeführtes Notional getrennt; Step-Size-Abrundung und Filter; Gebühren auf tatsächlichem Notional; Verkauf exakt der gekauften Menge; Golden Trades bitgleich.

## Aufgabe 8 – Next-Tradable-Price und pessimistische Intrabar-Ausführung

**Status:** `NOT_STARTED`

**Ziel:** Signal-, Entry-, Stop-, TP-, Trail-, Gap- und Time-Exit-Reihenfolge realistisch festlegen.

**DONE_100:** Entry frühestens nach abgeschlossener Signalbar; Stop gewinnt bei gleicher 1m-Kerze; Gaps zum schlechteren Preis; keine perfekten Extremfills; Basis und Stress nutzen dieselbe Engine.

## Aufgabe 9 – Warmup-, Purge-, Fold-End- und Outer-State-Maschine

**Status:** `NOT_STARTED`

**Ziel:** Informationsintervalle, Pending Entry, Cooldown, offene Position und Modellwechsel kausal behandeln.

**DONE_100:** Purge aus maximalem Horizont; innere Folds flat mit konservativem Ende; zwischen Origins nur offene Altposition mit alter Exitlogik; alte Konfiguration exit-only, neue wartet auf `valid_from` und `flat_time`.

## Aufgabe 10 – Kontextparität und Drei-Markt-Watermark

**Status:** `NOT_STARTED`

**Ziel:** Kontext in Research, Replay, Finalpfad und Challenger identisch als reines Veto/Bestätigung verwenden.

**DONE_100:** Nur drei ausgerichtete geschlossene Bars; fehlende/stale Daten blockieren; BTCUSDC/ETHBTC können nie handeln; Kontextidentität in Fingerprints/Cache-Keys.

## Aufgabe 11 – Protocol-v3-Report-Schemas und Evidenzbedeutung

**Status:** `NOT_STARTED`

**Ziel:** Research-, Monatsprozess-, Challenger-, Forward- und Pipeline-Finalberichte getrennt versionieren.

**DONE_100:** Eigene Schemas/Storage-Roots; Freshness, historische Zielerreichung, statistische Unterstützung und Adoption nicht falsch setzbar; sichtbare Forward-Monate nie nachträglich Finalfenster.

## Aufgabe 12 – Kompakte Artefaktarchitektur

**Status:** `NOT_STARTED`

**Ziel:** Zwölf Monatsrefits ohne mehrfach eingebettete Großartefakte speicher- und lesbar machen.

**DONE_100:** Kleiner Index; deduplizierte Trade-, Daily-PnL-, Equity- und Diagnostikartefakte; Digest/Schema/Provenienz; Größenbudgets; UI liest nur kleine Statusartefakte.

## Aufgabe 13 – Content-addressed Cache und transaktionales Resume

**Status:** `NOT_STARTED`

**Ziel:** Abbruch, Neustart und Cache-Wiederverwendung dürfen keine Entscheidung verändern.

**DONE_100:** Cache-Key bindet alle Identitäten; Checkpoint bindet Code, Snapshot, Exchange Info, Pipeline, Trial-Head, Origins, Rotation und Store-Head; Atomic Replace, Lock und Digestprüfung verhindern Teilstände/Doppelungen; Resume bitgleich.

## Aufgabe 14 – Exakten inneren 6×60-Tage-Fold-Planer bauen

**Status:** `NOT_STARTED`

**Ziel:** Sechs nicht überlappende Validation-Folds auf den letzten 360 Entwicklungstagen bilden.

**DONE_100:** Blueprint-Boundaries exakt; Fits wachsen ab 370 Tagen vor Purging in 60-Tage-Schritten; Timestamp-Spies beweisen keine Validation-/Outer-Sicht; fehlende Raster blockieren.

## Aufgabe 15 – Reine innere Auswahlfunktion extrahieren

**Status:** `NOT_STARTED`

**Ziel:** `select_candidate(training_window, frozen_pipeline_config)` deterministisch und ohne UI-/Laufzeitabhängigkeit bereitstellen.

**DONE_100:** Kein Zugriff nach `training_end`; gleiche Inputs/Hashes gleiche Auswahl; vorhandene Engine und 40/12/3/2 wiederverwendet; Fehler/fehlende Evidenz liefern `NO_TRADE`.

## Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets

**Status:** `NOT_STARTED`

**Ziel:** Allen zwölf getesteten Profilen dieselbe 360-Tage-OOS-Basisreihe geben.

**DONE_100:** Netto-MTM inklusive Nulltage; Cash als Nullbaseline; Promotion 12 → 3 → 2 nachvollziehbar und budgetfest; jeder datenbewertete Kandidat im Trial-Ledger.

## Aufgabe 17 – PBO/CSCV exakt implementieren

**Status:** `NOT_STARTED`

**Ziel:** `development_pbo` nach 12 Blöcken und 924 Splits berechnen.

**DONE_100:** IS-Ties, OOS-Ränge, Omega, Lambda und PBO vertragsgemäß; unvollständige/ungleiche Reihen liefern `INSUFFICIENT_EVIDENCE`; keine Outer-Rückkopplung.

## Aufgabe 18 – DSR und Multiple-Testing-Diagnostik implementieren

**Status:** `NOT_STARTED`

**Ziel:** DSR mit permanenten Trials, Autokorrelation, Schiefe und Kurtosis berechnen.

**DONE_100:** N, K, VIF, effektive Stichprobe, SR0, z und Phi reportierbar; Gate nutzt `N_raw`; unvollständige Historie oder ungültige Statistik blockiert; WRC/SPA getrennte Warnleuchte.

## Aufgabe 19 – Kausalen Multi-Timeframe-Feature-Store bauen

**Status:** `NOT_STARTED`

**Ziel:** Abgeschlossene 5m/15m/30m/1h/4h/1d-Features und Wochen-/Monatskontext fold-sicher bereitstellen.

**DONE_100:** Unfertige Bars unsichtbar; Normalisierung/Quantile nur Fold-Training; Feature-State hashbar/replaybar; Warmup ohne Signal/Label/PnL; Leakage-Tests grün.

## Aufgabe 20 – Opportunity- und Regime-Schicht implementieren

**Status:** `NOT_STARTED`

**Ziel:** Bewegungskapazität, Trend, Range, Kompression und Stress kausal erkennen.

**DONE_100:** Regimegrenzen nur Fold-Training; Entscheidungen erklärbar; keine zukünftige MFE/MAE; unbekanntes Regime führt `NO_TRADE`.

## Aufgabe 21 – Lokale Spezialisten hinter der bestehenden Engine bauen

**Status:** `NOT_STARTED`

**Ziel:** Pullback/Reclaim, Breakout/Retest, bestätigte Range-Reversion und Mehrtagesswing als kleine Challenger-Familien integrieren.

**DONE_100:** Vorhandene Familien/Engine wiederverwendet; Entry/Stop/TP/Trail/Time-Exit/Tradezahl/Haltedauer begrenzt; Signal-Funnel/Ablehnungsgründe; lokale Development-Evidenz Pflicht.

## Aufgabe 22 – Router, NO_TRADE und FrozenCandidateBundle verbinden

**Status:** `NOT_STARTED`

**Ziel:** Router, Spezialisten, Fit-State und Ausführungsvertrag als gehashtes Bundle einfrieren.

**DONE_100:** Router wählt Spezialist oder `NO_TRADE`; maximal ein Lot; Bundle enthält Parameter, Quantile, Scaler, Features, Kontext, Kosten, Rotation und Gültigkeit; jede Entscheidung rückführbar.

## Aufgabe 23 – Zwölf äußere Monats-Origins orchestrieren

**Status:** `NOT_STARTED`

**Ziel:** Die unveränderte Auswahlpipeline an jeder Origin vollständig auf den vorherigen 730 Tagen neu ausführen.

**DONE_100:** Zwölf Fit-Stichtage und genau ein Bundle/`NO_TRADE` je Origin; OOS späteren Fits unsichtbar; 365 Tage lückenlos/duplikatfrei; Origin-Fehler führt `NO_TRADE`.

## Aufgabe 24 – 24h-Aktivierung und Outer-Rotation-State

**Status:** `NOT_STARTED`

**Ziel:** Alte Exitlogik und neue wartende Entrylogik deterministisch über Monatsgrenzen führen.

**DONE_100:** Neue Entries frühestens `T+24h` und nach `flat_time`; altes Bundle exit-only; Rotation-State versioniert/hashbar/resume-fähig; keine Doppelentries.

## Aufgabe 25 – Tägliches MTM-Ledger und zwei Zeitaggregationen

**Status:** `NOT_STARTED`

**Ziel:** Deployment-Intervalle und UTC-Kalenderperioden ohne Doppelzählung getrennt auswerten.

**DONE_100:** Daily MTM inklusive Nulltage; Trade-PnL dem Exit und Kosten dem Ausführungstag; Intervalle/Monate/Quartale getrennt; Grenzpositionen genau einmal; Konsistenztests.

## Aufgabe 26 – Monthly Quality Gate, Stress und Pflichtmetriken

**Status:** `NOT_STARTED`

**Ziel:** `monthly_quality_gate_v1` ergänzend zum unveränderten Quality-Gate-v1 umsetzen.

**DONE_100:** Alle inneren/Outer/Kalender/Konzentrations/Stress/Nachbarschaft/Regime/DSR/PBO/Integritätsgates; fehlende Evidenz besteht nicht; Grün/Gelb/Rot ehrlich; Gates vor Lauf eingefroren.

## Aufgabe 27 – Hindsight-Benchmarks, Capture-Ratios und Bootstrap

**Status:** `NOT_STARTED`

**Ziel:** Historische Zielerreichung ehrlich von frischer statistischer Unterstützung trennen.

**DONE_100:** Hindsight-Solver reine Diagnostik; Capture-Ratios/Overfit-Sperren; Stationary Bootstrap 5/10/20 mit 10.000 Replikationen reproduzierbar; verbrauchte Historie nie `statistically_supported=true`.

## Aufgabe 28 – Aktuellen 730-Tage-Refit und Champion/Challenger/Cash-Entscheidung

**Status:** `NOT_STARTED`

**Ziel:** Für den nächsten Anker deterministisch Bundle oder `NO_TRADE` einfrieren.

**DONE_100:** Fenster `[T-730,T)`; Report mit Gültigkeit/Hashes/Bundle/Vorgänger/Wechselgrund/Stress; Champion/Challenger/Cash deterministisch; bis frische Evidenz `diagnostic_only`; keine Rückdatierung.

## Aufgabe 29 – Orderfreien Research-Challenger-Shadow bauen

**Status:** `NOT_STARTED`

**Ziel:** Retrospektive Challenger strikt getrennt vom kanonischen Adoption-Shadow virtuell beobachten.

**DONE_100:** Eigener Reporttyp/Storage/Controller/Aktion/Forward-Ledger; keine Orders/API/Kontodaten/Keys; Drei-Markt-Parität; Lücken/Hashabweichung blockieren; `adopt_for_shadow` kann ihn nicht annehmen.

## Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Status:** `NOT_STARTED`

**Ziel:** Origins, Folds, Fortschritt, Safety, Ergebnisbedeutung und manuelle Challenger-Aktion korrekt anzeigen.

**DONE_100:** Keine vorzeitige Outer-PnL; vorhandene Bedienbuttons funktionieren; Ergebnis/Freshness/Champion sichtbar; Paper/Testtrade/Live/Orders gesperrt; Refresh zustandsneutral.

## Aufgabe 31 – Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr

**Status:** `NOT_STARTED`

**Ziel:** Die monatlich refittende Pipeline in einem vorab registrierten neuen 365-Tage-Fenster genau einmal final prüfen.

**DONE_100:** Zwölf kausale Refits; Zwischenresultate bis Tag 365 verborgen; sichtbare Forward-Monate nicht nachregistrierbar; nur dieser Pfad erzeugt Protocol-v3-Finalreport.

## Aufgabe 32 – End-to-End-Parität, Fehler-Injektion und vollständige Abnahme

**Status:** `NOT_STARTED`

**Ziel:** Die gesamte Pipeline vor dem langen Lauf technisch beweisen.

**DONE_100:** Research/Replay/Cache/Resume/Challenger bitgleich; Fehler-Injektionen vollständig; alle Tests grün; fixture-basierter 12-Origin-Dry-Run reproduzierbar; keine offene P0-Abweichung.

## Aufgabe 33 – Erster vollständiger Protocol-v3-Research-Lauf und Abschlussbericht

**Status:** `NOT_STARTED`

**Ziel:** Erst nach Aufgaben 1–32 den realen historischen Monatsprozess unverändert ausführen und auswerten.

**DONE_100:** Alle zwölf Origins und 365 OOS-Tage einmalig; reproduzierbar fortsetzbar; kompakte digest-gebundene Artefakte; sieben Erfolgsfragen beantwortet; ehrliches `TARGET_REACHED`, `TARGET_NOT_REACHED` oder `NO_EDGE_FOUND`.

## Fortschrittsführung

Kanonische Statuszeile:

```text
Protocol v3: Aufgabe X/33 – <Titel> – NOT_STARTED | IN_PROGRESS | BLOCKED | DONE_100
```

Aktueller Stand:

```text
Protocol v3: Aufgabe 3/33 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren – DONE_100
Protocol v3: Aufgabe 4/33 – Permanentes Trial-Ledger und historischen Import bauen – NOT_STARTED
Gesamt: 3/33 DONE_100 = 9,09 %
```

Nach jeder Aufgabe werden ausschließlich der abgeschlossene Schritt und die exakt nächste Aufgabe freigegeben. Fortschritt wird nicht nach Zeit oder Token geschätzt, sondern als `DONE_100 / 33` ausgewiesen.
