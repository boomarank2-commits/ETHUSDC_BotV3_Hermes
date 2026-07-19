# Protocol v3 – Re-Audit und Korrekturen Aufgaben 11 bis 14

Stand: 2026-07-19

## Status

Die Aufgaben 11 bis 14 wurden am tatsächlichen Produktionscode des Ausgangs-Heads

`44edb2129471132bace8acf8da9a10a59f248a02`

neu adversarial geprüft. Die Prüfung beschränkte sich nicht auf Handoff-Texte oder bereits vorhandene Positivtests. Für jeden Verdacht wurde zuerst ein reproduzierender Negativtest gegen den unveränderten Code ausgeführt. Nur reproduzierbare Abweichungen wurden korrigiert.

Die fachliche Reihenfolge bleibt unverändert:

```text
Aufgabe 15 = DONE_100, aber vor Aufgabe 16 erneut adversarial zu prüfen
Aufgabe 16 = NOT_STARTED
```

Paper, Testtrade, Live, Orders, private Endpunkte, Trading-API und API-Keys bleiben gesperrt.

## Aufgabe 11 – Report- und Registrierungsleser

### Gefundener Fehler

`read_protocol_v3_report(...)` und `read_forward_window_registration(...)` öffneten den vom Aufrufer übergebenen Pfad, bevor geprüft wurde, ob er innerhalb des jeweils festen Protocol-v3-Roots lag und keine Symlink-Komponente enthielt.

Ein fremder oder symlinkierter JSON-Pfad wurde danach zwar abgelehnt, seine Bytes konnten aber vorher bereits gelesen beziehungsweise geparst werden. Damit war die dokumentierte Root-/Symlink-Sperre in der falschen Reihenfolge implementiert.

### Korrektur

Vor dem ersten Bytezugriff wird jetzt:

1. ein echtes, nicht symlinkiertes Repository-Root verlangt;
2. der Pfad lexikalisch einem erlaubten festen Report- oder Registrierungsroot zugeordnet;
3. jede existierende Pfadkomponente auf Symlinks geprüft;
4. der Pfad strikt aufgelöst;
5. die aufgelöste Lage erneut gegen den ausgewählten festen Root geprüft.

Erst danach wird JSON gelesen und anschließend weiterhin die genaue kanonische Datei aus `artifact_kind`, `report_id` beziehungsweise `registration_id` verlangt.

Neue Regressionstests beweisen, dass ungültiges JSON außerhalb des Roots und ein symlinkierter Registrierungspfad vor dem JSON-Open blockieren.

## Aufgabe 12 – Kompakter Artefaktstore

### Gefundener Fehler

Die frühere Task-12-Korrektur schützte den stabilen öffentlichen Facade-Leser. Das Kernmodul `artifact_store.py` las einen Indexpfad bei direktem Import aber weiterhin vor seiner Root-Prüfung. Das Verhalten hing damit von der Importreihenfolge und davon ab, ob zuvor `artifact_store_api.py` die Kernfunktion monkey-gepatcht hatte.

### Korrektur

Die Vorabprüfung liegt jetzt zusätzlich im Kernmodul selbst. Ein frischer Prozess, der ausschließlich `artifact_store` direkt importiert, blockiert fremde und symlinkierte Indexpfade vor dem ersten JSON-Zugriff.

Die öffentliche Facade bleibt kompatibel und darf weiterhin denselben Kern aufrufen. Es wurde keine zweite Store-Architektur gebaut.

## Aufgabe 13 – Stale-Lock-Recovery und Temp-Pfade

### Gefundener Fehler 1: Recovery-Rennen

Wenn ein immutable Recovery-Receipt bereits existierte, löschte ein wiederholter Recovery-Aufruf den aktuell vorhandenen Lockpfad blind. In folgendem Rennen konnte dadurch ein gültiges neues Writer-Lock gelöscht werden:

1. altes Lock wird erfolgreich in das Recovery-Root verschoben;
2. ein neuer Writer erwirbt denselben aktiven Lockpfad;
3. ein verspäteter Retry besitzt noch die alte Lockbeobachtung;
4. der vorhandene Code findet das alte Receipt und löscht den nun neuen Lockpfad.

### Korrektur 1

