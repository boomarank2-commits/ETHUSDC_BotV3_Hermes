# Protocol v3 – Handoff Aufgabe 12/33

Stand: 2026-07-16

## Status

`Protocol v3: Aufgabe 12/33 – Kompakte Artefaktarchitektur – DONE_100`

Gesamtfortschritt: `12/33 = 36,36 %`.

Exakt nächste Aufgabe: `Aufgabe 13 – Content-addressed Cache und transaktionales Resume`.

## Geprüfter Ausgangsstand

Ausgangs-Head vor dem vorgeschriebenen Review von Aufgabe 11:

`b54e0c1dbe1a4b3db5dfdaee8ca6190dbb3d6ba6`

PR #17 blieb offen, Draft und ungemerged.

## Adversariales Review von Aufgabe 11

Aufgabe 11 wurde vor Task 12 am echten Code geprüft. Fachlich korrekt waren insbesondere:

- abgeleitete statt frei behauptete Freshness-, Support- und Adoptionssemantik;
- create-only Forward-Registrierungen mit vollständiger Reload-Revalidierung;
- automatische Berücksichtigung aller persistierten sichtbaren Forward-Monate;
- feste Reportroots, Traversal-/Alias-/Symlink-Sperren;
- Legacy-Final-/Shadow-Ablehnung;
- Pipeline- und Run-Fingerprint-Bindung;
- unveränderte Safety-Sperren.

Gefunden wurde eine reale Integrationslücke: `reporting.py` war implementiert und getestet, aber es fehlte ein ausdrücklich stabiler öffentlicher Protocol-v3-Fassadenmodulname. Das frühere Handoff behauptete damit mehr öffentliche Verkabelung als tatsächlich vorhanden war.

## Separate Task-11-Korrektur

Korrekturcommit:

`43ba634f523b10147e98f6534ec0893cdfbde076`

Umgesetzt wurden:

- `src/ethusdc_bot/protocol_v3/reporting_api.py` als stabile validierte Task-11-Fassade;
- `tests/unit/test_protocol_v3_reporting_public_api.py`;
- Pipelinebindung der Fassade;
- Wiederherstellung und Korrektur des Task-11-Handoffs.

Review CI Run 422 war vollständig grün:

`https://github.com/boomarank2-commits/ETHUSDC_BotV3_Hermes/actions/runs/29496179947`

Ein vorheriger GitHub-Contents-Aufruf hatte die Task-11-Handoff-Datei kurzzeitig durch einen Platzhalter ersetzt (`f950ba87d3145f914aeb68c606b79d863c90ca98`). Dieser reine Dokumentationsfehler wurde im unmittelbar folgenden Korrekturcommit vollständig repariert. Produktionscode und Evidenzsemantik waren davon nicht betroffen.

## Task-12-Implementierung

Implementierungscommits:

- `1eff71a4102779694d94502251b7dac732bca901` – Vertrag, Store, öffentliche Fassade und Tests;
- `40f52e153aed29d173ded690dd540c54e9e4b11d` – ausschließlich Gitignore-Sperre für generierte Artefakte.

Geänderte beziehungsweise neue Produktionsdateien:

- `configs/protocol_v3_artifact_store_contract.json`;
- `configs/protocol_v3_pipeline_contract.json`;
- `src/ethusdc_bot/protocol_v3/artifact_store.py`;
- `src/ethusdc_bot/protocol_v3/artifact_store_api.py`;
- `.gitignore`.

Tests:

- `tests/unit/test_protocol_v3_artifact_store.py`.

## Versionierter Vertrag

Eingefroren wurden:

- Vertrag: `protocol_v3_compact_artifact_store_v1`;
- Objektschema: `protocol_v3_artifact_object_v1`;
- Referenzschema: `protocol_v3_artifact_reference_v1`;
- Indexschema: `protocol_v3_artifact_index_v1`;
- Größenpolitik: `protocol_v3_compact_index_size_policy_v1`.

Feste Roots:

- Objekte: `reports/protocol_v3/artifacts/objects`;
- Indizes: `reports/protocol_v3/artifact_indexes`.

