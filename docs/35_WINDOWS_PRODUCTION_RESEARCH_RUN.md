# 35 - Windows production research run

Stand: 2026-07-11

## Zweck

`tools/run_production_research.ps1` startet den vollständigen lokalen
Research-Protocol-v2-Lauf auf dem Windows-Rechner. Der Starter verwendet die
lokalen öffentlichen ETHUSDC-Marktdaten, führt vorher alle Tests aus und
kontrolliert den erzeugten Report anschließend erneut auf die verbindlichen
Sicherheitsgrenzen.

Der Starter führt ausschließlich Forschung aus. Er eröffnet keine Orders und
aktiviert weder Paper, Testtrade noch Live.

## Voraussetzungen

- Windows PowerShell 5.1 oder PowerShell 7;
- Python 3.12 über den Windows-Python-Launcher `py`;
- Git im `PATH`;
- sauberer Git-Arbeitsbaum;
- mindestens 1.095 vollständige ETHUSDC-1m-ZIP-/CHECKSUM-Tagespaare unter:

  `C:\TradingBot\data\ETHUSDC_BotV3_Hermes\raw\binance\spot\ETHUSDC\klines\1m`

Die Rohdaten müssen außerhalb des Git-Repositorys liegen.

## Aufruf

Im Repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_production_research.ps1
```

Mit PowerShell 7:

```powershell
pwsh -File .\tools\run_production_research.ps1
```

Begrenzter Kontrolllauf mit zwei Research-Zyklen:

```powershell
pwsh -File .\tools\run_production_research.ps1 -MaxCycles 2
```

Der kanonische vollständige Lauf verwendet maximal acht Zyklen. Ein kleinerer
Wert verändert nicht die Kandidaten-, WFV- oder Finalistenbudgets innerhalb
eines Zyklus.

## Verbindliche Produktionskonfiguration

Der Starter übergibt explizit:

- 40 erzeugte Kandidaten;
- 12 getestete Kandidaten;
- 3 Walk-Forward-Kandidaten;
- 2 Finalisten;
- 6 Walk-Forward-Folds;
- 3 historische Rolling-Origin-Fenster.

Diese Werte werden nicht aus einem alten Report oder aus einem Auditfenster
abgeleitet.

## Vorprüfungen

Der Lauf startet nur, wenn:

- Repository und Python-Projektstruktur vorhanden sind;
- Git und Python 3.12 verfügbar sind;
- der Arbeitsbaum sauber ist;
- Branch und vollständiger Commit-Hash ermittelt werden können;
- die Rohdaten außerhalb des Repositorys liegen;
- mindestens 1.095 ETHUSDC-ZIP- und CHECKSUM-Dateien vorhanden sind;
- jede gefundene ZIP-Datei ein CHECKSUM-Gegenstück besitzt;
- die vollständige Python-Testsuite erfolgreich ist;
- der komplette Source-Tree kompiliert.

Ein Fehler beendet den Starter sofort.

## Holdout- und Sicherheitskontrolle

Nach dem Research-Lauf liest der Starter den erzeugten JSON-Report erneut und
verlangt:

- `execution_profile == production_protocol`;
- `audit_policy.evaluated_in_research_loop == false`;
- `window_plan.final_holdout_window.evaluated == false`;
- Live, Paper und Testtrade bleiben `locked`;
- Orders bleiben `not_created`;
- Binance-Trading-API und API-Keys bleiben `not_used`;
- Shorts, Margin, Futures und Leverage bleiben `forbidden`;
- der Kandidat bleibt während Research nicht adoptierbar.

Bei jeder Abweichung gilt der Lauf als fehlgeschlagen.

## Ausgaben

Der Starter erzeugt:

- den kanonischen Research-JSON-Report;
- den zugehörigen TXT-Report;
- ein vollständiges Konsolenprotokoll;
- ein zusätzliches Manifest mit Branch, Commit, Start-/Endzeit, Datenpfad,
  Zykluszahl, Reportpfad und Sicherheitsstatus.

Damit kann Codex später exakt nachvollziehen, welcher Code- und Datenstand den
Lauf erzeugt hat.

## Bewertung des Ergebnisses

Der Lauf bewertet ausschließlich Training, interne Validation, Walk-Forward,
Rolling-Origin und die vollständigen Selection-Quality-Gates.

Er beweist nicht automatisch den finalen Zielwert von 3 USDC pro Kalendertag,
weil der neue versiegelte Holdout nicht geöffnet wird. Ein Kandidat darf nur
dann als methodisch geeignet eingefroren werden, wenn seine Selection-Evidenz
vollständig ist und alle Gates besteht. Der endgültige unabhängige Nachweis ist
ein späterer, einmaliger Schritt mit einem bis dahin unangetasteten Holdout.

## Verbotene Abkürzungen

Nicht zulässig sind:

- Tests überspringen;
- unsauberen Arbeitsbaum akzeptieren;
- `--fixture-smoke` für einen Produktionsnachweis verwenden;
- Kandidatenbudgets erhöhen, ohne das Ressourcenbudget anzupassen;
- den konsumierten Auditzeitraum erneut zur Auswahl oder Optimierung nutzen;
- nachträglich Kosten oder Gates lockern, um ein gewünschtes Ergebnis zu
  erzeugen;
- Live-, Paper-, Testtrade- oder Orderpfade aktivieren.
