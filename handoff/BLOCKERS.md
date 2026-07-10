# Blockers

Current strategic blocker:

- The `+3 USDC/day` target is not reached.
- Post-fix control validation is negative at `-0.0086568356 USDC/day` with profit factor `0.4915795763` and only 17 trades.
- The consumed audit-window result is also negative at `-0.0012839958 USDC/day` and is not eligible for selection or optimization.

Current methodological blockers:

- `max_candidates_per_cycle=40` is misleading in practice: the generator currently emits 11 candidates and the runner hard-slices evaluation to the first 4.
- Only one candidate per cycle receives walk-forward validation.
- The repeatedly viewed 365-day window is consumed and cannot serve as an untouched final holdout.
- The current loop evaluates that audit window every cycle even though it does not feed programmatic ranking.
- Research reports do not yet separate generated, tested, WFV, and finalist counts.
- Rolling-origin robustness across additional historical windows is not implemented.
- The current `context_filter` does not consume BTCUSDC or ETHBTC data; it only re-runs an ETHUSDC base signal.
- Fixed numerical quality gates and stress-test acceptance are not yet implemented.

Other known product gaps:

- Exchange info remains unsupported by the current public-data downloader path.
- BookTicker and orderbook snapshots require future public live collection and must not be fabricated historically.
- Full background UI execution/progress wiring remains incomplete.

Resolved:

- Diagnostic execution slippage no longer includes normal holding-period market movement.
- Fees are recorded once per side and slippage is not double-subtracted from P&L.
- Hand-checkable accounting and all exit paths have regression coverage.

Safety locks remain:

- Live locked.
- Paper with order endpoints locked.
- Testtrade locked.
- No trading API, keys, account data, or orders.
- No candidate adoption.
