"""Compact content-addressed Protocol v3 artifact architecture for Task 12.

The store persists canonical, validated objects first and publishes a small
reference-only index only after every referenced object has been reloaded and
semantically verified.  This module does not implement Task-13 crash/resume
transactions, Task-14 folds, Task-23 outer orchestration, trading, or orders.
"""
from __future__ import annotations
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Final
from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.protocol_v3.reporting_api import read_protocol_v3_report
ARTIFACT_STORE_CONTRACT_PATH: Final = Path('configs/protocol_v3_artifact_store_contract.json')
ARTIFACT_STORE_CONTRACT_SCHEMA: Final = 'protocol_v3_artifact_store_contract_v1'
ARTIFACT_STORE_CONTRACT_VERSION: Final = 'protocol_v3_compact_artifact_store_v1'
ARTIFACT_OBJECT_SCHEMA_VERSION: Final = 'protocol_v3_artifact_object_v1'
ARTIFACT_REFERENCE_SCHEMA_VERSION: Final = 'protocol_v3_artifact_reference_v1'
ARTIFACT_INDEX_SCHEMA_VERSION: Final = 'protocol_v3_artifact_index_v1'
INDEX_SIZE_POLICY_VERSION: Final = 'protocol_v3_compact_index_size_policy_v1'
PROTOCOL_VERSION: Final = '3.0.0'
OBJECT_ROOT: Final = 'reports/protocol_v3/artifacts/objects'
INDEX_ROOT: Final = 'reports/protocol_v3/artifact_indexes'
TRADES: Final = 'trades'
DAILY_MTM: Final = 'daily_mtm'
EQUITY_UNDERWATER: Final = 'equity_underwater'
DIAGNOSTICS: Final = 'diagnostics'
ARTIFACT_KINDS: Final = (TRADES, DAILY_MTM, EQUITY_UNDERWATER, DIAGNOSTICS)
ARTIFACT_SCHEMAS: Final = {TRADES: 'protocol_v3_trades_v1', DAILY_MTM: 'protocol_v3_daily_mtm_v1', EQUITY_UNDERWATER: 'protocol_v3_equity_underwater_v1', DIAGNOSTICS: 'protocol_v3_fold_candidate_diagnostics_v1'}
MAX_REFERENCES: Final = 768
MAX_INDEX_BYTES: Final = 1048576
MAX_WORK_UNIT_IDENTITY_BYTES: Final = 16384
REPRESENTATIVE_REFERENCES: Final = 384
_HEX64_RE = re.compile('^[0-9a-f]{64}$')
_SAFE_ID_RE = re.compile('^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
_PIPELINE_RE = re.compile('^protocol_v3_pipeline_sha256:[0-9a-f]{64}$')
_RUN_RE = re.compile('^protocol_v3_run_sha256:[0-9a-f]{64}$')
_INDEX_ID_RE = re.compile('^protocol_v3_artifact_index_sha256:[0-9a-f]{64}$')
_FORBIDDEN_RAW_KEYS = {'candles', 'raw_candles', 'klines', 'ohlcv', 'market_bars', 'one_minute_bars', 'raw_market_data'}
_OBJECT_KEYS = {'schema_version', 'protocol_version', 'artifact_kind', 'artifact_schema', 'coverage', 'logical_cardinality', 'records'}
_REFERENCE_KEYS = {'schema_version', 'reference_id', 'artifact_kind', 'artifact_schema', 'sha256', 'byte_size', 'logical_cardinality', 'relative_path', 'provenance'}
_PROVENANCE_KEYS = {'parent_report_id', 'parent_report_sha256', 'run_fingerprint', 'pipeline_generation', 'work_unit_id', 'work_unit_sha256'}
_INDEX_KEYS = {'schema_version', 'protocol_version', 'contract_version', 'index_id', 'parent_report', 'run_fingerprint', 'pipeline_generation', 'work_unit', 'artifacts', 'index_sha256'}
_PARENT_REPORT_KEYS = {'report_id', 'report_sha256', 'relative_path'}
_WORK_UNIT_KEYS = {'work_unit_id', 'work_unit_sha256', 'identity'}
_DAILY_COVERAGE_KEYS = {'start_inclusive_utc', 'end_exclusive_utc', 'calendar_days'}
_CANONICAL_CONTRACT: dict[str, Any] = {'schema_version': ARTIFACT_STORE_CONTRACT_SCHEMA, 'protocol_version': PROTOCOL_VERSION, 'contract_version': ARTIFACT_STORE_CONTRACT_VERSION, 'object_schema_version': ARTIFACT_OBJECT_SCHEMA_VERSION, 'reference_schema_version': ARTIFACT_REFERENCE_SCHEMA_VERSION, 'index_schema_version': ARTIFACT_INDEX_SCHEMA_VERSION, 'object_root': OBJECT_ROOT, 'index_root': INDEX_ROOT, 'artifact_kinds': {DAILY_MTM: {'artifact_schema': ARTIFACT_SCHEMAS[DAILY_MTM], 'cardinality_unit': 'utc_days', 'coverage_policy': 'complete_contiguous_utc_day_grid'}, DIAGNOSTICS: {'artifact_schema': ARTIFACT_SCHEMAS[DIAGNOSTICS], 'cardinality_unit': 'records', 'coverage_policy': 'not_applicable'}, EQUITY_UNDERWATER: {'artifact_schema': ARTIFACT_SCHEMAS[EQUITY_UNDERWATER], 'cardinality_unit': 'points', 'coverage_policy': 'ordered_unique_utc_timestamps'}, TRADES: {'artifact_schema': ARTIFACT_SCHEMAS[TRADES], 'cardinality_unit': 'trades', 'coverage_policy': 'ordered_unique_trade_ids'}}, 'storage_policy': {'content_address_algorithm': 'sha256_actual_canonical_bytes_v1', 'object_relative_path': '<artifact_kind>/<sha256_prefix_2>/<sha256>.json', 'existing_object_requires_full_reload_and_semantic_validation': True, 'overwrite_existing_object': False, 'publish_index_only_after_all_objects_reloaded': True, 'deduplicate_only_identical_bytes_and_semantics': True, 'large_generated_artifacts_gitignored': True, 'raw_candles_forbidden': True, 'index_embeds_records': False}, 'provenance_policy': {'required_fields': ['parent_report_id', 'parent_report_sha256', 'run_fingerprint', 'pipeline_generation', 'work_unit_id', 'work_unit_sha256'], 'parent_report_must_be_persisted_and_revalidated': True, 'work_unit_identity_is_embedded_once_in_index': True, 'references_must_match_index_provenance': True}, 'size_policy': {'version': INDEX_SIZE_POLICY_VERSION, 'rationale': '12 origins x 8 cycles x 4 artifact references = 384 references; limits provide 2x reference headroom while remaining independent of candle and curve row counts', 'representative_outer_origins': 12, 'representative_cycles_per_origin': 8, 'artifact_types_per_cycle': 4, 'representative_references': REPRESENTATIVE_REFERENCES, 'max_references': MAX_REFERENCES, 'max_index_bytes': MAX_INDEX_BYTES, 'max_work_unit_identity_bytes': MAX_WORK_UNIT_IDENTITY_BYTES}, 'deferred_scope': {'transactional_resume_task': 13, 'fold_planner_task': 14, 'outer_orchestration_task': 23}, 'safety': {'api_keys': 'forbidden', 'live': 'locked', 'orders': 'locked', 'paper': 'locked', 'testtrade': 'locked', 'trading_api': 'forbidden'}}

class ProtocolV3ArtifactStoreError(ValueError):
    """Raised when compact artifacts or their provenance fail closed."""

@dataclass(frozen=True)
class ArtifactPayload:
    canonical_json: str
    sha256: str
    byte_size: int
    logical_cardinality: int

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)

    @property
    def artifact_kind(self) -> str:
        return str(self.to_dict()['artifact_kind'])

    @property
    def artifact_schema(self) -> str:
        return str(self.to_dict()['artifact_schema'])

    @property
    def canonical_bytes(self) -> bytes:
        return _serialized_bytes(self.canonical_json)

