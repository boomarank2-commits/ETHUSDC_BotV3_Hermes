# Research Loop Results

Latest loop run:

- Loop run ID: `research_loop_20260709T213134Z`
- Reports:
  - `reports/research_loop/research_loop_20260709T213134Z.json`
  - `reports/research_loop/research_loop_20260709T213134Z.txt`
  - `reports/research_loop/index.jsonl`
- Command:
  - `PYTHONPATH=src python -m ethusdc_bot.backtest.research_loop_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --max-cycles 8 --max-candidates-per-cycle 40`
- Git commit recorded by report: `6911ff9-dirty` because the loop was executed before the final commit.
- Cycles executed: 7 of 8.
- Generated candidate proposals: 77.
- Tested candidate frontier rows: 28.
- Stop reason: `validation_stagnation_3_cycles`.
- Target reached: false.

Cycle summary:

| Cycle | Best validation candidate | Validation USDC/day | Blindtest audit USDC/day | Validation trades |
|---:|---|---:|---:|---:|
| 1 | `breakout_volatility_filter_01_001` | -0.0086568356 | -0.0012839958 | 17 |
| 2 | `breakout_volatility_filter_02_001` | -0.0070945587 | 0.0096502748 | 13 |
| 3 | `breakout_volatility_filter_03_001` | -0.0049659017 | 0.0049085533 | 9 |
| 4 | `breakout_volatility_filter_04_001` | -0.0004208934 | -0.0067358372 | 8 |
| 5 | `breakout_volatility_filter_05_001` | -0.0034848477 | -0.0076226041 | 5 |
| 6 | `breakout_volatility_filter_06_001` | -0.0015801624 | -0.0116253967 | 3 |
| 7 | `breakout_volatility_filter_07_001` | -0.0030471361 | -0.0036968249 | 2 |

Best validation result:

- Candidate: `breakout_volatility_filter_04_001`
- Family: `breakout_volatility_filter`
- Validation net USDC/day: `-0.0004208934`
- Validation profit factor: `0.9184698895`
- Validation trade count: `8`

Best blindtest audit result:

- Net profit: `3.5223502955 USDC`
- Net USDC/day: `0.0096502748`
- Trade count: `11`
- Profit factor: `1.7538949399`
- Marked as `repeated_blindtest_audit: true` and `audit_only_not_selection: true`.

Interpretation:

- The +3 USDC/day target was not reached.
- Best validation remained slightly negative and sparse.
- The best blindtest audit was positive but only `0.0096502748 USDC/day`, far below the target and not valid for tuning.
- Later cycles reduced trade frequency heavily; cycle 7 had only 2 validation trades and stop-loss domination in exit analysis.
- The next research direction should not loosen gates for report cosmetics. It should investigate why stricter breakout/cost controls suppress activity before producing sufficient edge, then test a different ETHUSDC-only entry class or context-filtered regime with enough validation trades.

Safety status:

- Live locked.
- Paper locked.
- Testtrade locked.
- Orders not created.
- Binance Trading API not used.
- API keys not used.
- No candidate adopted.
