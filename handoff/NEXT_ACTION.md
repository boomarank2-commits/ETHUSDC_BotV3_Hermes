# Next Action – Protocol v3 Aufgabe 29

Stand: 2026-07-20

## Startbedingung

Aufgabe 29 darf erst begonnen werden, wenn der Task-28-Dokumentations-Head mit Abschluss-Handoff, `CURRENT_STATUS.md`, dieser Datei und `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` vollständig gepusht und in GitHub CI grün ist.

Vor der ersten Codeänderung erneut vollständig lesen:

1. `AGENTS.md`
2. `handoff/CURRENT_STATUS.md`
3. `handoff/NEXT_ACTION.md`
4. `handoff/PROTOCOL_V3_TASK_28_2026-07-20.md`
5. `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`
6. `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md`
7. `configs/protocol_v3_contract.json`

## Exakter nächster Auftrag

Ausschließlich Aufgabe 29 umsetzen:

`Orderfreien Research-Challenger-Shadow bauen`.

## Bestehende Architektur zuerst prüfen

Vor neuen Dateien oder Komponenten vollständig prüfen und bevorzugt erweitern:

- `src/ethusdc_bot/protocol_v3/reporting.py` und `reporting_api.py`;
- `src/ethusdc_bot/protocol_v3/artifact_store.py` und `artifact_store_api.py`;
- `src/ethusdc_bot/protocol_v3/transactional_cache*.py`;
- vorhandene Forward-Ledger-/Trial-Ledger- und Checkpoint-Pfade;
- `src/ethusdc_bot/shadow/` einschließlich bestehender Adoption-/Shadow-Sperren;
- bestehende Drei-Markt-Kontext-, Simulator-, Execution- und Runtime-State-Schnittstellen;
- vorhandene Controller-/Runner-Strukturen;
- vorhandene Reporttypen und erlaubte Storage-Roots.

Keine zweite Reporting-, Storage-, Resume-, Simulator-, Router- oder Shadow-Architektur bauen, wenn eine vorhandene Stelle sicher erweitert werden kann.

## Pflichtumfang Aufgabe 29

Der Research-Challenger-Shadow muss:

- ausschließlich die vollständig validierte Task-28-Ausgabe als Startprovenienz akzeptieren;
- einen eigenen, versionierten Reporttyp besitzen;
- einen eigenen erlaubten Storage-Root und content-addressed Artefaktpfad verwenden;
- einen eigenen orderfreien Controller besitzen;
- ein eigenes Forward-Ledger führen, das an Pipelinegeneration, Task-28-Bundle, Snapshot, Kontext, Execution, Kosten, Exchange Info und Checkpoints gebunden ist;
- virtuelle Signale, Fills, Gebühren, Slippage, Positionen, MTM und Tageswerte mit derselben bestehenden Engine-/Simulatorlogik erzeugen;
- ETHUSDC als einziges Handelssymbol und BTCUSDC/ETHBTC ausschließlich als exakt ausgerichteten Kontext verwenden;
- Zeitpunkt `t` erst nach geschlossenen, exakt ausgerichteten ETHUSDC-, BTCUSDC- und ETHBTC-Bars verarbeiten;
- bei fehlenden, stale, zukünftigen oder versetzten Daten fail-closed pausieren beziehungsweise `NO_TRADE` liefern;
- Bundle-Gültigkeit, `valid_from`, `valid_until`, Task-24-Rotation, Exit-only-Handoff und höchstens ein offenes Lot einhalten;
- Resume ausschließlich aus dem letzten vollständig validierten, atomar publizierten Checkpoint erlauben;
- bei Familien-/Feature-/Pipelinewechsel eine neue Pipelinegeneration und ein leeres Forward-Ledger verlangen;
- klar von historischem Prozess-OOS, verbrauchtem Holdout, kanonischem Adoption-Shadow und späterem frischen Finalfenster getrennt bleiben.

## Harte Sperren

Der neue Pfad darf niemals:

- Orders erstellen oder senden;
- Binance-Private-/Account-Endpunkte oder API-Keys verwenden;
- Paper-, Testtrade- oder Live-Pfade starten;
- den bestehenden `adopt_for_shadow`- oder kanonischen Adoptionpfad verwenden;
- `active_config.json` oder eine handelbare Config schreiben;
- retrospektiv einen Challenger auswählen oder annehmen;
- Task-27-/Task-28-Historie als frische oder statistisch unterstützte Evidenz umetikettieren;
- sichtbare Forward-Daten in ein späteres versiegeltes Finalfenster aufnehmen;
- Quality-Gates, Kosten, Slippage, Exchange-Regeln oder Sicherheitslocks lockern;
- Fake-Trades, Fake-Fills oder Fake-Reports erzeugen.

Pflichtflags bleiben mindestens:

- `orders_allowed=false`
- `paper_allowed=false`
- `testtrade_allowed=false`
- `live_allowed=false`
- `trading_api_allowed=false`
- `canonical_adoption_eligible=false`
- `protocol_v3_final_status=false`

## Pflicht-Negativtests

Mindestens testen:

- falsche oder fehlende Task-28-Provenienz;
- Versuch, einen historischen oder abgelaufenen Challenger zu starten;
- Versuch, `adopt_for_shadow`, Paper, Testtrade, Live, Orders oder private API zu erreichen;
- fehlender oder falscher Drei-Markt-Watermark;
- stale, zukünftiger, versetzter oder lückenhafter Kontext;
- Bundle-, Pipeline-, Code-, Snapshot-, Exchange-, Kosten- oder Execution-Hash-Manipulation;
- Entry vor `valid_from`, nach `valid_until` oder während Exit-only;
- mehr als ein offenes Lot;
- Checkpoint-/Forward-Ledger-Manipulation, Teilwrite, falscher Head oder Cross-Generation-Resume;
- Familien-/Featurewechsel ohne neues leeres Forward-Ledger;
- UI-/Refresh- oder mehrfacher Controller-Aufruf verändert Signal-, Fill- oder Ledgerergebnis;
- Versuch, Research-Challenger-Evidenz als fresh, statistically supported, adoptionfähig oder Protocol-v3-final zu markieren.

## Abnahme

Aufgabe 29 ist erst `DONE_100`, wenn:

1. Reporttyp, Schema, Storage, Controller und Forward-Ledger vollständig implementiert sind;
2. vorhandene Simulator-/Execution-/Kontextfunktionen wiederverwendet werden;
3. Golden-Trade-/Paritätsfixtures und Negativtests vollständig grün sind;
4. vollständige Pytest-Suite, Python-Compile, PowerShell-Syntax und Whitespace grün sind;
5. Handoff, `CURRENT_STATUS.md`, `NEXT_ACTION.md` und `docs/41` aktualisiert und gepusht sind;
6. der abschließende GitHub-CI-Lauf des Dokumentations-Heads grün ist.

Aufgabe 30 darf vorher nicht begonnen werden.

## Sicherheitsstatus beim Einstieg

- kein Backtest-, Paper-, Testtrade-, Live- oder Order-Start;
- keine Secrets;
- kein neuer Finalstatus;
- der Bot darf nicht gestartet werden.