@dataclass(frozen=True)
class CompactArtifactIndex:
    canonical_json: str
    index_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)

@dataclass(frozen=True)
class CompactArtifactBundle:
    index: CompactArtifactIndex
    artifacts: Mapping[str, ArtifactPayload]

def load_artifact_store_contract(repo_root: str | Path | None=None, *, contract_path: str | Path | None=None) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    path = Path(contract_path) if contract_path is not None else root / ARTIFACT_STORE_CONTRACT_PATH
    if not path.is_absolute():
        path = root / path
    try:
        value = _strict_json_loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolV3ArtifactStoreError(f'Protocol v3 artifact-store contract is missing or invalid: {path}') from exc
    validate_artifact_store_contract(value)
    return value

def validate_artifact_store_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize_json(value) != _CANONICAL_CONTRACT:
        raise ProtocolV3ArtifactStoreError('Protocol v3 artifact-store contract is not canonical')

def build_artifact_payload(artifact_kind: str, records: Sequence[Mapping[str, Any]], *, coverage: Mapping[str, Any] | None=None) -> ArtifactPayload:
    if artifact_kind not in ARTIFACT_KINDS:
        raise ProtocolV3ArtifactStoreError(f'unsupported Protocol v3 artifact_kind: {artifact_kind!r}')
    if isinstance(records, (str, bytes, bytearray)) or not isinstance(records, Sequence):
        raise ProtocolV3ArtifactStoreError('artifact records must be a sequence')
    normalized_records = [dict(_mapping(row, 'artifact record')) for row in records]
    payload = {'schema_version': ARTIFACT_OBJECT_SCHEMA_VERSION, 'protocol_version': PROTOCOL_VERSION, 'artifact_kind': artifact_kind, 'artifact_schema': ARTIFACT_SCHEMAS[artifact_kind], 'coverage': dict(coverage) if coverage is not None else None, 'logical_cardinality': len(normalized_records), 'records': normalized_records}
    return validate_artifact_payload(payload)

