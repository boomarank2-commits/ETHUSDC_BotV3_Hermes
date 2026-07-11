# Research Quality Gates V1

## Purpose

`quality_gate_v1` is a fixed, fail-closed evidence contract for offline
ETHUSDC research.  Its thresholds are defined before a sealed holdout is
opened.  They must not be changed in response to validation, audit, or
holdout results.

The implementation is a pure evaluator in
`src/ethusdc_bot/backtest/quality_gates.py`.  It does not load market data,
run a strategy, inspect reports, select candidates, create orders, or unlock
live, paper, or testtrade modes.

## Stages

### `selection`

Consumes training/validation-only evidence.  Passing means that a frozen
candidate is eligible for exactly one sealed-holdout evaluation.  It does not
make the candidate adoptable.

### `final`

Re-evaluates the frozen selection evidence and additionally requires the
single sealed-holdout result.  Passing may mark the candidate as ready for a
separate human adoption decision.  It never marks live trading ready.

The serialized report always contains:

- every individual check and its actual/expected value;
- sorted missing and invalid evidence paths;
- the complete immutable threshold set;
- research-evidence, sealed-holdout, and candidate-adoption readiness;
- explicit live/paper/testtrade locks.

Any missing, null, non-numeric, non-finite, or structurally invalid required
value fails closed.  Insufficient observations are failures, not zero-valued
successes.  Selection-phase missing and invalid paths are tracked directly;
`research_evidence_complete` cannot become true because a structural error
was reported by a composite check with different wording.

## Fixed thresholds

### Validation and walk-forward validation

- validation: at least 50 trades, positive net USDC/day, PF at least 1.10,
  drawdown no more than 15 USDC;
- exactly 6 chronological WFV folds;
- every fold covers at least 60 days and 30 closed trades;
- at least 180 WFV trades in total;
- aggregate WFV net USDC/day positive and PF at least 1.20;
- at least 5/6 folds positive and at least 5/6 with PF at least 1.05;
- worst fold PF at least 0.90 and net USDC/day at least -0.10;
- median fold net USDC/day positive;
- fold-net coefficient of variation no more than 1.0;
- aggregate WFV net/day retains at least 60% of positive full-training
  net/day;
- WFV drawdown no more than 15 USDC.

WFV evidence must cover the actual reported fold duration.  A sampled candle
slice must not be divided by the duration of a larger unsimulated window.
The evaluator independently derives total trades, total net P&L,
day-weighted net USDC/day, aggregate profit factor, chained mark-to-market
drawdown, positive-fold count, PF-at-least-1.05 count, worst fold PF, median
and worst fold net/day, and fold-net coefficient of variation from
`wfv.folds[]`.
Every corresponding `wfv.aggregate` value must match the derived value.
Each fold must therefore include numeric `days`, `trade_count`,
`net_profit_usdc`, `net_usdc_per_day`, `profit_factor`,
`gross_profit_usdc`, `gross_loss_usdc`, and `max_drawdown_usdc`. It must also
include `drawdown_method: mark_to_market` and a chronological
`equity_curve_usdc` starting at zero and ending at the fold net P&L. The
evaluator checks fold net/day, gross-profit/loss PF, fold drawdown, aggregate
PF, and chained aggregate drawdown against those proofs. Missing curves in
the current simulator therefore fail closed; they are never fabricated from
closed trades.

### Drawdown and profit concentration

- drawdown no more than 15 USDC;
- longest underwater period no more than 60 days;
- largest winning trade no more than 10% of total positive trade P&L;
- five largest winning trades no more than 35% of total positive trade P&L;
- after removing the top five winners, net P&L remains positive and PF is at
  least 1.05.

These values require a complete trade ledger and a chronological,
mark-to-market equity curve.  Closed-trade-only drawdown is not equivalent.
Every section whose drawdown is evaluated (`validation`, `wfv.aggregate`,
`rolling`, `stress.joint`, and, at final stage, `final`) must explicitly carry
`drawdown_method: mark_to_market`.  A missing method or `closed_trade` fails
closed even when the numeric drawdown is below its limit.

