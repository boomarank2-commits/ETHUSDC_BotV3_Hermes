# Backtest Research Loop

This repository now has a reproducible offline research loop runner for ETHUSDC Binance Spot LONG-only strategy experiments.

Command:

```bash
PYTHONPATH=src python -m ethusdc_bot.backtest.research_loop_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --max-cycles 8 --max-candidates-per-cycle 40
```

Safety scope:

- ETHUSDC is the only tradeable symbol.
- Quote/capital basis remains USDC.
- The simulator is Binance Spot LONG-only.
- Trade notional remains 100 USDC per simulated trade.
- No shorts, margin, futures, leverage, Binance Trading API, API keys, orders, live mode, paper mode, or testtrade mode are created or unlocked.
- BTCUSDC and ETHBTC are allowed only as context-filter metadata and cannot trigger trades.
- Raw public data stays outside the repository under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.

Loop architecture:

1. Check the local data gate.
2. Load ETHUSDC 1m candles from the external raw-data root.
3. Build the existing 730-day training / 365-day blindtest split.
4. Split training internally into subtrain/validation.
5. Generate a deterministic bounded candidate search space from validation-only diagnosis.
6. Evaluate a bounded deterministic frontier of generated candidates on subtrain and validation.
7. Run walk-forward validation inside training for the validation leader.
8. Rank candidates without blindtest metrics.
9. Store leaderboard summaries, family aggregates, WFV summaries, and exit-reason analysis.
10. Blindtest-audit only the selected top candidate and mark the audit as repeated audit-only.
11. Derive the next search-space state from training/validation/WFV/exit evidence only.
12. Continue until target reached, max cycles, stagnation, safety violation, or test/runtime failure.

Stop criteria:

- `target_reached_clean_validation_candidate`: validation candidate and blindtest audit both meet the +3 USDC/day target after the minimum cycle count.
- `max_cycles_reached`: configured cycle cap reached.
- `validation_stagnation_3_cycles`: no validation improvement for the configured stagnation window after the minimum cycle count.
- `safety_violation`: any safety lock deviates from locked/not-used/not-created.

Blindtest discipline:

Blindtest results are audit-only. They are recorded as `repeated_blindtest_audit` and are not used by the search-space generator or ranking inputs.

Reports:

- JSON/TXT loop reports: `reports/research_loop/`
- Append-only index: `reports/research_loop/index.jsonl`

If a report says the target is reached, it still states: `Ziel im Backtest erreicht, keine Live-Freigabe.`
If the target is not reached, it states: `Ziel nicht erreicht.`
