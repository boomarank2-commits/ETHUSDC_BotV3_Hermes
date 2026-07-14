# Protocol v3 – Handoff Aufgabe 6/33

Stand: 2026-07-14

## Status

`Protocol v3: Aufgabe 6/33 – Exchange-Info-Snapshot und vollständige Run-Fingerprints bauen – DONE_100`

Gesamtfortschritt nach Statusupdate: `6/33 = 18,18 %`

Exakt nächste Aufgabe: `Aufgabe 7 – Notional-, Mengen-, Gebühren- und Rundungsparität herstellen`.

Codex darf Aufgabe 7 erst beginnen, nachdem der Branch lokal auf den finalen PR-Head dieses Handoffs gezogen und ein sauberer Arbeitsbaum bestätigt wurde.

## Vorherige Aufgabe kontrolliert

Vor Beginn wurde Aufgabe 5 vollständig gegen den aktuellen PR-Stand geprüft:

- PR #17 war offen, mergebar, Draft und nicht gemerged.
- Kontrollierter Ausgangs-Head: `90d5e0c4be6ca45ea979260c5834ded7ab696fc8`.
- Review-CI Run 366 war vollständig grün.
- Der dynamische Drei-Markt-Datensnapshot, die gemeinsame Watermark, das 1.440-Minuten-Tagesraster, die Qualitätsregeln und der dynamische Warmup waren vorhanden und pipelinegebunden.
- Der bekannte reale 1.095-Tage-Bestand blieb ehrlich `BLOCKED_MISSING_WARMUP`.
- Keine Exchange-Info- oder vollständige Run-Fingerprint-Arbeit war in Aufgabe 5 vorgezogen worden.

## Vorhandene Funktionen geprüft und wiederverwendet

Vor der Umsetzung wurden insbesondere inventarisiert:

- `src/ethusdc_bot/protocol_v3/data_snapshot.py`
  - unveränderlicher SHA-256-gebundener Drei-Markt-Snapshot;
  - Rohdaten-, Watermark-, Boundary-, Warmup- und Marktidentitäten;
  - create-only Speicherung und semantische Revalidierung.
- `src/ethusdc_bot/protocol_v3/pipeline.py`
  - content-addressed Pipelinegeneration;
  - Komponentenverträge und Quelldigests;
  - vollständiger 40-Zeichen-Git-Commit;
  - timestamp-freie kanonische Identitäten.
- `src/ethusdc_bot/protocol_v3/trial_ledger.py`
  - permanenter Trial-Counter-Namespace;
  - hashverketteter Ledger-Head;
  - Eventcount, Lower-Bound- und DSR-Status.
- `src/ethusdc_bot/backtest/research_loop_runner.py`
  - vorhandene atomische Protocol-v2-Resume-Artefakte;
  - Git-Commit- und Konfigurationsprüfung.
- `src/ethusdc_bot/backtest/research_supervisor.py`
  - vorhandene Revalidierung persistierter Cycles und Safety-Zustände.

Die Protocol-v2-Resume-Struktur wurde nicht umgedeutet. Aufgabe 6 ergänzt eine getrennte Protocol-v3-Identitätsschicht, die spätere Cache-/Resume-Implementierungen verwenden müssen.

## Was umgesetzt wurde

### 1. Versionierter Run-Identity-Vertrag

Neue Datei `configs/protocol_v3_run_identity_contract.json` friert ein:

- Schema `protocol_v3_run_identity_contract_v1`;
- Exchange-Info-Vertrag `binance_spot_ethusdc_exchange_info_snapshot_v1`;
- Run-Fingerprint-Vertrag `protocol_v3_complete_run_fingerprint_v1`;
- Binance Spot `ETHUSDC`, Basis `ETH`, Quote `USDC`, Status `TRADING`;
- öffentliche Payloads ohne private oder kontobezogene Daten;
- erforderliche Filter `PRICE_FILTER`, `LOT_SIZE`, `MARKET_LOT_SIZE`;
- mindestens einen Notional-Filter aus `MIN_NOTIONAL` oder `NOTIONAL`;
- kanonische Dezimalstrings;
- create-only Speicherung und SHA-256-Bindung;
- exakt zwölf erforderliche Laufidentitätsklassen;
- exakte Fingerprint-Gleichheit für Resume und Cache-Hit;
- unveränderte Safety-Locks.

### 2. Öffentlicher Exchange-Info-Snapshot

Neue Datei `src/ethusdc_bot/protocol_v3/run_identity.py` baut aus einem explizit übergebenen öffentlichen Binance-`exchangeInfo`-Payload einen unveränderlichen ETHUSDC-Snapshot.

Das Modul:

