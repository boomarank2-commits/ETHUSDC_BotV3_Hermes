# Current Status – GPT 1 / Protocol v3

Stand: 2026-07-20

## Verbindlicher Gesamtstand

`29/33 = 87,88 % DONE_100`.

Abgeschlossene Aufgaben: `1 bis 29`.

Nächste Aufgabe: `30 – UI und Bedienzustände vollständig anschließen` – `NOT_STARTED`.

Aufgaben 31 bis 33 bleiben strikt `NOT_STARTED`.

## Repository-Wahrheit

- Repository: `boomarank2-commits/ETHUSDC_BotV3_Hermes`;
- Branch: `codex/research-resume-and-ui-state-v1`;
- Draft-PR: `#17`;
- Task-29-technischer Head: `96d069054a452f55ebccb29f964fe27ca5c5fe0b`;
- grüner technischer GitHub-CI-Lauf: `29736897831`;
- vollständige Suite: `1.233 Tests erfolgreich`;
- Python-Compile, PowerShell-Syntax und Whitespace: erfolgreich;
- grüner Task-29-Dokumentations-CI-Lauf: `29737703423` auf Head `3c276345f39068e29b35b9f90669fe7aa50483c0`.

## Aufgabe 29 – DONE_100

Abschlussbericht:
`handoff/PROTOCOL_V3_TASK_29_2026-07-20.md`

Umgesetzt:

- separater, manuell gestarteter und strikt orderfreier `research_challenger_shadow`;
- ausschließlich vollständig validierte Task-28-Ausgabe als Startprovenienz;
- eigener versionierter Vertrag, Reporttyp, erlaubter Storage-Root, Controller und hashverkettetes Forward-Ledger;
- Wiederverwendung der bestehenden Drei-Markt-Kontext-, Task-8-Intrabar-, Execution-, Kosten-, Report-, Artefakt- und Task-13-Resume-Pfade;
- ETHUSDC als einziges virtuelles Handelssymbol, BTCUSDC/ETHBTC ausschließlich als exakt geschlossener Kontext;
- Warmup ohne Signale/Fills/PnL/Ledger, manuelle Aktivierungsminute ohne rückwirkenden Forward-Backfill;
- virtuelle Signale, Fills, Gebühren, Slippage, Positionen, Pending Entries, MTM, Tageswerte und Closing Equity bei dauerhaft `orders_created=0`;
- content-addressed Trades-, Daily-MTM-, Equity-/Underwater- und Diagnoseartefakte;
- kompakte Task-13-Checkpoint-Receipts und bitgleicher öffentlicher Präfix-Replay statt gespeicherter Rohkerzen;
- neue Pipelinegeneration und leeres Ledger bei Familien-, Feature-, Controller-, Execution- oder Pipelinewechsel;
- Task-13-Vertrag v4 erlaubt ausschließlich echte validierte Produktionskandidaten aus Task 16→17→18; synthetische Fixtures bleiben blockiert;
- vollständige Paritäts-, Idempotenz-, Provenienz-, Watermark-, Gültigkeits-, Hash-, Ledger-, Checkpoint-, Resume- und Safety-Negativtests.

## Aufgabe 30 – NOT_STARTED

Verbindlicher Umfang:

- bestehendes Dashboard und vorhandene Controller als einzige UI-/Runtime-Wahrheit erweitern;
- Origins, Folds, Aufgabenfortschritt, Safety, Ergebnisbedeutung und manuellen Research-Challenger-Start korrekt anzeigen;
- Buttons ausschließlich aus kanonischen Readiness-/Report-/Checkpointzuständen aktivieren;
- keine vorzeitige Outer-PnL oder erfundene Fortschritts-/Ergebnisanzeige;
- Refresh, Neustart und wiederholte Anzeige dürfen keine Research-, Signal-, Fill- oder Ledgerzustände verändern;
- Paper, Testtrade, Live, Orders, private Endpunkte, API-Keys und kanonische Adoption bleiben gesperrt.

Aufgabe 30 darf erst nach vollständig grünem Task-29-Dokumentations-CI begonnen werden.

## Sicherheitsstatus

- kein Backtest-, Paper-, Testtrade-, Live- oder Order-Start;
- keine API-Keys oder privaten Endpunkte;
- keine Secrets committed;
- keine Quality-Gates gelockert;
- keine Fake-Trades, Fake-Fills oder Fake-Reports;
- kein kanonischer Adoption- oder Finalpfad geöffnet;
- kein Protocol-v3-Finalstatus ohne wirklich neuen `sealed_final_holdout`;
- der Bot darf nicht gestartet werden.

## Nächster Einstieg

Die sieben Pflichtdateien erneut vollständig lesen und ausschließlich Aufgabe 30 beginnen.
