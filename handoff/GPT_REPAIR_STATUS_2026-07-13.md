# GPT-Reparaturstatus – 2026-07-13

## Bearbeiteter Stand

- PR: #17 `Resume research after Windows restart`
- Branch: `codex/research-resume-and-ui-state-v1`
- Ausgangs-Head der GPT-Prüfung: `a39e249`
- Historischer Research-Lauf: `research_loop_supervisor_20260713T061220Z`
- Historischer Runner-Commit: `4eb2dbb`

Der historische Lauf wurde nicht neu gerechnet. Alle Performancewerte im
Analysepaket bleiben historische Evidenz von `4eb2dbb`.

## Durch GPT umgesetzt

### 1. Endlicher, stichprobenabhängiger Profit Factor

Datei: `src/ethusdc_bot/backtest/metrics.py`

- Verlustfreie Stichproben erzeugen kein `Infinity` mehr.
- Als konservativer Pseudoverlust wird ein durchschnittlicher Gewinner
  angesetzt.
- Ein einzelner Gewinner hat dadurch PF 1.0 statt unendlich.
- Mehrere verlustfreie Gewinner bleiben unterscheidbar, müssen aber weiterhin
  die unveränderten Trade-, WFV- und Robustheits-Gates erfüllen.

Grund: Ein oder zwei verlustfreie Trades durften Ranking und Fold-Evidenz nicht
mehr dominieren oder als ungültige numerische Evidenz alle Fold-Prüfungen
mitreißen.

### 2. Validation-Ranking an bestehende Gates angepasst

Datei: `src/ethusdc_bot/backtest/research_runner.py`

- PF-Beitrag ist auf einen sinnvollen Bereich begrenzt.
- PF-Beitrag wird mit der vorhandenen Trade-Stichprobe gewichtet.
- Kandidaten unter dem bestehenden Minimum von 50 Validation-Trades erhalten
  eine deutliche Unteraktivitätsstrafe.
- Bei sonst gleichem Ergebnis werden mehr belastbare Trades nicht mehr durch
  `-trade_count` benachteiligt.
- Drawdown- und `too_few_trades`-Diagnosen verwenden die eingefrorenen
  Quality-Gate-Grenzen.

Keine Gate-Schwelle wurde gelockert.

### 3. Fail-closed Resume-Prüfung im Supervisor

Datei: `src/ethusdc_bot/backtest/research_supervisor.py`

Vor dem Start eines wiederaufgenommenen Child-Runners werden jetzt geprüft:

- Manifest-Schema, Artifact-Kind, Run-ID und Cycle-Dateiliste,
- Übereinstimmung von `completed_cycle_count` und Cycle-Dateien,
- lückenlose Cycle-Nummern,
- vollständiger kanonischer Safety-Vertrag jedes gespeicherten Zyklus,
- bei Context-Produktion die exakten Stufen 40/12/3/2,
- sechs WFV-Folds,
- audit-/holdout-freie Auswahl,
- gebundene Kontext-Proofs im Supervisor-Checkpoint.

Ein alter Lauf mit unsicherem Zyklus oder fehlendem Context-Proof wird nicht
fortgesetzt.

### 4. Tests ergänzt

- `tests/unit/test_metrics_ranking_guards.py`
- `tests/unit/test_research_resume_guards.py`

Abgedeckt sind endlicher PF, Low-Sample-Ranking und fail-closed Resume-Safety.

### 5. Analysepaket berichtigt

Datei: `reports/research_loop/analysis_20260713T061220Z.md`

- Zyklus-4-Feld korrekt als Validation des ausgewählten WFV-Finalisten
  bezeichnet.
- Der tatsächliche rohe Validation-Leader wird separat genannt.
- `rolling_origin_limit=3` wird von tatsächlich ausgeführten Origins getrennt.
- Für den Lauf waren `rolling_origins_executed=0`.
- Historische Resultate werden ausdrücklich dem Runner-Commit `4eb2dbb`
  zugeordnet.

## Nicht durch GPT repariert – Codex-Aufgaben

### P0: Vor dem nächsten langen Research-Lauf

1. **Root-Reihenfolge im Runner**
   - `research_loop_runner.run_research_loop()` hängt den Zyklus an und
     persistiert ihn noch vor `_safety_ok()`.
   - Der Supervisor blockiert jetzt einen unsicheren Resume, aber die Ursache im
     Runner muss trotzdem behoben werden.
   - Safety prüfen, bevor ein Zyklus als abgeschlossen gespeichert wird.

