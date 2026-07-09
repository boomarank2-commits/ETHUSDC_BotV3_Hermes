# Next Action

Recommended next mini-ticket:
- Add report-level research diagnosis for `reports/research/research_20260709T170636Z.json` and use it to design the next training-only improvement.

Suggested next smallest safe step:
1. Read the new research report and compare candidate family behavior.
2. Add per-candidate result tables to the research report so failed families can be diagnosed, not only the selected candidate.
3. Investigate why validation remained negative and why the best candidate still had blindtest profit_factor < 1.
4. Add one controlled improvement at a time, for example:
   - better exit model,
   - lower-cost trade frequency rules,
   - volatility/session filter refinement,
   - context filter from BTCUSDC/ETHBTC that is past-only and cannot trigger trades.
5. Keep Blindtest final-only. Do not tune parameters from blindtest results.

UI next step:
- Wire the dashboard “Backtest / Strategie-Suche starten” button to run `ethusdc_bot.backtest.research_runner` in a background thread.
- Display real stages only: data gate, data load, feature prep, subtrain, validation, selection, blindtest, report written.
- Do not show fake progress or fake results.

Safety reminder:
- Live/Paper/Testtrade remain locked.
- Do not start trading/API/order functionality.
- No API keys.
