# Protocol v3 – verbindliche Implementierungsreihenfolge

Stand: 2026-07-14
Quelle: `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 7/33 abgeschlossen

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
- Der reine 12-Origin-Prozess erzwingt maximal 96 Cycles und 3.840/1.152/288/192 Stufenreservierungen.
- Die gebundene globale Hülle ergänzt genau einen aktuellen Refit und erzwingt insgesamt 104/4.160/1.248/312/208.
- `selection_stagnation_3_cycles` kann nur verkürzen und niemals Budgets erweitern; das 3-USDC-Ziel ist keine Stopregel.
- Eine neue Generation erhält nur einen neuen Forward-Ledger-Namespace; der permanente Trial-Counter bleibt generationsübergreifend.

**Berichte:**

- `handoff/PROTOCOL_V3_TASK_03_2026-07-14.md`
- `handoff/PROTOCOL_V3_TASK_03_BUDGET_CORRECTION_2026-07-14.md`

## Aufgabe 4 – Permanentes Trial-Ledger und historischen Import bauen

**Status:** `DONE_100`

**Ziel:** Jeden dateninformierten Versuch append-only und generationsübergreifend erfassen.

**Abnahme:**

- Deterministische Trial-ID bindet Kandidat, Parameter, Featurevariante, Seed, Ranking-/Gate-/Simulator-/Kosten-/Boundary-Version, Codehash, Scope und kausale Tagesreihe.
- Hashverkettete, sequenzierte Eventdateien plus digest-gebundener Head erkennen Mutation, Löschung, Lücke, Umbenennung und gebrochene Kette.
- Manuelle Änderungen nach Ergebnissicht zählen als eigener Trial.
- Cache-Hits und byte-identische Reportkopien bleiben sichtbare Wiederverwendung und zählen nicht als unabhängiger Trial.
- Protocol-v2- und ältere Research-Reports können nur mit rekonstruierbarer Identität importiert werden; fehlende Felder werden nicht erfunden.
- Der belegbare Altbestand bleibt ehrlich `historical_trial_count_is_lower_bound=true`: 180 bekannte Bewertungszeilen, aber derzeit 0 vollständig aufgelöste unabhängige Alt-Trials.
- Unvollständige Historie oder fehlende Tagesreihen erzwingen `development_dsr_status=INSUFFICIENT_TRIAL_HISTORY`; nur `NO_TRADE` ist freigabefähig.
- Eine spätere Completion erfordert vollständiges Mapping aller historischen Zeilen, Duplikat-/Cache-Reconciliation, alle kausalen Tagesreihen und kombinierte SHA-256-Attestierung.
- Keine DSR- oder PBO-Berechnung wurde vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_04_2026-07-14.md`

## Aufgabe 5 – Dynamischen Drei-Markt-Datensnapshot und Warmup herstellen

**Status:** `DONE_100`

**Ziel:** Gemeinsamen letzten vollständigen UTC-Tag und erforderlichen Warmup für ETHUSDC, BTCUSDC und ETHBTC dynamisch bestimmen und einfrieren.

**Abnahme:**

- Kein Produktions-Hardcode auf `2026-07-07` oder einen anderen festen Datenendtag bleibt.
- Die Watermark ist der neueste in allen drei Märkten vollständig auditierte UTC-Tag; das Prozessende folgt ausschließlich der Task-2-Ankerregel.
- Jeder Pflicht-UTC-Tag besitzt exakt 1.440 fortlaufende 1m-Kerzen ohne Duplikate oder Lücken und mit endlichen, positiven und konsistenten OHLC-Werten.
- Einzelne Nullvolumenkerzen werden gezählt und sichtbar gemacht; ein vollständiger Nullvolumentag blockiert.
- `warmup_duration = max(alle aktiven ETH-/BTC-/ETHBTC-Lookbacks) + 1 kleinste Quellbar` ist technisch erzwungen.
- Die aktive Lookback-Menge muss alle drei Märkte enthalten; fehlender Warmup oder ein unvollständiger Markt blockiert.
- Warmup darf Features speisen, aber niemals Scaler, Quantile, Regimefits, Labels oder PnL.
- Der immutable Snapshot bindet Vertrag, Watermark, Task-2-Grenzen, Warmup, Rohintervall, Marktrollen, Tagesbestand sowie Zeitraster-, Marktinhalt- und ZIP-/CHECKSUM-Digests.
- Der bekannte aktuelle 1.095-Tage-Bestand bleibt ehrlich `BLOCKED_MISSING_WARMUP`, bis in allen drei Märkten zusätzliche vollständige Historie vor D1 vorhanden ist.

