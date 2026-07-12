# Session Log

## 2026-07-09 - Show persistent overall data progress after restart

Timebox: max 120 minutes.

Goal:
- Fix misleading dashboard restart behavior where the main progress could jump to 0% even though local files already existed.
- Keep total local data state separate from current-run progress.

Initial guard:
- `git status --short` was clean before work.
- Work stayed inside the allowed file list.
- No raw data, reports, engine, strategy, exchange, backtest, live, paper, API-key, or order code was created.

Read-only local data inspection:
- Root: `C:/TradingBot/data/ETHUSDC_BotV3_Hermes` exists.
- Total files: 6589.
- `.tmp/.part`: 0.
- 0-byte files: 0.
- Latest mtime: `2026-07-09T15:49:55.882725`.
- ETHUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- BTCUSDC 1m: 1095 ZIP / 1095 CHECKSUM / 1095 complete pairs.
- ETHBTC 1m: 1096 ZIP / 1096 CHECKSUM / 1096 complete pairs.
- ETHUSDC aggTrades: 7 ZIP / 7 CHECKSUM / 7 complete pairs.
- ETHUSDC trades: 1 ZIP / 1 CHECKSUM / 1 complete pair.
- No broken/half files were found by name/size checks.

Root cause:
- `format_operator_summary_for_display()` and the Tk progress area used runtime `progress_pct` as `Gesamtfortschritt`.
- On restart, `build_dashboard_snapshot()` built a new idle runtime with `progress_pct = 0`.
- With no active data thread, `refresh_status()` applied that idle runtime to the main progress bar.
- The UI had task/run progress but no persistent overall local-data progress field.

Tests added/extended first:
- Existing local files produce `overall_data_progress_pct > 0`.
- Idle runtime 0 does not overwrite overall data progress.
- Operator summary shows `Gesamtdatenstand` and `Aktueller Lauf` separately.
- ZIP without CHECKSUM is not counted as a complete day.
- CHECKSUM without ZIP is not counted as a complete day.
- `.part`, `.tmp`, and 0-byte files are not counted as complete days.
- 0-byte existing downloader target is not skipped as complete.
- ZIP-only existing file is not treated as a fully skipped pair; missing CHECKSUM is still downloaded/planned in execute path.

Implementation:
- `dashboard_state.build_overall_data_progress()` computes persistent progress from readiness requirements for the five operator-visible public sources.
- Dashboard snapshot includes:
  - `overall_data_progress_pct`
  - `overall_data_progress`
  - `current_run_progress_pct`
- Main `data_prep_progress_pct` now maps to overall data progress for the main bar.
- Tk dashboard keeps the main bar on overall data state and displays current-run progress as text.
- Readiness public-data availability now requires non-empty `.zip` plus matching non-empty `.zip.CHECKSUM` for a day.
- `.tmp`, `.part`, and 0-byte files are excluded from availability counts.
- Downloader skip check now requires an existing non-empty final file.

Local smoke:
- `PYTHONPATH=src` dashboard snapshot against the real local data root returned:
  - `overall_data_progress_pct 100.0`
  - `current_run_progress_pct 0`
  - all five operator rows complete against their configured requirements/minimums.
- Summary shows `Gesamtdatenstand: 100.0%` and `Aktueller Lauf: 0% seit Start / Idle` separately.

Verification:
- Targeted tests failed before implementation for the intended cases.
- Targeted tests passed after implementation.
- `pytest tests/ -q` passed before handoff update.

No real downloads were started.
No reports/backtests were created.
No forbidden directories/files were created.

## 2026-07-09 - Add deterministic ETHUSDC backtest strategy search foundation

Timebox: max 180 minutes.

Goal:
- Start the real backtest section without live, paper, testtrade, API keys, Trading API, or fake results.
- Build a reproducible ETHUSDC 1m data loader, 730/365 split, conservative LONG-only simulator, strategy search, runner, and honest report.

Initial guard:
- `git status --short` was clean before work.
- Handoff files were read first.
- Local data readiness was checked read-only before implementation.
- Existing full suite passed before implementation.

