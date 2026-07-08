# Data Readiness Gate

This document describes the read-only data readiness gate for a future UI-driven backtest start.

Implemented modules:

- `src/ethusdc_bot/data_pipeline/data_requirements.py`
- `src/ethusdc_bot/data_pipeline/data_readiness.py`

The gate does not backtest, download, trade, create reports, create candidates, or unlock Live/Paper/Testtrade.

## Future UI backtest-start flow

When the UI Backtest button is eventually wired to a real engine, the intended sequence is:

1. User presses Backtest in the UI.
2. UI builds a data readiness report.
3. Missing or outdated data is listed as explicit update tasks.
4. Approved public downloads or live collectors run separately.
5. Local audit validates the data.
6. Only allowed and validated data enters feature build.
7. Only then may a real backtest engine run.

At this stage, the Backtest button remains disabled because the data gate is not fully green and no engine exists.

Visible UI hint:

`Backtest waits for data readiness and real engine implementation. No fake result.`

## Rolling 1095-day window

The gate must not blindly use `today - 1095 days`, because the newest public Binance daily files may not be available yet.

Rule:

1. Determine the newest complete auditable UTC day.
2. Set `data_end` to that day.
3. Set `data_start = data_end - 1094 days`.
4. Training is the first 730 days.
5. Blindtest is the last 365 days.
6. No blindtest data may leak into training.

Example from the current local data:

- latest complete ETHUSDC day: `2026-07-06`
- data_start: `2023-07-08`
- data_end: `2026-07-06`
- training_start: `2023-07-08`
- training_end: `2025-07-06`
- blind_start: `2025-07-07`
- blind_end: `2026-07-06`

Because only 1094 ETHUSDC complete UTC days are present, the gate remains blocked.

## 7-day update rule

Public historical files older than 7 days are marked `update_required=true` and `status=outdated`.

This prevents stale data from silently looking ready.

## Status fields per source

Each source status includes:

- requirement_id
- symbol
- data_type
- role
- required
- context_only
- trade_market
- publicly_downloadable
- live_collected
- required_days
- minimum_days
- available_days
- coverage_pct
- status
- included_in_backtest
- diagnostic_only
- positive_candidate_influence_allowed
- blocking_backtest
- update_required
- reason
- expected_path

Allowed status values:

- `missing`
- `partial`
- `current`
- `outdated`
- `optional_missing`
- `diagnostic_only`
- `blocked`

## Download and collection tasks

The readiness report can list tasks but does not execute them.

Task fields:

- task_id
- requirement_id
- symbol
- data_type
- interval
- start_date
- end_date
- target_path
- source_kind
- execute_allowed
- reason

Current task behavior:

- ETHUSDC 1m klines can use the existing public downloader path, so execute_allowed may be true.
- BTCUSDC 1m, ETHBTC 1m, ETHUSDC aggTrades, ETHUSDC trades, and exchange_info are marked `next_required_downloader` until explicit downloaders are implemented.
- bookTicker and orderbook snapshots are live-collection tasks, not historical public-download tasks.

## No fake release

The gate must never:

- create fake trades;
- create fake reports;
- create profit fields;
- create candidate-adoption fields;
- claim a data source is ready without local evidence;
- let BTCUSDC or ETHBTC trigger orders;
- include live-collected bookTicker/orderbook data before 30 validated days exist;
- unlock Live/Paper/Testtrade.
