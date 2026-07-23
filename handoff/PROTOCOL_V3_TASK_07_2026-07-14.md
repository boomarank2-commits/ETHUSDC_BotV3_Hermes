# Protocol v3 – Handoff Aufgabe 7/33

Stand: 2026-07-14

## Status

`Protocol v3: Aufgabe 7/33 – Notional-, Mengen-, Gebühren- und Rundungsparität herstellen – DONE_100`

Gesamtfortschritt nach Statusupdate: `7/33 = 21,21 %`

Exakt nächste Aufgabe: `Aufgabe 8 – Next-Tradable-Price und pessimistische Intrabar-Ausführung`.

Codex darf Aufgabe 8 erst beginnen, nachdem der Branch lokal auf den finalen PR-Head dieses Handoffs gezogen und ein sauberer Arbeitsbaum bestätigt wurde.

## Vorherige Aufgabe kontrolliert

Vor Beginn wurde Aufgabe 6 vollständig gegen den aktuellen PR-Stand geprüft:

- PR #17 war offen, mergebar, Draft und nicht gemerged.
- Kontrollierter Ausgangs-Head: `23e7d63a755ae5100cb338ec6feefd671172f522`.
- Review-CI Run 374 war vollständig grün.
- Der öffentliche ETHUSDC-Exchange-Info-Snapshot und vollständige Protocol-v3-Run-Fingerprint waren vorhanden und pipelinegebunden.
- Die Filter `PRICE_FILTER`, `LOT_SIZE`, `MARKET_LOT_SIZE` sowie `MIN_NOTIONAL` und/oder `NOTIONAL` waren versioniert.
- Ein realer Exchange-Info-Snapshot und realer vollständiger Run-Fingerprint waren weiterhin nicht versiegelt; der reale Task-5-Datensnapshot blieb `BLOCKED_MISSING_WARMUP`.
- Keine Mengen-, Notional-, Gebühren- oder Rundungsparität war in Aufgabe 6 vorgezogen worden.

## Vorhandene Funktionen geprüft und wiederverwendet

Vor der Umsetzung wurden insbesondere inventarisiert:

- `src/ethusdc_bot/backtest/simulator.py`
  - vorhandene LONG-only-Signal-, Entry-, Exit-, Fee-, Slippage- und MTM-Logik;
  - vorhandene Menge bisher `trade_usdc / entry_price` ohne Exchange-Step-Size;
  - Entry- und Exit-Fee bereits auf dem jeweiligen tatsächlichen Notional;
  - Exit verwendete bereits dieselbe intern gespeicherte Menge.
- `src/ethusdc_bot/backtest/portfolio_simulator.py`
  - gemeinsamer deterministischer Reducer für Portfolio-Backtest und orderfreien Shadow-Replay;
  - bestehende Entry-/Exit-Zeitpunkte und Kapazitätsreservierung;
  - feste 100-USDC-Reservierung je logischem Lot.
- `src/ethusdc_bot/portfolio.py`
  - unveränderliches 100-USDC-Lot;
  - kein Compounding;
  - 10 bps Gebühr und 5 bps adverse Slippage je Seite.
- `src/ethusdc_bot/protocol_v3/run_identity.py`
  - validierter öffentlicher ETHUSDC-Exchange-Info-Snapshot;
  - kanonische Decimal-Filterwerte und Snapshot-Digest.
- `docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md`
- `docs/40_MONTHLY_ETHUSDC_RESEARCH_BLUEPRINT.md`
  - `requested=100`, `reserved=100`, `executed<=100` getrennt;
  - Fees zusätzlich;
  - Menge abrunden und beim Verkauf exakt wiederverwenden.

Die bestehende Protocol-v2-Simulationsengine wurde nicht strukturell umgebaut. Aufgabe 7 ergänzt eine getrennte Protocol-v3-Ausführungsparität, die dieselben bestehenden Signal- und Exit-Zeitpunkte verwendet und ausschließlich Menge, Notional, Gebühren und MTM-Werte nach den versiegelten Exchange-Filtern neu berechnet.

## Was umgesetzt wurde

### 1. Versionierter Execution-Parity-Vertrag

Neue Datei `configs/protocol_v3_execution_parity_contract.json` friert ein:

