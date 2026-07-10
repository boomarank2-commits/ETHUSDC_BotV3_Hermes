# Last Known Good

Code baseline:

- Local safe commit: `03e9db0 Fix backtest execution cost accounting`.
- Parent remote baseline before synchronization: `8ac7003 Add multi-cycle offline research loop runner`.
- The Slippage commit changes only:
  - `src/ethusdc_bot/backtest/simulator.py`,
  - `tests/unit/test_backtest_simulator.py`,
  - `docs/29_BACKTEST_EXECUTION_COST_AUDIT.md`.
- Post-fix full test verification: 412 tests passed.

Execution-cost baseline:

- Fixed notional: 100 USDC per trade.
- At most one ETHUSDC LONG position.
- No compounding.
- Fee: 0.1% per side.
- Slippage: 5 bps per side.
- No BNB discount in the binding baseline.
- Entry quantity uses entry execution price.
- Net P&L equals execution gross P&L minus entry and exit fees.
- Slippage is embedded in execution prices and is reported diagnostically, not deducted twice.

Data baseline:

- Public local data root: `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Total files at the last data-gate verification: 6,589.
- `.tmp/.part`: 0; zero-byte files: 0.
- ETHUSDC 1m: 1,095 ZIP/checksum pairs.
- BTCUSDC 1m: 1,095 ZIP/checksum pairs.
- ETHBTC 1m: 1,096 ZIP/checksum pairs.
- ETHUSDC aggTrades: 7 ZIP/checksum pairs.
- ETHUSDC trades: 1 ZIP/checksum pair.

Latest post-fix control research:

- Report: `reports/research_loop/research_loop_20260710T054549Z.json` and `.txt`.
- Index: `reports/research_loop/index.jsonl`.
- Cycles: 4; stop reason: `validation_stagnation_3_cycles`.
- Generated/tested per cycle: 11/4.
- Best validation: `-0.0086568356 USDC/day`, PF `0.4915795763`, 17 trades.
- Best consumed audit result: `-0.0012839958 USDC/day`, PF `0.9423532464`, 14 trades.
- Target: not reached.

Historical-report policy:

- The viewed 365-day audit window is consumed and cannot be called an untouched final blindtest.
- Pre-`03e9db0` slippage-derived rankings and cost diagnoses are obsolete.
- Historical reports remain append-only and are not deleted or rewritten.

Safety:

- ETHUSDC/USDC Spot LONG-only simulation.
- BTCUSDC/ETHBTC context may never trigger trades.
- No Live, Paper, or Testtrade unlock, Trading API, API keys, account data, or orders. Public-data-only hypothetical Shadow mode remains a separate future scope.
