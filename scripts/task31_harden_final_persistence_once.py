from pathlib import Path
import json

report_path = Path("src/ethusdc_bot/protocol_v3/pipeline_final_report.py")
report = report_path.read_text(encoding="utf-8")
old_import = '''from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.protocol_v3.hindsight_binding import BoundHindsightBenchmarks
'''
new_import = '''from ethusdc_bot.path_safety import is_path_within
from ethusdc_bot.protocol_v3.boundaries import MonthlyProcessBoundaryPlan
from ethusdc_bot.protocol_v3.hindsight_binding import BoundHindsightBenchmarks
'''
if report.count(old_import) != 1:
    raise SystemExit("final report boundary import replacement mismatch")
report = report.replace(old_import, new_import)
report = report.replace(
    '    "protocol_v3_exactly_once_pipeline_final_report_open_v1"\n',
    '    "protocol_v3_exactly_once_pipeline_final_report_open_v2"\n',
    1,
)
if report.count("    boundary_plan: Any,\n") != 1:
    raise SystemExit("final report boundary type replacement mismatch")
report = report.replace(
    "    boundary_plan: Any,\n",
    "    boundary_plan: MonthlyProcessBoundaryPlan,\n",
)
open_start = report.index("def open_pipeline_final_report(")
open_end = report.index("\ndef validate_pipeline_final_report(", open_start)
open_function = '''def open_pipeline_final_report(
    *,
    attestation_path: str | Path,
    repository_root: str | Path,
    source_repository_root: str | Path,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
    progress: PipelineFinalProgress,
    checkpoint: PipelineFinalCheckpoint,
    boundary_plan: MonthlyProcessBoundaryPlan,
    outer_process: OuterOriginProcess,
    baseline_ledger: OuterMtmLedger,
    joint_stress_ledger: OuterMtmLedger,
    slippage_stress_ledger: OuterMtmLedger,
    monthly_quality_report: MonthlyQualityGateReport,
    stress_identity_evidence: Mapping[str, Any],
    regime_evidence: Mapping[str, Any],
    integrity_evidence: Mapping[str, Any],
    bound_hindsight_benchmarks: BoundHindsightBenchmarks,
    opened_at_utc: str,
) -> PipelineFinalReportOpenResult:
    repo = _repo(repository_root)
    stored = read_pipeline_final_attestation(attestation_path, repo)
    try:
        attested = validate_pipeline_final_attestation(
            stored.to_dict(),
            registration=registration,
            claim=claim,
            progress=progress,
            checkpoint=checkpoint,
            boundary_plan=boundary_plan,
            outer_process=outer_process,
            baseline_ledger=baseline_ledger,
            joint_stress_ledger=joint_stress_ledger,
            slippage_stress_ledger=slippage_stress_ledger,
            monthly_quality_report=monthly_quality_report,
            stress_identity_evidence=stress_identity_evidence,
            regime_evidence=regime_evidence,
            integrity_evidence=integrity_evidence,
            bound_hindsight_benchmarks=bound_hindsight_benchmarks,
            source_repository_root=source_repository_root,
        )
    except PipelineFinalAttestationError as exc:
        raise PipelineFinalReportError(
            "pipeline-final attestation failed transitive revalidation"
        ) from exc
    opened = _utc(opened_at_utc, "opened_at_utc")
    if abs(_utc_now() - opened) > _CLOCK_TOLERANCE:
        raise PipelineFinalReportError(
            "pipeline-final report open timestamp is not current"
        )
    source = attested.to_dict()
    report_root = _safe_root(repo, REPORT_ROOT, create=True)
    receipt_root = _safe_root(repo, OPEN_RECEIPT_ROOT, create=True)
    report_id = _report_id(source["registration_sha256"])
    report_path = report_root / f"{report_id}.json"
    receipt_path = receipt_root / f"{source['registration_sha256']}.json"

    report_exists = report_path.exists() or report_path.is_symlink()
    receipt_exists = receipt_path.exists() or receipt_path.is_symlink()
    if receipt_exists and not report_exists:
        raise PipelineFinalReportError(
            "pipeline-final open receipt exists without its final report"
        )
    if report_exists:
        report = read_pipeline_final_report(
            report_path,
            repo,
            attestation=attested,
            registration=registration,
        )
    else:
        report = build_pipeline_final_report(
            attested,
            registration,
            created_at_utc=opened_at_utc,
        )
    if receipt_exists:
        existing = read_pipeline_final_open_receipt(
            receipt_path,
            repo,
            attestation=attested,
            registration=registration,
            report=report,
        )
        raise PipelineFinalReportAlreadyOpenedError(
            f"pipeline-final report was already opened: {existing.receipt_id}"
        )
    if not report_exists:
        try:
            _write_create_only(report_path, _bytes(report.canonical_json))
        except FileExistsError:
            report = read_pipeline_final_report(
                report_path,
                repo,
                attestation=attested,
                registration=registration,
            )
        else:
            reloaded_report = read_pipeline_final_report(
                report_path,
                repo,
                attestation=attested,
                registration=registration,
            )
            if reloaded_report != report:
                raise PipelineFinalReportError(
                    "pipeline-final report reload mismatch"
                )
    receipt = build_pipeline_final_open_receipt(
        attested,
        registration,
        report,
        opened_at_utc=opened_at_utc,
        report_path=report_path.relative_to(repo).as_posix(),
    )
    try:
        _write_create_only(receipt_path, _bytes(receipt.canonical_json))
    except FileExistsError as exc:
        raise PipelineFinalReportAlreadyOpenedError(
            "pipeline-final report open receipt already exists"
        ) from exc
    reloaded_receipt = read_pipeline_final_open_receipt(
        receipt_path,
        repo,
        attestation=attested,
        registration=registration,
        report=report,
    )
    if reloaded_receipt != receipt:
        raise PipelineFinalReportError("pipeline-final open receipt reload mismatch")
    return PipelineFinalReportOpenResult(
        report,
        report_path,
        receipt,
        receipt_path,
    )

'''
report = report[:open_start] + open_function + report[open_end + 1 :]
old_receipt_validation = '''    _utc(root["opened_at_utc"], "opened_at_utc")
    path = PurePosixPath(root["report_path"])
    if path.is_absolute() or ".." in path.parts:
        raise PipelineFinalReportError("pipeline-final receipt report path is unsafe")
'''
new_receipt_validation = '''    opened = _utc(root["opened_at_utc"], "opened_at_utc")
    report_created = _utc(report_payload["created_at_utc"], "report.created_at_utc")
    path = PurePosixPath(root["report_path"])
    expected_path = PurePosixPath(
        REPORT_ROOT,
        f"{report_payload['report_id']}.json",
    )
    if (
        opened < report_created
        or path.is_absolute()
        or ".." in path.parts
        or path != expected_path
    ):
        raise PipelineFinalReportError(
            "pipeline-final receipt time or report path is invalid"
        )
'''
if report.count(old_receipt_validation) != 1:
    raise SystemExit("final receipt time/path replacement mismatch")
