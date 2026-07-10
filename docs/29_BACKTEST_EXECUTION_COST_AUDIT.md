# Backtest Execution Cost Audit

## Scope and conclusion

Audit date: 2026-07-10

Starting commit: `8ac7003`

The suspected diagnostic slippage defect in `src/ethusdc_bot/backtest/simulator.py` was confirmed. The simulator used the later exit candle's open both as exit mid-price and as the comparison price for the entry fill. Normal market movement between entry and exit was therefore reported as entry slippage.

The execution-price P&L itself was already computed from slipped entry and exit execution prices. The defect did not directly change trade net P&L. It did change `slippage_usdc`, cost diagnostics, candidate rank scores, family diagnostics, exit-reason cost summaries, WFV cost load, and search-space adjustments that consume reported slippage. Historical reports that used this field for ranking or diagnosis are obsolete for those purposes.

## Old formula and root cause

Old exit-side code was equivalent to:

```text
entry_execution_price = entry candle open * (1 + slippage_rate)
exit_execution_price = exit candle open * (1 - slippage_rate)
quantity = 100 / entry_execution_price
ideal_qty = 100 / exit candle open
reported_slippage =
    abs(entry_execution_price - exit candle open) * ideal_qty
  + abs(exit candle open - exit_execution_price) * quantity
```

The first term compares an entry fill to the exit mid-price. It therefore contains the intervening market return and varies with holding-period price movement.

## Corrected execution model

For fixed notional `N = 100 USDC` and per-side slippage rate `s = slippage_bps / 10_000`:

```text
entry_mid_price = actual entry candle open
entry_execution_price = entry_mid_price * (1 + s)
quantity = N / entry_execution_price

exit_mid_price = actual exit candle open
exit_execution_price = exit_mid_price * (1 - s)

entry_slippage_usdc =
    (entry_execution_price - entry_mid_price) * quantity
exit_slippage_usdc =
    (exit_mid_price - exit_execution_price) * quantity
slippage_usdc = entry_slippage_usdc + exit_slippage_usdc

execution_gross_profit_usdc =
    (exit_execution_price - entry_execution_price) * quantity
entry_fee_usdc = entry_execution_price * quantity * fee_rate
exit_fee_usdc = exit_execution_price * quantity * fee_rate
fees_usdc = entry_fee_usdc + exit_fee_usdc
net_profit_usdc = execution_gross_profit_usdc - fees_usdc
```

Slippage is already embedded in execution prices and is not subtracted again from net P&L.

The trade record now retains `entry_mid_price`, `exit_mid_price`, `entry_slippage_usdc`, `exit_slippage_usdc`, `entry_fee_usdc`, and `exit_fee_usdc` for auditability.

## Hand-checkable examples

For entry mid `100`, exit mid `100`, notional `100`, and `5 bps` per side:

```text
entry execution = 100.05
quantity = 100 / 100.05 = 0.999500249875...
exit execution = 99.95
entry slippage = 0.05 * quantity = 0.0499750125 USDC
exit slippage = 0.05 * quantity = 0.0499750125 USDC
total slippage = 0.0999500250 USDC
execution gross = -0.0999500250 USDC
```

With zero fees, net P&L is approximately `-0.0999500250 USDC`.

With `0.1%` fee per side:

```text
entry fee = 100.00 * 0.001 = 0.1000000000 USDC
exit fee = (99.95 * quantity) * 0.001 = 0.0999000500 USDC
total fees = 0.1999000500 USDC
net P&L = -0.0999500250 - 0.1999000500
          = -0.2998500750 USDC
```

Ten identical flat round trips report approximately `0.99950025 USDC` slippage. 1,623 identical flat round trips report approximately `162.2188906 USDC`, not more than `1,000 USDC`.

For exit mids `99`, `101`, and `120`, the reported slippage is only the two execution offsets. The `-1%`, `+1%`, or `+20%` market move is not classified as slippage.

## Test coverage

`tests/unit/test_backtest_simulator.py` now verifies:

- flat round trip with zero fees;
- flat round trip with 0.1% fees per side;
- rising, falling, and +20% market moves do not become slippage;
- 10 and 1,623 identical round trips scale linearly;
- holding duration does not affect costs when entry and exit mids are identical;
- entry and exit fees are each charged exactly once;
- `net = execution gross - fees`;
- quantity is based on actual entry execution price;
- closed-candle signal enters no earlier than the next candle open;
- forced end-of-data exit uses the same accounting;
- take-profit, stop-loss, time-exit, break-even, and trailing-stop records use one shared execution-cost formula.

TDD evidence:

- Before the implementation, the targeted test run failed in 13 cases for the expected missing fields and incorrect slippage values.
- After the minimal implementation, `PYTHONPATH=src pytest tests/unit/test_backtest_simulator.py -q` passed: `23 passed`.
- Full verification after the correction: `PYTHONPATH=src pytest tests/ -q` passed: `412 passed`.

## Impact assessment

### Net P&L

Direct net P&L: **not changed by this defect fix**.

Reason: gross P&L already used slipped execution prices and net P&L already subtracted fees exactly once. The incorrect diagnostic slippage value was not separately subtracted from net P&L.

### Reporting and ranking

Diagnostic slippage: **changed materially**.

Candidate ranking: **affected** because `research_runner.py` includes `(fees_usdc + slippage_usdc)` in `cost_penalty`.

Other affected derived diagnostics include:

- cost-load weaknesses and family aggregates;
- report diagnosis;
- WFV cost load;
- exit-reason cost summaries;
- validation-driven search-space adjustment.

### Post-fix control evidence

The first cycle of the pre-fix run `research_loop_20260709T213134Z` and the post-fix control run `research_loop_20260710T054549Z` selected the same candidate, `breakout_volatility_filter_01_001`, with identical parameters and 14 audit trades. This provides a like-for-like accounting comparison:

| Metric | Pre-fix | Post-fix |
|---|---:|---:|
| Net profit | -0.4686584526 USDC | -0.4686584526 USDC |
| Net per day | -0.0012839958 USDC | -0.0012839958 USDC |
| Fees | 2.8023336751 USDC | 2.8023336751 USDC |
| Diagnostic slippage | 16.4060172167 USDC | 1.4011677713 USDC |

Net P&L, fees, and trade count are unchanged, while diagnostic slippage falls by approximately 91.46%. This confirms that the defect was diagnostic/cost-ranking corruption rather than a direct P&L subtraction error.

### Obsolete historical report use

All reports produced before this correction remain historical evidence of the execution-price net P&L that was calculated at the time, but their slippage totals, cost penalties, cost-based ranking, cost diagnoses, and any search-space decisions derived from those values must not be used as a valid current ranking basis.

This specifically includes:

- `reports/backtests/bt_20260709T151036Z.*`;
- prior `reports/research/research_*.json` and `.txt`;
- `reports/research_loop/research_loop_20260709T213134Z.json` and `.txt`.

They are retained append-only and are not deleted or overwritten.
