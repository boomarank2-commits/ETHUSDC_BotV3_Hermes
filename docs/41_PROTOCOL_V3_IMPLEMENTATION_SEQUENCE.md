# Protocol v3 – verbindliche Implementierungsreihenfolge

Stand: 2026-07-18
Quelle: `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 15/33 abgeschlossen

## Arbeitsregel

Es ist immer genau eine Aufgabe aktiv. Eine spätere Aufgabe beginnt erst, wenn die vorherige Aufgabe `DONE_100` besitzt.

`DONE_100` erfordert vollständig umgesetzten Umfang, Wiederverwendung vorhandener Funktionen, grüne Unit-/Integrations-/Negativtests, Python-Kompilierung, PowerShell-Syntax, Whitespace-Prüfung, dokumentierte Grenzen, keinen Vorgriff auf spätere Aufgaben und einen eindeutigen GitHub-Handoff. Paper, Testtrade, Live, Orders, private Endpunkte und API-Keys bleiben gesperrt.

## Aufgaben 1 bis 15 – abgeschlossen

### Aufgabe 1 – Protocol-v3-Vertrag versioniert übernehmen

**Status:** `DONE_100`

Blueprint, Projektvertrag, Agentenregeln sowie Portfolio-/Shadow-Vertrag wurden widerspruchsfrei als Vertragsgeneration 3.0.0 übernommen. Verbrauchter Audit bleibt `NOT_FRESH`; Legacy-Pfade können keinen Protocol-v3-Finalstatus erzeugen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_01_2026-07-13.md`

### Aufgabe 2 – Monatskalender und Boundary-Vertrag implementieren

**Status:** `DONE_100`

Exakt zwölf Origins, 730 Entwicklungstage je Origin, 365 lückenlose Prozess-OOS-Tage, UTC-Ankertag 8 und `T+24h`-Aktivierung sind als reine Boundary-Schicht umgesetzt.

**Bericht:** `handoff/PROTOCOL_V3_TASK_02_2026-07-14.md`

### Aufgabe 3 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren

**Status:** `DONE_100`

Pipelinegeneration, timestamp-freies Pre-Run-Manifest, deterministische Seeds, globale 12-Origin-Budgets und ausschließlich verkürzende Stopregeln sind eingefroren. Das 3-USDC-Ziel ist keine Suchverlust- oder Stopregel.

**Berichte:**
- `handoff/PROTOCOL_V3_TASK_03_2026-07-14.md`
- `handoff/PROTOCOL_V3_TASK_03_BUDGET_CORRECTION_2026-07-14.md`

### Aufgabe 4 – Permanentes Trial-Ledger und historischen Import bauen

**Status:** `DONE_100`

Versuche werden append-only, hashverkettet und generationsübergreifend erfasst. Der belegbare Altbestand bleibt eine Untergrenze mit 180 bekannten Bewertungszeilen und 0 vollständig aufgelösten unabhängigen Alt-Trials; deshalb bleibt nur `NO_TRADE` freigabefähig.

**Bericht:** `handoff/PROTOCOL_V3_TASK_04_2026-07-14.md`

### Aufgabe 5 – Dynamischen Drei-Markt-Datensnapshot und Warmup herstellen

**Status:** `DONE_100`

ETHUSDC, BTCUSDC und ETHBTC erhalten eine gemeinsame vollständige UTC-Watermark, exakte 1m-Rasterprüfung, Markt-/Archivdigests und `max(active lookbacks)+1 Quellbar` Warmup. Der reale bekannte Bestand bleibt `BLOCKED_MISSING_WARMUP`.

**Bericht:** `handoff/PROTOCOL_V3_TASK_05_2026-07-14.md`

### Aufgabe 6 – Exchange-Info-Snapshot und vollständige Run-Fingerprints bauen

**Status:** `DONE_100`