**Bericht:** `handoff/PROTOCOL_V3_TASK_05_2026-07-14.md`

## Aufgabe 6 – Exchange-Info-Snapshot und vollständige Run-Fingerprints bauen

**Status:** `DONE_100`

**Ziel:** Binance-Filter und sämtliche Laufidentitäten versioniert und resume-sicher binden.

**Abnahme:**

- Ein öffentlicher, unveränderlicher ETHUSDC-Exchange-Info-Snapshot bindet `PRICE_FILTER`, `LOT_SIZE`, `MARKET_LOT_SIZE` sowie mindestens `MIN_NOTIONAL` oder `NOTIONAL`; beide werden erhalten, wenn Binance beide liefert.
- Status, ETH/USDC-Assets, Spot-Freigabe, kanonische Dezimalwerte, Herkunft, Zeitpunkt und Safety sind SHA-256-gebunden; private oder kontobezogene Daten blockieren.
- Der timestamp-freie Run-Fingerprint bindet Rohdaten, Stichtag, Git-Commit, Pipeline, Features, Kontext, Gates, Kosten, Simulator, Boundary, Trial-Ledger-Head und Exchange Info.
- Drei-Markt-Raster-, Inhalts-, Archiv- und Tagesdigests bleiben Bestandteil der Rohdatenidentität.
- `resume_key` und `cache_key` sind derselbe content-addressed Fingerprint; jede Änderung einer der zwölf Identitätsklassen verhindert Resume und Cache-Hit.
- Exchange-Info- und Fingerprint-Artefakte sind create-only und werden semantisch sowie per Digest revalidiert.
- Der Identity-Vertrag und die Implementierung sind an die Pipelinegeneration gebunden; der permanente Trial-Counter wird nicht zurückgesetzt.
- Keine Mengenrundung, Gebühren-, Notional- oder Simulatorparität aus Aufgabe 7 wurde vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_06_2026-07-14.md`

## Aufgabe 7 – Notional-, Mengen-, Gebühren- und Rundungsparität herstellen

**Status:** `DONE_100`

**Ziel:** Das 100-USDC-Lot realistisch gemäß Produktvertrag und Exchange-Filtern simulieren.

**Abnahme:**

- Das logische Lot berichtet `requested_entry_notional_usdc=100`, `reserved_entry_notional_usdc=100` und ein separat berechnetes `executed_entry_notional_usdc<=100`.
- Die Menge wird mit exakter Decimal-Arithmetik ausschließlich nach unten auf den gemeinsamen positiven `LOT_SIZE`-/`MARKET_LOT_SIZE`-Raster abgerundet.
- Gemeinsame Min-/Max-Mengengrenzen und anwendbare `MIN_NOTIONAL`-/`NOTIONAL`-Grenzen werden für Entry und Exit fail-closed geprüft.
- Entry-Fee basiert auf dem tatsächlich ausgeführten Entry-Notional; Exit-Fee basiert auf dem tatsächlichen Exit-Notional und wird jeweils zusätzlich verbucht.
- Der Exit verwendet exakt die gekaufte Entry-Menge; eine zweite Mengenrundung ist ausgeschlossen.
- Single-Position- und Portfolio-/Shadow-Pfad verwenden dieselbe Task-7-Repricing- und MTM-Logik; gemeinsame Golden-Trade-Felder sind bitgleich.
- Sequentielle Trades verwenden unverändert jeweils 100 USDC requested/reserved; Compounding bleibt aus.
- Kosten- und Simulatorvertrag sowie neue Ausführungsquellen sind an Pipelinegeneration und Run-Fingerprint gebunden.
- Tick-Rundung, Next-Tradable-Price, Intrabar-Priorität und Gap-Fills aus Aufgabe 8 wurden nicht vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_07_2026-07-14.md`

## Aufgabe 8 – Next-Tradable-Price und pessimistische Intrabar-Ausführung

**Status:** `NOT_STARTED` – exakt nächste Aufgabe

**Ziel:** Signal-, Entry-, Stop-, TP-, Trail-, Gap- und Time-Exit-Reihenfolge realistisch festlegen.

**DONE_100:** Entry frühestens nach abgeschlossener Signalbar; Stop gewinnt bei Berührung in derselben 1m-Kerze; Gaps füllen zum schlechteren Preis; perfekte Extremfills sind ausgeschlossen; Basis und Stress verwenden dieselbe Engine.