Data/UI Abschlussprüfung:
- `START_DASHBOARD.bat` exists.
- External root `C:/TradingBot/data/ETHUSDC_BotV3_Hermes` exists.
- Total files: 6589.
- `.tmp/.part`: 0.
- 0-byte files: 0.
- Data gate: ready.
- ETHUSDC 1m 1095/1095, BTCUSDC 1m 1095/1095, ETHBTC 1m 1096/1095, ETHUSDC aggTrades 7/7, ETHUSDC trades 1/1.
- ZIP/CHECKSUM pairs matched for all checked public sources.

TDD:
- New backtest tests were written first and failed with missing `ethusdc_bot.backtest` package.
- Implemented only after RED.

Implementation:
- Added `src/ethusdc_bot/backtest/` package.
- Loader reads ETHUSDC 1m ZIP/CHECKSUM pairs read-only, validates symbol, UTC order, 1m spacing, duplicates, gaps, and normalizes Binance microsecond timestamps to milliseconds.
- Split enforces 1095 UTC days for real runs: first 730 training, last 365 blindtest.
- Simulator is ETHUSDC Spot LONG-only with fees/slippage and no parallel positions.
- Search uses a small deterministic grid over momentum, mean-reversion, and breakout families; selection is training/validation only.
- Runner writes real JSON/TXT reports only after successful completion.
- Dashboard state now has a separate backtest-mode status/button model; full background UI execution remains next-step work.

Real backtest:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Loaded 1,576,800 ETHUSDC candles.
- Split: training 2023-07-09..2025-07-07; blindtest 2025-07-08..2026-07-07.
- Selected candidate: breakout lookback 60 / threshold 10 bps / TP 120 bps / SL 80 bps / max hold 90 minutes.
- Blindtest: -491.2563751241 USDC total, -1.3459078771 USDC/day, 1623 trades.
- Target 3 USDC/day: not reached.
- Report: `reports/backtests/bt_20260709T151036Z.json` and `.txt`.

Verification:
- Targeted tests passed.
- Real CLI runner passed.
- `pytest tests/ -q` passed before handoff update.

Safety:
- No API keys.
- No Binance Trading API.
- No orders.
- No live/paper/testtrade activation.
- Reports keep live/paper/testtrade locked and candidate_adoptable false.

## 2026-07-09 - Add reproducible offline strategy research runner

Timebox: max 240 minutes.

Goal:
- Move from a single baseline backtest to a reproducible offline strategy-research system.
- Diagnose the first negative backtest.
- Add protocol, features, context safety, experiment registry, and a CLI research runner.

Initial guard:
- `git status --short` was clean before work.
- Handoff and existing baseline reports were read first.
- Current backtest code was inspected before implementation.
- Baseline `pytest tests/ -q` passed.

Baseline diagnosis:
- Source: `reports/backtests/bt_20260709T151036Z.json` and `.txt`.
- Ziel nicht erreicht.
- Training negative.
- Blindtest negative.
- Profit factor < 1.
- Winrate low.
- Costs/slippage high.
- Overtrading suspected.
- Drawdown high.
- Interpretation: no reliable edge shown by the baseline candidate; no claim that a simple change will fix it.

TDD:
- Tests were added first for report diagnosis, research protocol, experiment registry, no-lookahead features, context safety, and research runner.
- RED was observed as missing modules.
- Implementation followed the failing tests.

Implementation:
- `report_diagnosis.py`: reads completed backtest reports and emits honest JSON/text diagnosis.
- `research_protocol.py`: defines reproducibility fields and forbids blindtest selection.
- `experiment_registry.py`: writes append-only research JSON/TXT/index.jsonl without overwriting old runs.
- `features.py`: returns, rolling volatility, intraday range, breakout distance, mean-reversion distance, trend slope, relative volume, time/session fields.
- `context_loader.py`: BTCUSDC/ETHBTC context helper; context symbols cannot trigger trades.
- `research_runner.py`: CLI research runner with controlled candidate grid and validation-only ranking.
- `simulator.py`: extended with trend, volatility, regime, pullback, session, cooldown, and fee-aware filters.

