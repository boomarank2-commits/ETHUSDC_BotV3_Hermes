# Next Action

Recommended next mini-ticket:
- Improve strategy research after the first honest blindtest failed the 3 USDC/day target.
- Do not loosen gates or reuse blindtest for optimization.
- Analyze the new report first:
  - `reports/backtests/bt_20260709T151036Z.json`
  - `reports/backtests/bt_20260709T151036Z.txt`

Suggested next smallest safe step:
1. Add a report-diagnosis helper that reads completed backtest reports and summarizes why candidates failed.
2. Add one additional training-only strategy family or filter at a time.
3. Keep the blindtest untouched for final one-time evaluation after training/validation selection.
4. Preserve live/paper/testtrade locks.

UI next step:
- Wire the dashboard button to run the backtest runner in a background thread with progress updates.
- Keep data mode and backtest mode separate.
- Do not show fake progress or fake results.

Safety reminder:
- Live/Paper/Testtrade remain locked.
- Do not start trading/API/order functionality.
- No API keys.
