# Current Status

Updated: 2026-07-12

Repository state:

- Active branch: `codex/ui-responsiveness-and-next-iteration`
- Branch base: `08bd555ece20b472a72196844954be7360309207` (PR #15 head)
- UI responsiveness implementation: `5ef7eb8c0283ab67f89b249a274637d465cea8a3`
- Draft PR #15 remains the completed profile-rotation block; the current branch is the next stacked block.
- PR #14 CI run `29191047437`: successful, 846 tests on the PR14 head.
- Current local verification: 854 tests passed; Python compile and `git diff --check` passed.

Canonical user path:

`START_DASHBOARD.bat`
-> `ethusdc_bot.ui.dashboard`
-> `TrainingResearchController`
-> `tools/run_production_research.ps1`
-> `ethusdc_bot.backtest.research_supervisor`
-> `ethusdc_bot.backtest.research_loop_runner`
-> the single ETHUSDC simulator.

No V1/legacy runner is reachable from the UI button. Legacy public entry points remain fail-closed. Direct PowerShell/Supervisor/Runner invocations are internal or diagnostic surfaces, not a second algorithm.

Latest completed production-selection run:

- Supervisor run ID: `production_research_supervisor_20260712T163528Z`
- Runner run ID: `research_loop_20260712T163528Z`
- Branch/commit: `codex/canonical-backtest-audit-and-consolidation` / `08bd555ece20b472a72196844954be7360309207`
- Status: completed normally after 7/8 cycles, `selection_stagnation_3_cycles`
- Totals: 280 generated / 84 tested / 21 WFV / 14 finalists; every cycle kept 40/12/3/2 and context 6/2.
- Selected: `breakout_volatility_filter_04_012`
- WFV: +6.875145713 USDC total, +0.012591842 USDC/day, 28 trades, PF 1.4688289221, win rate 50%, max drawdown 6.3883786063 USDC
- Costs: 5.6124876333 USDC fees plus 2.8062476402 USDC slippage
- Folds: 4/4/2/2/12/4 trades; three positive folds; worst fold -0.0185551606 USDC/day
- Temporal activity: 12/19 active months, 7/19 positive months, maximum no-trade gap 135 days
- Best validation: `cooldown_fee_aware_07_003`, +0.0288672693 USDC/day, 16 trades, PF 1.3159707518; its WFV was only +0.0037115468 USDC/day.
- Rolling origins: zero actually executed because exactly 1095 days provide no older 730+365 window
- Quality gate: failed; no qualified finalist; final holdout not evaluated

Measured patch effect and current bottleneck:

- Profile offsets 0 through 6 were really exercised, and selected families diversified from breakout to cooldown-fee-aware in cycles 6-7.
- Compared with `research_loop_20260712T081650Z`, WFV net/day improved by 0.0387498936 USDC, PF by 1.158535593, and drawdown by 10.1389691002 USDC.
- Activity did not materially improve: 28 versus 27 trades and 135 versus 136 no-trade days.
- The best selected WFV candidate is positive after costs but remains far below +3 USDC/day (gap -2.987408158) and fails fold-trade, temporal-coverage, concentration, stress, and stability gates.
- The next smallest evidence patch is signal-funnel/rejection attribution in the existing simulator/report. Entry/filter rejection cannot currently be separated well enough to justify another parameter or strategy change.

Dashboard responsiveness fix:

- Root cause: the one-second Tk heartbeat synchronously called `build_dashboard_snapshot`, whose frozen-report discovery fully deserialized every 3.2-3.7 GB JSON; completion then streamed the newest 3.23 GB report on the Tk thread.
- Snapshot and final-report formatting now run on a daemon refresh worker and publish only a small payload back to Tk.
- Non-frozen large reports are rejected from frozen-candidate discovery via their compact TXT status in about 0.003 seconds; genuinely frozen large reports are bounded-streamed once and cached.
- A durable running supervisor checkpoint blocks a second start after UI restart.
- The original dashboard PID was restored without termination from off-screen coordinates `(-32000,-32000)` to `(40,40)` after the research runner had exited cleanly.

Safety status:

- ETHUSDC Spot LONG-only; fixed 100 USDC; one position; no compounding.
- 0.1% fee and 5 bps slippage per side remain unchanged.
- BTCUSDC and ETHBTC remain aligned context-only markets and cannot create a trade.
- Audit and final holdout remain closed.
- Live, Paper, Testtrade, orders, trading API, account access, and API keys remain locked or unused.