- Schema `protocol_v3_execution_parity_contract_v1`;
- Vertrag `ethusdc_spot_fixed_lot_execution_parity_v1`;
- Binance Spot `ETHUSDC`, LONG-only;
- angefordertes Entry-Notional exakt 100 USDC;
- reserviertes Entry-Notional exakt 100 USDC;
- ausgeführtes Entry-Notional höchstens 100 USDC;
- Fees zusätzlich und nicht aus dem 100-USDC-Lot abgezogen;
- kein Compounding;
- ein offenes Lot im kanonischen Research-Profil;
- exakte Decimal-Arithmetik;
- Rundung ausschließlich `ROUND_DOWN`;
- ein `stepSize=0` deaktiviert den jeweiligen Binance-Filter; mindestens ein positiver wirksamer Step bleibt Pflicht;
- gemeinsamer gültiger Step-Raster aller aktiven Filter;
- strengere gemeinsame Min-/Max-Mengengrenzen;
- Exit-Menge exakt gleich Entry-Menge;
- Anwendung von `MIN_NOTIONAL`/`NOTIONAL` gemäß Market-Flags;
- Entry- und Exit-Notionalprüfung;
- Entry-Fee auf ausgeführtem Entry-Notional;
- Exit-Fee auf ausgeführtem Exit-Notional;
- kanonischer Protocol-v3-Pfad ausschließlich mit 0,1 % Gebühr und 5 bps adverser Slippage je Seite; abweichende Aufruferwerte blockieren fail-closed;
- PRICE_FILTER-Min-/Max-Prüfung;
- Tick-Rundung ausdrücklich auf Aufgabe 8 verschoben;
- unveränderte Safety-Locks.

### 2. Gemeinsame exakte Ausführungsregeln

Neue Datei `src/ethusdc_bot/protocol_v3/execution_parity.py` leitet aus dem versiegelten Task-6-Exchange-Info-Snapshot die effektiven Ausführungsregeln ab.

Mengenraster:

- ein Step von null deaktiviert nur den jeweiligen Filter, wie es reale Binance-`MARKET_LOT_SIZE`-Payloads erlauben;
- mindestens ein Step muss positiv sein und die ausgeführte Menge muss auf jedem aktiven Raster liegen;
- bei zwei aktiven Rastern wird der effektive Raster exakt als gemeinsames Decimal-Mehrfaches bestimmt;
- die Entry-Menge wird immer nach unten auf diesen Raster abgerundet;
- niemals aufgerundet.

Mengengrenzen:

- Minimum ist die strengere gemeinsame Untergrenze;
- Maximum ist die strengere gemeinsame Obergrenze;
- kein gemeinsames Intervall blockiert fail-closed;
- Nullmenge, Unterminimum, Übermaximum oder Off-grid-Menge blockiert.

### 3. Getrennte Notional-Wahrheiten

Jeder Protocol-v3-Trade berichtet getrennt:

- `requested_entry_notional_usdc=100`;
- `reserved_entry_notional_usdc=100`;
- `executed_entry_notional_usdc<=100`;
- `unspent_reserved_notional_usdc`;
- `entry_cash_cost_including_fee_usdc`.

Berechnung:

```text
raw_quantity = 100 / tatsächlicher simulierter Entry-Fillpreis
executed_quantity = floor_to_exchange_step(raw_quantity)
executed_entry_notional = Entry-Fillpreis × executed_quantity
entry_fee = executed_entry_notional × fee_rate
entry_cash_cost_including_fee = executed_entry_notional + entry_fee
```

Der Fee-Betrag ist zusätzlich. Deshalb darf der gesamte Entry-Cash-Abfluss einschließlich Fee über 100 USDC liegen, während das ausgeführte Entry-Notional höchstens 100 USDC bleibt.

### 4. Notional-Filter

Angewendet werden die im Exchange-Info-Snapshot gespeicherten Market-Flags:

- `MIN_NOTIONAL.apply_to_market`;
- `NOTIONAL.apply_min_to_market`;
- `NOTIONAL.apply_max_to_market`.

Falls mehrere anwendbare Mindestgrenzen existieren, gilt die strengste. Für mehrere Maximalgrenzen gilt die strengste Obergrenze. Widersprüchliche Grenzen blockieren.

Sowohl Entry als auch Exit werden auf tatsächlichem simuliertem Fillpreis und tatsächlich ausgeführter Menge geprüft.

### 5. Gebühren- und Mengenparität

Entry:

```text
entry_fee = executed_entry_notional × fee_rate
```

Exit:

```text
executed_exit_notional = Exit-Fillpreis × exakt gekaufte Entry-Menge
exit_fee = executed_exit_notional × fee_rate
exit_proceeds_after_fee = executed_exit_notional - exit_fee
```

