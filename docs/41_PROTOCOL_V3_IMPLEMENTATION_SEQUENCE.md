# Protocol v3 – verbindliche Implementierungsreihenfolge

Stand: 2026-07-16
Quelle: `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 12/33 abgeschlossen

## Arbeitsregel

Es ist immer genau eine Aufgabe aktiv. Eine spätere Aufgabe beginnt erst, wenn die vorherige Aufgabe `DONE_100` besitzt.

`DONE_100` erfordert vollständig umgesetzten Umfang, Wiederverwendung vorhandener Funktionen, grüne Unit-/Integrations-/Negativtests, Python-Kompilierung, PowerShell-Syntax, Whitespace-Prüfung, dokumentierte Grenzen, keinen Vorgriff auf spätere Aufgaben und einen eindeutigen GitHub-Handoff. Paper, Testtrade, Live, Orders, private Endpunkte und API-Keys bleiben gesperrt.

## Aufgaben 1 bis 12 – abgeschlossen

### Aufgabe 1 – Protocol-v3-Vertrag versioniert übernehmen

**Status:** `DONE_100`

Blueprint, Projektvertrag, Agentenregeln sowie Portfolio-/Shadow-Vertrag wurden widerspruchsfrei als Vertragsgeneration 3.0.0 übernommen. Der Pipelineaufbau validiert diese Repository-Verträge fail-closed und bindet ihre vollständigen Quelldigests in jede Pipelinegeneration. Verbrauchter Audit bleibt `NOT_FRESH`; Legacy-Pfade können keinen Protocol-v3-Finalstatus erzeugen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_01_2026-07-13.md`

### Aufgabe 2 – Monatskalender und Boundary-Vertrag implementieren

**Status:** `DONE_100`

Exakt zwölf Origins, 730 Entwicklungstage je Origin, 365 lückenlose Prozess-OOS-Tage, UTC-Ankertag 8 und `T+24h`-Aktivierung sind als reine Boundary-Schicht umgesetzt.

**Bericht:** `handoff/PROTOCOL_V3_TASK_02_2026-07-14.md`

### Aufgabe 3 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren

**Status:** `DONE_100`

Pipelinegeneration, timestamp-freies Pre-Run-Manifest, deterministische Seeds, globale 12-Origin-Budgets und ausschließlich verkürzende Stopregeln sind eingefroren. Der zusätzliche aktuelle Refit benötigt vor der ersten Reservierung eine gebundene Manifestidentität, kann nur einmal begonnen und nach Abschluss nicht fortgesetzt werden. Das 3-USDC-Ziel ist keine Suchverlust- oder Stopregel.

**Berichte:**
- `handoff/PROTOCOL_V3_TASK_03_2026-07-14.md`
- `handoff/PROTOCOL_V3_TASK_03_BUDGET_CORRECTION_2026-07-14.md`

### Aufgabe 4 – Permanentes Trial-Ledger und historischen Import bauen

**Status:** `DONE_100`

Versuche werden append-only, hashverkettet und generationsübergreifend erfasst. Historischer Import zählt nur vollständig quell- und beobachtungsgebundene Trials; bloße Zeilenzahlen, vom Aufrufer gelieferte Attestierungswerte oder spätere Ledger-Ereignisse können den damaligen Gate-Zustand nicht rückwirkend freigeben. Der belegbare Altbestand bleibt eine Untergrenze mit 180 bekannten Bewertungszeilen und 0 vollständig aufgelösten unabhängigen Alt-Trials; deshalb bleibt nur `NO_TRADE` freigabefähig.

**Bericht:** `handoff/PROTOCOL_V3_TASK_04_2026-07-14.md`

### Aufgabe 5 – Dynamischen Drei-Markt-Datensnapshot und Warmup herstellen

**Status:** `DONE_100`

ETHUSDC, BTCUSDC und ETHBTC erhalten eine dynamische gemeinsame vollständige UTC-Watermark, exakte 1m-Rasterprüfung, Markt-/Archivdigests, einen SHA-256-Inhaltsnachweis für jeden Markt und UTC-Tag sowie `max(active lookbacks)+1 Quellbar` Warmup. ZIP-Prüfsummen werden gestreamt und fail-closed geparst. Der reale bekannte Bestand bleibt `BLOCKED_MISSING_WARMUP`.

