# Backtest Research Protocol

This document defines the allowed offline strategy-research protocol for ETHUSDC_BotV3_Hermes.

Hard boundaries:
- Symbol traded by the simulator: ETHUSDC only.
- Quote: USDC only.
- Market: Binance Spot LONG-only.
- Trade notional: 100 USDC.
- No shorts, margin, futures, leverage, orders, API keys, Binance Trading API, paper, testtrade, or live activation.
- BTCUSDC and ETHBTC may be used only as context filters. They may never create trades or orders.
- Raw data remains outside the repository under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Standard Library only unless the user explicitly approves dependencies.

Data protocol:
1. Check the data gate.
2. Load local ETHUSDC 1m ZIP/CHECKSUM pairs read-only.
3. Validate ordering, 1m spacing, duplicates, and gaps.
4. Split exactly 1095 UTC days for real runs:
   - first 730 UTC days: training block,
   - last 365 UTC days: blindtest block.
5. Split the training block internally:
   - subtrain for first candidate evaluation,
   - validation for candidate selection.
6. The blindtest is never used for ranking or parameter selection.

Research-run protocol:
1. Create a protocol object with run_id, git commit, raw_root, windows, families, parameter space, ranking rules, and safety locks.
2. Prepare no-lookahead features from current/past candles only.
3. Generate a small controlled candidate grid.
4. Evaluate candidates on subtrain and validation.
5. Rank using validation-only conservative criteria:
   - net_usdc_per_day,
   - profit_factor,
   - max_drawdown,
   - sufficient but not excessive trade_count,
   - fee/slippage cost load,
   - training/validation stability.
6. Select one candidate.
7. Only after selection, run the final blindtest once.
8. Store the complete experiment in `reports/research/`:
   - `<run_id>.json`,
   - `<run_id>.txt`,
   - `index.jsonl` append entry.
9. Include a full `candidate_leaderboard` for every tested candidate:
   - candidate_id,
   - family,
   - params,
   - training_metrics,
   - validation_metrics,
   - rank_score,
   - rank_position,
   - why_ranked_here,
   - weaknesses/rejection reasons.
10. Include `blindtest_metrics` inside the leaderboard only for the final selected candidate.
11. Include a `candidate_diagnosis` summary showing best training family, best validation family, lowest-cost family, overtrading/too-few-trades families, near-one profit-factor families, and why the result still is not profitable enough.
12. Report whether +3 USDC/day was reached. Never fake or force success.

Current implemented families:
- momentum_trend_filter
- breakout_volatility_filter
- mean_reversion_regime_filter
- pullback_in_trend
- session_filter
- cooldown_fee_aware

Reproducibility notes:
- Reports include the git commit. If the working tree is dirty during execution, the commit is recorded with `-dirty`.
- The current first research run was intentionally executed before final commit as part of the requested workflow, so it records `7cf9940-dirty`.
- To reproduce after commit, rerun:

`PYTHONPATH=src python -m ethusdc_bot.backtest.research_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
