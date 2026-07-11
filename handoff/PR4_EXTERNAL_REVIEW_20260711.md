# PR #4 external review handoff

Stand: 2026-07-11

## Scope

This review branch starts from remote PR #4 commit:

`bafbc187f393b38e44d5489a30af0b92d352f21e`

The original Codex branch `agent/portfolio-shadow-v1` was intentionally not
modified because the local Windows worktree may contain unpushed changes that
are not visible on GitHub.

Review branch:

`review/pr4-final-alignment`

## Changes made on the review branch

The confirmed proportional desired guidance is now:

- 100 USDC -> 3 USDC per calendar day
- 200 USDC -> 6 USDC per calendar day
- 500 USDC -> 15 USDC per calendar day
- 1000 USDC -> 30 USDC per calendar day

The prior 500-USDC desired value of 13 was changed to 15 in:

- `config/default.toml`
- `src/ethusdc_bot/portfolio.py`
- `docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md`
- `tests/unit/test_portfolio_policy.py`
- `tests/unit/test_config_templates.py`

The product contract now also states that a larger budget profile must have its
own evidence before it can be called green. A green 100-USDC result must not be
mathematically multiplied and presented as a proven 200/500/1000-USDC result.

## Important architecture finding

At remote commit `bafbc18`, `assess_final_report(...)` determines the green,
yellow, or red assessment from the final report before
`adopt_for_shadow(...)` receives the manually selected deployment budget.

That means a final report proven for the canonical 100-USDC profile can later
be adopted with a 200/500/1000-USDC deployment budget while retaining the
source assessment color. This is safe from an order perspective, but the color
is not automatically evidence that the larger budget achieved its proportional
6/15/30-USDC daily target.

Before PR #4 is merged, Codex should make the semantics explicit and test them.
Acceptable minimal outcomes are:

1. Keep the source final-assessment color explicitly bound to the canonical
   100-USDC evidence and show larger deployment budgets as unproven scaling
   profiles until separately evaluated; or
2. Introduce separate budget-profile evidence and a budget-specific assessment
   without reopening or reusing the consumed holdout.

Do not silently inherit a green 100-USDC target claim as a proven green result
for a larger budget.

## Still to verify on the local Codex worktree

- whether local commits or uncommitted changes exist beyond `bafbc18`;
- complete budget reporting, including average deployed capital and unused
  capacity;
- capacity rejection reporting;
- absolute and budget-relative drawdown reporting;
- backtest/shadow parity for identical candles;
- no compounding after gains or losses;
- stop does not create an artificial end-of-data exit;
- no order, account, API-key, Paper, Testtrade, or Live paths;
- all target-guidance references use 3/6/15/30;
- no remaining `500 -> 13` expectations in code, tests, docs, or UI text.

## Test status

No local test suite was executed from this ChatGPT GitHub review environment.
The changes are small and matching unit expectations were updated, but Codex
must run the complete Windows/Python 3.12 suite before integration:

```powershell
py -3.12 -m pytest -q
py -3.12 -m compileall -q src
git diff --check
```

Do not disable tests or relax safety assertions.

## Integration instructions for Codex

After the local interrupted worktree has been inspected and safely committed:

1. Fetch `review/pr4-final-alignment`.
2. Compare it against the local `agent/portfolio-shadow-v1` state.
3. Cherry-pick or manually apply only changes that are not already present.
4. Resolve any target-guidance conflict in favor of 3/6/15/30.
5. Run the complete suite.
6. Update PR #4 with the final test count and semantic decision for larger
   budget assessment colors.
7. Keep PR #4 draft and do not merge until external review is complete.

## Safety status

This review did not enable Live, Paper, Testtrade, orders, account access,
Trading API, API keys, shorts, margin, futures, or leverage.
