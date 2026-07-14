# Protocol v3 – Handoff Aufgabe 5/33

Stand: 2026-07-14

## Status

`Protocol v3: Aufgabe 5/33 – Dynamischen Drei-Markt-Datensnapshot und Warmup herstellen – DONE_100`

Gesamtfortschritt nach Statusupdate: `5/33 = 15,15 %`

Exakt nächste Aufgabe: `Aufgabe 6 – Exchange-Info-Snapshot und vollständige Run-Fingerprints bauen`.

Codex darf Aufgabe 6 erst beginnen, nachdem der Branch lokal auf den finalen PR-Head dieses Handoffs gezogen und ein sauberer Arbeitsbaum bestätigt wurde.

## Vorherige Aufgabe kontrolliert

Vor Beginn wurde Aufgabe 4 vollständig gegen den aktuellen PR-Stand geprüft:

- PR #17 war offen, mergebar, Draft und nicht gemerged.
- Kontrollierter Ausgangs-Head: `1a4a5a48a693bc04247c507bdde467a0a4253222`.
- Review-CI Run 359 war vollständig grün.
- Das append-only Trial-Ledger, der historische Lower-Bound-Import und das Reconciliation-Gate waren vorhanden und pipelinegebunden.
- Der ehrliche Status blieb unverändert:
  - `historical_trial_count_is_lower_bound=true`;
  - `known_observed_historical_evaluation_rows=180`;
  - `independent_trial_count_resolved=0`;
  - `development_dsr_status=INSUFFICIENT_TRIAL_HISTORY`;
  - nur `NO_TRADE` freigabefähig.
- Keine Daten-Snapshot- oder Warmup-Arbeit war in Aufgabe 4 vorgezogen worden.

## Vorhandene Funktionen geprüft und wiederverwendet

Vor der Umsetzung wurden insbesondere inventarisiert:

- `src/ethusdc_bot/backtest/data_loader.py`
  - erlaubte Märkte ETHUSDC, BTCUSDC und ETHBTC;
  - ETHUSDC als einziger Handelsmarkt;
  - BTCUSDC und ETHBTC ausschließlich als Kontext;
  - ZIP-/CHECKSUM-Paarprüfung;
  - Binance-1m-CSV-Parsing;
  - Duplikat-, Schritt-, Preis-, Volumen- und OHLC-Prüfung;
  - exakte Drei-Markt-Zeitstempelausrichtung.
- `src/ethusdc_bot/data_pipeline/kline_zip_audit.py`
  - 1.440-Minuten-Tagesraster;
  - Gap-, Duplikat- und Sortierungsdiagnostik.
- `src/ethusdc_bot/data_pipeline/data_requirements.py`
- `src/ethusdc_bot/data_pipeline/catalog_schema.py`
- `src/ethusdc_bot/data_pipeline/inventory.py`
- `src/ethusdc_bot/protocol_v3/boundaries.py`
  - dynamische Ankerwahl aus dem letzten vollständigen Tag;
  - exakt 730 Trainingstage je Origin;
  - exakt 365 Prozess-OOS-Tage.

Es wurde kein zweiter Marktdatenparser, kein zweiter Downloader und keine zweite Simulationsengine gebaut.

## Was umgesetzt wurde

### 1. Versionierter Daten-Snapshot-Vertrag

Neue Datei `configs/protocol_v3_data_snapshot_contract.json` friert ein:

- Schema `protocol_v3_data_snapshot_contract_v1`;
- Vertrag `dynamic_three_market_snapshot_v1`;
- UTC und kleinste Quellbar 1 Minute;
- exakt 1.440 Minuten je vollständigem UTC-Tag;
- exakt 1.095 Fit-/Prozess-Tage;
- ETHUSDC als einziger Handelsmarkt;
- BTCUSDC und ETHBTC als nicht handelbare Kontextmärkte;
- dynamische gemeinsame Watermark;
- dynamischen Warmup;
- Qualitäts- und Nullvolumenregeln;
- kanonische SHA-256-Bindung und immutable Speicherung;
- unveränderte Safety-Locks.

### 2. Dynamische gemeinsame Drei-Markt-Watermark

Neue Datei `src/ethusdc_bot/protocol_v3/data_snapshot.py`:

- inventarisiert ausschließlich gepaarte, nicht leere tägliche ZIP-/CHECKSUM-Dateien;
- prüft ETHUSDC, BTCUSDC und ETHBTC;
- bestimmt den neuesten Tag, der in allen drei Märkten vollständig und inhaltlich gültig ist;
- verwendet keinen Produktions-Hardcode auf `2026-07-07` oder ein anderes festes Datum;
- leitet `process_end_exclusive` ausschließlich über die Task-2-Funktion `resolve_process_end_exclusive` ab;
- baut und validiert anschließend den unveränderten Task-2-Monatsplan.