- führt selbst keinen Netzwerkaufruf aus;
- akzeptiert keine API-Keys, Signaturen, Accounts oder privaten Daten;
- verlangt genau eine ETHUSDC-Symbolzeile;
- verlangt `status=TRADING`;
- verlangt `baseAsset=ETH`, `quoteAsset=USDC`;
- verlangt aktiviertes Spot-Trading;
- erkennt doppelte oder fehlende Filter fail-closed;
- normalisiert Dezimalwerte ohne Float-Rundungsbehauptung;
- bindet Snapshot-Zeitpunkt, Vertrag, Filter, Herkunft und Safety per SHA-256;
- speichert create-only und erkennt nachträgliche Manipulation.

### 3. Versionierte Binance-Filter

Der Snapshot erfasst ohne bereits die Task-7-Ausführung zu implementieren:

- `PRICE_FILTER`
  - `min_price`;
  - `max_price`;
  - `tick_size`.
- `LOT_SIZE`
  - `min_qty`;
  - `max_qty`;
  - `step_size`.
- `MARKET_LOT_SIZE`
  - `min_qty`;
  - `max_qty`;
  - `step_size`.
- `MIN_NOTIONAL`, falls vorhanden
  - `min_notional`;
  - `apply_to_market`;
  - `avg_price_mins`.
- `NOTIONAL`, falls vorhanden
  - `min_notional`;
  - `max_notional`;
  - `apply_min_to_market`;
  - `apply_max_to_market`;
  - `avg_price_mins`.

`MIN_NOTIONAL`, `NOTIONAL` oder beide werden akzeptiert. Mindestens einer davon ist Pflicht. Die tatsächliche Mengenrundung und Notional-Anwendung bleibt ausschließlich Aufgabe 7.

### 4. Vollständiger Protocol-v3-Run-Fingerprint

Der timestamp-freie kanonische Fingerprint bindet mindestens:

1. Rohdaten-Snapshot und dessen SHA-256;
2. `as_of_day`;
3. vollständigen Git-Commit;
4. Pipelinegeneration und Pipelinevertrag;
5. Featurevertrag und Feature-Quelldigest;
6. Kontextvertrag und Kontext-Quelldigest;
7. Quality-Gate-Vertrag und Gate-Quelldigest;
8. Kostenmodellvertrag und Kosten-Quelldigest;
9. Simulatorvertrag und Simulator-Quelldigest;
10. Boundary-Vertrag und Boundary-Quelldigest;
11. permanenten Trial-Counter-Namespace, Trial-Ledger-Head, Eventcount, Lower-Bound- und DSR-Status;
12. Exchange-Info-Snapshot und Filterdigest.

Die Rohdatenidentität enthält zusätzlich die drei Marktinhalts-, Raster-, Archiv- und vollständigen-Tages-Digests für ETHUSDC, BTCUSDC und ETHBTC.

Der resultierende Schlüssel besitzt die Form:

```text
protocol_v3_run_sha256:<64-stelliger SHA-256>
```

`resume_key` und `cache_key` sind absichtlich identisch. Jede Änderung einer gebundenen Identität erzeugt einen anderen Schlüssel.

### 5. Fail-closed Resume- und Cache-Vertrag

`assert_resume_compatible` und `assert_cache_hit_compatible` verlangen vollständige Fingerprint-Gleichheit.

Getestete einzelne Änderungen, die blockieren:

- Rohdaten-Snapshot;
- Stichtag;
- Git-Commit;
- Pipelinegeneration;
- Featureidentität;
- Kontextidentität;
- Gate-Identität;
- Kostenmodellidentität;
- Simulatoridentität;
- Boundary-Identität;
- Trial-Ledger-Head;
- Exchange-Info-Snapshot.

Ein inhaltlich manipulierter Fingerprint blockiert auch ohne gültigen neuen Digest. Ein nachträglich geänderter Cache-/Resume-Key blockiert ebenfalls.

### 6. Pipelinebindung

`configs/protocol_v3_pipeline_contract.json` bindet jetzt per Quelldigest:

- `configs/protocol_v3_run_identity_contract.json`;
- `src/ethusdc_bot/protocol_v3/run_identity.py`.

Die Search-/Identity-Komponente trägt jetzt den Vertrag `protocol_v3_bounded_search_identity_global_budget_and_run_fingerprint_v1`.

Eine Änderung der Exchange-Info- oder Run-Fingerprint-Regeln erzeugt damit eine neue Pipelinegeneration. Der permanente Trial-Counter bleibt weiterhin generationsübergreifend.

## Aktueller ehrlicher Laufzustand

Die Task-6-Implementierung ist bereit und getestet. Es wurde jedoch kein realer ETHUSDC-Exchange-Info-Snapshot und kein vollständiger realer Protocol-v3-Run-Fingerprint erzeugt, weil:

- der GitHub-CI kein explizit versiegelter realer öffentlicher Binance-`exchangeInfo`-Payload vorlag;
- das Modul absichtlich keine Netzwerkabfrage ausführt;
- der bekannte reale Task-5-Datensnapshot weiterhin wegen fehlendem Warmup blockiert;
- noch kein vollständiger Protocol-v3-Lauf existiert.

