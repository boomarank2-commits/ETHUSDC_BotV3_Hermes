"""Permanent append-only Protocol v3 trial ledger.

Task 4 records every data-informed evaluation, cache reuse, historical import,
evidence attachment, and inventory attestation as an immutable hash-chained
event. It does not calculate DSR/PBO and does not run market research.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

LEDGER_SCHEMA_VERSION = "protocol_v3_trial_ledger_v1"
EVENT_SCHEMA_VERSION = "protocol_v3_trial_event_v1"
TRIAL_RECORD_SCHEMA_VERSION = "protocol_v3_trial_record_v1"
HISTORICAL_IMPORT_SCHEMA_VERSION = "protocol_v3_historical_trial_lower_bound_v1"
PERMANENT_TRIAL_COUNTER_NAMESPACE = "protocol_v3_permanent_trial_counter_v1"
CANONICAL_HISTORICAL_IMPORT_PATH = Path(
    "configs/protocol_v3_historical_trial_lower_bound.json"
)
DEVELOPMENT_DSR_INSUFFICIENT = "INSUFFICIENT_TRIAL_HISTORY"
DEVELOPMENT_DSR_READY = "READY_FOR_DSR_IMPLEMENTATION"
NO_TRADE = "NO_TRADE"
TRADING_CANDIDATE = "TRADING_CANDIDATE"

_ZERO_HASH = "0" * 64
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_OBSERVATION_KEY_RE = re.compile(r"^observation_sha256:[0-9a-f]{64}$")
_EVENT_NAME_RE = re.compile(
    r"^(?P<sequence>[0-9]{12})_(?P<digest>[0-9a-f]{64})\.json$"
)
_REQUIRED_VERSIONS = {
    "pipeline_generation",
    "ranking_version",
    "gate_version",
    "simulator_version",
    "cost_model_version",
    "boundary_version",
}
_NATIVE_SOURCE_KINDS = {"native_evaluation", "manual_patch_after_results"}
_EVENT_TYPES = {
    "trial_evaluated",
    "cache_reuse",
    "historical_import_summary",
    "historical_lower_bound_import",
    "trial_daily_series_attached",
    "history_inventory_attested",
}


class TrialLedgerError(RuntimeError):
    """Raised when the permanent trial ledger is incomplete or contradictory."""


@dataclass(frozen=True)
class TrialRecord:
    trial_id: str
    payload_sha256: str
    canonical_payload_json: str

    def payload(self) -> dict[str, Any]:
        return json.loads(self.canonical_payload_json)

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload()
        payload["trial_id"] = self.trial_id
        payload["payload_sha256"] = self.payload_sha256
        return payload


@dataclass(frozen=True)
class TrialLedgerStatus:
    event_count: int
    resolved_trial_count: int
    native_trial_count: int
    historical_resolved_trial_count: int
    cache_reuse_count: int
    known_observed_historical_evaluation_rows: int
    historical_trial_count_is_lower_bound: bool
    canonical_historical_import_present: bool
    missing_daily_series_trial_ids: tuple[str, ...]
    permanent_trial_count_lower_bound: int
    development_dsr_status: str
    only_release_decision_allowed: str | None
    head_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "resolved_trial_count": self.resolved_trial_count,
            "native_trial_count": self.native_trial_count,
            "historical_resolved_trial_count": self.historical_resolved_trial_count,
            "cache_reuse_count": self.cache_reuse_count,
            "known_observed_historical_evaluation_rows": (
                self.known_observed_historical_evaluation_rows
            ),
            "historical_trial_count_is_lower_bound": (
                self.historical_trial_count_is_lower_bound
            ),
            "canonical_historical_import_present": (
                self.canonical_historical_import_present
            ),
            "missing_daily_series_trial_ids": list(
                self.missing_daily_series_trial_ids
            ),
            "permanent_trial_count_lower_bound": (
                self.permanent_trial_count_lower_bound
            ),
            "development_dsr_status": self.development_dsr_status,
            "only_release_decision_allowed": self.only_release_decision_allowed,
            "head_sha256": self.head_sha256,
        }


@dataclass(frozen=True)
class TrialLedgerSnapshot:
    root: Path
    manifest: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    trials: dict[str, dict[str, Any]]
    attached_daily_series: dict[str, tuple[dict[str, Any], ...]]
    status: TrialLedgerStatus


@dataclass(frozen=True)
class HistoricalImportResult:
    source_count: int
    imported_trial_count: int
    reused_trial_count: int
    skipped_candidate_count: int
    observed_evaluation_rows: int
    event_count_after: int


def build_trial_record(
    *,
    source_kind: str,
    candidate_id: str,
    family: str,
    parameters: Mapping[str, Any],
    feature_variant: str,
    seed: int,
    versions: Mapping[str, str],
    code_commit: str,
    evaluation_scope: Mapping[str, Any],
    daily_net_mtm_usdc: Sequence[Mapping[str, Any]],
    result_summary: Mapping[str, Any],
) -> TrialRecord:
    """Build one strict native/manual data-informed trial record."""

    if source_kind not in _NATIVE_SOURCE_KINDS:
        raise TrialLedgerError(
            "source_kind must be native_evaluation or manual_patch_after_results"
        )
    normalized_candidate_id = _required_text(candidate_id, "candidate_id")
    normalized_family = _required_text(family, "family")
    normalized_feature = _required_text(feature_variant, "feature_variant")
    if isinstance(seed, bool) or not isinstance(seed, int) or not (0 <= seed < 2**64):
        raise TrialLedgerError("seed must be an unsigned 64-bit integer")
    normalized_commit = str(code_commit).strip().lower()
    if not _COMMIT_RE.fullmatch(normalized_commit):
        raise TrialLedgerError(
            "code_commit must be a full lowercase 40-character git SHA"
        )
    normalized_versions = _validate_versions(versions, allow_unknown=False)
    normalized_scope = _normalize_nonempty_object(
        evaluation_scope, "evaluation_scope"
    )
    normalized_parameters = _normalize_object(parameters, "parameters")
    normalized_result = _normalize_object(result_summary, "result_summary")
    daily = _normalize_daily_series(daily_net_mtm_usdc, allow_empty=False)

    identity_basis = {
        "source_kind": source_kind,
        "candidate": {
            "candidate_id": normalized_candidate_id,
            "family": normalized_family,
            "parameters": normalized_parameters,
        },
        "feature_variant": normalized_feature,
        "seed": seed,
        "versions": normalized_versions,
        "code_commit": normalized_commit,
        "evaluation_scope": normalized_scope,
    }
    trial_id = f"trial_sha256:{_sha256_json(identity_basis)}"
    payload = {
        "schema_version": TRIAL_RECORD_SCHEMA_VERSION,
        "identity_basis": identity_basis,
        "data_informed": True,
        "historical_trial_count_is_lower_bound": False,
        "daily_net_mtm_usdc": daily,
        "daily_series_sha256": _sha256_json(daily),
        "result_summary": normalized_result,
        "completeness": {
            "candidate_identity_complete": True,
            "seed_complete": True,
            "versions_complete": True,
            "code_commit_complete": True,
            "daily_series_complete": True,
            "missing_fields": [],
        },
    }
    canonical = _canonical_json(payload)
    return TrialRecord(
        trial_id=trial_id,
        payload_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        canonical_payload_json=canonical,
    )


def initialize_trial_ledger(
    root: str | Path,
    *,
    required_historical_import_sha256: str,
) -> TrialLedgerSnapshot:
    ledger_root = Path(root)
    ledger_root.mkdir(parents=True, exist_ok=True)
    (ledger_root / "events").mkdir(parents=True, exist_ok=True)
    if not _HEX64_RE.fullmatch(required_historical_import_sha256):
        raise TrialLedgerError("required historical import digest must be SHA-256")
    manifest = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "permanent_trial_counter_namespace": PERMANENT_TRIAL_COUNTER_NAMESPACE,
        "append_only": True,
        "deletion_supported": False,
        "mutation_supported": False,
        "cache_reuse_counts_as_independent_trial": False,
        "required_historical_import_sha256": required_historical_import_sha256,
    }
    manifest_path = ledger_root / "manifest.json"
    if manifest_path.exists():
        existing = _read_json_object(manifest_path, "trial ledger manifest")
        if existing != manifest:
            raise TrialLedgerError(
                "trial ledger manifest conflicts with requested contract"
            )
    else:
        _write_new_json(manifest_path, manifest)

    head_path = ledger_root / "head.json"
    if not head_path.exists():
        _write_new_json(head_path, _head_payload(0, _ZERO_HASH, 0))
    return read_trial_ledger(ledger_root)


def build_canonical_historical_import_digest(
    repo_root: str | Path,
    *,
    manifest_path: str | Path = CANONICAL_HISTORICAL_IMPORT_PATH,
) -> str:
    root = Path(repo_root)
    path = Path(manifest_path)
    if not path.is_absolute():
        path = root / path
    payload = _read_json_object(path, "historical lower-bound manifest")
    validate_historical_lower_bound_manifest(payload)
    return _sha256_json(payload)


def import_canonical_historical_lower_bound(
    ledger_root: str | Path,
    repo_root: str | Path,
    *,
    manifest_path: str | Path = CANONICAL_HISTORICAL_IMPORT_PATH,
) -> TrialLedgerSnapshot:
    root = Path(repo_root)
    path = Path(manifest_path)
    if not path.is_absolute():
        path = root / path
    payload = _read_json_object(path, "historical lower-bound manifest")
    validate_historical_lower_bound_manifest(payload)
    digest = _sha256_json(payload)
    initialize_trial_ledger(
        ledger_root, required_historical_import_sha256=digest
    )
    event_payload = {
        "event_key": f"historical_lower_bound:{digest}",
        "manifest_sha256": digest,
        "known_observed_evaluation_rows": payload[
            "known_observed_evaluation_rows"
        ],
        "independent_trial_count_resolved": payload[
            "independent_trial_count_resolved"
        ],
        "historical_trial_count_is_lower_bound": True,
        "identity_inventory_complete": False,
        "daily_series_complete": False,
        "source_ids": [row["source_id"] for row in payload["sources"]],
        "observed_rows_by_source": {
            row["source_id"]: row["observed_evaluation_rows"]
            for row in payload["sources"]
        },
    }
    _append_event_idempotent(
        Path(ledger_root), "historical_lower_bound_import", event_payload
    )
    return read_trial_ledger(ledger_root)


def validate_historical_lower_bound_manifest(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "protocol_version",
        "historical_trial_count_is_lower_bound",
        "identity_inventory_complete",
        "daily_series_complete",
        "known_observed_evaluation_rows",
        "independent_trial_count_resolved",
        "sources",
        "interpretation",
        "safety",
    }
    if set(payload) != required:
        raise TrialLedgerError(
            "historical lower-bound manifest fields are missing or unexpected"
        )
    if payload.get("schema_version") != HISTORICAL_IMPORT_SCHEMA_VERSION:
        raise TrialLedgerError("historical lower-bound schema is invalid")
    if payload.get("protocol_version") != "3.0.0":
        raise TrialLedgerError(
            "historical lower-bound protocol version is invalid"
        )
    if payload.get("historical_trial_count_is_lower_bound") is not True:
        raise TrialLedgerError("historical import must remain a lower bound")
    if payload.get("identity_inventory_complete") is not False:
        raise TrialLedgerError(
            "historical identity inventory must remain incomplete"
        )
    if payload.get("daily_series_complete") is not False:
        raise TrialLedgerError(
            "historical daily series must remain incomplete"
        )
    observed = payload.get("known_observed_evaluation_rows")
    resolved = payload.get("independent_trial_count_resolved")
    if (
        isinstance(observed, bool)
        or not isinstance(observed, int)
        or observed <= 0
        or isinstance(resolved, bool)
        or not isinstance(resolved, int)
        or resolved < 0
        or resolved > observed
    ):
        raise TrialLedgerError(
            "historical observed/resolved counts are invalid"
        )
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise TrialLedgerError("historical lower-bound sources are missing")
    source_ids: list[str] = []
    summed_rows = 0
    for row in sources:
        if not isinstance(row, dict):
            raise TrialLedgerError(
                "historical lower-bound source must be an object"
            )
        source_id = _required_text(row.get("source_id"), "source_id")
        source_ids.append(source_id)
        rows = row.get("observed_evaluation_rows")
        cycles = row.get("observed_cycles")
        tested = row.get("observed_tested_rows_per_cycle")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in (rows, cycles, tested)
        ):
            raise TrialLedgerError(
                "historical source counts must be positive integers"
            )
        if rows != cycles * tested:
            raise TrialLedgerError(
                "historical source row count is inconsistent"
            )
        if row.get("candidate_identity_inventory_available") is not False:
            raise TrialLedgerError(
                "historical candidate identity availability is overstated"
            )
        if row.get("causal_daily_series_available") is not False:
            raise TrialLedgerError(
                "historical daily series availability is overstated"
            )
        _required_text(row.get("evidence_reference"), "evidence_reference")
        summed_rows += rows
    if len(set(source_ids)) != len(source_ids):
        raise TrialLedgerError("historical source ids must be unique")
    if summed_rows != observed:
        raise TrialLedgerError(
            "historical observed row total is inconsistent"
        )
    interpretation = payload.get("interpretation")
    if not isinstance(interpretation, dict):
        raise TrialLedgerError("historical interpretation is missing")
    if (
        interpretation.get(
            "observed_evaluation_rows_are_not_independent_trial_count"
        )
        is not True
        or interpretation.get("duplicates_or_cache_equivalents_may_exist")
        is not True
        or interpretation.get("development_dsr_status")
        != DEVELOPMENT_DSR_INSUFFICIENT
        or interpretation.get("only_release_decision_allowed") != NO_TRADE
    ):
        raise TrialLedgerError(
            "historical interpretation must remain fail-closed"
        )
    if payload.get("safety") != {
        "api_keys": "forbidden",
        "live": "locked",
        "orders": "locked",
        "paper": "locked",
        "testtrade": "locked",
        "trading_api": "forbidden",
    }:
        raise TrialLedgerError("historical import safety locks are invalid")


def append_trial(root: str | Path, record: TrialRecord) -> TrialLedgerSnapshot:
    ledger_root = Path(root)
    validate_trial_record(record)
    with _ledger_lock(ledger_root):
        snapshot = _read_trial_ledger_unlocked(ledger_root)
        existing = snapshot.trials.get(record.trial_id)
        if existing is not None:
            if existing != record.to_dict():
                raise TrialLedgerError(
                    "trial id already exists with different immutable payload"
                )
            return snapshot
        payload = {
            "event_key": f"trial:{record.trial_id}",
            "trial": record.to_dict(),
        }
        _append_event_unlocked(
            ledger_root, snapshot, "trial_evaluated", payload
        )
    return read_trial_ledger(ledger_root)


def record_cache_reuse(
    root: str | Path,
    *,
    trial_id: str,
    reuse_scope: Mapping[str, Any],
) -> TrialLedgerSnapshot:
    ledger_root = Path(root)
    normalized_scope = _normalize_nonempty_object(reuse_scope, "reuse_scope")
    with _ledger_lock(ledger_root):
        snapshot = _read_trial_ledger_unlocked(ledger_root)
        if trial_id not in snapshot.trials:
            raise TrialLedgerError("cache reuse references an unknown trial")
        reuse_key = _sha256_json(
            {"trial_id": trial_id, "reuse_scope": normalized_scope}
        )
        payload = {
            "event_key": f"cache_reuse:{reuse_key}",
            "trial_id": trial_id,
            "reuse_scope": normalized_scope,
            "counts_as_independent_trial": False,
        }
        _append_event_idempotent_unlocked(
            ledger_root, snapshot, "cache_reuse", payload
        )
    return read_trial_ledger(ledger_root)


def attach_trial_daily_series(
    root: str | Path,
    *,
    trial_id: str,
    daily_net_mtm_usdc: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
) -> TrialLedgerSnapshot:
    ledger_root = Path(root)
    daily = _normalize_daily_series(daily_net_mtm_usdc, allow_empty=False)
    normalized_provenance = _normalize_nonempty_object(
        provenance, "provenance"
    )
    with _ledger_lock(ledger_root):
        snapshot = _read_trial_ledger_unlocked(ledger_root)
        trial = snapshot.trials.get(trial_id)
        if trial is None:
            raise TrialLedgerError(
                "daily-series attachment references an unknown trial"
            )
        if trial.get("daily_net_mtm_usdc") is not None:
            if trial["daily_net_mtm_usdc"] != daily:
                raise TrialLedgerError("native trial daily series is immutable")
            return snapshot
        existing = snapshot.attached_daily_series.get(trial_id)
        if existing is not None:
            if list(existing) != daily:
                raise TrialLedgerError(
                    "historical daily-series attachment conflicts"
                )
            return snapshot
        payload = {
            "event_key": f"daily_series:{trial_id}",
            "trial_id": trial_id,
            "daily_net_mtm_usdc": daily,
            "daily_series_sha256": _sha256_json(daily),
            "provenance": normalized_provenance,
        }
        _append_event_unlocked(
            ledger_root,
            snapshot,
            "trial_daily_series_attached",
            payload,
        )
    return read_trial_ledger(ledger_root)


def attest_complete_trial_inventory(
    root: str | Path,
    *,
    expected_resolved_trial_count: int,
    inventory_sha256: str,
    reconciliation_sha256: str,
    attestor: str,
) -> TrialLedgerSnapshot:
    ledger_root = Path(root)
    if (
        isinstance(expected_resolved_trial_count, bool)
        or not isinstance(expected_resolved_trial_count, int)
        or expected_resolved_trial_count < 2
    ):
        raise TrialLedgerError(
            "expected_resolved_trial_count must be at least 2"
        )
    if not _HEX64_RE.fullmatch(str(inventory_sha256)):
        raise TrialLedgerError(
            "inventory_sha256 must be a lowercase SHA-256"
        )
    if not _HEX64_RE.fullmatch(str(reconciliation_sha256)):
        raise TrialLedgerError(
            "reconciliation_sha256 must be a lowercase SHA-256"
        )
    normalized_attestor = _required_text(attestor, "attestor")
    with _ledger_lock(ledger_root):
        snapshot = _read_trial_ledger_unlocked(ledger_root)
        if not snapshot.status.canonical_historical_import_present:
            raise TrialLedgerError(
                "canonical historical lower-bound import is missing"
            )
        if len(snapshot.trials) != expected_resolved_trial_count:
            raise TrialLedgerError(
                "inventory attestation count does not match ledger"
            )
        if snapshot.status.missing_daily_series_trial_ids:
            raise TrialLedgerError(
                "inventory attestation requires every causal daily series"
            )
        incomplete_historical = _incomplete_historical_trial_ids(
            snapshot.trials
        )
        if incomplete_historical:
            raise TrialLedgerError(
                "inventory attestation cannot resolve historical trials with "
                "incomplete seed, versions, code, daily series, or fields"
            )
        (
            observed_rows_by_source,
            observed_artifacts_by_source,
            observed_keys_by_source,
        ) = _observed_evidence_by_provenance_from_events(snapshot.events)
        _validate_historical_source_assignments(
            snapshot.trials,
            observed_rows_by_source,
            observed_artifacts_by_source,
            observed_keys_by_source,
        )
        if (
            snapshot.status.historical_resolved_trial_count
            != snapshot.status.known_observed_historical_evaluation_rows
        ):
            raise TrialLedgerError(
                "inventory attestation requires immutable evidence for every "
                "observed historical evaluation row"
            )
        expected_inventory_sha256 = build_trial_inventory_evidence_sha256(
            snapshot
        )
        if inventory_sha256 != expected_inventory_sha256:
            raise TrialLedgerError(
                "inventory_sha256 does not match the immutable ledger inventory"
            )
        expected_reconciliation_sha256 = (
            build_historical_reconciliation_evidence_sha256(snapshot)
        )
        if reconciliation_sha256 != expected_reconciliation_sha256:
            raise TrialLedgerError(
                "reconciliation_sha256 does not match ledger provenance"
            )
        trial_ids_sha256 = _sha256_json(sorted(snapshot.trials))
        attestation_key = _sha256_json(
            {
                "inventory_sha256": inventory_sha256,
                "reconciliation_sha256": reconciliation_sha256,
            }
        )
        payload = {
            "event_key": f"inventory_attestation:{attestation_key}",
            "expected_resolved_trial_count": expected_resolved_trial_count,
            "inventory_sha256": inventory_sha256,
            "reconciliation_sha256": reconciliation_sha256,
            "trial_ids_sha256": trial_ids_sha256,
            "attestor": normalized_attestor,
            "historical_trial_count_is_lower_bound": False,
        }
        _append_event_idempotent_unlocked(
            ledger_root,
            snapshot,
            "history_inventory_attested",
            payload,
        )
    return read_trial_ledger(ledger_root)


def import_historical_reports(
    root: str | Path,
    report_paths: Iterable[str | Path],
) -> HistoricalImportResult:
    ledger_root = Path(root)
    sources = _expand_json_paths(report_paths)
    imported = 0
    reused = 0
    skipped = 0
    observed_rows = 0
    for source in sources:
        raw_bytes = source.read_bytes()
        source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
        try:
            report = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise TrialLedgerError(
                f"historical report is invalid: {source}"
            ) from exc
        if not isinstance(report, dict):
            raise TrialLedgerError(
                f"historical report root must be an object: {source}"
            )
        rows, source_observed, source_skipped, report_format = (
            _extract_historical_trial_rows(report, source_sha256)
        )
        source_id = _historical_report_source_id(report, source_sha256)
        observation_keys = tuple(
            _historical_observation_key(source_sha256, row_index)
            for row_index in range(1, source_observed + 1)
        )
        rows = [
            {**row, "historical_observation_key": observation_keys[index]}
            for index, row in enumerate(rows)
        ]
        existing_snapshot = read_trial_ledger(ledger_root)
        (
            existing_source_counts,
            existing_source_artifacts,
            existing_observation_keys,
        ) = _observed_evidence_by_provenance_from_events(
            existing_snapshot.events
        )
        _merge_observed_source_count(
            existing_source_counts,
            existing_source_artifacts,
            existing_observation_keys,
            source_id,
            source_observed,
            artifact_sha256=source_sha256,
            observation_keys=observation_keys,
        )
        observed_rows += source_observed
        skipped += source_skipped
        records = [_build_historical_trial_record(row) for row in rows]
        for record in records:
            before = read_trial_ledger(ledger_root)
            after = append_trial(ledger_root, record)
            if (
                after.status.resolved_trial_count
                > before.status.resolved_trial_count
            ):
                imported += 1
            else:
                reused += 1
        summary_payload = {
            "event_key": f"historical_report:{source_sha256}",
            "source_sha256": source_sha256,
            "source_name": source.name,
            "source_id": source_id,
            "report_format": report_format,
            "observed_evaluation_rows": source_observed,
            "observation_keys": list(observation_keys),
            "imported_identity_rows": len(rows),
            "skipped_identity_rows": source_skipped,
            "historical_trial_count_is_lower_bound": True,
            "causal_daily_series_complete": False,
        }
        _append_event_idempotent(
            ledger_root, "historical_import_summary", summary_payload
        )
    snapshot = read_trial_ledger(ledger_root)
    return HistoricalImportResult(
        source_count=len(sources),
        imported_trial_count=imported,
        reused_trial_count=reused,
        skipped_candidate_count=skipped,
        observed_evaluation_rows=observed_rows,
        event_count_after=snapshot.status.event_count,
    )


def read_trial_ledger(root: str | Path) -> TrialLedgerSnapshot:
    return _read_trial_ledger_unlocked(Path(root))


def build_trial_inventory_evidence_sha256(
    snapshot: TrialLedgerSnapshot,
) -> str:
    """Digest the immutable trial payloads and attached causal series."""

    return _inventory_evidence_sha256(
        snapshot.manifest,
        snapshot.trials,
        snapshot.attached_daily_series,
    )


def build_historical_reconciliation_evidence_sha256(
    snapshot: TrialLedgerSnapshot,
) -> str:
    """Digest ledger-derived historical provenance, never caller claims."""

    (
        observed_rows_by_source,
        observed_artifacts_by_source,
        observed_keys_by_source,
    ) = _observed_evidence_by_provenance_from_events(snapshot.events)
    return _reconciliation_evidence_sha256(
        snapshot.manifest,
        snapshot.trials,
        snapshot.attached_daily_series,
        observed_rows_by_source,
        observed_artifacts_by_source,
        observed_keys_by_source,
    )


def assert_release_decision_allowed(
    snapshot: TrialLedgerSnapshot,
    decision_kind: str,
) -> None:
    if decision_kind not in {NO_TRADE, TRADING_CANDIDATE}:
        raise TrialLedgerError(
            "decision_kind must be NO_TRADE or TRADING_CANDIDATE"
        )
    if (
        snapshot.status.development_dsr_status
        == DEVELOPMENT_DSR_INSUFFICIENT
        and decision_kind != NO_TRADE
    ):
        raise TrialLedgerError(
            "incomplete permanent trial history permits NO_TRADE only"
        )


def validate_trial_record(record: TrialRecord) -> None:
    if not re.fullmatch(r"trial_sha256:[0-9a-f]{64}", record.trial_id):
        raise TrialLedgerError("trial_id is invalid")
    if not _HEX64_RE.fullmatch(record.payload_sha256):
        raise TrialLedgerError("trial payload digest is invalid")
    try:
        payload = json.loads(record.canonical_payload_json)
    except json.JSONDecodeError as exc:
        raise TrialLedgerError(
            "trial payload is not valid canonical JSON"
        ) from exc
    if _canonical_json(payload) != record.canonical_payload_json:
        raise TrialLedgerError("trial payload is not canonical")
    if (
        hashlib.sha256(record.canonical_payload_json.encode("utf-8")).hexdigest()
        != record.payload_sha256
    ):
        raise TrialLedgerError("trial payload digest mismatch")
    if payload.get("schema_version") != TRIAL_RECORD_SCHEMA_VERSION:
        raise TrialLedgerError("trial record schema is invalid")
    identity = payload.get("identity_basis")
    if not isinstance(identity, dict):
        raise TrialLedgerError("trial identity basis is missing")
    expected_id = f"trial_sha256:{_sha256_json(identity)}"
    if record.trial_id != expected_id:
        raise TrialLedgerError("trial id does not match identity basis")
    if payload.get("data_informed") is not True:
        raise TrialLedgerError(
            "only data-informed evaluations belong in the ledger"
        )
    candidate = identity.get("candidate")
    if not isinstance(candidate, dict):
        raise TrialLedgerError("trial candidate identity is missing")
    _required_text(candidate.get("candidate_id"), "candidate_id")
    _required_text(candidate.get("family"), "family")
    _normalize_object(candidate.get("parameters", {}), "parameters")
    _required_text(identity.get("feature_variant"), "feature_variant")
    _normalize_nonempty_object(
        identity.get("evaluation_scope", {}), "evaluation_scope"
    )
    source_kind = identity.get("source_kind")
    completeness = payload.get("completeness")
    required_completeness_fields = {
        "candidate_identity_complete",
        "seed_complete",
        "versions_complete",
        "code_commit_complete",
        "daily_series_complete",
        "missing_fields",
    }
    if (
        not isinstance(completeness, dict)
        or set(completeness) != required_completeness_fields
        or completeness.get("candidate_identity_complete") is not True
        or any(
            not isinstance(completeness.get(field), bool)
            for field in (
                "seed_complete",
                "versions_complete",
                "code_commit_complete",
                "daily_series_complete",
            )
        )
        or not isinstance(completeness.get("missing_fields"), list)
        or any(
            not isinstance(field, str) or not field
            for field in completeness.get("missing_fields", [])
        )
    ):
        raise TrialLedgerError("trial completeness metadata is invalid")
    if source_kind in _NATIVE_SOURCE_KINDS:
        if payload.get("historical_trial_count_is_lower_bound") is not False:
            raise TrialLedgerError(
                "native trial cannot be marked historical lower bound"
            )
        seed = identity.get("seed")
        if (
            isinstance(seed, bool)
            or not isinstance(seed, int)
            or not (0 <= seed < 2**64)
        ):
            raise TrialLedgerError("native trial seed is invalid")
        _validate_versions(identity.get("versions", {}), allow_unknown=False)
        if not _COMMIT_RE.fullmatch(str(identity.get("code_commit") or "")):
            raise TrialLedgerError("native trial code commit is invalid")
        daily = payload.get("daily_net_mtm_usdc")
        if not isinstance(daily, list) or not daily:
            raise TrialLedgerError(
                "native trial requires a causal daily series"
            )
        normalized_daily = _normalize_daily_series(daily, allow_empty=False)
        if payload.get("daily_series_sha256") != _sha256_json(
            normalized_daily
        ):
            raise TrialLedgerError(
                "native trial daily series digest mismatch"
            )
        if completeness != {
            "candidate_identity_complete": True,
            "seed_complete": True,
            "versions_complete": True,
            "code_commit_complete": True,
            "daily_series_complete": True,
            "missing_fields": [],
        }:
            raise TrialLedgerError(
                "native trial completeness metadata is inconsistent"
            )
    elif source_kind == "historical_import":
        if payload.get("historical_trial_count_is_lower_bound") is not True:
            raise TrialLedgerError(
                "historical trial must remain marked lower bound"
            )
        _validate_versions(identity.get("versions", {}), allow_unknown=True)
        historical_source_sha256 = payload.get("historical_source_sha256")
        if (
            not isinstance(historical_source_sha256, str)
            or not _HEX64_RE.fullmatch(historical_source_sha256)
        ):
            raise TrialLedgerError(
                "historical trial source digest is missing or invalid"
            )
        historical_observation_key = payload.get(
            "historical_observation_key"
        )
        if (
            historical_observation_key is not None
            and (
                not isinstance(historical_observation_key, str)
                or not _OBSERVATION_KEY_RE.fullmatch(
                    historical_observation_key
                )
            )
        ):
            raise TrialLedgerError(
                "historical trial observation key is invalid"
            )
        if historical_observation_key is None and all(
            completeness[field]
            for field in (
                "seed_complete",
                "versions_complete",
                "code_commit_complete",
                "daily_series_complete",
            )
        ):
            raise TrialLedgerError(
                "complete historical trial requires an observation key"
            )
        if completeness["seed_complete"]:
            seed = identity.get("seed")
            if (
                isinstance(seed, bool)
                or not isinstance(seed, int)
                or not (0 <= seed < 2**64)
            ):
                raise TrialLedgerError(
                    "historical seed is not complete as claimed"
                )
        if completeness["versions_complete"]:
            _validate_versions(identity.get("versions", {}), allow_unknown=False)
        if completeness["code_commit_complete"] and not _COMMIT_RE.fullmatch(
            str(identity.get("code_commit") or "")
        ):
            raise TrialLedgerError(
                "historical code commit is not complete as claimed"
            )
        if completeness["daily_series_complete"]:
            daily = payload.get("daily_net_mtm_usdc")
            if not isinstance(daily, list) or not daily:
                raise TrialLedgerError(
                    "historical daily series is not complete as claimed"
                )
            normalized_daily = _normalize_daily_series(
                daily, allow_empty=False
            )
            if payload.get("daily_series_sha256") != _sha256_json(
                normalized_daily
            ):
                raise TrialLedgerError(
                    "historical daily series digest mismatch"
                )
        if completeness["missing_fields"] and all(
            completeness[field]
            for field in (
                "seed_complete",
                "versions_complete",
                "code_commit_complete",
                "daily_series_complete",
            )
        ):
            raise TrialLedgerError(
                "historical missing fields contradict completeness claims"
            )
    else:
        raise TrialLedgerError("trial source kind is unsupported")


def _build_historical_trial_record(row: Mapping[str, Any]) -> TrialRecord:
    candidate_id = _required_text(row.get("candidate_id"), "candidate_id")
    family = _required_text(row.get("family"), "family")
    parameters = _normalize_object(row.get("parameters", {}), "parameters")
    source_sha256 = _required_text(
        row.get("source_sha256"), "source_sha256"
    )
    if not _HEX64_RE.fullmatch(source_sha256):
        raise TrialLedgerError("historical source digest is invalid")
    observation_key = _required_text(
        row.get("historical_observation_key"),
        "historical_observation_key",
    )
    if not _OBSERVATION_KEY_RE.fullmatch(observation_key):
        raise TrialLedgerError("historical observation key is invalid")
    versions = _validate_versions(
        row.get("versions", {}), allow_unknown=True
    )
    identity_basis = {
        "source_kind": "historical_import",
        "candidate": {
            "candidate_id": candidate_id,
            "family": family,
            "parameters": parameters,
        },
        "feature_variant": str(
            row.get("feature_variant") or "UNKNOWN_LEGACY"
        ),
        "seed": row.get("seed"),
        "versions": versions,
        "code_commit": str(row.get("code_commit") or "UNKNOWN"),
        "evaluation_scope": _normalize_nonempty_object(
            row.get("evaluation_scope", {}), "evaluation_scope"
        ),
    }
    trial_id = f"trial_sha256:{_sha256_json(identity_basis)}"
    payload = {
        "schema_version": TRIAL_RECORD_SCHEMA_VERSION,
        "identity_basis": identity_basis,
        "data_informed": True,
        "historical_trial_count_is_lower_bound": True,
        "daily_net_mtm_usdc": None,
        "daily_series_sha256": None,
        "result_summary": _normalize_object(
            row.get("result_summary", {}), "result_summary"
        ),
        "completeness": {
            "candidate_identity_complete": True,
            "seed_complete": False,
            "versions_complete": False,
            "code_commit_complete": bool(
                _COMMIT_RE.fullmatch(str(row.get("code_commit") or ""))
            ),
            "daily_series_complete": False,
            "missing_fields": [
                "seed",
                "feature_variant",
                "complete_versions",
                "full_code_commit",
                "daily_net_mtm_usdc",
            ],
        },
        "historical_source_sha256": source_sha256,
        "historical_observation_key": observation_key,
    }
    canonical = _canonical_json(payload)
    return TrialRecord(
        trial_id=trial_id,
        payload_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        canonical_payload_json=canonical,
    )


def _extract_historical_trial_rows(
    report: Mapping[str, Any],
    source_sha256: str,
) -> tuple[list[dict[str, Any]], int, int, str]:
    if isinstance(report.get("cycles"), list):
        return _extract_protocol_v2_loop_rows(report, source_sha256)
    leaderboard = report.get("candidate_leaderboard")
    if isinstance(leaderboard, list):
        rows: list[dict[str, Any]] = []
        skipped = 0
        for index, candidate in enumerate(leaderboard, start=1):
            if not isinstance(candidate, dict):
                skipped += 1
                continue
            family = candidate.get("family")
            candidate_id = candidate.get("candidate_id")
            params = candidate.get("params", candidate.get("parameters"))
            if (
                not isinstance(family, str)
                or not isinstance(candidate_id, str)
                or not isinstance(params, dict)
            ):
                skipped += 1
                continue
            rows.append(
                {
                    "source_sha256": source_sha256,
                    "candidate_id": candidate_id,
                    "family": family,
                    "parameters": params,
                    "feature_variant": "legacy_single_run_unknown",
                    "seed": None,
                    "versions": _legacy_versions(report, candidate),
                    "code_commit": report.get("git_commit"),
                    "evaluation_scope": {
                        "legacy_run_id": str(
                            report.get("run_id") or "UNKNOWN"
                        ),
                        "candidate_row": index,
                        "source_sha256": source_sha256,
                    },
                    "result_summary": {
                        key: value
                        for key, value in candidate.items()
                        if key not in {"params", "parameters"}
                    },
                }
            )
        return (
            rows,
            len(leaderboard),
            skipped,
            "protocol_v1_single_research",
        )
    raise TrialLedgerError("historical report format is unsupported")


def _extract_protocol_v2_loop_rows(
    report: Mapping[str, Any],
    source_sha256: str,
) -> tuple[list[dict[str, Any]], int, int, str]:
    rows: list[dict[str, Any]] = []
    observed = 0
    skipped = 0
    loop_run_id = str(
        report.get("loop_run_id") or report.get("run_id") or "UNKNOWN"
    )
    cycles = report.get("cycles", [])
    for cycle_position, cycle in enumerate(cycles, start=1):
        if not isinstance(cycle, dict):
            skipped += 1
            continue
        stage_ids = cycle.get("candidate_stage_ids")
        inventory = cycle.get("generated_candidate_inventory")
        if not isinstance(inventory, list):
            tested_count = cycle.get("tested_candidates")
            if isinstance(tested_count, int) and not isinstance(
                tested_count, bool
            ):
                observed += max(0, tested_count)
                skipped += max(0, tested_count)
            continue
        inventory_by_id = {
            row.get("candidate_id"): row
            for row in inventory
            if isinstance(row, dict)
            and isinstance(row.get("candidate_id"), str)
        }
        if isinstance(stage_ids, dict) and isinstance(
            stage_ids.get("tested"), list
        ):
            tested_ids = [str(value) for value in stage_ids["tested"]]
        else:
            tested_ids = [
                str(row["candidate_id"])
                for row in inventory
                if isinstance(row, dict)
                and row.get("tested") is True
                and isinstance(row.get("candidate_id"), str)
            ]
        observed += len(tested_ids)
        for tested_position, candidate_id in enumerate(
            tested_ids, start=1
        ):
            row = inventory_by_id.get(candidate_id)
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("family"), str)
                or not isinstance(row.get("params"), dict)
            ):
                skipped += 1
                continue
            walk_forward_ids = (
                stage_ids.get("walk_forward", [])
                if isinstance(stage_ids, dict)
                else []
            )
            finalist_ids = (
                stage_ids.get("finalists", [])
                if isinstance(stage_ids, dict)
                else []
            )
            result_summary: dict[str, Any] = {
                "legacy_cycle_id": cycle.get(
                    "cycle_id", cycle_position
                ),
                "stage_membership": {
                    "tested": True,
                    "walk_forward": candidate_id in walk_forward_ids,
                    "finalist": candidate_id in finalist_ids,
                },
            }
            selected = cycle.get("selected_candidate")
            if (
                isinstance(selected, dict)
                and selected.get("candidate_id") == candidate_id
            ):
                result_summary["selected_candidate_score"] = cycle.get(
                    "selected_candidate_score"
                )
                result_summary["quality_gate"] = cycle.get("quality_gate")
            rows.append(
                {
                    "source_sha256": source_sha256,
                    "candidate_id": candidate_id,
                    "family": row["family"],
                    "parameters": row["params"],
                    "feature_variant": "legacy_protocol_v2_unknown",
                    "seed": None,
                    "versions": _legacy_versions(report, cycle),
                    "code_commit": report.get("git_commit"),
                    "evaluation_scope": {
                        "legacy_loop_run_id": loop_run_id,
                        "legacy_cycle_id": cycle.get(
                            "cycle_id", cycle_position
                        ),
                        "tested_position": tested_position,
                        "source_sha256": source_sha256,
                    },
                    "result_summary": result_summary,
                }
            )
    return rows, observed, skipped, "protocol_v2_research_loop"


def _legacy_versions(
    report: Mapping[str, Any],
    row: Mapping[str, Any],
) -> dict[str, str]:
    protocol = report.get("research_protocol")
    protocol_version = (
        f"legacy_protocol_{protocol.get('schema_version')}"
        if isinstance(protocol, dict)
        else "legacy_unknown"
    )
    gate = row.get("quality_gate")
    gate_version = (
        str(gate.get("gate_version"))
        if isinstance(gate, dict) and gate.get("gate_version")
        else str(report.get("quality_gate_version") or "legacy_unknown")
    )
    score = row.get("selected_candidate_score")
    ranking_version = (
        str(score.get("ranking_rule"))
        if isinstance(score, dict) and score.get("ranking_rule")
        else "legacy_unknown"
    )
    return {
        "pipeline_generation": protocol_version,
        "ranking_version": ranking_version,
        "gate_version": gate_version,
        "simulator_version": "legacy_unknown",
        "cost_model_version": "legacy_unknown",
        "boundary_version": "legacy_protocol_v2_split",
    }


def _historical_report_source_id(
    report: Mapping[str, Any], source_sha256: str
) -> str:
    for field in ("loop_run_id", "run_id"):
        value = report.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"report_sha256:{source_sha256}"


def _historical_observation_key(
    source_sha256: str, row_index: int
) -> str:
    return "observation_sha256:" + _sha256_json(
        {"source_sha256": source_sha256, "row_index": row_index}
    )


def _append_event_idempotent(
    root: Path,
    event_type: str,
    payload: Mapping[str, Any],
) -> None:
    with _ledger_lock(root):
        snapshot = _read_trial_ledger_unlocked(root)
        _append_event_idempotent_unlocked(
            root, snapshot, event_type, payload
        )


def _append_event_idempotent_unlocked(
    root: Path,
    snapshot: TrialLedgerSnapshot,
    event_type: str,
    payload: Mapping[str, Any],
) -> None:
    event_key = payload.get("event_key")
    if not isinstance(event_key, str) or not event_key:
        raise TrialLedgerError("event payload requires an event_key")
    existing = [
        event
        for event in snapshot.events
        if event.get("payload", {}).get("event_key") == event_key
    ]
    if existing:
        if (
            existing[-1].get("event_type") != event_type
            or existing[-1].get("payload") != dict(payload)
        ):
            raise TrialLedgerError(
                "event key already exists with different payload"
            )
        return
    _append_event_unlocked(root, snapshot, event_type, payload)


def _append_event_unlocked(
    root: Path,
    snapshot: TrialLedgerSnapshot,
    event_type: str,
    payload: Mapping[str, Any],
) -> None:
    if event_type not in _EVENT_TYPES:
        raise TrialLedgerError("unsupported trial ledger event type")
    normalized_payload = _normalize_nonempty_object(
        payload, "event payload"
    )
    sequence = len(snapshot.events) + 1
    previous = snapshot.status.head_sha256 if snapshot.events else _ZERO_HASH
    body = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "sequence": sequence,
        "previous_event_sha256": previous,
        "event_type": event_type,
        "payload": normalized_payload,
    }
    digest = _sha256_json(body)
    event = {**body, "event_sha256": digest}
    event_path = root / "events" / f"{sequence:012d}_{digest}.json"
    _write_new_json(event_path, event)
    resolved_count = len(snapshot.trials) + (
        1 if event_type == "trial_evaluated" else 0
    )
    _write_replace_json(
        root / "head.json",
        _head_payload(sequence, digest, resolved_count),
    )


def _read_trial_ledger_unlocked(root: Path) -> TrialLedgerSnapshot:
    manifest = _read_json_object(
        root / "manifest.json", "trial ledger manifest"
    )
    _validate_ledger_manifest(manifest)
    events_dir = root / "events"
    if not events_dir.is_dir():
        raise TrialLedgerError("trial ledger events directory is missing")
    event_files = sorted(events_dir.iterdir())
    stray = [
        path.name
        for path in event_files
        if path.is_file() and not _EVENT_NAME_RE.fullmatch(path.name)
    ]
    if stray:
        raise TrialLedgerError(
            f"trial ledger contains unexpected event files: {stray}"
        )
    files = [path for path in event_files if path.is_file()]
    events: list[dict[str, Any]] = []
    previous = _ZERO_HASH
    event_heads = [_ZERO_HASH]
    resolved_counts = [0]
    event_keys: set[str] = set()
    trials: dict[str, dict[str, Any]] = {}
    attachments: dict[str, tuple[dict[str, Any], ...]] = {}
    cache_reuse_count = 0
    observed_rows_by_source: dict[str, int] = {}
    observed_artifacts_by_source: dict[str, str | None] = {}
    observed_keys_by_source: dict[str, tuple[str, ...] | None] = {}
    canonical_import_present = False
    lower_bound = False
    attested_historical_trial_ids: set[str] = set()
    for expected_sequence, path in enumerate(files, start=1):
        match = _EVENT_NAME_RE.fullmatch(path.name)
        if (
            match is None
            or int(match.group("sequence")) != expected_sequence
        ):
            raise TrialLedgerError(
                "trial ledger event sequence is missing or non-contiguous"
            )
        event = _read_json_object(path, "trial ledger event")
        if event.get("schema_version") != EVENT_SCHEMA_VERSION:
            raise TrialLedgerError("trial ledger event schema is invalid")
        if event.get("sequence") != expected_sequence:
            raise TrialLedgerError(
                "trial ledger event sequence does not match filename"
            )
        if event.get("previous_event_sha256") != previous:
            raise TrialLedgerError("trial ledger hash chain is broken")
        if event.get("event_type") not in _EVENT_TYPES:
            raise TrialLedgerError("trial ledger event type is invalid")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            raise TrialLedgerError("trial ledger event payload is invalid")
        event_key = payload.get("event_key")
        if (
            not isinstance(event_key, str)
            or not event_key
            or event_key in event_keys
        ):
            raise TrialLedgerError(
                "trial ledger event key is missing or duplicated"
            )
        event_keys.add(event_key)
        body = dict(event)
        digest = body.pop("event_sha256", None)
        expected_digest = _sha256_json(body)
        if (
            digest != expected_digest
            or match.group("digest") != expected_digest
        ):
            raise TrialLedgerError(
                "trial ledger event digest or filename is invalid"
            )
        previous = expected_digest

        event_type = event["event_type"]
        if event_type == "trial_evaluated":
            trial = payload.get("trial")
            if not isinstance(trial, dict):
                raise TrialLedgerError("trial event has no record")
            record = _trial_record_from_dict(trial)
            validate_trial_record(record)
            if record.trial_id in trials:
                raise TrialLedgerError(
                    "trial ledger contains duplicate evaluated trial"
                )
            trials[record.trial_id] = record.to_dict()
            if (
                record.to_dict()["identity_basis"]["source_kind"]
                == "historical_import"
            ):
                lower_bound = True
        elif event_type == "cache_reuse":
            trial_id = payload.get("trial_id")
            if (
                trial_id not in trials
                or payload.get("counts_as_independent_trial") is not False
            ):
                raise TrialLedgerError("cache reuse event is invalid")
            cache_reuse_count += 1
        elif event_type == "trial_daily_series_attached":
            trial_id = payload.get("trial_id")
            daily = payload.get("daily_net_mtm_usdc")
            if trial_id not in trials or not isinstance(daily, list):
                raise TrialLedgerError(
                    "daily-series attachment is invalid"
                )
            normalized_daily = _normalize_daily_series(
                daily, allow_empty=False
            )
            if payload.get("daily_series_sha256") != _sha256_json(
                normalized_daily
            ):
                raise TrialLedgerError(
                    "daily-series attachment digest mismatch"
                )
            if trial_id in attachments:
                raise TrialLedgerError(
                    "trial has multiple daily-series attachments"
                )
            attachments[str(trial_id)] = tuple(normalized_daily)
        elif event_type == "historical_lower_bound_import":
            required_digest = manifest.get(
                "required_historical_import_sha256"
            )
            if payload.get("manifest_sha256") != required_digest:
                raise TrialLedgerError(
                    "canonical historical import digest mismatch"
                )
            canonical_import_present = True
            lower_bound = True
            source_counts = payload.get("observed_rows_by_source")
            if source_counts is None:
                source_counts = {
                    "canonical_manifest:"
                    f"{payload.get('manifest_sha256')}": payload.get(
                        "known_observed_evaluation_rows", 0
                    )
                }
            if not isinstance(source_counts, dict) or not source_counts:
                raise TrialLedgerError(
                    "canonical historical source provenance is invalid"
                )
            for source_id, count in source_counts.items():
                _merge_observed_source_count(
                    observed_rows_by_source,
                    observed_artifacts_by_source,
                    observed_keys_by_source,
                    source_id,
                    count,
                )
        elif event_type == "historical_import_summary":
            lower_bound = True
            source_sha256 = payload.get("source_sha256")
            if not isinstance(source_sha256, str) or not _HEX64_RE.fullmatch(
                source_sha256
            ):
                raise TrialLedgerError(
                    "historical import source digest is invalid"
                )
            source_id = payload.get(
                "source_id", f"report_sha256:{source_sha256}"
            )
            observation_keys = payload.get("observation_keys")
            if observation_keys is None:
                # Legacy summaries did not persist per-row provenance and
                # therefore can never support a completion attestation.
                normalized_observation_keys = None
            elif isinstance(observation_keys, list):
                normalized_observation_keys = tuple(observation_keys)
            else:
                raise TrialLedgerError(
                    "historical observation-key inventory is invalid"
                )
            _merge_observed_source_count(
                observed_rows_by_source,
                observed_artifacts_by_source,
                observed_keys_by_source,
                source_id,
                payload.get("observed_evaluation_rows"),
                artifact_sha256=source_sha256,
                observation_keys=normalized_observation_keys,
            )
        elif event_type == "history_inventory_attested":
            # Legacy v1 attestations had no ledger-derived reconciliation
            # digest.  They remain visible but cannot clear the lower bound.
            if "reconciliation_sha256" not in payload:
                lower_bound = True
            else:
                missing_at_attestation = _missing_daily_series_trial_ids(
                    trials, attachments
                )
                incomplete_historical = _incomplete_historical_trial_ids(
                    trials
                )
                historical_count_at_attestation = sum(
                    1
                    for trial in trials.values()
                    if trial["identity_basis"]["source_kind"]
                    == "historical_import"
                )
                observed_at_attestation = sum(
                    observed_rows_by_source.values()
                )
                expected_inventory = _inventory_evidence_sha256(
                    manifest, trials, attachments
                )
                expected_reconciliation = _reconciliation_evidence_sha256(
                    manifest,
                    trials,
                    attachments,
                    observed_rows_by_source,
                    observed_artifacts_by_source,
                    observed_keys_by_source,
                )
                _validate_historical_source_assignments(
                    trials,
                    observed_rows_by_source,
                    observed_artifacts_by_source,
                    observed_keys_by_source,
                )
                if (
                    payload.get("expected_resolved_trial_count")
                    != len(trials)
                    or payload.get("trial_ids_sha256")
                    != _sha256_json(sorted(trials))
                    or missing_at_attestation
                    or incomplete_historical
                    or not canonical_import_present
                    or historical_count_at_attestation
                    != observed_at_attestation
                    or payload.get("inventory_sha256")
                    != expected_inventory
                    or payload.get("reconciliation_sha256")
                    != expected_reconciliation
                    or payload.get("historical_trial_count_is_lower_bound")
                    is not False
                ):
                    raise TrialLedgerError(
                        "history inventory attestation is inconsistent"
                    )
                attested_historical_trial_ids = {
                    trial_id
                    for trial_id, trial in trials.items()
                    if trial["identity_basis"]["source_kind"]
                    == "historical_import"
                }
                lower_bound = False
        events.append(event)
        event_heads.append(previous)
        resolved_counts.append(len(trials))

    head = _read_json_object(root / "head.json", "trial ledger head")
    _validate_head(head, event_heads, resolved_counts)
    if not canonical_import_present:
        lower_bound = True
    missing_daily = _missing_daily_series_trial_ids(trials, attachments)
    incomplete_historical = _incomplete_historical_trial_ids(trials)
    native_count = 0
    historical_count = 0
    for trial_id, trial in trials.items():
        identity = trial["identity_basis"]
        source_kind = identity["source_kind"]
        if source_kind == "historical_import":
            historical_count += 1
        else:
            native_count += 1
    observed_rows = sum(observed_rows_by_source.values())
    # Native identities are independent by construction. Historical
    # placeholders remain possible duplicates until a complete per-row
    # attestation has covered them; observed report rows are diagnostic only.
    permanent_lower_bound = (
        len(trials)
        if not lower_bound
        else native_count + len(attested_historical_trial_ids)
    )
    insufficient = (
        len(trials) < 2
        or lower_bound
        or bool(missing_daily)
        or bool(incomplete_historical)
        or not canonical_import_present
    )
    dsr_status = (
        DEVELOPMENT_DSR_INSUFFICIENT
        if insufficient
        else DEVELOPMENT_DSR_READY
    )
    status = TrialLedgerStatus(
        event_count=len(events),
        resolved_trial_count=len(trials),
        native_trial_count=native_count,
        historical_resolved_trial_count=historical_count,
        cache_reuse_count=cache_reuse_count,
        known_observed_historical_evaluation_rows=observed_rows,
        historical_trial_count_is_lower_bound=lower_bound,
        canonical_historical_import_present=canonical_import_present,
        missing_daily_series_trial_ids=tuple(sorted(missing_daily)),
        permanent_trial_count_lower_bound=permanent_lower_bound,
        development_dsr_status=dsr_status,
        only_release_decision_allowed=NO_TRADE if insufficient else None,
        head_sha256=previous,
    )
    return TrialLedgerSnapshot(
        root=root,
        manifest=manifest,
        events=tuple(events),
        trials=trials,
        attached_daily_series=attachments,
        status=status,
    )


def _trial_record_from_dict(value: Mapping[str, Any]) -> TrialRecord:
    raw = dict(value)
    trial_id = raw.pop("trial_id", None)
    payload_sha256 = raw.pop("payload_sha256", None)
    if not isinstance(trial_id, str) or not isinstance(
        payload_sha256, str
    ):
        raise TrialLedgerError(
            "stored trial record identifiers are missing"
        )
    canonical = _canonical_json(raw)
    return TrialRecord(trial_id, payload_sha256, canonical)


def _validate_ledger_manifest(manifest: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "permanent_trial_counter_namespace",
        "append_only",
        "deletion_supported",
        "mutation_supported",
        "cache_reuse_counts_as_independent_trial",
        "required_historical_import_sha256",
    }
    if set(manifest) != required:
        raise TrialLedgerError("trial ledger manifest fields are invalid")
    if manifest.get("schema_version") != LEDGER_SCHEMA_VERSION:
        raise TrialLedgerError("trial ledger schema is invalid")
    if (
        manifest.get("permanent_trial_counter_namespace")
        != PERMANENT_TRIAL_COUNTER_NAMESPACE
    ):
        raise TrialLedgerError(
            "permanent trial counter namespace is invalid"
        )
    if (
        manifest.get("append_only") is not True
        or manifest.get("deletion_supported") is not False
        or manifest.get("mutation_supported") is not False
        or manifest.get("cache_reuse_counts_as_independent_trial")
        is not False
    ):
        raise TrialLedgerError(
            "trial ledger append-only policy is invalid"
        )
    digest = manifest.get("required_historical_import_sha256")
    if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
        raise TrialLedgerError(
            "required historical import digest is invalid"
        )


def _merge_observed_source_count(
    observed_rows_by_source: dict[str, int],
    observed_artifacts_by_source: dict[str, str | None],
    observed_keys_by_source: dict[str, tuple[str, ...] | None],
    source_id: Any,
    count: Any,
    *,
    artifact_sha256: str | None = None,
    observation_keys: Sequence[str] | None = None,
) -> None:
    normalized_source_id = _required_text(source_id, "historical source_id")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise TrialLedgerError(
            "historical observed row count must be a non-negative integer"
        )
    existing = observed_rows_by_source.get(normalized_source_id)
    if existing is not None and existing != count:
        raise TrialLedgerError(
            "historical source provenance has contradictory row counts"
        )
    if artifact_sha256 is not None and not _HEX64_RE.fullmatch(
        artifact_sha256
    ):
        raise TrialLedgerError(
            "historical source provenance artifact digest is invalid"
        )
    existing_artifact = observed_artifacts_by_source.get(
        normalized_source_id
    )
    if (
        artifact_sha256 is not None
        and existing_artifact is not None
        and existing_artifact != artifact_sha256
    ):
        raise TrialLedgerError(
            "historical source provenance references conflicting artifacts"
        )
    normalized_observation_keys: tuple[str, ...] | None = None
    if observation_keys is not None:
        normalized_observation_keys = tuple(observation_keys)
        if (
            len(normalized_observation_keys) != count
            or len(set(normalized_observation_keys))
            != len(normalized_observation_keys)
            or any(
                not isinstance(key, str)
                or not _OBSERVATION_KEY_RE.fullmatch(key)
                for key in normalized_observation_keys
            )
        ):
            raise TrialLedgerError(
                "historical observation-key inventory is inconsistent"
            )
    existing_keys = observed_keys_by_source.get(normalized_source_id)
    if (
        normalized_observation_keys is not None
        and existing_keys is not None
        and existing_keys != normalized_observation_keys
    ):
        raise TrialLedgerError(
            "historical source provenance has conflicting observation keys"
        )
    observed_rows_by_source[normalized_source_id] = count
    observed_artifacts_by_source[normalized_source_id] = (
        artifact_sha256
        if artifact_sha256 is not None
        else existing_artifact
    )
    observed_keys_by_source[normalized_source_id] = (
        normalized_observation_keys
        if normalized_observation_keys is not None
        else existing_keys
    )


def _observed_evidence_by_provenance_from_events(
    events: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[str, int],
    dict[str, str | None],
    dict[str, tuple[str, ...] | None],
]:
    observed_rows_by_source: dict[str, int] = {}
    observed_artifacts_by_source: dict[str, str | None] = {}
    observed_keys_by_source: dict[str, tuple[str, ...] | None] = {}
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            raise TrialLedgerError("trial ledger event payload is invalid")
        if event.get("event_type") == "historical_lower_bound_import":
            source_counts = payload.get("observed_rows_by_source")
            if source_counts is None:
                source_counts = {
                    "canonical_manifest:"
                    f"{payload.get('manifest_sha256')}": payload.get(
                        "known_observed_evaluation_rows", 0
                    )
                }
            if not isinstance(source_counts, Mapping):
                raise TrialLedgerError(
                    "canonical historical source provenance is invalid"
                )
            for source_id, count in source_counts.items():
                _merge_observed_source_count(
                    observed_rows_by_source,
                    observed_artifacts_by_source,
                    observed_keys_by_source,
                    source_id,
                    count,
                )
        elif event.get("event_type") == "historical_import_summary":
            source_sha256 = payload.get("source_sha256")
            source_id = payload.get(
                "source_id", f"report_sha256:{source_sha256}"
            )
            _merge_observed_source_count(
                observed_rows_by_source,
                observed_artifacts_by_source,
                observed_keys_by_source,
                source_id,
                payload.get("observed_evaluation_rows"),
                artifact_sha256=str(source_sha256),
                observation_keys=(
                    tuple(payload["observation_keys"])
                    if isinstance(payload.get("observation_keys"), list)
                    else None
                ),
            )
    return (
        observed_rows_by_source,
        observed_artifacts_by_source,
        observed_keys_by_source,
    )


def _missing_daily_series_trial_ids(
    trials: Mapping[str, Mapping[str, Any]],
    attachments: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[str]:
    return sorted(
        trial_id
        for trial_id, trial in trials.items()
        if trial.get("daily_net_mtm_usdc") is None
        and trial_id not in attachments
    )


def _incomplete_historical_trial_ids(
    trials: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    required_true = (
        "candidate_identity_complete",
        "seed_complete",
        "versions_complete",
        "code_commit_complete",
        "daily_series_complete",
    )
    incomplete: list[str] = []
    for trial_id, trial in trials.items():
        identity = trial.get("identity_basis")
        if (
            not isinstance(identity, Mapping)
            or identity.get("source_kind") != "historical_import"
        ):
            continue
        completeness = trial.get("completeness")
        if (
            not isinstance(completeness, Mapping)
            or any(completeness.get(field) is not True for field in required_true)
            or completeness.get("missing_fields") != []
        ):
            incomplete.append(trial_id)
    return sorted(incomplete)


def _validate_historical_source_assignments(
    trials: Mapping[str, Mapping[str, Any]],
    observed_rows_by_source: Mapping[str, int],
    observed_artifacts_by_source: Mapping[str, str | None],
    observed_keys_by_source: Mapping[str, Sequence[str] | None],
) -> None:
    expected_assignments: set[tuple[str, str]] = set()
    seen_artifacts: dict[str, str] = {}
    for source_id, count in observed_rows_by_source.items():
        artifact_sha256 = observed_artifacts_by_source.get(source_id)
        observation_keys = observed_keys_by_source.get(source_id)
        if artifact_sha256 is None or observation_keys is None:
            raise TrialLedgerError(
                "historical completion lacks immutable source artifacts or "
                "per-row observation provenance"
            )
        prior_source = seen_artifacts.get(artifact_sha256)
        if prior_source is not None and prior_source != source_id:
            raise TrialLedgerError(
                "one historical artifact cannot attest multiple sources"
            )
        seen_artifacts[artifact_sha256] = source_id
        if len(observation_keys) != count:
            raise TrialLedgerError(
                "historical source observation inventory is incomplete"
            )
        expected_assignments.update(
            (artifact_sha256, observation_key)
            for observation_key in observation_keys
        )

    actual_assignments: list[tuple[str, str]] = []
    for trial in trials.values():
        identity = trial.get("identity_basis")
        if (
            not isinstance(identity, Mapping)
            or identity.get("source_kind") != "historical_import"
        ):
            continue
        actual_assignments.append(
            (
                str(trial.get("historical_source_sha256")),
                str(trial.get("historical_observation_key")),
            )
        )
    if (
        len(set(actual_assignments)) != len(actual_assignments)
        or set(actual_assignments) != expected_assignments
    ):
        raise TrialLedgerError(
            "historical trials are not exactly mapped to immutable source "
            "observation rows"
        )


def _inventory_evidence_sha256(
    manifest: Mapping[str, Any],
    trials: Mapping[str, Mapping[str, Any]],
    attachments: Mapping[str, Sequence[Mapping[str, Any]]],
) -> str:
    inventory: list[dict[str, Any]] = []
    for trial_id in sorted(trials):
        trial = trials[trial_id]
        daily_sha256 = trial.get("daily_series_sha256")
        if daily_sha256 is None and trial_id in attachments:
            daily_sha256 = _sha256_json(list(attachments[trial_id]))
        inventory.append(
            {
                "trial_id": trial_id,
                "payload_sha256": trial.get("payload_sha256"),
                "daily_series_sha256": daily_sha256,
            }
        )
    return _sha256_json(
        {
            "schema_version": "protocol_v3_trial_inventory_evidence_v1",
            "required_historical_import_sha256": manifest.get(
                "required_historical_import_sha256"
            ),
            "trial_inventory": inventory,
        }
    )


def _reconciliation_evidence_sha256(
    manifest: Mapping[str, Any],
    trials: Mapping[str, Mapping[str, Any]],
    attachments: Mapping[str, Sequence[Mapping[str, Any]]],
    observed_rows_by_source: Mapping[str, int],
    observed_artifacts_by_source: Mapping[str, str | None],
    observed_keys_by_source: Mapping[
        str, Sequence[str] | None
    ],
) -> str:
    historical_inventory: list[dict[str, Any]] = []
    for trial_id in sorted(trials):
        trial = trials[trial_id]
        identity = trial.get("identity_basis")
        if (
            not isinstance(identity, Mapping)
            or identity.get("source_kind") != "historical_import"
        ):
            continue
        daily_sha256 = trial.get("daily_series_sha256")
        if daily_sha256 is None and trial_id in attachments:
            daily_sha256 = _sha256_json(list(attachments[trial_id]))
        historical_inventory.append(
            {
                "trial_id": trial_id,
                "payload_sha256": trial.get("payload_sha256"),
                "daily_series_sha256": daily_sha256,
                "completeness": trial.get("completeness"),
            }
        )
    return _sha256_json(
        {
            "schema_version": (
                "protocol_v3_historical_reconciliation_evidence_v1"
            ),
            "required_historical_import_sha256": manifest.get(
                "required_historical_import_sha256"
            ),
            "observed_sources": {
                source_id: {
                    "observed_evaluation_rows": (
                        observed_rows_by_source[source_id]
                    ),
                    "artifact_sha256": observed_artifacts_by_source.get(
                        source_id
                    ),
                    "observation_keys": (
                        list(observed_keys_by_source[source_id])
                        if observed_keys_by_source.get(source_id) is not None
                        else None
                    ),
                }
                for source_id in sorted(observed_rows_by_source)
            },
            "historical_trial_inventory": historical_inventory,
        }
    )


def _head_payload(
    event_count: int,
    event_head_sha256: str,
    resolved_trial_count: int,
) -> dict[str, Any]:
    body = {
        "schema_version": "protocol_v3_trial_ledger_head_v1",
        "event_count": event_count,
        "event_head_sha256": event_head_sha256,
        "resolved_trial_count": resolved_trial_count,
    }
    return {**body, "head_sha256": _sha256_json(body)}


def _validate_head(
    head: Mapping[str, Any],
    event_heads: Sequence[str],
    resolved_counts: Sequence[int],
) -> None:
    body = dict(head)
    digest = body.pop("head_sha256", None)
    if digest != _sha256_json(body):
        raise TrialLedgerError("trial ledger head digest is invalid")
    head_event_count = head.get("event_count")
    if (
        isinstance(head_event_count, bool)
        or not isinstance(head_event_count, int)
        or head_event_count < 0
        or head_event_count >= len(event_heads)
        or len(event_heads) != len(resolved_counts)
    ):
        raise TrialLedgerError(
            "trial ledger head is ahead of or unrelated to immutable events"
        )
    expected = _head_payload(
        head_event_count,
        event_heads[head_event_count],
        resolved_counts[head_event_count],
    )
    if dict(head) != expected:
        raise TrialLedgerError(
            "trial ledger head does not match its immutable event prefix"
        )


@contextmanager
def _ledger_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".ledger.lock"
    try:
        descriptor = os.open(
            lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
        )
    except FileExistsError as exc:
        raise TrialLedgerError(
            "trial ledger is locked; stale locks fail closed"
        ) from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise TrialLedgerError(f"append-only file already exists: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = (_canonical_json(payload) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise TrialLedgerError(
                f"append-only file appeared concurrently: {path}"
            )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_replace_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = (_canonical_json(payload) + "\n").encode("utf-8")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TrialLedgerError(
            f"{label} is missing or invalid: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise TrialLedgerError(f"{label} root must be an object")
    return value


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


def _normalize_daily_series(
    rows: Sequence[Mapping[str, Any]],
    *,
    allow_empty: bool,
) -> list[dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        raise TrialLedgerError("daily series must be a sequence")
    normalized: list[dict[str, Any]] = []
    previous_day: date | None = None
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"day", "net_usdc"}:
            raise TrialLedgerError(
                "daily series rows require day and net_usdc only"
            )
        try:
            day_value = date.fromisoformat(str(row["day"]))
        except ValueError as exc:
            raise TrialLedgerError(
                "daily series contains an invalid ISO day"
            ) from exc
        value = row["net_usdc"]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise TrialLedgerError(
                "daily series contains a non-finite numeric value"
            )
        if previous_day is not None and day_value <= previous_day:
            raise TrialLedgerError(
                "daily series days must be strictly increasing and unique"
            )
        normalized.append(
            {"day": day_value.isoformat(), "net_usdc": float(value)}
        )
        previous_day = day_value
    if not normalized and not allow_empty:
        raise TrialLedgerError("daily series must not be empty")
    return normalized


def _validate_versions(
    versions: Mapping[str, Any],
    *,
    allow_unknown: bool,
) -> dict[str, str]:
    if not isinstance(versions, Mapping) or set(versions) != _REQUIRED_VERSIONS:
        raise TrialLedgerError(
            "versions must define every required version binding"
        )
    normalized: dict[str, str] = {}
    for key in sorted(_REQUIRED_VERSIONS):
        value = str(versions[key]).strip()
        if not value or (
            not allow_unknown and value.lower() == "unknown"
        ):
            raise TrialLedgerError(
                f"version binding is invalid: {key}"
            )
        normalized[key] = value
    return normalized


def _normalize_nonempty_object(
    value: Mapping[str, Any],
    label: str,
) -> dict[str, Any]:
    normalized = _normalize_object(value, label)
    if not normalized:
        raise TrialLedgerError(f"{label} must not be empty")
    return normalized


def _normalize_object(
    value: Mapping[str, Any],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TrialLedgerError(f"{label} must be an object")
    normalized = _normalize_json(dict(value))
    if not isinstance(normalized, dict):
        raise TrialLedgerError(f"{label} must be an object")
    return normalized


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrialLedgerError(f"{label} must be a non-empty string")
    return value.strip()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _normalize_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_json(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TrialLedgerError(
                "non-finite values are forbidden in ledger JSON"
            )
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TrialLedgerError(
                    "ledger JSON object keys must be strings"
                )
            normalized[key] = _normalize_json(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    raise TrialLedgerError(
        f"unsupported ledger JSON type: {type(value).__name__}"
    )


__all__ = [
    "CANONICAL_HISTORICAL_IMPORT_PATH",
    "DEVELOPMENT_DSR_INSUFFICIENT",
    "DEVELOPMENT_DSR_READY",
    "EVENT_SCHEMA_VERSION",
    "HISTORICAL_IMPORT_SCHEMA_VERSION",
    "LEDGER_SCHEMA_VERSION",
    "NO_TRADE",
    "PERMANENT_TRIAL_COUNTER_NAMESPACE",
    "TRADING_CANDIDATE",
    "TRIAL_RECORD_SCHEMA_VERSION",
    "HistoricalImportResult",
    "TrialLedgerError",
    "TrialLedgerSnapshot",
    "TrialLedgerStatus",
    "TrialRecord",
    "append_trial",
    "assert_release_decision_allowed",
    "attach_trial_daily_series",
    "attest_complete_trial_inventory",
    "build_canonical_historical_import_digest",
    "build_historical_reconciliation_evidence_sha256",
    "build_trial_inventory_evidence_sha256",
    "build_trial_record",
    "import_canonical_historical_lower_bound",
    "import_historical_reports",
    "initialize_trial_ledger",
    "read_trial_ledger",
    "record_cache_reuse",
    "validate_historical_lower_bound_manifest",
    "validate_trial_record",
]
