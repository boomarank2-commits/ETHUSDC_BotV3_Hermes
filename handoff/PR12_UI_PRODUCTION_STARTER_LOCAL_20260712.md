# PR #12 - lokaler UI-Produktionsstarter

Stand: 2026-07-12

## Basis

- Arbeitsbranch: `codex/pr12-final-local-run`
- PR-#12-Basiscommit: `0cec0830a64874d1afd1f385b01a7fe0adcb941a`
- Basisprüfung: `832` Tests bestanden, `compileall` und `git diff --check`
  bestanden.

Die Rescue-Commits `49d7469...` und `af4c6d1...` wurden nicht übernommen.
Der erste betrifft den für diesen Backtest nicht benötigten Shadow-Runtime-Pfad.
Der zweite enthält einen alternativen, nicht in die Produktion verdrahteten
Evidence-Baustein; PR #12 besitzt bereits die neuere integrierte
Selection-/WFV-Evidenz. Ein Cherry-Pick würde den gestapelten PR-#12-Stand
überschreiben oder parallelisieren.

## Minimal korrigierter Pfad

Der UI-Button rief zuvor `run_research_loop` direkt mit ausgeschaltetem Kontext
auf. Er startet jetzt ausschließlich:

```text
UI
-> tools/run_production_research.ps1
-> ethusdc_bot.backtest.research_supervisor
-> ethusdc_bot.backtest.research_loop_runner
-> Search Frontier v2 und vollständige PR-#12-Kontext-Evidenz
```

Der Controller setzt `enable_context=true`, verwendet 40/12/3/2, sechs
Walk-Forward-Folds, das Rolling-Origin-Limit drei und startet den vorhandenen
Windows-Produktionsstarter. Es wurde keine zweite Engine gebaut.

## Reproduzierbares Datenfenster

Im Datenordner liegt für ETHBTC bereits ein zusätzlicher Tag 2026-07-08, für
ETHUSDC und BTCUSDC noch nicht. Löschen, Verschieben, Fill oder Interpolation
wären unzulässig. Der Produktionslauf bindet deshalb ausdrücklich den letzten
gemeinsamen sicheren Tag `2026-07-07`.

Für das Fenster `2023-07-09` bis `2026-07-07` wurden verifiziert:

- je Symbol `1.095` ZIP-/CHECKSUM-Paare;
- keine ungepaarten Dateien;
- `1.576.800` Kerzen je Symbol;
- exakt identische UTC-Minutenzeitachsen;
- keine gelöschten oder veränderten Marktdaten.

## Laufzeitnachweis und Abschluss

Nach jedem kontextaktiven Zyklus gibt der Runner eine fail-closed Proof-Zeile
aus. Sie bestätigt die tatsächlichen 40/12/3/2 Stufen, sechs erzeugte und zwei
getestete Kontextkandidaten, sechs WFV-Folds, Rolling-Origin-Limit drei sowie
`audit_evaluated=false` und `final_holdout_evaluated=false`.

Der Windows-Starter vergleicht für jeden abgeschlossenen Zyklus Stage- und
Proof-Zeile. Der mehrgigabytegroße Detailreport wird nach dem Lauf nicht mehr
vollständig in Windows PowerShell deserialisiert. Das kleine kanonische
TXT-Ergebnis liefert die Manifestwerte; der vollständige JSON-Report bleibt die
Performancewahrheit. Damit wird der beim PR-#10-Lauf nachgewiesene
`ConvertFrom-Json`-Speicherfehler vermieden.

Live, Paper, Testtrade, Orders, Trading-API und API-Keys bleiben gesperrt oder
ungenutzt. Audit und finaler Holdout werden durch diesen Button nicht
ausgewertet.

## Nächster Schritt

Der fertige Stand wurde mit `835` Tests, Python-3.12-Kompilierung,
PowerShell-Parser und `git diff --check` geprüft. Die echte Dashboard-UI öffnete
mit einem reagierenden Fenster; während der reinen UI-Prüfung liefen null
Research-/Supervisor-Prozesse. Der Button war aktiviert und meldete die Aktion
`pr12_production_starter_supervised_context_protocol_v2`; Trading-API und
Final-Holdout blieben aus.

Nächster Schritt: diesen Stand committen und auf GitHub pushen. Danach die UI
erneut vom sauberen Commit öffnen, den Backtest-Button einmal auslösen und nach
Zyklus 1 Stage-/Proof-Zeile sowie den Supervisor-Checkpoint prüfen.