Der Exit verkauft exakt die gekaufte Menge. Eine zweite Rundung oder Neuberechnung der Exit-Menge ist verboten.

### 6. Protocol-v3-Single- und Portfolio-/Shadow-Parität

Neue öffentliche Pfade:

- `simulate_protocol_v3_strategy`;
- `simulate_protocol_v3_portfolio_strategy`.

Beide verwenden:

1. die bestehende Simulator-/Portfolio-Engine ausschließlich für Signal-, Entry- und Exit-Zeitpunkte;
2. dieselben Task-7-Decimal-Regeln zur Repricing-Berechnung;
3. dieselbe gekaufte Menge für den Exit;
4. dieselbe Fee- und Notional-Logik;
5. eine mit den neuen tatsächlichen Mengen und Gebühren neu aufgebaute MTM-Equity-Kurve.

Damit bleiben bestehender Backtest und orderfreier Portfolio-/Shadow-Replay im Task-7-Kern bitgleich.

### 7. Golden Trade

Fixture:

```text
Signalpreis: 1.900 USDC
nächster Entry-Mid: 2.000 USDC
Entry-Fill nach 5 bps: 2.001 USDC
Exit-Mid: 2.100 USDC
Exit-Fill nach 5 bps: 2.098,95 USDC
Step Size: 0,0001 ETH
Fee: 10 bps je Seite
```

Erwartetes und geprüftes Ergebnis:

```text
requested_entry_notional_usdc = 100,000000000
reserved_entry_notional_usdc  = 100,000000000
executed_quantity              = 0,049900000 ETH
executed_entry_notional_usdc   = 99,849900000
entry_fee_usdc                 = 0,099849900
executed_exit_notional_usdc    = 104,737605000
exit_fee_usdc                  = 0,104737605
gross_profit_usdc              = 4,887705000
fees_usdc                      = 0,204587505
net_profit_usdc                = 4,683117495
exit_quantity                  = 0,049900000 ETH
```

Single-Position- und Portfolio-Pfad liefern für alle gemeinsamen Trade-Felder exakt dieselben Werte.

### 8. Kein Compounding

Mehrere sequentielle Trades verwenden immer wieder:

```text
requested_entry_notional_usdc = 100
reserved_entry_notional_usdc = 100
compounding_enabled = false
```

Vorherige Gewinne oder Verluste verändern die nächste angeforderte Lotgröße nicht.

### 9. Pipelinebindung

`configs/protocol_v3_pipeline_contract.json` bindet jetzt per Quelldigest:

- `configs/protocol_v3_execution_parity_contract.json`;
- `src/ethusdc_bot/protocol_v3/execution_parity.py`;
- den bestehenden Single-Position-Simulator;
- den bestehenden Portfolio-/Shadow-Simulator.

Aktualisierte Komponentenverträge:

- Kostenmodell: `fee_10bps_slippage_5bps_actual_notional_v1`;
- Simulator: `conservative_spot_long_only_execution_parity_v1`.

Eine Änderung an Mengen-, Notional-, Fee- oder Rundungsregeln erzeugt damit eine neue Pipelinegeneration und verändert den Task-6-Run-Fingerprint.

## Aktueller ehrlicher Laufzustand

Die Task-7-Implementierung ist bereit und mit synthetischen Golden Trades getestet. Es wurde kein realer historischer Protocol-v3-Langlauf ausgeführt, weil:

- kein realer Task-6-Exchange-Info-Snapshot versiegelt ist;
- der reale Task-5-Datensnapshot weiterhin `BLOCKED_MISSING_WARMUP` ist;
- die vollständige historische Monatsorchestrierung erst in späteren Aufgaben entsteht.

Daher gilt:

```text
Task-7-Implementierung = bereit und getestet
Golden Trades = grün
realer Protocol-v3-Backtest mit versiegelten Filtern = noch nicht ausführbar
```

Das ist keine Performance-, Zielerreichungs- oder Freigabebehauptung.

## Neue und geänderte Dateien

- `configs/protocol_v3_execution_parity_contract.json`
- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/execution_parity.py`
- `src/ethusdc_bot/protocol_v3/__init__.py`
- `tests/unit/test_protocol_v3_execution_parity.py`
- `handoff/PROTOCOL_V3_TASK_07_2026-07-14.md`
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` – wird im Abschlussstand auf 7/33 aktualisiert

