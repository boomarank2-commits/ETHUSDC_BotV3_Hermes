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

Draft integration PR:

`#5 Align PR4 budget targets and document external review`

## Changes completed on the review branch

### Proportional desired guidance

The confirmed guidance is now consistent throughout configuration, strict
schema, portfolio policy, documentation and tests:

- 100 USDC -> 3 USDC per calendar day
- 200 USDC -> 6 USDC per calendar day
- 500 USDC -> 15 USDC per calendar day
- 1000 USDC -> 30 USDC per calendar day

The prior 500-USDC desired value of 13 was removed from the active contract.

### Budget evidence scope

The sealed final evaluation remains canonical for the `100 USDC` research
profile. A larger manually selected Shadow deployment budget remains allowed,
but its proportional target is no longer silently represented as proven.

Every Shadow deployment now records:

- `color_scope = canonical_100_usdc_final_evaluation`
- `target_evidence_budget_usdc = 100`
- selected `deployment_budget_usdc`
- proportional `deployment_target_usdc_per_day`
- `deployment_target_status`
- `deployment_target_reached`

Status rules:

- green 100-USDC source + 100-USDC deployment -> `verified`
- yellow 100-USDC source + 100-USDC deployment -> `below_target`
- any 200/500/1000-USDC deployment -> `unverified_scaling`

Larger budgets are therefore usable in order-free Shadow, but require separate
evidence before their 6/15/30-USDC target can be called achieved.

### Cross-platform path safety

GitHub Actions revealed that native Linux `Path.resolve()` interpreted the
canonical Windows external-data path as repository-local. A shared
cross-platform containment helper now compares absolute Windows paths with
Windows semantics even on Linux, while native POSIX containment remains strict.

This removes a false positive without allowing raw data inside the repository.
Regression tests cover Windows, POSIX, mixed path flavours and different drives.

### Automated CI

A read-only GitHub Actions workflow now executes on review and agent branches:

- Python 3.12
- project install with dev dependencies
- full `pytest` suite
- `compileall`
- committed whitespace check
- pytest diagnostics artifact on failure

The corrected alignment state passed the complete CI before the budget-evidence
scope patch. The final branch must remain green after every subsequent commit.

Temporary write-enabled patch workflows and their helper scripts were removed
after their one-time commits. Only the read-only review CI remains.

## Important remaining Research Protocol blocker

`research_loop_runner._quality_evidence()` currently emits protocol,
validation, WFV and an empty `rolling` mapping. The fixed quality gate also
requires real evidence for:

- rolling drawdown and trade concentration
- cost/slippage stress
- parameter stability
- temporal stability
- regime stability

Therefore a production finalist cannot currently obtain complete selection
evidence even if its simple P&L metrics are attractive. These evidence
producers must be implemented on a separate stacked branch using only
training/validation/WFV data. The sealed holdout must not be opened or used for
selection.

## Safety status

No change enables Live, Paper, Testtrade, orders, account access, Trading API,
API keys, shorts, margin, futures or leverage.

## Codex integration instructions

1. Inspect and preserve all local unpushed work on `agent/portfolio-shadow-v1`.
2. Fetch `review/pr4-final-alignment` and inspect PR #5.
3. Compare, then cherry-pick or manually integrate only missing changes.
4. Resolve all target guidance in favour of `3/6/15/30`.
5. Preserve budget evidence scope; do not promote a green 100-USDC source colour
   into a proven larger-budget result.
6. Run the complete Windows Python 3.12 suite, compileall and diff check.
7. Keep PR #4 and PR #5 unmerged until external review is complete.
