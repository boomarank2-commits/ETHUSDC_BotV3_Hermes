# Protocol v3 – verbindliche Implementierungsreihenfolge

Stand: 2026-07-13  
Quelle: `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md` auf Commit `c0676dbec97812a823c225e72c6577b7154d4013`  
Status: verbindlicher Ausführungs- und Abnahmeplan; noch keine Protocol-v3-Codefreigabe

## Arbeitsregel

Dieser Plan zerlegt den Blueprint in einzeln abschließbare Aufgaben. Es ist immer genau **eine** Aufgabe aktiv. Eine spätere Aufgabe beginnt erst, wenn die vorherige Aufgabe den Status `DONE_100` besitzt.

`DONE_100` bedeutet ohne Ausnahme:

1. Ziel und Grenzen der Aufgabe sind im Code beziehungsweise Vertrag umgesetzt.
2. Bestehende vergleichbare Funktionen wurden geprüft und möglichst wiederverwendet.
3. Unit-, Integrations-, Negativ- und Fail-closed-Tests der Aufgabe sind grün.
4. Python-Kompilierung, PowerShell-Syntax und `git diff --check` sind grün.
5. Relevante lokale Tests mit echten Rohdaten sind durch Codex oder den lokalen PC ausgeführt und als kleine Evidenz dokumentiert.
6. Keine spätere Aufgabe wurde heimlich vorgezogen.
7. Handoff nennt Dateien, Tests, Resultate, offene Grenzen und die exakt nächste Aufgabe.
8. GitHub-Branch und lokaler Arbeitsbaum sind synchron.

Eine Aufgabe ist **nicht** fertig, wenn nur ein Teil implementiert, nur ein Happy Path getestet oder nur eine Dokumentation geschrieben wurde. Lange Research-Läufe ersetzen keine Tests. Paper, Testtrade, Live, Orders, private Endpunkte und API-Keys bleiben in allen Aufgaben gesperrt.

## Rollen

- **ChatGPT/GitHub:** Architekturprüfung, fokussierte Repository-Änderungen, Tests, Review, CI und Handoff.
- **Codex/lokaler PC:** lokale Rohdaten, lange Läufe, Windows-/PowerShell-Ausführung und große Laufartefakte.
- **Nutzer:** ausdrückliche Produkt-/Vertragsentscheidungen und manuelle Freigaben; niemals automatische Trading-Freigabe.

## Aufgabe 1 – Protocol-v3-Vertrag versioniert übernehmen

**Ziel:** Der Blueprint wird zu einer ausdrücklich versionierten, ausführbaren Vertragsgeneration, ohne den verbrauchten Holdout als frisch umzudeuten.

**DONE_100:**

- `PROJECT_CONTRACT.md`, `AGENTS.md` und der Portfolio-/Shadow-Vertrag besitzen eine widerspruchsfreie Protocol-v3-Ergänzung.
- Begriffe `monthly_process_oos`, `consumed_audit`, `sealed_final_holdout`, `forward_shadow_month`, `research_challenger_shadow` und `diagnostic_only` sind eindeutig.
- Rolling-Training auf verbrauchter Rohhistorie ist ausdrücklich entweder erlaubt oder bleibt technisch `diagnostic_only`; diese Entscheidung ist versioniert.
- Der bestehende Protocol-v2- und Single-Candidate-Finalpfad bleibt erhalten und kann keinen Protocol-v3-Finalstatus erzeugen.
- Vertragstests blockieren widersprüchliche oder fehlende Versionen.

## Aufgabe 2 – Monatskalender und Boundary-Vertrag implementieren

**Ziel:** Exakt zwölf äußere Origins, 730 Entwicklungstage, 365 lückenlose Prozess-OOS-Tage und `T+24h`-Aktivierung werden als reine Boundary-Objekte implementiert.

**DONE_100:**

- UTC, Ankertag 8, synthetisches `b0`, `valid_from`, `valid_until`, `as_of_day`, `entry_enabled_at` und Late-Button-Regeln sind modelliert.
- Leap-/Non-Leap-Fixtures für Enden 2024-03-08, 2025-03-08 und 2026-07-08 liefern exakt zwölf Intervalle.
- Jeder der 365 OOS-Tage erscheint genau einmal und nie im eigenen Training.
- Fehlerhafte, doppelte oder lückenhafte Grenzen blockieren fail-closed.

## Aufgabe 3 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren

**Ziel:** Jede inhaltliche Pipelineversion besitzt eine unveränderliche Identität und vorab festgelegte Suchgrenzen.

**DONE_100:**

- Pipelinegeneration bindet Features, Familien, Suchraum, Ranking, Gates, Kosten, Simulator und Boundary-Regeln.
- Seeds sind deterministisch aus einem kanonischen Pre-Run-Manifest abgeleitet.
- Grenzen 12 Origins, 8 Zyklen, 40/12/3/2 und die globalen Maximalzahlen sind technisch erzwungen.
- `selection_stagnation_3_cycles` kann nur den inneren Lauf verkürzen, nie Budgets erweitern.
- Jede relevante Änderung erzeugt eine neue Generation und setzt ausschließlich deren Forward-Ledger zurück, niemals den permanenten Trial-Zähler.

## Aufgabe 4 – Permanentes Trial-Ledger und historischen Import bauen

**Ziel:** Jeder dateninformierte Versuch wird append-only und generationsübergreifend erfasst.

**DONE_100:**

- Deterministische Trial-ID, Kandidat, Parameter, Featurevariante, Seed, Ranking-/Gate-Version, Codehash und Ergebnisreihe werden gespeichert.
- Cache-Hits sind als Wiederverwendung sichtbar und werden nicht als unabhängiger neuer Versuch ausgegeben.
- Rekonstruierbare historische Trials werden importiert und mit `historical_trial_count_is_lower_bound=true` markiert.
- Solange Historie unvollständig ist oder kausale Tagesreihen fehlen, lautet DSR zwingend `INSUFFICIENT_TRIAL_HISTORY` und nur `NO_TRADE` ist freigabefähig.
- Ein bewerteter Trial kann weder gelöscht noch unprotokolliert verändert werden.

## Aufgabe 5 – Dynamischen Drei-Markt-Datensnapshot und Warmup herstellen

**Ziel:** Der letzte gemeinsame vollständige UTC-Tag und die erforderliche Warmup-Historie werden für ETHUSDC, BTCUSDC und ETHBTC dynamisch bestimmt und eingefroren.

**DONE_100:**

- Kein Produktions-Hardcode auf `2026-07-07` bleibt bestehen.
- Gemeinsamer Watermark, Vollständigkeit, 1.440-Minuten-Raster, Duplikate, Lücken, OHLC und Nullvolumen werden geprüft.
- `warmup_duration` wird aus allen aktiven Lookbacks plus einer Quellbar berechnet.
- Fehlt Warmup oder ein vollständiger Tag in nur einem Markt, blockiert Protocol v3.
- Der lokale Download-/Prüflauf liefert einen kleinen Snapshot-Report und Hash.

## Aufgabe 6 – Exchange-Info-Snapshot und vollständige Run-Fingerprints bauen

**Ziel:** Binance-Handelsfilter und sämtliche Identitäten eines Laufs sind versioniert und resume-sicher gebunden.

**DONE_100:**

- Versionierter Exchange-Info-Snapshot enthält PRICE_FILTER, LOT_SIZE/MARKET_LOT_SIZE und MIN_NOTIONAL/NOTIONAL für ETHUSDC.
- Fingerprints binden Rohdateien/Checksummen, Stichtag, Code, Pipeline, Features, Kontext, Gates, Kosten, Simulator, Boundary, Trial-Ledger-Head und Exchange Info.
- Eine Änderung an einem gebundenen Bestandteil verhindert Resume und Cache-Hit.
- Manifest und Hashbildung sind kanonisch, deterministisch und mit Manipulations-/Mismatch-Tests abgesichert.

## Aufgabe 7 – Notional-, Mengen-, Gebühren- und Rundungsparität im Simulator

**Ziel:** Das 100-USDC-Lot wird gemäß Produktvertrag und Binance-Filtern realistisch simuliert.

**DONE_100:**

- `requested_entry_notional_usdc=100`, `reserved_entry_notional_usdc=100` und `executed_entry_notional_usdc<=100` werden getrennt gespeichert.
- Menge wird auf Step Size abgerundet; Preis- und Notionalfilter werden geprüft.
- Entry- und Exit-Gebühren werden auf tatsächlichem Notional zusätzlich verbucht.
- Verkauf verwendet exakt die gerundete gekaufte Menge; kein Pfad erzeugt mehr als ein Lot.
- Golden-Trade-Fixtures prüfen Menge, Notional, Fees, Slippage und PnL bitgleich.