### Execution costs and stress

The mandatory baseline is:

- fee: 10 bps per side;
- slippage: 5 bps per side.

The fixed stress cases are:

1. joint stress: 15 bps fee and 10 bps slippage per side;
2. slippage stress: 10 bps fee and 15 bps slippage per side.

Joint stress must remain net positive, retain at least 50% of baseline
net/day, have PF at least 1.10, and drawdown no more than 20 USDC.  Slippage
stress must remain net positive with PF at least 1.05.  Baseline friction
(fees plus slippage) must not exceed 40% of positive pre-cost P&L.

Slippage is already embedded in execution prices.  The evidence producer
must not subtract it a second time when calculating net P&L.

### Parameter stability

- every numeric strategy parameter is tested one-at-a-time at -10% and +10%;
- integer parameters use deterministic rounding with a minimum one-unit step;
- session hours use a one-hour step;
- evidence must contain at least two neighbors per numeric parameter;
- at least 80% of neighbors pass their profitability/PF eligibility check;
- median neighbor net/day retains at least 75% of the center result;
- worst neighbor net/day is at least -0.10 USDC.

Categorical parameters are not silently treated as numeric.  Their allowed
alternatives must be declared separately by the evidence producer.

### Temporal robustness

- at least 12 observed months and at least 4 observed quarters;
- at least 75% of every reported month window positive;
- at least 10/12 (83.33%) of every reported month window active;
- 100% of all reported quarters positive;
- at least 20 trades in every quarter;
- no no-trade gap longer than 30 days;
- worst calendar month no worse than -5 USDC.

The percentage rules scale with windows longer than 12 months or 4 quarters;
the evaluator never truncates a longer evidence window merely to satisfy the
minimum.  Trades are assigned consistently by exit timestamp for P&L
aggregation.

### Regime robustness

The fixed regime definition is the Cartesian product of:

- trailing 30-day ETHUSDC return sign at entry; and
- realized volatility above/below the median learned only from training.

This produces four regimes.  Regime assignment uses only trailing data known
at entry time.  Required evidence is:

- all four regimes represented;
- at least 20 trades per regime;
- at least three regimes net positive and with PF at least 1.05;
- worst regime PF at least 0.90 and net P&L at least -5 USDC;
- no regime contributes more than 60% of total positive P&L.

### Final sealed holdout

- exactly one sealed-holdout evaluation;
- at least 120 trades;
- net result at least 3.00 USDC/day;
- PF at least 1.25;
- average trade positive;
- drawdown no more than 15 USDC.

The candidate, parameter set, quality-gate version, evidence algorithms, and
cost scenarios must be frozen before this evaluation.

## Evidence structure

The evaluator accepts a mapping with these required sections:

```text
protocol
validation
wfv.fold_count
wfv.folds[]
wfv.aggregate
rolling
stress.baseline
stress.joint
stress.slippage
parameter_stability
temporal
regime
final                 # required only for stage=final
```

`protocol.selection_uses_audit` must be false,
`protocol.gate_frozen_before_evaluation` must be true, and
`protocol.gate_version` must equal `quality_gate_v1`.

At selection, rolling/temporal/regime evidence is calculated from
out-of-sample training-only/WFV trades.  At final, those same aggregations
must be produced from the one sealed-holdout run without opening additional
holdout evaluations.  Parameter and cost-stress selection evidence remains
frozen.

## Current integration boundary

The evaluator intentionally does not synthesize absent evidence.  Existing
aggregate metrics provide net P&L, net/day, trade count, PF, fees, slippage,
winrate, and closed-trade drawdown.  Complete concentration, temporal,
underwater, regime, parameter-neighborhood, cost-stress, and mark-to-market
evidence still has to be generated by dedicated research/reporting code.

Until those inputs exist and pass, the report remains fail-closed and the
sealed holdout, candidate adoption, paper, testtrade, and live stages remain
blocked.