def validate_artifact_payload(value: ArtifactPayload | Mapping[str, Any]) -> ArtifactPayload:
    root = value.to_dict() if isinstance(value, ArtifactPayload) else dict(_mapping(value, 'artifact_object'))
    _exact_keys(root, _OBJECT_KEYS, 'artifact_object')
    _literal(root, 'schema_version', ARTIFACT_OBJECT_SCHEMA_VERSION, 'artifact_object')
    _literal(root, 'protocol_version', PROTOCOL_VERSION, 'artifact_object')
    kind = root.get('artifact_kind')
    if kind not in ARTIFACT_KINDS:
        raise ProtocolV3ArtifactStoreError('artifact_object.artifact_kind is invalid')
    _literal(root, 'artifact_schema', ARTIFACT_SCHEMAS[str(kind)], 'artifact_object')
    records = root.get('records')
    if not isinstance(records, list):
        raise ProtocolV3ArtifactStoreError('artifact_object.records must be a list')
    cardinality = root.get('logical_cardinality')
    if type(cardinality) is not int or cardinality != len(records):
        raise ProtocolV3ArtifactStoreError('artifact_object.logical_cardinality must equal the actual record count')
    coverage = root.get('coverage')
    if kind == TRADES:
        if coverage is not None:
            raise ProtocolV3ArtifactStoreError('trades coverage must be null')
        _validate_trade_records(records)
    elif kind == DAILY_MTM:
        _validate_daily_mtm_records(records, coverage)
    elif kind == EQUITY_UNDERWATER:
        if coverage is not None:
            raise ProtocolV3ArtifactStoreError('equity_underwater coverage must be null')
        _validate_equity_records(records)
    else:
        if coverage is not None:
            raise ProtocolV3ArtifactStoreError('diagnostics coverage must be null')
        _validate_diagnostic_records(records)
    _reject_raw_candle_payloads(root, 'artifact_object')
    _assert_finite_json(root, 'artifact_object')
    canonical = _canonical_json(root)
    raw = _serialized_bytes(canonical)
    digest = hashlib.sha256(raw).hexdigest()
    return ArtifactPayload(canonical, digest, len(raw), len(records))

def persist_compact_artifact_bundle(*, parent_report_path: str | Path, repository_root: str | Path, work_unit_id: str, work_unit_identity: Mapping[str, Any], artifacts: Mapping[str, ArtifactPayload]) -> Path:
    """Persist validated objects, reload them, then publish one compact index."""
    repo = _repository_root(repository_root)
    report_path = Path(parent_report_path)
    report = read_protocol_v3_report(report_path, repo)
    report_payload = report.to_dict()
    report_resolved = report_path.resolve(strict=True)
    if not is_path_within(report_resolved, repo):
        raise ProtocolV3ArtifactStoreError('parent report escapes repository_root')
    parent_relative = report_resolved.relative_to(repo).as_posix()
    parent_raw = report_resolved.read_bytes()
    parent_sha = hashlib.sha256(parent_raw).hexdigest()
    work_id = _safe_identifier(work_unit_id, 'work_unit_id')
    identity = dict(_mapping(work_unit_identity, 'work_unit_identity'))
    _reject_raw_candle_payloads(identity, 'work_unit_identity')
    _assert_finite_json(identity, 'work_unit_identity')
    identity_bytes = _serialized_bytes(_canonical_json(identity))
    if len(identity_bytes) > MAX_WORK_UNIT_IDENTITY_BYTES:
        raise ProtocolV3ArtifactStoreError('work_unit_identity exceeds the versioned compact size policy')
    work_sha = hashlib.sha256(identity_bytes).hexdigest()
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise ProtocolV3ArtifactStoreError('at least one artifact reference is required')
    if len(artifacts) > MAX_REFERENCES:
        raise ProtocolV3ArtifactStoreError('artifact reference count exceeds size policy')
    provenance = {'parent_report_id': report.report_id, 'parent_report_sha256': parent_sha, 'run_fingerprint': report_payload['run_fingerprint'], 'pipeline_generation': report_payload['pipeline_generation'], 'work_unit_id': work_id, 'work_unit_sha256': work_sha}
    references: list[dict[str, Any]] = []
    for reference_id in sorted(artifacts):
        ref_id = _safe_identifier(reference_id, 'reference_id')
        payload = validate_artifact_payload(artifacts[reference_id])
        reference = _persist_or_validate_object(payload=payload, reference_id=ref_id, provenance=provenance, repository_root=repo)
        references.append(reference)
    index_payload = _build_index_payload(parent_report={'report_id': report.report_id, 'report_sha256': parent_sha, 'relative_path': parent_relative}, run_fingerprint=str(report_payload['run_fingerprint']), pipeline_generation=str(report_payload['pipeline_generation']), work_unit={'work_unit_id': work_id, 'work_unit_sha256': work_sha, 'identity': identity}, references=references)
    index = validate_artifact_index(index_payload)
    index_root = _safe_storage_root(repo, INDEX_ROOT, create=True)
    parent_dir = index_root / report.report_id
    _ensure_safe_directory(repo, parent_dir)
    index_path = parent_dir / f'{work_id}.json'
    _write_create_only(index_path, _serialized_bytes(index.canonical_json))
    reloaded = read_compact_artifact_bundle(index_path, repo)
    if reloaded.index != index:
        raise ProtocolV3ArtifactStoreError('artifact index reload mismatch')
    return index_path

