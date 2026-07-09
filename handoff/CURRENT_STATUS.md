# Current Status

Status: Research reports now include family-level aggregates/diagnosis, plus one controlled cost-filter improvement.

Latest completed changes:
- Extended `src/ethusdc_bot/backtest/research_runner.py`:
  - `family_aggregates` derived from candidate leaderboard using training/validation only.
  - `family_diagnosis` answering best training family, best validation family, lowest-cost family, overtrading families, too-few-trades families, nearest-to-one profit-factor family, high-cost families, and problem assessment.
  - two controlled stronger minimum expected move / cost-filter candidates.
- Extended `src/ethusdc_bot/backtest/experiment_registry.py` text output with family aggregate/diagnosis summary.
- Updated tests in `tests/unit/test_research_runner.py`.
- Updated docs:
  - `docs/25_BACKTEST_RESEARCH_PROTOCOL.md`
  - `docs/26_BACKTEST_EXPERIMENT_LOG.md`

Previous research run:
- `research_20260709T181800Z`
- Candidates: 14.
- Selected: `breakout_volatility_filter_013`.
- Training: -0.0722564539 USDC/day.
- Validation: -0.1363876748 USDC/day.
- Blindtest: -0.0327853251 USDC/day.
- Target +3 USDC/day: not reached.
- Candidate diagnosis: 14/14 negative validation, 14/14 high cost, no near-one profit factor.

New real research run:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Run-ID: `research_20260709T193221Z`.
- Reports:
  - `reports/research/research_20260709T193221Z.json`
  - `reports/research/research_20260709T193221Z.txt`
  - `reports/research/index.jsonl`
- Git commit recorded by report: `2a3475a-dirty` because the run was executed before final commit.
- Candidates: 16.
- Families: 6.
- Selected candidate remained:
  - candidate_id: `breakout_volatility_filter_013`
  - family: breakout_volatility_filter
- Training: -0.0722564539 USDC/day.
- Validation: -0.1363876748 USDC/day.
- Blindtest: -0.0327853251 USDC/day.
- Target +3 USDC/day: not reached.

Family diagnosis:
- Best training family: breakout_volatility_filter.
- Best validation family: breakout_volatility_filter.
- Lowest-cost family: breakout_volatility_filter.
- Profit-factor-nearest-one family: cooldown_fee_aware.
- High-cost families: all six families.
- Overtrading families: mean_reversion_regime_filter, momentum_trend_filter, pullback_in_trend.
- Too-few-trades families: none.
- Problem assessment: costs_and_insufficient_edge.

Family aggregate highlights:
- breakout_volatility_filter: best validation -0.1363876748 USDC/day, average validation -0.4615362819, average cost load 197.949645143, best PF 0.424519183.
- cooldown_fee_aware: best validation -0.3658020743 USDC/day, average validation -0.6553294037, average cost load 338.3443250539, best PF 0.5651269724.
- pullback_in_trend: best validation -0.6476439022 USDC/day, average validation -1.2609972581, average cost load 609.4991328381, best PF 0.5573490765.

Comparison:
- Previous research blindtest: -0.0327853251 USDC/day.
- New research blindtest: -0.0327853251 USDC/day.
- Selected candidate and result did not change; stronger cost-filter candidates did not outrank breakout_volatility_filter_013 on validation.

Verification:
- Targeted family aggregate tests passed.
- Full `pytest tests/ -q` passed before real research run.
- Final full test rerun after handoff/docs is still required before commit.

Safety unchanged:
- No Binance Trading API.
- No API keys.
- No exchange client.
- No orders.
- No live/paper/testtrade folders or activation.
- BTCUSDC and ETHBTC remain context-only and cannot trigger trades.
