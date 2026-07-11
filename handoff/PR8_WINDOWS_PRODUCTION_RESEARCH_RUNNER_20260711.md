# PR #8 - Windows production research launcher

Stand: 2026-07-11

## Branch

- Branch: `review/windows-production-research-runner-v1`
- Base: `review/search-frontier-v2`
- Pull request: #8
- Last fully tested branch commit before this handoff update: `982a8ced6d81242537b0b6cba96db86816813414`

## Zweck

Der neue Starter `tools/run_production_research.ps1` führt den korrigierten
Research-Protocol-v2-Stack reproduzierbar auf dem lokalen Windows-Rechner aus.
GitHub selbst besitzt keinen Zugriff auf die lokalen 1m-Marktdaten. Der Starter
schließt diese Lücke, ohne einen Trading- oder Holdout-Pfad zu öffnen.

## Verbindliche Ausführung

Vor dem Research-Lauf verlangt das Skript:

- sauberen Git-Arbeitsbaum;
- vollständigen 40-stelligen Commit-Hash und Branchnamen;
- Python 3.12 und Git;
- externen ETHUSDC-Rohdatenpfad;
- mindestens 1.095 ZIP- und CHECKSUM-Dateien;
- keine ungepaarte ZIP-Datei;
- vollständige Python-Testsuite;
- erfolgreiche Python-Kompilierung.

Der Research-Aufruf verwendet explizit:

- 40 erzeugte Kandidaten;
- 12 getestete Kandidaten;
- 3 Walk-Forward-Kandidaten;
- 2 Finalisten;
- 6 Walk-Forward-Folds;
- 3 historische Origins;
- maximal 8 Zyklen.

## Nachträgliche Reportvalidierung

Der Launcher akzeptiert den erzeugten Report nur, wenn:

- `execution_profile=production_protocol`;
- Research kein Auditfenster ausgewertet hat;
- der finale Holdout geschlossen blieb;
- Live, Paper und Testtrade `locked` sind;
- Orders `not_created` bleiben;
- Binance-Trading-API und API-Keys `not_used` bleiben;
- Shorts, Margin, Futures und Leverage `forbidden` bleiben;
- der Research-Kandidat nicht adoptierbar ist.

Diese Werte entsprechen exakt `research_protocol.safety_status()`.

## Ausgaben

Neben JSON- und TXT-Research-Report entstehen:

- vollständiges Konsolenprotokoll;
- Manifest mit Branch, Commit, Start-/Endzeit, Datenpfad, Reports, Zykluszahl und
  Sicherheitsstatus.

Damit kann Codex einen späteren lokalen Lauf exakt einem Codezustand zuordnen.

## Prüfungen im Repository

GitHub Actions auf Ubuntu 24.04 mit Python 3.12 und PowerShell:

- 783 Tests bestanden;
- Python-Source-Kompilierung bestanden;
- PowerShell-Parserprüfung bestanden;
- gestapelte Whitespace-Prüfung bestanden.

Zusätzlich sichern statische Tests ab:

- kanonische 40/12/3/2/6/3-Argumente;
- sauberer Git-Arbeitsbaum und Commitbindung;
- externe 1.095-Tage-Datenbasis;
- vollständige Sicherheitsfelder;
- kein Netzwerk- oder Orderbefehl im Launcher;
- Windows-PowerShell-5.1-kompatibles JSON-Lesen.

## Wichtige Grenze

Der Launcher macht keinen Gewinnnachweis. Er führt den vollständigen
Selection-Research-Lauf aus. Der neue versiegelte Holdout bleibt geschlossen.
Der Zielwert von 3 USDC pro Kalendertag darf erst nach echter Evidenz berichtet
werden und wird durch dieses Skript weder behauptet noch erzwungen.

## Sicherheit

Keine Funktion in diesem PR aktiviert Live, Paper, Testtrade, Orders,
Kontozugriff, private Endpunkte, API-Keys, Shorts, Margin, Futures oder Leverage.
