# Protocol v3 – Aufgabe 27 DONE_100

Stand: 2026-07-19

## Verbindlicher Abschlussstand

`27/33 = 81,82 % DONE_100`.

Aufgabe 27 ist vollständig umgesetzt, getestet, auf Branch `codex/research-resume-and-ui-state-v1` und in Draft-PR `#17` gepusht.

## Umgesetzte Hindsight-Solver

### `all_candle_one_trade_close_hindsight`

- konsumiert exakt 365 vollständige UTC-Tage beziehungsweise 525.600 geordnete ETHUSDC-1m-Kerzen;
- verlangt endliche, gültige OHLCV-Daten und positive Volumenpunkte;
- erlaubt höchstens einen LONG-Roundtrip je UTC-Tag;
- bestimmt einen früheren Entry-Close und einen strikt späteren Exit-Close innerhalb desselben UTC-Tags;
- verwendet dieselbe Task-7-/8-Marktpreis-, Mengen-, Rundungs-, Gebühren-, Slippage- und Exchange-Info-Logik;
- bleibt ausdrücklich optimistische Hindsight-Diagnostik und niemals handelbare Evidenz.

### `candidate_matched_volume_filtered_hindsight`

- konsumiert dieselben vollständigen ETHUSDC-Prozessdaten;
- arbeitet LONG-only und mit höchstens einem offenen Lot;
- übernimmt pro Task-22-Bundle die aus dem Task-25-Baseline-Ledger abgeleitete maximale tatsächliche Roundtrip-Zahl je UTC-Entry-Tag;
- übernimmt die eingefrorene `max_hold_minutes`-Grenze des Kandidatenbundles;
- hält T+24h, Bundle-Gültigkeit, Monatsrotation und Task-24-Exit-only-/Flat-Handoff kausal ein;
- erzwingt keine Liquidation an Monatsgrenzen;
- bewertet den Prozessend-Close mit derselben Task-24-Terminalpreis-, Rundungs-, Gebühren- und Slippage-Logik und gibt nur vollständig geschlossene Pfade aus;
- verwendet keine Outer-Ergebnisse für Auswahl oder Gate-Anpassung.

## Transitive Evidenzbindung

Die neue Binding-Schicht revalidiert und bindet:

- vollständigen Frozen-Data-Snapshot und jeden der 365 ETHUSDC-Tagesdigests;
- binären vollständigen Solver-Prozessdatenhash;
- Exchange-Info-Snapshot und Execution-Rules-Hash;
- Task-7-/8-Ausführungs-, Gebühren- und Slippage-Verträge;
- aktuellen Solver-Code, Historical-Diagnostics-Code und Pipeline-Vertrag;
- aktuelle Pipelinegeneration und deren Component-/Source-Digests;
- alle zwölf Task-23-Origin-Hashes und Run-Fingerprints;
- die vollständige Task-22-Bundle-Kette einschließlich Router, Kosten, Vorgänger und Gültigkeit;
- alle zwölf Task-24-Rotationszustände einschließlich Exit-only, `flat_time_utc`, `entry_enabled_at_utc` und verbotener Monatsliquidation;
- Task-25-Outer-MTM-Ledger;
- sämtliche Solver-Eingaben, Policy-Kette, Tagesausgaben, Trades und Solver-Ausgabehashes.

Persistierte Bindings werden nur durch vollständiges Quellen-Replay akzeptiert. Der frühere allgemeine `benchmark_evidence`-Kanal und freie Caller-Claims für Benchmarkwerte, Datenhash, Commit oder Pipelinegeneration wurden entfernt.

## Historical Diagnostics und Bootstrap

Unverändert erhalten und nun an echte Solver gebunden:

- exakt 10.000 Circular-Stationary-Bootstrap-Replikationen je `L ∈ {5,10,20}`;
- deterministischer UInt64-Seed aus dem kanonischen Pre-Bootstrap-Manifest;
- einseitige 95-%-Untergrenze als exakt 500. geordneter Wert ohne Interpolation;
- strenges historisches Ziel-Flag nur, wenn alle drei Untergrenzen mindestens 3 USDC/Kalendertag erreichen;
- Capture-Ratios ausschließlich aus den gebundenen Solver-Ausgaben;
- manuelle Leakage-/Overfit-Sperre bei auffälliger Capture;
- `NOT_FRESH`, `diagnostic_only`, `statistically_supported=false`, `sealed_bootstrap_target_supported=false`, `canonical_adoption_eligible=false`;
- keinerlei Rückwirkung auf Auswahl oder Monthly Quality Gate.

## Negativtests

Fail-closed geprüft werden mindestens:

- fehlende, doppelte oder umsortierte Minuten beziehungsweise UTC-Tage;
- negative, nichtfinite oder vollständig unhandelbare Volumendaten;
- Lookahead-/Hindsight-Umdeklaration;
- zu viele Roundtrips;
- überschrittene Haltedauer;
- überlappende oder ungeordnete Trades;
- T+24-/Origin-Gültigkeitsverletzungen;
- Task-22-Bundle-, Task-23-Origin- und Task-24-Rotations-/Handoff-Manipulation trotz neuem Hash;
- Kosten-, Gebühren-, Slippage-, Exchange- oder Solver-Hash-Manipulation;
- manipulierte Solverwerte oder Ausgaben trotz neuem Evidence-Hash;
- unerlaubtes Feedback in Auswahl oder Monthly Quality Gate;
- falsche Freshness-, Statistik-, Adoption- oder Finalstatus-Claims.

## Commits dieses Abschlussblocks

- `6f9691907dccfc7243acdf62153d850cb6e1ec7b` – echte Hindsight-Solver;
- `9f86f3ecea194f1cf308d6e04edc5c5486244056` – Solver-Negativtests;
- `1febdbcac90f6203a642a42f0eaf4cf3708ea134` – transitive Evidenzbindung;
- `12a6cddca3108f2db5889553c10daf8b666a44a3` – Historical Diagnostics konsumiert nur gebundene Solver;
- `5ed34c68f5f377eab982820eebcd011641a55d26` – Historical-Diagnostics-Vertrag v2;
- `c8989860e392df3ed0a273468744136d5a7afa4e` – Solverquellen in Pipelinegeneration;
- `7c071f2e3d2c0eb597a00287131278bd58f5a16a` – gebundene Diagnose-/Caller-Claim-Tests;
- `f5d83c6dbf3ebe17bdb712acf38142d73ff9439a` – gehärtete Bundle-/Origin-/Exit-only-Kette;
- `60bc41cf655ec39edb6d889a6b3d6abcbb4590be` – exakte Task-24-UTC-Rotationsfelder;
- `1b9a47035ebf72d1e00508b8ed78021615363f71` – direkte Rehash-Manipulationstests.

## Validierung

GitHub-CI-Run `29706161878` auf Head `1b9a47035ebf72d1e00508b8ed78021615363f71`:

- vollständige Suite: `1.205 Tests erfolgreich`;
- Python-Quellkompilierung: erfolgreich;
- PowerShell-Syntaxprüfung: erfolgreich;
- committed whitespace check: erfolgreich.

Der frühere rote Zwischenlauf betraf ausschließlich falsch benannte Task-24-Felder ohne `_utc`; dieser Fehler wurde vor dem grünen Abschlusslauf korrigiert.

## Sicherheitsstatus

- kein Backtest-, Paper-, Testtrade-, Live- oder Order-Start;
- keine API-Keys, privaten Endpunkte oder Secrets;
- keine Quality-Gates gelockert;
- keine Fake-Trades oder Fake-Reports;
- verbrauchter historischer Zeitraum bleibt `NOT_FRESH` und `diagnostic_only`;
- kein Protocol-v3-Finalstatus ohne wirklich neuen `sealed_final_holdout`;
- der Bot ist nicht start- oder live-fähig.

## Nächste Aufgabe

Erst nach grünem CI-Lauf des Dokumentations-Heads beginnt Aufgabe 28: aktueller 730-Tage-Refit und Champion/Challenger/Cash-Entscheidung.
