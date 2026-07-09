# Blockers

Current blockers:
- The strategic target is still not reached.
- Latest research run `research_20260709T181800Z` produced blindtest -0.0327853251 USDC/day, below the +3 USDC/day target.
- Validation for the selected candidate remained negative (-0.1363876748 USDC/day).
- Candidate leaderboard shows all 14 candidates have negative validation and high cost load.
- No family has validation profit factor near 1.
- Overtrading remains present in 3 candidates/families, but the selected candidate is not overtrading; its issue is still negative validation/profit factor below 1/cost load.
- Exchange info remains unsupported by current public-data downloader path.
- BookTicker and orderbook snapshot tasks remain live-collector tasks and are not implemented in this UI workflow.
- Dashboard button is represented in state, but full background UI execution/progress wiring remains a next step.

Resolved in this session:
- Research reports now include a full per-candidate leaderboard.
- Leaderboard ranking uses training/validation only.
- Blindtest metrics appear only on the final selected candidate row.
- Candidate diagnosis answers best training family, best validation family, lowest-cost family, overtrading/too-few-trades groups, near-one profit-factor groups, and why result is not profitable enough.
- One controlled improvement was added: trailing-stop/break-even-stop exit variants.

Safety locks remain:
- Live locked.
- Paper locked.
- Testtrade locked.
- No trading API.
- No keys.
- No orders.
