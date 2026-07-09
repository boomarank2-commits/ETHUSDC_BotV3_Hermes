# Blockers

Current blockers:
- The strategic target is still not reached.
- Latest research run `research_20260709T170636Z` produced blindtest -0.0674168068 USDC/day, below the +3 USDC/day target.
- Validation was also negative (-0.2452730967 USDC/day), so the selected candidate is not a strong candidate even before blindtest.
- Research reports currently store the selected candidate and parameter space, but not a full per-candidate leaderboard; this limits diagnosis of why other families failed.
- Exchange info remains unsupported by current public-data downloader path.
- BookTicker and orderbook snapshot tasks remain live-collector tasks and are not implemented in this UI workflow.
- Dashboard button is represented in state, but full background UI execution/progress wiring remains a next step.

Resolved in this session:
- Baseline backtest diagnosis helper exists.
- Formal research protocol exists and forbids blindtest selection.
- Experiment registry writes `reports/research/index.jsonl`, JSON, and TXT without overwriting old runs.
- No-lookahead features exist.
- Context helpers explicitly prevent BTCUSDC/ETHBTC from triggering trades.
- Research runner can run from CLI and save a real experiment.

Safety locks remain:
- Live locked.
- Paper locked.
- Testtrade locked.
- No trading API.
- No keys.
- No orders.