Beide Roots sind Git-ignoriert. Große Laufartefakte werden nicht in Git aufgenommen.

## Getrennte Artefaktklassen

Es existieren getrennte, streng validierte Objektarten für:

1. `trades` – geordnete eindeutige Trades;
2. `daily_mtm` – vollständige zusammenhängende UTC-Tagesreihe einschließlich echter Nulltage;
3. `equity_underwater` – geordnete eindeutige Equity-/Underwater-Punkte;
4. `diagnostics` – Fold-, Kandidaten- und Diagnostikevidenz.

Ein echter Nulltag mit `0.0` bleibt vorhanden und ist maschinell von einem fehlenden Tag unterscheidbar. Fehlende, doppelte oder ungeordnete Tage blockieren.

## Content Addressing und Deduplikation

Für jedes Objekt werden ausschließlich aus den tatsächlich kanonisch serialisierten Bytes berechnet:

- SHA-256;
- Bytegröße;
- logische Kardinalität.

Aufruferwerte in einem manipulierten `ArtifactPayload` werden nicht vertraut, sondern aus dem Inhalt neu berechnet.

Objektpfad:

```text
<artifact_kind>/<sha256-prefix-2>/<sha256>.json
```

Identische kanonische Bytes derselben Artefaktsemantik werden genau einmal gespeichert und können über verschiedene Referenz-IDs mehrfach referenziert werden. Unterschiedliche Inhalte erhalten unterschiedliche Digests und Pfade.

Ein bereits vorhandenes Objekt wird vollständig gelesen, streng geparst, kanonisch und fachlich validiert sowie gegen Digest, Größe, Kardinalität, Art und Schema geprüft. Es wird niemals blind überschrieben.

## Referenzindex und Provenienz

Der kompakte Index enthält keine langen fachlichen Reihen und keine Rohkerzen. Er enthält ausschließlich Referenzen und einmalig die Work-Unit-Identität.

Jede Referenz bindet:

- Artefaktart und Schema;
- SHA-256;
- Bytegröße;
- logische Kardinalität;
- relativen content-addressed Pfad;
- Elternreport-ID und tatsächlichen Elternreport-SHA;
- vollständigen Run-Fingerprint;
- Pipelinegeneration;
- Work-Unit-ID und Work-Unit-SHA.

Der Elternreport wird über die öffentliche Task-11-Fassade aus seiner festen Root erneut validiert. Der Index kann nicht durch eine frei behauptete Report-, Pipeline- oder Work-Unit-Identität freigeschaltet werden.

## Schreib- und Reload-Reihenfolge

Ablauf:

```text
validierter Task-11-Elternreport
→ Artefaktbytes kanonisieren und fachlich validieren
→ Objekte create-only schreiben und fsync
→ jedes Objekt vollständig reloaden und erneut validieren
→ kompakten Referenzindex create-only veröffentlichen
→ Index und alle transitiven Objekte erneut laden und validieren
```

Task 12 behauptet keine vollständige Crash-/Resume-Transaktion. Ein abgeschnittenes oder manipuliertes Objekt beziehungsweise ein Teilindex wird beim nächsten Lesen blockiert. Lock-, Checkpoint-, Commit-/Replace- und Restart-Idempotenz bleiben ausschließlich Aufgabe 13.

## Pfad- und Inhalts-Sicherheit

Fail-closed blockiert werden:

- absolute oder traversierende Referenzpfade;
- Backslash-/POSIX-Verwechslungen;
- Symlink-Komponenten und Symlink-Objekte;
- falsche Root, Art, Schema oder Provenienz;
- fehlende, verkürzte oder manipulierte Objekte;
- Duplicate JSON Keys;
- `NaN` und Infinity;
- unbekannte Indexfelder;
- eingebettete Rohkerzen, Klines, OHLCV- oder 1m-Marktbar-Reihen.

## Versionierte Größenpolitik

Der Blueprint nennt keine willkürliche MB-Grenze. Daher wurde eine begründete versionierte Politik eingefroren:

```text
12 Origins × 8 Cycles × 4 Artefaktarten = 384 Referenzen
```

Grenzen:

- repräsentative Last: 384 Referenzen;
- Maximum: 768 Referenzen (2× Headroom);
- maximaler Index: 1 MiB;
- maximale einmalig eingebettete Work-Unit-Identität: 16 KiB.

Der synthetische 12-Origin-Test belegt, dass die Indexgröße von der Referenzanzahl, nicht von Millionen 1m-Candles oder mehrfachen Equity-Kopien wächst.

## Tests und CI

Neue Task-12-Tests: 15.

Abgedeckt sind:

- exakter Vertrag, öffentliche Fassade und Pipelinebindung;
- Roundtrip aller vier Artefaktklassen und Summen;
- echter Nulltag versus fehlende Tageszeile;
- Deduplikation identischer Bytes bei getrennten Referenzen;
- unterschiedliche Inhalte ohne Namens-/Metadatenkollision;
- fehlende, verkürzte oder manipulierte Objekte;
- vertauschte Art/Schema und falsche Provenienz bei formal neu berechnetem Indexdigest;
- vorhandenes korruptes Digestobjekt wird nicht überschrieben;
- Traversal-, Symlink- und Rohkerzensperren;
- repräsentativer 384-Referenz-Index;
- Indexgröße unabhängig von fachlichen Zeilenmengen;
- Neuberechnung von Digest, Größe und Kardinalität;
- Duplicate Keys, nichtfinite Werte und unbekannte Felder;
- Gitignore-Sperre der generierten Roots.

Review CI Run 423:

`https://github.com/boomarank2-commits/ETHUSDC_BotV3_Hermes/actions/runs/29497781522`

Ergebnis:

- vollständige Suite: 1.080 Tests erfolgreich;
- Python-Kompilierung: grün;
- PowerShell-Syntax: grün;
- Whitespace: grün;
- abschließender Pytest-Gate-Schritt: grün.

## Ehrlicher aktueller Zustand

```text
Task-12-Vertrag und Store = implementiert und pipelinegebunden
Objekte/Index Roundtrip und Manipulationstests = grün
Task-11-Korrektur = separat implementiert und CI-grün
Task-13 transaktionales Resume = nicht implementiert
realer Protocol-v3-Langlauf = weiterhin nicht ausführbar
Performance-/3-USDC-/Final-/Live-Freigabe = nicht behauptet
```

## Explizit nicht umgesetzt

Keine Aufgabe 13 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- keine Checkpoint-/Resume-Transaktion;
- keine Writer-Locks oder stale Lock-Heilung;
- keine Cache-Hit-Logik;
- kein Fold-Planer;
- keine Kandidatenauswahl, Matrix, PBO oder DSR;
- kein Feature-Store;
- keine Outer-Origin-Orchestrierung;
- kein Challenger-Controller;
- kein Final-Evaluator;
- keine UI;
- keine Orders, Trading-API, API-Keys, Paper, Testtrade oder Live.

## Startanweisung für Aufgabe 13

Vor Aufgabe 13 muss Aufgabe 12 adversarial anhand des dann aktuellen Codes kontrolliert werden. Besonders zu prüfen sind:

- vollständige transitive Revalidierung jedes Objekts und Indexes;
- keine vom Aufrufer behauptbaren Digest-, Größen-, Kardinalitäts- oder Provenienzwerte;
- create-only Deduplikation ohne blindes Vertrauen in vorhandene Objekte;
- echte Nulltage versus fehlende Evidenz;
- Root-/Traversal-/Symlink-Sicherheit;
- kompakte, nicht candle-proportionale Indizes;
- Pipeline-/Fingerprintbindung;
- keine fälschliche Task-13-Transaktionsbehauptung.

Gefundene Fehler müssen vor Task 13 in einem eigenen Commit korrigiert und mit grüner CI abgeschlossen werden.

## Exakt nächstes Ticket

`Aufgabe 13 – Content-addressed Cache und transaktionales Resume`
