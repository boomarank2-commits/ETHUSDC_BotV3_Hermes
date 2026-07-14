# Protocol v3 – Handoff Aufgabe 2/33

Stand: 2026-07-14

## Status

`Protocol v3: Aufgabe 2/33 – Monatskalender und Boundary-Vertrag implementieren – DONE_100`

Gesamtfortschritt: `2/33 = 6,06 %`

Exakt nächste Aufgabe: `Aufgabe 3 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren`.

Codex darf Aufgabe 3 erst beginnen, nachdem der Branch lokal auf den finalen PR-Head dieses Handoffs gezogen und ein sauberer Arbeitsbaum bestätigt wurde.

## Vorherige Aufgabe kontrolliert

Vor Beginn wurde Aufgabe 1 gegen den aktuellen PR-Head kontrolliert:

- PR #17 war offen, mergebar, Draft und nicht gemerged.
- Head vor Aufgabe 2 war `61e8bc7c45c88202707f10bb1f4555ea482a78c7`.
- Vertragsmanifest, Validator, Vertragstests und Handoff aus Aufgabe 1 waren vorhanden.
- Die Protocol-v2-Datei `src/ethusdc_bot/backtest/split.py` wurde geprüft und bewusst nicht umgedeutet oder verändert.

Bei der Abschlusskontrolle wurde entdeckt, dass `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md` beim vorherigen Statusupdate versehentlich auf 67 Zeilen gekürzt worden war. Die vollständige Sequenz 1–33 wurde in diesem Arbeitszyklus wiederhergestellt und Aufgabe 2 korrekt eingetragen.

## Was umgesetzt wurde

Eine neue, reine Protocol-v3-Boundary-Schicht wurde erstellt. Sie besitzt keine Kandidatensuche, keine PnL, keine Marktdatenzugriffe und keine Trading-Funktion.

Verbindlich umgesetzt:

- Zeitzone ausschließlich UTC.
- Deployment-Ankertag 8.
- `process_start_inclusive = process_end_exclusive - 365 Tage`.
- Genau 13 Grenzen `b0..b12` und daraus exakt zwölf äußere Origins.
- `b0` ist immer der konzeptionell synthetische erste Prozesszeitpunkt, auch wenn sein Kalendertag zufällig auf den 8. fällt.
- `b1..b12` sind echte Monatsanker.
- Je Origin exakt 730 Entwicklungstage `[test_start-730, test_start)`.
- OOS-Intervall exakt `[test_start, test_end)`.
- `as_of_day = test_start - 1 UTC-Tag`.
- `valid_from = test_start + 24 Stunden`.
- `valid_until = test_end`.
- `manual_decision_deadline = valid_from`.
- Flat-at-anchor-Standard `entry_enabled_at = valid_from`.
- Laufzeitauflösung `entry_enabled_at=max(valid_from, flat_time)`; bei Flat-Zeit ab Intervallende kein neuer Entry.
- Ein Button vor dem Anker oder strikt vor `T+24h` zielt auf den aktuellen Anker.
- Ein Button exakt ab `T+24h` zielt ausschließlich auf den nächsten Anker; Rückdatierung ist immer `false`.
- Hohe Ankertage werden allgemein auf den letzten gültigen Monatstag geklemmt; Protocol v3 selbst bleibt fest auf Tag 8.
- Der neueste mögliche `process_end_exclusive` kann aus dem letzten vollständigen UTC-Tag rein kalendarisch bestimmt werden.

## Neue Dateien

- `src/ethusdc_bot/protocol_v3/__init__.py`
  - kontrollierte Exporte der bereits abgeschlossenen Protocol-v3-Boundary-Schicht.
- `src/ethusdc_bot/protocol_v3/boundaries.py`
  - unveränderliche Boundary-Dataclasses;
  - Monatsanker und Leap-/Non-Leap-Planung;
  - Prozessende-Auflösung;
  - Late-Button-Auflösung;
  - vollständiger Fail-closed-Validator.
- `tests/unit/test_protocol_v3_boundaries.py`
  - Positiv-, Leap-, Non-Leap-, Late-Button-, UTC-, Duplikat-, Lücken-, Überlappungs-, Aktivierungs- und Determinismustests.

## Aktualisierte Datei

- `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`
  - vollständige Aufgabenfolge 1–33 wiederhergestellt;
  - Aufgabe 1 und Aufgabe 2 `DONE_100`;
  - Aufgabe 3 als einzige nächste Aufgabe `NOT_STARTED`;
  - Fortschritt `2/33 = 6,06 %`.

## Boundary-Beispiele

### Ende 2024-03-08

- Prozessstart: `2023-03-09` wegen Schaltjahr.
- `b0=2023-03-09` synthetisch.
- `b1=2023-04-08` bis `b12=2024-03-08` echte Monatsanker.
- Exakt zwölf Intervalle und 365 OOS-Tage.

