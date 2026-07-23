# UI backtest checkpoint

- Branch: `codex/research-resume-and-ui-state-v1`
- Dashboard/UI commit at start: `4eb2dbb`
- Run-ID: `production_research_supervisor_20260713T061220Z`
- Backtest started through `START_DASHBOARD.bat` and the UI button: yes
- Completion: 7 of 8 cycles, stopped regularly with `selection_stagnation_3_cycles`
- `generated/tested/walk_forward/finalists`: `280/84/21/14` total; `40/12/3/2` in every completed cycle
- Context research: enabled (UI shows context active; BTCUSDC/ETHBTC context only)
- Audit evaluated: false
- Final holdout evaluated: false
- Orders/live/paper/testtrade: none; safety locks remain active
- Checkpoint: `C:\TradingBot\data\ETHUSDC_BotV3_Hermes\runtime\reports\research_loop\production_research_supervisor_20260713T061220Z.checkpoint.json`
- Console log: `C:\TradingBot\data\ETHUSDC_BotV3_Hermes\runtime\reports\research_loop\production_research_20260713T061158Z.console.log`

The run completed under the PR-12 production research path. See
`analysis_20260713T061220Z.md` and `candidate_evidence_20260713T061220Z.json`
for the small GitHub-ready analysis package. No strategy or engine changes were
made while the research was running.