2. **Resume-Datenfingerprint**
   - Manifest bindet noch keine SHA-256-Hashes der Rohdaten, Cycle-Dateien,
     Feature-Version, Gate-Version, Search-Frontier-Version und Kostenmodell-
     Version.
   - Resume muss bei jeder Daten- oder Modellabweichung fail-closed abbrechen.

3. **Kompakter Resume-State**
   - Cycle-Dateien liegen weiterhin bei etwa 390–425 MB.
   - Resume braucht nur Entscheidungsevidenz und Zustand, nicht Bar-/Kurven-
     Rohdetails.

4. **Quality-Gate Fold-Diagnose nach neuem Lauf prüfen**
   - Der endliche PF sollte das frühere Mitreißen von `fold_days` und
     `fold_trades` durch Infinity beseitigen.
   - Mit einem kleinen reproduzierbaren Lauf verifizieren, dass gültige Fold-
     Tage nicht mehr als `missing_or_invalid_fold_evidence` erscheinen.

5. **Sticky UI-Wunschzustand**
   - `_requested_view="backtest_running"` kann einen fehlgeschlagenen oder
     bereits beendeten Start optisch als laufend festhalten.
   - Wunschzustand nach Startfehler und beim Übergang zu Result/Idle löschen.

6. **Primär- und Sekundärblocker im Abschlussbericht**
   - `blocked_by_holdout_policy` verdeckt derzeit gleichzeitig gescheiterte
     Quality Gates.
   - Ausweisen: `primary_blocker=quality_gates_failed` und zusätzlich
     `secondary_blocker=no_fresh_sealed_holdout`.

### P1: Such- und Rankinglogik

1. Global getestete Candidate-Signaturen über alle Zyklen speichern und echte
   Wiederholungen vermeiden.
2. Suchzustand je Familie statt eines globalen `pressure/opening_bias` führen.
3. Parameter lokal und einzeln verändern; nicht mehrere Entry-/Exit-/Cooldown-
   Parameter gleichzeitig verschieben.
4. WFV-Frontier nach Aktivitäts-/Kostenprofil diversifizieren.
5. Null-Trader ausdrücklich als `diagnostic_no_trade` führen, nicht als beste
   Strategie einer negativen Familie.
6. WFV-Ranking um Mindestaktivität und No-Trade-Gap ergänzen, ohne Gates zu
   lockern.

### P2: Fachlich korrekter Zielpfad

Der aktuelle Research-Lauf bleibt ein globaler Einzelstrategie-Suchlauf. Für
README-/Projektkonformität fehlen weiterhin:

1. vollständige Nutzung der vorhandenen Feature-Reihen über 730 Trainingstage,
2. echte abgeschlossene 5m/15m/30m/1h-Timeframes,
3. Tages-/Wochen-/Monatskontext,
4. datengetriebene Marktphasen und Opportunity-Cluster,
5. lokale Spezialisten pro Situation,
6. eingefrorener Router mit `NO_TRADE` und konkreten Setup-Mappings,
7. unveränderte Router-Ausführung im separaten Blindtest.

Keine neuen Strategiefamilien bauen, bevor die vorhandenen Familien als lokale
Spezialisten im Router verwendet werden.

### P3: Simulator-/Live-Gleichheit

1. 100-USDC-Cashbudget muss Entry-Gebühr enthalten; derzeit wird 100 USDC
   Notional gekauft und die Gebühr zusätzlich belastet.
2. Binance Tick Size, Step Size, Mindestnotional und Mengenrundung anwenden.
3. TP/SL/Trail konservativ mit Intrabar-High/Low modellieren.
4. TP/SL-Priorität vor `time_exit` eindeutig festlegen.
5. dynamisches Spread-/Slippage-Modell erst auf validierter Datenbasis ergänzen.

Diese Simulatoränderungen wurden von GPT bewusst nicht direkt vorgenommen,
weil sie alle historischen Kennzahlen verändern und zuerst zusammen mit den
bestehenden Live-/Paper-Ausführungsregeln abgeglichen werden müssen.

## Verbindlicher nächster Ablauf für Codex

1. Aktuellen Branch pullen und GPT-Commits nicht überschreiben.
2. Vollständige Tests erneut lokal auf Windows ausführen.
3. P0-Punkte einzeln und mit Tests reparieren.
4. Kleinen Fixture-/Smoke-Research ausführen und Reports prüfen.
5. Noch keinen großen 1095-Tage-Lauf starten, solange Runner-Safety,
   Datenfingerprint und Report-Blocker nicht sauber sind.
6. Danach erst fachlichen Router-/Cluster-Pfad umsetzen.
7. Finalen Holdout geschlossen lassen; Paper/Live/Testtrade bleiben gesperrt.