### Ende 2025-03-08

- Prozessstart: `2024-03-08`.
- Exakt zwölf Intervalle und 365 OOS-Tage.

### Ende 2026-07-08

- Prozessstart: `2025-07-08`.
- Erste Origin: Training `2023-07-09..2025-07-08(exklusiv)`, OOS `2025-07-08..2025-08-08(exklusiv)`.
- Neue Entry-Gültigkeit ab `2025-07-09 00:00 UTC`.

## Tests und CI

Erster CI-Lauf auf Implementierungsstand `5df0d98cabfde3d990a7b8e6a7047ca89b3980e5`:

- Boundary-Logik korrekt;
- ein Negativtest erwartete eine zu enge Fehlermeldung;
- der Validator blockierte früher und korrekt mit `364 statt 365 OOS-Tage`;
- zusätzlich wurde eine Python-Regex-Escape-Warnung gefunden.

Gezielte Korrektur auf `c65262abdcac15d71c0e7c1b7271950d1ddf1fe5`:

- Test akzeptiert den korrekten frühesten Fail-closed-Blocker;
- Regex als Raw-String geschrieben;
- keine Produktionslogik geändert.

Danach vollständig grün:

- komplette Pytest-Suite;
- alle Protocol-v3-Boundary-Tests;
- Python-Kompilierung;
- PowerShell-Syntax;
- Whitespace-Prüfung;
- finaler Pytest-Status.

Ein Rohdaten- oder Backtestlauf ist für diese reine Kalender-/Boundary-Aufgabe fachlich nicht relevant und wurde bewusst nicht vorgezogen.

## Fail-closed-Abdeckung

Der Validator blockiert mindestens:

- Prozessende nicht am verbindlichen Monatsanker;
- andere Zeitzone oder naive Datetimes;
- andere Protocol-v3-Konstanten als 730/365/12/24/Tag 8;
- fehlende, doppelte, rückwärts laufende oder lückenhafte Grenzen;
- nicht exakt zwölf Origins;
- nicht exakt 365 eindeutige OOS-Tage;
- Training/OOS-Überlappung;
- falsches `as_of_day`, `valid_from`, `valid_until`, Deadline oder Entry-Zeit;
- mehr als ein synthetisches Boundary-Objekt;
- einen realen Monatsanker außerhalb des 8. Tages.

## Explizit nicht umgesetzt

Keine Arbeit aus Aufgabe 3 oder später wurde vorgezogen. Insbesondere nicht umgesetzt:

- Pipelinegeneration oder Pipelinehash;
- Seeds oder Pre-Run-Manifest;
- Suchbudgets und Stopregeln;
- Trial-Ledger;
- Datensnapshot oder Warmup-Download;
- Exchange Info;
- Simulator-, Strategie-, Ranking-, Gate-, Router-, Shadow- oder UI-Änderung;
- Orders, Paper, Testtrade, Live, API-Keys oder Trading-API.

## Safety

Unverändert gesperrt:

- Orders;
- Trading-API;
- API-Keys und Kontodaten;
- Paper;
- Testtrade;
- Live;
- finaler Holdout.

## Codex-Startanweisung für Aufgabe 3

1. Branch `codex/research-resume-and-ui-state-v1` auf den finalen PR-Head ziehen.
2. `git status` muss sauber sein; lokaler `HEAD` muss dem GitHub-PR-Head entsprechen.
3. Dieses Handoff, `docs/41_PROTOCOL_V3_IMPLEMENTATION_SEQUENCE.md`, `docs/42_PROTOCOL_V3_EXECUTABLE_CONTRACT.md` und `src/ethusdc_bot/protocol_v3/boundaries.py` lesen.
4. Die bestehende Identitäts-/Fingerprint-/Budgetlogik im Repository vollständig inventarisieren.
5. Danach ausschließlich Aufgabe 3 umsetzen.
6. Die Boundary-Werte aus Aufgabe 2 nur binden und hashen, nicht neu berechnen oder duplizieren.
7. Keine Trial-Ledger-, Daten-, Simulator-, Router-, Shadow- oder UI-Arbeit vorziehen.

## Exakt nächstes Ticket

`Aufgabe 3 – Pipelinegeneration, Seeds, Budgets und Stopregeln einfrieren`

Ziel ist eine unveränderliche Pipelineidentität, welche Feature-, Familien-, Suchraum-, Ranking-, Gate-, Kosten-, Simulator- und Boundary-Versionen bindet, deterministische Seeds aus einem kanonischen Pre-Run-Manifest erzeugt und die festgelegten 12/8/40/12/3/2- sowie globalen Budgets technisch unüberschreitbar macht.
