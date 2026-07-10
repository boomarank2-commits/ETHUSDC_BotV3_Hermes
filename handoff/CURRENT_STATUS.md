# Current Status

Status: The backtest execution-cost defect is fixed and independently verified. A post-fix control research loop was completed, but the strategic target remains unmet.

Latest completed code change:

- Commit `03e9db0 Fix backtest execution cost accounting` corrects diagnostic slippage accounting in `src/ethusdc_bot/backtest/simulator.py`.
- Entry and exit mid-prices are retained separately from execution prices.
- Entry and exit fees and slippage are recorded separately.
- Quantity remains based on the 100 USDC entry execution notional.
- Net P&L remains execution-price gross P&L minus fees; diagnostic slippage is not subtracted twice.
- End-of-data, take-profit, stop-loss, time-exit, break-even, and trailing-stop exits use the shared cost-accounting path.
- `docs/29_BACKTEST_EXECUTION_COST_AUDIT.md` documents the defect, formulas, impact, and hand-checkable examples.

Post-fix control run:

- Run ID: `research_loop_20260710T054549Z`.
- Git commit recorded by the report: `03e9db0`.
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_loop_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --max-cycles 8 --max-candidates-per-cycle 40`.
- Cycles executed: 4 of 8.
- Stop reason: `validation_stagnation_3_cycles`.
- Each cycle generated 11 candidates but evaluated only the first 4.
- Only one validation leader per cycle received walk-forward validation.
- Best validation: `-0.0086568356 USDC/day`, profit factor `0.4915795763`, 17 trades.
- Best consumed audit-window result: `-0.0012839958 USDC/day`, profit factor `0.9423532464`, 14 trades.
- Target `+3 USDC/day`: not reached.
- No candidate is adoptable.

Methodological status:

- All previously viewed 365-day blindtest results are now formally classified as `consumed_audit_window = true`.
- They may be retained for history, comparison, and defect analysis, but not for strategy selection, ranking, parameter changes, router decisions, or optimization.
- Reports produced before `03e9db0` retain historical execution-price P&L evidence, but their slippage-derived rankings and cost diagnoses are obsolete.
- The current loop's fixed first-four candidate frontier, single-candidate WFV, repeated audit evaluation, and non-functional context filter require a Research Protocol v2 repair before any strategy work.

Safety status:

- Trade symbol: ETHUSDC only.
- Quote/notional: fixed 100 USDC per trade, no compounding, at most one open position.
- Cost baseline: 0.1% fee and 5 bps slippage per side, no BNB discount.
- Spot LONG-only; no shorts, margin, futures, or leverage.
- Live, paper-with-order-endpoints, and testtrade remain locked.
- No Binance Trading API, API keys, account data, or orders.
- BTCUSDC and ETHBTC remain context-only and cannot open trades.