## Aufgabe 9 – Warmup-, Purge-, Fold-End- und Outer-State-Maschine

**Status:** `NOT_STARTED`

**Ziel:** Informationsintervalle, Pending Entry, Cooldown, offene Position und Modellwechsel kausal behandeln.

**DONE_100:** Purge folgt maximalem Horizont plus Latenz und Ausführungsbar; innere Folds starten flat und liquidieren konservativ; zwischen Origins wird nur eine offene Altposition mit alter Exitlogik übertragen; alte Konfiguration ist exit-only, neue wartet auf `valid_from` und `flat_time`.

## Aufgabe 10 – Kontextparität und Drei-Markt-Watermark

**Status:** `NOT_STARTED`

**Ziel:** Kontext in Research, Replay, Finalpfad und Challenger identisch als reines Veto/Bestätigung verwenden.

**DONE_100:** Zeitpunkt `t` wird nur mit drei ausgerichteten geschlossenen Bars verarbeitet; fehlende, versetzte oder stale Daten blockieren; BTCUSDC und ETHBTC können nie handeln; Kontextidentität ist Bestandteil aller Fingerprints und Cache-Keys.

## Aufgabe 11 – Protocol-v3-Report-Schemas und Evidenzbedeutung

**Status:** `NOT_STARTED`

**Ziel:** Research-, Monatsprozess-, Challenger-, Forward- und Pipeline-Finalberichte getrennt versionieren.

**DONE_100:** Eigene Schemas und Storage-Roots verhindern Legacy-Verwechslung; Freshness, historische Zielerreichung, statistische Unterstützung und Adoption können nicht falsch gesetzt werden; sichtbare Forward-Monate können nie nachträglich Finalfenster werden.

## Aufgabe 12 – Kompakte Artefaktarchitektur

**Status:** `NOT_STARTED`

**Ziel:** Zwölf Monatsrefits ohne mehrfach eingebettete Großartefakte speicher- und lesbar machen.

**DONE_100:** Kleiner JSON-Index; getrennte deduplizierte Trade-, Daily-PnL-, Equity- und Diagnostikartefakte; Referenzen besitzen Digest, Schema und Provenienz; Größenbudgets werden geprüft; UI liest nur kleine Statusartefakte.

## Aufgabe 13 – Content-addressed Cache und transaktionales Resume

**Status:** `NOT_STARTED`

**Ziel:** Abbruch, Neustart und Cache-Wiederverwendung dürfen keine Entscheidung verändern.

**DONE_100:** Cache-Key bindet alle Daten-, Kontext-, Feature-, Kandidaten-, Fold-, Boundary-, Execution-, Simulator- und Kostenidentitäten; Checkpoints binden Code, Snapshot, Exchange Info, Pipeline, Trial-Head, Origins, Rotation und Store-Head; Atomic Replace, Lock und Digestprüfung verhindern Teilstände und doppelte Origins.

## Aufgabe 14 – Exakten inneren 6×60-Tage-Fold-Planer bauen

**Status:** `NOT_STARTED`

**Ziel:** Sechs nicht überlappende Validation-Folds auf den letzten 360 Entwicklungstagen bilden.

**DONE_100:** Boundary-Objekte entsprechen exakt Blueprint Abschnitt 6.3; Fits wachsen ab 370 Tagen vor Purging in 60-Tage-Schritten; Timestamp-Spies beweisen, dass kein Fit Validation oder Outer-Test sieht; fehlende Raster blockieren.

## Aufgabe 15 – Reine innere Auswahlfunktion extrahieren

**Status:** `NOT_STARTED`

**Ziel:** `select_candidate(training_window, frozen_pipeline_config)` deterministisch und ohne UI-/Laufzeitabhängigkeit bereitstellen.

**DONE_100:** Kein Zugriff nach `training_end` und kein Outer-Ergebnis als Input; gleiche Inputs und Hashes erzeugen dieselbe Auswahl; vorhandene Engine und 40/12/3/2-Stufen werden wiederverwendet; Fehler oder fehlende Evidenz liefern `NO_TRADE`.

## Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets

**Status:** `NOT_STARTED`

**Ziel:** Allen zwölf getesteten Profilen dieselbe 360-Tage-OOS-Basisreihe geben.

**DONE_100:** Tägliche Netto-MTM-Reihe inklusive Nulltage je Profil; Cash als Nullbaseline; Promotion 12 Basisreihen → 3 Full-WFV → 2 Finalisten ist budgetfest; jeder datenbewertete Kandidat wird im Trial-Ledger gespeichert.

