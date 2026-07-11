# PR #10 - lokaler Production-Research-Abschluss

Stand: 2026-07-11

## Ausgangsstand

- Quellbranch: `review/context-veto-engine-v1`
- Quellcommit: `97167626ead4925d70fb4a880a5b3bcbbf3e10b6`
- lokaler Laufbranch vor der Sicherung: `codex/review-stack-20260711`
- Run-ID: `research_loop_20260711T145403Z`
- Ausführungsprofil: `production_protocol`
- Stopgrund: `max_cycles_reached`

Der erste Aufruf des unveränderten Windows-Runners stoppte vor dem Research,
weil `src` nicht im Prozess-`PYTHONPATH` lag. Der identische Runner wurde danach
mit einem ausschließlich prozesslokalen `PYTHONPATH=src` erneut aufgerufen. Es
gab dafür keine Code- oder Strategieänderung und keinen parallelen zweiten Lauf.

## Verifikation und Daten

- vollständige Tests vor dem Lauf und erneut vor dem Abschlusscommit:
  jeweils `814 passed`;
- Python-3.12-Kompilierung: bestanden;
- `git diff --check`: bestanden;
- Rohdaten: `1.095` ZIP-Dateien und `1.095` zugehörige Checksum-Dateien;
- Paarprüfung: `1.095` vollständige Paare, keine fehlenden oder verwaisten
  Dateien;
- Datenzeitraum: `2023-07-09` bis `2026-07-07`;
- nach dem Lauf waren keine Instanzen von `research_loop_runner`,
  `research_supervisor` oder `run_production_research` mehr aktiv.

## Vollständiger Lauf

Alle acht vorgesehenen Zyklen wurden beendet. Jeder Zyklus verwendete exakt:

- `40` erzeugte Kandidaten;
- `12` getestete Kandidaten;
- `3` Walk-Forward-Kandidaten;
- `2` Finalisten;
- `6` Walk-Forward-Folds;
- ein Rolling-Origin-Limit von `3`.

Gesamt wurden damit `320 / 96 / 24 / 16` Kandidaten über die vier Stufen
geführt. In allen acht Zyklen war `qualified_finalists = 0`.

| Zyklus | vom Report geführte beste Validation (USDC/Tag) | Trades | PF |
| ---: | ---: | ---: | ---: |
| 1 | -0,0616125616 | 29 | 0,4756362645 |
| 2 | -0,0671165634 | 35 | 0,4612169686 |
| 3 | -0,0616125616 | 29 | 0,4756362645 |
| 4 | -0,0424111216 | 25 | 0,5749687664 |
| 5 | -0,0499040292 | 32 | 0,5833233110 |
| 6 | -0,0205462855 | 21 | 0,7558196835 |
| 7 | -0,0205462855 | 21 | 0,7558196835 |
| 8 | -0,0205462855 | 21 | 0,7558196835 |

Das vom Report bezeichnete beste Validation-Ergebnis war
`breakout_volatility_filter_06_001` mit `-0,0205462855 USDC/Tag`, `21` Trades
und Profit Factor `0,7558196835`. Der Abstand zum Richtwert von `+3 USDC/Tag`
beträgt damit `3,0205462855 USDC/Tag`.

Der nach Quality-Gate- und Walk-Forward-Rang ausgewählte Parametersatz erschien
ab Zyklus 6 als `breakout_volatility_filter_06_007` und in Zyklus 8 mit
identischer Signatur als `breakout_volatility_filter_08_007`. Seine wichtigsten
Werte im letzten Zyklus waren:

- Validation: `-0,0001383214 USDC/Tag`, Profit Factor `0,9963450861`, `9`
  Trades, Mark-to-Market-Drawdown `5,1500495034 USDC`;
- Walk-Forward: `-0,0261580516 USDC/Tag`, Profit Factor `0,3102933291`, `27`
  Trades und Mark-to-Market-Drawdown `16,5273477065 USDC`;
- schlechtester Fold: `-0,0702512706 USDC/Tag`;
- positive Folds: `2 von 6`;
- Walk-Forward-Kostenlast: `8,08666167 USDC`;
- Quality Gate: `false`, Status `fail_invalid_evidence`; von `73` Prüfungen
  bestanden `29`, während `44` scheiterten.

Die offizielle beste Validation-Zeile und der ausgewählte WFV-Kandidat sind
nicht derselbe Kandidat. Der ausgewählte Kandidat liegt beim rohen
Validation-Netto näher an null, hat aber nur neun Validation-Trades und erfüllt
damit den Mindestnachweis von 50 Trades deutlich nicht.

## Evidenzdiagnose des letzten Zyklus

Die wichtigsten Quality-Gate-Blocker waren:

- Validation war nicht positiv und der Profit Factor lag unter `1,10`;
- WFV war nicht positiv, der Profit Factor lag unter `1,20`, der Drawdown lag
  über `15 USDC`, und nur zwei statt mindestens fünf Folds waren positiv;
- zwei Fold-Profit-Factor-Werte waren als ungültige Evidenz markiert;
- maximale Unterwasserzeit: `545` Tage statt höchstens `60`;
- Top-1-/Top-5-Gewinnkonzentration: `0,7502702350` / `0,9693480915`;
- Ergebnis ohne die fünf besten Trades: `-20,5108297333 USDC`;
- gemeinsamer Kostenstress (15 bps Gebühr und 10 bps Slippage je Seite):
  `-0,0352306324 USDC/Tag`, Profit Factor `0,2134031866`;
- Slippage-Stress (10 bps Gebühr und 15 bps Slippage je Seite):
  `-0,0275348911 USDC/Tag`, Profit Factor `0,3293720804`;
