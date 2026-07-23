# Protocol v3 – Cross-Cycle-Origin-Auswahl

Stand: 2026-07-23

## Ergebnis

Die result-unabhängige Cross-Cycle-Auswahl für einen vollständigen
Production-Origin ist implementiert. Sie ist kein Profit-Pass und keine
Bot-Freigabe.

Der neue Pfad:

- verlangt exakt die acht erlaubten Cycles eines Origins;
- prüft Source-Digests, Code-, Pipeline-, Origin- und Fold-Identität;
- führt alle 96 Profile in einer vollständigen Task-16-Matrix zusammen;
- berechnet PBO und DSR auf dieser vollständigen Matrix neu;
- akzeptiert Task-15-Entscheidungen nur, wenn sie exakt an die neu berechnete
  Evidenz gebunden sind;
- verwendet denselben öffentlichen lexikographischen Rank-Key wie die
  Inner-Cycle-Auswahl;
- verwendet das Ziel `+3 USDC/Tag` nicht als Ranking- oder Auswahlvariable;
- endet bei fehlenden Task-15-Entscheidungen fail-closed mit
  `BLOCKED_MISSING_TASK15_DECISIONS` und `NO_TRADE`;
- schreibt den Report create-only.

## Geänderte Produktionsflächen

- `configs/protocol_v3_production_origin_selection_contract.json`
- `configs/protocol_v3_pipeline_contract.json`
- `src/ethusdc_bot/protocol_v3/production_origin_selection.py`
- `src/ethusdc_bot/protocol_v3/production_origin_selection_api.py`
- `src/ethusdc_bot/protocol_v3/inner_selection.py`
- `src/ethusdc_bot/protocol_v3/inner_selection_api.py`
- `src/ethusdc_bot/protocol_v3/production_outer_adapter.py`
- `scripts/build_protocol_v3_production_origin_selection.py`
- `tests/unit/test_protocol_v3_production_inner_cycle.py`

## Verifikation

- fokussierte Cross-Cycle-/Inner-Cycle-/Outer-Adapter-Suite:
  `25/25` grün;
- zusätzliche Protocol-v3-Identitäts-, Runtime-, Task-33- und
  Dashboard-Tests: `63/63` grün;
- vollständige lokale Suite: `1.367/1.367` grün;
- `compileall src scripts`: grün;
- Ruff für alle geänderten Python-Dateien: grün;
- `git diff --check`: grün.

Ein repo-weites Ruff-Audit meldet 308 bereits vorhandene, nicht durch diesen
Diff verursachte Befunde. Sie wurden nicht in dieses fachliche Ticket gezogen.

## Alte Origin-1-Artefakte

Die vorhandenen acht Origin-1-Cycle-Artefakte wurden unter Commit `950c763`
und einer älteren Pipelinegeneration erzeugt. Der neue Selector verwirft sie
korrekt wegen gemischter beziehungsweise veralteter Identität. Sie dürfen
nicht umetikettiert, kopiert oder als Evidenz der neuen Generation ausgegeben
werden.

Der teure Origin-1-Lauf wird noch nicht erneut gestartet: Der nächste
Produktionsschritt ändert erneut die Pipelinegeneration. Ein vorheriger Lauf
wäre danach wieder veraltet.

## Belegter nächster Engpass

Der Production-Fold-Evaluator verwirft nach der Simulation noch die
detaillierte Quality-Evidenz. Für rechtmäßige Task-15-Entscheidungen fehlen
insbesondere vollständige WFV-Fold-Metriken und Equity, Full-Training- und
Validation-Nachweise, Joint-/Slippage-Stress, Parameterstabilität sowie
rollende, zeitliche und Regime-Evidenz.

Nächste Reihenfolge:

1. Production-Finalistenpfad um diese vollständige Quality-Evidenz erweitern.
2. Pro Cycle echte, evidenzgebundene Task-15-Entscheidungen erzeugen.
3. Origin 1 genau einmal über alle acht Cycles unter der dann finalen
   Pipelinegeneration neu ausführen.
4. Cross-Cycle-Origin-Selector ausführen.
5. Task-13-Origin-Work-Unit, Tasks 19 bis 27 und danach Origins 2 bis 12
   anbinden.

Bis dahin bleiben Adoption, Paper, Testtrade, Live und Botstart gesperrt.
