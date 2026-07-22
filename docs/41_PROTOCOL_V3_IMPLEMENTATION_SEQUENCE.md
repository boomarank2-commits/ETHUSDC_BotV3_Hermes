# Protocol v3 – verbindliche Implementierungsreihenfolge

Stand: 2026-07-22
Quelle: `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
Status: Protocol-v3-Vertragsgeneration 3.0.0 aktiv; Umsetzung 32/33 abgeschlossen

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
- Durch Aufgabe 29 wurde der Vertrag versioniert zu `protocol_v3_content_addressed_cache_and_transactional_resume_with_inner_selection_and_production_candidates_v4`; Fold- und Kandidatenslot bleiben vollständig gebunden, echte Task-16→17→18-Produktionskandidaten sind zulässig und synthetische Fixtures bleiben blockiert.

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
- Aufgaben 16 bis 18 sind abgeschlossen. Seit Aufgabe 29 darf Task 13 neben `NO_TRADE` ausschließlich eine echte, vollständig validierte produktive `CANDIDATE`-Entscheidung binden; synthetische Evidenz bleibt unzulässig.
- Synthetische vollständige Evidenz ist ausschließlich Testfixture und wird am Transaktionsrand abgelehnt.
- Candidate-`NOT_APPLICABLE/task15_not_implemented` ist nicht mehr zulässig; der Kandidatenslot muss `BOUND` sein.
- Transaktionsvertrag und Identität stehen nach Aufgabe 29 auf v4; alte Cache-/Resume-Stände ohne gebundene beziehungsweise produktionsgültige Auswahlentscheidung können nicht treffen. Das Kernmodell besitzt diese Wahrheit selbst und lädt den JSON-Vertrag unabhängig von der Importreihenfolge.
- Aufgabe 16 oder später wurde nicht vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_15_2026-07-18.md`

**Korrekturbericht:** `handoff/PROTOCOL_V3_TASK_15_IMPORT_ORDER_CORRECTION_2026-07-19.md`

## Aufgaben 16 bis 33 – verbindliche Reihenfolge

### Aufgabe 16 – Vollständige Kandidaten-Tagesmatrix und Promotion-Budgets

**Status:** `DONE_100`

**Abnahme:**

- Jede deklarierte getestete Kandidateninstanz besitzt sechs an den Task-14-Plan gebundene 60-Tage-Reihen und damit exakt dieselbe geordnete 360-Tage-Netto-MTM-Basis.
- Nulltage bleiben explizite `0.0`; fehlende, zusätzliche, doppelte, umsortierte oder nichtfinite Tageswerte blockieren.
- Alle getesteten Profile aller Cycles bleiben in der Origin-Matrix, unabhängig von Promotion oder Finalistenstatus.
- Profile, Foldprovenienz, Tagesraster, Tagesinhalt, Cycles und Gesamtmatrix sind kanonisch gehasht und semantisch revalidiert.
- Promotion bleibt eine verschachtelte Teilmenge innerhalb `tested <= 12`, `promoted <= min(3, tested)` und `finalists <= min(2, promoted)`; kleine oder leere legitime Inventare werden nicht aufgefüllt.
- Jede datenbewertete Reihe muss exakt mit einem immutable Trial im permanenten Ledger übereinstimmen. Cache-Reuse benötigt ein sichtbares Origin-/Cycle-Receipt und erhöht den unabhängigen Trial-Count nicht.
- Foldwerte werden ausschließlich als tägliche Netto-MTM-Deltas verkettet; Fold-Resets absoluter Equity werden nicht als zusätzliche PnL interpretiert.
- Die reine Task-15-Auswahl kann produktive Task-16-Matrixevidenz konsumieren, bleibt ohne Task-17-PBO und Task-18-DSR typisiert `NO_TRADE`.
- PBO, DSR, Features, Regime und Outer-Ergebnisse wurden nicht vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_16_2026-07-19.md`

### Aufgabe 17 – PBO/CSCV exakt implementieren

**Status:** `DONE_100`

**Abnahme:**

- PBO konsumiert ausschließlich die vollständige, ledgergebundene Task-16-Origin-Matrix aller getesteten Profile.
- Zwölf chronologische 30-Tage-Blöcke erzeugen lexikographisch exakt `C(12,6)=924` eindeutige IS-Kombinationen mit jeweils 180 IS- und 180 komplementären OOS-Tagen.
- IS-Auswahl verwendet die mittlere tägliche Netto-MTM-PnL; Gleichstand entscheidet primär die kanonische Kandidaten-ID und bei gebundenem Cache-Reuse sekundär die kanonische Profil-ID.
- Eine immutable Cash-/`NO_TRADE`-Nullspalte mit kanonischer ID nimmt an jeder IS-Auswahl und jedem OOS-Rang teil, zählt aber weder als Trial noch zum Minimum von zwei Tradingprofilen.
- OOS-Gleichstände verwenden den exakten Durchschnittsrang mit `1=schlechtester`, `M=bester`; Omega, Lambda und `development_pbo` werden ohne Zwischenrundung berechnet.
- Der separate Cash-Vergleich verlangt je Tradingprofil einen strikt positiven aggregierten 360-Tage-Mittelwert; Gleichstand reicht nicht.
- Weniger als zwei Tradingprofile liefert typisiertes `INSUFFICIENT_EVIDENCE` ohne numerischen Ersatzwert.
- Golden Fixtures belegen konstante positive Reihen mit `PBO=0`, spiegelbildliche Überanpassung mit `PBO=1` und identische Nullreihen mit `PBO=1`.
- Die Task-15-Auswahl konsumiert produktive Task-17-Evidenz, bleibt ohne Task-18-DSR aber typisiert `NO_TRADE`.
- DSR, Outer-Bootstrap und Monthly Gates wurden nicht vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_17_2026-07-19.md`

