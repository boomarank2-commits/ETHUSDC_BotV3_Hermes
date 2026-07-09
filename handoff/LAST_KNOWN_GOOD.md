# Last Known Good

Last known safe state:
- Public local data gate is ready under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Dashboard data mode remains available:
  - `Daten prüfen & fehlende Daten laden` maps to execute=True.
  - `Nur prüfen ohne Download` maps to execute=False.
- Backtest state is represented separately from data mode.
- Local baseline backtest runner exists:
  - `PYTHONPATH=src python -m ethusdc_bot.backtest.runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Local research runner exists:
  - `PYTHONPATH=src python -m ethusdc_bot.backtest.research_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`

Last verified data counts, read-only from previous data gate:
- Total files: 6589.
- `.tmp/.part`: 0.
- 0-byte files: 0.
- ETHUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- BTCUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- ETHBTC 1m: 1096 ZIP / 1096 CHECKSUM / 1096 complete pairs.
- ETHUSDC aggTrades: 7 ZIP / 7 CHECKSUM / 7 complete pairs.
- ETHUSDC trades: 1 ZIP / 1 CHECKSUM / 1 complete pair.

Last baseline backtest:
- Report: `reports/backtests/bt_20260709T151036Z.json` and `.txt`.
- Training: -1.197560472 USDC/day.
- Blindtest: -1.3459078771 USDC/day.
- Target +3 USDC/day: not reached.

Research run before this session:
- Report: `reports/research/research_20260709T181800Z.json` and `.txt`.
- Tested 14 candidates across 6 families.
- Selected candidate: `breakout_volatility_filter_013`.
- Training: -0.0722564539 USDC/day.
- Validation: -0.1363876748 USDC/day.
- Blindtest: -0.0327853251 USDC/day.
- Target +3 USDC/day: not reached.

Latest research run:
- Report: `reports/research/research_20260709T193221Z.json` and `.txt`.
- Index: `reports/research/index.jsonl`.
- Tested 16 candidates across 6 families.
- Report contains `candidate_leaderboard`, `candidate_diagnosis`, `family_aggregates`, and `family_diagnosis`.
- Selected candidate remained: `breakout_volatility_filter_013`.
- Training: -0.0722564539 USDC/day.
- Validation: -0.1363876748 USDC/day.
- Blindtest: -0.0327853251 USDC/day.
- Target +3 USDC/day: not reached.
- Family diagnosis: best validation and lowest cost family are breakout_volatility_filter; all families are high-cost; problem assessment is costs_and_insufficient_edge.

Verification:
- Targeted family aggregate tests passed.
- `pytest tests/ -q` passed before real research run.
- Final rerun required before commit.

Safety:
- No live/paper/testtrade unlock.
- No orders.
- No API keys.
- No trading API.
- BTCUSDC/ETHBTC context remains non-trading.
