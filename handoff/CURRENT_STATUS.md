# Current Status

Status: First real local ETHUSDC backtest foundation has been implemented and exercised.

Latest completed changes:
- Added `src/ethusdc_bot/backtest/` package:
  - read-only ETHUSDC 1m ZIP/CHECKSUM data loader,
  - 730/365 train/blind split,
  - conservative Binance Spot LONG-only simulator,
  - metrics,
  - small deterministic strategy search,
  - honest JSON/TXT reporting,
  - `python -m ethusdc_bot.backtest.runner` CLI runner.
- Added TDD/unit/integration coverage for loader, split, simulator, strategy search, metrics, reporting, runner smoke, safety, and UI backtest-mode state.
- Updated dashboard state model so a local backtest/strategy-search button can be represented separately from data-prep mode.
- Added `docs/24_BACKTEST_ENGINE_AND_STRATEGY_SEARCH.md`.

Read-only local data state observed under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes` before implementation:
- Root exists: yes.
- `START_DASHBOARD.bat` exists: yes.
- Total files: 6589.
- `.tmp`: 0.
- `.part`: 0.
- 0-byte files: 0.
- Data readiness: ready / data gate true.
- ETHUSDC 1m: 1095/1095 current, latest 2026-07-07.
- BTCUSDC 1m: 1095/1095 current, latest 2026-07-07.
- ETHBTC 1m: 1096/1095 current, latest 2026-07-08.
- ETHUSDC aggTrades: 7/7 current, latest 2026-07-08.
- ETHUSDC trades: 1/1 current, latest 2026-07-08.
- ZIP/CHECKSUM pairs matched for all observed public sources.
- Backtest window from readiness: data 2023-07-09..2026-07-07, training 2023-07-09..2025-07-07, blindtest 2025-07-08..2026-07-07.

Real backtest run executed:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Candles loaded: 1,576,800.
- Split: 730 training days / 365 blindtest days.
- Strategy families tested: momentum, mean_reversion, breakout.
- Selected candidate from training/validation only: breakout, lookback 60, threshold 10 bps, TP 120 bps, SL 80 bps, max hold 90 minutes.
- Blindtest result: -491.2563751241 USDC total, -1.3459078771 USDC/day, 1623 trades.
- Target 3 USDC/day: not reached.
- Report: `reports/backtests/bt_20260709T151036Z.json` and `.txt`.

Verification:
- Initial clean check: `git status --short` was clean.
- Pre-change full suite: `pytest tests/ -q` passed.
- RED: new tests failed with missing `ethusdc_bot.backtest` package.
- Targeted green tests passed.
- Real CLI runner passed after timestamp-unit normalization.
- Final `pytest tests/ -q` passed.

Safety unchanged:
- No Binance Trading API.
- No API keys.
- No exchange client.
- No orders.
- No live/paper/testtrade folders or activation.
- BTCUSDC and ETHBTC remain context-only and cannot trigger simulated ETHUSDC orders.
- Backtest report explicitly keeps live/paper/testtrade locked and candidate_adoptable false.
