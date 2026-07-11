# Last Known Good

Repository baseline:

- Synchronized `main` before Protocol v2: `c73c71d Clarify control audit and Paper lock`.
- Active implementation branch: `agent/research-protocol-v2`.
- Branch verification: 505 collected tests, 505 passed with `py -3.12 -m pytest -q`.
- `git diff --check`: clean.
- No production research run was executed on the branch.

Protocol-v2 guarantees covered by tests:

- Exact complete-day validation for ETHUSDC 1-minute data.
- Dynamic latest 730+365 windows and 1,095/1,096-day consumed-ledger boundaries.
- No overlap between consumed dates and selection-bearing windows.
- Complete-day WFV folds and sampling.
- Day-weighted WFV aggregate/ranking consistency.
- Honest candidate stage subsets, counts, and hard caps.
- Candidate identity and quality-gate binding before freeze.
- Strict JSON handling of non-finite diagnostics.
- Fixture simulator spy proving no final-holdout candle is evaluated.
- Synthetic production-orchestration wiring test proving canonical 40/12/3/2 budgets, six WFV folds, three origin slots, and no planned-holdout simulation.
- Fail-closed legacy backtest/research entrypoints.
- Full canonical safety contract, including forbidden short/margin/futures/leverage and `candidate_adoptable=false`.

Execution-cost baseline:

- Fixed 100 USDC entry execution notional.
- At most one ETHUSDC LONG position; no compounding.
- Fee: 0.1% per side.
- Slippage: 5 bps per side.
- No BNB discount.
- Entry quantity uses entry execution price.
- Net P&L equals execution-price gross P&L minus entry and exit fees.
- Slippage is embedded in execution prices and reported diagnostically, not deducted twice.

Historical evidence policy:

- Post-fix control report: `reports/research_loop/research_loop_20260710T054549Z.json` and `.txt`.
- The viewed `2025-07-08` through `2026-07-07` audit window is permanently consumed for selection purposes.
- Pre-`03e9db0` slippage-derived rankings and cost diagnoses are obsolete.
- Historical reports remain append-only and are not deleted or rewritten.

Safety:

- ETHUSDC/USDC Spot LONG-only simulation.
- BTCUSDC/ETHBTC cannot trigger trades.
- No Live, Paper, Testtrade, Trading API, API keys, account data, or orders.
