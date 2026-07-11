# Backtest Research Loop v2

The Protocol-v2 runner is the only active strategy-research entrypoint. It performs bounded, deterministic selection using training-only evidence and never evaluates the current final holdout.

## Reported stages

Every cycle records:

- actual and configured generated-candidate counts;
- tested candidates and any explicit non-testing reason;
- WFV candidates and all fold boundaries;
- finalists;
- exact candidate IDs at every nested stage;
- validation, WFV, historical-window, exit-reason, family, and fail-closed quality-gate summaries.

Default caps are 40 generated, 12 tested, 3 WFV, and 2 finalists. The current generator normally emits fewer than 40, so the report states the actual generated count. Supported candidates within the tested cap are all evaluated.

## Holdout policy

- The previously viewed 365-day window is consumed.
- Holdout candles are never passed to `simulate_strategy` by this runner.
- Holdout metadata may be recorded to prove boundaries and consumed/sealed status.
- No cycle contains `blindtest_audit`, `blindtest_metrics`, `audit_result`, or holdout-result payloads.
- A report cannot claim `+3 USDC/day` or `target_reached=true` without a separate future sealed-holdout workflow.

## Stops

- `max_cycles_reached`;
- `selection_stagnation_3_cycles`;
- `safety_violation`;
- explicit runtime/test failure.

There is no target-based stop inside research because the target is a final sealed-holdout criterion.

## Reproducibility and safety

- Window endpoint: latest complete UTC day, never a fixed year.
- Production completeness: exactly 1,440 contiguous one-minute candles per accepted UTC day.
- Consumed ledger: every selection-bearing window is checked before simulation and overlap fails closed.
- Candidate preselection: deterministic family round-robin only when a cap is necessary.
- WFV: six chronological folds using actual simulated calendar days.
- Historical origins: fully before the latest holdout; zero reported honestly when history is insufficient.
- Quality gate: immutable `quality_gate_v1`, missing evidence fails closed.
- Candidate identity: any passing gate is bound to the selected finalist ID and canonical parameter signature before freeze.
- Resource ceiling: configured stage caps plus an explicit candidate-day/candle-evaluation cap are enforced before work starts.
- Total adaptation ceiling: no more than eight cycles; production uses exactly 40/12/3/2 configured stage budgets, six WFV folds, and up to three 365-day historical origins.
- Trade model: ETHUSDC/USDC Spot LONG-only, fixed 100 USDC notional, one position, no compounding.
- Costs: 0.1% fee and 5 bps slippage per side.
- Live, Paper, and Testtrade stay locked; no orders, APIs, keys, account access, margin, futures, leverage, or shorts.

Reports remain under `reports/research_loop/` with append-only `index.jsonl`. Historical schema-v1 reports are retained and not rewritten.

`--fixture-smoke` reports are labelled `fixture_smoke_non_production`; their intentionally small split can verify the execution path but is never quality-gate or production evidence.

Custom cycle runners are accepted only in the fixture/test profile. Fixture reports always use `fixture_nonproduction_no_freeze`, even if synthetic evidence satisfies numerical gates.

The current simulator exposes closed-trade drawdown only. Because `quality_gate_v1` requires mark-to-market drawdown plus additional robustness producers, real selection reports remain fail-closed and cannot freeze a candidate until those evidence producers exist.
