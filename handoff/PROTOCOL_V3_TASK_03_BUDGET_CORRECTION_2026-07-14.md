# Protocol v3 – Korrektur zum Handoff Aufgabe 3/33

Stand: 2026-07-14

## Korrigierter Begriff

Im ursprünglichen Task-3-Handoff wurden `96 / 3.840 / 1.152 / 288 / 192` als globale Maximalbudgets bezeichnet. Diese Werte sind korrekt für den **historischen 12-Origin-Monatsprozess**, aber nicht für den gesamten im Blueprint vorgesehenen Research-Ablauf.

Der Blueprint verlangt zusätzlich genau einen aktuellen 730-Tage-Refit mit derselben inneren Obergrenze von acht Cycles und `40/12/3/2`.

Verbindliche Trennung:

| Budgetebene | Cycles | generiert | getestet | Walk-forward | Finalisten |
|---|---:|---:|---:|---:|---:|
| zwölf historische Origins | 96 | 3.840 | 1.152 | 288 | 192 |
| genau ein aktueller Refit | 8 | 320 | 96 | 24 | 16 |
| gesamte Protocol-v3-Hülle | 104 | 4.160 | 1.248 | 312 | 208 |

## Technische Korrektur

- `SearchBudgetPolicy` bleibt die reine, bereits getestete 12-Origin-Prozessgrenze.
- `src/ethusdc_bot/protocol_v3/global_budget.py` ergänzt genau einen aktuellen Refit und erzwingt die gesamte Hülle.
- Ein zweiter aktueller Refit, ein neunter Cycle eines Selection-Runs oder eine globale Überschreitung blockiert fail-closed.
- `configs/protocol_v3_pipeline_contract.json` bindet diese Hülle per Quelldigest in die Pipelinegeneration.

Damit werden keine Budgets erweitert. Es wird ausschließlich der bereits im Blueprint vorhandene aktuelle Refit korrekt zur globalen Obergrenze addiert.

Alle Stellen im ursprünglichen Task-3-Handoff, die 96 Cycles als „global“ bezeichnen, sind durch diese Korrektur ersetzt und als **12-Origin-Prozessbudget** zu lesen.
