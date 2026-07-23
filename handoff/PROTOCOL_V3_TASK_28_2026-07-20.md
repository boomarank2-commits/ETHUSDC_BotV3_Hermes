# Protocol v3 – Aufgabe 28 DONE_100

Stand: 2026-07-20

## Verbindlicher Abschlussstand

`28/33 = 84,85 % DONE_100`.

Aufgabe 28 ist vollständig umgesetzt, getestet, auf Branch `codex/research-resume-and-ui-state-v1` und in Draft-PR `#17` gepusht.

## Unveränderte aktuelle Auswahlpipeline

- Für den expliziten Zielanker `T` wird genau die bestehende Task-15-/Task-22-Einzel-Origin-Pipeline über `outer_origins.run_outer_origin(...)` wiederverwendet.
- Das Entwicklungsfenster ist semantisch exakt `[T-730 Tage,T)`.
- Eine zweite Auswahl-, Ranking-, Router- oder Simulationspipeline wurde nicht eingeführt.
- Frühere Outer-PnL, Rankings, Reports, Monthly-Gate-Ergebnisse, Hindsight-Werte und menschliche Interpretation besitzen keinen Eingangskanal in die aktuelle Auswahl.

## Vollständige aktuelle Evidenzbindung

Vor dem Refit werden transitiv gebunden und erneut geprüft:

- Zielanker `T`, Trainingsanfang, Trainingsende, `valid_from=T+24h` und nächster Monatsanker als `valid_until`;
- vollständiger Frozen-Data-Snapshot für `ETHUSDC`, `BTCUSDC` und `ETHBTC`;
- `snapshot_as_of_day=T-1`, `latest_common_complete_day=T-1` und exaktes Rohdatenende bei UTC-Mitternacht `T`;
- Snapshot-, Drei-Markt-, Code-Commit-, Pipelinegenerations- und Run-Fingerprint-Identität;
- Exchange-Info-Snapshot und dessen kausaler Zeitstempel;
- Kostenmodell, Execution-/Fee-/Slippage-Quellenhash, Quality-Gate-Quellenhash und Trial-Ledger-Head;
- Task-14-Foldplan, exaktes 730-Tage-Trainingsfenster, Seed und Development-Support;
- Feature-Store-, Feature-Fit-, Regime-Fit-, Assessment- und Drei-Markt-Kontextidentität;
- vollständige Vorgänger-Bundle-Identität aus dem letzten historischen Task-23-Origin;
- Task-24-Rotation einschließlich `valid_from`, `valid_until`, `entry_enabled_at_utc`, Flat-Handoff und State-Hash;
- historische Task-25-Baseline- sowie Task-26-Baseline-/Joint-/Slippage-Stress-Hashes;
- Task-27-Historical-Diagnostics-Hash ausschließlich als `NOT_FRESH`-Provenienz.

Persistierte Task-28-Ausgaben werden nur durch vollständiges Quellen-Replay akzeptiert.

## Champion/Challenger/Cash

Die Entscheidung ist deterministisch und verwendet ausschließlich die aktuelle Task-15-Auswahl und das aktuelle Task-22-Router-/Bundle-Ergebnis:

- `CHAMPION`, wenn der bisherige Kandidat im aktuellen 730-Tage-Inventar erneut getestet und von der aktuellen Pipeline wieder ausgewählt wird;
- `CHALLENGER`, wenn ein anderer aktuell getesteter Kandidat den erneut getesteten Champion und Cash über die unveränderte lexikografische Auswahl schlägt und alle Gate-, DSR-, PBO-, Cash- und Router-Nachweise vollständig sind;
- `CASH`, wenn die aktuelle Auswahl `NO_TRADE` ergibt oder das aktuelle Bundle nicht routbar ist;
- fehlt der erneute Champion-Test oder vollständige aktuelle Evidenz, wird fail-closed keine aktivierbare Tradingentscheidung erzeugt.

Das Ergebnis bindet Kandidaten-IDs, Ranking-Evidenz, Routerausgang, aktuelles Bundle, Vorgängerbundle und einen eigenen Entscheidungsdigest.

## T+24 und Rotation

- Anfragen vor `T` sind unzulässig.
- Abschluss nach `T+24h` darf nicht rückwirkend aktiviert werden.
- Neue Entries bleiben bis `valid_from=T+24h` gesperrt.
- `entry_enabled_at_utc` folgt dem Task-24-Zustand und muss mit der Bundle-Gültigkeit übereinstimmen.
- Der historische Prozess muss vor dem aktuellen Refit flat enden.
- Der vorherige Kandidat ist ausschließlich über seine gebundene Vorgängeridentität sichtbar; keine historische Position oder versteckter Runtime-Zustand wird übernommen.

## Historischer Status und Safety

Sämtliche Task-28-Ausgaben bleiben:

- `freshness=NOT_FRESH`;
- `diagnostic_only=true`;
- `canonical_adoption_eligible=false`;
- `manual_research_shadow_start_required=true`;
- `manual_research_shadow_start_allowed=false`;
- `sealed_final_holdout_used=false`;
- `bot_start_allowed=false`.

