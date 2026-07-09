# Last Known Good

Last known safe state:
- Public local data gate is ready under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Dashboard data mode remains available:
  - `Daten prüfen & fehlende Daten laden` maps to execute=True.
  - `Nur prüfen ohne Download` maps to execute=False.
- Backtest state is represented separately from data mode.
- Local backtest runner exists and is CLI-startable:
  - `PYTHONPATH=src python -m ethusdc_bot.backtest.runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Runner completed a real local backtest and wrote:
  - `reports/backtests/bt_20260709T151036Z.json`
  - `reports/backtests/bt_20260709T151036Z.txt`

Last verified data counts, read-only:
- Total files: 6589.
- `.tmp/.part`: 0.
- 0-byte files: 0.
- ETHUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- BTCUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- ETHBTC 1m: 1096 ZIP / 1096 CHECKSUM / 1096 complete pairs.
- ETHUSDC aggTrades: 7 ZIP / 7 CHECKSUM / 7 complete pairs.
- ETHUSDC trades: 1 ZIP / 1 CHECKSUM / 1 complete pair.

Last verified backtest result:
- Data window: 2023-07-09..2026-07-07.
- Training: 2023-07-09..2025-07-07 (730 days).
- Blindtest: 2025-07-08..2026-07-07 (365 days).
- Selected family: breakout.
- Blindtest net result: -491.2563751241 USDC.
- Blindtest average: -1.3459078771 USDC/day.
- Target 3 USDC/day: not reached.

Verification:
- `pytest tests/ -q` passed after handoff update still needs final rerun before commit.

Safety:
- No live/paper/testtrade unlock.
- No orders.
- No API keys.
- No trading API.
- Reports are real backtest reports only and mark candidate_adoptable false.