report = report.replace(old_receipt_validation, new_receipt_validation)
old_metric = '''    net = _number(metrics["process_oos_net_usdc"], "process_oos_net_usdc")
'''
new_metric = '''    _number(metrics["process_oos_net_usdc"], "process_oos_net_usdc")
    net = _decimal(metrics["process_oos_net_usdc"], "process_oos_net_usdc")
'''
if report.count(old_metric) != 1:
    raise SystemExit("final report exact metric replacement mismatch")
report = report.replace(old_metric, new_metric)
if report.count("    expected_hit = net / 365 >= 3.0\n") != 1:
    raise SystemExit("final report exact target replacement mismatch")
report = report.replace(
    "    expected_hit = net / 365 >= 3.0\n",
    "    expected_hit = net / Decimal(365) >= _TARGET\n",
)
old_write = '''def _write_create_only(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise
    except OSError as exc:
        raise PipelineFinalReportError(f"could not persist pipeline-final JSON: {path}") from exc


def _read(path: Path, name: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineFinalReportError(f"{name} is unreadable or invalid") from exc
    if not isinstance(value, dict):
        raise PipelineFinalReportError(f"{name} must contain one object")
    return value, raw
'''
new_write = '''def _write_create_only(path: Path, data: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(path.parent)
    except FileExistsError:
        raise
    except OSError as exc:
        raise PipelineFinalReportError(
            f"could not persist pipeline-final JSON: {path}"
        ) from exc


def _read(path: Path, name: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise PipelineFinalReportError(f"{name} is unreadable or invalid") from exc
    value = _strict_json_loads(text, name)
    if not isinstance(value, dict):
        raise PipelineFinalReportError(f"{name} must contain one object")
    return value, raw


def _strict_json_loads(text: str, name: str) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise PipelineFinalReportError(
            f"{name} contains invalid or duplicate-key JSON"
        ) from exc


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError as exc:
        raise PipelineFinalReportError(
            f"could not open directory for fsync: {path}"
        ) from exc
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
'''
if report.count(old_write) != 1:
    raise SystemExit("final report strict persistence replacement mismatch")