## Aufgabe 8 – Next-Tradable-Price und pessimistische Intrabar-Ausführung

**Ziel:** Signal-, Entry-, Stop-, TP-, Trail-, Gap- und Time-Exit-Reihenfolge entspricht dem Blueprint.

**DONE_100:**

- Signal auf abgeschlossener Bar, Entry frühestens am nächsten handelbaren Preis.
- Stop und TP in derselben 1m-Kerze: Stop gewinnt ausnahmslos.
- Gaps füllen zum schlechteren handelbaren Preis; perfekte High-/Low-Fills sind unmöglich.
- Exit-Prioritäten und terminale Liquidation sind explizit und getestet.
- Basis-, Slippage- und Joint-Stress verwenden dieselbe Execution-Engine.

## Aufgabe 9 – Warmup-, Purge-, Fold-End- und Outer-State-Maschine

**Ziel:** Informationsintervalle, Pending Entry, Cooldown, offene Position und Modellwechsel sind kausal und eindeutig.

**DONE_100:**

- `purge_duration` folgt dem maximalen Label-/Holding-Horizont plus Latenz und Ausführungsbar.
- Innere Folds starten flat und schließen Restpositionen konservativ am Fold-Ende.
- Nur die erste Outer-Origin startet flat; spätere Origins dürfen ausschließlich eine offene Altposition mit alter Exitlogik übernehmen.
- Pending Entries, Cooldowns, Scaler und Modellzustand werden nicht über Origins getragen.
- Alte Konfiguration ist ab Grenze exit-only; neue wartet auf `valid_from` und `flat_time`.

## Aufgabe 10 – Kontextparität und Drei-Markt-Watermark

**Ziel:** Kontext ist in Research, Replay, späterem Finalpfad und Challenger identisch, bleibt aber reines Veto/Bestätigung.

**DONE_100:**

- Zeitpunkt `t` wird nur mit drei exakt ausgerichteten, geschlossenen Bars verarbeitet.
- Fehlende, versetzte oder stale Kontextdaten pausieren fail-closed.
- BTCUSDC und ETHBTC können niemals einen Trade oder handelbaren Symbolwechsel erzeugen.
- Derselbe eingefrorene Kontextkandidat erzeugt in Kern und Replay identische Entscheidungen.
- Kontextidentität ist Bestandteil aller Fingerprints und Cache-Keys.

## Aufgabe 11 – Protocol-v3-Report-Schemas und Evidenzbedeutung

**Ziel:** Research-, Monatsprozess-, Challenger-, Forward- und Pipeline-Finalberichte sind getrennt versioniert und semantisch ehrlich.

**DONE_100:**

- Eigene Schemaarten und Storage-Roots verhindern Verwechslung mit Single-Candidate-Finalreports.
- `consumed`, `diagnostic_only`, `freshness`, `historically_hit`, `statistically_supported` und Adoption-Eignung können nicht falsch gesetzt werden.
- Der strikte Reader akzeptiert nur die zu seinem Vertrag gehörenden Felder und Versionen.
- Sichtbare Forward-Monate können nicht nachträglich in ein Finalfenster aufgenommen werden.
- Schema-Migrations- und Negativtests sind vollständig.

## Aufgabe 12 – Kompakte Artefaktarchitektur

**Ziel:** Zwölf Monatsrefits sind speicher- und lesbar, ohne 400-MB-Zyklusduplikate.

**DONE_100:**

- Kleiner JSON-Index und getrennte deduplizierte Trade-, Daily-PnL-, Equity- und Diagnostikartefakte.
- Keine millionenfach eingebetteten Kurven oder identischen Payloads.
- Alle Referenzen besitzen Digest, Schema und Provenienz.
- Dokumentierte Größenbudgets werden in Tests/Reports geprüft.
- UI und Reader laden nur kleine Status-/Indexartefakte.

## Aufgabe 13 – Content-addressed Cache und transaktionales Resume

**Ziel:** Abbruch, Neustart und Cache-Wiederverwendung verändern keine Entscheidung.

**DONE_100:**

