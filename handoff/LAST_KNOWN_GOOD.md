# Last Known Good

Last known safe state:
- Public local data gate is ready under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Dashboard data mode remains available:
  - `Daten prüfen & fehlende Daten laden` maps to execute=True.
  - `Nur prüfen ohne Download` maps to execute=False.
- Backtest state is represented separately from data mode.
- Local baseline backtest runner exists:
  - `PYTHONPATH=src python -m ethusdc_bot.backtest.runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Local single-run research runner exists:
  - `PYTHONPATH=src python -m ethusdc_bot.backtest.research_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Local multi-cycle research loop runner exists:
  - `PYTHONPATH=src python -m ethusdc_bot.backtest.research_loop_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --max-cycles 8 --max-candidates-per-cycle 40`

Last verified data counts, read-only from previous data gate:
- Total files: 6589.
- `.tmp/.part`: 0.
- 0-byte files: 0.
- ETHUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- BTCUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- ETHBTC 1m: 1096 ZIP / 1096 CHECKSUM / 1096 complete pairs.
- ETHUSDC aggTrades: 7 ZIP / 7 CHECKSUM / 7 complete pairs.
- ETHUSDC trades: 1 ZIP / 1 complete pair.

Latest single-run research:
- Report: `reports/research/research_20260709T193221Z.json` and `.txt`.
- Tested 16 candidates across 6 families.
- Selected candidate: `breakout_volatility_filter_013`.
- Training: `-0.0722564539 USDC/day`.
- Validation: `-0.1363876748 USDC/day`.
- Blindtest: `-0.0327853251 USDC/day`.
- Target +3 USDC/day: not reached.
- Family diagnosis: best validation and lowest cost family are breakout_volatility_filter; all families are high-cost; problem assessment is costs_and_insufficient_edge.

Latest multi-cycle research loop:
- Report: `reports/research_loop/research_loop_20260709T213134Z.json` and `.txt`.
- Index: `reports/research_loop/index.jsonl`.
- Cycles executed: 7 of 8.
- Generated candidate proposals: 77.
- Tested candidate frontier rows: 28.
- Stop reason: `validation_stagnation_3_cycles`.
- Best validation candidate: `breakout_volatility_filter_04_001`.
- Best validation: `-0.0004208934 USDC/day`, PF `0.9184698895`, 8 trades.
- Best blindtest audit: `0.0096502748 USDC/day`, PF `1.7538949399`, 11 trades.
- Target +3 USDC/day: not reached.
- Blindtest audit is marked repeated/audit-only and not used for search-space adjustment.

Verification:
- `pytest tests/ -q` passed before real loop.
- Final rerun required before commit.

Safety:
- No live/paper/testtrade unlock.
- No orders.
- No API keys.
- No trading API.
- BTCUSDC/ETHBTC context remains non-trading.
