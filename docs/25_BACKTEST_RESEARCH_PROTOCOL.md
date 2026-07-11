# Backtest Research Protocol v2

This document defines the binding offline selection protocol for ETHUSDC research.

## Hard boundaries

- ETHUSDC/USDC Spot LONG-only.
- Fixed 100 USDC notional per trade, at most one open position, no compounding.
- Baseline costs: 0.1% fee plus 5 bps slippage per side, without BNB discount.
- No shorts, margin, futures, leverage, orders, account data, API keys, Trading API, Paper, Testtrade, or Live activation.
- BTCUSDC and ETHBTC can never open a trade. Until their real context data are integrated, generated `context_filter` candidates are explicitly ineligible for testing.
- Raw public data remains outside the repository under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.

## Dynamic windows

The current window is derived from the latest complete UTC day in the available, continuous dataset:

- previous 730 complete UTC days: training;
- following 365 complete UTC days: sealed holdout/audit metadata;
- no fixed calendar years.

When more than 1,095 days are available, the latest 1,095-day block is used. Historical 730+365 origin windows must end before the latest holdout begins. The first non-overlapping historical origin therefore requires at least 1,460 complete days. With 1,095-1,459 days, `historical_origin_count=0` is the only valid result.

For production 1-minute data, a complete UTC day means exactly 1,440 contiguous candles from 00:00 through 23:59. An incomplete latest day is excluded; an incomplete internal day fails closed.

The repeatedly viewed window `2025-07-08` through `2026-07-07` is recorded in the historical consumed-audit ledger. Fixed ledger dates do not drive dynamic window selection; they prevent any overlapping training, validation, WFV, or historical-replay window from being used. A final holdout may overlap only as consumed metadata and remains unevaluated.

## Candidate stages and budgets

Protocol v2 reports configured caps separately from actual counts and candidate IDs:

| Stage | Default cap |
|---|---:|
| Generated | 40 |
| Tested | 12 |
| Walk-forward | 3 |
| Finalists | 2 |

The invariant is:

```text
finalists <= walk_forward <= tested <= generated
```

Generated candidates are deduplicated deterministically. If the supported generated set fits within the tested cap, all supported candidates are evaluated. Otherwise, a deterministic family-round-robin frontier is used. Candidate generation order is never silently truncated to a fixed prefix.

The runner also hard-caps estimated selection work. At the canonical stage and historical-origin caps, this is at most 14,600 candidate-days or 21,024,000 one-minute candle evaluations per cycle, with at most eight cycles. Per-cycle and whole-loop ceilings are written to the report; configuration above a cap is rejected before data evaluation starts.

## Selection sequence

The only selection-bearing datasets are, in this exact order: `subtrain`, `validation`, and `walk_forward`. Historical fixed-candidate replay is diagnostic evidence only; it is not selection data and cannot change ranking, parameters, finalists, or freeze status.

1. Validate the public-data gate and continuous UTC windows.
2. Split only the 730-day training block into chronological subtrain and validation sections.
3. Generate and inventory candidates.
4. Exclude unsupported placeholder context candidates with an explicit reason.
5. Evaluate the tested stage on subtrain and validation.
6. Rank without audit/holdout metrics.
7. Evaluate the leading three candidates across six chronological WFV folds.
8. Select at most two finalists from WFV evidence.
9. Apply `quality_gate_v1` to training-only evidence.
10. Freeze at most one candidate only if every required selection gate passes.

The final holdout is not evaluated anywhere in this loop. `target_reached` therefore remains false and the target status remains `not_evaluated_no_sealed_holdout_run`. A separate future workflow may evaluate a completely frozen candidate exactly once.

## Walk-forward and historical-origin discipline

WFV uses the actually simulated candle slice and its actual UTC calendar-day count. Sampled candles are never divided by the duration of a larger unsimulated fold.

Historical origin boundaries are planned without overlap with the final holdout. Optional origin candidates that overlap the consumed ledger are skipped and reported with their boundaries and reason; the planner continues backward to collect older clean origins. The current final training window itself is never skipped: consumed overlap there blocks the run. A fixed-candidate historical backcast is reported explicitly as `fixed_candidate_historical_replay`, with `pipeline_refit_per_origin=false`; it cannot affect finalist ranking or satisfy the formal rolling-origin quality gate. Formal rolling-origin evidence requires the whole selection pipeline to be refit using only data available inside each origin. Until that evidence producer exists and enough history is available, the gate fails closed.

## Quality gates

The immutable thresholds and evidence contract are documented in `docs/30_RESEARCH_QUALITY_GATES.md`. Missing concentration, mark-to-market drawdown, parameter-neighborhood, cost-stress, temporal, regime, or time-local rolling-origin evidence blocks candidate freeze. Missing evidence is never interpreted as zero or success.

Passing selection gates means only that a candidate is eligible for one sealed-holdout evaluation. It does not adopt a candidate and never unlocks Paper, Testtrade, or Live.

## Legacy path

The old `ethusdc_bot.backtest.runner`, `ethusdc_bot.backtest.research_runner`, and direct `strategy_search`/`evaluate_blindtest_once` paths are fail-closed because they evaluated the consumed holdout. Compatibility types remain for historical report reading, but every legacy execution raises an error directing callers to the v2 loop. Passing `--fixture-smoke` or `required_days=None` does not bypass these guards.

## Command

```powershell
$env:PYTHONPATH='src'
python -m ethusdc_bot.backtest.research_loop_runner `
  --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes `
  --max-cycles 8 `
  --max-candidates-per-cycle 40 `
  --tested-candidates-per-cycle 12 `
  --walk-forward-candidates-per-cycle 3 `
  --finalists-per-cycle 2 `
  --walk-forward-folds 6 `
  --rolling-origin-limit 3
```

Long historical runs are intentionally deferred until the code and gates are reviewed and merged.
