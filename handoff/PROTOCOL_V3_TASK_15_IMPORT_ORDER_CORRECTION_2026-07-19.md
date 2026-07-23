# Protocol v3 – Aufgabe 15 Importreihenfolge-Korrektur

Stand: 2026-07-19

## Ausgangslage

Aufgabe 15 war am Branch-Stand nach dem Re-Audit der Aufgaben 11 bis 14 als `DONE_100` dokumentiert. Vor Aufgabe 16 wurde der tatsächliche Task-15-Code erneut in frischen Prozessen und ohne vorherigen Facade-Import geprüft.

Veröffentlichter kombinierter Korrekturcommit:

`087d816ac4299489a94a51efa3991b7fee62163e`

## Gefundener Fehler 1 – Transaktionsvertrag nur nach Facade-Import v3

`configs/protocol_v3_transaction_contract.json` verlangte bereits:

`protocol_v3_content_addressed_cache_and_transactional_resume_with_inner_selection_v3`

Das eigentliche Kernmodell `transactional_cache_model.py` enthielt jedoch weiterhin die Task-14-v2-Konstanten. Erst `transactional_cache.py` änderte Konstanten, kanonischen Vertrag und Transition-Validatoren zur Laufzeit per Monkey-Patch.

Ein frischer Prozess mit direktem Import des Kernmodells konnte deshalb seinen eigenen versionierten Vertrag nicht laden und scheiterte mit `Protocol v3 transaction contract is not canonical`.

## Korrektur 1

Die Task-15-v3-Wahrheit liegt jetzt direkt im Kernmodell:

- Vertragsschema v3;
- Transaktionsvertragsversion mit Inner Selection v3;
- Transaktionsidentität v3;
- `bound_candidate_selection_required=true`;
- Deferred Scope beginnt bei den Aufgaben 16 bis 18;
- Kandidatenslot wird direkt als vollständige semantisch revalidierte Task-15-Entscheidung geprüft;
- synthetische Fixture-Entscheidungen und produktive Kandidatenauswahl vor Aufgaben 16 bis 18 bleiben blockiert;
- Fold-, Run-Fingerprint- und abgeleitete Identitätsslots bleiben gegenseitig gebunden.

`transactional_cache.py` ist nun eine reine stabile Re-Export-Fassade über Modell und Store. Sie verändert keine Produktionswahrheit mehr beim Import.

## Gefundener Fehler 2 – Fail-closed Selector nur nach API-Import

Die robuste Behandlung unvollständiger Kandidatenevidenz lag in `inner_selection_api.py` und ersetzte beim Import die interne Funktion `_selection_basis` des Kernmoduls.

Ein direkter Import von `inner_selection.py` konnte deshalb bei unvollständiger Ranking-Evidenz anders reagieren beziehungsweise mit `KeyError`/`TypeError` abbrechen, während die öffentliche Facade typisiertes `NO_TRADE` lieferte.

## Korrektur 2

Die fail-closed Entscheidungsberechnung liegt jetzt direkt in `inner_selection.py`:

- Quality Gates werden vor Rankingfeldern ausgewertet;
- Ranking wird nur nach bestandenem Gate gelesen;
- fehlende oder widersprüchliche Ranking-Evidenz erzeugt maschinenlesbare Blocker;
- unvollständige Produktionsbeweise bleiben typisiertes `NO_TRADE`;
- das 3-USDC-Ziel bleibt außerhalb von Ranking, Loss und Stopregeln.

`inner_selection_api.py` ist nun ebenfalls eine reine stabile Re-Export-Fassade und patcht das Kernmodul nicht mehr.

## Regressionstests

Neu beziehungsweise erweitert:

- Core- und Public-Selector verwenden dieselbe im Kern definierte Funktion;
- ein frischer Prozess lädt `transactional_cache_model.py` direkt;
- Modellkonstante und geladener JSON-Vertrag sind ohne Facade-Import identisch v3;
- bestehende Missing-Evidence-, Kandidatenidentitäts-, Cache-, Resume-, Fold- und Ledger-Tests bleiben grün.

## Lokale Validierung

```text
gezielte Task-15-/Transaktionssuite: 22 Tests erfolgreich
vollständige Suite: 1.118 Tests erfolgreich
python -m compileall -q src: erfolgreich
frischer Core-Import des Transaktionsvertrags: erfolgreich v3
```

Die verbindliche GitHub-Review-CI ist auf dem nachfolgenden normalen Connector-Commit erneut auszuführen. Erst ein grüner finaler Head bestätigt den Abschluss.

## Nicht verändert

- keine Kandidaten-Tagesmatrix aus Aufgabe 16;
- keine Promotion 12 → 3 → 2;
- keine PBO-/CSCV- oder DSR-Berechnung;
- keine Strategie-, Parameter-, PnL-, Gate- oder Rankingänderung;
- keine Paper-, Testtrade-, Live-, Order- oder API-Freigabe.

## Nächster Schritt

Nach grüner Review CI ist Aufgabe 16 die exakt nächste zulässige Aufgabe. Vor ihrer Umsetzung ist Aufgabe 15 am dann aktuellen Head noch einmal kurz auf Core-/Facade-Parität, vollständige 730-Tage-/6-Fold-Bindung und produktives `NO_TRADE` ohne Aufgaben-16-bis-18-Evidenz zu kontrollieren.