Real research run:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Run-ID: `research_20260709T170636Z`.
- Reports:
  - `reports/research/research_20260709T170636Z.json`
  - `reports/research/research_20260709T170636Z.txt`
  - `reports/research/index.jsonl`
- Families tested: momentum_trend_filter, breakout_volatility_filter, mean_reversion_regime_filter, pullback_in_trend, session_filter, cooldown_fee_aware.
- Candidates: 12.
- Selected: breakout_volatility_filter with lookback 120, threshold 10 bps, volatility filter 10..120 bps, TP 140 bps, SL 90 bps, max hold 180 minutes, cooldown 90 minutes.
- Selection used subtrain/validation only; blindtest was evaluated after candidate selection.
- Training: -0.1171462622 USDC/day.
- Validation: -0.2452730967 USDC/day.
- Blindtest: -0.0674168068 USDC/day.
- Target +3 USDC/day: not reached.
- Compared to baseline, loss and trade frequency were reduced, but no sufficient edge exists yet.

Verification:
- Targeted new tests passed.
- Full `pytest tests/ -q` passed before the real research run.
- Final `pytest tests/ -q` will be rerun after handoff/docs before commit.

Safety:
- No live, paper, or testtrade.
- No orders.
- No API keys.
- No Binance Trading API.
- No raw data in repo.

## 2026-07-09 - Candidate leaderboard and controlled exit improvement

Timebox: max 240 minutes.

Goal:
- Add full per-candidate leaderboard to research reports.
- Diagnose candidate/family behavior before any further strategy changes.
- Add exactly one controlled training-only improvement.

Initial guard:
- `git status --short` was clean before work.
- Handoff was read.
- Existing research report `research_20260709T170636Z` was read.
- Current research code was read before edits.

TDD:
- Tests were added first for:
  - report contains `candidate_leaderboard`,
  - leaderboard contains all candidates,
  - only selected candidate has blindtest metrics,
  - ranking diagnosis declares no blindtest ranking,
  - candidate diagnosis detects negative validation, cost load, too few trades, and overtrading,
  - controlled improvement is deterministic and does not use target as a parameter.
- Targeted tests initially failed because `build_candidate_leaderboard` / `build_candidate_diagnosis` did not exist.

Implementation:
- `research_runner.py` now creates candidate ids and stores a full leaderboard.
- Leaderboard fields include candidate_id, family, params, training_metrics, validation_metrics, rank_score, rank_position, why_ranked_here, and weaknesses.
- Blindtest metrics are only embedded on the final selected candidate row.
- `candidate_diagnosis` summarizes best training family, best validation family, lowest-cost family, overtrading families, too-few-trades families, profit-factor-near-one families, and why no candidate is profitable enough.
- `simulator.py` gained optional trailing-stop and break-even-stop exits using only prior closes, not future candles.
- `experiment_registry.py` text report output now includes leaderboard/diagnosis summary.

Controlled improvement:
- Added two controlled candidates using the same exit-improvement idea:
  - trailing stop,
  - break-even stop after favorable movement.
- No broad brute force was added.
- Candidate count increased from 12 to 14.

Real research run:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Run-ID: `research_20260709T181800Z`.
- Reports:
  - `reports/research/research_20260709T181800Z.json`
  - `reports/research/research_20260709T181800Z.txt`
  - `reports/research/index.jsonl`
- Selected candidate: `breakout_volatility_filter_013`.
- Training: -0.0722564539 USDC/day.
- Validation: -0.1363876748 USDC/day.
- Blindtest: -0.0327853251 USDC/day.
- Target +3 USDC/day: not reached.

Leaderboard diagnosis:
- Best training family: breakout_volatility_filter.
- Best validation family: breakout_volatility_filter.
- Lowest-cost family: breakout_volatility_filter.
- Negative validation candidates: 14/14.
- High-cost candidates: 14/14.
- Overtrading candidates: 3.
- Too-few-trades candidates: 0.
- Profit-factor-near-one families: none.
- Interpretation: improvement reduced losses again, but all candidates are still negative in validation; no sufficient edge.