- Reibungskostenanteil am positiven Vor-Kosten-PnL: `0,9074033552`;
- Parameterstabilität: `22` Nachbarn für `11` numerische Parameter, aber nur
  `18,18 %` statt mindestens `80 %` bestandene Nachbarn und Median-Retention
  `0,0`;
- Zeitstabilität: `19` Monate, davon `10,53 %` positiv und `52,63 %` aktiv;
  maximale No-Trade-Lücke `136` Tage; nur `14,29 %` von sieben Quartalen
  positiv; schlechtester Monat `-6,2193028367 USDC`;
- Regimestabilität: vier Regime vorhanden, aber mindestens ein Regime ohne
  Trades, kein positives Regime, schlechtester Regime-PF `0,0`, schlechstes
  Regime-Netto `-14,2822961930 USDC`.

Die letzten neun Validation-Trades endeten viermal per Stop-Loss, dreimal per
Trailing-Stop, einmal per Break-even und einmal per Take-Profit. Die Kostenlast
pro Trade betrug `0,3002970056 USDC`. Die Familiendiagnose bewertet das Problem
als `missing_edge`, während Search Frontier v2 es als
`costs_and_insufficient_edge` zusammenfasst. Alle zwölf Validation-Kandidaten
des letzten Zyklus waren negativ; über alle acht Zyklen trugen alle `96`
getesteten Kandidaten die Schwächen `training_negative`, `validation_negative`
und `profit_factor_below_one`.

Das konfigurierte Rolling-Origin-Limit war drei, aber der Window-Plan enthielt
`historical_origin_count = 0`. Die separate historische Replay-Zusammenfassung
hat daher `origin_count = 0` und ist nicht als Quality-Gate-Evidenz zugelassen.
Die im Gate als `rolling` ausgewiesenen Drawdown-, Unterwasser- und
Konzentrationswerte stammen aus der chronologischen WFV-Evidenz und sind davon
zu unterscheiden.

## Kontextgrenze dieses PR-#10-Laufs

Dieser Lauf ist ein ehrlicher PR-#10-Kontrolllauf, aber noch kein aktiver
Kontext-Research-Lauf. In allen Zyklen steht
`context_candidates_enabled = false` mit dem Grund
`real_context_market_data_not_integrated`. Der Report führt nur die sechs
ETHUSDC-Familien ohne `context_filter`; BTCUSDC/ETHBTC wurden in diesem
Search-Frontier-Lauf nicht als aktive Kontextvarianten geladen. Das entspricht
der dokumentierten Grenze von PR #10 und ist der konkrete
Integrationsgegenstand des nachfolgenden PR #12.

## Holdout und Sicherheit

- Das frühere Audit-/Holdoutfenster ist als `consumed` dokumentiert, wurde in
  diesem Research-Lauf aber nicht ausgewertet und beeinflusste die Auswahl
  nicht.
- Der finale versiegelte Holdout wurde nicht geöffnet oder ausgewertet.
- Das Ziel von `+3 USDC/Tag` ist deshalb ausdrücklich
  `not_evaluated_no_sealed_holdout_run`.
- `freeze_status = blocked_by_holdout_policy`; kein Kandidat wurde eingefroren
  oder übernommen.
- Live, Paper und Testtrade blieben gesperrt. Es gab keine Orders, API-Keys,
  Trading-API-Nutzung, Shorts, Margin, Futures oder Leverage.

## Artefakte und Integrität

| Artefakt | Größe | SHA-256 | Git-Status |
| --- | ---: | --- | --- |
| `reports/research_loop/research_loop_20260711T145403Z.json` | 3.751.815.534 Bytes | `453DF84AD2E1E0D22C33CFFF03C7CE6CC972449F7F9ABEAFB3ADAB1260CF6CAC` | lokal erhalten, wegen Größe nicht commitbar |
| `reports/research_loop/research_loop_20260711T145403Z.txt` | 2.791 Bytes | `B6384694CE6D41905FD7D2864DAB7EC497B4BE901C901B4D5680200E3CF229E3` | Abschlusscommit |
| `reports/research_loop/production_research_20260711T145341Z.console.log` | 4.160 Bytes | `62599E77276912C0F4B93F79B2274BE867A417D0F19DCBADB00FE8855EEA62E1` | lokal erhalten, durch `*.log` ignoriert |

Der Research-Prozess selbst schrieb JSON, TXT und Index vollständig. Erst die
nachgelagerte PowerShell-Validierung versuchte, das 3,75-GB-JSON mit
`Get-Content -Raw | ConvertFrom-Json` vollständig in den Speicher zu laden und
endete mit `OutOfMemoryException`. Daher wurde kein
`production_research_*.manifest.json` erzeugt. Dieser Wrapperfehler wird hier
ausdrücklich dokumentiert; es wird kein nachträglicher Erfolg vorgetäuscht und
der teure Research-Lauf wird nicht wiederholt.

## Offene Punkte und nächster Schritt

- Der Windows-Wrapper sollte künftig nur eine kompakte Zusammenfassung
  streamen oder ein kleines Laufmanifest direkt vom Runner erhalten, statt den
  vollständigen Detailreport in den Speicher zu laden.
- PR #10 liefert keine qualifizierte oder profitable Strategie und darf nicht
  übernommen werden.
- Exakter nächster Schritt nach Commit und Push dieses Checkpoints: den
  vollständigen Stand von PR #12 auf Commit
  `0cec0830a64874d1afd1f385b01a7fe0adcb941a` in einem neuen Arbeitsbranch
  auschecken, dessen Dokumentation und UI-Produktionspfad prüfen und danach die
  erwartete `832`-Test-Basis verifizieren.
