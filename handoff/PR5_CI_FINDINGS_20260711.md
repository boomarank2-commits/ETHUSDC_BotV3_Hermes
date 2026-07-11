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

## Safety impact

The correction does not loosen the rule that raw market data must remain
outside the repository. It removes a false positive caused solely by running
Windows path contracts on Linux. Real paths inside the repository remain
blocked.

No Live, Paper, Testtrade, order, account, API-key, short, margin, futures or
leverage capability was introduced.

## Next checks

A new full CI run must confirm:

- all 754 previous tests plus the new path-safety tests pass;
- Python source compiles;
- committed diff has no whitespace errors;
- the larger-budget assessment is not displayed as independently proven merely
  because the canonical 100-USDC final report was green.