### Aufgabe 18 – DSR und Multiple-Testing-Diagnostik implementieren

**Status:** `DONE_100`

DSR bindet permanenten Trial-Count, Autokorrelation, Schiefe und Kurtosis; unvollständige Trial-Historie oder ungültige Statistik blockiert.

**Abnahme:**

- DSR konsumiert für den ausgewählten Trading-Kandidaten exakt dieselbe ledgergebundene 360-Tage-Netto-MTM-Reihe wie Task 16 und dieselbe vollständige Task-17-PBO-Identität.
- `SR` verwendet den unannualisierten Tagesmittelwert und die Stichprobenstandardabweichung mit `ddof=1`; `K=5`, Bartlett-gewichteter VIF und `n_eff` sind ohne Zwischenrundung reproduzierbar.
- Schiefe ist der adjustierte Fisher-Pearson-Schätzer `G1`; Kurtosis ist der unverzerrte Fisher-Exzessschätzer `G2` plus drei als Pearson-Kurtosis.
- `N_raw` stammt ausschließlich aus dem erneut validierten vollständigen permanenten Trial-Ledger. `N_eff_trials` aus der gemeinsamen Pearson-Korrelationsmatrix bleibt reine Diagnostik und ersetzt `N_raw` nicht.
- Nullvarianz, ungültiger DSR-Nenner, weniger als zwei vollständige Trials oder fehlendes gemeinsames Tagesraster ergeben typisiertes `INSUFFICIENT_EVIDENCE` ohne numerischen Ersatzwert.
- Die belegbar unvollständige reale historische Trial-Inventur bleibt `INSUFFICIENT_TRIAL_HISTORY`; dadurch bleibt `NO_TRADE` die einzige zulässige Freigabeentscheidung.
- Cash ist explizit `NOT_APPLICABLE_NO_TRADE` und erhält weder einen künstlichen DSR-Wert noch einen Gate-Pass.
- Task-15 kann produktive Task-18-Identitäten konsumieren; Matrix-, PBO-, Profil-, Origin-, Cycle- und aktueller Ledger-Head werden vor dem Einfrieren fail-closed gegengeprüft.
- Golden Fixtures fixieren sämtliche wesentlichen Zwischenwerte; Manipulationen, veraltete Ledger-Heads und numerische Ersatzwerte blockieren.
- Feature Store, Regime, Outer-Bootstrap und Monthly Gates wurden nicht vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_18_2026-07-19.md`

### Aufgabe 19 – Kausalen Multi-Timeframe-Feature-Store bauen

**Status:** `DONE_100`

Nur abgeschlossene 5m/15m/30m/1h/4h/1d- sowie Wochen-/Monatsfeatures; Scaler, Quantile und Feature-State sind fold-sicher, hashbar und replaybar.

**Abnahme:**

- Der Store konsumiert ausschließlich den semantisch validierten gemeinsamen Task-10-Drei-Markt-Kontext und bindet dessen Snapshot-, Grid-, Marktinhalt- und Kontextidentität.
- `ETHUSDC`, `BTCUSDC` und `ETHBTC` besitzen dieselben eingefrorenen Zeitebenen `5m/15m/30m/1h/4h/1d/1w/1mo`; Kontextmärkte erhalten weiterhin keinerlei Orderrecht.
- Feste Zeitebenen sind UTC-epochverankert, Wochen beginnen Montag 00:00 UTC und Monate folgen exakten UTC-Kalendergrenzen.
- Erste und letzte Teilbuckets sowie jeder nicht exakt vollständige Bucket werden nicht emittiert. Der Informationstimestamp ist immer das exklusive Bar-Ende; Snapshots dürfen nur Bars mit `close_time_exclusive_ms <= context_timestamp_ms` lesen.
- Die feste Task-19-Featurebasis umfasst kausalen Vorbar-Return, Range, Body, Close-Position und Volumen. Opportunity- und Regimeklassifikation bleibt ausdrücklich Aufgabe 20.
- Scaler und Type-7-Quantile werden je Task-14-Fold nur aus Bars mit `open>=fit_start` und `close<=fit_end` gefittet; Warmup geht nicht in Fit-Statistiken ein.
- Feature Store und Fold-Fit-State besitzen kompakte SHA-256-Identitäten, vollständige Replay-Validierung und unveränderte Safety Locks ohne Signal- oder PnL-Recht.
- Präfix-Replay, unfertige Bars, zukünftige Snapshot-Zugriffe, neu gehashte Manipulationen und abweichende Foldgrenzen sind getestet und blockieren fail-closed.
- Opportunity/Regime, Spezialisten, Router und Outer-Orchestrierung wurden nicht vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_19_2026-07-19.md`