Safety:
- No live, paper, or testtrade.
- No orders.
- No API keys.
- No Binance Trading API.
- No raw data in repo.

## 2026-07-09 - Family aggregates and controlled cost-filter improvement

Timebox: max 240 minutes.

Goal:
- Add family-level aggregates and family diagnosis to research reports.
- Use the all-families high-cost diagnosis for exactly one controlled improvement.

Initial guard:
- `git status --short` was clean before work.
- Handoff was read.
- Existing research report `research_20260709T181800Z` was read.
- Current research code was read before edits.

TDD:
- Tests were added first for:
  - report contains `family_aggregates`,
  - aggregates cover all families,
  - aggregates contain no blindtest metrics,
  - family diagnosis detects best validation family, lowest-cost family, overtrading families, and nearest-to-one profit factor family,
  - controlled cost-filter improvement is deterministic and does not use target as a parameter.
- Targeted tests initially failed because `build_family_aggregates` / `build_family_diagnosis` did not exist.

Implementation:
- `research_runner.py` now writes `family_aggregates` using training/validation metrics only.
- `family_diagnosis` summarizes best training family, best validation family, lowest-cost family, overtrading families, too-few-trades families, profit-factor-nearest-one family, high-cost families, and problem assessment.
- Added two stronger minimum expected move / cost-filter candidates under cooldown_fee_aware:
  - min_expected_move_bps 70,
  - min_expected_move_bps 85.
- Candidate count increased from 14 to 16.
- `experiment_registry.py` text reports now include family diagnosis summary.

