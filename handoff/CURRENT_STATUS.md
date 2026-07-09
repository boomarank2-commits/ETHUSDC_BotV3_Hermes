# Current Status

Status: Multi-cycle offline ETHUSDC research loop runner is implemented, tested, and executed.

Latest completed changes:
- Added `src/ethusdc_bot/backtest/research_loop_runner.py`:
  - CLI: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_loop_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --max-cycles 8 --max-candidates-per-cycle 40`.
  - Executes multiple deterministic research cycles instead of one isolated experiment.
  - Writes JSON/TXT/index reports under `reports/research_loop/`.
  - Stops on target reached, max cycles, validation stagnation, or safety violation.
- Added `src/ethusdc_bot/backtest/search_space.py`:
  - Deterministic bounded candidate generation.
  - Uses validation/diagnosis state only, not blindtest feedback.
  - Keeps `target_usdc_per_day` out of strategy parameters.
- Added `src/ethusdc_bot/backtest/walk_forward.py`:
  - Chronological walk-forward validation folds inside training.
  - Ranking helper marks blindtest as unused.
- Added `src/ethusdc_bot/backtest/exit_reason_analysis.py`:
  - Exit reason counts, net, fees, slippage, average trade, shares, cost load, loss-per-losing-trade.
- Extended `src/ethusdc_bot/backtest/simulator.py`:
  - Distinguishes `time_exit`, `take_profit`, `stop_loss`, `break_even`, `trailing_stop`, and `end_of_data` where applicable.
  - Supports `context_filter` only as an ETHUSDC base-strategy filter; context symbols cannot trigger trades.
- Added docs:
  - `docs/27_BACKTEST_RESEARCH_LOOP.md`
  - `docs/28_RESEARCH_LOOP_RESULTS.md`
- Added unit tests:
  - `tests/unit/test_research_loop_runner.py`
  - `tests/unit/test_search_space.py`
  - `tests/unit/test_exit_reason_analysis.py`
  - `tests/unit/test_walk_forward.py`

Real loop run:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_loop_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --max-cycles 8 --max-candidates-per-cycle 40`
- Loop run ID: `research_loop_20260709T213134Z`
- Reports:
  - `reports/research_loop/research_loop_20260709T213134Z.json`
  - `reports/research_loop/research_loop_20260709T213134Z.txt`
  - `reports/research_loop/index.jsonl`
- Cycles executed: 7 of 8.
- Generated candidate proposals: 77.
- Tested candidate frontier rows: 28.
- Stop reason: `validation_stagnation_3_cycles`.
- Target reached: false.
- Best validation candidate: `breakout_volatility_filter_04_001`.
- Best validation: `-0.0004208934 USDC/day`, PF `0.9184698895`, 8 validation trades.
- Best blindtest audit: `0.0096502748 USDC/day`, PF `1.7538949399`, 11 blindtest trades.
- Target `+3 USDC/day` not reached.

Verification:
- Targeted new tests passed.
- `pytest tests/ -q` passed before the real loop.
- Final `pytest tests/ -q` still required after handoff/docs before commit.

Safety unchanged:
- ETHUSDC only for trades.
- USDC quote.
- Binance Spot LONG-only simulation.
- 100 USDC simulated trade notional.
- No Binance Trading API.
- No API keys.
- No orders.
- No live/paper/testtrade unlock.
- BTCUSDC and ETHBTC remain context-only and cannot trigger trades.
