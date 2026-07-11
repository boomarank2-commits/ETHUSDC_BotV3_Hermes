# Blockers

Current strategic blocker:

- No strategy has demonstrated the fixed `+3 USDC/day` target on a valid one-shot sealed holdout.
- The last post-Slippage control validation was negative at `-0.0086568356 USDC/day`, profit factor `0.4915795763`, with 17 trades.
- Its repeatedly viewed audit result is consumed historical evidence and cannot select or tune a candidate.

Current quality-evidence blockers:

- Mark-to-market drawdown is not yet produced; closed-trade drawdown cannot satisfy `quality_gate_v1`.
- Formal time-local rolling-origin refits are not implemented.
- Concentration, underwater duration, parameter-neighborhood, cost-stress, temporal, and regime evidence producers are not implemented.
- Therefore Protocol v2 intentionally reports failed/missing gates and cannot freeze a candidate.

Current data-policy blocker:

- Every selection-bearing date must avoid the consumed ledger window `2025-07-08` through `2026-07-07`.
- As the latest dynamic 1,095-day window moves forward, consumed dates can enter training. Such a run now fails closed instead of silently reusing them.
- The final 365-day holdout can overlap the ledger only as unevaluated consumed metadata; it cannot become selection evidence.

Other product gaps:

- Real BTCUSDC/ETHBTC context signals are not integrated; placeholder context candidates are not tested.
- Exchange info remains unsupported by the current public-data downloader path.
- BookTicker/orderbook history must not be fabricated; future collection is separate scope.
- Full background UI execution/progress wiring remains incomplete.

Resolved methodological defects:

- Generated, tested, WFV, and finalist stages now have honest counts and IDs.
- Candidate evaluation is deterministic and bounded instead of a hidden first-four slice.
- Multiple candidates receive WFV on complete UTC-day folds.
- Holdout candles are absent from the research loop.
- Consumed selection overlap fails closed.
- WFV aggregates cannot contradict their fold evidence and still pass.
- A forged or mismatched passing gate cannot freeze a candidate.
- Both legacy repeated-holdout entrypoints are disabled.

Safety locks remain:

- Live locked; Paper locked; Testtrade locked.
- No candidate adoption, Trading API, API keys, account data, or orders.
- Spot LONG-only; no shorts, margin, futures, or leverage.
