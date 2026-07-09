# Blockers

Current blockers:
- The first real strategy search did not reach the strategic target in the 365-day blindtest.
- Blindtest result from `bt_20260709T151036Z`: -1.3459078771 USDC/day, so target 3 USDC/day is not reached.
- Additional strategy development is needed, but must use training/validation only; no blindtest optimization.
- Exchange info remains unsupported by current public-data downloader path.
- BookTicker and orderbook snapshot tasks remain live-collector tasks and are not implemented in this UI workflow.
- Dashboard button is represented in state, but full background UI execution/progress wiring remains a next step.

Resolved blockers in this session:
- Backtest package now exists.
- Loader can read current Binance ZIP timestamp units after normalization.
- Train/blind split exists and is validated.
- A real local runner can execute and write honest reports.

Safety locks remain:
- Live locked.
- Paper locked.
- Testtrade locked.
- No trading API.
- No keys.
- No orders.