def read_compact_artifact_bundle(index_path: str | Path, repository_root: str | Path) -> CompactArtifactBundle:
    repo = _repository_root(repository_root)
    path = Path(index_path)
    value, raw = _read_strict_canonical_json(path)
    index = validate_artifact_index(value)
    if raw != _serialized_bytes(index.canonical_json):
        raise ProtocolV3ArtifactStoreError('artifact index bytes are not canonical')
    payload = index.to_dict()
    expected_root = _safe_storage_root(repo, INDEX_ROOT, create=False)
    parent = dict(_mapping(payload['parent_report'], 'artifact_index.parent_report'))
    work = dict(_mapping(payload['work_unit'], 'artifact_index.work_unit'))
    expected = expected_root / str(parent['report_id']) / f"{work['work_unit_id']}.json"
    _require_exact_path(path, expected, expected_root)
    report_relative = _safe_relative_path(parent['relative_path'], 'artifact_index.parent_report.relative_path')
    report_path = repo.joinpath(*report_relative.parts)
    report = read_protocol_v3_report(report_path, repo)
    report_raw = report_path.read_bytes()
    if report.report_id != parent['report_id']:
        raise ProtocolV3ArtifactStoreError('parent report id mismatch')
    if hashlib.sha256(report_raw).hexdigest() != parent['report_sha256']:
        raise ProtocolV3ArtifactStoreError('parent report digest mismatch')
    report_payload = report.to_dict()
    if report_payload['run_fingerprint'] != payload['run_fingerprint']:
        raise ProtocolV3ArtifactStoreError('parent report run fingerprint mismatch')
    if report_payload['pipeline_generation'] != payload['pipeline_generation']:
        raise ProtocolV3ArtifactStoreError('parent report pipeline generation mismatch')
    identity = dict(_mapping(work['identity'], 'artifact_index.work_unit.identity'))
    identity_digest = hashlib.sha256(_serialized_bytes(_canonical_json(identity))).hexdigest()
    if identity_digest != work['work_unit_sha256']:
        raise ProtocolV3ArtifactStoreError('work-unit identity digest mismatch')
    expected_provenance = {'parent_report_id': parent['report_id'], 'parent_report_sha256': parent['report_sha256'], 'run_fingerprint': payload['run_fingerprint'], 'pipeline_generation': payload['pipeline_generation'], 'work_unit_id': work['work_unit_id'], 'work_unit_sha256': work['work_unit_sha256']}
    loaded: dict[str, ArtifactPayload] = {}
    for reference_value in payload['artifacts']:
        reference = validate_artifact_reference(reference_value)
        if reference['provenance'] != expected_provenance:
            raise ProtocolV3ArtifactStoreError('artifact reference provenance does not match its index')
        object_path = _object_path_from_reference(reference, repo)
        artifact = _read_artifact_object(object_path, reference)
        reference_id = str(reference['reference_id'])
        if reference_id in loaded:
            raise ProtocolV3ArtifactStoreError('duplicate artifact reference_id')
        loaded[reference_id] = artifact
    return CompactArtifactBundle(index=index, artifacts=loaded)