- Cache-Key bindet Daten, Kontext, Features, Kandidat, Fold, Boundary, Execution, Simulator und Kosten.
- Checkpoint bindet Code, Snapshot, Exchange Info, Pipelinegeneration, Trial-Head, Origin-Digests, Rotation-State und Sealed-Store-Head.
- Atomic Replace, Dateisperre, Digestprüfung und deterministische IDs verhindern Teilstände und doppelte Origins.
- Resume auf Outer-Origin- und Inner-Cycle-Ebene liefert bitgleiche Entscheidungsmetriken.
- PID-Reuse, stale Locks, manipulierte Dateien und unvollständige Writes sind negativ getestet.

## Aufgabe 14 – Exakten inneren 6-x-60-Tage-Fold-Planer bauen

**Ziel:** Die sechs nicht überlappenden Validation-Folds der letzten 360 Entwicklungstage ersetzen die heutige ungeeignete Grenzlogik.

**DONE_100:**

- Fold-Boundary-Objekte entsprechen exakt Abschnitt 6.3 des Blueprints.
- Fit wächst von 370 Tagen vor Purging in 60-Tage-Schritten.
- Timestamp-Spies beweisen, dass kein Fit Validation oder Outer-Test sieht.
- Purge und Warmup werden pro Fold korrekt angewendet.
- Fehlende 730 Tage, 60-Tage-Folds oder vollständige Tagesraster blockieren.

## Aufgabe 15 – Reine innere Auswahlfunktion extrahieren

**Ziel:** Die heutige Engine wird als wiederverwendbare, deterministische Funktion für beliebige 730-Tage-Fenster nutzbar.

```text
select_candidate(training_window, frozen_pipeline_config)
    -> candidate | NO_TRADE, evidence, fingerprints
```

**DONE_100:**

- Keine globale Laufzeit- oder UI-Abhängigkeit in der Auswahlfunktion.
- Kein Zugriff nach `training_end` und kein Outer-Ergebnis als Input.
- Gleicher Input und gleiche Hashes erzeugen bitgleich dieselbe Auswahl.
- Bestehende Familien, Simulator und 40/12/3/2-Stufen werden wiederverwendet.
- Fehler, fehlende Evidenz oder kein bestandener Kandidat liefern deterministisch `NO_TRADE`.

## Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets

**Ziel:** Alle zwölf getesteten Profile je Zyklus besitzen dieselbe 360-Tage-OOS-Basisreihe; nur drei gehen in teure Robustheit.

**DONE_100:**

- Tägliche Netto-MTM-Reihe inklusive Nulltage für jedes getestete Profil.
- Kandidatenmatrix besitzt identische 360 Tage und Cash als feste Nullbaseline.
- Promotion 12 Basisreihen -> 3 Full-WFV -> 2 Finalisten ist nachvollziehbar und budgetfest.
- Trial-Ledger erfasst jeden datenbewerteten Kandidaten, auch billige Vorstufen.
- Globale Maximalbudgets können technisch nicht überschritten werden.

## Aufgabe 17 – PBO/CSCV exakt implementieren

**Ziel:** `development_pbo` folgt exakt dem 12-Block-/924-Split-Vertrag.

**DONE_100:**

- 12 zusammenhängende Blöcke zu je 30 Tagen und exakt 924 Kombinationen.
- IS-Ties, OOS-Ränge, Omega, Lambda und PBO entsprechen dem Blueprint.
- Cashbaseline, nichtfinite Werte, weniger als zwei Tradingprofile oder ungleiche Tagesachsen liefern `INSUFFICIENT_EVIDENCE`.
- Alle Splits und Zwischenwerte sind reportierbar und deterministisch getestet.
- PBO wird nur aus innerer Development-Matrix berechnet und nie aus Outer-Ergebnissen zurückgespielt.

## Aufgabe 18 – DSR und Multiple-Testing-Diagnostik implementieren

**Ziel:** `development_dsr` verwendet permanente Trials, Autokorrelationskorrektur, Skew und Kurtosis gemäß Vertrag.

**DONE_100:**

- N, K, VIF, effektive Stichprobe, Trial-SR-Verteilung, SR0, z und Phi sind nachvollziehbar.
- Das harte Gate nutzt `N_raw`, nicht den kleineren diagnostischen effektiven Trialwert.
- Unvollständige Trial-Historie, fehlende gemeinsame Reihen, Nullvarianz oder ungültiger Nenner liefern `INSUFFICIENT_EVIDENCE`.
- White Reality Check beziehungsweise Hansen SPA bleibt klar als retrospektive Warnleuchte getrennt.
- Referenz- und Property-Tests decken Grenzfälle ab.

