"""Local data inventory status command without downloads.

The command loads the data catalog template, checks expected local source paths,
and prints an honest inventory status. It does not read market data contents,
download data, call Binance, run a strategy, execute a backtest, start a UI, or
produce real/fake reports.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
import tomllib

from ethusdc_bot.data_pipeline.inventory import scan_local_inventory


DEFAULT_LOCAL_ROOT = "C:/TradingBot/data/ETHUSDC_BotV3_Hermes"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CATALOG_PATH = REPOSITORY_ROOT / "config" / "data_catalog.example.toml"
SAFETY_NOTICE = (
    "no download; no Binance API; no market data read; no backtest; "
    "live/paper/testtrade locked"
)


def load_data_catalog(path: str | Path) -> dict[str, Any]:
    """Load a TOML data catalog from disk without reading market data."""

    catalog_path = Path(path)
    return tomllib.loads(catalog_path.read_text(encoding="utf-8"))


def build_inventory_status(
    catalog_path: str | Path = DEFAULT_CATALOG_PATH,
    local_root: str | Path = DEFAULT_LOCAL_ROOT,
    repository_root: str | Path = REPOSITORY_ROOT,
) -> dict[str, Any]:
    """Build an honest path-only local inventory status."""

    catalog = load_data_catalog(catalog_path)
    inventory = scan_local_inventory(catalog, local_root, repository_root)
    counts = _count_source_statuses(inventory["sources"])

    return {
        "schema_version": 1,
        "status_type": "local_data_inventory_status",
        "catalog_path": str(Path(catalog_path)),
        "local_root": inventory["local_root"],
        "repository_root": inventory["repository_root"],
        "overall_status": inventory["status"],
        "quality_status": inventory["quality_status"],
        "counts": counts,
        "inventory": inventory,
        "safety_notice": SAFETY_NOTICE,
    }


def format_inventory_status_text(status: Mapping[str, Any]) -> str:
    """Format inventory status as human-readable terminal text."""

    counts = status["counts"]
    inventory = status["inventory"]
    lines = [
        "Local Data Inventory Status",
        f"local_root: {status['local_root']}",
        f"repository_root: {status['repository_root']}",
        f"overall status: {status['overall_status']}",
        f"quality_status: {status['quality_status']}",
        (
            "sources total: "
            f"{counts['total']} | missing: {counts['missing']} | "
            f"present: {counts['present']} | blocked: {counts['blocked']}"
        ),
        "status legend: missing, present, blocked, unknown, partial",
        f"safety: {status['safety_notice']}",
        "sources:",
    ]
    for source in inventory["sources"]:
        lines.extend(
            [
                f"- source_id: {source['source_id']}",
                f"  symbol: {source['symbol']}",
                f"  role: {source['role']}",
                f"  data_type: {source['data_type']}",
                f"  expected_path: {source['expected_path']}",
                f"  status: {source['status']}",
                f"  quality_status: {source['quality_status']}",
                f"  may_trigger_orders: {str(source['may_trigger_orders']).lower()}",
            ]
        )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Run the inventory status command."""

    parser = argparse.ArgumentParser(
        description="Show local data inventory status without downloads."
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG_PATH),
        help="Path to data_catalog.example.toml",
    )
    parser.add_argument(
        "--local-root",
        default=DEFAULT_LOCAL_ROOT,
        help="Local raw data root outside the repository",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of text",
    )
    args = parser.parse_args(argv)

    status = build_inventory_status(args.catalog, args.local_root, REPOSITORY_ROOT)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
    else:
        print(format_inventory_status_text(status), end="")
    return 0


def _count_source_statuses(sources: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"total": len(sources), "missing": 0, "present": 0, "blocked": 0, "unknown": 0}
    for source in sources:
        source_status = source["status"]
        if source_status in counts:
            counts[source_status] += 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
