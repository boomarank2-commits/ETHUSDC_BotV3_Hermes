# Next Action

Recommended next mini-ticket:
- Use `reports/research/research_20260709T193221Z.json` family aggregates to investigate why all families remain high-cost and negative in validation.

Suggested safe next step:
1. Add a per-family/candidate exit-reason summary if trade logs are stored or derivable without bloating reports.
2. Diagnose whether losses come mainly from:
   - stop losses,
   - time exits,
   - trailing/break-even exits,
   - immediate cost/slippage drag.
3. If adding one next improvement, prefer a training/validation-only idea based on exit-reason evidence, not blindtest:
   - reduce bad entries if most exits are stops,
   - refine time/session regime if many time exits leak losses,
   - consider context filter only as ETHUSDC-signal filter, never trade trigger.
4. Keep candidate space small and explainable.
5. Keep blindtest final-only. Do not tune from blindtest.

Safety reminder:
- Live/Paper/Testtrade remain locked.
- Do not start trading/API/order functionality.
- No API keys.