## Aufgabe 19 – Kausalen Multi-Timeframe-Feature-Store bauen

**Ziel:** Vollständig abgeschlossene 5m/15m/30m/1h/4h/1d-Features sowie Wochen-/Monatskontext stehen fold-sicher bereit.

**DONE_100:**

- Unfertige Bars sind nie sichtbar; Signal und Kontext besitzen einen gemeinsamen Informationsstand.
- Normalisierung, Quantile und Feature-Auswahl werden ausschließlich auf Fold-Training fitten.
- Feature-Version und Fit-State sind hashbar und replaybar.
- Warmup seedet alle drei Märkte, erzeugt aber kein Signal, Label oder PnL.
- Determinismus-, Leakage- und Boundary-Tests sind grün.

## Aufgabe 20 – Opportunity- und Regime-Schicht implementieren

**Ziel:** Volatilitätskapazität entscheidet nur über mögliche Bewegung; Richtung und Entry bleiben separat belegt.

**DONE_100:**

- Opportunity-Kapazität, ATR/Range, Kompression, Trend-Effizienz, Trendanker, Pullback-Tiefe und Stressregime sind kausal.
- Regimegrenzen und Quantile werden je Fold nur aus Training gelernt.
- Jede Regimeentscheidung ist erklärbar und im Bundle gespeichert.
- Kein Zukunfts-MFE/MAE dient als Feature.
- Unbekanntes oder widersprüchliches Regime führt fail-closed zu `NO_TRADE`.

## Aufgabe 21 – Lokale Spezialisten hinter der bestehenden Engine bauen

**Ziel:** Die vier begrenzten Challenger-Familien verwenden vorhandene Mechanismen statt einer zweiten Simulationsengine.

**DONE_100:**

- `trend_pullback_reclaim`, `compression_breakout_retest`, `range_reversion_confirmed` und `multiday_swing_trend` sind klein, versioniert und kausal.
- Bestehende Momentum-/Breakout-/Pullback-/Mean-Reversion-Logik wird gezielt wiederverwendet.
- Entry-Bestätigung, Stop, TP, Trail, Time-Exit und maximale Trades/Haltedauer sind vorab begrenzt.
- Jeder Spezialist besitzt Signal-Funnel und eindeutige Ablehnungsgründe.
- Kein Spezialist darf ohne lokale Development-Evidenz freigegeben werden.

## Aufgabe 22 – Router, NO_TRADE und FrozenCandidateBundle verbinden

**Ziel:** Champion ist ein gehashtes Bundle aus Router, Spezialisten, Fit-State und Ausführungsvertrag.

**DONE_100:**

- Router wählt Trend/Pullback, Breakout, Range/Reversion oder `NO_TRADE`.
- Maximal ein Lot insgesamt; keine parallelen Spezialistenpositionen.
- Bundle enthält Router, Spezialisten, Parameter, Quantile, Scaler, Feature-State, Kontextpolicy, Kosten, Rotation und Gültigkeit.
- Flache unvollständige `StrategyCandidate.params` können keinen Router als ausführbar markieren.
- Jede Entscheidung ist auf Regime, Spezialist, Featurestand und Bundlehash zurückführbar.

## Aufgabe 23 – Zwölf äußere Monats-Origins orchestrieren

**Ziel:** Die unveränderte Auswahlpipeline wird an jedem Origin vollständig neu auf den jeweils vorherigen 730 Tagen ausgeführt.

**DONE_100:**

- `pipeline_refit_per_origin=true` und zwölf unterschiedliche Fit-Stichtage.
- Jede Origin friert genau einen Bundle-Kandidaten oder `NO_TRADE` ein.
- OOS-Ergebnis einer Origin wird versiegelt und ist für spätere Fits unsichtbar.
- 365 Tage sind exakt, lückenlos und duplikatfrei verkettet.
- Fehler einer Origin führen für ihr Intervall zu `NO_TRADE`, nicht zu stiller Verlängerung.

## Aufgabe 24 – 24h-Aktivierung und Outer-Rotation-State

**Ziel:** Alte Exitlogik und neue wartende Entrylogik koexistieren deterministisch über Monatsgrenzen.

**DONE_100:**

- Neue Entries frühestens `T+24h` und zusätzlich erst nach `flat_time`.
- Früher Abschluss wartet; verspäteter Button plant nur den nächsten Anker.
- Altes Bundle ist nach Grenze ausschließlich exit-only.
- Rotation-State ist versioniert, hashbar, resume-fähig und verhindert Doppelentries.
- Grenz-, Abbruch-, offene-Position- und Monatswechsel-Fixtures sind vollständig.

