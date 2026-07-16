# Protocol v3 – Aufgabe 12 Pfadwächter-Korrektur

Stand: 2026-07-16

## Anlass

Beim vorgeschriebenen adversarialen Review vor Aufgabe 13 wurde ein konkreter Reihenfolgefehler im öffentlichen Task-12-Lesepfad gefunden.

Der Kernvalidator lehnte einen fremden oder symlinkierten Indexpfad zwar nach der semantischen Prüfung ab, öffnete die Datei aber zuvor bereits. Damit war die im Task-12-Handoff behauptete Root-/Symlink-Sperre im öffentlichen Einstiegspunkt nicht vollständig fail-closed vor dem ersten Read.

## Korrektur

Die stabile Fassade `src/ethusdc_bot/protocol_v3/artifact_store_api.py` prüft nun vor jedem Datei-Read:

- reales, nicht symlinkiertes Repository-Root;
- vorhandene, reale Protocol-v3-Indexroot;
- keine absolute oder relative Flucht aus der Repository- beziehungsweise Indexroot;
- keine vorhandene Symlink-Komponente;
- aufgelöster Zielpfad liegt tatsächlich innerhalb der festen Indexroot.

Erst danach wird der bestehende vollständige kanonische und semantische Task-12-Validator aufgerufen.

## Regressionstests

`tests/unit/test_protocol_v3_artifact_store_path_guard.py` prüft:

- äußerer ungültiger JSON-Pfad wird wegen Root-Flucht und nicht wegen JSON-Parsing abgelehnt;
- Symlink auf einen äußeren ungültigen JSON-Pfad wird vor dem Öffnen blockiert.

## Scope

Unverändert bleiben:

- content-addressed Objektbytes und Digests;
- Referenz- und Provenienzsemantik;
- Größenpolitik und Deduplikation;
- Parent-Report-Revalidierung;
- Safety-Sperren;
- Task 13 bleibt bis zur grünen Review-CI dieser Korrektur unbegonnen.

## Commits

- Testcommit: `4622e71e371399c428306d4517a21df72ea60c3a`
- Produktionskorrektur: `ff6751ecda0935f1dd0ce50d1acfd4717be27579`

Der finale CI-Nachweis wird im Task-13-Handoff dokumentiert.
