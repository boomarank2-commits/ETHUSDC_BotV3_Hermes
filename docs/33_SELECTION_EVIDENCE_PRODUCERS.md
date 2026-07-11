# 33 - Selection evidence producers

Stand: 2026-07-11

This document defines the evidence that must be produced before a candidate can
pass `quality_gate_v1` selection. All evidence is derived exclusively from
training, validation and Walk-Forward data. The sealed holdout is not loaded,
read or evaluated by these producers.

## Required evidence groups

### Rolling robustness

- mark-to-market maximum drawdown;
- maximum underwater calendar days;
- share of all positive trade P&L contributed by the best trade;
- share contributed by the best five trades;
- net P&L and profit factor after removing the five best positive trades.

### Cost stress

The same frozen candidate is evaluated with:

- baseline: 10 bps fee and 5 bps slippage per side;
- joint stress: 15 bps fee and 10 bps slippage per side;
- slippage stress: 10 bps fee and 15 bps slippage per side.

The report also states friction as a share of positive pre-cost P&L. Stress
profiles are fixed before evaluation and must never be adapted to results.

### Parameter stability

Every numeric strategy parameter that can be safely perturbed is tested at the
fixed ex-ante neighbourhood:

- minus 10 percent;
- plus 10 percent;
- session-hour parameters additionally move by exactly one hour.

Structural values such as symbol, side and booleans are not treated as numeric
search parameters. Integer parameters remain valid integers and all neighbours
are canonicalized and deduplicated.

### Temporal stability

Trades are grouped by UTC entry month and quarter. Evidence includes:

- observed, active and positive months;
- maximum gap between trade-entry dates;
- observed and positive quarters;
- minimum trades in any observed quarter;
- worst monthly net P&L.

The observation calendar comes from the evaluated validation/WFV period, so
months without trades remain visible instead of disappearing from the result.

### Regime stability

Four regimes are formed from two training-only thresholds:

- trailing trend sign at entry;
- trailing volatility below/above the training median.

Assignment uses only data available strictly before or at each trade entry.
BTCUSDC and ETHBTC are not introduced by this PR. The regime producer operates
on ETHUSDC candles only and cannot trigger trades or orders.

## Integrity rules

- no audit or sealed-holdout input;
- deterministic output for identical inputs;
- explicit UTC windows and provenance;
- no missing evidence replaced with optimistic defaults;
- no threshold changes based on observed performance;
- fixed 100-USDC canonical research notional;
- no Live, Paper, Testtrade, order, key or account capability.