## Aufgabe 25 – Tägliches MTM-Ledger und zwei Zeitaggregationen

**Ziel:** Deployment-Intervalle und UTC-Kalenderperioden werden ohne Doppelzählung getrennt ausgewertet.

**DONE_100:**

- Tägliche Netto-MTM-Reihe enthält alle Nulltage.
- Closed-Trade-PnL und Tradezahl werden dem Exit-Zeitpunkt zugeordnet; Fees/Slippage dem Ausführungstag.
- Zwölf Deployment-Intervalle sowie alle berührten Kalendermonate und -quartale werden separat reportiert.
- Grenzpositionen erscheinen genau einmal in MTM-Gesamt-PnL.
- Konsistenztests gleichen Tagesledger, Trades, Kosten, Equity und Endpunkt ab.

## Aufgabe 26 – Monthly Quality Gate, Stress und Pflichtmetriken

**Ziel:** `monthly_quality_gate_v1` ergänzt den bestehenden unveränderten Gate-v1-Evaluator, ersetzt ihn aber nicht.

**DONE_100:**

- Alle inneren, Outer-, Deployment-, Kalender-, Konzentrations-, Stress-, Nachbarschafts-, Regime-, DSR/PBO- und Integritätsanforderungen sind umgesetzt.
- Fehlende Evidenz besteht kein Trading-Gate; `NO_TRADE` kann keine Robustheit vortäuschen.
- Grün verlangt Robustheit plus Ziel; Gelb nur `robustness_passed_ex_target=true`; Rot bleibt nicht übernehmbar.
- Gates sind vor dem Lauf eingefroren und können nicht aus Outer-Ergebnissen angepasst werden.
- Flat, ETH Buy-and-hold und alle Pflichtmetriken sind vollständig.

## Aufgabe 27 – Hindsight-Benchmarks, Capture-Ratios und Bootstrap

**Ziel:** Historische Zielerreichung wird ehrlich von statistisch frischer Unterstützung getrennt.

**DONE_100:**

- All-Candle-Ein-Trade-Diagnose und kandidatengleicher volumen-/zustandsgefilterter Solver sind ausschließlich nachgelagerte Diagnostik.
- Solver speist niemals Features, Labels, Suche oder Ranking.
- Capture-Ratios, Leakage-/Overfit-Warnschwellen und manuelle Sperre sind umgesetzt.
- Circular Stationary Bootstrap mit Längen 5/10/20, 10.000 Replikationen und manifestbasiertem Seed ist bitgleich reproduzierbar.
- Verbrauchte Historie kann niemals `statistically_supported=true` setzen.

## Aufgabe 28 – Aktuellen 730-Tage-Refit und Champion/Challenger/Cash-Entscheidung

**Ziel:** Dieselbe Pipeline erzeugt für den nächsten Anker einen eingefrorenen Kandidaten oder `NO_TRADE`.

**DONE_100:**

- Datenfenster exakt `[T-730,T)`, niemals Daten nach T.
- Report enthält Gültigkeit, Hashes, Bundle, Vorgänger, Wechselgrund, Stressstatus und manuelle Shadow-Pflicht.
- Champion, Challenger und Cash werden paarweise und deterministisch verglichen.
- Bis zur nötigen Vertrags-/Frischelage bleibt Ergebnis korrekt `diagnostic_only` und `canonical_adoption_eligible=false`.
- Später Button kann keine rückwirkende Gültigkeit erzeugen.

## Aufgabe 29 – Orderfreien Research-Challenger-Shadow bauen

**Ziel:** Retrospektive Protocol-v3-Challenger können ausschließlich virtuell und strikt getrennt vom kanonischen Adoption-Shadow beobachtet werden.

**DONE_100:**

- Eigener Reporttyp, Storage-Root, Controller, Action und append-only Forward-Ledger.
- Keine Orders, Trading-API, privaten Endpunkte, Kontodaten oder API-Keys.
- Drei-Markt-Watermark, Bundle, Execution und Golden Trades sind end-to-end identisch zum Researchkern.
- Datenlücke, Stale Feed oder Hashabweichung blockiert virtuelle Entries.
- `adopt_for_shadow` kann diesen Challenger weder finden noch annehmen.

## Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Ziel:** Nutzer sieht Lauf, Origins, Folds, Sicherheit, Ergebnisbedeutung und manuelle Challenger-Aktion korrekt.

**DONE_100:**

- Während des Laufs: Snapshot/Hash, Origin 1-12, Fold, Kandidatenstufe, Resume und Safety; keine vorzeitige Outer-PnL.
- Start, Pause, Fortsetzen, Abbruch, Neustart, Zurücksetzen und Datenprüfung bleiben sichtbar und funktionsfähig.
- Nach Abschluss: Prozessmetriken, Zielstatus, Freshness, Champion/Challenger/Cash und Gültigkeit.
- Paper, Testtrade, Live und Orders bleiben sichtbar gesperrt.
- UI-Refresh ist zustandsneutral; GUI-Neustart setzt aus gültigem Checkpoint fort.

## Aufgabe 31 – Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr

**Ziel:** Der Protocol-v3-Champion – die monatlich refittende Pipeline – erhält einen eigenen zukünftigen Finalpfad.

**DONE_100:**

- Frisches 365-Tage-Fenster wird vor Beginn registriert und bis Tag 365 verborgen.
- Alle zwölf Refits verwenden nur am jeweiligen Origin bekannte Daten.
- Zwischenresultate bleiben verborgen; Öffnung erfolgt genau einmal am Ende.
- Sichtbare Challenger-/Forward-Monate können nicht nachregistriert werden.
- Nur dieser getrennte Evaluator kann später einen kanonischen Protocol-v3-`final_evaluation`-Report erzeugen.

## Aufgabe 32 – End-to-End-Parität, Fehler-Injektion und vollständige Abnahme

**Ziel:** Die gesamte Pipeline ist vor einem langen Lauf technisch bewiesen.

**DONE_100:**

- Research, Replay, Cache, Resume und Challenger liefern für identische Inputs bitgleiche Entscheidungen.
- Fehler-Injektionen decken Datenlücken, Hashmismatch, Abbruch, Lock, beschädigte Artefakte, Kontextversatz, Boundaryfehler und Rotation ab.
- Alle Unit-, Integrations-, Golden-, Boundary-, Leakage-, Statistik-, UI- und PowerShell-Tests sind grün.
- Ein kleiner fixture-basierter 12-Origin-Dry-Run läuft vollständig und reproduzierbar.
- Keine offene P0-Abweichung aus dem Blueprint bleibt bestehen.

## Aufgabe 33 – Erster vollständiger Protocol-v3-Research-Lauf und Abschlussbericht

**Ziel:** Erst nach Aufgaben 1-32 wird der reale historische Monatsprozess auf dem lokalen PC ausgeführt und unverändert ausgewertet.

**DONE_100:**

- Warmup, Snapshot, Trial-Status und alle 12 Origins sind ehrlich gebunden.
- 365 Prozess-OOS-Tage werden genau einmal verarbeitet; Outer-Ergebnisse bleiben bis Ende geschlossen.
- Lauf ist reproduzierbar fortsetzbar und erzeugt kompakte, digest-gebundene Artefakte.
- Bericht beantwortet vollständig die sieben Erfolgsfragen aus Abschnitt 13 des Blueprints.
- Ergebnis lautet ehrlich `TARGET_REACHED`, `TARGET_NOT_REACHED` oder `NO_EDGE_FOUND`; keine Gates oder Parameter werden nach Betrachtung dieses Laufs angepasst.
- Nächste Entscheidung wird als neue, ausdrücklich freigegebene Pipelinegeneration oder unverändertes Forward-Challenger-Monitoring dokumentiert.

## Fortschrittsführung

Die kanonische Statuszeile lautet:

```text
Protocol v3: Aufgabe X/33 – <Titel> – NOT_STARTED | IN_PROGRESS | BLOCKED | DONE_100
```

Nach jeder Aufgabe wird in diesem Dokument ausschließlich der Status der abgeschlossenen Aufgabe und der exakt nächsten Aufgabe aktualisiert. Prozentfortschritt wird nicht nach Zeit oder Token geschätzt, sondern ausschließlich als `vollständig abgenommene Aufgaben / 33` ausgewiesen.

Aktueller Stand:

```text
Protocol v3: Aufgabe 1/33 – Protocol-v3-Vertrag versioniert übernehmen – NOT_STARTED
Gesamt: 0/33 DONE_100 = 0,00 %
```
