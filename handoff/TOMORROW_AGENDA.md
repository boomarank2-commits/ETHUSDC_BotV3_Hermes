# Agenda für morgen

## 1. Research-Lauf reboot-sicher machen

Aktueller Befund: Der Supervisor schreibt zwar einen atomaren Checkpoint, aber
`resume_supported` steht derzeit auf `false`. Nach einem Windows-Neustart kann
ein Lauf deshalb nicht an der letzten abgeschlossenen Zyklusgrenze fortgesetzt
werden. Ein liegengebliebener `status=running`-Checkpoint kann außerdem von der
UI als aktiver Lauf erkannt werden, obwohl kein Prozess mehr existiert.

Morgen zuerst die Änderungen von GitHub einholen und anschließend eine kleine,
belegte Lösung bauen:

- pro abgeschlossenem Zyklus einen kleinen, atomaren Resume-State sichern;
- Runner und Supervisor so erweitern, dass derselbe Lauf ab dem letzten
  konsistenten Zyklus fortgesetzt werden kann;
- vor dem Fortsetzen Branch, Commit, Konfiguration, Daten-Cutoff und
  Sicherheitsflags vergleichen;
- bei inkonsistentem oder unvollständigem State fail-closed abbrechen;
- stale Checkpoints nach einem Reboot über echte Prozess-/Run-Zuordnung erkennen;
- niemals zwei Supervisoren für dieselbe Run-ID starten;
- keine Reportdateien löschen oder überschreiben.

Ein Neustart darf keine bereits abgeschlossenen Zyklen verlieren und darf keine
zweite Research-Engine erzeugen. Die vollständige Zwischen-/Resume-Speicherung
wird erst morgen implementiert, nicht während des aktuellen Laufs.

## 2. UI-Anzeige in drei klaren Zuständen prüfen

### Datenlauf / Download

Die UI soll während Datenprüfung und Download nur den Datenlauf zeigen:
Gesamtfortschritt, aktueller Task/Markt/Zeitraum, Dateien und Bytes,
Startzeit, letzte Aktualisierung, Geschwindigkeit/ETA sofern belastbar,
Tests/Validierungen, übersprungene und fehlgeschlagene Aufgaben sowie den
konkreten Blocker. Backtest- und Trading-Elemente bleiben in diesem Zustand
ausgeblendet.

### Laufender Backtest / Research

Die UI soll den Research-Lauf von 0–100 % nachvollziehbar anzeigen:
Run-ID, Branch/Commit, Phase, Zyklus `n/8`, Gesamt- und Zyklusfortschritt,
Startzeit, Laufzeit, letzte Checkpoint-Zeit, geschätzte Restzeit nur bei
verlässlicher Grundlage, 40/12/3/2-Stufenzähler, Kontext 6/2, WFV-Folds,
Rolling-Origin-Limit, letzte und beste Auswahl, Validation/WFV-Kennzahlen,
Tradezahl, Profit Factor, Netto/Tag, Drawdown, Gebühren, Slippage,
No-Trade-Gap, Quality-Gate-Status, Audit/Holdout-Status und alle
Sicherheitssperren. Große JSON-Reports dürfen den Refresh nicht blockieren;
die UI liest nur Checkpoint, begrenzten Log-Tail und kleine Extracts.

### Beendeter Backtest

Nach Abschluss sollen Run-ID, Abschlusszeit, Stop-Grund, Zyklen ausgeführt,
beste Validation, beste WFV-Auswahl, Walk-Forward/Rolling-Origin,
Profit Factor, Trades, Netto gesamt/Tag, Drawdown, Gebühren, Slippage,
No-Trade-Gap, aktive Monate, positive/schlechtester Fold, getestete
Familien/Profile, Abstand zu `+3 USDC/Tag`, Quality-Gate sowie die Report-,
Checkpoint-, Manifest- und Logpfade sichtbar sein. Audit, finaler Holdout,
Live, Paper, Testtrade, Orders und API bleiben ausdrücklich gesperrt.

## Reihenfolge

1. GitHub-Stand von GPT/Codex einholen und Konflikte prüfen.
2. Resume-/Stale-Checkpoint-Tests schreiben.
3. Minimal implementieren und fokussiert testen.
4. UI-Zustandsanzeigen und Regressionstests vervollständigen.
5. Committen, pushen, Draft-PR aktualisieren.
6. Erst danach den nächsten kanonischen UI-Backtest starten.
