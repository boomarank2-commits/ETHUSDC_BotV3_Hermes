"""Rebuild full cross-cycle evidence for one real Protocol-v3 origin."""

from __future__ import annotations

import argparse
from datetime import timedelta
import json
from pathlib import Path

from ethusdc_bot.protocol_v3.boundaries import (
    build_monthly_process_boundary_plan,
)
from ethusdc_bot.protocol_v3.inner_folds import (
    build_inner_fold_plan_for_origin,
)
from ethusdc_bot.protocol_v3.production_origin_selection import (
    build_production_origin_selection,
    write_production_origin_selection,
)
from ethusdc_bot.protocol_v3.production_runtime import (
    load_production_runtime_inputs,
)
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy
from ethusdc_bot.protocol_v3.task33_preflight import (
    validate_task33_preflight_report,
)
from ethusdc_bot.protocol_v3.trial_ledger import read_trial_ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument(
        "--cycle-result",
        type=Path,
        action="append",
        required=True,
        help="Repeat exactly eight times for cycles 1 through 8.",
    )
    parser.add_argument(
        "--cycle-decision",
        type=Path,
        action="append",
        default=[],
        help="Repeat for validated Task-15 decisions; omitted decisions block.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--origin-index", type=int, required=True)
    args = parser.parse_args()

    report = validate_task33_preflight_report(
        json.loads(args.preflight_report.read_text(encoding="utf-8"))
    ).to_dict()
    runtime = load_production_runtime_inputs(args.repo_root)
    policy = HorizonPolicy(**runtime["horizon_policy"])
    boundary = build_monthly_process_boundary_plan(
        report["data"]["boundary"]["process_end_exclusive"]
    )
    if not 1 <= args.origin_index <= len(boundary.origins):
        parser.error("--origin-index must be in 1..12")
    origin = boundary.origins[args.origin_index - 1]
    plan = build_inner_fold_plan_for_origin(
        origin,
        policy,
        repo_root=args.repo_root,
    )
    if (
        plan.folds[-1].validation_end_exclusive_utc
        - plan.folds[0].validation_start_inclusive_utc
        != timedelta(days=360)
    ):
        parser.error("Task-14 validation union must contain exactly 360 days")
    cycle_results = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.cycle_result
    ]
    cycle_decisions = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in args.cycle_decision
    ]
    result = build_production_origin_selection(
        repo_root=args.repo_root,
        fold_plan=plan,
        trial_ledger=read_trial_ledger(args.ledger_root),
        cycle_results=cycle_results,
        code_commit=args.code_commit,
        cycle_decisions=cycle_decisions,
    )
    target = write_production_origin_selection(result, args.output)
    payload = result.to_dict()
    print(
        json.dumps(
            {
                "output": str(target),
                "result_sha256": payload["result_sha256"],
                "origin_index": payload["origin_index"],
                "profile_count": payload["matrix"]["profile_count"],
                "development_pbo": payload["pbo_summary"][
                    "development_pbo"
                ],
                "state": payload["state"],
                "outcome": payload["outcome"],
                "blockers": payload["blockers"],
                "trial_ledger_head_sha256": payload[
                    "trial_ledger_head_sha256"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
