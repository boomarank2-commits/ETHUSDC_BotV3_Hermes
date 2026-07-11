# 34 - ETHUSDC Search Frontier v2

Stand: 2026-07-11

## Problem

The production loop declares a generated-candidate cap of 40 and a tested cap
of 12, but the prior generator normally produced only about 11 unique
candidates. Two of those were labelled `context_filter` even though the current
simulator receives only ETHUSDC candles and therefore replays the ETHUSDC base
strategy without evaluating BTCUSDC or ETHBTC.

This wastes declared capacity and can present pseudo-context variants as if
context evidence existed.

## Frontier v2 contract

The active frontier uses only strategy families already implemented by the
ETHUSDC simulator:

- `breakout_volatility_filter`
- `cooldown_fee_aware`
- `momentum_trend_filter`
- `pullback_in_trend`
- `mean_reversion_regime_filter`
- `session_filter`

Candidates are generated in deterministic rounds. Each round contributes one
variant from every family before another round is added. This ensures that a
bounded family-balanced testing frontier sees every active family before it
receives second variants.

The parameter levels are fixed ex ante and are adjusted only by the existing
validation diagnosis pressure:

- cost/overtrading pressure raises entry thresholds, minimum expected move and
  cooldown;
- too-few-trades pressure opens thresholds and cooldown conservatively;
- no audit, holdout or target result is used;
- the desired 3-USDC/day value is not a candidate parameter.

## Context policy

`context_filter` is excluded from active candidate generation until the research
engine actually consumes aligned BTCUSDC or ETHBTC market data. This is not a
rejection of context trading research. It prevents duplicate ETHUSDC signals
from being mislabelled as context-tested evidence.

BTCUSDC and ETHBTC remain context-only and can never be traded or submit orders.
A later dedicated context PR must provide aligned data, trailing-only context
features and explicit provenance before context candidates return.

## Capacity and transparency

- requested generated cap: up to 40;
- production tested cap remains 12;
- WFV and finalist caps remain unchanged;
- duplicate canonical signatures are removed;
- report metadata states generator version, requested cap, actual count, family
  counts, context status and holdout exclusion.

## Safety

No change enables Live, Paper, Testtrade, orders, private endpoints, account
access, keys, shorts, margin, futures or leverage. Costs, fixed 100-USDC research
notional, quality gates and holdout policy remain unchanged.
