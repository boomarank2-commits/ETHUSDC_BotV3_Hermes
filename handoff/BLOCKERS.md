# Blockers

Current blockers:
- Strategic target is still not reached.
- Latest multi-cycle loop `research_loop_20260709T213134Z` stopped for `validation_stagnation_3_cycles`.
- Best validation stayed negative at `-0.0004208934 USDC/day` with only 8 validation trades.
- Best blindtest audit was only `0.0096502748 USDC/day`, far below `+3 USDC/day`, and is explicitly repeated-audit-only.
- Candidate improvements increasingly reduced trade frequency; later cycles had only 5, 3, and 2 validation trades.
- Exit analysis in the last cycle showed stop-loss domination, suggesting entry quality/regime filtering remains unresolved.
- Exchange info remains unsupported by current public-data downloader path.
- BookTicker and orderbook snapshot tasks remain live-collector tasks and are not implemented in this UI workflow.
- Dashboard button is represented in state, but full background UI execution/progress wiring remains a next step.

Resolved in this session:
- Multi-cycle offline research loop runner added.
- Deterministic search-space generator added.
- Walk-forward validation helper added.
- Exit-reason/trade-cause analysis added.
- Simulator now emits specific exit reasons instead of only generic `rule` exits.
- Loop reports now include cycle summaries, stop reason, target status, safety locks, WFV summary, family summaries, exit summaries, and repeated blindtest audit marking.

Safety locks remain:
- Live locked.
- Paper locked.
- Testtrade locked.
- No trading API.
- No keys.
- No orders.
- No candidate adoption.
