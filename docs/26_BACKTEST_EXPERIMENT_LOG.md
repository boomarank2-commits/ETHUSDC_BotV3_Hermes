# Backtest Experiment Log

## Prior baseline

Backtest report:
- `reports/backtests/bt_20260709T151036Z.json`
- `reports/backtests/bt_20260709T151036Z.txt`

Baseline result:
- Families: momentum, mean_reversion, breakout.
- Selected: breakout lookback 60 / threshold 10 bps / TP 120 bps / SL 80 bps / max hold 90 minutes.
- Training: -1.197560472 USDC/day.
- Validation: -1.5482525392 USDC/day.
- Blindtest: -1.3459078771 USDC/day.
- Target +3 USDC/day: not reached.
- Diagnosis: no reliable edge indicated; training and blindtest were both negative, profit factor < 1, winrate low, and costs/slippage were a major burden.

## Research run: research_20260709T170636Z

Report files:
- `reports/research/research_20260709T170636Z.json`
- `reports/research/research_20260709T170636Z.txt`
- `reports/research/index.jsonl`

Data:
- ETHUSDC 1m local ZIP/CHECKSUM data under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Data window: 2023-07-09 to 2026-07-07.
- Training: 2023-07-09 to 2025-07-07.
- Validation: last 20% of training, selection only.
- Blindtest: 2025-07-08 to 2026-07-07, final evaluation only.

Candidate generation:
- 6 families.
- 12 total candidates.
- Families:
  - momentum_trend_filter
  - breakout_volatility_filter
  - mean_reversion_regime_filter
  - pullback_in_trend
  - session_filter
  - cooldown_fee_aware

Selected candidate:
- family: breakout_volatility_filter
- params:
  - lookback: 120
  - threshold_bps: 10
  - volatility_lookback: 240
  - min_vol_bps: 10
  - max_vol_bps: 120
  - take_profit_bps: 140
  - stop_loss_bps: 90
  - max_hold_minutes: 180
  - cooldown_minutes: 90

Selection reason:
- Highest conservative validation rank using validation net/day, profit factor, drawdown, stability, trade frequency, and cost load.
- Blindtest was not used for ranking.

Results:
- Training net_usdc_per_day: -0.1171462622
- Validation net_usdc_per_day: -0.2452730967
- Blindtest net_usdc_per_day: -0.0674168068
- Blindtest net_profit_usdc: -24.60713449
- Blindtest trade_count: 106
- Blindtest profit_factor: 0.6548895154
- Blindtest max_drawdown_usdc: 26.2866075483
- Target +3 USDC/day: not reached.

Comparison to baseline:
- Baseline blindtest: -1.3459078771 USDC/day.
- Research run blindtest: -0.0674168068 USDC/day.
- Loss and overtrading were reduced substantially, but the strategy still did not show a positive enough edge.

Safety:
- No live.
- No paper.
- No testtrade.
- No orders.
- No Binance Trading API.
- No API keys.
