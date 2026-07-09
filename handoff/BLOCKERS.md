# Blockers

Current blockers:
- The strategic target is still not reached.
- Latest research run `research_20260709T193221Z` produced blindtest -0.0327853251 USDC/day, below the +3 USDC/day target.
- Validation for the selected candidate remained negative (-0.1363876748 USDC/day).
- Family aggregates show all six families are high-cost families.
- No family has validation profit factor near or above 1; nearest-to-one family is cooldown_fee_aware but still below 1.
- Stronger minimum expected move / cost-filter candidates did not outrank the existing selected candidate on validation.
- Exchange info remains unsupported by current public-data downloader path.
- BookTicker and orderbook snapshot tasks remain live-collector tasks and are not implemented in this UI workflow.
- Dashboard button is represented in state, but full background UI execution/progress wiring remains a next step.

Resolved in this session:
- Research reports now include family-level aggregates.
- Family aggregates use training/validation only and contain no blindtest metrics.
- Research reports now include family diagnosis.
- One controlled improvement was added: stronger minimum expected move / cost filters in two cooldown_fee_aware candidates.

Safety locks remain:
- Live locked.
- Paper locked.
- Testtrade locked.
- No trading API.
- No keys.
- No orders.