### Aufgabe 20 – Opportunity- und Regime-Schicht implementieren

**Status:** `DONE_100`

Bewegungskapazität, Trend, Range, Kompression und Stress werden kausal erkannt; unbekanntes oder widersprüchliches Regime führt `NO_TRADE`.

**Abnahme:**

- Die Schicht konsumiert ausschließlich den Task-19-Feature-Store, dessen foldgebundenen Fit-State und dieselbe Task-14-Foldidentität; Source-Replay gegen den Task-10-Kontext bleibt Pflicht.
- Realisierte 24h-Volatilität, 14h-ATR, erwartete 20h-Range, 4h-Kompression, 24h-Trend, Trend-Effizienz, robuster 4h-Anker, Pullback-Tiefe sowie BTCUSDC-/ETHBTC-Kontext werden nur aus abgeschlossenen Bars berechnet.
- Alle Regimegrenzen werden ausschließlich aus dem jeweiligen Fold-Fitintervall als Type-7-Quantile gefittet; mindestens 60 vollständige kausale Metrikzeilen sind Pflicht und Warmup bleibt ausgeschlossen.
- Die vorhandenen vier Quality-Gate-Regime `down_low/down_high/up_low/up_high` bleiben kompatibel und werden um getrennte Opportunity-, Range- und Strukturdiagnostik ergänzt.
- Opportunity bewertet nur Bewegungskapazität und bestimmt niemals die Long-Richtung.
- `TREND`, `COMPRESSION` und `RANGE` erzeugen lediglich einen unverbindlichen Familienhinweis für den späteren Router. Sie wählen weder Strategie noch Signal.
- `STRESS`, niedrige Opportunity, widersprüchlicher Drei-Markt-Kontext, unbekannte Struktur und unvollständiger Warmup erzwingen jeweils `NO_TRADE`.
- Fit-State und Assessment sind kompakt identitätsgebunden und werden vollständig aus Store, Feature-Fit, Fold und Kontextzeitpunkt replayt.
- Spezialisten, Router, Outer-Orchestrierung und Orders wurden nicht vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_20_2026-07-19.md`

### Aufgabe 21 – Lokale Spezialisten hinter der bestehenden Engine bauen

**Status:** `DONE_100`

Pullback/Reclaim, Breakout/Retest, bestätigte Range-Reversion und Mehrtagesswing werden als kleine begrenzte Familien hinter derselben Engine geprüft.

**Abnahme:**

- Vier begrenzte Spezialisten mappen exakt auf die vorhandenen Engine-Familien `pullback_in_trend`, `breakout_volatility_filter`, `mean_reversion_regime_filter` und `momentum_trend_filter`; eine zweite Simulationsengine existiert nicht.
- `trend_pullback_reclaim` verlangt Task-20-`TREND`, einen abgeschlossenen 15m-Pullback und anschließenden Reclaim.
- `compression_breakout_retest` verlangt Task-20-`COMPRESSION`, abgeschlossenen 15m-Breakout und gehaltenen Retest statt Impulskauf.
- `range_reversion_confirmed` verlangt Task-20-`RANGE` und Wiedereintritt in die abgeschlossene 15m-Range.
- `multiday_swing_trend` verlangt Task-20-`TREND` sowie ausgerichteten abgeschlossenen 1d-/4h-Trend und besitzt einen klar begrenzten Mehrtages-Haltehorizont.
- Der Spezialisten-Gate darf ausschließlich ein bereits vorhandenes Rohsignal der Basisengine bestätigen. Ohne Rohsignal, bei Regime-Mismatch, fehlender Bestätigung oder `no_trade` bleibt `allowed=false`.
- ETHUSDC, LONG-only, Haltezeitgrenzen, kanonische Bundle-Identität und Safety Locks werden fail-closed validiert.
- Spezialisten liefern nur Filterevidenz. Auswahl zwischen Spezialisten und lokaler Edge-Nachweis bleiben Aufgabe 22.

**Bericht:** `handoff/PROTOCOL_V3_TASK_21_2026-07-19.md`

### Aufgabe 22 – Router, NO_TRADE und FrozenCandidateBundle verbinden

**Status:** `DONE_100`

Router wählt genau einen Spezialisten oder `NO_TRADE`; Bundle bindet Parameter, Fit-State, Features, Kontext, Kosten, Rotation und Gültigkeit.

**Umgesetzt:**

- `NO_TRADE` ist der deterministische Default. Ein Spezialist wird nur bei vollständiger Task-15-Auswahl, exakt revalidiertem Task-20-Assessment, eindeutiger Task-21-Familienzuordnung und bestandenem Local-Edge-Replay im identischen Regime gewählt.
- Das Local-Edge-Replay umfasst exakt sechs chronologische 60-Tage-Folds mit 360 vollständigen specialist-gefilterten Netto-MTM-Tageszeilen. Tagesraster, Foldprovenienz, Netto-/Bruttoarithmetik, Mindest-Trades, Profit-Factor und positive Fold-Untergrenze werden semantisch berechnet; der Replay-Hash wird aus dem Inhalt abgeleitet.
- Das gehashte `FrozenCandidateBundle` bindet Routerentscheidung, Spezialistenbundle, skalare Parameter, Task-19-Scaler/Quantile und Feature-Identität, Task-20-Quantile, Drei-Markt-Kontextpolicy, Kostenmodell, Auswahl-/Edge-Evidenz, Vorgänger, Rotation und Gültigkeit.
- `valid_from` ist exakt `as_of+24h`; maximal ein Lot, Exit-only-Vorgänger und Flat-Handoff sind eingefroren. Der konkrete resume-fähige Runtime-Rotation-State bleibt strikt Aufgabe 24.
- Synthetische Fixtures bleiben nicht routbar. Alle Routerentscheidungen bleiben transaktionsunfähig; Orders, Paper, Testtrade, Live und Trading-API bleiben gesperrt.

**Bericht:** `handoff/PROTOCOL_V3_TASK_22_2026-07-19.md`

### Aufgabe 23 – Zwölf äußere Monats-Origins orchestrieren

**Status:** `DONE_100`

Die unveränderte Auswahlpipeline läuft an zwölf Fit-Stichtagen auf den jeweils vorherigen 730 Tagen; 365 OOS-Tage bleiben lückenlos und spätere Fits sehen frühere OOS-Ergebnisse nicht.

**Umgesetzt:**

- Der Orchestrator konsumiert ausschließlich den kanonischen Task-2-Boundaryplan und exakt zwölf geordnete Origin-Requests. Für jede Origin konstruiert er aus dem Task-14-Foldplan das exakte 730-Tage-Trainingsfenster und ruft intern den unveränderten Task-15-Einstieg `select_candidate(...)` auf.
- Feature-Store- und Task-20-Assessment-Cutoff müssen exakt dem jeweiligen Fit-/Testanker entsprechen. Jede Auswahl wird an genau eine Task-22-Routerentscheidung und genau ein vollständiges `FrozenCandidateBundle` mit der Intervallgültigkeit dieser Origin gebunden.
- Alle zwölf Origins müssen dieselbe Pipelinegeneration und denselben Code-Commit verwenden; ihre Fit-Cutoffs sind strikt chronologisch und eindeutig. Die vereinigte OOS-Tagesmenge wird semantisch als exakt 365 eindeutige, lückenlose UTC-Tage validiert.
- Der Auswahlpfad besitzt keinen Outer-Ergebniskanal. Frühere rohe Marktbeobachtungen dürfen später innerhalb des kausalen 730-Tage-Fensters gelesen werden; frühere PnL, Rankings, Reports, Gate-Ergebnisse und menschliche Interpretationen werden durch einen expliziten Isolation-Guard blockiert.
- Rotation/Flat-Handoff bleibt Aufgabe 24; tägliches MTM, Trades und Zeitaggregation bleiben Aufgabe 25. Damit werden keine späteren Aufgaben vorgezogen.

**Bericht:** `handoff/PROTOCOL_V3_TASK_23_2026-07-19.md`

### Aufgabe 24 – 24h-Aktivierung und Outer-Rotation-State

**Status:** `DONE_100`

Neue Entries erst `T+24h` und nach `flat_time`; altes Bundle bleibt exit-only, Rotation-State wird versioniert, hashbar und resume-fähig.

- Der bereits in Aufgabe 9 eingefrorene semantische Rotationszustand bleibt die einzige Runtime-Wahrheit: erster Origin flat, höchstens ein getragenes Lot, Vorgänger strikt `exit_only`, keine Pending-Entry-/Cooldown-/Scaler-/Modellzustände und Entry-Freigabe exakt bei `max(valid_from, flat_time)`.
- Persistierter Zustand wird aus kanonischem JSON rekonstruiert und erneut vollständig semantisch validiert. Nichtkanonische Zeitstempel, fehlende oder zusätzliche Felder und selbst neu gehashte Widersprüche werden fail-closed abgewiesen.
- Die gebundene Rotation-Identity verknüpft exakt Task-23-Prozess/Origin/Selection mit dem Task-22-Frozen-Bundle und dem Task-13-Transaktionsvertrag. Ein Origin-, Selection-, Bundle- oder Zustandswechsel erzeugt eine andere Transaktions-, Cache- und Resume-Identität.
- Der bisherige kanonische Genesis-Slot bleibt für vorgelagerte Inner-Transaktionen kompatibel. Sobald ein Outer-Rotationszustand existiert, ist nur der konkrete Task-24-Bound-Slot resume-fähig; es wurde kein zweiter Zustandskanal geschaffen.
- Tägliches MTM, Trades und die beiden Zeitaggregationen bleiben strikt Aufgabe 25.

**Bericht:** `handoff/PROTOCOL_V3_TASK_24_2026-07-19.md`

### Aufgabe 25 – Tägliches MTM-Ledger und zwei Zeitaggregationen

**Status:** `DONE_100`

Daily MTM inklusive Nulltage; Deployment-Intervalle und UTC-Kalenderperioden werden ohne Doppelzählung getrennt ausgewertet.

- Die zwölf Task-23-Origin-Ergebnisse und ihre Task-24-Rotationszustände werden zu exakt 365 eindeutigen, lückenlosen UTC-Tageszeilen verkettet. Jeder Tageswert ist das exakte Delta der fortlaufenden Closing-Equity; Origin-Grenzen dürfen die Equity nicht zurücksetzen.
- Explizite Nulltage bleiben erhalten. Fehlende, zusätzliche, doppelte, umsortierte oder nichtfinite Werte sowie gebrochene Equity-Deltas blockieren fail-closed.
- MTM-PnL wird parallel, aber strikt getrennt nach den zwölf Deployment-Intervallen sowie allen berührten UTC-Kalendermonaten und -quartalen aggregiert. Exit-Trades gehören ausschließlich zum UTC-Exit-Zeitpunkt; Gebühren und Slippage zu konkreten Ausführungstagsereignissen.
- MTM-Gesamt-PnL ist die primäre Prozesswahrheit. Closed-Trade-Netto bleibt eine getrennte, am flachen Prozessende exakt abzustimmende Diagnose und wird niemals ein zweites Mal zum MTM-Ergebnis addiert.
- Grenzüberschreitende Trades müssen zum getragenen Task-24-Exit-only-Lot gehören. Eine Terminal-Liquidation ist ausschließlich am letzten Tag des gesamten Prozesses zulässig.
- Gates, Stressmetriken und Grenzwerte bleiben strikt Aufgabe 26.

**Bericht:** `handoff/PROTOCOL_V3_TASK_25_2026-07-19.md`

### Aufgabe 26 – Monthly Quality Gate, Stress und Pflichtmetriken

**Status:** `DONE_100`

Alle inneren, Outer-, Kalender-, Konzentrations-, Stress-, Nachbarschafts-, Regime-, DSR-, PBO- und Integritätsgates werden vorab eingefroren und fail-closed ausgewertet.

- `monthly_quality_gate_v1` ist als reiner, content-gehashter Evaluator umgesetzt. Die bereits eingefrorenen inneren Quality-/Nachbarschafts-/DSR-/PBO-/Cash-Belege werden ausschließlich aus den semantisch validierten Task-23-Auswahlentscheidungen übernommen; `NO_TRADE` besteht nur die Origin-Integrität und niemals ein Trading-Gate.
- Outer-, Deployment-, UTC-Monats-/Quartals-, Drawdown-/Underwater-, Trade-, Konzentrations-, Friction- und No-Trade-Gap-Metriken werden aus dem erneut validierten Task-25-Baseline-Ledger abgeleitet. Gemeldete Metrikclaims werden nicht blind übernommen.
- Joint- und Slippage-Stress konsumieren getrennte, erneut validierte Task-25-Ledger. Exakte 10/5-, 15/10- und 10/15-bps-Szenarien sowie derselbe Simulator werden durch eine content-gehashte Stress-Identity belegt.
- Regime- und sämtliche Integritätsbelege benötigen eigene Inhaltsdigests. Fehlende, falsche oder nackte Bool-Claims blockieren fail-closed.
- `GREEN` verlangt Robustheit und historisch mindestens 3 USDC/Kalendertag; `YELLOW` bedeutet ausschließlich `robustness_passed_ex_target`; sonst gilt `RED`. Jeder historische Status bleibt `diagnostic_only`, `NOT_FRESH`, nicht statistisch unterstützt und nicht adoption-/finalfähig.
- Hindsight, Capture-Ratios und Stationary Bootstrap bleiben strikt Aufgabe 27.

**Bericht:** `handoff/PROTOCOL_V3_TASK_26_2026-07-19.md`

### Aufgabe 27 – Hindsight-Benchmarks, Capture-Ratios und Bootstrap

**Status:** `DONE_100`

Hindsight bleibt reine Diagnostik; Capture-Ratios, Overfit-Sperren und reproduzierbarer Stationary Bootstrap trennen historische Zielerreichung von frischer Unterstützung.

**Abnahme:**

- `all_candle_one_trade_close_hindsight` läuft auf exakt 365 vollständigen UTC-Tagen beziehungsweise 525.600 geordneten ETHUSDC-1m-Kerzen, nutzt ausschließlich positive Volumenpunkte und erlaubt höchstens einen LONG-Roundtrip je UTC-Tag.
- `candidate_matched_volume_filtered_hindsight` ist ein echter ein-Lot-/LONG-only-Solver mit der aus dem Baseline-Ledger abgeleiteten maximalen tatsächlichen Tradezahl, der eingefrorenen Kandidaten-Haltedauer, T+24, Bundle-Gültigkeit, Monatsrotation und Exit-only-/Flat-Handoff.
- Beide Solver verwenden dieselbe Task-7-/8-Ausführungs-, Rundungs-, Exchange-, Gebühren- und Slippage-Logik; Monatsgrenzen liquidieren nicht und der Prozessend-Close folgt derselben Task-24-Terminalausführung.
- Frozen-Data-Snapshot, alle 365 ETHUSDC-Tagesdigests, vollständiger Prozessdatenhash, Exchange Info, Execution Rules, Solver-Code und Pipelinegeneration sind transitiv gebunden.
- Die vollständige Task-22-Bundle-Kette, alle Task-23-Origin-Hashes/Run-Fingerprints, alle Task-24-Rotationszustände und das Task-25-Ledger sind semantisch gebunden. Persistierte Bindings verlangen vollständiges Quellen-Replay.
- Der frühere freie `benchmark_evidence`-/Caller-Claim-Kanal ist entfernt. Capture-Ratios werden ausschließlich aus den gebundenen Solver-Ausgaben berechnet und dürfen Auswahl oder Monthly Gate niemals beeinflussen.
- Der deterministische 10.000er Circular-Stationary-Bootstrap für `L={5,10,20}`, Manifest-/Seed-Bindung, exakt 500. Ordnungsstatistik und manuelle Leakage-/Overfit-Sperre bleiben erhalten.
- Fehlende/doppelte Tage oder Minuten, ungültiges Volumen, Lookahead, zu viele Trades, überschrittene Haltedauer, überlappende Trades sowie neu gehashte Bundle-, Origin-, Handoff-, Kosten-, Hash-, Feedback-, Freshness- und Adoption-Manipulationen blockieren fail-closed.
- Sämtliche historischen Ergebnisse bleiben `NOT_FRESH`, `diagnostic_only`, `statistically_supported=false`, `sealed_bootstrap_target_supported=false` und `canonical_adoption_eligible=false`.

**Bericht:** `handoff/PROTOCOL_V3_TASK_27_2026-07-19.md`

### Aufgabe 28 – Aktuellen 730-Tage-Refit und Champion/Challenger/Cash-Entscheidung

**Status:** `DONE_100`

Für den nächsten Anker wird dieselbe unveränderte Task-15-/Task-22-Einzel-Origin-Pipeline exakt auf `[T-730 Tage,T)` ausgeführt und ein vollständig gebundenes Bundle oder fail-closed `NO_TRADE` eingefroren.

**Abnahme:**

- Zielanker, Drei-Markt-Snapshot, `snapshot_as_of_day=T-1`, gemeinsamer letzter vollständiger Tag `T-1` und exaktes Rohdatenende `T` werden vor der Auswahl semantisch geprüft; stale, zukünftige oder falsch abgeschnittene Daten blockieren.
- Code-Commit, Pipelinegeneration, Run-Fingerprint, Exchange Info, Kosten-/Execution-/Gate-Quellen, Trial-Ledger, Task-14-Fold, Seed, Feature-/Regime-Fit-State und Kontextidentität sind transitiv gebunden.
- Das aktuelle `FrozenCandidateBundle` bindet den unmittelbaren Task-23-Vorgänger, `valid_from=T+24h`, den nächsten Monatsanker als `valid_until`, Task-24-Rotation und `entry_enabled_at_utc`.
- `CHAMPION`, `CHALLENGER` oder `CASH` werden ausschließlich aus der aktuellen unveränderten Auswahl, erneutem Champion-Test, aktueller Ranking-/Gate-/DSR-/PBO-/Cash-Evidenz und aktuellem Routerausgang deterministisch abgeleitet.
- Historische Baseline-, Joint-, Slippage-, Monthly-Gate- und Task-27-Hindsight-Evidenz bleibt reine `NOT_FRESH`-Provenienz und besitzt keinen Rückwirkungskanal in Auswahl oder Router.
- Persistierte Ausgaben verlangen vollständiges Quellen-Replay. Frühe/späte Anfrage, falsches Fenster, falscher Vorgänger, abgelaufene Gültigkeit, Rotations-, Stress-, Entscheidungs-, Freshness-, Adoption- oder Start-Manipulationen blockieren fail-closed.
- Jede Ausgabe bleibt `NOT_FRESH`, `diagnostic_only`, `canonical_adoption_eligible=false`, `sealed_final_holdout_used=false` und `bot_start_allowed=false`.

**Bericht:** `handoff/PROTOCOL_V3_TASK_28_2026-07-20.md`

### Aufgabe 29 – Orderfreien Research-Challenger-Shadow bauen

**Status:** `DONE_100`

Retrospektive Challenger besitzen einen eigenen Reporttyp, erlaubten Storage-Root, orderfreien Controller und ein pipelinegebundenes Forward-Ledger, können aber niemals als kanonischer Adoption-Shadow angenommen werden.

**Abnahme:**

- Startprovenienz ist ausschließlich eine vollständig validierte Task-28-Entscheidung; Start ist manuell und erzeugt keinen rückwirkenden Forward-Backfill.
- ETHUSDC ist einziges virtuelles Handelssymbol. BTCUSDC und ETHBTC bleiben exakt geschlossener, ausgerichteter Kontext ohne Orderrecht.
- Die bestehende inkrementelle Task-8-Intrabar-/Execution-/Kostenlogik wird wiederverwendet; Ende eines Datenpräfixes liquidiert nicht künstlich und höchstens ein Lot bleibt erlaubt.
- Warmup erzeugt keine Signale, Fills, PnL oder Ledgerzeilen. Forward-Einträge beginnen exakt an der manuellen Aktivierungsminute.
- Das append-only SHA-256-Ledger bindet Pipelinegeneration, Task-28-Bundle, Snapshot, Kontext, Exchange Info, Execution, Kosten, Kerzeninhalt, virtuelle Events, Position, MTM und Closing Equity.
- Eigene Task-11-Reports und Task-12-Artefakte speichern Trades, Daily MTM, Equity/Underwater und Diagnostik content-addressed; Rohkerzen werden nicht in Reports oder Checkpoints kopiert.
- Task-13 speichert nur kompakte Receipts. Resume verlangt atomaren HEAD, vollständigen öffentlichen Präfix-Replay und bitgleichen State-/Ledger-/Cursor-/Safety-Nachweis.
- Familien-, Feature-, Controller-, Execution- oder Pipelinewechsel erzeugt eine neue Generation, einen neuen Namespace und ein leeres Forward-Ledger.
- Der Task-13-Vertrag v4 erlaubt echte vollständig validierte Task-16→17→18-Produktionskandidaten; Fixture-, Cross-Generation-, Hash-, Side-Effect-, Freshness-, Adoption- und Finalmanipulationen blockieren.
- Sämtliche Ausgaben bleiben `NOT_FRESH`, `diagnostic_only`, nicht statistisch unterstützt, nicht adoptionfähig und nicht final. Orders, Paper, Testtrade, Live, private Endpunkte und API-Keys bleiben gesperrt.

**Bericht:** `handoff/PROTOCOL_V3_TASK_29_2026-07-20.md`

### Aufgabe 30 – UI und Bedienzustände vollständig anschließen

**Status:** `DONE_100`

Das bestehende Operator-Dashboard zeigt genau einen fail-closed Protocol-v3-Zustand. Origins, Folds, Cycles, Kandidatenfortschritt, aktueller Rechenschritt, Drei-Markt-Watermark, Monatsrefit, Research-Challenger, Finalfenster und kanonischer Shadow sind semantisch getrennt.

**Abnahme:**

- Task-28-/29-/13-Evidenz wird nur typisiert und transitiv validiert in die read-only UI-Bridge übernommen; rohe JSON-, Bool- oder Dateifund-Claims können keinen Button aktivieren.
- Manueller Start verlangt aktuelle geschlossene Drei-Markt-Daten, passende Pipelinegeneration, gültiges Task-28-Fenster, Exchange-Info-Parität und einen öffentlichen checkpointfähigen Backend-Worker.
- Resume verlangt bitgleichen State, Checkpoint-Receipt, Ledger-Head und dieselbe Generation. Uncheckpointed In-Memory-State ist nicht resume-fähig.
- Der Task-29-Controller bleibt asynchron, kooperativ stoppbar, orderfrei und strikt von kanonischer Adoption getrennt.
- Restart, Refresh und wiederholtes Öffnen verändern keine Research-, Signal-, Fill-, Ledger-, Report- oder Checkpointidentität.
- Historisches Prozess-OOS, aktueller Refit, späteres Finalfenster und kanonischer Shadow besitzen getrennte sichtbare Lebenszykluszustände.
- Outer-PnL bleibt bis zu einem vollständig publizierten Ergebnis verborgen. Task 27 bis 29 bleiben `NOT_FRESH`, `diagnostic_only`, nicht statistisch unterstützt, nicht adoptionfähig und nicht final.
- Paper, Testtrade, Live, Orders, private Endpunkte, API-Keys, `active_config.json`, kanonische Adoption und Botstart bleiben sichtbar und technisch gesperrt.

**Bericht:** `handoff/PROTOCOL_V3_TASK_30_2026-07-20.md`

### Aufgabe 31 – Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr

**Status:** `DONE_100`

Die monatlich refittende Pipeline besitzt nun eine getrennt versionierte, genau-einmalige Finalschicht für ein wirklich neues, vorab registriertes und bis zum Ende versiegeltes 365-Tage-Fenster.

**Abnahme:**

- Exakt der Task-2-Plan mit zwölf Origins, 730 Entwicklungstagen je Origin, T+24h und 365 lückenlosen UTC-OOS-Tagen ist bindend; falsche oder überlappende Fenster blockieren.
- Vorregistrierung und Einmal-Claim sind create-only, müssen vor Fensterstart aktuell persistiert werden, schließen den verbrauchten Audit sowie sichtbare Forward-Monate aus und erlauben keinen zweiten Evaluationsversuch.
- Pipelinegeneration, Code, Run-Fingerprint, Daten, Features, Kontext, Exchange Info, Execution, Kosten, Gates, Bootstrap, Seeds, Budgets, Stopregeln, Boundaries und permanenter Trial-Ledger-Head werden aus Repository- und Runtime-Wahrheit neu berechnet und unveränderlich gebunden.
- Der zwölf-Origin-Fortschritt bleibt result-blind. Outer-PnL, Rankings, Strategiewechsel, Reports und Finalclaims sind bis zum vollständigen Fensterende ausgeschlossen.
- Task 13 bleibt die einzige Checkpoint-/HEAD-/Resume-Wahrheit. Registration, Claim, Progress, Run-Fingerprint, Pipelinegeneration, Code und Trial-Ledger-Head müssen beim Resume bitgleich sein.
- Die create-only Task-31-Attestation revalidiert transitiv Task 23, Task 25, Task 26 und Task 27. `historically_hit`, `fresh_pre_registered_sealed_365`, `sealed_bootstrap_target_supported` und `statistically_supported` werden neu abgeleitet; nackte oder neu gehashte Bool-Claims werden abgewiesen.
- Genau ein `protocol_v3_pipeline_final`-Report darf aus einer persistierten Attestation geöffnet werden. Report-vor-Receipt-Reihenfolge erlaubt ausschließlich die exakte Crash-Recovery zwischen vollständigem Reportwrite und Open-Receipt; danach blockiert jeder zweite Open-Versuch.
- Legacy-`final_evaluation`, Protocol v2, Single-Candidate-Pfade sowie Task-27-/28-/29-Objekte können keinen Task-31-Finalstatus erzeugen. Adoption, Paper, Testtrade, Live, Orders, private Endpunkte und API-Keys bleiben gesperrt.
- Kein echtes Finalfenster wurde registriert, geclaimt, gelesen, ausgeführt oder geöffnet. Der fixture-basierte vollständige Dry-Run bleibt Aufgabe 32; der erste echte Protocol-v3-Lauf bleibt Aufgabe 33.

**Bericht:** `handoff/PROTOCOL_V3_TASK_31_2026-07-22.md`

### Aufgabe 32 – End-to-End-Parität, Fehler-Injektion und vollständige Abnahme

**Status:** `DONE_100`

Research, Replay, Cache, Resume und Challenger müssen bitgleich sein; Fehler-Injektionen und fixture-basierter 12-Origin-Dry-Run müssen vollständig grün sein.

**Abnahme:**

- Der Task-32-Vertrag `protocol_v3_fixture_isolated_e2e_parity_and_fault_acceptance_v1` bindet Erstlauf, Task-13-Resume, Cache-Reuse und deterministisches Replay an exakt dieselben 30 semantischen Identitäten.
- Der vollständige synthetische Task-23-bis-31-Pfad umfasst zwölf Origins, 365 lückenlose OOS-Tage, MTM, Monthly Gate, Hindsight/Bootstrap, result-blinden Checkpoint, transitive Attestation und genau-einmaliges Report-Opening.
- Finalreport und Open-Receipt des Dry-Runs dürfen ausschließlich in einem realen temporären Fixture-Root außerhalb des kanonischen Repository-Roots liegen. Der Akzeptanzstatus bleibt `FIXTURE_ONLY`, `diagnostic_only=true`, nicht final, nicht adoptionfähig und nicht startfähig.
- Task-13-Abbrüche vor dem atomaren HEAD behalten den vorherigen gültigen HEAD; ein Abbruch nach dem atomaren HEAD hinterlässt den vollständig validen neuen HEAD. Parallele Attestation- und Open-Versuche liefern jeweils exakt einen Gewinner.
- Die vollständige Fault-Matrix bindet Atomic-Write, Report/Receipt, Identitäten, Origin-Topologie, Daten/Kontext/Warmup, Resume/Cache, Ergebnisclaims, Pfade/Encoding und create-only Races.
- UI-Refresh und wiederholte Reads sind bitgleich und zustandsneutral. Fixture-, Freshness-, Final-, Adoption-, Safety- und Task-33-Claims können nicht umetikettiert werden.
- Vollständige Suite: 1.321 Tests erfolgreich; Python-Compile, PowerShell-Syntax, Ruff und Whitespace erfolgreich. Technischer GitHub-CI-Run `29924203612` vollständig grün.

**Bericht:** `handoff/PROTOCOL_V3_TASK_32_2026-07-22.md`

### Aufgabe 33 – Erster vollständiger Protocol-v3-Research-Lauf und Abschlussbericht

**Status:** `NOT_STARTED`

Erst nach Aufgaben 1–32 werden zwölf Origins und 365 OOS-Tage einmalig ausgeführt; Ergebnis ist ehrlich `TARGET_REACHED`, `TARGET_NOT_REACHED` oder `NO_EDGE_FOUND`.

## Fortschrittsführung

```text
Protocol v3: Aufgabe 27/33 – Hindsight-Benchmarks, Capture-Ratios und Bootstrap – DONE_100
Protocol v3: Aufgabe 28/33 – Aktueller 730-Tage-Refit und Champion/Challenger/Cash – DONE_100
Protocol v3: Aufgabe 29/33 – Orderfreier Research-Challenger-Shadow – DONE_100
Protocol v3: Aufgabe 30/33 – UI und Bedienzustände vollständig anschließen – DONE_100
Protocol v3: Aufgabe 31/33 – Pipeline-Final-Evaluator für ein frisches versiegeltes Jahr – DONE_100
Protocol v3: Aufgabe 32/33 – End-to-End-Parität, Fehler-Injektion und vollständige Abnahme – DONE_100
Gesamt: 32/33 DONE_100 = 96,97 %
```

Fortschritt wird ausschließlich als `DONE_100 / 33` ausgewiesen, nicht nach Zeit oder Token geschätzt.