Ein vorhandenes Recovery-Receipt erlaubt kein `unlink()` des aktiven Pfads mehr. Ist der aktive Pfad inzwischen wieder vorhanden, wird sein vollständiger Lock-Inhalt gelesen:

- anderer Lock: Recovery blockiert als Race;
- angeblich derselbe alte Lock noch aktiv: Recovery blockiert fail-closed;
- kein aktiver Pfad: idempotenter Erfolg.

### Gefundener Fehler 2: Checkpoint-Temp-Symlink

Beim Checkpoint-Publish wurde ein vorhandener Temp-Pfad per `read_bytes()` geprüft, bevor feststand, dass er eine echte reguläre Datei und kein Symlink war. Ein verwaister Temp-Symlink konnte deshalb vor der Ablehnung gelesen und anschließend geheilt werden.

### Korrektur 2

Checkpoint-, Cache- und atomare Replace-Temp-Pfade werden jetzt vor jedem Lesen oder Löschen auf Symlink und regulären Dateityp geprüft. Unsichere Temp-Pfade blockieren.

Neue Regressionstests reproduzieren sowohl das Recovery-Rennen als auch den Temp-Symlink-Angriff.

## Aufgabe 14 – Untere Fit-Grenze beim Purging

### Gefundener Fehler

Der öffentliche Helfer `purge_fold_training_events(...)` entfernte Ereignisse ab `fit_end`, behielt aber Ereignisse mit einer Signalzeit vor `fit_start` im Fitbestand.

Das widersprach der bereits anderweitig implementierten halboffenen Fit-Grenze `[fit_start, fit_end)` und der Regel, dass Warmup vor Trainingsbeginn feature-only bleibt. Die frühere Annahme, jeder Aufrufer müsse diese Ereignisse bereits vorfiltern, war für einen öffentlichen fail-closed Boundary-Helfer nicht ausreichend und nicht durch dessen Schnittstelle erzwungen.

### Korrektur

Ein Ereignis bleibt nur noch erhalten, wenn seine Signalzeit innerhalb

`fit_start <= signal_time < fit_end`

liegt und sein Informationsende die Validation-Grenze nicht berührt. Ereignisse vor `fit_start` werden als gepurgt dokumentiert. Die abschließende Postcondition prüft nun beide Fit-Grenzen.

Ein Regressionstest beweist, dass ein Warmup-Label vor `fit_start` nicht als Trainingsevidenz erhalten bleibt, während das erste Ereignis exakt an `fit_start` zulässig bleibt.

## Veränderte Dateien

Produktionscode:

- `src/ethusdc_bot/protocol_v3/reporting.py`;
- `src/ethusdc_bot/protocol_v3/artifact_store.py`;
- `src/ethusdc_bot/protocol_v3/transactional_cache_store.py`;
- `src/ethusdc_bot/protocol_v3/inner_folds.py`.

Regressionstests:

- `tests/unit/test_protocol_v3_reporting.py`;
- `tests/unit/test_protocol_v3_artifact_store_path_guard.py`;
- `tests/unit/test_protocol_v3_transactional_cache.py`;
- `tests/unit/test_protocol_v3_inner_folds.py`.

## Lokale Validierung des kombinierten Stands

```text
gezielte Aufgaben-11-bis-14-Suite: 50 Tests erfolgreich
vollständige Suite: 1.117 Tests erfolgreich
python -m compileall -q src: erfolgreich
```

Die verbindliche GitHub-Review-CI ist nach Veröffentlichung dieses Korrekturstands erneut auszuführen. Erst ein grüner finaler Branch-Head bestätigt den Abschluss.

## Nicht verändert

- keine Strategie- oder Kandidatenparameter;
- keine Ranking- oder Quality-Gate-Schwelle;
- keine PnL- oder Performance-Aussage;
- keine Daten-, Fold- oder Prozessfenster;
- keine Candidate-Matrix, PBO, DSR, Feature-Store-, Router- oder Outer-Origin-Logik;
- keine Paper-, Testtrade-, Live- oder Orderfunktion.

## Nächster Pflichtschritt

Vor Aufgabe 16 muss Aufgabe 15 am korrigierten aktuellen Code adversarial geprüft werden. Insbesondere ist zu kontrollieren, dass der versionierte Transaktionsvertrag v3 nicht von Importreihenfolge oder einem erst später ausgeführten Facade-Monkey-Patch abhängt.
