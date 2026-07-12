# Next Action

Immediate sequence for branch `codex/ui-responsiveness-and-next-iteration`:

1. Preserve the completed UI responsiveness fix and its focused/full regression coverage.
2. Add bounded signal-funnel attribution to the existing simulator/search report only: eligible observations, raw entry signals, and rejection counts by existing entry/filter/cooldown/context reason.
3. Do not change strategy parameters, costs, gates, candidate budgets, family definitions, or ranking in that instrumentation block.
4. Use a small deterministic simulation test to prove counters reconcile and do not affect trades or PnL.
5. Commit, push, and update the stacked draft PR/handoff.
6. Only then prepare the next canonical UI run and verify 40/12/3/2, context 6/2, six folds, audit false, final holdout false, and all trading locks.

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
