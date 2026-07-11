# PR #5 automated CI findings

Stand: 2026-07-11

## Tested branch

- Branch: `review/pr4-final-alignment`
- Base PR #4 commit: `bafbc187f393b38e44d5489a30af0b92d352f21e`
- Automated environment: GitHub Actions, Ubuntu 24.04, Python 3.12

## First full-suite result

The first automated run completed the full suite and exposed seven failures.

### 1. Target-guidance schema mismatch

`config/default.toml`, the portfolio policy and their direct tests had already
been updated from 13 to 15 USDC/day for the 500-USDC profile, but the strict
config schema still required the old value 13.

Correction:

- `src/ethusdc_bot/config/schema.py` now requires the canonical desired targets
  `3 / 6 / 15 / 30`.

### 2. Windows path interpreted as repository-local on Linux

The canonical external data path is a Windows path:

`C:/TradingBot/data/ETHUSDC_BotV3_Hermes`

On Linux, native `Path.resolve()` interpreted that string as a relative POSIX
path below the checkout, so safety validation falsely rejected it as being
inside the repository.

Correction:

- new shared helper `src/ethusdc_bot/path_safety.py`;
- Windows absolute paths are compared with Windows semantics even on Linux;
- mixed Windows/POSIX absolute path flavours are treated as disjoint;
- native POSIX paths continue to use resolved native containment;
- both `catalog_schema.py` and `raw_data_contract.py` now use the same helper;
- regression tests cover Windows, POSIX, mixed-flavour and cross-drive cases.

The corrected state subsequently passed the full automated test, compile and
whitespace pipeline.

## Budget evidence-scope correction

A second review found that final green/yellow assessment was computed for the
canonical 100-USDC final evaluation before a later manual Shadow deployment
budget was selected. This permitted a 500-USDC Shadow deployment to inherit the
source green colour without explicitly stating that 15 USDC/day had not been
independently demonstrated.

Correction:

- source assessment colour is explicitly scoped to the canonical 100-USDC final
  evaluation;
- each deployment records its selected budget and proportional target;
- 100-USDC green is `verified`;
- 100-USDC yellow is `below_target`;
- every larger deployment is `unverified_scaling` until separate evidence
  exists;
- strict schema and unit tests enforce these fields;
- dashboard status exposes this distinction.

This does not block larger fixed-lot Shadow budgets. It prevents an unsupported
performance claim.

## Safety impact

The corrections do not loosen the rule that raw market data must remain outside
the repository and do not enable trading.

No Live, Paper, Testtrade, order, account, API-key, short, margin, futures or
leverage capability was introduced.

## Research blocker identified

The current production research loop does not yet produce all evidence required
by `quality_gate_v1`. Missing producers include rolling concentration,
cost/slippage stress, parameter stability, temporal stability and regime
stability. Until these are computed from training/validation/WFV data, a real
candidate cannot honestly obtain a complete selection pass.

This work belongs in a separate stacked branch/PR and must not use or reopen the
sealed holdout.

## Current branch hygiene

The two temporary write-enabled patch workflows and their deterministic helper
scripts were removed after applying their one-time commits. The retained
`review-ci.yml` workflow has read-only repository permissions and performs only
installation, tests, compilation and whitespace checks.
