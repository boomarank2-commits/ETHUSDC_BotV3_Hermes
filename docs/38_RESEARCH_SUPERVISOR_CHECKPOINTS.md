# 38 – Research-Supervisor und dauerhafte Fortschritts-Checkpoints

Stand: 2026-07-11

## Zweck

Lange lokale Research-Protocol-v2-Läufe dauern auf vollständigen ETHUSDC-1m-Daten deutlich länger als eine einzelne Codex-Sitzung. Der Supervisor trennt deshalb Bedienungslimit und Rechenprozess von der Ergebniswahrheit:

- der bestehende `research_loop_runner` bleibt unverändert die einzige Research-Engine;
- der Supervisor startet ihn als Child-Prozess;
- jede Konsolenzeile wird unverändert weitergereicht;
- nach jeder kanonischen abgeschlossenen Zykluszeile wird ein atomarer JSON-Checkpoint geschrieben;
- der finale Runner-JSON-Report bleibt die einzige Performance- und Quality-Gate-Wahrheit.

## Nachgewiesener Ausgangsfehler

Der erste reale Windows-Produktionsstart bestand die Tests und die Kompilierung, scheiterte danach aber vor Zyklus 1 mit:

```text
ModuleNotFoundError: No module named 'ethusdc_bot'
```

Ursache war das lokale `src`-Layout: Der Starter rief `py -m ...` auf, ohne `src` selbst in `PYTHONPATH` zu binden. Ein manuell gesetztes prozesslokales `PYTHONPATH` bestätigte die Diagnose und ließ den Lauf starten.

Der Starter setzt jetzt selbst deterministisch:

```text
PYTHONPATH=<Repository>\src[;<vorheriger PYTHONPATH>]
```

Vor dem langen Lauf importiert er sowohl Runner als auch Supervisor explizit.

## Checkpoint-Inhalt

`research_supervisor.py` schreibt unter dem gewählten Reportordner Dateien nach dem Muster:

```text
production_research_supervisor_<UTC>.checkpoint.json
```

Enthalten sind:

- gebundener Git-Commit und Branch;
- Start- und Aktualisierungszeit;
- Status `starting`, `running`, `completed`, `failed` oder `interrupted`;
- aktive Zyklusnummer;
- alle bereits vom Runner bestätigten abgeschlossenen Zykluszeilen;
- erzeugte, getestete, Walk-Forward- und Finalistenanzahl;
- unveränderter Text des Selection-Ranks;
- Child-Exit-Code;
- finaler Reportpfad, sobald der Runner ihn ausgibt;
- explizite Sicherheitsdeklaration.

## Wichtige Grenze

Der Checkpoint ist **kein Resume-Token**. Er enthält keine unbestätigten In-Memory-Kandidaten und darf nicht als Ergebnisreport verwendet werden.

Bei einem Abbruch gilt:

1. Checkpoint lesen und abgeschlossene Zyklen dokumentieren.
2. Lauf auf demselben Git-Commit reproduzierbar neu starten.
3. Neue abgeschlossene Zyklen gegen den Checkpoint vergleichen.
4. Nur den finalen kanonischen Runner-JSON-Report für Leistungsentscheidungen verwenden.

## Sicherheitsvertrag

Der Supervisor:

- lädt selbst keine Marktdaten;
- bewertet keine Strategie;
- verändert keine Parameter;
- öffnet weder Audit noch finalen Holdout;
- besitzt keine Netzwerk-, Account-, Key- oder Orderfunktion;
- aktiviert weder Live, Paper noch Testtrade.

## Prüfung

GitHub Actions auf Python 3.12:

- 821 Tests bestanden;
- Python-Kompilierung bestanden;
- PowerShell-Syntaxprüfung bestanden;
- gestapelte Whitespace-Prüfung gegen PR #10 bestanden.

Gezielte Tests prüfen:

- kanonische Zykluszeilen;
- unmögliche Zyklusindizes;
- atomare Dateiersetzung;
- Sicherheitsfelder;
- zwei vollständig gespeicherte Zyklen und finalen Reportpfad;
- Erhalt von Zyklus 1, wenn der Child-Prozess in Zyklus 2 fehlschlägt.