Öffentliche ETHUSDC-Exchange-Filter und zwölf Identitätsklassen sind immutable und SHA-256-gebunden. Private oder kontobezogene Schlüssel werden abgelehnt; Resume und Cache-Hit verlangen denselben vollständigen Run-Fingerprint v2.

**Bericht:** `handoff/PROTOCOL_V3_TASK_06_2026-07-14.md`

### Aufgabe 7 – Notional-, Mengen-, Gebühren- und Rundungsparität herstellen

**Status:** `DONE_100`

Requested und reserved bleiben exakt 100 USDC; executed bleibt wegen aktiver Raster höchstens 100 USDC. Gebühren, Slippage, Tick-/Step-Rundung, Notional und Exitmenge folgen dem eingefrorenen Binance-Spot-Vertrag; Compounding bleibt aus.

**Bericht:** `handoff/PROTOCOL_V3_TASK_07_2026-07-14.md`

### Aufgabe 8 – Next-Tradable-Price und pessimistische Intrabar-Ausführung

**Status:** `DONE_100`

Entry erfolgt nach geschlossener Signalbar am nächsten positiven Volumen-Open. Pending Entries verfallen deterministisch; Stop gewinnt bei Doppelberührung, Gaps werden pessimistisch gefüllt und Break-even/Trail gelten erst ab Folgebalken.

**Bericht:** `handoff/PROTOCOL_V3_TASK_08_2026-07-14.md`

### Aufgabe 9 – Warmup-, Purge-, Fold-End- und Outer-State-Maschine

**Status:** `DONE_100`

Warmup ist feature-only, Purge folgt dem maximalen Informationshorizont plus Ausführungsbar, innere Folds starten flat und enden konservativ. Zwischen Origins wird ausschließlich höchstens eine offene Altposition mit alter Exitlogik übernommen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_09_2026-07-14.md`

### Aufgabe 10 – Kontextparität und Drei-Markt-Watermark

**Status:** `DONE_100`

ETHUSDC ist einziges Handelssymbol; BTCUSDC und ETHBTC bleiben Kontext. Entscheidungen verlangen drei exakt ausgerichtete geschlossene 1m-Bars. Fehlender, versetzter, alter oder zukünftiger Kontext blockiert; Kontext kann nur ein ETHUSDC-Signal bestätigen oder vetoen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_10_2026-07-15.md`

### Aufgabe 11 – Protocol-v3-Report-Schemas und Evidenzbedeutung

**Status:** `DONE_100`

Getrennte, versionierte Reportarten und feste Roots existieren für Research, Monatsprozess-OOS, Research-Challenger, Forward-Monat und den späteren Pipeline-Finalreport. Historische Zielerreichung erzeugt weder Freshness noch statistische Unterstützung oder Adoption. Report- und Registrierungsleser prüfen feste Roots und Symlinks vor dem ersten Bytezugriff.

**Bericht:** `handoff/PROTOCOL_V3_TASK_11_2026-07-16.md`

**Re-Audit:** `handoff/PROTOCOL_V3_TASK_11_14_REAUDIT_2026-07-19.md`

### Aufgabe 12 – Kompakte Artefaktarchitektur

**Status:** `DONE_100`

Content-addressed Objekte sind von kleinen kanonischen Referenzindizes getrennt. Tatsächliche Bytes bestimmen Digest, Größe und Kardinalität; Elternreport, Run-Fingerprint, Pipelinegeneration und Work-Unit-Provenienz werden transitiv revalidiert. Die Indexpfad-Sperre sitzt sowohl in der öffentlichen Facade als auch importreihenfolgeunabhängig im Kernmodul vor dem ersten Read.

**Bericht:** `handoff/PROTOCOL_V3_TASK_12_2026-07-16.md`

**Korrekturberichte:**

- `handoff/PROTOCOL_V3_TASK_12_PATH_GUARD_CORRECTION_2026-07-16.md`;
- `handoff/PROTOCOL_V3_TASK_11_14_REAUDIT_2026-07-19.md`.

