# Research evidence producer branch plan

A separate stacked branch will be created from the final green PR #5 alignment
head. Its sole scope is selection-only evidence production for
`quality_gate_v1`.

Required producers:

- rolling mark-to-market drawdown and underwater duration;
- top-1/top-5 positive trade concentration and net/profit factor without top 5;
- baseline, joint fee/slippage and slippage-only stress;
- numeric parameter neighbours at fixed ex-ante perturbations;
- month/quarter activity and performance stability;
- four training-thresholded entry-time regimes.

Hard constraints:

- training/validation/WFV data only;
- no sealed holdout load or evaluation;
- fixed 100-USDC canonical research profile;
- no gate threshold changes based on observed results;
- no strategy or UI expansion in this branch;
- deterministic evidence with explicit provenance and complete unit tests.
