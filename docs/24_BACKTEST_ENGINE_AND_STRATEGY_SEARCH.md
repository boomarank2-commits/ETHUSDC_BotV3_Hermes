# Backtest Engine and Strategy Search

This phase adds the first real, reproducible ETHUSDC backtest foundation.

Scope:
- ETHUSDC only for trade signals.
- Binance Spot LONG-only simulation.
- 100 USDC trade notional.
- Conservative fee and slippage model.
- No shorts, margin, futures, leverage, API keys, Binance Trading API, paper, testtrade, or live orders.
- BTCUSDC and ETHBTC remain context-only data sources and must never trigger orders.

Data:
- Raw public data stays outside the repository under `C:/TradingBot/data/ETHUSDC_BotV3_Hermes`.
- Loader reads ETHUSDC 1m ZIP/CHECKSUM pairs read-only.
- Loader validates ETHUSDC naming, UTC order, 1m spacing, duplicates, and gaps.
- Loader returns only no-lookahead candle fields: open_time, open, high, low, close, volume.

Split:
- Required full window: 1095 UTC days.
- First 730 UTC days: training/validation selection only.
- Last 365 UTC days: blindtest.
- No overlap; blindtest is evaluated once after candidate selection.

Implemented first strategy families:
- Momentum.
- Mean-reversion.
- Breakout.

Search discipline:
- Small deterministic candidate grid.
- Training is internally split into subtrain/validation.
- Candidate selection uses training/validation only.
- The target of 3 USDC/day is a reporting threshold, not a parameter used to optimize candidates.

Run command:

`PYTHONPATH=src python -m ethusdc_bot.backtest.runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`

Reports:
- Real completed runs write JSON and TXT under `reports/backtests/`.
- Reports include training and blindtest metrics separately.
- Reports state honestly whether the 3 USDC/day blindtest target was reached.
- Reports never unlock live/paper/testtrade.