### Aufgabe 13 – Content-addressed Cache und transaktionales Resume

**Status:** `DONE_100`

**Abnahme:**

- Die Task-13-Grundlage bindet exakt 16 Pflichtidentitäten; fehlende, zusätzliche, umsortierte oder `None`-Slots blockieren.
- Checkpoints binden Pre-Run-Manifest, Seed, Budgets, Stop-/Stagnationszustand, Ergebnis, Artefaktköpfe, Ledger-Receipt und eine vollständige Hashkette.
- Nur ein separat atomar publiziertes `HEAD.json` macht einen Checkpoint für Resume sichtbar.
- Writer-Locks sind create-only; Recovery verlangt Same-Host-Dead-Process-Nachweis und erzeugt ein immutable Receipt. Ein vorhandenes altes Receipt darf niemals ein später neu erworbenes Lock löschen.
- Cache-Records entstehen nur aus dem aktuellen committed HEAD und revalidieren Task-12-Indizes, Objekte, Reports und Trial-Ledger transitiv.
- Cache-Reuse ist deterministisch, idempotent und zählt nicht als unabhängiger Trial. Checkpoint-, Cache- und Replace-Temp-Pfade blockieren als Symlinks oder Nicht-Dateien vor jedem Lesen.
- Der Task-4-/Task-13-Adapter bindet das echte Ledgerfeld `event_sha256`; ein fremder späterer Ledgerfortschritt blockiert.
- Durch Aufgabe 15 wurde der Vertrag ohne Lockerung fortgeschrieben zu `protocol_v3_content_addressed_cache_and_transactional_resume_with_inner_selection_v3`; Fold- und Kandidatenslot sind nun beide gebunden.

**Bericht:** `handoff/PROTOCOL_V3_TASK_13_2026-07-16.md`

**Korrekturberichte:**

- `handoff/PROTOCOL_V3_TASK_13_LEDGER_EVENT_ADAPTER_CORRECTION_2026-07-17.md`;
- `handoff/PROTOCOL_V3_TASK_11_14_REAUDIT_2026-07-19.md`.

### Aufgabe 14 – Exakten inneren 6×60-Tage-Fold-Planer bauen

**Status:** `DONE_100`

**Abnahme:**

- Vertrag `protocol_v3_exact_inner_6x60_day_folds_v1` erzeugt auf jedem exakt 730 Tage großen Entwicklungsfenster sechs chronologische, nicht überlappende 60-Tage-Validation-Folds.
- Die Validation-Union umfasst lückenlos exakt die letzten 360 Entwicklungstage.
- Die Fits beginnen am gemeinsamen `training_start`; ihre Spannen vor Purging betragen exakt 370, 430, 490, 550, 610 und 670 Tage.
- `fit_end = validation_start - purge_duration`; die Purge-Dauer stammt ausschließlich aus der Task-9-`HorizonPolicy`.
- Task-9-Boundary-Touch-Purge und ein fester maximaler Purge-Cutoff wirken gemeinsam; Trainingsevidenz bleibt nur innerhalb des halboffenen Fitintervalls `[fit_start, fit_end)`.
- Timestamp-Spies blockieren Fit-, Scaler-, Quantile-, Regime-, Validation-, Feature- und Labelzugriffe außerhalb ihrer kausalen Grenzen.
- Alle zwölf Origins aus drei Boundary-Fixtures, insgesamt 36 Origin-Fenster, besitzen dieselbe exakte Fold-Struktur.
- Der Transaktions-Fold-Slot muss `BOUND` sein und den vollständigen semantisch revalidierten Plan enthalten; alte `task14_not_implemented`-Identitäten blockieren.
- Fold-Plan und separate Transaktions-Horizon-Identität sind gegenseitig gebunden. Abweichende Label-, Holding-, Pending-Entry- oder Purge-Horizonte blockieren.
- Foldvertrag, Planermodul und öffentliche API sind pipelinegebunden; alte Cache-/Resume-Stände ohne Fold-Plan können nicht treffen.
- Der erneute Re-Audit korrigierte die zuvor übersehene untere Fit-Grenze: Warmup-Ereignisse vor `fit_start` können nicht als Fit-/Label-Evidenz erhalten bleiben.

