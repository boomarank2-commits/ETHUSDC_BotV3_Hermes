"""Fail-closed completion gate for the permanent trial history.

The append-only ledger can store historical identities and later evidence, but a
mere count must never clear ``historical_trial_count_is_lower_bound``.  This
wrapper requires a digest-bound reconciliation of every previously observed
legacy evaluation row before the inventory may be attested complete.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .trial_ledger import (
    TrialLedgerError,
    TrialLedgerSnapshot,
    attest_complete_trial_inventory as _attest_complete_trial_inventory,
    read_trial_ledger,
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def attest_complete_trial_inventory(
    root: str,
    *,
    expected_resolved_trial_count: int,
    inventory_sha256: str,
    attestor: str,
    historical_reconciliation: Mapping[str, Any],
) -> TrialLedgerSnapshot:
    """Clear the lower-bound flag only after full legacy-row reconciliation."""

    snapshot = read_trial_ledger(root)
    _validate_historical_reconciliation(snapshot, historical_reconciliation)
    return _attest_complete_trial_inventory(
        root,
        expected_resolved_trial_count=expected_resolved_trial_count,
        inventory_sha256=inventory_sha256,
        attestor=attestor,
    )


def _validate_historical_reconciliation(
    snapshot: TrialLedgerSnapshot,
    value: Mapping[str, Any],
) -> None:
    required = {
        "all_observed_rows_mapped",
        "all_historical_daily_series_complete",
        "duplicate_or_cache_row_count",
        "mapped_observed_evaluation_rows",
        "observation_mapping_sha256",
        "resolved_historical_trial_count",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise TrialLedgerError(
            "historical reconciliation fields are missing or unexpected"
        )
    observed = snapshot.status.known_observed_historical_evaluation_rows
    resolved = snapshot.status.historical_resolved_trial_count
    mapped = value.get("mapped_observed_evaluation_rows")
    resolved_claim = value.get("resolved_historical_trial_count")
    duplicates = value.get("duplicate_or_cache_row_count")
    for field_name, field_value in (
        ("mapped_observed_evaluation_rows", mapped),
        ("resolved_historical_trial_count", resolved_claim),
        ("duplicate_or_cache_row_count", duplicates),
    ):
        if (
            isinstance(field_value, bool)
            or not isinstance(field_value, int)
            or field_value < 0
        ):
            raise TrialLedgerError(f"{field_name} must be a non-negative integer")
    if mapped != observed:
        raise TrialLedgerError(
            "historical reconciliation must map every observed evaluation row"
        )
    if resolved_claim != resolved:
        raise TrialLedgerError(
            "historical reconciliation resolved count differs from ledger"
        )
    if resolved + duplicates != observed:
        raise TrialLedgerError(
            "resolved plus duplicate/cache rows must equal observed rows"
        )
    if value.get("all_observed_rows_mapped") is not True:
        raise TrialLedgerError("all observed historical rows must be mapped")
    if value.get("all_historical_daily_series_complete") is not True:
        raise TrialLedgerError(
            "every resolved historical trial requires a causal daily series"
        )
    mapping_digest = value.get("observation_mapping_sha256")
    if not isinstance(mapping_digest, str) or not _HEX64_RE.fullmatch(mapping_digest):
        raise TrialLedgerError(
            "observation_mapping_sha256 must be a lowercase SHA-256"
        )
    missing_historical = [
        trial_id
        for trial_id in snapshot.status.missing_daily_series_trial_ids
        if snapshot.trials[trial_id]["identity_basis"]["source_kind"]
        == "historical_import"
    ]
    if missing_historical:
        raise TrialLedgerError(
            "historical reconciliation cannot complete while daily series are missing"
        )


__all__ = ["attest_complete_trial_inventory"]
