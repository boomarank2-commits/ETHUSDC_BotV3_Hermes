# Current Status

Updated: 2026-07-12

Repository state:

- Active branch: `codex/canonical-backtest-audit-and-consolidation`
- Branch base: `5f6eb9030d44856ccb41f94d0fed3bab68fe8954` (PR #14 head)
- Verified implementation commit: `3299a4f879e2737b1166adc1db37f155fe4315e3` (pushed)
- Draft PR: #15, `Rotate bounded research profiles across cycles`, stacked onto `review/backtest-ui-live-status-v1`
- PR #14 CI run `29191047437`: successful, 846 tests on the PR14 head.
- Current local verification after the search patch: 850 tests passed; Python compile, PowerShell parse, and `git diff --check` passed.

Canonical user path:

`START_DASHBOARD.bat`
-> `ethusdc_bot.ui.dashboard`
-> `TrainingResearchController`
-> `tools/run_production_research.ps1`
-> `ethusdc_bot.backtest.research_supervisor`
-> `ethusdc_bot.backtest.research_loop_runner`
-> the single ETHUSDC simulator.

No V1/legacy runner is reachable from the UI button. Legacy public entry points remain fail-closed. Direct PowerShell/Supervisor/Runner invocations are internal or diagnostic surfaces, not a second algorithm.

Last completed production-selection run:

- Supervisor run ID: `production_research_supervisor_20260712T081650Z`
- Runner run ID: `research_loop_20260712T081650Z`
- Supervisor branch/commit: `codex/pr12-final-local-run` / `c42cfd504c50d30e42c2e4b958068831d61df444`; der kanonische Runner-TXT-Bericht weist intern `c4b9254ac2671ab627dc8c30d6c7b5233a8c18a4` aus. Diese Provenienzabweichung bleibt dokumentiert.
- Status: completed, 8/8 cycles, `max_cycles_reached`
- Totals: 320 generated / 96 tested / 24 WFV / 16 finalists
- Selected: `breakout_volatility_filter_06_009`
- WFV: -14.282296193 USDC total, -0.0261580516 USDC/day, 27 trades, PF 0.3102933291, win rate 22.22%, max drawdown 16.5273477065 USDC
- Costs: 5.3911088127 USDC fees plus 2.6955528573 USDC slippage
- Best validation: -0.0205462855 USDC/day, 21 trades, PF 0.7558196835
- Rolling origins: zero actually executed because exactly 1095 days provide no older 730+365 window
- Quality gate: failed; no qualified finalist; final holdout not evaluated

Proven bottleneck and current patch:

- The selected WFV candidate traded only 3/4/3/1/15/1 times across six folds and had a 136-day no-trade gap.
- The old 40/12 selector always tested the same earliest profiles; 28 generated rows per cycle were skipped and cycles 6-8 repeated identical signatures.
- The old feedback examined best-validation activity before selected-WFV activity and answered the low-activity result with higher thresholds and longer cooldowns.
- The patch rotates existing profile starts and base-family extra slots across cycles while preserving 40/12 and the mandatory context 6 generated / 2 tested contract.
- WFV activity and temporal gap now select the existing `too_few_trades` opening path before cost pressure. No family, gate, cost, holdout, target, or simulator rule was added or relaxed.

Safety status:

- ETHUSDC Spot LONG-only; fixed 100 USDC; one position; no compounding.
- 0.1% fee and 5 bps slippage per side remain unchanged.
- BTCUSDC and ETHBTC remain aligned context-only markets and cannot create a trade.
- Audit and final holdout remain closed.
- Live, Paper, Testtrade, orders, trading API, account access, and API keys remain locked or unused.
