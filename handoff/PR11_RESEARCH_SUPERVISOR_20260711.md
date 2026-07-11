# PR #11 – Research-Supervisor und Checkpoints

Stand: 2026-07-11

## Branch und Basis

- Branch: `review/research-checkpoints-context-v1`
- Base: `review/context-veto-engine-v1`
- Pull Request: `#11`
- Status: offen, Draft, nicht gemergt

## Anlass

Ein realer lokaler Produktionslauf auf 1.095 ETHUSDC-Tagen zeigte zwei betriebliche Schwachstellen:

1. Der erste Runnerstart scheiterte nach erfolgreicher Testsuite mit `ModuleNotFoundError`, weil das `src`-Layout nicht selbst in `PYTHONPATH` gebunden war.
2. Der mehrstündige Lauf schrieb den vollständigen JSON-Report erst am Ende. Bei einem Bedienungs- oder Tokenlimit blieb nur das Konsolenlog als Zwischenstand.

## Umsetzung

### Windows-Starter

`tools/run_production_research.ps1`:

- löst den Repository- und Source-Pfad explizit auf;
- setzt `PYTHONPATH` prozesslokal und bewahrt einen vorhandenen Wert;
- importiert Runner und Supervisor vor dem langen Lauf;
- startet nun `ethusdc_bot.backtest.research_supervisor`;
- behält alle bisherigen Daten-, Git-, Test-, Audit-, Holdout- und Safety-Prüfungen bei;
- dokumentiert Source-Pfad und effektiven `PYTHONPATH` im Manifest.

### Supervisor

`src/ethusdc_bot/backtest/research_supervisor.py`:

- startet den unveränderten kanonischen Runner als Child-Prozess;
- spiegelt stdout unverändert;
- erkennt nur die bereits vorhandenen kanonischen `cycle ... generated=...`-Zeilen;
- schreibt nach jedem abgeschlossenen Zyklus atomar einen JSON-Checkpoint;
- schreibt bei normalem Ende, Child-Fehler oder Unterbrechung einen finalen Supervisorstatus;
- erklärt ausdrücklich `resume_supported=false`;
- erklärt den kanonischen Runner-JSON als alleinige Ergebniswahrheit.

## Nicht umgesetzt

- keine automatische Wiederaufnahme mitten in einem Zyklus;
- keine Änderung der Research-Rankings;
- keine neue Strategie;
- keine Veränderung von Gebühren oder Slippage;
- keine Öffnung von Audit oder finalem Holdout;
- kein Live-, Paper-, Testtrade-, Order-, Account- oder Key-Pfad.

## Tests

GitHub Actions, Python 3.12:

- 821 Tests bestanden;
- `compileall` bestanden;
- PowerShell-Parser bestanden;
- `git diff --check` gegen PR #10 bestanden.

Neue Tests decken ab:

- Selbstbindung des `src`-Layouts;
- Importcheck vor dem Research;
- Supervisor als tatsächlichen Starter;
- kanonische Zyklusparser;
- atomare Checkpoints;
- vollständigen Zwei-Zyklen-Ablauf;
- Child-Fehler nach einem abgeschlossenen Zyklus;
- unveränderte Audit-, Holdout- und Trading-Sperren.

## Parallel gesicherter Codex-Stand

Codex hat vor dem lokalen Research-Lauf zwei Rescue-Commits gepusht:

- `49d746931300da75478c33028b1addf865dc1d55` – bounded Shadow runtime follow-up;
- `af4c6d17af3056609a1d74fe55afe4a6e4b5b82a` – rolling and temporal evidence producers.

Diese Commits sind nicht automatisch in PR #11 übernommen. Sie müssen später separat gegen den gestapelten Review-Stand geprüft werden.

## Bekannter lokaler Research-Stand beim Codex-Limit

Der laufende lokale Prozess verwendete noch Commit:

```text
97167626ead4925d70fb4a880a5b3bcbbf3e10b6
```

Dokumentiert waren:

- 1.095 ZIP-/CHECKSUM-Paare;
- 814 lokale Tests grün;
- Zyklen 1 bis 5 abgeschlossen;
- Zyklus 6 aktiv;
- je Zyklus 40/12/3/2;
- bisher negative Leistungsanteile in den ausgegebenen Rank-Vektoren;
- noch kein 3-USDC/Tag-Nachweis;
- Audit und finaler Holdout ungeöffnet.

Der Python-Prozess kann nach Ende der Codex-Bedienung weitergelaufen sein. Vor einem Neustart muss sein Status sowie das neueste Konsolenlog geprüft werden.

## Nächster Schritt

1. Lokalen Prozessstatus und vorhandene finale Reports prüfen.
2. Falls der alte Lauf fertig ist, unveränderten Report vollständig auswerten.
3. Falls er noch läuft, nicht parallel neu starten.
4. Falls er abgebrochen ist, Ursache und letzte abgeschlossene Zykluszeile sichern.
5. PR #11 lokal prüfen.
6. Danach echten BTCUSDC-/ETHBTC-Kontext nur in einem getrennten Research-PR aktivieren.
