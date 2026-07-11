# PR #5 final green alignment status

Stand: 2026-07-11

Branch head at the end of the alignment work:

`d5aec6956cc8b4031dcf6c4a3e4bda5fcfda6bbd`

GitHub Actions result:

- full Python 3.12 pytest suite: passed
- source compilation: passed
- committed whitespace check: passed

Completed alignment scope:

- desired targets normalized to 3/6/15/30 USDC per calendar day;
- strict config schema synchronized;
- cross-platform external-data path containment fixed and regression-tested;
- Shadow source colour explicitly scoped to canonical 100-USDC evidence;
- larger 200/500/1000-USDC Shadow deployments marked `unverified_scaling`
  until separate budget evidence exists;
- Dashboard exposes source colour, evidence budget and deployment target status;
- legacy Shadow test fixtures updated to the strict assessment schema;
- all temporary write-enabled workflows and patch helpers removed;
- only the read-only review CI remains.

No Live, Paper, Testtrade, order, account, key, margin, futures, leverage or
short capability was enabled.

Next work starts on a separate stacked branch for missing Research Protocol v2
evidence producers. The sealed holdout remains unopened and excluded from
selection.
