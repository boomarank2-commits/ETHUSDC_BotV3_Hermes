# Current Status

Status: Reproducible offline ETHUSDC strategy-research runner is implemented and exercised.

Latest completed changes:
- Added report diagnosis helper: `src/ethusdc_bot/backtest/report_diagnosis.py`.
- Added research protocol guardrails: `src/ethusdc_bot/backtest/research_protocol.py`.
- Added append-only experiment registry: `src/ethusdc_bot/backtest/experiment_registry.py`.
- Added no-lookahead feature generation: `src/ethusdc_bot/backtest/features.py`.
- Added context helpers for BTCUSDC/ETHBTC safety: `src/ethusdc_bot/backtest/context_loader.py`.
- Added CLI research runner: `src/ethusdc_bot/backtest/research_runner.py`.
- Extended simulator with controlled research families and cooldown/session/volatility/trend filters.
- Added docs:
  - `docs/25_BACKTEST_RESEARCH_PROTOCOL.md`
  - `docs/26_BACKTEST_EXPERIMENT_LOG.md`

Baseline diagnosis:
- Source report: `reports/backtests/bt_20260709T151036Z.json` / `.txt`.
- Target was not reached.
- Training was negative.
- Blindtest was negative.
- Profit factor was below 1.
- Winrate was low.
- Fee/slippage load was high.
- Overtrading was suspected.
- Drawdown was high.
- Diagnosis: no reliable edge indicated for the tested baseline candidate.

Real research run executed:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Research run_id: `research_20260709T170636Z`.
- Report files:
  - `reports/research/research_20260709T170636Z.json`
  - `reports/research/research_20260709T170636Z.txt`
  - `reports/research/index.jsonl`
- Git commit recorded by report: `7cf9940-dirty` because the requested research run was executed before the final session commit.
- Data window: 2023-07-09..2026-07-07.
- Training: 2023-07-09..2025-07-07.
- Validation: last 20% of training, selection only.
- Blindtest: 2025-07-08..2026-07-07, final evaluation only.
- Strategy families tested: momentum_trend_filter, breakout_volatility_filter, mean_reversion_regime_filter, pullback_in_trend, session_filter, cooldown_fee_aware.
- Candidates tested: 12.
- Selected candidate: breakout_volatility_filter, lookback 120, threshold 10 bps, volatility lookback 240, min/max volatility 10/120 bps, TP 140 bps, SL 90 bps, max hold 180 min, cooldown 90 min.
- Selection reason: highest conservative validation rank using validation net/day, profit factor, drawdown, stability, trade frequency, and cost load; blindtest not used.
- Training net_usdc_per_day: -0.1171462622.
- Validation net_usdc_per_day: -0.2452730967.
- Blindtest net_usdc_per_day: -0.0674168068.
- Blindtest net_profit_usdc: -24.60713449.
- Target +3 USDC/day: not reached.

Comparison to previous baseline:
- Previous blindtest: -1.3459078771 USDC/day.
- Research run blindtest: -0.0674168068 USDC/day.
- Loss, drawdown, and overtrading were reduced, but no sufficient positive edge was found.

Verification:
- Pre-change `pytest tests/ -q` passed.
- New tests were written first and failed on missing modules.
- Targeted tests passed after implementation.
- Full `pytest tests/ -q` passed before real research run.
- Full test rerun after handoff update still required before commit.

Safety unchanged:
- No Binance Trading API.
- No API keys.
- No exchange client.
- No orders.
- No live/paper/testtrade folders or activation.
- BTCUSDC and ETHBTC remain context-only and cannot trigger trades.