**Bericht:** `handoff/PROTOCOL_V3_TASK_14_2026-07-17.md`

**Re-Audit:** `handoff/PROTOCOL_V3_TASK_11_14_REAUDIT_2026-07-19.md`

### Aufgabe 15 – Reine innere Auswahlfunktion extrahieren

**Status:** `DONE_100`

**Abnahme:**

- Der stabile öffentliche Einstieg `inner_selection_api.select_candidate(training_window, frozen_pipeline_config)` verwendet ausschließlich explizite immutable Eingaben. Core und Facade besitzen dieselbe im Kern definierte fail-closed Entscheidungsfunktion; kein Import-Monkey-Patch verändert das Verhalten.
- UI, aktuelle Uhrzeit, Umgebung, Netzwerk, implizite Arbeitsverzeichnisdateien und Outer-Ergebnisse sind ausgeschlossen.
- Das Training-Window enthält exakt 730 UTC-Tage und ist vollständig an den semantisch revalidierten Task-14-Fold-Plan gebunden.
- Manifest, Run-Fingerprint, Pipelinegeneration, Code, Daten, Kontext, Kosten, Simulator, Gates, Exchange-Info, Trial-Ledger, Origin, Zyklus und Seed werden gegenseitig gebunden.
- Kandidateninventare bleiben innerhalb 40 generated, 12 tested, 3 Full-WFV und 2 Finalisten und müssen verschachtelte eindeutige Teilmengen sein.
- Die Rangfolge ist exakt: Worst Fold, Median Fold, aggregiertes WFV, Joint Stress, Drawdown, Friktionsanteil, freie Parameter, kanonische Kandidaten-ID.
- Das 3-USDC-Ziel ist kein Ranking-, Loss-, Distanz- oder Stopwert.
- Gates werden aus Evidenz neu berechnet; behauptete Freigaben werden nicht vertraut.
- Fehlende oder widersprüchliche Evidenz erzeugt typisiertes `NO_TRADE` mit maschinenlesbaren Blockern statt Ausnahme oder stiller Auswahl.
- Bis Aufgaben 16 bis 18 bleibt der einzige produktiv transaktionsfähige Zustand `NO_TRADE`.
- Synthetische vollständige Evidenz ist ausschließlich Testfixture und wird am Transaktionsrand abgelehnt.
- Candidate-`NOT_APPLICABLE/task15_not_implemented` ist nicht mehr zulässig; der Kandidatenslot muss `BOUND` sein.
- Transaktionsvertrag und Identität wurden zu v3 fortgeschrieben; alte Cache-/Resume-Stände ohne gebundene Auswahlentscheidung können nicht treffen. Das Kernmodell besitzt diese v3-Wahrheit selbst und lädt den JSON-Vertrag unabhängig von der Importreihenfolge.
- Aufgabe 16 oder später wurde nicht vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_15_2026-07-18.md`

**Korrekturbericht:** `handoff/PROTOCOL_V3_TASK_15_IMPORT_ORDER_CORRECTION_2026-07-19.md`

## Aufgaben 16 bis 33 – verbindliche Reihenfolge

### Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets

**Status:** `NOT_STARTED` – exakt nächste Aufgabe

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
Protocol v3: Aufgabe 15/33 – Reine innere Auswahlfunktion extrahieren – DONE_100
Protocol v3: Aufgabe 16/33 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets – NOT_STARTED
Gesamt: 15/33 DONE_100 = 45,45 %
```

Fortschritt wird ausschließlich als `DONE_100 / 33` ausgewiesen, nicht nach Zeit oder Token geschätzt.