report = report.replace(old_write, new_write)
report_path.write_text(report, encoding="utf-8")

attestation_path = Path("src/ethusdc_bot/protocol_v3/pipeline_final_attestation.py")
attestation = attestation_path.read_text(encoding="utf-8")
old_attestation_io = '''def _write_create_only(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation is unreadable or invalid"
        ) from exc
    if not isinstance(value, dict):
        raise PipelineFinalAttestationError(
            "pipeline-final attestation must contain one object"
        )
    return value, raw
'''
new_attestation_io = '''def _write_create_only(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation is unreadable or invalid"
        ) from exc
    value = _strict_json_loads(text)
    if not isinstance(value, dict):
        raise PipelineFinalAttestationError(
            "pipeline-final attestation must contain one object"
        )
    return value, raw


def _strict_json_loads(text: str) -> Any:
    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    try:
        return json.loads(
            text,
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise PipelineFinalAttestationError(
            "pipeline-final attestation contains invalid or duplicate-key JSON"
        ) from exc


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError as exc:
        raise PipelineFinalAttestationError(
            f"could not open directory for fsync: {path}"
        ) from exc
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
'''
if attestation.count(old_attestation_io) != 1:
    raise SystemExit("attestation strict persistence replacement mismatch")
attestation_path.write_text(
    attestation.replace(old_attestation_io, new_attestation_io),
    encoding="utf-8",
)

final_path = Path("src/ethusdc_bot/protocol_v3/pipeline_final.py")
final = final_path.read_text(encoding="utf-8")
final = final.replace(
    '            "protocol_v3_exactly_once_pipeline_final_report_open_v1"\n',
    '            "protocol_v3_exactly_once_pipeline_final_report_open_v2"\n',
    1,
)
sealing_anchor = '''        "exact_report_without_receipt_is_crash_recoverable": True,
        "second_open_after_receipt_forbidden": True,
        "result_feedback_to_pipeline_forbidden": True,
'''
sealing_new = '''        "exact_report_without_receipt_is_crash_recoverable": True,
        "delayed_receipt_recovery_uses_persisted_report_timestamp": True,
        "duplicate_json_keys_forbidden": True,
        "file_and_directory_fsync_required": True,
        "receipt_without_report_forbidden": True,
        "second_open_after_receipt_forbidden": True,
        "result_feedback_to_pipeline_forbidden": True,
'''
if final.count(sealing_anchor) != 1:
    raise SystemExit("pipeline-final sealing hardening replacement mismatch")
final_path.write_text(final.replace(sealing_anchor, sealing_new), encoding="utf-8")

contract_path = Path("configs/protocol_v3_pipeline_final_contract.json")
contract = json.loads(contract_path.read_text(encoding="utf-8"))
contract["sealing_policy"].update(
    {
        "final_report_contract_version": (
            "protocol_v3_exactly_once_pipeline_final_report_open_v2"
        ),
        "delayed_receipt_recovery_uses_persisted_report_timestamp": True,
        "duplicate_json_keys_forbidden": True,
        "file_and_directory_fsync_required": True,
        "receipt_without_report_forbidden": True,
    }
)
contract_path.write_text(
    json.dumps(contract, indent=2, ensure_ascii=True) + "\n",
    encoding="utf-8",
)

