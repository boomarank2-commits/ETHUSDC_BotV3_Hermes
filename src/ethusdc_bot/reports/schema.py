"""Strict schema validation for Phase 1 report summary placeholders."""

from collections.abc import Mapping
from typing import Any

from ethusdc_bot.validation import (
    SchemaValidationError,
    require_exact_keys,
    require_false,
    require_literal,
    require_mapping,
    require_non_empty_string,
)


REPORT_SUMMARY_PLACEHOLDER_KEYS = {
    "schema_version",
    "template",
    "status",
    "candidate_adoptable",
    "reason",
}
SUCCESS_STATUSES = {"success", "passed", "profitable", "candidate_ready"}
FORBIDDEN_REPORT_FIELDS = {
    "profit_usdc",
    "net_usdc_per_day",
    "winrate",
    "profit_factor",
    "best_candidate",
    "adopted_candidate",
    "trades",
    "trade_count",
    "real_trades",
    "engine_entry_attempts",
}


def validate_report_summary_placeholder(data: Mapping[str, Any]) -> None:
    """Validate a report summary placeholder without allowing fake results."""

    root = require_mapping(data, "report_summary_placeholder")
    forbidden_present = sorted(FORBIDDEN_REPORT_FIELDS & set(root.keys()))
    if forbidden_present:
        raise SchemaValidationError(
            "report_summary_placeholder contains forbidden result fields: "
            f"{forbidden_present}"
        )

    status = root.get("status")
    if isinstance(status, str) and status in SUCCESS_STATUSES:
        raise SchemaValidationError(
            "report_summary_placeholder.status must not claim success"
        )

    require_exact_keys(
        root, REPORT_SUMMARY_PLACEHOLDER_KEYS, "report_summary_placeholder"
    )
    require_literal(root, "schema_version", 1, "report_summary_placeholder")
    require_literal(root, "template", True, "report_summary_placeholder")
    require_literal(root, "status", "placeholder_only", "report_summary_placeholder")
    require_false(root, "candidate_adoptable", "report_summary_placeholder")
    require_non_empty_string(root, "reason", "report_summary_placeholder")