Ein unvollständiger neuester Tag darf ausschließlich als trailing Diagnose verworfen werden. Eine Lücke oder ein ungültiger Tag innerhalb des ausgewählten Raw-/Warmup-/Fit-/Prozessintervalls blockiert.

### 3. Dynamischer Warmup

Der Warmup wird ausschließlich aus der vorab übergebenen aktiven Lookback-Menge berechnet:

```text
max_lookback_seconds = max(bars × bar_seconds aller aktiven ETH-/BTC-/ETHBTC-Lookbacks)
warmup_duration_seconds = max_lookback_seconds + 60 Sekunden
```

Pflichten:

- die aktive Lookback-Menge darf nicht leer sein;
- ETHUSDC, BTCUSDC und ETHBTC müssen jeweils mindestens vertreten sein;
- jede Zeitebene muss auf das 1m-Quellraster passen;
- fehlender Warmup in nur einem Markt blockiert;
- Warmup darf nur kausale Features speisen;
- Warmup darf keine Scaler, Quantile, Regimefits, Labels oder PnL speisen.

Für das Testbeispiel mit maximal 20 vollständigen Tagen gilt:

```text
max_lookback = 20 Tage
warmup_duration = 20 Tage + 1 Minute
```

Der vollständig auditierte Tagesumschlag beginnt deshalb am Kalendertag, der die exakte minutenweise Warmup-Grenze enthält. Die exakte Raw-Grenze bleibt sekundengenau im Snapshot erhalten.

### 4. Qualitätsprüfungen pro Markt und Tag

Jeder erforderliche UTC-Tag muss:

- exakt 1.440 Kerzen besitzen;
- exakt von `00:00` bis `23:59 UTC` reichen;
- streng aufsteigende 60.000-ms-Schritte besitzen;
- keine Duplikate und keine Lücken besitzen;
- endliche OHLCV-Werte besitzen;
- ausschließlich positive Preise besitzen;
- konsistente OHLC-Werte besitzen;
- kein negatives Volumen besitzen.

Nullvolumenregeln:

- einzelne Nullvolumenkerzen sind zulässig, werden gezählt und im Snapshot sichtbar gemacht;
- ein kompletter Tag mit 1.440 Nullvolumenkerzen blockiert;
- Nullvolumen wird nicht still verworfen oder als Liquidität behauptet.

### 5. Speicher- und Digest-Bindung

Der Snapshot bindet je Markt:

- den vollständigen UTC-Tagesbestand;
- das gemeinsame Minutenraster;
- den Marktinhalt;
- die ZIP-/CHECKSUM-Inventare;
- die Nullvolumenanzahl;
- alle Tagesaudit-Digests.

Zusätzlich bindet der kanonische Snapshot:

- Daten-Snapshot-Vertrag;
- gemeinsame Watermark;
- Task-2-Prozessgrenzen;
- aktive Lookbacks und Warmup;
- Rohdatenintervall;
- Marktrollen;
- Safety-Status.

Der Snapshot besitzt einen kanonischen SHA-256-Digest. Schreiben erfolgt create-only. Eine bestehende Snapshot-Datei kann nicht überschrieben werden. Inhaltliche Manipulation blockiert auch dann, wenn jemand nur den äußeren Digest neu berechnet.

### 6. Pipelinebindung

`configs/protocol_v3_pipeline_contract.json` bindet jetzt per Quelldigest:

- `configs/protocol_v3_data_snapshot_contract.json`;
- den vorhandenen Drei-Markt-Loader;
- `src/ethusdc_bot/protocol_v3/data_snapshot.py`.

Dadurch erzeugt jede Änderung an Watermark-, Warmup-, Qualitäts-, Marktrollen- oder Snapshotregeln eine neue Pipelinegeneration.

Dies ist noch kein vollständiger Run-Fingerprint. Exchange Info und die kombinierte Bindung aller Run-Identitäten bleiben ausschließlich Aufgabe 6.

## Aktueller ehrlicher Datenzustand

Der Blueprint dokumentiert derzeit exakt 1.095 gemeinsame vollständige Tage vom 09.07.2023 bis 07.07.2026. Protocol v3 verlangt zusätzlich den dynamisch berechneten Warmup vor dem ersten dieser 1.095 Fit-/Prozess-Tage.

Daher gilt aktuell ausdrücklich:

```text
Task-5-Implementierung = bereit und getestet
realer Protocol-v3-Snapshot mit dem bekannten 1.095-Tage-Bestand = BLOCKED_MISSING_WARMUP
```

Das ist kein Implementierungsfehler, sondern die beabsichtigte fail-closed Wirkung des Blueprints. Ein echter Snapshot kann erst erzeugt werden, wenn in allen drei Märkten genügend zusätzliche, vollständige und geprüfte UTC-Historie vor `D1` vorhanden ist. Dieser Task hat keine Daten heruntergeladen und keine fehlende Historie erfunden.

Da die aktive Featuremenge erst in späteren Aufgaben endgültig implementiert wird, muss jeder reale Lauf die dann eingefrorene aktive Lookback-Menge explizit an den Snapshot-Builder übergeben. Eine leere oder nur teilweise Drei-Markt-Lookback-Menge blockiert.