pipeline_contract_path = Path("configs/protocol_v3_pipeline_contract.json")
pipeline_contract = json.loads(pipeline_contract_path.read_text(encoding="utf-8"))
versions = pipeline_contract["component_contracts"]["quality_gates"]
if "protocol_v3_exactly_once_pipeline_final_report_open_v1" in versions:
    versions.remove("protocol_v3_exactly_once_pipeline_final_report_open_v1")
if "protocol_v3_exactly_once_pipeline_final_report_open_v2" not in versions:
    versions.append("protocol_v3_exactly_once_pipeline_final_report_open_v2")
pipeline_contract_path.write_text(
    json.dumps(pipeline_contract, indent=2, ensure_ascii=True) + "\n",
    encoding="utf-8",
)

reporting_path = Path("src/ethusdc_bot/protocol_v3/reporting.py")
reporting = reporting_path.read_text(encoding="utf-8")
old_policy = '''    "final_evidence_policy": {"sealed_final_holdout_is_window_class_not_report_kind": True, "pipeline_final_artifact_kind": PROTOCOL_V3_PIPELINE_FINAL, "legacy_final_report_type_forbidden": "final_evaluation", "task31_attestation_required": True, "task31_attestation_available": False, "visible_forward_month_overlap_forbidden": True},
'''
new_policy = '''    "final_evidence_policy": {"sealed_final_holdout_is_window_class_not_report_kind": True, "pipeline_final_artifact_kind": PROTOCOL_V3_PIPELINE_FINAL, "legacy_final_report_type_forbidden": "final_evaluation", "task31_attestation_required": True, "task31_attestation_available": False, "generic_task11_builder_remains_reserved": True, "dedicated_task31_opener_required": True, "dedicated_task31_reader_required": True, "visible_forward_month_overlap_forbidden": True},
'''
if reporting.count(old_policy) != 1:
    raise SystemExit("generic report dedicated Task31 policy replacement mismatch")
reporting_path.write_text(reporting.replace(old_policy, new_policy), encoding="utf-8")

report_contract_path = Path("configs/protocol_v3_report_contract.json")
report_contract = json.loads(report_contract_path.read_text(encoding="utf-8"))
report_contract["final_evidence_policy"].update(
    {
        "generic_task11_builder_remains_reserved": True,
        "dedicated_task31_opener_required": True,
        "dedicated_task31_reader_required": True,
    }
)
report_contract_path.write_text(
    json.dumps(report_contract, indent=2, ensure_ascii=True) + "\n",
    encoding="utf-8",
)

report_test_path = Path("tests/unit/test_protocol_v3_pipeline_final_report.py")
test = report_test_path.read_text(encoding="utf-8")
test = test.replace(
    "from datetime import datetime\n",
    "from datetime import datetime, timedelta\n",
    1,
)
old_crash = '''    original = report_path.read_bytes()
    opened = _open(state)
    assert opened.report == report
    assert report_path.read_bytes() == original
    assert opened.receipt_path.exists()
'''
new_crash = '''    original = report_path.read_bytes()
    recovered_dt = state["opened_dt"] + timedelta(hours=2)
    recovered = dict(state)
    recovered["opened_dt"] = recovered_dt
    recovered["opened_at"] = recovered_dt.isoformat().replace("+00:00", "Z")
    monkeypatch.setattr(
        pipeline_final_report,
        "_utc_now",
        lambda: recovered_dt,
    )
    opened = _open(recovered)
    assert opened.report == report
    assert report_path.read_bytes() == original
    assert opened.receipt.to_dict()["opened_at_utc"] == recovered["opened_at"]
    assert opened.receipt_path.exists()
'''
if test.count(old_crash) != 1:
    raise SystemExit("delayed report crash-recovery test replacement mismatch")
