# Legacy Backtest Engine and Strategy Search (Disabled)

This document records the status of the first backtest/search path. It is retained for history, but its execution workflow is no longer valid under Research Protocol v2.

## Why it is disabled

The legacy flow selected a candidate from training/validation and then evaluated the same 365-day blindtest whenever the command or helper was called. That window was viewed repeatedly and is now permanently classified as consumed for selection purposes.

The following APIs fail closed before loading, simulating, or writing:

- `ethusdc_bot.backtest.runner.run_backtest`;
- `ethusdc_bot.backtest.research_runner.run_research`;
- `ethusdc_bot.backtest.strategy_search.run_strategy_search`;
- `ethusdc_bot.backtest.strategy_search.evaluate_blindtest_once`.

`--fixture-smoke` and `required_days=None` do not bypass the legacy guards.

## Active research path

The only active strategy-research entrypoint is:

```powershell
$env:PYTHONPATH='src'
python -m ethusdc_bot.backtest.research_loop_runner `
  --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes
```

Protocol v2 uses dynamic, complete UTC windows and training-only subtrain, validation, and WFV evidence. It records final-holdout metadata but never passes those candles to the simulator.

The dashboard does not yet start Protocol v2. Its engine button remains disabled and labelled `research_protocol_v2_not_wired`; dashboard work is a later ticket.

## Historical reports

Existing schema-v1 backtest reports remain append-only historical artifacts. They must not be used for candidate selection, ranking, parameter changes, freeze, or target claims. The live, Paper, and Testtrade locks remain unchanged.