## Aufgabe 17 – PBO/CSCV exakt implementieren

**Status:** `NOT_STARTED`

**Ziel:** `development_pbo` nach 12 Blöcken und 924 Splits berechnen.

**DONE_100:** IS-Ties, OOS-Ränge, Omega, Lambda und PBO entsprechen dem Vertrag; unvollständige oder ungleiche Reihen liefern `INSUFFICIENT_EVIDENCE`; Outer-Ergebnisse werden nie zurückgespielt.

## Aufgabe 18 – DSR und Multiple-Testing-Diagnostik implementieren

**Status:** `NOT_STARTED`

**Ziel:** DSR mit permanenten Trials, Autokorrelation, Schiefe und Kurtosis berechnen.

**DONE_100:** N, K, VIF, effektive Stichprobe, SR0, z und Phi sind reportierbar; das Gate nutzt `N_raw`; unvollständige Historie oder ungültige Statistik blockiert; WRC/SPA bleibt getrennte Warnleuchte.

## Aufgabe 19 – Kausalen Multi-Timeframe-Feature-Store bauen

**Status:** `NOT_STARTED`

**Ziel:** Abgeschlossene 5m/15m/30m/1h/4h/1d-Features und Wochen-/Monatskontext fold-sicher bereitstellen.

**DONE_100:** Unfertige Bars sind unsichtbar; Normalisierung und Quantile werden ausschließlich im Fold-Training fitten; Feature-State ist hashbar und replaybar; Warmup erzeugt kein Signal, Label oder PnL; Leakage-Tests sind grün.

## Aufgabe 20 – Opportunity- und Regime-Schicht implementieren

**Status:** `NOT_STARTED`

**Ziel:** Bewegungskapazität, Trend, Range, Kompression und Stress kausal erkennen.

**DONE_100:** Regimegrenzen werden nur auf Fold-Training gelernt; Entscheidungen sind erklärbar; keine zukünftige MFE/MAE wird Feature; unbekanntes oder widersprüchliches Regime führt `NO_TRADE`.

## Aufgabe 21 – Lokale Spezialisten hinter der bestehenden Engine bauen

**Status:** `NOT_STARTED`

**Ziel:** Pullback/Reclaim, Breakout/Retest, bestätigte Range-Reversion und Mehrtagesswing als kleine Challenger-Familien integrieren.

**DONE_100:** Vorhandene Familien und dieselbe Simulationsengine werden wiederverwendet; Entry, Stop, TP, Trail, Time-Exit, Tradezahl und Haltedauer sind begrenzt; jeder Spezialist hat klare Ablehnungsgründe und lokale Development-Evidenz.

## Aufgabe 22 – Router, NO_TRADE und FrozenCandidateBundle verbinden

**Status:** `NOT_STARTED`

**Ziel:** Router, Spezialisten, Fit-State und Ausführungsvertrag als gehashtes Bundle einfrieren.

**DONE_100:** Router wählt genau einen Spezialisten oder `NO_TRADE`; maximal ein Lot insgesamt; Bundle enthält Parameter, Quantile, Scaler, Features, Kontext, Kosten, Rotation und Gültigkeit; jede Entscheidung ist rückführbar.

## Aufgabe 23 – Zwölf äußere Monats-Origins orchestrieren

**Status:** `NOT_STARTED`

**Ziel:** Die unveränderte Auswahlpipeline an jeder Origin vollständig auf den vorherigen 730 Tagen neu ausführen.

**DONE_100:** Zwölf Fit-Stichtage und genau ein Bundle oder `NO_TRADE` je Origin; OOS bleibt späteren Fits unsichtbar; 365 Tage sind lückenlos und duplikatfrei; Origin-Fehler führt `NO_TRADE`.

## Aufgabe 24 – 24h-Aktivierung und Outer-Rotation-State

**Status:** `NOT_STARTED`

**Ziel:** Alte Exitlogik und neue wartende Entrylogik deterministisch über Monatsgrenzen führen.

**DONE_100:** Neue Entries frühestens `T+24h` und nach `flat_time`; altes Bundle exit-only; Rotation-State versioniert, hashbar und resume-fähig; keine Doppelentries.

## Aufgabe 25 – Tägliches MTM-Ledger und zwei Zeitaggregationen

**Status:** `NOT_STARTED`

**Ziel:** Deployment-Intervalle und UTC-Kalenderperioden ohne Doppelzählung getrennt auswerten.

