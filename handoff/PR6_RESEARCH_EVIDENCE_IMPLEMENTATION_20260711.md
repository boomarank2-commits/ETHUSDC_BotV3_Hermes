# PR #6 - Complete selection evidence implementation

Stand: 2026-07-11

## Branch and base

- Branch: `review/research-evidence-producers-v1`
- Base: `review/pr4-final-alignment`
- Last fully tested implementation commit before this handoff: `85a6efe05f8ad4f154120bdf88e61b634946b9f1`
- Pull request: #6

## Problem corrected

`quality_gate_v1` required complete evidence for rolling robustness, fixed cost
stress, parameter stability, temporal stability and regime stability. The
production research loop previously emitted no usable evidence for these
sections, so a real finalist could not receive a complete selection decision
regardless of its P&L.

## Implemented producers

### Rolling robustness

The Walk-Forward validation folds now produce:

- chained mark-to-market maximum drawdown;
- maximum underwater calendar days;
- best-one and best-five positive-trade concentration;
- net P&L and profit factor after removing the five best positive trades.

### Fixed friction stress

Every finalist is re-evaluated on the same chronological WFV folds with fixed,
predeclared profiles:

- baseline: 10 bps fee + 5 bps slippage per side;
- joint stress: 15 bps fee + 10 bps slippage per side;
- slippage stress: 10 bps fee + 15 bps slippage per side.

No stress threshold or profile is changed in response to results.

### Parameter stability

Every numeric strategy parameter receives deterministic minus/plus neighbours:

- normally minus/plus 10 percent;
- session hours minus/plus one hour;
- integer and strictly-positive constraints remain valid;
- symbol, side, base family and context identifiers are excluded as structural
  values;
- canonical duplicates are removed;
- at most 12 numeric parameters per finalist are evaluated. More complex
  candidates fail the completeness gate instead of silently exceeding the
  declared resource budget.

Parameter neighbours are evaluated on internal validation data only.

### Temporal stability

Chronological WFV trades are grouped over the complete observation calendar,
including inactive periods:

- observed, active and positive months;
- observed and positive quarters;
- minimum quarterly trade count;
- maximum no-trade gap;
- worst monthly net result.

### Regime stability

Four entry-time ETHUSDC regimes are built per fold from training-only
thresholds:

- up/low volatility;
- up/high volatility;
- down/low volatility;
- down/high volatility.

Trade assignment uses only trailing data available at entry. No BTCUSDC or
ETHBTC context is claimed or simulated by this PR.

## Research-loop integration

The production research loop now places the generated evidence directly into
the exact field paths consumed by `quality_gate_v1`:

- `rolling`
- `stress`
- `parameter_stability`
- `temporal`
- `regime`

Provenance is recorded as selection-only. The research loop still does not load
or evaluate the sealed holdout.

## Resource accounting

The report now separates:

- normal selection candidate-days;
- stress-evidence candidate-days;
- parameter-neighbour candidate-days;
- total candidate-days and candle evaluations;
- maximum numeric parameters per finalist.

For the production defaults the declared per-cycle caps are:

- stress evidence: 2,920 candidate-days;
- parameter evidence: 7,008 candidate-days;
- total selection work: 24,528 candidate-days.

This is intentionally conservative and explicit. The added work is not hidden
inside the original candidate count.

## Zero-mean WFV correction

Both the WFV producer and the independent quality-gate recalculation now use the
same semantics:

- identical zero-valued folds -> coefficient of variation `0.0`;
- non-identical folds with mean zero -> coefficient undefined and fail-closed;
- fewer than two folds -> coefficient undefined.

## Fixture behavior

The six-day monotonic smoke fixture deliberately produces no closed wins or
losses. It now demonstrates that:

- no required producer evidence is missing;
- undefined profit-factor evidence remains invalid and fails closed;
- no holdout candle is evaluated.

A degenerate no-trade fixture is therefore never promoted into apparently valid
performance evidence.

## Automated verification

GitHub Actions, Ubuntu 24.04, Python 3.12:

- 767 tests passed;
- `python -m compileall -q src` passed;
- committed whitespace check passed.

## Safety status

Unchanged and locked:

- Live;
- Paper;
- Testtrade;
- real orders;
- account access;
- API keys and private endpoints;
- shorts;
- margin;
- futures;
- leverage.

## Remaining work

The evidence architecture is now complete enough for a real local production
research run. The next separate PR must improve the existing deterministic
ETHUSDC search frontier because the nominal 40-candidate budget currently
produces only about 11 candidates and still includes two pseudo-context
candidates that do not consume real context-market data.

No claim of 3 USDC/day is made by this PR. That value requires a new local run
against the real selection data with the corrected pipeline.