Daher gilt:

```text
Task-6-Implementierung = bereit und getestet
realer Exchange-Info-Snapshot = noch nicht versiegelt
realer vollständiger Run-Fingerprint = noch nicht erzeugbar
```

Das ist keine Ergebnis-, Performance- oder Freigabebehauptung.

## Neue und geänderte Dateien

- `configs/protocol_v3_run_identity_contract.json`
- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/run_identity.py`
- `src/ethusdc_bot/protocol_v3/__init__.py`
- `tests/unit/test_protocol_v3_run_identity.py`
- `handoff/PROTOCOL_V3_TASK_06_2026-07-14.md`
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` – wird im Abschlussstand auf 6/33 aktualisiert

## Tests und Review

Die neue Suite prüft mindestens:

- unveränderten Task-5-Warmup-Vertrag;
- exakten Run-Identity-Vertrag und unveränderte Safety-Locks;
- Normalisierung und Bindung aller Pflichtfilter;
- `MIN_NOTIONAL`, `NOTIONAL` oder beide;
- fehlenden Pflichtfilter;
- falsche Quote `USDT` als Fehler;
- private oder kontobezogene Felder als Fehler;
- create-only Exchange-Info-Snapshot;
- Digestmanipulation;
- deterministischen vollständigen Run-Fingerprint;
- alle zwölf gebundenen Identitätsklassen;
- blockiertes Resume und blockierten Cache-Hit nach jeder einzelnen Identitätsänderung;
- manipulierten Fingerprint ohne passenden Digest;
- abweichenden permanenten Trial-Namespace;
- create-only Fingerprint-Speicherung;
- veränderte gespeicherte Cache-/Resume-Keys.

CI-Historie:

1. Review-CI Run 371 fand ausschließlich einen Fehler in der künstlichen Testfixture: Für den dritten Markt war versehentlich ein 128-stelliger statt 64-stelliger SHA-256-Testwert konstruiert worden. Die Produktionsprüfung blockierte diesen ungültigen Digest korrekt fail-closed.
2. Ausschließlich die Testfixture wurde korrigiert; Produktions- und Schutzlogik blieben unverändert.
3. Review-CI Run 372 auf Implementierungshead `a74e47e1c2cde1e8aa08bf5c4d641ed769d82d51` war danach vollständig grün:
   - komplette Pytest-Suite;
   - Python-Kompilierung;
   - PowerShell-Syntax;
   - Whitespace-Prüfung;
   - finaler Pytest-Status.
4. Der finale Dokumentations-/Handoff-Head wird erneut durch dieselbe Review-CI geprüft.

Ein Marktdaten-, Backtest- oder Langlauf ist für die reine Identity-/Snapshot-Aufgabe fachlich nicht erforderlich und wurde nicht vorgezogen.

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 7 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- keine Berechnung der aus 100 USDC kaufbaren Menge;
- keine Abrundung auf `LOT_SIZE` oder `MARKET_LOT_SIZE`;
- keine Prüfung eines konkreten Orders gegen Min-/Max-Notional;
- keine Trennung requested/reserved/executed Entry-Notional;
- keine Gebührenbuchung;
- kein Verkauf der exakt gekauften Menge;
- keine Golden Trades;
- keine Execution-, Slippage-, Stop-, TP- oder Simulatoränderung;
- kein vollständiges Task-13-Cache-/Checkpoint-Store-System;
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

## Codex-Startanweisung für Aufgabe 7

1. Branch `codex/research-resume-and-ui-state-v1` auf den finalen PR-Head ziehen.
2. `git status` muss sauber sein und lokaler `HEAD` muss GitHub entsprechen.
3. Dieses Handoff, Dokument 41, `configs/protocol_v3_run_identity_contract.json`, `src/ethusdc_bot/protocol_v3/run_identity.py` und den Portfolio-/Shadow-Produktvertrag vollständig lesen.
4. Vorhandene Simulator-, Mengen-, Gebühren-, Notional- und Golden-Trade-Funktionen inventarisieren und wiederverwenden.
5. Danach ausschließlich Aufgabe 7 umsetzen.
6. Requested, reserved und executed Entry-Notional getrennt behandeln.
7. Mengen ausschließlich nach den versiegelten Exchange-Filtern abrunden; nie aufrunden.
8. Fees zusätzlich auf tatsächlich ausgeführtem Notional verbuchen; Verkauf verwendet exakt die gekaufte Menge.
9. Keine Execution-Reihenfolge, Intrabar-Logik, Feature-, Router-, Shadow- oder UI-Arbeit vorziehen.

## Exakt nächstes Ticket

`Aufgabe 7 – Notional-, Mengen-, Gebühren- und Rundungsparität herstellen`
