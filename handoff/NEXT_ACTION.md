# Next Action

Recommended next mini-ticket:
- Use the new per-candidate leaderboard from `reports/research/research_20260709T181800Z.json` to diagnose why every candidate still has negative validation and high cost load.

Suggested safe next step:
1. Add a compact family-level aggregate table to the research report:
   - average validation net/day per family,
   - best validation candidate per family,
   - average cost load per family,
   - average trade count per family,
   - best/worst drawdown per family.
2. Use only training/validation for diagnosis and changes.
3. Investigate whether costs dominate because:
   - entry threshold is too low,
   - exits cut winners too early,
   - simulated slippage assumptions are too punitive for small moves,
   - market edge is absent in simple OHLCV-only rules.
4. Add at most one controlled next improvement, likely one of:
   - stronger minimum expected move filter,
   - trend/session regime filter refinement,
   - context filter from BTCUSDC/ETHBTC that remains past-only and cannot trigger trades,
   - alternative exit that lets winners run while keeping drawdown bounded.
5. Keep blindtest final-only. Do not tune from blindtest.

Safety reminder:
- Live/Paper/Testtrade remain locked.
- Do not start trading/API/order functionality.
- No API keys.
