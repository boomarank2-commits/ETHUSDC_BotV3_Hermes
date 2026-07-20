# Protocol v3 – Aufgabe 29 DONE_100

Stand: 2026-07-20

## Verbindlicher Abschlussstand

`29/33 = 87,88 % DONE_100`.

Aufgabe 29 ist vollständig umgesetzt, getestet, auf Branch `codex/research-resume-and-ui-state-v1` und in Draft-PR `#17` gepusht.

## Separater orderfreier Research-Challenger

Der neue Pfad ist ausschließlich ein `research_challenger_shadow`:

- Startprovenienz ist genau eine vollständig validierte Task-28-Entscheidung;
- Start erfolgt ausschließlich manuell und beginnt mit der ersten geschlossenen Forward-Minute nach der manuellen Aktivierung;
- `ETHUSDC` ist das einzige virtuelle Handelssymbol;
- `BTCUSDC` und `ETHBTC` bleiben ausschließlich exakt ausgerichteter, geschlossener Kontext;
- der Pfad besitzt keinen Zugang zu Orders, Konten, privaten Endpunkten, API-Keys, Paper, Testtrade oder Live;
- er besitzt keine Verbindung zu `adopt_for_shadow`, `active_config.json` oder einem kanonischen Adoptionpfad;
- historische Task-27-/Task-28-Evidenz bleibt `NOT_FRESH` und `diagnostic_only`.

Der Research-Challenger ist damit weder Botstart noch Paper-Trading noch Protocol-v3-Finalnachweis.

## Bestehende Engine statt zweiter Simulationsarchitektur

- Der Controller verwendet den vorhandenen inkrementellen Task-8-Intrabar-Reducer.
- Next-Tradable-Price, pessimistische Fill-Reihenfolge, Gebühren, Slippage, Mengen-/Preisrundung, Notional und höchstens ein offenes Lot bleiben identisch zur bestehenden Protocol-v3-Ausführung.
- Ein externes Entry-Veto darf nur eine geplante neue Entry-Reservierung kausal zurücknehmen; Exit, Stop, Trail, Break-even, MTM und bestehende Positionen werden nicht neu implementiert.
- Das Ende eines Datenpräfixes liquidiert keine offene Position künstlich.
- Warmup füllt ausschließlich kausalen Signal-/Featurezustand. Vor der manuellen Aktivierungsminute entstehen keine Signale, Fills, PnL- oder Forward-Ledger-Einträge.

## Drei-Markt-Kontext und Gültigkeit

Jede verarbeitete Minute verlangt:

- dieselbe geschlossene Minute für `ETHUSDC`, `BTCUSDC` und `ETHBTC`;
- einen vollständigen Task-10-Kontextbinding- und Watermark-Nachweis;
- keine stale, zukünftigen, doppelten, versetzten oder lückenhaften Kerzen;
- dieselbe eingefrorene Context-Veto-Policy wie im Task-28-Bundle;
- denselben Run-Fingerprint, Code, Pipelinegeneration, Snapshot, Exchange-Info-, Kosten- und Execution-Nachweis;
- Einhaltung von `valid_from`, `valid_until`, Task-24-Rotation, Exit-only-Handoff und Ein-Lot-Grenze.

Fehlende oder widersprüchliche Evidenz blockiert fail-closed. `CASH` erzeugt explizite Forward-Null-/No-Trade-Zeilen, aber niemals eine handelbare Freigabe.

## Eigenes Forward-Ledger

Das Task-29-Ledger ist:

- append-only und SHA-256-hashverkettet;
- an Pipelinegeneration und deren eigenen Forward-Namespace gebunden;
- bei Familien-, Feature-, Controller-, Execution- oder Pipelinewechsel zwingend leer und neu;
- ab der manuellen Aktivierungsminute lückenlos;
- idempotent bei Refresh, Wiederholung und Präfix-Replay;
- mit Kerzeninhaltsdigests, Kontextentscheidung, virtuellen Engine-Ereignissen, Fills, Gebühren, Slippage, Position, Pending-Entry, MTM, Realized PnL und Closing Equity versehen;
- dauerhaft mit `orders_created=0` und `private_api_calls=0` gesperrt.

Ein veränderter Record, Head, Cursor, Namespace oder Pipelinehash blockiert die Wiederherstellung.

## Report- und Artefaktintegration

Aufgabe 29 erweitert die vorhandenen Task-11-/Task-12-Schichten:

- eigener versionierter Reporttyp `research_challenger`;
- eigener erlaubter Storage-Root;
- content-addressed Artefakte für Trades, Daily MTM, Equity/Underwater und Diagnostik;
- Parent-Report-, Work-Unit-, Run-Fingerprint- und Pipeline-Provenienz;
- nur vollständig geschlossene UTC-Tage werden als Tagesartefakt publiziert;
- gespeicherte Reports und Objekte werden beim Lesen erneut semantisch validiert;
- keine Rohkerzen werden in Report-, Artefakt- oder Checkpointpayload kopiert.

## Transaktionales Checkpoint/Resume

Der bestehende Task-13-Store bleibt die einzige Checkpoint-Wahrheit:

- Task 29 speichert nur einen kompakten Receipt aus State-, Bundle-, Selection-, Run-, Pipeline-, Ledger-, Cursor- und Safety-Hashes;
- ein atomar publiziertes Task-13-`HEAD.json` bleibt die einzige sichtbare Resume-Grenze;
- nach Neustart wird der komplette Zustand aus Task 28 und dem öffentlichen Drei-Markt-Präfix deterministisch neu abgespielt;
- Resume wird nur akzeptiert, wenn der neu berechnete Receipt bitgleich ist;
- Cross-Generation-Resume, falscher Ledger-Head, Teilwrite, veraltete Identität oder manipuliertes Receipt blockiert.

Der Task-13-Vertrag wurde versioniert zu:

`protocol_v3_content_addressed_cache_and_transactional_resume_with_inner_selection_and_production_candidates_v4`.

Damit können echte, vollständig validierte Produktionskandidaten aus der abgeschlossenen Task-16→17→18-Kette gebunden werden. Synthetische Fixtures, ungebundene Kandidaten und widersprüchliche `NO_TRADE`-/`CANDIDATE`-Entscheidungen bleiben verboten.

## Pipelinegeneration

Vertrag, Controller, API, Evidenzadapter, Checkpointadapter und inkrementeller Intrabar-Reducer sind in die Pipelinegeneration eingebunden.

Jede Änderung an diesen Quellen erzeugt:

- eine neue Pipelinegenerations-ID;
- einen neuen Forward-Ledger-Namespace;
- ein leeres neues Forward-Ledger;
- keinen Treffer auf alte Task-13-Cache-/Resume-Stände.

## Pflichtflags und Ergebnisbedeutung

Alle Task-29-Ausgaben bleiben mindestens:

- `freshness=NOT_FRESH`;
- `diagnostic_only=true`;
- `statistically_supported=false`;
- `canonical_adoption_eligible=false`;
- `protocol_v3_final_status=false`;
- `orders_allowed=false`;
- `paper_allowed=false`;
- `testtrade_allowed=false`;
- `live_allowed=false`;
- `trading_api_allowed=false`.

## Negativ- und Paritätstests

Fail-closed geprüft werden unter anderem:

- fehlende, falsche oder manipulierte Task-28-Provenienz;
- Start vor Gültigkeit, historischer Rückfill oder abgelaufenes Bundle;
- falscher Drei-Markt-Watermark, Lücken, Duplikate, Versatz, stale oder zukünftige Daten;
- Pipeline-, Snapshot-, Kontext-, Exchange-, Kosten-, Execution-, Bundle- oder State-Hash-Manipulation;
- Entry außerhalb des Gültigkeitsfensters oder während Exit-only;
- mehr als ein offenes beziehungsweise reserviertes Lot;
- Side-Effect-Manipulation zu Orders oder privaten API-Aufrufen;
- Refresh-/Replay-Nichtdeterminismus;
- Report-/Artefakt-/Forward-Ledger-/Checkpoint-/HEAD-Manipulation;
- Cross-Generation-Resume und Familien-/Featurewechsel ohne leeres Ledger;
- falsche Freshness-, Support-, Adoption- oder Finalclaims;
- echte produktive Task-16→17→18-Kandidatenbindung sowie fortbestehende Fixture-Sperre.

## Wesentliche Abschlusscommits

- `3e48857d9ab42df356fb1e6009c53203bb94dc98` – ersten orderfreien Task-29-Controller und Forward-Ledger anlegen;
- `f963b697` – Vertrag, öffentliche API und Safety-Regressionsgrundlage ergänzen;
- `f5a8235afd67c1a4c27128e31e49caea05d51d4d` – Task-13-Vertrag v4 für echte validierte Produktionskandidaten fortschreiben;
- `6614fe4cdbccdcdfe706c14d2f8aa98f34051d9c` – kompakten Receipt-Rohdatennachweis präzisieren;
- `ce9321998e288274b88906e12c4f4579e6eea9ca` – echte stabile Task-16→17→18-Produktionsfixture herstellen;
- `96d069054a452f55ebccb29f964fe27ca5c5fe0b` – temporären Migrationsworkflow entfernen und bereinigten technischen Head herstellen.

## Validierung

GitHub-CI-Run `29736897831` auf technischem Head `96d069054a452f55ebccb29f964fe27ca5c5fe0b`:

- vollständige Suite: `1.233 Tests erfolgreich`;
- Python-Quellkompilierung: erfolgreich;
- PowerShell-Syntaxprüfung: erfolgreich;
- committed whitespace check: erfolgreich.

## Sicherheitsstatus

- kein Backtest-, Paper-, Testtrade-, Live- oder Order-Start;
- keine API-Keys, privaten Endpunkte oder Secrets;
- keine Quality-Gates gelockert;
- keine Fake-Trades, Fake-Fills oder Fake-Reports;
- kein kanonischer Adoptionpfad geöffnet;
- kein Protocol-v3-Finalstatus ohne wirklich neuen `sealed_final_holdout`;
- der Bot ist nicht start- oder live-fähig.

## Nächste Aufgabe

Aufgabe 30 – UI und Bedienzustände vollständig anschließen – darf erst nach grünem GitHub-CI-Lauf des Task-29-Dokumentations-Heads begonnen werden.