**Bericht:** `handoff/PROTOCOL_V3_TASK_05_2026-07-14.md`

### Aufgabe 6 – Exchange-Info-Snapshot und vollständige Run-Fingerprints bauen

**Status:** `DONE_100`

Öffentliche ETHUSDC-Exchange-Filter und zwölf Identitätsklassen sind immutable und SHA-256-gebunden. Private oder kontobezogene Schlüssel werden auf jeder Payload-Tiefe abgelehnt. Der Run-Fingerprint v2 verlangt eine konkrete validierte Kontextbindung und gleicht deren Datensnapshot mit der Rohdatenidentität ab; Resume und Cache-Hit verlangen denselben vollständigen Fingerprint.

**Bericht:** `handoff/PROTOCOL_V3_TASK_06_2026-07-14.md`

### Aufgabe 7 – Notional-, Mengen-, Gebühren- und Rundungsparität herstellen

**Status:** `DONE_100`

Requested und reserved bleiben exakt 100 USDC; executed bleibt wegen der aktiven LOT-/MARKET_LOT-Raster höchstens 100 USDC. Ein Binance-Filter mit `stepSize=0` ist einzeln deaktiviert, mindestens ein positiver wirksamer Raster bleibt Pflicht. Der kanonische Pfad erzwingt exakt 0,1 % Gebühr und 5 bps Slippage je Seite. Entry-/Exit-Fees verwenden tatsächliche Notionals, der Exit exakt die gekaufte Menge, Compounding bleibt aus.

**Bericht:** `handoff/PROTOCOL_V3_TASK_07_2026-07-14.md`

### Aufgabe 8 – Next-Tradable-Price und pessimistische Intrabar-Ausführung

**Status:** `DONE_100`

Entry erfolgt erst nach geschlossener Signalbar am nächsten positiven Volumen-Open. Eine Pending Entry besitzt denselben eingefrorenen Horizont wie Purge und verfällt deterministisch; am oder nach dem letzten handelbaren Balken entstehen keine neuen Entries. Tick-Rundung ist adverse, Stop gewinnt bei Doppelberührung, Gaps werden pessimistisch gefüllt, perfekte Extremfills sind ausgeschlossen und Break-even/Trail gelten erst ab Folgebalken.

**Bericht:** `handoff/PROTOCOL_V3_TASK_08_2026-07-14.md`

### Aufgabe 9 – Warmup-, Purge-, Fold-End- und Outer-State-Maschine

**Status:** `DONE_100`

Warmup ist feature-only, Purge folgt dem maximalen Informationshorizont plus Ausführungsbar, innere Folds starten flat und enden konservativ. Eine Altposition darf nur mit identischer Candidate-Bundle-Identität fortgeführt werden; terminale Liquidation erfolgt auf dem letzten tatsächlich handelbaren Balken. Zwischen Origins wird ausschließlich höchstens eine offene Altposition mit alter Exitlogik übernommen; neue Entries warten auf `max(valid_from,flat_time)`.

**Bericht:** `handoff/PROTOCOL_V3_TASK_09_2026-07-14.md`

### Aufgabe 10 – Kontextparität und Drei-Markt-Watermark

**Status:** `DONE_100`

**Abnahme:**