def validate_artifact_reference(value: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(_mapping(value, 'artifact_reference'))
    _exact_keys(root, _REFERENCE_KEYS, 'artifact_reference')
    _literal(root, 'schema_version', ARTIFACT_REFERENCE_SCHEMA_VERSION, 'artifact_reference')
    _safe_identifier(root.get('reference_id'), 'artifact_reference.reference_id')
    kind = root.get('artifact_kind')
    if kind not in ARTIFACT_KINDS:
        raise ProtocolV3ArtifactStoreError('artifact_reference.artifact_kind is invalid')
    _literal(root, 'artifact_schema', ARTIFACT_SCHEMAS[str(kind)], 'artifact_reference')
    digest = _sha256(root.get('sha256'), 'artifact_reference.sha256')
    byte_size = root.get('byte_size')
    if type(byte_size) is not int or byte_size <= 0:
        raise ProtocolV3ArtifactStoreError('artifact_reference.byte_size must be positive')
    cardinality = root.get('logical_cardinality')
    if type(cardinality) is not int or cardinality < 0:
        raise ProtocolV3ArtifactStoreError('artifact_reference.logical_cardinality must be non-negative')
    relative = _safe_relative_path(root.get('relative_path'), 'artifact_reference.relative_path')
    expected = _object_relative_path(str(kind), digest)
    if relative != expected:
        raise ProtocolV3ArtifactStoreError('artifact_reference.relative_path does not match its content address')
    provenance = dict(_mapping(root.get('provenance'), 'artifact_reference.provenance'))
    _exact_keys(provenance, _PROVENANCE_KEYS, 'artifact_reference.provenance')
    _safe_identifier(provenance.get('parent_report_id'), 'provenance.parent_report_id')
    _sha256(provenance.get('parent_report_sha256'), 'provenance.parent_report_sha256')
    _run_fingerprint(provenance.get('run_fingerprint'))
    _pipeline_generation(provenance.get('pipeline_generation'))
    _safe_identifier(provenance.get('work_unit_id'), 'provenance.work_unit_id')
    _sha256(provenance.get('work_unit_sha256'), 'provenance.work_unit_sha256')
    _assert_finite_json(root, 'artifact_reference')
    return _normalize_json(root)

def validate_artifact_index(value: CompactArtifactIndex | Mapping[str, Any]) -> CompactArtifactIndex:
    root = value.to_dict() if isinstance(value, CompactArtifactIndex) else dict(_mapping(value, 'artifact_index'))
    _exact_keys(root, _INDEX_KEYS, 'artifact_index')
    _literal(root, 'schema_version', ARTIFACT_INDEX_SCHEMA_VERSION, 'artifact_index')
    _literal(root, 'protocol_version', PROTOCOL_VERSION, 'artifact_index')
    _literal(root, 'contract_version', ARTIFACT_STORE_CONTRACT_VERSION, 'artifact_index')
    _run_fingerprint(root.get('run_fingerprint'))
    _pipeline_generation(root.get('pipeline_generation'))
    parent = dict(_mapping(root.get('parent_report'), 'artifact_index.parent_report'))
    _exact_keys(parent, _PARENT_REPORT_KEYS, 'artifact_index.parent_report')
    _safe_identifier(parent.get('report_id'), 'artifact_index.parent_report.report_id')
    _sha256(parent.get('report_sha256'), 'artifact_index.parent_report.report_sha256')
    _safe_relative_path(parent.get('relative_path'), 'artifact_index.parent_report.relative_path')
    work = dict(_mapping(root.get('work_unit'), 'artifact_index.work_unit'))
    _exact_keys(work, _WORK_UNIT_KEYS, 'artifact_index.work_unit')
    _safe_identifier(work.get('work_unit_id'), 'artifact_index.work_unit.work_unit_id')
    work_sha = _sha256(work.get('work_unit_sha256'), 'artifact_index.work_unit.work_unit_sha256')
    identity = dict(_mapping(work.get('identity'), 'artifact_index.work_unit.identity'))
    _reject_raw_candle_payloads(identity, 'artifact_index.work_unit.identity')
    _assert_finite_json(identity, 'artifact_index.work_unit.identity')
    identity_bytes = _serialized_bytes(_canonical_json(identity))
    if len(identity_bytes) > MAX_WORK_UNIT_IDENTITY_BYTES:
        raise ProtocolV3ArtifactStoreError('work-unit identity exceeds size policy')
    if hashlib.sha256(identity_bytes).hexdigest() != work_sha:
        raise ProtocolV3ArtifactStoreError('artifact_index work-unit digest mismatch')
    artifacts = root.get('artifacts')
    if not isinstance(artifacts, list) or not artifacts:
        raise ProtocolV3ArtifactStoreError('artifact_index.artifacts must be a non-empty list')
    if len(artifacts) > MAX_REFERENCES:
        raise ProtocolV3ArtifactStoreError('artifact index reference count exceeds size policy')
    normalized_refs = [validate_artifact_reference(item) for item in artifacts]
    reference_ids = [str(item['reference_id']) for item in normalized_refs]
    if reference_ids != sorted(reference_ids) or len(reference_ids) != len(set(reference_ids)):
        raise ProtocolV3ArtifactStoreError('artifact references must be uniquely sorted by reference_id')
    expected_provenance = {'parent_report_id': parent['report_id'], 'parent_report_sha256': parent['report_sha256'], 'run_fingerprint': root['run_fingerprint'], 'pipeline_generation': root['pipeline_generation'], 'work_unit_id': work['work_unit_id'], 'work_unit_sha256': work['work_unit_sha256']}
    if any((ref['provenance'] != expected_provenance for ref in normalized_refs)):
        raise ProtocolV3ArtifactStoreError('artifact reference provenance does not match index provenance')
    root['artifacts'] = normalized_refs
    observed_sha = _sha256(root.get('index_sha256'), 'artifact_index.index_sha256')
    observed_id = root.get('index_id')
    if not isinstance(observed_id, str) or not _INDEX_ID_RE.fullmatch(observed_id):
        raise ProtocolV3ArtifactStoreError('artifact_index.index_id is invalid')
    basis = dict(root)
    basis.pop('index_id')
    basis.pop('index_sha256')
    expected_sha = hashlib.sha256(_serialized_bytes(_canonical_json(basis))).hexdigest()
    if observed_sha != expected_sha or observed_id != f'protocol_v3_artifact_index_sha256:{expected_sha}':
        raise ProtocolV3ArtifactStoreError('artifact index digest or id mismatch')
    _reject_raw_candle_payloads(root, 'artifact_index')
    _assert_finite_json(root, 'artifact_index')
    canonical = _canonical_json(root)
    raw = _serialized_bytes(canonical)
    if len(raw) > MAX_INDEX_BYTES:
        raise ProtocolV3ArtifactStoreError('artifact index exceeds compact size policy')
    return CompactArtifactIndex(canonical, expected_sha)

def _build_index_payload(*, parent_report: Mapping[str, Any], run_fingerprint: str, pipeline_generation: str, work_unit: Mapping[str, Any], references: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    basis = {'schema_version': ARTIFACT_INDEX_SCHEMA_VERSION, 'protocol_version': PROTOCOL_VERSION, 'contract_version': ARTIFACT_STORE_CONTRACT_VERSION, 'parent_report': dict(parent_report), 'run_fingerprint': run_fingerprint, 'pipeline_generation': pipeline_generation, 'work_unit': dict(work_unit), 'artifacts': [dict(item) for item in references]}
    digest = hashlib.sha256(_serialized_bytes(_canonical_json(basis))).hexdigest()
    return {**basis, 'index_id': f'protocol_v3_artifact_index_sha256:{digest}', 'index_sha256': digest}

def _persist_or_validate_object(*, payload: ArtifactPayload, reference_id: str, provenance: Mapping[str, Any], repository_root: Path) -> dict[str, Any]:
    validated = validate_artifact_payload(payload)
    object_root = _safe_storage_root(repository_root, OBJECT_ROOT, create=True)
    relative = _object_relative_path(validated.artifact_kind, validated.sha256)
    path = object_root.joinpath(*relative.parts)
    _ensure_safe_directory(repository_root, path.parent)
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise ProtocolV3ArtifactStoreError('existing artifact object path is unsafe')
        existing = _read_artifact_object(path, {'artifact_kind': validated.artifact_kind, 'artifact_schema': validated.artifact_schema, 'sha256': validated.sha256, 'byte_size': validated.byte_size, 'logical_cardinality': validated.logical_cardinality})
        if existing.canonical_bytes != validated.canonical_bytes:
            raise ProtocolV3ArtifactStoreError('existing content-addressed object bytes differ; refusing overwrite')
    else:
        _write_create_only(path, validated.canonical_bytes)
        reloaded = _read_artifact_object(path, {'artifact_kind': validated.artifact_kind, 'artifact_schema': validated.artifact_schema, 'sha256': validated.sha256, 'byte_size': validated.byte_size, 'logical_cardinality': validated.logical_cardinality})
        if reloaded != validated:
            raise ProtocolV3ArtifactStoreError('artifact object reload mismatch')
    return validate_artifact_reference({'schema_version': ARTIFACT_REFERENCE_SCHEMA_VERSION, 'reference_id': reference_id, 'artifact_kind': validated.artifact_kind, 'artifact_schema': validated.artifact_schema, 'sha256': validated.sha256, 'byte_size': validated.byte_size, 'logical_cardinality': validated.logical_cardinality, 'relative_path': relative.as_posix(), 'provenance': dict(provenance)})

def _read_artifact_object(path: Path, reference: Mapping[str, Any]) -> ArtifactPayload:
    if path.is_symlink():
        raise ProtocolV3ArtifactStoreError('artifact object must not be a symlink')
    try:
        raw = path.read_bytes()
        value = _strict_json_loads(raw.decode('utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolV3ArtifactStoreError('artifact object is unreadable or invalid') from exc
    artifact = validate_artifact_payload(value)
    observed_sha = hashlib.sha256(raw).hexdigest()
    if raw != artifact.canonical_bytes:
        raise ProtocolV3ArtifactStoreError('artifact object bytes are not canonical')
    if observed_sha != reference['sha256'] or artifact.sha256 != reference['sha256']:
        raise ProtocolV3ArtifactStoreError('artifact object digest mismatch')
    if len(raw) != reference['byte_size']:
        raise ProtocolV3ArtifactStoreError('artifact object byte size mismatch')
    if artifact.logical_cardinality != reference['logical_cardinality']:
        raise ProtocolV3ArtifactStoreError('artifact object cardinality mismatch')
    if artifact.artifact_kind != reference['artifact_kind']:
        raise ProtocolV3ArtifactStoreError('artifact object kind mismatch')
    if artifact.artifact_schema != reference['artifact_schema']:
        raise ProtocolV3ArtifactStoreError('artifact object schema mismatch')
    return artifact

def _object_path_from_reference(reference: Mapping[str, Any], repo: Path) -> Path:
    root = _safe_storage_root(repo, OBJECT_ROOT, create=False)
    relative = _safe_relative_path(reference['relative_path'], 'artifact_reference.relative_path')
    path = root.joinpath(*relative.parts)
    expected = root.joinpath(*_object_relative_path(str(reference['artifact_kind']), str(reference['sha256'])).parts)
    if path != expected:
        raise ProtocolV3ArtifactStoreError('artifact object path is not canonical')
    _require_exact_path(path, expected, root)
    return path

def _validate_trade_records(records: list[Any]) -> None:
    seen: set[str] = set()
    order: list[tuple[str, str]] = []
    for index, raw in enumerate(records):
        path = f'trades.records[{index}]'
        row = dict(_mapping(raw, path))
        _exact_keys(row, {'trade_id', 'entry_time_utc', 'exit_time_utc', 'net_usdc', 'data'}, path)
        trade_id = _safe_identifier(row.get('trade_id'), f'{path}.trade_id')
        if trade_id in seen:
            raise ProtocolV3ArtifactStoreError('trade_id values must be unique')
        seen.add(trade_id)
        entry = _utc_datetime(row.get('entry_time_utc'), f'{path}.entry_time_utc')
        exit_time = _utc_datetime(row.get('exit_time_utc'), f'{path}.exit_time_utc')
        if exit_time < entry:
            raise ProtocolV3ArtifactStoreError('trade exit cannot precede entry')
        _finite_number(row.get('net_usdc'), f'{path}.net_usdc')
        data = dict(_mapping(row.get('data'), f'{path}.data'))
        _reject_raw_candle_payloads(data, f'{path}.data')
        _assert_finite_json(data, f'{path}.data')
        order.append((_format_utc(entry), trade_id))
    if order != sorted(order):
        raise ProtocolV3ArtifactStoreError('trade records must be canonically ordered')

def _validate_daily_mtm_records(records: list[Any], coverage_value: Any) -> None:
    coverage = dict(_mapping(coverage_value, 'daily_mtm.coverage'))
    _exact_keys(coverage, _DAILY_COVERAGE_KEYS, 'daily_mtm.coverage')
    start = _utc_datetime(coverage.get('start_inclusive_utc'), 'daily_mtm.coverage.start')
    end = _utc_datetime(coverage.get('end_exclusive_utc'), 'daily_mtm.coverage.end')
    _require_midnight(start, 'daily_mtm.coverage.start')
    _require_midnight(end, 'daily_mtm.coverage.end')
    if end <= start:
        raise ProtocolV3ArtifactStoreError('daily_mtm coverage end must follow start')
    expected_days = (end.date() - start.date()).days
    if type(coverage.get('calendar_days')) is not int or coverage['calendar_days'] != expected_days:
        raise ProtocolV3ArtifactStoreError('daily_mtm coverage calendar_days is inconsistent')
    expected_grid = [(start.date() + timedelta(days=i)).isoformat() for i in range(expected_days)]
    observed: list[str] = []
    for index, raw in enumerate(records):
        path = f'daily_mtm.records[{index}]'
        row = dict(_mapping(raw, path))
        _exact_keys(row, {'day_utc', 'net_mtm_usdc'}, path)
        day = _utc_date(row.get('day_utc'), f'{path}.day_utc')
        observed.append(day.isoformat())
        _finite_number(row.get('net_mtm_usdc'), f'{path}.net_mtm_usdc')
    if observed != expected_grid:
        raise ProtocolV3ArtifactStoreError('daily_mtm records must contain every covered UTC day exactly once; zero is distinct from missing')

def _validate_equity_records(records: list[Any]) -> None:
    observed: list[str] = []
    for index, raw in enumerate(records):
        path = f'equity_underwater.records[{index}]'
        row = dict(_mapping(raw, path))
        _exact_keys(row, {'timestamp_utc', 'equity_usdc', 'underwater_usdc'}, path)
        timestamp = _utc_datetime(row.get('timestamp_utc'), f'{path}.timestamp_utc')
        observed.append(_format_utc(timestamp))
        _finite_number(row.get('equity_usdc'), f'{path}.equity_usdc')
        underwater = _finite_number(row.get('underwater_usdc'), f'{path}.underwater_usdc')
        if underwater > 0:
            raise ProtocolV3ArtifactStoreError('underwater_usdc must be <= 0')
    if observed != sorted(observed) or len(observed) != len(set(observed)):
        raise ProtocolV3ArtifactStoreError('equity_underwater timestamps must be uniquely ordered')

def _validate_diagnostic_records(records: list[Any]) -> None:
    observed: list[str] = []
    for index, raw in enumerate(records):
        path = f'diagnostics.records[{index}]'
        row = dict(_mapping(raw, path))
        _exact_keys(row, {'record_id', 'category', 'data'}, path)
        record_id = _safe_identifier(row.get('record_id'), f'{path}.record_id')
        category = row.get('category')
        if not isinstance(category, str) or not category.strip():
            raise ProtocolV3ArtifactStoreError(f'{path}.category must be non-empty')
        data = dict(_mapping(row.get('data'), f'{path}.data'))
        _reject_raw_candle_payloads(data, f'{path}.data')
        _assert_finite_json(data, f'{path}.data')
        observed.append(record_id)
    if observed != sorted(observed) or len(observed) != len(set(observed)):
        raise ProtocolV3ArtifactStoreError('diagnostic records must be uniquely sorted by record_id')

def _object_relative_path(artifact_kind: str, digest: str) -> PurePosixPath:
    if artifact_kind not in ARTIFACT_KINDS:
        raise ProtocolV3ArtifactStoreError('invalid object artifact kind')
    _sha256(digest, 'object digest')
    return PurePosixPath(artifact_kind, digest[:2], f'{digest}.json')

def _repository_root(repository_root: str | Path) -> Path:
    root = Path(repository_root)
    if not root.exists() or not root.is_dir() or root.is_symlink():
        raise ProtocolV3ArtifactStoreError('repository_root must be an existing real directory')
    return root.resolve()

def _safe_storage_root(repo: Path, relative_root: str, *, create: bool) -> Path:
    relative = _safe_relative_path(relative_root, 'storage root')
    target = repo.joinpath(*relative.parts)
    _reject_symlink_components(repo, target)
    if create:
        target.mkdir(parents=True, exist_ok=True)
    if not target.exists() or not target.is_dir() or target.is_symlink():
        raise ProtocolV3ArtifactStoreError(f'storage root is missing or unsafe: {relative_root}')
    resolved = target.resolve()
    if not is_path_within(resolved, repo):
        raise ProtocolV3ArtifactStoreError('storage root escapes repository_root')
    _reject_symlink_components(repo, resolved)
    return resolved

def _ensure_safe_directory(repo: Path, directory: Path) -> None:
    _reject_symlink_components(repo, directory)
    directory.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(repo, directory)
    if directory.is_symlink() or not is_path_within(directory.resolve(), repo):
        raise ProtocolV3ArtifactStoreError('artifact directory is unsafe')

def _require_exact_path(path: Path, expected: Path, root: Path) -> None:
    if path.is_symlink():
        raise ProtocolV3ArtifactStoreError('artifact path must not be a symlink')
    try:
        resolved = path.resolve(strict=True)
        expected_resolved = expected.resolve(strict=True)
    except OSError as exc:
        raise ProtocolV3ArtifactStoreError('artifact path is missing or unreadable') from exc
    if resolved != expected_resolved or not is_path_within(resolved, root):
        raise ProtocolV3ArtifactStoreError('artifact path is outside its canonical root')

def _reject_symlink_components(repo: Path, target: Path) -> None:
    try:
        relative = target.relative_to(repo)
    except ValueError as exc:
        raise ProtocolV3ArtifactStoreError('artifact target escapes repository root') from exc
    current = repo
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ProtocolV3ArtifactStoreError('symlinked artifact paths are forbidden')

def _write_create_only(path: Path, data: bytes) -> None:
    if path.parent.is_symlink():
        raise ProtocolV3ArtifactStoreError('unsafe artifact parent path')
    try:
        with path.open('xb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise
    except OSError as exc:
        raise ProtocolV3ArtifactStoreError(f'could not persist artifact: {path}') from exc

def _read_strict_canonical_json(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = _strict_json_loads(raw.decode('utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolV3ArtifactStoreError(f'strict artifact JSON is invalid: {path}') from exc
    if not isinstance(value, dict):
        raise ProtocolV3ArtifactStoreError('artifact JSON must contain one object')
    return (value, raw)

def _strict_json_loads(text: str) -> Any:

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise ProtocolV3ArtifactStoreError(f'duplicate JSON key is forbidden: {key}')
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ProtocolV3ArtifactStoreError(f'non-finite JSON constant is forbidden: {value}')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)

def _safe_relative_path(value: Any, path: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or '\\' in value:
        raise ProtocolV3ArtifactStoreError(f'{path} must be a POSIX relative path')
    relative = PurePosixPath(value)
    if relative.is_absolute() or '..' in relative.parts or '.' in relative.parts:
        raise ProtocolV3ArtifactStoreError(f'{path} must stay inside its root')
    return relative

def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolV3ArtifactStoreError(f'{path} must be an object')
    return value

def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        raise ProtocolV3ArtifactStoreError(f'{path} keys are invalid; missing={sorted(missing)} extra={sorted(extra)}')

def _literal(value: Mapping[str, Any], key: str, expected: Any, path: str) -> None:
    observed = value.get(key)
    if observed != expected or type(observed) is not type(expected):
        raise ProtocolV3ArtifactStoreError(f'{path}.{key} must be {expected!r}')

def _safe_identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SAFE_ID_RE.fullmatch(value):
        raise ProtocolV3ArtifactStoreError(f'{path} is not a safe identifier')
    return value

def _sha256(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise ProtocolV3ArtifactStoreError(f'{path} must be a lowercase SHA-256 digest')
    return value

def _run_fingerprint(value: Any) -> str:
    if not isinstance(value, str) or not _RUN_RE.fullmatch(value):
        raise ProtocolV3ArtifactStoreError('run_fingerprint is invalid')
    return value

def _pipeline_generation(value: Any) -> str:
    if not isinstance(value, str) or not _PIPELINE_RE.fullmatch(value):
        raise ProtocolV3ArtifactStoreError('pipeline_generation is invalid')
    return value

def _utc_datetime(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not value.endswith('Z'):
        raise ProtocolV3ArtifactStoreError(f'{path} must be UTC and end in Z')
    try:
        parsed = datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError as exc:
        raise ProtocolV3ArtifactStoreError(f'{path} is invalid') from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ProtocolV3ArtifactStoreError(f'{path} must be UTC')
    return parsed

def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec='microseconds').replace('+00:00', 'Z')

def _utc_date(value: Any, path: str) -> date:
    if not isinstance(value, str):
        raise ProtocolV3ArtifactStoreError(f'{path} must be YYYY-MM-DD')
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ProtocolV3ArtifactStoreError(f'{path} must be YYYY-MM-DD') from exc
    if parsed.isoformat() != value:
        raise ProtocolV3ArtifactStoreError(f'{path} must be canonical YYYY-MM-DD')
    return parsed

def _require_midnight(value: datetime, path: str) -> None:
    if value.hour or value.minute or value.second or value.microsecond:
        raise ProtocolV3ArtifactStoreError(f'{path} must be UTC midnight')

def _finite_number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProtocolV3ArtifactStoreError(f'{path} must be a finite number')
    result = float(value)
    if not math.isfinite(result):
        raise ProtocolV3ArtifactStoreError(f'{path} must be finite')
    return result

def _reject_raw_candle_payloads(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_RAW_KEYS:
                raise ProtocolV3ArtifactStoreError(f'{path} embeds forbidden raw candle or market-bar data')
            _reject_raw_candle_payloads(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_raw_candle_payloads(item, f'{path}[{index}]')

def _assert_finite_json(value: Any, path: str) -> None:
    if isinstance(value, float) and (not math.isfinite(value)):
        raise ProtocolV3ArtifactStoreError(f'{path} contains a non-finite number')
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolV3ArtifactStoreError(f'{path} contains a non-string key')
            _assert_finite_json(item, f'{path}.{key}')
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_finite_json(item, f'{path}[{index}]')
    elif value is not None and (not isinstance(value, (str, int, float, bool))):
        raise ProtocolV3ArtifactStoreError(f'{path} is not strict JSON')

def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProtocolV3ArtifactStoreError(f'value is not canonical strict JSON: {exc}') from exc

def _serialized_bytes(canonical_json: str) -> bytes:
    return (canonical_json + '\n').encode('utf-8')

def _normalize_json(value: Any) -> Any:
    return json.loads(_canonical_json(value))
__all__ = ['ARTIFACT_INDEX_SCHEMA_VERSION', 'ARTIFACT_KINDS', 'ARTIFACT_OBJECT_SCHEMA_VERSION', 'ARTIFACT_REFERENCE_SCHEMA_VERSION', 'ARTIFACT_SCHEMAS', 'ARTIFACT_STORE_CONTRACT_PATH', 'ARTIFACT_STORE_CONTRACT_SCHEMA', 'ARTIFACT_STORE_CONTRACT_VERSION', 'DAILY_MTM', 'DIAGNOSTICS', 'EQUITY_UNDERWATER', 'INDEX_ROOT', 'INDEX_SIZE_POLICY_VERSION', 'MAX_INDEX_BYTES', 'MAX_REFERENCES', 'MAX_WORK_UNIT_IDENTITY_BYTES', 'OBJECT_ROOT', 'REPRESENTATIVE_REFERENCES', 'TRADES', 'ArtifactPayload', 'CompactArtifactBundle', 'CompactArtifactIndex', 'ProtocolV3ArtifactStoreError', 'build_artifact_payload', 'load_artifact_store_contract', 'persist_compact_artifact_bundle', 'read_compact_artifact_bundle', 'validate_artifact_index', 'validate_artifact_payload', 'validate_artifact_reference', 'validate_artifact_store_contract']