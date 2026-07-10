# Research Loop Results

## Latest post-fix control run

- Loop run ID: `research_loop_20260710T054549Z`.
- Git commit recorded by report: `03e9db0`.
- Reports:
  - `reports/research_loop/research_loop_20260710T054549Z.json`,
  - `reports/research_loop/research_loop_20260710T054549Z.txt`,
  - `reports/research_loop/index.jsonl`.
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_loop_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --max-cycles 8 --max-candidates-per-cycle 40`.
- Cycles executed: 4 of 8.
- Stop reason: `validation_stagnation_3_cycles`.
- Target reached: false.

| Cycle | Generated | Tested | Selected validation candidate | Validation USDC/day | Validation trades | Audit USDC/day |
|---:|---:|---:|---|---:|---:|---:|
| 1 | 11 | 4 | `breakout_volatility_filter_01_001` | -0.0086568356 | 17 | -0.0012839958 |
| 2 | 11 | 4 | `breakout_volatility_filter_02_001` | -0.0212667747 | 39 | -0.0320012511 |
| 3 | 11 | 4 | `breakout_volatility_filter_03_001` | -0.0086568356 | 17 | -0.0012839958 |
| 4 | 11 | 4 | `breakout_volatility_filter_04_001` | -0.0086568356 | 17 | -0.0012839958 |

Best validation result:

- Candidate: `breakout_volatility_filter_01_001`.
- Net: `-0.0086568356 USDC/day`.
- Profit factor: `0.4915795763`.
- Trade count: 17.

Best recorded audit result:

- Net profit: `-0.4686584526 USDC`.
- Net: `-0.0012839958 USDC/day`.
- Profit factor: `0.9423532464`.
- Trade count: 14.
- Original report flags: `repeated_blindtest_audit=true`, `audit_only_not_selection=true`.
- Current policy: `consumed_audit_window=true`.

## Interpretation

- Corrected slippage materially reduces reported diagnostic costs and changes cost-based ranking inputs.
- The control run still shows no sufficient edge and does not approach `+3 USDC/day`.
- `max_candidates_per_cycle=40` is only a generator cap. The generator emitted 11 candidates per cycle, while the runner evaluated a hard-coded first-four slice.
- Only one validation leader per cycle received WFV.
- The repeated 365-day audit window is now consumed. It may be shown for history and defect analysis but cannot be used for strategy selection, parameter changes, ranking, routing, or future optimization.
- A new untouched final holdout may be evaluated only after strategy profile, router, strategies, parameters, and costs are frozen.

## Historical reports

Reports before commit `03e9db0` remain append-only historical evidence. Their direct execution-price P&L was not changed by the diagnostic fix, but their slippage totals, cost penalties, cost-based rankings, cost diagnoses, and derived search-space decisions are obsolete.

This includes:

- `reports/backtests/bt_20260709T151036Z.*`,
- `reports/research/research_*.json` and `.txt`,
- `reports/research_loop/research_loop_20260709T213134Z.json` and `.txt`.

## Safety status

- Live, Paper, and Testtrade remain locked. Public-data-only hypothetical Shadow mode is a separate future scope and has no order endpoints.
- No orders, Trading API, API keys, account data, shorts, margin, futures, or leverage.
- No candidate adopted.