- Vertrag `three_market_closed_bar_context_parity_v2` bindet ETHUSDC als einziges Handelssymbol; BTCUSDC und ETHBTC bleiben ausschließlich Kontextmärkte.
- Die vorhandenen Research-/Replay-Adapter verwenden dieselbe Kontextfunktion, dieselbe `ContextVetoPolicy` und dieselbe Task-8-Ausführungsengine. Die Pfadnamen für Final-Evaluator und Research-Challenger sichern nur die spätere Paritätsanforderung; deren Controller bleiben ausdrücklich Aufgabe 31 beziehungsweise 29.
- Entscheidungen sind nur bei drei exakt ausgerichteten vollständig geschlossenen 1m-Bars zum Zeitpunkt `open_time+59.999 ms` erlaubt.
- Fehlender, versetzter, lückenhafter, veralteter oder zukünftiger Kontext blockiert; Nearest-Neighbor, Forward-Fill und Interpolation sind verboten.
- Die Watermark bleibt die Task-5-Datenwahrheit. Kontextfenster müssen aus vollständigen UTC-Tagen bestehen, und jeder Markt-/Tag-Inhalt muss exakt dem Task-5-Tagesindex entsprechen.
- Kontext darf ausschließlich ein vorhandenes ETHUSDC-Signal bestätigen oder vetoen; BTCUSDC und ETHBTC können weder Signal noch Trade erzeugen.
- Kontextidentität bindet Vertrag, Policy, den konkret validierten Task-5-Snapshot, drei Snapshot- und drei Fensterinhalte, Startzeit, letzte gemeinsame Bar und Candle-Anzahl.
- Cache-/Resume-Key verlangen dieselbe Kontextidentität; der Run-Fingerprint v2 bettet diese konkrete Laufzeitbindung ein und prüft sie gegen die Rohdatenidentität.
- Task-7-, Task-8- und Task-9-Verhalten blieb unverändert; keine Aufgabe 11 oder später wurde vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_10_2026-07-15.md`

### Aufgabe 11 – Protocol-v3-Report-Schemas und Evidenzbedeutung

**Status:** `DONE_100`

**Abnahme:**

- Vertrag `protocol_v3_evidence_reports_v1` definiert getrennte, versionierte Reportarten und feste Roots für Research, Monatsprozess-OOS, Research-Challenger, Forward-Monat und den eindeutig benannten späteren Protocol-v3-Pipeline-Finalreport.
- `sealed_final_holdout` ist ausschließlich die Evidenzfensterklasse des späteren Finalreports; der Legacy-Typ `final_evaluation` wird nicht wiederverwendet.
- `historically_hit` wird ausschließlich aus `process_oos_net_usdc / 365 >= 3.0` abgeleitet und erzeugt weder Freshness noch statistische Unterstützung oder Adoption.
- Task-27-/Task-31-Attestierungen können in Aufgabe 11 nicht behauptet werden; `fresh_pre_registered_sealed_365`, Bootstrap-Support und `statistically_supported` bleiben fail-closed falsch.
- Historischer Monatsprozess bleibt immer `NOT_FRESH`, `diagnostic_only` und nicht adoptierbar; Research-Challenger bleibt orderfrei; ein Forward-Monat ist nur eine frische Beobachtung und niemals alleiniger Finalnachweis.
- Forward-Monate werden vor Beginn create-only registriert, an Pipelinegeneration und Run-Fingerprint gebunden und beim Reload semantisch revalidiert. Ein späteres Finalfenster scannt die tatsächlich persistierten Registrierungen und blockiert jede Überlappung.
- JSON ist strikt: exakte Schlüssel und Versionen, keine Duplicate Keys, unbekannten Safety-/Evidenzfelder, `NaN`, Infinity oder nichtkanonischen Bytes.
- Persistenz ist create-only, Root-, Traversal-, Symlink- und Alias-sicher und revalidiert unmittelbar nach dem Schreiben.
- Jede Protocol-v3-Reportklasse wird von den bestehenden Legacy-Final-/Adoptionspfaden abgelehnt.
- Reportvertrag und Implementierung sind in Pipelinegeneration und Run-Fingerprint gebunden; keine kompakte Artefaktarchitektur, Cache-/Resume-, Final-Evaluator- oder Controllerarbeit aus Aufgabe 12 oder später wurde vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_11_2026-07-16.md`

### Aufgabe 12 – Kompakte Artefaktarchitektur

**Status:** `DONE_100`

**Abnahme:**

