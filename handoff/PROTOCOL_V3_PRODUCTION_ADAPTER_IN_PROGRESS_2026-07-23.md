# Protocol v3 – Produktionsadapter und erster echter Inner-Origin-Lauf

Stand: 2026-07-23

GitHub-Issue: `#21`

Branch/PR: `codex/research-resume-and-ui-state-v1`, Draft-PR `#17`

## Ergebnis

Der bisher fehlende Produktionspfad ist teilweise real implementiert und nicht
mehr nur Fixture-Evidenz:

- ein fail-closed Produktionsadapter-Plan bindet Rohdaten, Snapshot,
  Exchange-Info, permanenten Trial-Ledger, Pipelinegeneration, Tasks 13 bis 27,
  zwölf Origins und die exakten sechs 60-Tage-Folds;
- die echte Task-8-Simulation läuft über ausgerichtete
  `ETHUSDC`-/`BTCUSDC`-/`ETHBTC`-Minutendaten;
- pro Kandidat entstehen exakt 360 tägliche Netto-MTM-Werte;
- pro Inner-Cycle werden 40 Kandidaten erzeugt, 12 getestet, 3 promoted und 2
  Finalisten markiert;
- Task-16-Matrix, Task-17-PBO und Task-18-DSR werden produktiv berechnet;
- native Trials werden unveränderlich in den permanenten Ledger geschrieben;
- identische Versuche auf demselben Fenster werden als Cache-Reuse und nicht
  als neuer unabhängiger Trial gezählt;
- alle Handelswege bleiben gesperrt.

Der Adapter ist noch nicht fertig und darf Task 33 noch nicht auf READY setzen.
Task-13-Transaktionscheckpoint, Cross-Cycle-Origin-Champion, Tasks 19 bis 27 und
die zwölf vollständigen Outer Origins fehlen noch.

## Gebundene Commits

- `54a63a5` – fail-closed Produktionsadapter-Plan
- `875ab40` – exakter realer 6x60-Fold-Evaluator
- `7d1a56e` – realer Inner-Cycle mit Trial-Ledger, Matrix, PBO und DSR
- `950c763` – korrekte Cache-Reuse-Zählung

Alle Commits sind auf PR `#17` gepusht.

Validierung:

- vollständige lokale Suite: `1.365/1.365` grün;
- gezielte neue/abhängige Tests: `72/72` grün;
- GitHub Review CI für Head `950c763`: Run `29993051021`, grün;
- gezielter Ruff- und Diff-Check: grün.

## Reale Adapter-Plan-Evidenz

Create-only:

`C:\TradingBot\data\ETHUSDC_BotV3_Hermes\runtime\protocol_v3\production_outer_adapter\adapter-plan-54a63a5.json`

- Plan-Digest:
  `a9aafb5c26d9f9ad000cacc23507acbf0c4e1199f686f6f0f51e5bde9607e330`
- Daten-Snapshot:
  `ea4cb7750cea5bc75574a15e29fee6715af751d9a41a9d807fead70680d71447`
- Exchange-Info-Snapshot:
  `82c9d74c3fa02cede54f44c894882b3ab139da5a1cc64d651c685580bdf21029`
- 3 Märkte × 1.116 vollständige UTC-Tage vorhanden
- 12 Origins × 6 Folds × 60 Validierungstage gebunden
- Status: `ADAPTER_PLAN_READY`
- Execution-State: `EXECUTOR_NOT_READY`

Der Plan wurde vor den nachfolgenden Executor-Commits erzeugt und ist deshalb
absichtlich keine aktuelle Executor-Attestation.

## Echter Ursprung 1

- Origin: `1`
- Development: `2023-07-09..2025-07-07`
- Inner-Validierungsunion: `2024-07-13..2025-07-07`
- reales Drei-Markt-Raster: 518.400 gemeinsame Minuten für die sechs Folds

Unter der aktuellen Generation `950c763` wurden alle acht erlaubten Zyklen
ausgeführt. Das sind 96 Profile, davon 95 neue unabhängige Trials und eine
belegte Cache-Wiederverwendung. Ein älterer, vor der Cache-Korrektur erzeugter
Zyklus bleibt zusätzlich korrekt als 12 unabhängige historische native Trials
im permanenten Multiple-Testing-Zähler, wird aber nicht mit der aktuellen
Generation zur Auswahl vermischt.

