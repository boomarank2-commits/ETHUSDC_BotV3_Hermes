"""Run one real, order-free Protocol-v3 inner origin/cycle."""

from __future__ import annotations

import argparse
from datetime import timedelta
import json
from pathlib import Path

from ethusdc_bot.backtest.data_loader import load_aligned_market_candles
from ethusdc_bot.protocol_v3.boundaries import (
    build_monthly_process_boundary_plan,
)
from ethusdc_bot.protocol_v3.inner_folds import (
    build_inner_fold_plan_for_origin,
)
from ethusdc_bot.protocol_v3.production_inner_cycle import (
    execute_production_inner_cycle,
    write_production_inner_cycle_result,
)
from ethusdc_bot.protocol_v3.production_runtime import (
    load_production_runtime_inputs,
)
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy
from ethusdc_bot.protocol_v3.task33_preflight import (
    validate_task33_preflight_report,
)


def _required_context_days(plan):
    """Return the complete development window required by finalist quality."""

    return (
        plan.training_start_inclusive_utc.date(),
        plan.training_end_exclusive_utc.date() - timedelta(days=1),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--origin-index", type=int, required=True)
    parser.add_argument("--cycle-index", type=int, required=True)
    args = parser.parse_args()

    report = validate_task33_preflight_report(
        json.loads(args.preflight_report.read_text(encoding="utf-8"))
    ).to_dict()
    runtime = load_production_runtime_inputs(args.repo_root)
    policy = HorizonPolicy(**runtime["horizon_policy"])
    process_end = report["data"]["boundary"]["process_end_exclusive"]
    boundary = build_monthly_process_boundary_plan(process_end)
    if not 1 <= args.origin_index <= len(boundary.origins):
        parser.error("--origin-index must be in 1..12")
    origin = boundary.origins[args.origin_index - 1]
    plan = build_inner_fold_plan_for_origin(
        origin, policy, repo_root=args.repo_root
    )
    start, end = _required_context_days(plan)
    context = load_aligned_market_candles(
        args.raw_root,
        start_day=start,
        end_day=end,
    )
    result = execute_production_inner_cycle(
        repo_root=args.repo_root,
        context=context,
        fold_plan=plan,
        exchange_info_snapshot=report["exchange_info"],
        horizon_policy=policy,
        trial_ledger_root=args.ledger_root,
        origin_index=args.origin_index,
        cycle_index=args.cycle_index,
        code_commit=args.code_commit,
    )
    target = write_production_inner_cycle_result(result, args.output)
    payload = result.to_dict()
    print(
        json.dumps(
            {
                "output": str(target),
                "result_sha256": result.result_sha256,
                "origin_index": payload["origin_index"],
                "cycle_index": payload["cycle_index"],
                "best_candidate": max(
                    payload["candidate_summaries"],
                    key=lambda row: (
                        row["net_usdc_per_day"],
                        row["candidate_id"],
                    ),
                ),
                "pbo_state": payload["pbo"]["state"],
                "development_pbo": payload["pbo"]["development_pbo"],
                "trial_ledger_head_sha256": payload[
                    "trial_ledger_head_sha256"
                ],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
