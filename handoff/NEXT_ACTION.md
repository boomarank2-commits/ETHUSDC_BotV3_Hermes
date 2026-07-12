# Next Action

Immediate sequence for branch `codex/canonical-backtest-audit-and-consolidation`:

1. Ensure no old research process exists and reduce the two identical idle dashboard instances to one before the next launch.
2. Start only through `START_DASHBOARD.bat` and click `Backtest starten (Training/WFV)`.
3. Verify the new run is bound to commit `3299a4f879e2737b1166adc1db37f155fe4315e3` or its documentation-only descendant and still proves 40/12/3/2, context 6/2, six folds, audit false, final holdout false, and all trading locks.
4. After the first completed cycle, verify `profile_round_offset` and tested IDs differ from the old fixed-prefix frontier.
5. Let the run continue only if the canonical proof is valid; do not make another strategy change while it runs.
6. Compare the completed result with `production_research_supervisor_20260712T081650Z`, especially trades, no-trade gap, active months, WFV net/day, PF, drawdown, costs, positive folds, and family coverage.

Exact next diagnostic if the new run is still unprofitable:

- Use the new tested-profile evidence to identify whether any existing later profile improves activity and post-cost PF.
- If no existing profile does, add signal-funnel rejection counters to the current simulator/search report before changing entries or exits. The current report cannot attribute non-context signal rejection to individual filters.
- Do not invent a new engine, strategy family, router, cluster system, or Multi-Timeframe pipeline until that attribution exists.

Rolling-origin rule:

- Do not report 0/0 as a failed robustness test; it is unavailable with only 1095 complete days.
- One current 730+365 historical origin needs 1460 days; three need 2190 days.
- A formal ranking-capable rolling-origin result also requires a time-local pipeline refit; the existing fixed-candidate replay is diagnostic only.

Hard safety boundaries:

- No final holdout evaluation.
- No Quality-Gate relaxation or cost reduction.
- No Live, Paper, Testtrade, orders, API keys, account access, shorts, margin, futures, leverage, merge, force-push, or direct alternate production run.