Real research run:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes`
- Run-ID: `research_20260709T193221Z`.
- Reports:
  - `reports/research/research_20260709T193221Z.json`
  - `reports/research/research_20260709T193221Z.txt`
  - `reports/research/index.jsonl`
- Candidates: 16.
- Selected candidate remained `breakout_volatility_filter_013`.
- Training: -0.0722564539 USDC/day.
- Validation: -0.1363876748 USDC/day.
- Blindtest: -0.0327853251 USDC/day.
- Target +3 USDC/day: not reached.

Family diagnosis:
- Best training family: breakout_volatility_filter.
- Best validation family: breakout_volatility_filter.
- Lowest-cost family: breakout_volatility_filter.
- Profit-factor-nearest-one family: cooldown_fee_aware.
- High-cost families: all six families.
- Overtrading families: mean_reversion_regime_filter, momentum_trend_filter, pullback_in_trend.
- Too-few-trades families: none.
- Problem assessment: costs_and_insufficient_edge.

Safety:
- No live, paper, or testtrade.
- No orders.
- No API keys.
- No Binance Trading API.
- No raw data in repo.
## 2026-07-09 - Add multi-cycle offline research loop runner

Timebox: max 360 minutes.

Goal:
- Replace one-patch/one-research-run stopping behavior with a reproducible multi-cycle offline research loop.
- Keep ETHUSDC/USDC Binance Spot LONG-only safety rules locked.
- Use training/validation/walk-forward evidence for loop changes and mark blindtest checks as repeated audit-only.

Initial guard:
- `git status --short` was clean before work.
- Required handoff files, latest research report, and current research/backtest code were read before implementation.
- Work stayed inside the allowed file/report/doc/handoff lists.

TDD:
- Tests were added first for search-space determinism/no blindtest leakage, walk-forward chronology/no blindtest ranking, exit-reason cost summaries, multi-cycle loop stops/reports/safety locks, and context-symbol non-trading safety.
- RED was observed as missing new modules.
- Implementation followed the failing tests.

Implementation:
- Added `research_loop_runner.py` CLI for multi-cycle offline loops and reports under `reports/research_loop/`.
- Added `search_space.py` deterministic candidate proposals from validation-only diagnosis.
- Added `walk_forward.py` chronological WFV folds inside training.
- Added `exit_reason_analysis.py` exit-reason/trade-cause summaries.
- Extended simulator exit reasons beyond generic `rule`.
- Added context-filter support as ETHUSDC base-strategy filter only; BTCUSDC/ETHBTC cannot trigger trades.
- Added docs `docs/27_BACKTEST_RESEARCH_LOOP.md` and `docs/28_RESEARCH_LOOP_RESULTS.md`.

Real loop:
- Command: `PYTHONPATH=src python -m ethusdc_bot.backtest.research_loop_runner --raw-root C:/TradingBot/data/ETHUSDC_BotV3_Hermes --max-cycles 8 --max-candidates-per-cycle 40`
- Run-ID: `research_loop_20260709T213134Z`.
- Reports: `reports/research_loop/research_loop_20260709T213134Z.json` and `.txt`.
- Cycles executed: 7 of 8.
- Generated candidate proposals: 77.
- Tested candidate frontier rows: 28.
- Stop reason: `validation_stagnation_3_cycles`.
- Best validation: `breakout_volatility_filter_04_001`, `-0.0004208934 USDC/day`, PF `0.9184698895`, 8 trades.
- Best blindtest audit: `0.0096502748 USDC/day`, PF `1.7538949399`, 11 trades, repeated-audit-only.
- Target +3 USDC/day: not reached.

Safety:
- No Binance Trading API.
- No API keys.
- No orders.
- No live/paper/testtrade unlock.
- No candidate adoption.
- No raw data copied into repo.

Verification:
- Targeted new tests passed.
- `pytest tests/ -q` passed before the real loop.
- Final full suite rerun required after docs/handoff before commit.

## 2026-07-10 - Fix execution-cost accounting and run post-fix control

Goal:
- Correct the confirmed diagnostic Slippage defect without changing strategy parameters.
- Verify every exit path, document the accounting model, and run an unchanged research-loop control.

Initial guard:
- Starting commit: `8ac7003`.
- Worktree was clean before the Slippage fix.
- Existing simulator, research-loop code, tests, handoff, and reference reports were inspected.

TDD and implementation:
- Added hand-checkable regression tests before implementation; 13 expected failures demonstrated the missing/corrupt accounting fields.
- Stored entry and exit mid-prices separately from slipped execution prices.
- Recorded entry/exit fees and entry/exit slippage separately.
- Kept quantity based on the 100 USDC entry execution notional.
- Kept net P&L as execution-price gross P&L minus fees, with no second Slippage deduction.
- Verified end-of-data, take-profit, stop-loss, time-exit, break-even, and trailing-stop through the shared cost path.
- Added `docs/29_BACKTEST_EXECUTION_COST_AUDIT.md`.
- Created commit `03e9db0 Fix backtest execution cost accounting`.

Verification:
- Targeted simulator tests: 23 passed.
- Full suite after the cost correction: 412 passed.

Post-fix control run:
- Run ID: `research_loop_20260710T054549Z`.
- Cycles: 4 of 8.
- Stop reason: `validation_stagnation_3_cycles`.
- Generated/tested candidates per cycle: 11/4.
- Best validation: `-0.0086568356 USDC/day`, PF `0.4915795763`, 17 trades.
- Best recorded audit: `-0.0012839958 USDC/day`, PF `0.9423532464`, 14 trades.
- Target not reached; no candidate adopted.

Methodological decision:
- The repeatedly viewed 365-day window is formally consumed and may not guide selection or optimization.
- Pre-fix slippage-based rankings and cost diagnoses are obsolete.
- The next approved work item is Research Protocol v2 on a separate branch: honest candidate counts, broader deterministic evaluation/WFV, no repeated holdout evaluation, dynamic windows, rolling-origin support, and fixed quality gates.

Safety:
- No strategy changes in this work block.
- No live/paper/testtrade unlock, orders, API keys, account data, shorts, margin, futures, or leverage.

## 2026-07-11 - Implement and verify Research Protocol v2

Goal:

- Replace the leakage-prone research paths with one bounded, dynamic, training-only protocol.
- Preserve the consumed-audit decision and all trading safety locks.

Branch and baseline:

- Started branch `agent/research-protocol-v2` from synchronized `main` at `c73c71d`.
- Existing Slippage fix, control reports, and append-only historical reports were preserved.

Implementation:

- Added exact latest-complete-UTC-day planning for dynamic 730-day training plus 365-day final-holdout metadata.
- Added exact 1,440-candle UTC-day raster validation; partial and gap-compensated days fail closed.
- Added consumed-ledger exclusion for every selection-bearing training, validation, WFV, and historical-origin slice.
- Removed final-holdout evaluation from the research loop.
- Added honest generated/tested/WFV/finalist IDs and caps of 40/12/3/2.
- Replaced the fixed-prefix candidate frontier with deterministic family-balanced selection.
- Added multi-candidate, six-fold, complete-day WFV using day-weighted aggregate metrics.
- Labelled fixed-candidate historical replay as diagnostic and ineligible for selection/gates.
- Added immutable `quality_gate_v1`, fold/aggregate consistency checks, mark-to-market drawdown requirements, and fail-closed missing/invalid evidence.
- Bound passing gates to finalist IDs and canonical parameter signatures before freeze.
- Added explicit candidate-day and candle-evaluation work caps.
- Disabled both legacy execution paths that repeatedly evaluated holdout data.

Verification:

- Independent review found and drove fixes for partial days, consumed training overlap, mismatched freeze candidates, forged gates, WFV aggregate poisoning, incomplete safety payloads, inconsistent ranking, and active legacy bypasses.
- A six-day non-production fixture exercised the real Protocol-v2 runner path.
- A separate synthetic production-orchestration wiring test exercised canonical 40/12/3/2 budgets, six WFV folds, and three origin slots.
- Simulator spies confirmed neither path evaluated a planned final-holdout candle.
- Full collection: 505 tests.
- Full result: 505 passed with Python 3.12.
- `git diff --check` passed.
- No production historical research loop and no sealed-holdout evaluation were run.

Gate outcome:

- No candidate frozen or adopted.
- Current closed-trade drawdown is explicitly rejected where mark-to-market drawdown is required.
- Missing rolling-refit, concentration, parameter-stability, stress, temporal, and regime evidence blocks freeze.
- `+3 USDC/day` was not evaluated under Protocol v2.

Safety:

- Live, Paper, and Testtrade remained locked.
- No Trading API, API keys, account data, or orders.
- ETHUSDC Spot LONG-only, fixed 100 USDC notional, no compounding, one position maximum.
- No shorts, margin, futures, or leverage.

## 2026-07-12 - Audit canonical UI path and rotate existing search profiles

Goal:

- Prove which PR #3-#14 patches are active in the normal UI backtest.
- Diagnose the completed PR12 context run before changing parameters.
- Fix only the smallest demonstrated Search Frontier selection/feedback defect.

Read-only audit:

- Main worktree was clean at PR #14 head `5f6eb9030d44856ccb41f94d0fed3bab68fe8954`.
- The UI14 worktree was clean and fully ancestral; no unique work was removed.
- Every runtime-relevant head from PR #3 through #12 plus the PR12 UI bridge is an ancestor of PR #14. PR #13 is report-only and intentionally not in the stack.
- The button reaches one chain only: `START_DASHBOARD.bat` -> dashboard -> controller -> PowerShell starter -> supervisor -> Protocol-v2 runner -> simulator.
- Legacy runners are fail-closed. No second UI-reachable backtest engine exists.

Run diagnosis:

- `production_research_supervisor_20260712T081650Z` completed 8/8 with 40/12/3/2 and context enabled.
- Selected WFV result: 27 trades over 546 days, -0.0261580516 USDC/day, PF 0.3102933291, max drawdown 16.5273477065 USDC.
- Fold trades were 3/4/3/1/15/1; all trades belonged to one regime and the maximum no-trade gap was 136 days.
- Exactly 1095 complete days explain the real zero historical origins; there is no parser error.
- Search generation truncated a sequential 49-row context frontier to 40 and tested the same early family profiles. The capped pressure made cycles 6-8 identical.
- Feedback used the best-validation trade count instead of selected-WFV activity and therefore increased filtering despite the activity shortfall.

Implementation:

- Created `codex/canonical-backtest-audit-and-consolidation` from PR #14 head.
- Added deterministic per-cycle profile rotation and rotating extra slots among the six base families.
- Kept the context family pinned so every cycle retains exactly 6 generated and 2 tested context candidates.
- Bound the existing `too_few_trades` feedback to selected WFV total trades and temporal no-trade gap using immutable `quality_gate_v1` thresholds.
- The existing opening profile now removes diagnosis pressure when activity is insufficient; no strategy family or gate changed.
- Implementation commit `3299a4f879e2737b1166adc1db37f155fe4315e3` was pushed to `origin/codex/canonical-backtest-audit-and-consolidation`.
- Draft PR #15 was opened against `review/backtest-ui-live-status-v1`.

Review and verification:

- Initial regression run produced five expected failures before implementation.
- A focused review found that unrestricted family rotation would break context 6/2 after cycle 1; this was fixed before commit.
- Final focused selection/runner/context/Protocol-v2 set: 59 passed.
- Full suite: 850 passed with Python 3.12.
- Python compile, PowerShell parser, and `git diff --check`: passed.
- Deterministic eight-cycle smoke: every cycle 40 generated / 12 tested / context 6/2, 12 unique tested signatures, eight distinct tested-signature sets.
- No market-data backtest, audit, or final holdout was run in this work block.

Safety:

- Fixed 100 USDC, LONG-only, one position, no compounding, 0.1% fee and 5 bps slippage per side unchanged.
- Live, Paper, Testtrade, orders, API keys, account access, and Trading API remained locked or unused.

## 2026-07-12 - Complete rotated run and remove dashboard multi-GB hot path

Run result:

- Canonical UI run `production_research_supervisor_20260712T163528Z` / `research_loop_20260712T163528Z` completed normally after 7/8 cycles with `selection_stagnation_3_cycles`.
- Every cycle proved 40 generated / 12 tested / 3 WFV / 2 finalists, context 6/2, six folds, audit false, final holdout false, and all trading locks.
- Profile offsets 0-6 were exercised. The selected family changed to `cooldown_fee_aware` in cycles 6-7, proving that rotation expanded the tested frontier.
- Best selected WFV: `breakout_volatility_filter_04_012`, +6.875145713 USDC total, +0.012591842/day, 28 trades, PF 1.4688289221, 50% wins, 6.3883786063 USDC drawdown.
- Fees/slippage: 5.6124876333 / 2.8062476402 USDC. Fold trades: 4/4/2/2/12/4. Positive folds: 3. Worst fold: -0.0185551606/day. No-trade gap: 135 days.
- Versus the prior run, net/day, PF, drawdown, win rate, positive folds, and worst-fold loss improved; raw activity remained nearly unchanged.

UI diagnosis and fix:

- Research runner and supervisor had exited cleanly; only the dashboard appeared hung/off-screen.
- Dashboard PID 15468 had accumulated about 8888 CPU seconds. Its window rectangle was `-32000,-32000`; it was restored non-destructively to `40,40` after completion.
- The one-second heartbeat ran `build_dashboard_snapshot()` on Tk's thread. Frozen-report discovery called `read_text()` plus `json.loads()` for every research JSON, including 3.74 GB and 3.23 GB artifacts. Completion also streamed the latest detail report synchronously on Tk's thread.
- Commit `5ef7eb8c0283ab67f89b249a274637d465cea8a3` moves snapshot/result collection to a background refresh worker, bounds large-report discovery, uses compact TXT for fast non-frozen rejection, and recovers a durable active supervisor checkpoint to prevent duplicate starts after UI restart.
- Real-root frozen discovery dropped to about 0.003 seconds without reading either detail report as a whole.

Verification:

- Focused UI/controller/display tests: 51 passed.
- Full suite: 854 tests passed.
- Python compile and `git diff --check`: passed.
- No final holdout, Live, Paper, Testtrade, order, account, API key, or Trading API action occurred.
