"""Strict Protocol v3 Task-11 report schemas and evidence semantics."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib, json, math, os, re
from pathlib import Path, PurePosixPath
from typing import Any, Final

from ethusdc_bot.path_safety import is_path_within

REPORT_CONTRACT_PATH: Final = Path("configs/protocol_v3_report_contract.json")
REPORT_CONTRACT_SCHEMA: Final = "protocol_v3_report_contract_v1"
REPORT_CONTRACT_VERSION: Final = "protocol_v3_evidence_reports_v1"
REPORT_SCHEMA_VERSION: Final = "protocol_v3_report_v1"
WINDOW_REGISTRATION_SCHEMA_VERSION: Final = "protocol_v3_evidence_window_registration_v1"
PROTOCOL_VERSION: Final = "3.0.0"
TARGET_USDC_PER_CALENDAR_DAY: Final = 3.0
PROCESS_OOS_CALENDAR_DAYS: Final = 365
PROTOCOL_V3_RESEARCH: Final = "protocol_v3_research"
MONTHLY_PROCESS_OOS: Final = "monthly_process_oos"
RESEARCH_CHALLENGER_SHADOW: Final = "research_challenger_shadow"
FORWARD_SHADOW_MONTH: Final = "forward_shadow_month"
PROTOCOL_V3_PIPELINE_FINAL: Final = "protocol_v3_pipeline_final"
REPORT_KINDS: Final = (PROTOCOL_V3_RESEARCH, MONTHLY_PROCESS_OOS, RESEARCH_CHALLENGER_SHADOW, FORWARD_SHADOW_MONTH, PROTOCOL_V3_PIPELINE_FINAL)
REPORT_STORAGE_ROOTS: Final = {
    PROTOCOL_V3_RESEARCH: "reports/protocol_v3/research",
    MONTHLY_PROCESS_OOS: "reports/protocol_v3/monthly_process_oos",
    RESEARCH_CHALLENGER_SHADOW: "reports/protocol_v3/research_challenger_shadow",
    FORWARD_SHADOW_MONTH: "reports/protocol_v3/forward_shadow_month",
    PROTOCOL_V3_PIPELINE_FINAL: "reports/protocol_v3/pipeline_final",
}
FORWARD_REGISTRATION_ROOT: Final = "reports/protocol_v3/evidence_windows/forward_shadow_month"

_HEX = re.compile(r"^[0-9a-f]{64}$")
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PIPE = re.compile(r"^protocol_v3_pipeline_sha256:[0-9a-f]{64}$")
_RUN = re.compile(r"^protocol_v3_run_sha256:[0-9a-f]{64}$")
_CLOCK_TOLERANCE = timedelta(minutes=5)
_SAFETY = {"public_data_only": True, "orders_enabled": False, "trading_api_enabled": False, "api_keys_used": False, "live": "locked", "paper": "locked", "testtrade": "locked", "short_margin_futures_leverage": "forbidden", "canonical_adoption_enabled": False}
_WINDOWS = {PROTOCOL_V3_RESEARCH: "historical_research", MONTHLY_PROCESS_OOS: "monthly_process_oos", RESEARCH_CHALLENGER_SHADOW: "retrospective_research_challenger", FORWARD_SHADOW_MONTH: "forward_shadow_month", PROTOCOL_V3_PIPELINE_FINAL: "sealed_final_holdout"}
_FRESHNESS = {PROTOCOL_V3_RESEARCH: "NOT_FRESH", MONTHLY_PROCESS_OOS: "NOT_FRESH", RESEARCH_CHALLENGER_SHADOW: "NOT_FRESH", FORWARD_SHADOW_MONTH: "FRESH_FORWARD_OBSERVATION", PROTOCOL_V3_PIPELINE_FINAL: "PENDING_TASK_31"}
_STATUSES = {PROTOCOL_V3_RESEARCH: {"completed_diagnostic", "blocked"}, MONTHLY_PROCESS_OOS: {"completed_diagnostic", "blocked"}, RESEARCH_CHALLENGER_SHADOW: {"completed_diagnostic", "blocked"}, FORWARD_SHADOW_MONTH: {"completed_forward_observation", "blocked"}, PROTOCOL_V3_PIPELINE_FINAL: {"schema_reserved_task_31"}}
_REPORT_KEYS = {"schema_version", "protocol_version", "artifact_kind", "report_id", "created_at_utc", "run_fingerprint", "pipeline_generation", "evidence_window", "metrics", "evidence_inputs", "evidence_status", "details", "safety"}
_WINDOW_KEYS = {"window_id", "window_class", "start_inclusive_utc", "end_exclusive_utc", "calendar_days", "registration_id", "registration_sha256"}
_METRIC_KEYS = {"process_oos_net_usdc", "process_oos_calendar_days", "target_usdc_per_calendar_day"}
_INPUT_KEYS = {"historical_bootstrap_attestation_sha256", "sealed_bootstrap_attestation_sha256", "task31_final_attestation_sha256"}
_STATUS_KEYS = {"historically_hit", "historical_bootstrap_lower_bound", "freshness", "fresh_pre_registered_sealed_365", "sealed_bootstrap_target_supported", "statistically_supported", "canonical_adoption_eligible", "diagnostic_only"}
_DETAIL_KEYS = {"producer", "producer_status", "source_artifact_ids", "reason_codes"}
_REG_KEYS = {"schema_version", "protocol_version", "registration_id", "window_class", "registered_at_utc", "start_inclusive_utc", "end_exclusive_utc", "calendar_days", "pipeline_generation", "run_fingerprint", "registration_sha256"}

_CANONICAL_CONTRACT: dict[str, Any] = {
    "schema_version": REPORT_CONTRACT_SCHEMA, "protocol_version": PROTOCOL_VERSION,
    "contract_version": REPORT_CONTRACT_VERSION, "report_schema_version": REPORT_SCHEMA_VERSION,
    "window_registration_schema_version": WINDOW_REGISTRATION_SCHEMA_VERSION,
    "artifact_kinds": {kind: {"storage_root": REPORT_STORAGE_ROOTS[kind], "window_class": _WINDOWS[kind], "freshness": _FRESHNESS[kind], "canonical_adoption_eligible": False} for kind in REPORT_KINDS},
    "forward_registration_root": FORWARD_REGISTRATION_ROOT, "evidence_fields": sorted(_STATUS_KEYS),
    "target_policy": {"target_usdc_per_calendar_day": 3.0, "process_oos_calendar_days": 365, "historically_hit_formula": "process_oos_net_usdc/process_oos_calendar_days>=target_usdc_per_calendar_day", "historically_hit_never_implies_statistical_support": True},
    "final_evidence_policy": {"sealed_final_holdout_is_window_class_not_report_kind": True, "pipeline_final_artifact_kind": PROTOCOL_V3_PIPELINE_FINAL, "legacy_final_report_type_forbidden": "final_evaluation", "task31_attestation_required": True, "task31_attestation_available": False, "generic_task11_builder_remains_reserved": True, "dedicated_task31_opener_required": True, "dedicated_task31_reader_required": True, "visible_forward_month_overlap_forbidden": True},
    "strict_json": {"exact_keys": True, "duplicate_keys_forbidden": True, "unknown_security_fields_forbidden": True, "nan_forbidden": True, "infinity_forbidden": True, "canonical_serialization_required": True},
    "safety": {"api_keys": "forbidden", "live": "locked", "orders": "locked", "paper": "locked", "testtrade": "locked", "trading_api": "forbidden"},
}

class ProtocolV3ReportError(ValueError): pass

@dataclass(frozen=True)
class ProtocolV3WindowRegistration:
    canonical_json: str
    registration_sha256: str
    def to_dict(self) -> dict[str, Any]: return json.loads(self.canonical_json)

@dataclass(frozen=True)
class ProtocolV3Report:
    canonical_json: str
    report_sha256: str
    def to_dict(self) -> dict[str, Any]: return json.loads(self.canonical_json)
    @property
    def artifact_kind(self) -> str: return str(self.to_dict()["artifact_kind"])
    @property
    def report_id(self) -> str: return str(self.to_dict()["report_id"])

def load_report_contract(repo_root: str | Path | None = None, *, contract_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else Path(__file__).resolve().parents[3]
    path = Path(contract_path) if contract_path is not None else root / REPORT_CONTRACT_PATH
    if not path.is_absolute(): path = root / path
    try: value = _strict_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ProtocolV3ReportError(f"Protocol v3 report contract is missing or invalid: {path}") from exc
    validate_report_contract(value); return value

def validate_report_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize(value) != _CANONICAL_CONTRACT: raise ProtocolV3ReportError("Protocol v3 report contract is not canonical")

def build_forward_window_registration(*, registration_id: str, registered_at_utc: str, start_inclusive_utc: str, end_exclusive_utc: str, pipeline_generation: str, run_fingerprint: str) -> ProtocolV3WindowRegistration:
    _identifier(registration_id, "registration_id"); registered = _utc(registered_at_utc, "registered_at_utc"); start = _utc(start_inclusive_utc, "start_inclusive_utc"); end = _utc(end_exclusive_utc, "end_exclusive_utc")
    days = _days(start, end, "forward window"); _calendar_month(start, end)
    if registered >= start: raise ProtocolV3ReportError("forward window must be registered before its start")
    _pipeline(pipeline_generation); _fingerprint(run_fingerprint)
    basis = {"schema_version": WINDOW_REGISTRATION_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION, "registration_id": registration_id, "window_class": FORWARD_SHADOW_MONTH, "registered_at_utc": _fmt(registered), "start_inclusive_utc": _fmt(start), "end_exclusive_utc": _fmt(end), "calendar_days": days, "pipeline_generation": pipeline_generation, "run_fingerprint": run_fingerprint}
    return validate_window_registration({**basis, "registration_sha256": _sha(basis)})

def validate_window_registration(value: ProtocolV3WindowRegistration | Mapping[str, Any]) -> ProtocolV3WindowRegistration:
    root = value.to_dict() if isinstance(value, ProtocolV3WindowRegistration) else dict(_object(value, "window_registration")); _keys(root, _REG_KEYS, "window_registration")
    _lit(root, "schema_version", WINDOW_REGISTRATION_SCHEMA_VERSION, "window_registration"); _lit(root, "protocol_version", PROTOCOL_VERSION, "window_registration"); _identifier(root.get("registration_id"), "window_registration.registration_id"); _lit(root, "window_class", FORWARD_SHADOW_MONTH, "window_registration")
    registered = _utc(root.get("registered_at_utc"), "window_registration.registered_at_utc"); start = _utc(root.get("start_inclusive_utc"), "window_registration.start_inclusive_utc"); end = _utc(root.get("end_exclusive_utc"), "window_registration.end_exclusive_utc"); days = _days(start, end, "window_registration"); _calendar_month(start, end)
    if registered >= start: raise ProtocolV3ReportError("window_registration must precede the window start")
    if type(root.get("calendar_days")) is not int or root["calendar_days"] != days: raise ProtocolV3ReportError("window_registration.calendar_days is inconsistent")
    _pipeline(root.get("pipeline_generation")); _fingerprint(root.get("run_fingerprint")); observed = root.get("registration_sha256")
    if not isinstance(observed, str) or not _HEX.fullmatch(observed): raise ProtocolV3ReportError("window_registration.registration_sha256 is invalid")
    basis = dict(root); basis.pop("registration_sha256")
    if observed != _sha(basis): raise ProtocolV3ReportError("window_registration digest mismatch")
    return ProtocolV3WindowRegistration(_json(root), observed)

def build_protocol_v3_report(*, artifact_kind: str, report_id: str, created_at_utc: str, run_fingerprint: str, pipeline_generation: str, window_id: str, start_inclusive_utc: str | None, end_exclusive_utc: str | None, process_oos_net_usdc: float | int | None, producer: str, producer_status: str, source_artifact_ids: Sequence[str] = (), reason_codes: Sequence[str] = (), forward_registration: ProtocolV3WindowRegistration | None = None) -> ProtocolV3Report:
    if artifact_kind not in REPORT_KINDS: raise ProtocolV3ReportError(f"unsupported Protocol v3 artifact_kind: {artifact_kind!r}")
    _identifier(report_id, "report_id"); _identifier(window_id, "window_id"); created = _utc(created_at_utc, "created_at_utc"); _fingerprint(run_fingerprint); _pipeline(pipeline_generation); producer = _text(producer, "producer")
    if producer_status not in _STATUSES[artifact_kind]: raise ProtocolV3ReportError(f"producer_status is invalid for {artifact_kind}: {producer_status!r}")
    window = _build_window(artifact_kind, window_id, start_inclusive_utc, end_exclusive_utc, pipeline_generation, run_fingerprint, forward_registration)
    metrics = _metrics(artifact_kind, process_oos_net_usdc)
    payload = {"schema_version": REPORT_SCHEMA_VERSION, "protocol_version": PROTOCOL_VERSION, "artifact_kind": artifact_kind, "report_id": report_id, "created_at_utc": _fmt(created), "run_fingerprint": run_fingerprint, "pipeline_generation": pipeline_generation, "evidence_window": window, "metrics": metrics, "evidence_inputs": {key: None for key in sorted(_INPUT_KEYS)}, "evidence_status": _status(artifact_kind, metrics), "details": {"producer": producer, "producer_status": producer_status, "source_artifact_ids": _strings(source_artifact_ids, "source_artifact_ids"), "reason_codes": _strings(reason_codes, "reason_codes")}, "safety": dict(_SAFETY)}
    return validate_protocol_v3_report(payload)

def validate_protocol_v3_report(value: ProtocolV3Report | Mapping[str, Any]) -> ProtocolV3Report:
    root = value.to_dict() if isinstance(value, ProtocolV3Report) else dict(_object(value, "protocol_v3_report")); _keys(root, _REPORT_KEYS, "protocol_v3_report"); _lit(root, "schema_version", REPORT_SCHEMA_VERSION, "protocol_v3_report"); _lit(root, "protocol_version", PROTOCOL_VERSION, "protocol_v3_report")
    kind = root.get("artifact_kind")
    if kind not in REPORT_KINDS: raise ProtocolV3ReportError("protocol_v3_report.artifact_kind is invalid")
    _identifier(root.get("report_id"), "protocol_v3_report.report_id"); created = _utc(root.get("created_at_utc"), "protocol_v3_report.created_at_utc"); _fingerprint(root.get("run_fingerprint")); _pipeline(root.get("pipeline_generation"))
    window = dict(_object(root.get("evidence_window"), "protocol_v3_report.evidence_window")); _validate_window(str(kind), window, created)
    metrics = dict(_object(root.get("metrics"), "protocol_v3_report.metrics")); _validate_metrics(str(kind), metrics)
    inputs = dict(_object(root.get("evidence_inputs"), "protocol_v3_report.evidence_inputs")); _keys(inputs, _INPUT_KEYS, "protocol_v3_report.evidence_inputs")
    if any(item is not None for item in inputs.values()): raise ProtocolV3ReportError("Task-11 reports cannot claim Task-27 or Task-31 attestations")
    evidence = dict(_object(root.get("evidence_status"), "protocol_v3_report.evidence_status")); _keys(evidence, _STATUS_KEYS, "protocol_v3_report.evidence_status")
    if _normalize(evidence) != _status(str(kind), metrics): raise ProtocolV3ReportError("protocol_v3_report.evidence_status does not match derived evidence semantics")
    details = dict(_object(root.get("details"), "protocol_v3_report.details")); _keys(details, _DETAIL_KEYS, "protocol_v3_report.details"); _text(details.get("producer"), "protocol_v3_report.details.producer")
    if details.get("producer_status") not in _STATUSES[str(kind)]: raise ProtocolV3ReportError("protocol_v3_report.details.producer_status is invalid")
    if details.get("source_artifact_ids") != _strings(details.get("source_artifact_ids"), "source_artifact_ids") or details.get("reason_codes") != _strings(details.get("reason_codes"), "reason_codes"): raise ProtocolV3ReportError("details string lists must be sorted and unique")
    if _normalize(root.get("safety")) != _SAFETY: raise ProtocolV3ReportError("protocol_v3_report.safety is not canonical")
    _finite_json(root, "protocol_v3_report"); canonical = _json(root); return ProtocolV3Report(canonical, hashlib.sha256(canonical.encode()).hexdigest())

def write_forward_window_registration(registration: ProtocolV3WindowRegistration, repository_root: str | Path) -> Path:
    validated = validate_window_registration(registration); payload = validated.to_dict(); now = _utc_now(); registered = _utc(payload["registered_at_utc"], "registered_at_utc"); start = _utc(payload["start_inclusive_utc"], "start_inclusive_utc")
    if now >= start: raise ProtocolV3ReportError("forward registration must be persisted before the window starts")
    if abs(now - registered) > _CLOCK_TOLERANCE: raise ProtocolV3ReportError("forward registration timestamp is not current")
    root = _root(repository_root, FORWARD_REGISTRATION_ROOT, True); path = root / f"{payload['registration_id']}.json"; _write(path, validated.canonical_json); reloaded = read_forward_window_registration(path, repository_root)
    if reloaded != validated: raise ProtocolV3ReportError("forward registration reload mismatch")
    return path

def read_forward_window_registration(path: str | Path, repository_root: str | Path) -> ProtocolV3WindowRegistration:
    guarded = _guard_read_path(Path(path), repository_root, (FORWARD_REGISTRATION_ROOT,))
    value, raw = _read(guarded); registration = validate_window_registration(value); root = _root(repository_root, FORWARD_REGISTRATION_ROOT, False); expected = root / f"{registration.to_dict()['registration_id']}.json"; _exact_path(guarded, expected, root)
    if raw != _bytes(registration.canonical_json): raise ProtocolV3ReportError("forward registration bytes are not canonical")
    return registration

def write_protocol_v3_report(report: ProtocolV3Report, repository_root: str | Path) -> Path:
    if not isinstance(report, ProtocolV3Report): raise ProtocolV3ReportError("write_protocol_v3_report requires a validated ProtocolV3Report")
    validated = validate_protocol_v3_report(report); payload = validated.to_dict(); now = _utc_now(); created = _utc(payload["created_at_utc"], "created_at_utc")
    if abs(now - created) > _CLOCK_TOLERANCE: raise ProtocolV3ReportError("Protocol v3 report timestamp is not current")
    kind = str(payload["artifact_kind"])
    if kind == FORWARD_SHADOW_MONTH:
        end = _utc(payload["evidence_window"]["end_exclusive_utc"], "evidence_window.end")
        if now < end: raise ProtocolV3ReportError("forward_shadow_month cannot be persisted before the month is complete")
        reg_path = _root(repository_root, FORWARD_REGISTRATION_ROOT, False) / f"{payload['evidence_window']['registration_id']}.json"; reg = read_forward_window_registration(reg_path, repository_root); rp = reg.to_dict()
        if reg.registration_sha256 != payload["evidence_window"]["registration_sha256"] or rp["pipeline_generation"] != payload["pipeline_generation"] or rp["run_fingerprint"] != payload["run_fingerprint"]: raise ProtocolV3ReportError("forward report registration identity mismatch")
    root = _root(repository_root, REPORT_STORAGE_ROOTS[kind], True); path = root / f"{validated.report_id}.json"; _write(path, validated.canonical_json); reloaded = read_protocol_v3_report(path, repository_root)
    if reloaded != validated: raise ProtocolV3ReportError("Protocol v3 report reload mismatch")
    return path

def read_protocol_v3_report(path: str | Path, repository_root: str | Path) -> ProtocolV3Report:
    guarded = _guard_read_path(Path(path), repository_root, tuple(REPORT_STORAGE_ROOTS.values()))
    value, raw = _read(guarded); report = validate_protocol_v3_report(value); payload = report.to_dict(); root = _root(repository_root, REPORT_STORAGE_ROOTS[str(payload["artifact_kind"])], False); expected = root / f"{payload['report_id']}.json"; _exact_path(guarded, expected, root)
    if raw != _bytes(report.canonical_json): raise ProtocolV3ReportError("Protocol v3 report bytes are not canonical")
    return report

def assert_sealed_final_window_excludes_visible_forward_months(*, start_inclusive_utc: str, end_exclusive_utc: str, repository_root: str | Path) -> None:
    start = _utc(start_inclusive_utc, "sealed_final.start"); end = _utc(end_exclusive_utc, "sealed_final.end")
    if _days(start, end, "sealed_final") != 365: raise ProtocolV3ReportError("sealed_final_holdout candidate must contain 365 days")
    root = _root(repository_root, FORWARD_REGISTRATION_ROOT, False)
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json": raise ProtocolV3ReportError("forward registration root contains an unexpected or unsafe entry")
        item = read_forward_window_registration(path, repository_root).to_dict(); fs = _utc(item["start_inclusive_utc"], "forward.start"); fe = _utc(item["end_exclusive_utc"], "forward.end")
        if start < fe and fs < end: raise ProtocolV3ReportError("sealed_final_holdout candidate overlaps an already visible forward month")

def _build_window(kind: str, window_id: str, start_text: str | None, end_text: str | None, pipeline: str, fingerprint: str, registration: ProtocolV3WindowRegistration | None) -> dict[str, Any]:
    if kind == PROTOCOL_V3_PIPELINE_FINAL:
        if start_text is not None or end_text is not None: raise ProtocolV3ReportError("Task-11 pipeline-final schema is reserved; Task 31 must register the real sealed window")
        if registration is not None: raise ProtocolV3ReportError("pipeline-final schema cannot use a forward registration")
        return {"window_id": window_id, "window_class": _WINDOWS[kind], "start_inclusive_utc": None, "end_exclusive_utc": None, "calendar_days": None, "registration_id": None, "registration_sha256": None}
    if start_text is None or end_text is None: raise ProtocolV3ReportError(f"{kind} requires an explicit evidence window")
    start = _utc(start_text, "start_inclusive_utc"); end = _utc(end_text, "end_exclusive_utc"); days = _days(start, end, kind); reg_id = reg_sha = None
    if kind == FORWARD_SHADOW_MONTH:
        if registration is None: raise ProtocolV3ReportError("forward_shadow_month requires a validated pre-start registration")
        reg = validate_window_registration(registration); data = reg.to_dict(); expected = {"start_inclusive_utc": _fmt(start), "end_exclusive_utc": _fmt(end), "calendar_days": days, "pipeline_generation": pipeline, "run_fingerprint": fingerprint}
        if any(data[key] != value for key, value in expected.items()): raise ProtocolV3ReportError("forward report window differs from its registration")
        reg_id, reg_sha = data["registration_id"], reg.registration_sha256
    elif registration is not None: raise ProtocolV3ReportError("only forward_shadow_month may consume a forward registration")
    return {"window_id": window_id, "window_class": _WINDOWS[kind], "start_inclusive_utc": _fmt(start), "end_exclusive_utc": _fmt(end), "calendar_days": days, "registration_id": reg_id, "registration_sha256": reg_sha}

def _validate_window(kind: str, window: Mapping[str, Any], created: datetime) -> None:
    _keys(window, _WINDOW_KEYS, "evidence_window"); _identifier(window.get("window_id"), "window_id"); _lit(window, "window_class", _WINDOWS[kind], "evidence_window")
    if kind == PROTOCOL_V3_PIPELINE_FINAL:
        if any(window.get(key) is not None for key in _WINDOW_KEYS - {"window_id", "window_class"}): raise ProtocolV3ReportError("Task-11 pipeline-final report cannot claim an executed sealed holdout")
        return
    start = _utc(window.get("start_inclusive_utc"), "evidence_window.start"); end = _utc(window.get("end_exclusive_utc"), "evidence_window.end"); days = _days(start, end, "evidence_window")
    if type(window.get("calendar_days")) is not int or window["calendar_days"] != days: raise ProtocolV3ReportError("evidence_window.calendar_days is inconsistent")
    if kind == MONTHLY_PROCESS_OOS and days != 365: raise ProtocolV3ReportError("monthly_process_oos must contain exactly 365 days")
    if kind == FORWARD_SHADOW_MONTH:
        _calendar_month(start, end)
        if created < end: raise ProtocolV3ReportError("forward_shadow_month report cannot predate the completed month")
        _identifier(window.get("registration_id"), "registration_id")
        if not isinstance(window.get("registration_sha256"), str) or not _HEX.fullmatch(window["registration_sha256"]): raise ProtocolV3ReportError("registration_sha256 is invalid")
    elif window.get("registration_id") is not None or window.get("registration_sha256") is not None: raise ProtocolV3ReportError("non-forward report cannot claim a forward registration")

def _metrics(kind: str, net: float | int | None) -> dict[str, Any]:
    if kind == MONTHLY_PROCESS_OOS: return {"process_oos_net_usdc": _number(net, "process_oos_net_usdc"), "process_oos_calendar_days": 365, "target_usdc_per_calendar_day": 3.0}
    if net is not None: raise ProtocolV3ReportError("process_oos_net_usdc is only valid for monthly_process_oos")
    return {"process_oos_net_usdc": None, "process_oos_calendar_days": None, "target_usdc_per_calendar_day": 3.0}

def _validate_metrics(kind: str, metrics: Mapping[str, Any]) -> None:
    _keys(metrics, _METRIC_KEYS, "metrics"); _lit(metrics, "target_usdc_per_calendar_day", 3.0, "metrics")
    if kind == MONTHLY_PROCESS_OOS: _number(metrics.get("process_oos_net_usdc"), "process_oos_net_usdc"); _lit(metrics, "process_oos_calendar_days", 365, "metrics")
    elif metrics.get("process_oos_net_usdc") is not None or metrics.get("process_oos_calendar_days") is not None: raise ProtocolV3ReportError("only monthly_process_oos may contain process OOS metrics")

def _status(kind: str, metrics: Mapping[str, Any]) -> dict[str, Any]:
    hit = kind == MONTHLY_PROCESS_OOS and _number(metrics.get("process_oos_net_usdc"), "process_oos_net_usdc") / 365 >= 3.0
    return {"historically_hit": bool(hit), "historical_bootstrap_lower_bound": False, "freshness": _FRESHNESS[kind], "fresh_pre_registered_sealed_365": False, "sealed_bootstrap_target_supported": False, "statistically_supported": False, "canonical_adoption_eligible": False, "diagnostic_only": True}

def _root(repo_value: str | Path, relative_text: str, create: bool) -> Path:
    repo = Path(repo_value)
    if not repo.exists() or not repo.is_dir() or repo.is_symlink(): raise ProtocolV3ReportError("repository_root must be an existing real directory")
    repo = repo.resolve(); relative = PurePosixPath(relative_text)
    if relative.is_absolute() or ".." in relative.parts: raise ProtocolV3ReportError("storage root must be repository-relative")
    root = repo.joinpath(*relative.parts); _no_symlinks(repo, root)
    if create: root.mkdir(parents=True, exist_ok=True)
    if not root.exists() or not root.is_dir() or root.is_symlink(): raise ProtocolV3ReportError("storage root is missing or unsafe")
    root = root.resolve()
    if not is_path_within(root, repo): raise ProtocolV3ReportError("storage root escapes repository_root")
    _no_symlinks(repo, root); return root

def _guard_read_path(path: Path, repository_root: str | Path, allowed_roots: Sequence[str]) -> Path:
    repo_candidate = Path(repository_root)
    if not repo_candidate.exists() or not repo_candidate.is_dir() or repo_candidate.is_symlink():
        raise ProtocolV3ReportError("repository_root must be an existing real directory")
    repo = repo_candidate.resolve()
    candidate = path if path.is_absolute() else repo / path
    try:
        candidate.relative_to(repo)
    except ValueError as exc:
        raise ProtocolV3ReportError("report path is outside Protocol v3 storage roots") from exc
    _no_symlinks(repo, candidate)
    selected_root: Path | None = None
    for relative_text in allowed_roots:
        relative_root = PurePosixPath(relative_text)
        lexical_root = repo.joinpath(*relative_root.parts)
        try:
            candidate.relative_to(lexical_root)
        except ValueError:
            continue
        selected_root = _root(repo, relative_text, False)
        break
    if selected_root is None:
        raise ProtocolV3ReportError("report path is outside Protocol v3 storage roots")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ProtocolV3ReportError("report path is missing or unreadable") from exc
    if path.is_symlink() or candidate.is_symlink():
        raise ProtocolV3ReportError("report path must not be a symlink")
    if not is_path_within(resolved, selected_root):
        raise ProtocolV3ReportError("report path escapes its Protocol v3 storage root")
    return resolved

def _exact_path(path: Path, expected: Path, root: Path) -> None:
    if path.is_symlink(): raise ProtocolV3ReportError("report path must not be a symlink")
    try: actual, wanted = path.resolve(strict=True), expected.resolve(strict=True)
    except OSError as exc: raise ProtocolV3ReportError("report path is missing or unreadable") from exc
    if actual != wanted or actual.parent != root.resolve(): raise ProtocolV3ReportError("report is stored under the wrong Protocol v3 root")

def _no_symlinks(repo: Path, target: Path) -> None:
    try: parts = target.relative_to(repo).parts
    except ValueError as exc: raise ProtocolV3ReportError("storage target escapes repository root") from exc
    current = repo
    for part in parts:
        current /= part
        if current.exists() and current.is_symlink(): raise ProtocolV3ReportError("symlinked Protocol v3 storage paths are forbidden")

def _write(path: Path, canonical: str) -> None:
    try:
        with path.open("xb") as handle: handle.write(_bytes(canonical)); handle.flush(); os.fsync(handle.fileno())
    except FileExistsError: raise
    except OSError as exc: raise ProtocolV3ReportError(f"could not persist Protocol v3 JSON: {path}") from exc

def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    try: raw = path.read_bytes(); value = _strict_load(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ProtocolV3ReportError(f"Protocol v3 JSON is unreadable or invalid: {path}") from exc
    if not isinstance(value, dict): raise ProtocolV3ReportError("Protocol v3 JSON must contain one object")
    return value, raw

def _strict_load(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result: raise ProtocolV3ReportError(f"duplicate JSON key is forbidden: {key}")
            result[key] = value
        return result
    def constant(value: str) -> None: raise ProtocolV3ReportError(f"non-finite JSON constant is forbidden: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)

def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping): raise ProtocolV3ReportError(f"{path} must be an object")
    return value

def _keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing, extra = expected - set(value), set(value) - expected
    if missing or extra: raise ProtocolV3ReportError(f"{path} keys are invalid; missing={sorted(missing)} extra={sorted(extra)}")

def _lit(value: Mapping[str, Any], key: str, expected: Any, path: str) -> None:
    observed = value.get(key)
    if observed != expected or type(observed) is not type(expected): raise ProtocolV3ReportError(f"{path}.{key} must be {expected!r}")

def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or not _SAFE.fullmatch(value): raise ProtocolV3ReportError(f"{path} must be a safe identifier")
    return value

def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip(): raise ProtocolV3ReportError(f"{path} must be a non-empty string")
    return value

def _strings(value: Any, path: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence): raise ProtocolV3ReportError(f"{path} must be a sequence of strings")
    rows = [_text(item, path) for item in value]; return sorted(set(rows))

def _fingerprint(value: Any) -> str:
    if not isinstance(value, str) or not _RUN.fullmatch(value): raise ProtocolV3ReportError("run_fingerprint is invalid")
    return value

def _pipeline(value: Any) -> str:
    if not isinstance(value, str) or not _PIPE.fullmatch(value): raise ProtocolV3ReportError("pipeline_generation is invalid")
    return value

def _utc(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"): raise ProtocolV3ReportError(f"{path} must be an ISO-8601 UTC timestamp ending in Z")
    try: parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc: raise ProtocolV3ReportError(f"{path} is invalid") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed) or _fmt(parsed) != value: raise ProtocolV3ReportError(f"{path} must use canonical UTC serialization")
    return parsed.astimezone(UTC)

def _utc_now() -> datetime: return datetime.now(UTC)
def _fmt(value: datetime) -> str: return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
def _days(start: datetime, end: datetime, path: str) -> int:
    if end <= start: raise ProtocolV3ReportError(f"{path} end must be after start")
    days, remainder = divmod((end - start).total_seconds(), 86400)
    if remainder or start.hour or start.minute or start.second or start.microsecond or end.hour or end.minute or end.second or end.microsecond: raise ProtocolV3ReportError(f"{path} must use complete UTC days")
    return int(days)
def _calendar_month(start: datetime, end: datetime) -> None:
    if start.day != 1: raise ProtocolV3ReportError("forward window must begin on UTC calendar-month day 1")
    expected = start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    if end != expected: raise ProtocolV3ReportError("forward window must end at the next UTC month boundary")
def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)): raise ProtocolV3ReportError(f"{path} must be a finite number")
    return float(value)
def _finite_json(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str): raise ProtocolV3ReportError(f"{path} contains a non-string key")
            _finite_json(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value): _finite_json(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value): raise ProtocolV3ReportError(f"{path} contains a non-finite number")
    elif not isinstance(value, (str, int, float, bool, type(None))): raise ProtocolV3ReportError(f"{path} contains an unsupported JSON value")
def _json(value: Any) -> str: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
def _normalize(value: Any) -> Any: return json.loads(_json(value))
def _sha(value: Any) -> str: return hashlib.sha256(_json(value).encode()).hexdigest()
def _bytes(canonical: str) -> bytes: return (canonical + "\n").encode()

__all__ = ["FORWARD_REGISTRATION_ROOT", "FORWARD_SHADOW_MONTH", "MONTHLY_PROCESS_OOS", "PROCESS_OOS_CALENDAR_DAYS", "PROTOCOL_V3_PIPELINE_FINAL", "PROTOCOL_V3_RESEARCH", "REPORT_CONTRACT_PATH", "REPORT_CONTRACT_SCHEMA", "REPORT_CONTRACT_VERSION", "REPORT_KINDS", "REPORT_SCHEMA_VERSION", "REPORT_STORAGE_ROOTS", "RESEARCH_CHALLENGER_SHADOW", "TARGET_USDC_PER_CALENDAR_DAY", "WINDOW_REGISTRATION_SCHEMA_VERSION", "ProtocolV3Report", "ProtocolV3ReportError", "ProtocolV3WindowRegistration", "assert_sealed_final_window_excludes_visible_forward_months", "build_forward_window_registration", "build_protocol_v3_report", "load_report_contract", "read_forward_window_registration", "read_protocol_v3_report", "validate_protocol_v3_report", "validate_report_contract", "validate_window_registration", "write_forward_window_registration", "write_protocol_v3_report"]