Paper, Testtrade, Live, Orders, Trading-API und der kanonische Adoption-/Finalpfad bleiben gesperrt.

## Negativtests

Fail-closed geprüft werden mindestens:

- Zukunftsdaten sowie stale oder falsch abgeschnittene Drei-Markt-Snapshots;
- Anfrage vor `T` oder Abschluss nach `T+24h`;
- falscher Zielanker und manipuliertes 730-Tage-Fenster;
- falscher Vorgänger trotz neuem Reporthash und vollständigem Quellen-Replay;
- abgelaufene beziehungsweise widersprüchliche Bundle-Gültigkeit;
- manipulierte Task-24-Rotation oder `entry_enabled_at_utc` trotz neuem State-Hash;
- fehlender erneuter Champion-Test;
- deterministische echte `CHAMPION`-, `CHALLENGER`- und `CASH`-Pfade;
- manipulierte Champion/Challenger/Cash-Entscheidung;
- fehlende Joint-/Slippage-Stressbindung;
- unerlaubte Outer-/Hindsight-Rückwirkung;
- falsche Freshness-, Adoption-, Shadow-Start- oder Bot-Start-Claims trotz neuem Reporthash;
- gespeicherte Reports ohne vollständiges Quellen-Replay.

## Commits dieses Aufgabenblocks

- `da7ab0838f8d9cea4875a29c768e26d3786d6448` – Aufgabe 28 als aktiven Arbeitsstand markieren;
- `5f0582fcd9fbe66dac2da9b645027ab0ef2cb217` – bestehenden Einzel-Origin-Pfad mit optionaler Vorgängerbindung wiederverwenden;
- `84f114c5783b27d1508cf92fd40785413892481f` – Task-28-Refit-/Entscheidungsumschlag;
- `a00393e87868c24eb9865fa2902149f9a6421d92` – kanonischer Task-28-Vertrag;
- `fbfd22de010b62da9ec7a9a1123d9ab72d7d9a9f` – stabile Task-28-API;
- `3f6100b5a1cbeb91007e7aaaa106db44add34ec1` – erste Task-28- und Vorgänger-Regressionsprüfungen;
- `6893f499b3630645c7358354609d187d5c69221e` – Task-28 in die Pipelinegeneration binden;
- `753e8e19640bb83c19a08c92a9dcfb3fcf70e421` – Test-Fixture-Import korrigieren;
- `8fae482742063c342ea38ecac0d852ad9259e967` – Task-24-State-Serialisierung und Anfragekausalität härten;
- `3736c448f7e135c6693106198fe6ebad0777936e` – exakten aktuellen Drei-Markt-Snapshot binden;
- `e071ae046600b741e92720804a461f2d38c790c1` – Snapshot-, Kausalitäts- und Manipulationstests;
- `14a250a0dab5d8bcca0aa7f8a206a66594ba58fa` – Snapshot-/Stress-Provenienz im Python-Vertrag einfrieren;
- `4ceac2fb6af78f83ef53a81891071d7465c00e05` – kanonischen JSON-Vertrag synchronisieren;
- `de901fd3c8070e6b2f873ba1b4f4cf24878aeb79` – echte Pairwise- und Stress-Bindungstests;
- `7bcf19b811906732cf81cfc000a45409a949ecfb` – falschen Vorgänger, Ablauf und Fenster-Manipulation testen;
- `8b7134af30d98992ec53da9b140f1b7b9912c771` – erwarteten Task-23-Boundary-Fehler im Negativtest präzisieren.

## Validierung

GitHub-CI-Run `29722432007` auf technischem Head `8b7134af30d98992ec53da9b140f1b7b9912c771`:

- vollständige Suite: `1.214 Tests erfolgreich`;
- Python-Quellkompilierung: erfolgreich;
- PowerShell-Syntaxprüfung: erfolgreich;
- committed whitespace check: erfolgreich.

Zusätzliche grüne Zwischenläufe:

- `29720330944` – Rotation-State-/Kausalitätsfix vollständig grün;
- `29720886485` – exakte Snapshotbindung und Negativtests vollständig grün;
- `29721599216` – Pairwise-, Stress-, Compile-, PowerShell- und Whitespace-Prüfung vollständig grün.

## Sicherheitsstatus

- kein Backtest-, Paper-, Testtrade-, Live- oder Order-Start;
- keine API-Keys, privaten Endpunkte oder Secrets;
- keine Quality-Gates gelockert;
- keine Fake-Trades oder Fake-Reports;
- keine Rückwirkung historischer Ergebnisse auf aktuelle Auswahl;
- kein Protocol-v3-Finalstatus ohne wirklich neuen `sealed_final_holdout`;
- der Bot ist nicht start- oder live-fähig.

## Nächste Aufgabe

Erst nach grünem CI-Lauf des Task-28-Dokumentations-Heads beginnt Aufgabe 29: strikt orderfreier Research-Challenger-Shadow.