Aktueller permanenter Ledger:

- native/resolved Trials: `107`
- Cache-Reuse-Ereignisse: `1`
- konservativer Legacy-Multiplicity-Floor: `180`
- aktuelles `N_raw` für eine neue vollständige DSR-Auswertung: `287`

| Cycle | beste Familie | Netto USDC/Tag | Netto 360 Tage | Trades |
|---:|---|---:|---:|---:|
| 1 | breakout_volatility_filter | -0,107027 | -38,5297 | 132 |
| 2 | breakout_volatility_filter | -0,012850 | -4,6260 | 16 |
| 3 | session_filter | +0,005250 | +1,8900 | 40 |
| 4 | cooldown_fee_aware | +0,006437 | +2,3175 | 12 |
| 5 | breakout_volatility_filter | -0,021019 | -7,5668 | 15 |
| 6 | session_filter | **+0,017725** | **+6,3809** | 33 |
| 7 | cooldown_fee_aware | +0,009780 | +3,5209 | 11 |
| 8 | breakout_volatility_filter | -0,031947 | -11,5011 | 20 |

Der beste bislang beobachtete Entwicklungswert entspricht nur rund `0,59 %`
des Ziels `+3 USDC/Tag`. Er ist kein freigegebener Kandidat:

- nur 33 Trades in 360 Tagen;
- Cycle-6-DSR beim damaligen Ledger-Stand: `0.0`;
- `passed_minimum_dsr=false`;
- kein Quality-Gate-Pass;
- kein Outer-OOS-Ergebnis;
- keine Adoption oder Botfreigabe.

Create-only Cycle-Artefakte:

`C:\TradingBot\data\ETHUSDC_BotV3_Hermes\runtime\protocol_v3\production_outer_adapter\cycle-o01-c01-950c763.json`

bis

`C:\TradingBot\data\ETHUSDC_BotV3_Hermes\runtime\protocol_v3\production_outer_adapter\cycle-o01-c08-950c763.json`

## Nachgewiesene nächste Lücke

Task 16 verlangt ausdrücklich, dass alle getesteten Profile aller Cycles in der
Origin-Matrix erhalten bleiben. Task 15 definiert dagegen nur die Auswahl
innerhalb eines angegebenen Cycles. Der bestehende Vertrag sagt nicht
eindeutig, wie ein Origin-Champion aus bis zu acht Cycle-Entscheidungen
bestimmt und in Task 23 übergeben wird.

Nicht zulässig:

- automatisch den letzten Cycle verwenden;
- den höchsten Netto-Wert ohne vollständige Gates verwenden;
- nach Kenntnis der Ergebnisse eine neue Rankingregel erfinden;
- Profile verschiedener Pipelinegenerationen vermischen.

Der kleinste nächste Schritt ist deshalb eine vorab versionierte,
result-unabhängige Cross-Cycle-Origin-Selection-Regel. Danach:

1. vollständige Origin-Matrix der acht aktuellen Cycles bauen;
2. PBO/DSR gegen den aktuellen Ledger-Head neu berechnen;
3. pro Cycle die unveränderte Task-15-Entscheidung ausführen;
4. nur gate-bestandene Entscheidungen mit derselben lexikographischen
   Task-15-Rangfolge zum Origin-Champion zusammenführen; sonst `NO_TRADE`;
5. Task-19/20-Feature- und Regime-State auf echten Daten bauen;
6. Task-21/22-Spezialist und Router ausführen;
7. Task-13-Checkpoint/Resume für den vollständigen Origin-Work-Unit binden;
8. Origins 2 bis 12 und danach Tasks 24 bis 27 ausführen.

## Sicherheitsstatus

- keine API-Keys oder privaten Endpunkte
- keine Orders
- kein Paper-, Testtrade- oder Live-Start
- kein versiegelter Final-Holdout
- keine Gate-Lockerung
- keine erfundenen Trades, Tagesreihen oder Reports
- Task 33 bleibt blockiert
- Botstart bleibt gesperrt