## Tests und Review

Die neue Suite prüft mindestens:

- unveränderten Task-6-Exchange-Info-Vertrag;
- exakten Task-7-Vertrag und Safety-Locks;
- positiven gemeinsamen LOT_SIZE-/MARKET_LOT_SIZE-Raster;
- strengere Min-/Max-Mengengrenzen;
- exakte Trennung von requested/reserved/executed Notional;
- Fees zusätzlich zum Lot;
- ausschließlich `ROUND_DOWN`;
- ausgeführtes Entry-Notional niemals über 100 USDC;
- Entry-Min-/Max-Notional;
- Exit-Min-/Max-Notional;
- Verkauf exakt der gekauften Menge;
- Golden Single Trade;
- bitgleiche gemeinsame Trade-Felder zwischen Single und Portfolio;
- MTM-Endpunkt gleich realisierter Netto-PnL;
- mehrere sequentielle Trades ohne Compounding;
- blockiertes 99-USDC-Requested-Lot;
- blockierte Off-grid-Exit-Menge.

CI-Historie:

1. Review-CI Run 379 zeigte zwei Fixtures mit `MARKET_LOT_SIZE.stepSize=0`. Die damalige Behandlung wurde am 2026-07-16 an die reale Binance-Semantik korrigiert: Null deaktiviert den einzelnen Filter und darf den aktiven `LOT_SIZE`-Raster nicht ungültig machen.
2. Negativtests erzwingen weiterhin, dass nicht beide Step-Raster deaktiviert sein dürfen.
3. Review-CI Run 380 auf Head `60d07c9732f19343b8176157d2503e64117ffea4` war vollständig grün.
4. Danach wurden Vertrag und Implementierung erneut bereinigt: aktive Step Sizes sind positiv; Null-Steps werden ausdrücklich als deaktivierter Einzelfilter behandelt.
5. Review-CI Run 382 auf Implementierungshead `ae1ecd63e379ec52b8013483b88c966fa4c8ea72` war vollständig grün:
   - komplette Pytest-Suite;
   - Python-Kompilierung;
   - PowerShell-Syntax;
   - Whitespace-Prüfung;
   - finaler Pytest-Status.
6. Der finale Dokumentations-/Handoff-Head wird erneut durch dieselbe Review-CI geprüft.

Ein realer Marktdaten- oder Langlauf ist wegen der dokumentierten Task-5-/Task-6-Blocker derzeit nicht möglich und wurde nicht erfunden.

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 8 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- keine Tick-Size-Rundung von Entry- oder Exit-Preisen;
- kein Next-Tradable-Price-Modell;
- keine neue Signalbar-/Entrybar-Reihenfolge;
- keine pessimistische Intrabar-Stop-/TP-Priorität;
- keine Gap-Fill-Logik;
- keine Änderung an Stop, TP, Trail oder Time Exit;
- keine Teilfills oder Orderbuchausführung;
- keine neue Slippage-Logik;
- keine Fold-, Purge-, Outer-State-, Router-, Feature-, Cache-, Report- oder UI-Arbeit;
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

## Codex-Startanweisung für Aufgabe 8

1. Branch `codex/research-resume-and-ui-state-v1` auf den finalen PR-Head ziehen.
2. `git status` muss sauber sein und lokaler `HEAD` muss GitHub entsprechen.
3. Dieses Handoff, Dokument 41, `configs/protocol_v3_execution_parity_contract.json`, `src/ethusdc_bot/protocol_v3/execution_parity.py` und die vorhandenen Simulatorfunktionen vollständig lesen.
4. Vorhandene Entry-, Exit-, Stop-, TP-, Trail-, Gap- und Slippage-Funktionen inventarisieren und wiederverwenden.
5. Danach ausschließlich Aufgabe 8 umsetzen.
6. Signalbar muss abgeschlossen sein; Entry frühestens am nächsten handelbaren Preis.
7. Bei gleichzeitiger Stop-/TP-Berührung muss die pessimistische Reihenfolge gelten.
8. Gaps müssen zum schlechteren tatsächlich handelbaren Preis gefüllt werden.
9. Task-7-Menge, Notional und Fees unverändert wiederverwenden.
10. Keine Fold-, Outer-State-, Feature-, Router-, Shadow-, Cache-, Report- oder UI-Arbeit vorziehen.

## Exakt nächstes Ticket

`Aufgabe 8 – Next-Tradable-Price und pessimistische Intrabar-Ausführung`
