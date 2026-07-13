# Next Action

Immediate sequence for branch `codex/ui-responsiveness-and-next-iteration`:

1. Relaunch the existing dashboard only through `START_DASHBOARD.bat` so the committed asynchronous refresh code is active.
2. Verify the completed run appears without UI blocking and no second supervisor starts automatically.
3. Use the existing data-check button, wait for the Data Gate, then start the next canonical Training/WFV run through the UI button only.
4. Verify 40/12/3/2, context 6/2, six folds, audit false, final holdout false, and all trading locks after cycle 1.
5. Let the run complete without code or parameter changes.
6. Use the new validation/WFV signal funnels to decide whether inactivity is dominated by threshold, volatility, cooldown, position occupancy, session, or context veto.

Evidence to preserve:

- The rotation patch already found a positive post-cost WFV profile, but only 28 trades across 546 days.
- Fold trades are 4/4/2/2/12/4 and the maximum no-trade gap is 135 days.
- More trades alone are not success; preserve PF 1.4688, drawdown 6.3884, cost realism, and fold stability as comparison dimensions.
- Do not invent a new engine, strategy family, router, cluster system, or Multi-Timeframe pipeline until that attribution exists.

Rolling-origin rule:

- Do not report 0/0 as a failed robustness test; it is unavailable with only 1095 complete days.
- One current 730+365 historical origin needs 1460 days; three need 2190 days.
- A formal ranking-capable rolling-origin result also requires a time-local pipeline refit; the existing fixed-candidate replay is diagnostic only.

Hard safety boundaries:

- No final holdout evaluation.
- No Quality-Gate relaxation or cost reduction.
- No Live, Paper, Testtrade, orders, API keys, account access, shorts, margin, futures, leverage, merge, force-push, or direct alternate production run.
# Morgen zuerst: reboot-sicherer Resume-State und die dreistufige UI-Anzeige

Die vollständige Agenda steht in `handoff/TOMORROW_AGENDA.md`. Der aktuelle
Lauf darf nicht unterbrochen oder durch einen zweiten Runner ersetzt werden.
