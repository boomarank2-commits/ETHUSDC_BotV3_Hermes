# Current Status

Status: Research reports now include a full per-candidate leaderboard, candidate diagnosis, and one controlled training-only strategy improvement.

Latest completed changes:
- Extended `src/ethusdc_bot/backtest/research_runner.py`:
  - full `candidate_leaderboard` for every candidate,
  - candidate_id, params, training metrics, validation metrics, rank score, rank position, ranking explanation, and weaknesses,
  - blindtest metrics only on the final selected leaderboard row,
  - `candidate_diagnosis` summary,
  - two controlled exit-improvement candidates using trailing-stop and break-even-stop parameters.
- Extended `src/ethusdc_bot/backtest/simulator.py`:
  - optional no-lookahead trailing stop based on prior closes only,
  - optional break-even stop after a favorable move, also prior-close based.
- Extended `src/ethusdc_bot/backtest/experiment_registry.py` text report output with leaderboard/diagnosis summary.
- Updated docs:
  - `docs/25_BACKTEST_RESEARCH_PROTOCOL.md`
  - `docs/26_BACKTEST_EXPERIMENT_LOG.md`
- Extended tests in:
  - `tests/unit/test_research_runner.py`
  - `tests/unit/test_experiment_registry.py`

Previous research run:
- `research_20260709T170636Z`
- Candidates: 12.
- Selected: breakout_volatility_filter.
- Training: -0.1171462622 USDC/day.
- Validation: -0.2452730967 USDC/day.
- Blindtest: -0.0674168068 USDC/day.
- Target +3 USDC/day: not reached.

New real research run:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Run-ID: `research_20260709T181800Z`.
- Reports:
  - `reports/research/research_20260709T181800Z.json`
  - `reports/research/research_20260709T181800Z.txt`
  - `reports/research/index.jsonl`
- Git commit recorded by report: `c940d77-dirty` because the run was executed before final commit.
- Candidates: 14.
- Families: 6.
- Selected candidate:
  - candidate_id: `breakout_volatility_filter_013`
  - family: breakout_volatility_filter
  - params: lookback 120, threshold 10 bps, volatility lookback 240, min/max volatility 12/110 bps, TP 160 bps, SL 90 bps, trailing stop 70 bps, break-even after 65 bps, max hold 180 min, cooldown 120 min.
- Training: -0.0722564539 USDC/day.
- Validation: -0.1363876748 USDC/day.
- Blindtest: -0.0327853251 USDC/day.
- Blindtest net profit: -11.9666436613 USDC.
- Blindtest trade count: 50.
- Blindtest profit factor: 0.5945557275.
- Blindtest max drawdown: 12.2184541211 USDC.
- Target +3 USDC/day: not reached.

Candidate diagnosis from leaderboard:
- Best training family: breakout_volatility_filter.
- Best validation family: breakout_volatility_filter.
- Lowest-cost family: breakout_volatility_filter.
- Negative validation candidates: 14/14.
- High-cost candidates: 14/14.
- Overtrading candidates: 3.
- Too-few-trades candidates: 0.
- Profit-factor-near-one families: none.
- Why not profitable enough: best validation candidate is still negative before blindtest; no sufficient edge shown.

Comparison:
- Previous research blindtest: -0.0674168068 USDC/day.
- New research blindtest: -0.0327853251 USDC/day.
- Result improved, but still negative and far below +3 USDC/day.

Verification:
- Targeted tests for leaderboard/registry passed.
- Full `pytest tests/ -q` passed before the real research run.
- Final full test rerun after handoff/docs is still required before commit.

Safety unchanged:
- No Binance Trading API.
- No API keys.
- No exchange client.
- No orders.
- No live/paper/testtrade folders or activation.
- BTCUSDC and ETHBTC remain context-only and cannot trigger trades.