test = test.replace(old_crash, new_crash)
insert_anchor = '''def test_forged_report_evidence_or_legacy_source_is_blocked(state) -> None:
'''
new_tests = '''def test_duplicate_key_json_and_orphan_receipt_fail_closed(
    state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = pipeline_final_report.build_pipeline_final_report(
        state["attestation"],
        state["registration"],
        created_at_utc=state["opened_at"],
    )
    root = pipeline_final_report._safe_root(
        Path(state["repo"]).resolve(),
        pipeline_final_report.REPORT_ROOT,
        create=True,
    )
    report_path = root / f"{report.report_id}.json"
    malformed = report.canonical_json[:-1] + ',"report_id":"duplicate"}\n'
    report_path.write_text(malformed, encoding="utf-8")
    with pytest.raises(
        pipeline_final_report.PipelineFinalReportError,
        match="duplicate-key JSON",
    ):
        pipeline_final_report.read_pipeline_final_report(
            report_path,
            state["repo"],
            attestation=state["attestation"],
            registration=state["registration"],
        )

    report_path.unlink()
    receipt_root = pipeline_final_report._safe_root(
        Path(state["repo"]).resolve(),
        pipeline_final_report.OPEN_RECEIPT_ROOT,
        create=True,
    )
    orphan = receipt_root / (
        state["attestation"].to_dict()["registration_sha256"] + ".json"
    )
    orphan.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(
        pipeline_final_report,
        "_utc_now",
        lambda: state["opened_dt"],
    )
    with pytest.raises(
        pipeline_final_report.PipelineFinalReportError,
        match="receipt exists without its final report",
    ):
        _open(state)


def test_duplicate_key_attestation_is_rejected(state) -> None:
    path = state["attestation_path"]
    raw = state["attestation"].canonical_json
    path.write_text(raw[:-1] + ',"registration_id":"duplicate"}\n', encoding="utf-8")
    with pytest.raises(
        pipeline_final_attestation.PipelineFinalAttestationError,
        match="duplicate-key JSON",
    ):
        pipeline_final_attestation.read_pipeline_final_attestation(
            path,
            state["repo"],
        )


'''
if test.count(insert_anchor) != 1:
    raise SystemExit("strict final persistence tests insertion mismatch")
test = test.replace(insert_anchor, new_tests + insert_anchor)
report_test_path.write_text(test, encoding="utf-8")

reporting_test_path = Path("tests/unit/test_protocol_v3_reporting.py")
reporting_test = reporting_test_path.read_text(encoding="utf-8")
assertion_anchor = '''    assert contract["final_evidence_policy"]["legacy_final_report_type_forbidden"] == "final_evaluation"
'''
assertions = assertion_anchor + '''    assert contract["final_evidence_policy"]["task31_attestation_available"] is False
    assert contract["final_evidence_policy"]["generic_task11_builder_remains_reserved"] is True
    assert contract["final_evidence_policy"]["dedicated_task31_opener_required"] is True
    assert contract["final_evidence_policy"]["dedicated_task31_reader_required"] is True
'''
if reporting_test.count(assertion_anchor) != 1:
    raise SystemExit("generic report dedicated Task31 test anchor mismatch")
reporting_test_path.write_text(
    reporting_test.replace(assertion_anchor, assertions),
    encoding="utf-8",
)

final_test_path = Path("tests/unit/test_protocol_v3_pipeline_final.py")
final_test = final_test_path.read_text(encoding="utf-8")
anchor = '''    assert contract["sealing_policy"]["second_open_after_receipt_forbidden"] is True
'''
extra = anchor + '''    assert contract["sealing_policy"]["final_report_contract_version"] == (
        "protocol_v3_exactly_once_pipeline_final_report_open_v2"
    )
    assert contract["sealing_policy"][
        "delayed_receipt_recovery_uses_persisted_report_timestamp"
    ] is True
    assert contract["sealing_policy"]["duplicate_json_keys_forbidden"] is True
    assert contract["sealing_policy"]["file_and_directory_fsync_required"] is True
    assert contract["sealing_policy"]["receipt_without_report_forbidden"] is True
'''
if final_test.count(anchor) != 1:
    raise SystemExit("pipeline-final hardening contract test anchor mismatch")
final_test_path.write_text(final_test.replace(anchor, extra), encoding="utf-8")