- Vertrag `protocol_v3_compact_artifact_store_v1` trennt content-addressed Objekte von einem kleinen kanonischen Referenzindex.
- Eigene Objekt-Schemas existieren für Trades, tägliche Netto-MTM-PnL einschließlich echter Nulltage, Equity/Underwater sowie Fold-/Kandidaten-/Diagnostikevidenz.
- SHA-256, Bytegröße und logische Kardinalität werden aus den tatsächlich kanonisch serialisierten Objektbytes berechnet und niemals als Aufruferbehauptung übernommen.
- Jede Referenz bindet Art, Schema, Digest, Größe, Kardinalität und Provenienz; die Provenienz bindet den revalidierten Elternreport, vollständigen Run-Fingerprint, Pipelinegeneration und eine gehashte Work-Unit-Identität.
- Ein vorhandenes Objekt unter demselben Digest wird vollständig gelesen, kanonisch und semantisch validiert und niemals blind überschrieben.
- Alle Objekte werden geschrieben, geflusht, erneut gelesen und validiert, bevor der referenz-only Index veröffentlicht wird.
- Identische Bytes werden einmal gespeichert und dürfen mehrfach referenziert werden; unterschiedliche Inhalte besitzen unterschiedliche Content-Adressen.
- Der Index enthält keine Rohkerzen und keine eingebetteten Trade-, Daily-PnL- oder Equity-Reihen. Pfad-Traversal, Alias- und Symlink-Flucht blockieren.
- Die versionierte Größenpolitik ist auf 12 Origins × 8 Cycles × 4 Artefaktarten = 384 Referenzen geprüft, besitzt 2× Headroom und bleibt unabhängig von 1m-Candle- oder Kurvenlängen.
- Generierte Objekt- und Indexroots sind Git-ignoriert. Task-13-Crash-/Resume-Transaktionen, Locks und Checkpoints wurden ausdrücklich nicht vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_12_2026-07-16.md`

## Aufgaben 13 bis 33 – verbindliche Reihenfolge

### Aufgabe 13 – Content-addressed Cache und transaktionales Resume

**Status:** `NOT_STARTED` – exakt nächste Aufgabe

Cache- und Checkpoint-Identität müssen alle Daten-, Kontext-, Feature-, Kandidaten-, Fold-, Boundary-, Execution-, Simulator-, Kosten-, Code-, Snapshot-, Trial- und Rotationselemente binden; Atomic Replace, Lock und Digestprüfung verhindern Teilstände.

### Aufgabe 14 – Exakten inneren 6×60-Tage-Fold-Planer bauen

**Status:** `NOT_STARTED`

Sechs nicht überlappende 60-Tage-Validation-Folds auf den letzten 360 Entwicklungstagen; Fits wachsen ab 370 Tagen, Purge wird angewendet und Timestamp-Spies verhindern Leakage.

### Aufgabe 15 – Reine innere Auswahlfunktion extrahieren

**Status:** `NOT_STARTED`

`select_candidate(training_window, frozen_pipeline_config)` muss deterministisch, UI-unabhängig und ohne Zugriff nach `training_end` oder auf Outer-Ergebnisse arbeiten; fehlende Evidenz liefert `NO_TRADE`.

### Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets

**Status:** `NOT_STARTED`

Alle zwölf getesteten Profile erhalten dieselbe vollständige 360-Tage-Netto-MTM-Reihe inklusive Nulltagen; Promotion bleibt 12 Basisreihen → 3 Full-WFV → 2 Finalisten.

### Aufgabe 17 – PBO/CSCV exakt implementieren

**Status:** `NOT_STARTED`

PBO nach zwölf zusammenhängenden Blöcken und 924 Splits; unvollständige oder ungleiche Reihen liefern `INSUFFICIENT_EVIDENCE`.

### Aufgabe 18 – DSR und Multiple-Testing-Diagnostik implementieren

**Status:** `NOT_STARTED`

DSR bindet permanenten Trial-Count, Autokorrelation, Schiefe und Kurtosis; unvollständige Trial-Historie oder ungültige Statistik blockiert.

### Aufgabe 19 – Kausalen Multi-Timeframe-Feature-Store bauen

**Status:** `NOT_STARTED`

Nur abgeschlossene 5m/15m/30m/1h/4h/1d- sowie Wochen-/Monatsfeatures; Scaler, Quantile und Feature-State sind fold-sicher, hashbar und replaybar.

### Aufgabe 20 – Opportunity- und Regime-Schicht implementieren

**Status:** `NOT_STARTED`

Bewegungskapazität, Trend, Range, Kompression und Stress werden kausal erkannt; unbekanntes oder widersprüchliches Regime führt `NO_TRADE`.

### Aufgabe 21 – Lokale Spezialisten hinter der bestehenden Engine bauen

**Status:** `NOT_STARTED`

Pullback/Reclaim, Breakout/Retest, bestätigte Range-Reversion und Mehrtagesswing werden als kleine begrenzte Familien hinter derselben Engine geprüft.

### Aufgabe 22 – Router, NO_TRADE und FrozenCandidateBundle verbinden

**Status:** `NOT_STARTED`

Router wählt genau einen Spezialisten oder `NO_TRADE`; Bundle bindet Parameter, Fit-State, Features, Kontext, Kosten, Rotation und Gültigkeit.

### Aufgabe 23 – Zwölf äußere Monats-Origins orchestrieren

**Status:** `NOT_STARTED`

Die unveränderte Auswahlpipeline läuft an zwölf Fit-Stichtagen auf den jeweils vorherigen 730 Tagen; 365 OOS-Tage bleiben lückenlos und spätere Fits sehen frühere OOS-Ergebnisse nicht.

### Aufgabe 24 – 24h-Aktivierung und Outer-Rotation-State

**Status:** `NOT_STARTED`

Neue Entries erst `T+24h` und nach `flat_time`; altes Bundle bleibt exit-only, Rotation-State wird versioniert, hashbar und resume-fähig.

### Aufgabe 25 – Tägliches MTM-Ledger und zwei Zeitaggregationen

**Status:** `NOT_STARTED`

Daily MTM inklusive Nulltage; Deployment-Intervalle und UTC-Kalenderperioden werden ohne Doppelzählung getrennt ausgewertet.

### Aufgabe 26 – Monthly Quality Gate, Stress und Pflichtmetriken

**Status:** `NOT_STARTED`

Alle inneren, Outer-, Kalender-, Konzentrations-, Stress-, Nachbarschafts-, Regime-, DSR-, PBO- und Integritätsgates werden vorab eingefroren und fail-closed ausgewertet.

### Aufgabe 27 – Hindsight-Benchmarks, Capture-Ratios und Bootstrap

**Status:** `NOT_STARTED`

Hindsight bleibt reine Diagnostik; Capture-Ratios, Overfit-Sperren und reproduzierbarer Stationary Bootstrap trennen historische Zielerreichung von frischer Unterstützung.

### Aufgabe 28 – Aktuellen 730-Tage-Refit und Champion/Challenger/Cash-Entscheidung

**Status:** `NOT_STARTED`

Für den nächsten Anker wird deterministisch ein Bundle oder `NO_TRADE` mit Gültigkeit, Hashes, Vorgänger, Wechselgrund und Stress eingefroren; bis frische Evidenz bleibt alles `diagnostic_only`.

### Aufgabe 29 – Orderfreien Research-Challenger-Shadow bauen

**Status:** `NOT_STARTED`

Retrospektive Challenger erhalten eigenen Reporttyp, Storage, Controller und Forward-Ledger, bleiben strikt orderfrei und können nicht als kanonischer Adoption-Shadow angenommen werden.

### Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Status:** `NOT_STARTED`

Origins, Folds, Fortschritt, Safety, Ergebnisbedeutung und manuelle Challenger-Aktion werden korrekt angezeigt; keine vorzeitige Outer-PnL, Paper/Testtrade/Live/Orders bleiben gesperrt.

### Aufgabe 31 – Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr

**Status:** `NOT_STARTED`

Die monatlich refittende Pipeline wird in einem vorab registrierten neuen 365-Tage-Fenster genau einmal geprüft; nur dieser Pfad erzeugt einen Protocol-v3-Finalreport.

### Aufgabe 32 – End-to-End-Parität, Fehler-Injektion und vollständige Abnahme

**Status:** `NOT_STARTED`

Research, Replay, Cache, Resume und Challenger müssen bitgleich sein; Fehler-Injektionen und fixture-basierter 12-Origin-Dry-Run müssen vollständig grün sein.

### Aufgabe 33 – Erster vollständiger Protocol-v3-Research-Lauf und Abschlussbericht

**Status:** `NOT_STARTED`

Erst nach Aufgaben 1–32 werden zwölf Origins und 365 OOS-Tage einmalig ausgeführt; Ergebnis ist ehrlich `TARGET_REACHED`, `TARGET_NOT_REACHED` oder `NO_EDGE_FOUND`.

## Fortschrittsführung

```text
Protocol v3: Aufgabe 12/33 – Kompakte Artefaktarchitektur – DONE_100
Protocol v3: Aufgabe 13/33 – Content-addressed Cache und transaktionales Resume – NOT_STARTED
Gesamt: 12/33 DONE_100 = 36,36 %
```

Fortschritt wird ausschließlich als `DONE_100 / 33` ausgewiesen, nicht nach Zeit oder Token geschätzt.
