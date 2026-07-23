"""Fail-closed historical import and completion gates for the trial ledger.

A mere count must never clear ``historical_trial_count_is_lower_bound``.  This
module requires a digest-bound reconciliation of every previously observed
legacy evaluation row.  It also treats byte-identical report copies as visible
reuse rather than independent trials.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .trial_ledger import (
    HistoricalImportResult,
    TrialLedgerError,
    TrialLedgerSnapshot,
    attest_complete_trial_inventory as _attest_complete_trial_inventory,
    build_historical_reconciliation_evidence_sha256,
    build_trial_inventory_evidence_sha256,
    import_historical_reports as _import_historical_reports,
    read_trial_ledger,
)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def import_historical_reports(
    root: str | Path,
    report_paths: Iterable[str | Path],
) -> HistoricalImportResult:
    """Import reports once per byte digest and report later copies as reuse."""

    ledger_root = Path(root)
    sources = _expand_json_paths(report_paths)
    imported = 0
    reused = 0
    skipped = 0
    observed = 0
    for source in sources:
        source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        snapshot = read_trial_ledger(ledger_root)
        existing = next(
            (
                event["payload"]
                for event in snapshot.events
                if event.get("event_type") == "historical_import_summary"
                and isinstance(event.get("payload"), dict)
                and event["payload"].get("source_sha256") == source_sha256
            ),
            None,
        )
        if existing is not None:
            reused += int(existing.get("imported_identity_rows", 0))
            skipped += int(existing.get("skipped_identity_rows", 0))
            observed += int(existing.get("observed_evaluation_rows", 0))
            continue
        result = _import_historical_reports(ledger_root, [source])
        imported += result.imported_trial_count
        reused += result.reused_trial_count
        skipped += result.skipped_candidate_count
        observed += result.observed_evaluation_rows
    after = read_trial_ledger(ledger_root)
    return HistoricalImportResult(
        source_count=len(sources),
        imported_trial_count=imported,
        reused_trial_count=reused,
        skipped_candidate_count=skipped,
        observed_evaluation_rows=observed,
        event_count_after=after.status.event_count,
    )


def attest_complete_trial_inventory(
    root: str | Path,
    *,
    expected_resolved_trial_count: int,
    inventory_sha256: str,
    attestor: str,
    historical_reconciliation: Mapping[str, Any],
) -> TrialLedgerSnapshot:
    """Clear the lower-bound flag only after full legacy-row reconciliation."""

    snapshot = read_trial_ledger(root)
    _validate_historical_reconciliation(snapshot, historical_reconciliation)
    if not isinstance(inventory_sha256, str) or not _HEX64_RE.fullmatch(
        inventory_sha256
    ):
        raise TrialLedgerError("inventory_sha256 must be a lowercase SHA-256")
    expected_inventory_sha256 = build_trial_inventory_evidence_sha256(
        snapshot
    )
    if inventory_sha256 != expected_inventory_sha256:
        raise TrialLedgerError(
            "inventory_sha256 does not match the immutable ledger inventory"
        )
    return _attest_complete_trial_inventory(
        root,
        expected_resolved_trial_count=expected_resolved_trial_count,
        inventory_sha256=inventory_sha256,
        reconciliation_sha256=historical_reconciliation[
            "observation_mapping_sha256"
        ],
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
            raise TrialLedgerError(
                f"{field_name} must be a non-negative integer"
            )
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
    if duplicates != 0 or resolved != observed:
        raise TrialLedgerError(
            "duplicate/cache claims cannot clear history without immutable "
            "per-row mapping evidence"
        )
    if value.get("all_observed_rows_mapped") is not True:
        raise TrialLedgerError("all observed historical rows must be mapped")
    if value.get("all_historical_daily_series_complete") is not True:
        raise TrialLedgerError(
            "every resolved historical trial requires a causal daily series"
        )
    mapping_digest = value.get("observation_mapping_sha256")
    if not isinstance(mapping_digest, str) or not _HEX64_RE.fullmatch(
        mapping_digest
    ):
        raise TrialLedgerError(
            "observation_mapping_sha256 must be a lowercase SHA-256"
        )
    expected_mapping_digest = (
        build_historical_reconciliation_evidence_sha256(snapshot)
    )
    if mapping_digest != expected_mapping_digest:
        raise TrialLedgerError(
            "observation mapping digest does not match ledger provenance"
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
    incomplete_historical = [
        trial_id
        for trial_id, trial in snapshot.trials.items()
        if trial["identity_basis"]["source_kind"] == "historical_import"
        and (
            not isinstance(trial.get("completeness"), Mapping)
            or any(
                trial["completeness"].get(field) is not True
                for field in (
                    "candidate_identity_complete",
                    "seed_complete",
                    "versions_complete",
                    "code_commit_complete",
                    "daily_series_complete",
                )
            )
            or trial["completeness"].get("missing_fields") != []
        )
    ]
    if incomplete_historical:
        raise TrialLedgerError(
            "historical reconciliation cannot complete while identity or "
            "daily-series fields remain unresolved"
        )


def _expand_json_paths(paths: Iterable[str | Path]) -> list[Path]:
    expanded: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            expanded.extend(sorted(path.rglob("*.json")))
        elif path.is_file():
            expanded.append(path)
        else:
            raise TrialLedgerError(
                f"historical report path does not exist: {path}"
            )
    unique = sorted({path.resolve() for path in expanded})
    if not unique:
        raise TrialLedgerError("no historical JSON reports were found")
    return unique


__all__ = [
    "attest_complete_trial_inventory",
    "build_historical_reconciliation_evidence_sha256",
    "build_trial_inventory_evidence_sha256",
    "import_historical_reports",
]
