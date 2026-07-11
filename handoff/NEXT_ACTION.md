# Next Action

Next approved technical ticket after Protocol-v2 review and merge: implement the missing training-only quality-evidence producers. Do not change strategy parameters first.

Required sequence:

1. Add mark-to-market equity and drawdown evidence without changing execution P&L accounting.
2. Add profit-concentration and underwater-duration evidence.
3. Add deterministic +/-10% parameter-neighborhood evaluation.
4. Add the fixed fee/slippage stress scenarios from `quality_gate_v1`.
5. Add monthly, quarterly, and no-trade-gap evidence.
6. Add training-only regime assignment and regime-dependence evidence.
7. Implement genuine time-local rolling-origin pipeline refits; fixed-candidate historical replay remains diagnostic only.
8. Re-run all tests and an independent leakage review.
9. Run production selection only if every selection window is complete and has zero overlap with the consumed-audit ledger.

Holdout rule:

- Do not evaluate the final 365-day holdout during evidence production, candidate selection, ranking, parameter changes, or freeze.
- Do not claim `target_reached` or `+3 USDC/day` from training, validation, WFV, fixtures, or the consumed window.
- A separate future sealed-holdout workflow may run exactly once only after a candidate is fully frozen by all selection gates.

Deferred until the evidence contract is complete:

- Real BTCUSDC/ETHBTC context integration and adaptive strategy profiles.
- Public-data-only Shadow/replay work.
- UI background execution and progress wiring.
- Any Paper, Testtrade, Live, account, credential, or order functionality.
