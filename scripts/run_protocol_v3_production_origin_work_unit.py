"""Execute or resume one complete real Protocol-v3 origin."""

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
from ethusdc_bot.protocol_v3.pipeline import build_pipeline_generation
from ethusdc_bot.protocol_v3.production_origin_work_unit import (
    execute_production_origin_work_unit,
)
from ethusdc_bot.protocol_v3.production_runtime import (
    load_production_runtime_inputs,
)
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy
from ethusdc_bot.protocol_v3.task33_preflight import (
    BLOCKED_INPUTS,
    READY,
    validate_task33_preflight_report,
)

_SOLE_ADAPTER_BLOCKER = ["MISSING_PRODUCTION_OUTER_ORIGIN_ADAPTER"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--origin-index", type=int, required=True)
    args = parser.parse_args()

    repo = args.repo_root.resolve(strict=True)
    report = validate_task33_preflight_report(
        json.loads(args.preflight_report.read_text(encoding="utf-8"))
    ).to_dict()
    generation = build_pipeline_generation(repo)
    adapter_remediation = (
        report["status"] == BLOCKED_INPUTS
        and report["blockers"] == _SOLE_ADAPTER_BLOCKER
    )
    if (
        (report["status"] != READY and not adapter_remediation)
        or report["code_commit"] != args.code_commit
        or report["pipeline_generation_id"] != generation.generation_id
    ):
        parser.error(
            "preflight is neither READY nor blocked solely by this adapter, "
            "or differs from current code/pipeline"
        )
    runtime = load_production_runtime_inputs(repo)
    policy = HorizonPolicy(**runtime["horizon_policy"])
    boundary = build_monthly_process_boundary_plan(
        report["data"]["boundary"]["process_end_exclusive"]
    )
    if not 1 <= args.origin_index <= len(boundary.origins):
        parser.error("--origin-index must be in 1..12")
    origin = boundary.origins[args.origin_index - 1]
    plan = build_inner_fold_plan_for_origin(
        origin, policy, repo_root=repo
    )
    start = plan.training_start_inclusive_utc.date()
    end = plan.training_end_exclusive_utc.date() - timedelta(days=1)
    context = load_aligned_market_candles(
        args.raw_root,
        start_day=start,
        end_day=end,
    )
    result = execute_production_origin_work_unit(
        repo_root=repo,
        context=context,
        fold_plan=plan,
        boundary_plan=boundary,
        data_snapshot=report["data"],
        exchange_info_snapshot=report["exchange_info"],
        horizon_policy=policy,
        trial_ledger_root=args.ledger_root,
        initial_trial_ledger_status=report["trial_ledger"],
        origin_index=args.origin_index,
        code_commit=args.code_commit,
    )
    selection = result.origin_selection.to_dict()
    print(
        json.dumps(
            {
                "origin_index": result.origin_index,
                "cycle_result_paths": [
                    str(path) for path in result.cycle_result_paths
                ],
                "resumed_cycle_count": result.resumed_cycle_count,
                "origin_selection_path": str(
                    result.origin_selection_path
                ),
                "origin_selection_sha256": selection["result_sha256"],
                "outcome": selection["outcome"],
                "selected_cycle_index": selection[
                    "selected_cycle_index"
                ],
                "selected_candidate": selection["selected_candidate"],
                "development_pbo": selection["pbo_summary"][
                    "development_pbo"
                ],
                "trial_ledger_head_sha256": selection[
                    "trial_ledger_head_sha256"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