**DONE_100:** Daily MTM inklusive Nulltage; Trade-PnL dem Exit und Kosten dem Ausführungstag; Intervalle, Monate und Quartale getrennt; Grenzpositionen genau einmal; Konsistenztests grün.

## Aufgabe 26 – Monthly Quality Gate, Stress und Pflichtmetriken

**Status:** `NOT_STARTED`

**Ziel:** `monthly_quality_gate_v1` ergänzend zum unveränderten Quality-Gate-v1 umsetzen.

**DONE_100:** Alle inneren, Outer-, Kalender-, Konzentrations-, Stress-, Nachbarschafts-, Regime-, DSR-, PBO- und Integritätsgates sind vorhanden; fehlende Evidenz besteht nicht; Grün/Gelb/Rot bleibt ehrlich; Gates sind vor dem Lauf eingefroren.

## Aufgabe 27 – Hindsight-Benchmarks, Capture-Ratios und Bootstrap

**Status:** `NOT_STARTED`

**Ziel:** Historische Zielerreichung ehrlich von frischer statistischer Unterstützung trennen.

**DONE_100:** Hindsight-Solver ist reine Diagnostik; Capture-Ratios und Overfit-Sperren; Stationary Bootstrap 5/10/20 mit 10.000 Replikationen reproduzierbar; verbrauchte Historie kann nie `statistically_supported=true` erzeugen.

## Aufgabe 28 – Aktuellen 730-Tage-Refit und Champion/Challenger/Cash-Entscheidung

**Status:** `NOT_STARTED`

**Ziel:** Für den nächsten Anker deterministisch Bundle oder `NO_TRADE` einfrieren.

**DONE_100:** Fenster `[T-730,T)`; Report mit Gültigkeit, Hashes, Bundle, Vorgänger, Wechselgrund und Stress; Champion/Challenger/Cash deterministisch; bis frische Evidenz `diagnostic_only`; keine Rückdatierung.

## Aufgabe 29 – Orderfreien Research-Challenger-Shadow bauen

**Status:** `NOT_STARTED`

**Ziel:** Retrospektive Challenger strikt getrennt vom kanonischen Adoption-Shadow virtuell beobachten.

**DONE_100:** Eigener Reporttyp, Storage, Controller, Aktion und Forward-Ledger; keine Orders, API, Kontodaten oder Keys; Drei-Markt-Parität; Lücken oder Hashabweichung blockieren; `adopt_for_shadow` kann ihn nicht annehmen.

## Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Status:** `NOT_STARTED`

**Ziel:** Origins, Folds, Fortschritt, Safety, Ergebnisbedeutung und manuelle Challenger-Aktion korrekt anzeigen.

**DONE_100:** Keine vorzeitige Outer-PnL; vorhandene Bedienbuttons funktionieren; Ergebnis, Freshness und Champion sichtbar; Paper, Testtrade, Live und Orders gesperrt; Refresh ist zustandsneutral.

## Aufgabe 31 – Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr

**Status:** `NOT_STARTED`

**Ziel:** Die monatlich refittende Pipeline in einem vorab registrierten neuen 365-Tage-Fenster genau einmal final prüfen.

**DONE_100:** Zwölf kausale Refits; Zwischenresultate bis Tag 365 verborgen; sichtbare Forward-Monate nicht nachregistrierbar; nur dieser Pfad erzeugt Protocol-v3-Finalreport.

## Aufgabe 32 – End-to-End-Parität, Fehler-Injektion und vollständige Abnahme

**Status:** `NOT_STARTED`

**Ziel:** Die gesamte Pipeline vor dem langen Lauf technisch beweisen.

**DONE_100:** Research, Replay, Cache, Resume und Challenger sind bitgleich; Fehler-Injektionen vollständig; alle Tests grün; fixture-basierter 12-Origin-Dry-Run reproduzierbar; keine offene P0-Abweichung.

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
Protocol v3: Aufgabe 7/33 – Notional-, Mengen-, Gebühren- und Rundungsparität herstellen – DONE_100
Protocol v3: Aufgabe 8/33 – Next-Tradable-Price und pessimistische Intrabar-Ausführung – NOT_STARTED
Gesamt: 7/33 DONE_100 = 21,21 %
```

Nach jeder Aufgabe werden ausschließlich der abgeschlossene Schritt und die exakt nächste Aufgabe freigegeben. Fortschritt wird nicht nach Zeit oder Token geschätzt, sondern als `DONE_100 / 33` ausgewiesen.
