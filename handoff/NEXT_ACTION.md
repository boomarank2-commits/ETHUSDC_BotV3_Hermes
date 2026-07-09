# Next Action

Recommended next research ticket:
- Investigate why stricter breakout/cost controls approach breakeven validation but collapse to too few trades before producing sufficient edge.

Evidence from loop `research_loop_20260709T213134Z`:
- Best validation candidate: `breakout_volatility_filter_04_001`.
- Best validation: `-0.0004208934 USDC/day`, PF `0.9184698895`, only 8 validation trades.
- Best blindtest audit: `0.0096502748 USDC/day`, far below `+3 USDC/day` and audit-only.
- Later cycles reduced trades to 5, 3, then 2 validation trades.
- Cycle 7 exit analysis indicated stop-loss domination.

Suggested safe next step:
1. Do not tune from blindtest audit results.
2. Use training/validation/WFV evidence only.
3. Add a new controlled ETHUSDC-only entry class or filter that increases valid trade count without returning to high-cost overtrading.
4. Specifically compare:
   - stricter breakout thresholds with enough validation trades,
   - session/regime windows where breakout validation PF is closest to 1,
   - optional context filters using BTCUSDC/ETHBTC only as veto filters, never signal sources.
5. Keep all reports explicit about repeated blindtest audits.
6. Keep candidate adoption locked until a clean reproducible result exists.

Safety reminder:
- Live/Paper/Testtrade remain locked.
- Do not start trading/API/order functionality.
- No API keys.
