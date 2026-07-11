# Current Status

Status: Research Protocol v2 is implemented and locally verified on branch `agent/research-protocol-v2`. It has not run a production historical search and has not evaluated a final holdout.

Verified baseline:

- `origin/main` and local `main` were synchronized at `c73c71d Clarify control audit and Paper lock` before the branch was created.
- The post-Slippage control remains historical evidence only: `research_loop_20260710T054549Z`.
- Full Protocol-v2 branch suite: 505 tests passed with Python 3.12.
- The real runner path was exercised with a six-day report labelled `fixture_smoke_non_production` and a separate synthetic production-orchestration wiring test using canonical budgets, folds, and origin policy.
- Simulator spies proved that neither orchestration path evaluated a planned final-holdout candle.

Protocol-v2 implementation:

- Dynamic 730-day training plus 365-day final-holdout metadata is anchored to the latest complete UTC day, never fixed years.
- Production completeness requires exactly 1,440 contiguous 1-minute candles from 00:00 through 23:59 UTC. Partial or gap-compensated days fail closed.
- The consumed ledger window `2025-07-08` through `2026-07-07` is forbidden in every selection-bearing training, validation, WFV, and historical-origin slice.
- The current final holdout is metadata-only. The research loop never receives or evaluates its candles.
- Candidate stages are honest and bounded: up to 40 generated, 12 tested, 3 WFV, and 2 finalists, with exact IDs and counts.
- Candidate testing is deterministic and family-balanced when a cap is needed.
- Six-fold WFV uses complete UTC-day boundaries and day-weighted aggregate metrics.
- Fixed-candidate historical replay is labelled diagnostic and cannot affect ranking, quality gates, or freeze.
- `quality_gate_v1` is immutable and fail-closed. WFV aggregates are independently checked against fold evidence.
- A passing gate must match the selected finalist ID and canonical parameter signature before any freeze.
- The public legacy `backtest.runner` and `research_runner` execution paths are disabled because they repeatedly evaluated holdout data.
- Per-cycle work is hard-bounded and reported as candidate-day and one-minute candle-evaluation caps.

Current gate outcome:

- No candidate is frozen or adoptable.
- The current simulator reports closed-trade drawdown, while the gate requires mark-to-market drawdown.
- Formal time-local rolling-origin refits, concentration, parameter-neighborhood, cost-stress, temporal, and regime evidence are not yet produced.
- Missing or invalid evidence blocks freeze; it is never treated as zero or success.
- `+3 USDC/day` remains not evaluated under Protocol v2 because no sealed-holdout workflow was run.

Safety status:

- ETHUSDC/USDC Spot LONG-only, fixed 100 USDC notional, at most one position, no compounding.
- Baseline cost: 0.1% fee plus 5 bps slippage per side; no BNB discount.
- No shorts, margin, futures, or leverage.
- Live, Paper, and Testtrade remain locked.
- No Binance Trading API, API keys, account data, or orders.
- BTCUSDC and ETHBTC remain non-trading context only and are not yet integrated into signals.
