# Protocol v3 – Handoff Aufgabe 8/33

Stand: 2026-07-14

## Status

`Protocol v3: Aufgabe 8/33 – Next-Tradable-Price und pessimistische Intrabar-Ausführung – DONE_100`

Gesamtfortschritt nach Statusupdate: `8/33 = 24,24 %`

Exakt nächste Aufgabe: `Aufgabe 9 – Warmup-, Purge-, Fold-End- und Outer-State-Maschine`.

## Aufgabe 7 erneut vollständig geprüft

Vor Beginn und nochmals vor Abschluss wurde Aufgabe 7 gegen den finalen PR-Stand geprüft:

- PR #17 war offen, mergebar, Draft und nicht gemerged.
- Kontrollierter Ausgangs-Head: `36bd2950e2f369d55bb94372e6541ccd15831d62`.
- Review-CI Run 384 war vollständig grün.
- `requested_entry_notional_usdc=100` und `reserved_entry_notional_usdc=100` blieben unverändert.
- Die Menge wird weiter ausschließlich per Decimal und `ROUND_DOWN` auf den gemeinsamen positiven `LOT_SIZE`-/`MARKET_LOT_SIZE`-Raster abgerundet.
- Entry- und Exit-Fees verwenden weiter die tatsächlich ausgeführten Notionals.
- Der Exit verkauft weiter exakt die gekaufte Menge.
- Single- und Portfolio-Golden-Trade-Felder blieben bitgleich.
- Die Task-8-Arbeit änderte keine Task-7-Formel und baute keine parallele Mengen-/Fee-Berechnung.

Ergebnis der erneuten Prüfung: Aufgabe 7 ist so umgesetzt, wie fachlich vorgesehen, und bleibt `DONE_100`.

## Vorhandene Funktionen geprüft und wiederverwendet

Vor der Umsetzung wurden insbesondere geprüft:

- `src/ethusdc_bot/backtest/simulator.py`
  - vorhandene Signalentscheidungen und Kandidatenparameter;
  - bestehende LONG-only-Sperre;
  - vorhandene Stop-, TP-, Trail-, Break-even-, Time-Exit- und Cooldown-Parameter.
- `src/ethusdc_bot/backtest/portfolio_simulator.py`
  - bestehender orderfreier Portfolio-/Shadow-Ergebnistyp;
  - keine neue Strategie- oder Signalengine nötig.
- `src/ethusdc_bot/protocol_v3/execution_parity.py`
  - Task-7-Menge, Notional, Fees und exakte Exit-Menge;
  - Exchange-Info-gebundene Tick-, Mengen- und Notionalfilter.
