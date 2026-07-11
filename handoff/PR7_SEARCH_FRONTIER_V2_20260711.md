# PR #7 - ETHUSDC Search Frontier v2

Stand: 2026-07-11

## Branch

- Branch: `review/search-frontier-v2`
- Base: `review/research-evidence-producers-v1`
- Last fully tested implementation commit before this handoff: `5f86500f38fd4a7817af004661f781a71bf5b949`
- Pull request: #7

## Corrected problem

The configured production budget allowed 40 generated and 12 tested
candidates, but the prior generator normally produced only about 11 unique
candidates. Two were labelled `context_filter` despite the simulator receiving
only ETHUSDC candles, so they repeated base ETHUSDC logic without real BTCUSDC
or ETHBTC context.

## New deterministic frontier

Seven predeclared profile rounds use six existing simulator-backed ETHUSDC
families:

- breakout volatility filter;
- fee-aware cooldown;
- momentum trend filter;
- pullback in trend;
- mean-reversion regime filter;
- session filter.

Each round contributes one variant per family before the next round begins.
Canonical signatures are deduplicated and the requested cap is applied only
after normalization.

Production behavior:

- requested/generated: 40/40;
- tested: 12;
- first testing round: one candidate per family;
- second testing round: one additional candidate per family;
- WFV/finalist budgets remain 3/2.

## Diagnosis behavior

The existing validation-only diagnosis remains the only adaptive input:

- cost/overtrading pressure raises thresholds, expected move and cooldown;
- stop-loss pressure adds conservative strictness;
- too-few-trades pressure opens thresholds and cooldown;
- pressure is capped to prevent runaway parameters across repeated cycles.

No target, audit or holdout result enters the candidates.

## Context policy

Active `context_filter` generation is disabled until aligned BTCUSDC or ETHBTC
candles are actually consumed by the simulator. Reports state:

- `context_candidates_enabled=false`;
- `context_disabled_reason=real_context_market_data_not_integrated`.

This prevents duplicate ETHUSDC signals from being mislabelled as context-tested
evidence. BTCUSDC and ETHBTC remain context-only and non-tradable.

## Report transparency

Each cycle now reports:

- generator version;
- requested and generated count;
- active families and family counts;
- diagnosis pressure/opening bias;
- context status;
- explicit holdout and target exclusion.

## Verification

GitHub Actions, Python 3.12:

- 774 tests passed;
- `compileall` passed;
- committed whitespace check passed.

Tests confirm:

- exactly 40 unique candidates at the production cap;
- six active families;
- exactly two tested variants per family at the 12-candidate cap;
- no pseudo-context family or BTCUSDC/ETHBTC parameter in active candidates;
- no audit, blindtest or target parameter;
- deterministic output;
- bounded diagnosis pressure.

## Safety

No change enables Live, Paper, Testtrade, orders, account access, keys, private
endpoints, shorts, margin, futures or leverage. Costs, fixed 100-USDC research
notional, quality gates and sealed-holdout rules are unchanged.

## Next local action

After Codex safely integrates the stacked PR chain, run a new production
research cycle against the local real data. The corrected system can now test
the intended 12-candidate frontier with complete selection evidence. No claim
of 3 USDC/day is made until that real run produces it after costs over all
calendar days.
