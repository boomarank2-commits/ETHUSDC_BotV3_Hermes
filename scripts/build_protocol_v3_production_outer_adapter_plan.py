"""Create a real-data Protocol-v3 production outer-adapter plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ethusdc_bot.protocol_v3.production_outer_adapter import (
    build_production_outer_adapter_plan,
    write_production_outer_adapter_plan,
)
from ethusdc_bot.protocol_v3.task33_preflight import (
    validate_task33_preflight_report,
)
from ethusdc_bot.protocol_v3.trial_ledger import read_trial_ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--preflight-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()

    report = validate_task33_preflight_report(
        json.loads(args.preflight_report.read_text(encoding="utf-8"))
    ).to_dict()
    plan = build_production_outer_adapter_plan(
        repo_root=args.repo_root,
        raw_root=args.raw_root,
        data_snapshot=report["data"],
        exchange_info_snapshot=report["exchange_info"],
        trial_ledger=read_trial_ledger(args.ledger_root),
        code_commit=args.code_commit,
    )
    target = write_production_outer_adapter_plan(
        plan,
        args.output,
        repo_root=args.repo_root,
    )
    print(json.dumps({"output": str(target), **plan.to_dict()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
