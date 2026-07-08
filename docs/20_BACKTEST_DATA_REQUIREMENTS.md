# Backtest Data Requirements

This document defines the data matrix for the later realistic ETHUSDC Binance Spot LONG-only backtest path.

The goal remains:

- symbol: ETHUSDC
- quote: USDC
- market: Binance Spot
- position mode: LONG-only
- start capital: 100 USDC
- future target: at least 3 USDC/day in a realistic Training/Blindtest process
- training: 730 complete UTC days
- blindtest: 365 complete UTC days
- total rolling window: 1095 complete UTC days
- BTCUSDC and ETHBTC are context only and must never trigger orders

No requirement in this catalog is a backtest result, profit claim, trade, candidate, or live/paper/testtrade unlock.

## Data matrix

### Required trade market

1. ETHUSDC spot klines 1m
   - requirement_id: `ethusdc_klines_1m`
   - role: `trade_market`
   - required_days: 1095
   - publicly downloadable: yes
   - blocks normal backtest when missing/partial/outdated
   - only source that may become the traded market in a future engine

### Market context

2. BTCUSDC spot klines 1m
   - requirement_id: `btcusdc_klines_1m`
   - role: `market_context`
   - context_only: true
   - required_days target: 1095
   - publicly downloadable: yes
   - never trade_market
   - may not trigger orders
   - missing context prevents positive candidate confidence, but does not by itself unlock or create a backtest result

3. ETHBTC spot klines 1m
   - requirement_id: `ethbtc_klines_1m`
   - role: `market_context`
   - context_only: true
   - required_days target: 1095
   - publicly downloadable: yes
   - never trade_market
   - may not trigger orders
   - missing context prevents positive candidate confidence, but does not by itself unlock or create a backtest result

### Microstructure / tradeflow

4. ETHUSDC aggTrades
   - requirement_id: `ethusdc_aggtrades`
   - role: `microstructure_tradeflow`
   - public historical data target: as much as Binance public data reasonably provides
   - minimum start: 7 complete days
   - included_in_backtest=false until minimum coverage is validated
   - positive_candidate_influence_allowed=false while coverage is too low

5. ETHUSDC trades
   - requirement_id: `ethusdc_trades`
   - role: `microstructure_tradeflow`
   - public historical data target: as much as Binance public data reasonably provides
   - minimum start: 1 complete day
   - included_in_backtest=false until minimum coverage is validated
   - positive_candidate_influence_allowed=false while coverage is too low

### Rules and cost basis

6. exchange_info
   - requirement_id: `exchange_info`
   - role: `rules_cost_basis`
   - needed filters: tickSize, stepSize, minNotional, minQty
   - no private API key required
   - downloader/fetcher not yet implemented in this repository

7. fee_reference
   - requirement_id: `fee_reference`
   - role: `rules_cost_basis`
   - use conservative model or explicit local/manual config
   - no fake account-specific fee
   - no API key

8. slippage_model
   - requirement_id: `slippage_model`
   - role: `rules_cost_basis`
   - start conservative
   - can later be improved with validated bookTicker/orderbook history
   - no fake fill quality

### Live-collected future inputs

9. ETHUSDC bookTicker
   - requirement_id: `ethusdc_bookticker_live`
   - role: `live_microstructure`
   - live_collected: true
   - minimum history before inclusion: 30 validated days
   - included_in_backtest=false while under minimum
   - diagnostic_only=true while under minimum
   - positive_candidate_influence_allowed=false while under minimum

10. ETHUSDC orderbook snapshots
    - requirement_id: `ethusdc_orderbook_snapshots_live`
    - role: `live_microstructure`
    - live_collected: true
    - minimum history before inclusion: 30 validated days
    - included_in_backtest=false while under minimum
    - diagnostic_only=true while under minimum
    - positive_candidate_influence_allowed=false while under minimum

Optional later:

- BTCUSDC/ETHBTC bookTicker can become diagnostic context later, but is not a current Pflichtquelle.

## Why ETHUSDC 1m alone is not the target state

ETHUSDC 1m klines are necessary because they define the primary trade market and the 1095-day train/blind window. They are not sufficient for a credible final system because:

- context regimes from BTCUSDC and ETHBTC should be known before positive candidate confidence is allowed;
- Binance rules and fee/slippage assumptions must be represented conservatively;
- microstructure/tradeflow inputs may help diagnose execution and false signals, but only after coverage is validated;
- live spread/orderbook information cannot be backfilled honestly and must be collected before it can influence a future candidate.

The readiness gate therefore separates:

- data required to start the first normal backtest gate;
- context data that affects candidate confidence;
- diagnostic data that must not influence a positive candidate yet;
- future live-collected data that needs minimum validated history.