- `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
  - Signalbar abgeschlossen;
  - Entry frühestens nächster handelbarer Preis;
  - Stop vor TP bei gleicher 1m-Kerze;
  - Gaps zum schlechteren Preis;
  - keine perfekten High-/Low-Fills;
  - Basis und Stress durch dieselbe Engine.

Protocol v2 wurde nicht strukturell umgebaut. Der neue Protocol-v3-Pfad verwendet die vorhandene Signalentscheidung und ausschließlich die Task-7-Ausführungsparität für Mengen und Kosten.

## Was umgesetzt wurde

### 1. Versionierter Intrabar-Vertrag

Neue Datei `configs/protocol_v3_intrabar_execution_contract.json` friert ein:

- Schema `protocol_v3_intrabar_execution_contract_v1`;
- Vertrag `next_tradable_price_pessimistic_intrabar_v1`;
- Binance Spot ETHUSDC LONG-only auf 1m-Ausführungsbars;
- Signalbar muss vollständig abgeschlossen sein;
- Entry frühestens auf dem nächsten positiven Volumen-1m-Open;
- Buy-Slippage nach oben und Tick-Rundung mit `ROUND_CEILING`;
- Sell-Slippage nach unten und Tick-Rundung mit `ROUND_FLOOR`;
- Stops/TPs ausschließlich auf positiven Volumen-1m-Kerzen;
- Stop gewinnt ausnahmslos bei gleichzeitiger Stop-/TP-Berührung;
- Stop-Gap verwendet den schlechteren nächsten Open;
- günstiger Target-Gap wird konservativ auf das Target begrenzt;
- keine High-/Low-Extremfills;
- Break-even und Trail verwenden nur zuvor abgeschlossene, überlebte Bars;
- terminale Liquidation am letzten positiven Volumen-Bar-Close;
- Basis-, Slippage-Stress- und Joint-Stress-Profil verwenden dieselbe Engine;
- unveränderte Safety-Locks.

### 2. Gemeinsame Protocol-v3-Ausführungsengine

Neue Datei `src/ethusdc_bot/protocol_v3/intrabar_execution.py` implementiert genau einen Protocol-v3-Timingkern.

Öffentliche Pfade:

- `simulate_protocol_v3_intrabar_strategy`;
- `simulate_protocol_v3_intrabar_portfolio_strategy`.

Beide verwenden denselben internen Kern für:

- Pending Entry;
- Entry-Zeitpunkt;
- Entry-Tick-Rundung;
- initialen Stop;
- Target;
- Break-even;
- Trailing Stop;
- Time Exit;
- Stop-/TP-Priorität;
- Gap-Fills;
- terminale Liquidation;
- MTM-Equity.

Der Portfolio-/Shadow-Ausgabepfad ist kein zweiter Simulator. Er serialisiert dieselben Kerntrades lediglich in den vorhandenen orderfreien Portfolio-Ergebnistyp.

### 3. Entry auf dem nächsten handelbaren Preis

Ein akzeptiertes Signal wird erst nach Abschluss seiner Signalbar gespeichert.

Der Entry erfolgt:

```text
frühestens nächste 1m-Kerze mit volume > 0
entry_reference = deren Open
raw_entry_fill = entry_reference × (1 + slippage_bps / 10.000)
entry_fill = Tick-Rundung nach oben
```

Eine Nullvolumenkerze kann keinen Entry erzeugen. Der Pending Entry wartet
höchstens bis zur explizit eingefrorenen
`HorizonPolicy.pending_entry_latency_minutes`. Ist bis dahin keine positive
Volumenkerze verfügbar, wird er vor einem Fill deterministisch verworfen. Genau
dieselbe Obergrenze geht in die Task-9-Purge-Dauer ein.

Entry- und Exitprüfungen sind bereits auf der Entry-Kerze aktiv, nachdem der Entry am Open stattgefunden hat. Dadurch werden unrealistische risikofreie Entry-Bars ausgeschlossen.

### 4. Preis-Tick-Parität

Task 8 ergänzt die in Aufgabe 7 bewusst verschobene Preisrundung:

- Buy-Fill: adverse Slippage, danach auf den nächsten Tick nach oben;
- Sell-Fill: adverse Slippage, danach auf den nächsten Tick nach unten;
- initialer Stop: nach unten auf Tick;
- Target: nach oben auf Tick;
- Break-even-/Trailing-Stop: nach unten auf Tick.

Task-7-Mengenrundung bleibt davon unabhängig und unverändert `ROUND_DOWN`.

### 5. Pessimistische Intrabar-Reihenfolge

Für jede positive Volumen-1m-Kerze gilt:

1. fälliger Time Exit am Bar-Open;
2. Stop-Gap am schlechteren Open;
3. Target-Gap konservativ am Target;
4. Intrabar-Berührung des aktiven Stops;
5. Intrabar-Berührung des Targets.

Werden Stop und Target in derselben Kerze berührt, wird immer der Stop gewählt.

Die Fillpreise verwenden nie das Kerzen-Low oder -High. Verwendet werden ausschließlich:

- tatsächlicher Bar-Open bei Stop-Gap oder Time Exit;
- aktives Stop-Level;
- Target-Level;
- letzter Bar-Close bei terminaler Liquidation;
- jeweils danach adverse Slippage und Tick-Rundung.

### 6. Break-even und Trailing ohne Intrabar-Pfad-Erfindung

Break-even und Trailing dürfen nicht aus einer unbekannten Reihenfolge innerhalb derselben OHLC-Kerze profitieren.

Daher gilt:

- der aktive Stop zu Beginn einer Kerze stammt nur aus früheren vollständig abgeschlossenen Bars;
- die aktuelle Kerze wird zuerst mit diesem bereits aktiven Stop und dem Target geprüft;
- nur wenn die Kerze überlebt wird, darf ihr High den High-Watermark aktualisieren;
- ein daraus entstehender Break-even- oder Trailing-Stop gilt erst für die nächste handelbare Kerze.

Das verhindert eine optimistische Annahme wie „erst High erreicht, Trail aktiviert, danach ohne belegbaren Pfad günstig ausgestiegen“.

### 7. Gap-Regeln

Stop-Gap für LONG:

```text
wenn Open <= aktiver Stop:
    exit_reference = Open
    danach Sell-Slippage und Tick-Rundung nach unten