## Neue und geänderte Dateien

- `configs/protocol_v3_data_snapshot_contract.json`
- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/data_snapshot.py`
- `src/ethusdc_bot/protocol_v3/__init__.py`
- `tests/unit/test_protocol_v3_data_snapshot.py`
- `handoff/PROTOCOL_V3_TASK_05_2026-07-14.md`
- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` – wird im Abschlussstand auf 5/33 aktualisiert

## Tests und Review

Die neue Suite prüft mindestens:

- unveränderten Task-4-Lower-Bound- und `NO_TRADE`-Status;
- unveränderten Safety-Vertrag;
- exakte Vertragsfelder und blockierte Lockerung;
- Warmup `max(active lookbacks) + 1m`;
- Pflicht aller drei Märkte;
- blockierte leere, doppelte oder nicht 1m-ausgerichtete Lookbacks;
- dynamische Watermarks und Anker für 2024 und 2025;
- keinen Hardcode auf `2026-07-07`;
- protokollierten trailing unvollständigen Tag;
- blockierten fehlenden ETHBTC-Warmup;
- blockierten BTCUSDC-Gap im Pflichtintervall;
- drei unveränderliche Marktrollen;
- identischen gemeinsamen Minutenraster-Digest;
- immutable Snapshot-Schreiben;
- Digest- und semantische Manipulation;
- echten synthetischen 1.440-Zeilen-ZIP-Tag;
- einzelne Nullvolumenkerze als sichtbare Diagnose;
- blockierten 1.439-Zeilen-Tag;
- blockiertes ungültiges OHLC;
- blockierten vollständigen Nullvolumentag.

Review-CI Run 364 auf Implementierungshead `694aef277e69a096dd502cbdcb226fae7e6b4e09` war vollständig grün:

- komplette Pytest-Suite;
- Python-Kompilierung;
- PowerShell-Syntax;
- Whitespace-Prüfung;
- finaler Pytest-Status.

Der finale Dokumentations-/Handoff-Head wird erneut durch dieselbe Review-CI geprüft.

Ein realer Langlauf gegen `C:/TradingBot/data/ETHUSDC_BotV3_Hermes` konnte in der GitHub-CI nicht ausgeführt werden, weil diese lokale Windows-Rohdatenquelle dort nicht vorhanden ist. Der bekannte 1.095-Tage-Stand wäre ohnehin erwartungsgemäß wegen fehlendem Warmup blockiert. Die Dateiformat- und Inhaltslogik wurde mit echten synthetischen Binance-Tages-ZIPs geprüft.

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 6 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- kein Exchange-Info-Snapshot;
- keine PRICE_FILTER-, LOT_SIZE-, MARKET_LOT_SIZE-, MIN_NOTIONAL- oder NOTIONAL-Verarbeitung;
- kein vollständiger Run-Fingerprint;
- kein Cache-/Resume-Key auf dem neuen Snapshot;
- kein Daten-Download und keine Binance-API-Abfrage;
- keine Featureberechnung oder Multi-Timeframe-Resampling-Schicht;
- keine Simulator-, Strategie-, Router-, Gate-, Shadow- oder UI-Änderung;
- keine DSR-/PBO-Berechnung;
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

BTCUSDC und ETHBTC besitzen weiterhin `may_trigger_orders=false` und können nie als Handelsmarkt verwendet werden.

## Codex-Startanweisung für Aufgabe 6

1. Branch `codex/research-resume-and-ui-state-v1` auf den finalen PR-Head ziehen.
2. `git status` muss sauber sein und lokaler `HEAD` muss GitHub entsprechen.
3. Dieses Handoff, Dokument 41, `configs/protocol_v3_data_snapshot_contract.json`, `configs/protocol_v3_pipeline_contract.json` und `src/ethusdc_bot/protocol_v3/data_snapshot.py` vollständig lesen.
4. Vorhandene Exchange-Info-, Manifest-, Data-Fingerprint-, Resume- und Cache-Key-Funktionen inventarisieren und wiederverwenden.
5. Danach ausschließlich Aufgabe 6 umsetzen.
6. Exchange Info muss versioniert PRICE_FILTER, LOT_SIZE/MARKET_LOT_SIZE und MIN_NOTIONAL/NOTIONAL binden.
7. Der vollständige Run-Fingerprint muss mindestens Daten-Snapshot, Code, Pipeline, Features, Kontext, Gates, Kosten, Simulator, Boundary, Trial-Head und Exchange Info binden.
8. Jede Identitätsänderung muss Resume und Cache-Hit verhindern.
9. Keine Notional-/Rundungs-, Execution-, Feature-, Router-, Shadow- oder UI-Arbeit vorziehen.

## Exakt nächstes Ticket

`Aufgabe 6 – Exchange-Info-Snapshot und vollständige Run-Fingerprints bauen`
