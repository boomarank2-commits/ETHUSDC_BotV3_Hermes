# PR #8 - Windows production research launcher

Stand: 2026-07-11

## Branch

- Branch: `review/windows-production-research-runner-v1`
- Base: `review/search-frontier-v2`
- Pull request: to be created after this handoff commit

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
- keine Order erzeugt wurde;
- Binance-Trading-API und API-Keys nicht verwendet wurden;
- Shorts, Margin, Futures und Leverage verboten bleiben;
- der Research-Kandidat nicht adoptierbar ist.

Diese Werte entsprechen exakt `research_protocol.safety_status()`.

## Ausgaben

Neben JSON- und TXT-Research-Report entstehen:

- vollständiges Konsolenprotokoll;
- Manifest mit Branch, Commit, Start-/Endzeit, Datenpfad, Reports, Zykluszahl und
  Sicherheitsstatus.

Damit kann Codex einen späteren lokalen Lauf exakt einem Codezustand zuordnen.

## Prüfungen im Repository

- statische Unit-Tests für alle kanonischen Argumente und Sicherheitsprüfungen;
- Verbot von Netzwerk- und Orderbefehlen im Launcher;
- PowerShell-Parserprüfung in GitHub Actions;
- Python 3.12, vollständige Testsuite, `compileall` und Whitespace-Prüfung.

## Wichtige Grenze

Der Launcher macht keinen Gewinnnachweis. Er führt den vollständigen
Selection-Research-Lauf aus. Der neue versiegelte Holdout bleibt geschlossen.
Der Zielwert von 3 USDC pro Kalendertag darf erst nach echter Evidenz berichtet
werden und wird durch dieses Skript weder behauptet noch erzwungen.

## Sicherheit

Keine Funktion in diesem PR aktiviert Live, Paper, Testtrade, Orders,
Kontozugriff, private Endpunkte, API-Keys, Shorts, Margin, Futures oder Leverage.