```

Damit kann der Fill deutlich schlechter als das Stop-Level sein.

Target-Gap für LONG:

```text
wenn Open >= Target:
    exit_reference = Target
    nicht der bessere Gap-Open
```

Damit wird kein günstiger Übernacht-/Minutengap als zusätzliche nicht belegte Verbesserung gutgeschrieben.

### 8. Kostenprofile über dieselbe Engine

Versioniert sind:

```text
baseline:          10 bps Fee +  5 bps Slippage je Seite
slippage_stress:   10 bps Fee + 15 bps Slippage je Seite
joint_stress:      15 bps Fee + 10 bps Slippage je Seite
```

Alle drei Profile verwenden dieselbe Funktion, dieselbe Reihenfolge und dieselben Zustandsregeln. Ein nicht kanonisches Kostenprofil blockiert.

### 9. Task-7-Parität bleibt vollständig erhalten

Jeder Task-8-Trade berichtet weiterhin:

- requested Entry-Notional 100 USDC;
- reserved Entry-Notional 100 USDC;
- ausgeführtes Entry-Notional höchstens 100 USDC;
- Task-7-`ROUND_DOWN`-Menge;
- Entry-Fee auf tatsächlichem Entry-Notional;
- Exit-Fee auf tatsächlichem Exit-Notional;
- Exit-Menge exakt gleich Entry-Menge;
- kein Compounding.

Task 8 berechnet diese Werte nicht neu, sondern ruft direkt die Task-7-Funktionen `prepare_market_entry` und `prepare_market_exit` auf.

### 10. Pipeline- und Fingerprintbindung

`configs/protocol_v3_pipeline_contract.json` bindet jetzt:

- `configs/protocol_v3_intrabar_execution_contract.json`;
- `src/ethusdc_bot/protocol_v3/intrabar_execution.py`;
- den Task-7-Vertrag und die Task-7-Implementierung;
- vorhandenen Simulator und Portfolio-Simulator.

Aktuelle Komponentenverträge:

```text
cost_model = protocol_v3_actual_notional_baseline_and_stress_costs_v1
simulator  = next_tradable_price_pessimistic_intrabar_v1
```

Jede Änderung an Reihenfolge, Gap-Regeln, Tick-Rundung oder Kostenprofil erzeugt eine neue Pipelinegeneration und damit einen neuen Run-Fingerprint.

## Golden- und Negativtests

Die Suite prüft mindestens:

- unveränderte Task-7-Golden-Werte;
- exakten Task-8-Vertrag und Safety-Locks;
- Signalzeitpunkt vor Entry-Zeitpunkt;
- Entry nicht auf Signalbar;
- Nullvolumenkerze übersprungen;
- Buy-Tick-Rundung nach oben;
- Stop und Target auf Entry-Bar;
- Stop gewinnt bei Doppelberührung;
- Stop-Gap füllt unter dem Stop-Level am schlechteren Open;
- günstiger Target-Gap wird auf Target begrenzt;
- kein Fill am Kerzen-High oder -Low;
- Break-even erst ab Folgebalken;
- Trailing Stop nur aus vorheriger überlebter Bar;
- Time Exit vor Intrabar-Berührung;
- baseline und joint stress mit identischen Signal-/Entry-/Exit-Zeitpunkten und Exitgrund;
- identische Trade-Kernfelder zwischen Single und Portfolio;
- maximal ein offenes Lot im kanonischen Profil;
- unzulässiges 200-USDC-/Zwei-Lot-Profil blockiert;
- terminale Liquidation verwendet auch bei einem Nullvolumen-Tail die letzte
  positive Volumenkerze und erzeugt danach keine neuen Entries;
- abgelaufener Pending Entry wird vor später zurückkehrendem Volumen verworfen;
- nicht kanonisches Kostenprofil blockiert;
- Task-8-Quellen und Versionen sind pipelinegebunden.

## CI-Historie

1. Vor der ersten CI fand der interne Review einen fehlenden Exit-Zeitstempel im neuen Tradeobjekt. Dieser wurde korrigiert, bevor der Schritt zur Abnahme gestellt wurde.
2. Review-CI Run 388 auf dem ersten vollständigen Timing- und Golden-Teststand war vollständig grün.
3. Review-CI Run 390 nach Pipelinebindung und öffentlichem Protocol-v3-Export war vollständig grün.
4. Review-CI Run 391 nach zusätzlichen Trailing-, Kostenprofil- und Pipeline-Identitätstests war vollständig grün:
   - komplette Pytest-Suite;
   - Python-Kompilierung;
   - PowerShell-Syntax;
   - Whitespace-Prüfung;
   - finaler Pytest-Status.
5. Der finale Dokumentations-/Handoff-Head wird erneut durch dieselbe Review-CI geprüft.

## Aktueller ehrlicher Laufzustand

```text
Task-8-Implementierung = bereit und getestet
Task-7-Parität = erneut geprüft und unverändert
synthetische Intrabar-/Gap-Golden-Tests = grün
realer Protocol-v3-Langlauf = weiterhin nicht ausführbar
```

Der reale Lauf bleibt blockiert, weil:

- noch kein realer Task-6-Exchange-Info-Snapshot versiegelt ist;
- der reale Task-5-Datensnapshot weiterhin `BLOCKED_MISSING_WARMUP` ist;
- Fold-, Outer- und Monatszustandsmaschinen erst in späteren Aufgaben entstehen.

Das ist keine Performance-, Zielerreichungs- oder Freigabebehauptung.

## Neue und geänderte Dateien

- `configs/protocol_v3_intrabar_execution_contract.json`
- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/intrabar_execution.py`
- `src/ethusdc_bot/protocol_v3/__init__.py`
- `tests/unit/test_protocol_v3_intrabar_execution.py`
- `tests/unit/test_protocol_v3_intrabar_execution_binding.py`
- `handoff/PROTOCOL_V3_TASK_08_2026-07-14.md`
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` – wird im Abschlussstand auf 8/33 aktualisiert

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 9 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- keine Purge-Dauer oder Informationsintervallberechnung;
- keine Fold-Start-/Fold-End-State-Maschine;
- kein Outer-Origin-Handoff;
- keine alte Konfiguration exit-only über Monatsgrenzen;
- kein `valid_from`-/`flat_time`-Zusammenspiel;
- kein Kontextgleichstand aus Aufgabe 10;
- keine neue Feature-, Router-, Kandidaten- oder Regimelogik;
- kein Cache-/Resume-Store;
- keine Report-, UI- oder Shadow-Aktivierung;
- keine Teilfills oder Orderbuchausführung;
- keine Orders, Trading-API, API-Keys, Paper, Testtrade oder Live;
- kein finaler Holdout.

## Safety

Unverändert gesperrt:

- Orders;
- Trading-API;
- API-Keys und Kontodaten;
- Paper;
- Testtrade;
- Live;
- finaler Holdout.

BTCUSDC und ETHBTC bleiben reine Kontextmärkte und können nie handeln.

## Codex-Startanweisung für Aufgabe 9

1. Branch `codex/research-resume-and-ui-state-v1` auf den finalen PR-Head ziehen.
2. `git status` muss sauber sein und lokaler `HEAD` muss GitHub entsprechen.
3. Dieses Handoff, Dokument 41, den Task-2-Boundary-Vertrag und den Task-8-Intrabar-Vertrag vollständig lesen.
4. Vorhandene Walk-forward-, Split-, Pending-, Cooldown-, Positions- und Resume-State-Funktionen inventarisieren und wiederverwenden.
5. Danach ausschließlich Aufgabe 9 umsetzen.
6. Purge muss maximalen Label-/Holding-Horizont, Pending-Latenz und eine Ausführungsbar abdecken.
7. Innere Folds starten flat und enden konservativ liquidiert.
8. Zwischen Outer-Origins darf ausschließlich eine offene Altposition mit alter Exitlogik übertragen werden; Pending, Cooldown und Fit-State werden nicht übernommen.
9. Alte Konfiguration ist ab Monatsgrenze exit-only; neue Entries warten auf `valid_from` und `flat_time`.
10. Keine Kontext-, Report-, Cache-, Router-, Feature- oder UI-Arbeit vorziehen.

## Exakt nächstes Ticket

`Aufgabe 9 – Warmup-, Purge-, Fold-End- und Outer-State-Maschine`
