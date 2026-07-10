# Next Action

Next approved ticket: implement Research Protocol v2 on a separate branch after the Slippage work block is synchronized to `origin/main`.

Required scope:

1. Report honest counts for `generated_candidates`, `tested_candidates`, `walk_forward_candidates`, and `finalists`.
2. Replace the hidden fixed first-four slice with deterministic, reproducible, resource-controlled candidate selection.
3. Apply walk-forward validation to multiple validation leaders.
4. Stop evaluating the consumed 365-day audit window inside research cycles.
5. Treat the current repeatedly viewed window as `consumed_audit_window = true`.
6. Derive the latest 730-day training plus 365-day audit/holdout window from complete UTC data rather than fixed years.
7. Add historical rolling-origin evaluation when more than the minimum 1,095 complete days are available.
8. Add fixed, documented quality gates for activity, drawdown, profit factor, profit concentration, WFV stability, parameter stability, stress costs, temporal robustness, and regime dependence.
9. Keep the current 0.1% fee plus 5 bps slippage per side as the binding baseline.
10. Do not change strategy parameters or add real BTCUSDC/ETHBTC context until the protocol is verified.

Acceptance requirements:

- Tests are written before implementation and demonstrate the old protocol defects.
- No ranking or adjustment consumes audit/holdout metrics.
- Reports state exactly which candidates and folds were evaluated.
- All safety locks remain unchanged.
- Full tests pass.
- Work is published on a separate branch through a reviewed pull request.

Large historical rolling-origin, UI end-to-end, and later shadow/replay runs remain future Hermes tasks after a clean synchronized handoff.
