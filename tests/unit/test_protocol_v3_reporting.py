"""Protocol v3 Task-11 report-schema and evidence-semantics tests."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import shutil

import pytest

from ethusdc_bot.protocol_v3 import reporting
from ethusdc_bot.protocol_v3.pipeline import build_pipeline_generation
from ethusdc_bot.protocol_v3.reporting import (
    FORWARD_SHADOW_MONTH,
    MONTHLY_PROCESS_OOS,
    PROTOCOL_V3_PIPELINE_FINAL,
    PROTOCOL_V3_RESEARCH,
    REPORT_KINDS,
    REPORT_STORAGE_ROOTS,
    RESEARCH_CHALLENGER_SHADOW,
    ProtocolV3ReportError,
    assert_sealed_final_window_excludes_visible_forward_months,
    build_forward_window_registration,
    build_protocol_v3_report,
    load_report_contract,
    read_forward_window_registration,
    read_protocol_v3_report,
    validate_protocol_v3_report,
    validate_report_contract,
    write_forward_window_registration,
    write_protocol_v3_report,
)
from ethusdc_bot.shadow.adoption import (
    ShadowAdoptionError,
    adopt_for_shadow,
    validate_final_evaluation_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_GENERATION = "protocol_v3_pipeline_sha256:" + "a" * 64
RUN_FINGERPRINT = "protocol_v3_run_sha256:" + "b" * 64


def _report(
    kind: str,
    *,
    report_id: str | None = None,
    created_at_utc: str = "2026-07-16T10:00:00Z",
    process_oos_net_usdc: float | None = None,
    forward_registration=None,
):
    windows = {
        PROTOCOL_V3_RESEARCH: (
            "historical_research_window",
            "2024-01-01T00:00:00Z",
            "2024-02-01T00:00:00Z",
            "completed_diagnostic",
        ),
        MONTHLY_PROCESS_OOS: (
            "monthly_process_window",
            "2025-07-08T00:00:00Z",
            "2026-07-08T00:00:00Z",
            "completed_diagnostic",
        ),
        RESEARCH_CHALLENGER_SHADOW: (
            "challenger_window",
            "2024-03-01T00:00:00Z",
            "2024-04-01T00:00:00Z",
            "completed_diagnostic",
        ),
        FORWARD_SHADOW_MONTH: (
            "forward_window",
            "2026-08-01T00:00:00Z",
            "2026-09-01T00:00:00Z",
            "completed_forward_observation",
        ),
        PROTOCOL_V3_PIPELINE_FINAL: (
            "sealed_final_holdout_reserved",
            None,
            None,
            "schema_reserved_task_31",
        ),
    }
    window_id, start, end, producer_status = windows[kind]
    return build_protocol_v3_report(
        artifact_kind=kind,
        report_id=report_id or f"report_{kind}",
        created_at_utc=created_at_utc,
        run_fingerprint=RUN_FINGERPRINT,
        pipeline_generation=PIPELINE_GENERATION,
        window_id=window_id,
        start_inclusive_utc=start,
        end_exclusive_utc=end,
        process_oos_net_usdc=(
            1095.0 if kind == MONTHLY_PROCESS_OOS and process_oos_net_usdc is None
            else process_oos_net_usdc
        ),
        producer="test_protocol_v3_reporting",
        producer_status=producer_status,
        source_artifact_ids=("source_b", "source_a"),
        reason_codes=("reason_b", "reason_a"),
        forward_registration=forward_registration,
    )


def _write_at_clock(monkeypatch: pytest.MonkeyPatch, report, root: Path, now: datetime) -> Path:
    monkeypatch.setattr(reporting, "_utc_now", lambda: now)
    return write_protocol_v3_report(report, root)


def _persisted_forward(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    registration_time = datetime(2026, 7, 1, tzinfo=UTC)
    monkeypatch.setattr(reporting, "_utc_now", lambda: registration_time)
    registration = build_forward_window_registration(
        registration_id="forward_registration_august_2026",
        registered_at_utc="2026-07-01T00:00:00Z",
        start_inclusive_utc="2026-08-01T00:00:00Z",
        end_exclusive_utc="2026-09-01T00:00:00Z",
        pipeline_generation=PIPELINE_GENERATION,
        run_fingerprint=RUN_FINGERPRINT,
    )
    registration_path = write_forward_window_registration(registration, tmp_path)
    reloaded_registration = read_forward_window_registration(registration_path, tmp_path)
    report = _report(
        FORWARD_SHADOW_MONTH,
        created_at_utc="2026-09-01T00:00:00Z",
        forward_registration=reloaded_registration,
    )
    report_path = _write_at_clock(
        monkeypatch, report, tmp_path, datetime(2026, 9, 1, tzinfo=UTC)
    )
    return reloaded_registration, report, report_path


def test_report_contract_is_exact_and_storage_roots_are_unique() -> None:
    contract = load_report_contract(REPO_ROOT)
    assert contract["contract_version"] == "protocol_v3_evidence_reports_v1"
    assert set(contract["artifact_kinds"]) == set(REPORT_KINDS)
    assert len(set(REPORT_STORAGE_ROOTS.values())) == len(REPORT_KINDS)
    assert contract["final_evidence_policy"]["legacy_final_report_type_forbidden"] == "final_evaluation"
    changed = json.loads(json.dumps(contract))
    changed["artifact_kinds"][MONTHLY_PROCESS_OOS]["freshness"] = "FRESH"
    with pytest.raises(ProtocolV3ReportError, match="not canonical"):
        validate_report_contract(changed)


def test_pipeline_generation_binds_task11_contract_and_implementation() -> None:
    basis = build_pipeline_generation(REPO_ROOT).basis()
    assert "protocol_v3_evidence_reports_v1" in basis["component_contracts"]["quality_gates"]
    contract = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text(encoding="utf-8"))
    bindings = contract["source_bindings"]["quality_gates"]
    assert "configs/protocol_v3_report_contract.json" in bindings
    assert "src/ethusdc_bot/protocol_v3/reporting.py" in bindings
    assert len(basis["component_source_sha256"]["quality_gates"]) == 64


def test_monthly_historical_hit_is_derived_without_statistical_support() -> None:
    hit = _report(MONTHLY_PROCESS_OOS, process_oos_net_usdc=1095.0).to_dict()
    miss = _report(MONTHLY_PROCESS_OOS, process_oos_net_usdc=1094.999).to_dict()
    assert hit["evidence_status"] == {
        "historically_hit": True,
        "historical_bootstrap_lower_bound": False,
        "freshness": "NOT_FRESH",
        "fresh_pre_registered_sealed_365": False,
        "sealed_bootstrap_target_supported": False,
        "statistically_supported": False,
        "canonical_adoption_eligible": False,
        "diagnostic_only": True,
    }
    assert miss["evidence_status"]["historically_hit"] is False


@pytest.mark.parametrize(
    ("field", "forged"),
    [
        ("freshness", "FRESH"),
        ("historically_hit", False),
        ("statistically_supported", True),
        ("canonical_adoption_eligible", True),
        ("diagnostic_only", False),
    ],
)
def test_evidence_status_cannot_be_asserted_by_the_caller(field: str, forged: object) -> None:
    payload = _report(MONTHLY_PROCESS_OOS).to_dict()
    payload["evidence_status"][field] = forged
    with pytest.raises(ProtocolV3ReportError, match="derived evidence"):
        validate_protocol_v3_report(payload)


def test_future_attestations_cannot_be_claimed_in_task11() -> None:
    payload = _report(MONTHLY_PROCESS_OOS).to_dict()
    payload["evidence_inputs"]["task31_final_attestation_sha256"] = "c" * 64
    with pytest.raises(ProtocolV3ReportError, match="cannot claim"):
        validate_protocol_v3_report(payload)


def test_forward_month_is_fresh_observation_but_never_final_or_adoptable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _, report, path = _persisted_forward(monkeypatch, tmp_path)
    reloaded = read_protocol_v3_report(path, tmp_path)
    assert reloaded == report
    evidence = reloaded.to_dict()["evidence_status"]
    assert evidence["freshness"] == "FRESH_FORWARD_OBSERVATION"
    assert evidence["fresh_pre_registered_sealed_365"] is False
    assert evidence["statistically_supported"] is False
    assert evidence["canonical_adoption_eligible"] is False


def test_forward_registration_cannot_be_backdated_or_written_after_start(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registration = build_forward_window_registration(
        registration_id="future_forward",
        registered_at_utc="2026-07-01T00:00:00Z",
        start_inclusive_utc="2026-08-01T00:00:00Z",
        end_exclusive_utc="2026-09-01T00:00:00Z",
        pipeline_generation=PIPELINE_GENERATION,
        run_fingerprint=RUN_FINGERPRINT,
    )
    monkeypatch.setattr(reporting, "_utc_now", lambda: datetime(2026, 8, 1, tzinfo=UTC))
    with pytest.raises(ProtocolV3ReportError, match="before the window starts"):
        write_forward_window_registration(registration, tmp_path)


def test_forward_report_cannot_be_written_before_month_completion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(reporting, "_utc_now", lambda: datetime(2026, 7, 1, tzinfo=UTC))
    registration = build_forward_window_registration(
        registration_id="forward_before_complete",
        registered_at_utc="2026-07-01T00:00:00Z",
        start_inclusive_utc="2026-08-01T00:00:00Z",
        end_exclusive_utc="2026-09-01T00:00:00Z",
        pipeline_generation=PIPELINE_GENERATION,
        run_fingerprint=RUN_FINGERPRINT,
    )
    write_forward_window_registration(registration, tmp_path)
    with pytest.raises(ProtocolV3ReportError, match="cannot predate"):
        _report(FORWARD_SHADOW_MONTH, created_at_utc="2026-08-15T00:00:00Z", forward_registration=registration)


def test_challenger_is_order_free_and_never_canonical_adoption_eligible() -> None:
    payload = _report(RESEARCH_CHALLENGER_SHADOW).to_dict()
    assert payload["evidence_status"]["canonical_adoption_eligible"] is False
    assert payload["safety"]["orders_enabled"] is False
    assert payload["safety"]["trading_api_enabled"] is False
    assert payload["safety"]["api_keys_used"] is False
    assert payload["safety"]["paper"] == "locked"
    assert payload["safety"]["live"] == "locked"


def test_pipeline_final_schema_is_reserved_and_cannot_claim_task31_evidence() -> None:
    reserved = _report(PROTOCOL_V3_PIPELINE_FINAL).to_dict()
    assert reserved["artifact_kind"] == PROTOCOL_V3_PIPELINE_FINAL
    assert reserved["evidence_window"]["window_class"] == "sealed_final_holdout"
    assert reserved["evidence_window"]["start_inclusive_utc"] is None
    assert reserved["evidence_status"]["freshness"] == "PENDING_TASK_31"
    assert reserved["evidence_status"]["statistically_supported"] is False
    with pytest.raises(ProtocolV3ReportError, match="Task 31"):
        build_protocol_v3_report(
            artifact_kind=PROTOCOL_V3_PIPELINE_FINAL,
            report_id="forged_final",
            created_at_utc="2026-07-16T10:00:00Z",
            run_fingerprint=RUN_FINGERPRINT,
            pipeline_generation=PIPELINE_GENERATION,
            window_id="forged_final_window",
            start_inclusive_utc="2027-01-01T00:00:00Z",
            end_exclusive_utc="2028-01-01T00:00:00Z",
            process_oos_net_usdc=None,
            producer="test",
            producer_status="schema_reserved_task_31",
        )


def test_visible_forward_month_can_never_overlap_future_sealed_holdout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _persisted_forward(monkeypatch, tmp_path)
    with pytest.raises(ProtocolV3ReportError, match="overlaps"):
        assert_sealed_final_window_excludes_visible_forward_months(
            start_inclusive_utc="2026-01-01T00:00:00Z",
            end_exclusive_utc="2027-01-01T00:00:00Z",
            repository_root=tmp_path,
        )
    assert_sealed_final_window_excludes_visible_forward_months(
        start_inclusive_utc="2027-01-01T00:00:00Z",
        end_exclusive_utc="2028-01-01T00:00:00Z",
        repository_root=tmp_path,
    )


def test_roundtrip_preserves_exact_meaning_and_input_order_is_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    first = build_protocol_v3_report(
        artifact_kind=PROTOCOL_V3_RESEARCH,
        report_id="deterministic_report",
        created_at_utc="2026-07-16T10:00:00Z",
        run_fingerprint=RUN_FINGERPRINT,
        pipeline_generation=PIPELINE_GENERATION,
        window_id="deterministic_window",
        start_inclusive_utc="2024-01-01T00:00:00Z",
        end_exclusive_utc="2024-02-01T00:00:00Z",
        process_oos_net_usdc=None,
        producer="determinism_test",
        producer_status="completed_diagnostic",
        source_artifact_ids=("b", "a", "b"),
        reason_codes=("z", "a", "z"),
    )
    second = build_protocol_v3_report(
        artifact_kind=PROTOCOL_V3_RESEARCH,
        report_id="deterministic_report",
        created_at_utc="2026-07-16T10:00:00Z",
        run_fingerprint=RUN_FINGERPRINT,
        pipeline_generation=PIPELINE_GENERATION,
        window_id="deterministic_window",
        start_inclusive_utc="2024-01-01T00:00:00Z",
        end_exclusive_utc="2024-02-01T00:00:00Z",
        process_oos_net_usdc=None,
        producer="determinism_test",
        producer_status="completed_diagnostic",
        source_artifact_ids=("a", "b"),
        reason_codes=("a", "z"),
    )
    assert first == second
    path = _write_at_clock(monkeypatch, first, tmp_path, datetime(2026, 7, 16, 10, tzinfo=UTC))
    assert read_protocol_v3_report(path, tmp_path) == first


def test_report_reader_rejects_outside_path_before_json_open(tmp_path: Path) -> None:
    (tmp_path / REPORT_STORAGE_ROOTS[PROTOCOL_V3_RESEARCH]).mkdir(parents=True)
    outside = tmp_path.parent / "outside_task11_report.json"
    outside.write_text("not-json", encoding="utf-8")
    try:
        with pytest.raises(
            ProtocolV3ReportError,
            match="outside|wrong Protocol v3 root",
        ):
            read_protocol_v3_report(outside, tmp_path)
    finally:
        outside.unlink(missing_ok=True)


def test_registration_reader_rejects_symlink_before_json_open(
    tmp_path: Path,
) -> None:
    registration_root = tmp_path / reporting.FORWARD_REGISTRATION_ROOT
    registration_root.mkdir(parents=True)
    outside = tmp_path / "outside_task11_registration.json"
    outside.write_text("not-json", encoding="utf-8")
    linked = registration_root / "linked.json"
    try:
        linked.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ProtocolV3ReportError, match="symlink"):
        read_forward_window_registration(linked, tmp_path)


def test_wrong_root_and_symlinked_root_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = _report(PROTOCOL_V3_RESEARCH)
    path = _write_at_clock(monkeypatch, report, tmp_path, datetime(2026, 7, 16, 10, tzinfo=UTC))
    wrong_root = tmp_path / REPORT_STORAGE_ROOTS[MONTHLY_PROCESS_OOS]
    wrong_root.mkdir(parents=True)
    wrong_path = wrong_root / path.name
    shutil.copyfile(path, wrong_path)
    with pytest.raises(ProtocolV3ReportError, match="wrong Protocol v3 root"):
        read_protocol_v3_report(wrong_path, tmp_path)
    other_root = tmp_path / "outside"
    other_root.mkdir()
    symlink_root = tmp_path / "symlink_repo"
    symlink_root.mkdir()
    protocol_root = symlink_root / "reports" / "protocol_v3"
    protocol_root.parent.mkdir(parents=True)
    try:
        protocol_root.symlink_to(other_root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable on this platform")
    with pytest.raises(ProtocolV3ReportError, match="symlink|escapes"):
        _write_at_clock(monkeypatch, _report(PROTOCOL_V3_RESEARCH, report_id="symlink_report"), symlink_root, datetime(2026, 7, 16, 10, tzinfo=UTC))


def test_duplicate_keys_nan_unknown_fields_and_noncanonical_bytes_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = _report(MONTHLY_PROCESS_OOS, report_id="strict_json")
    payload = report.to_dict()
    payload["evidence_status"]["live_eligible"] = True
    with pytest.raises(ProtocolV3ReportError, match="keys are invalid"):
        validate_protocol_v3_report(payload)
    root = tmp_path / REPORT_STORAGE_ROOTS[MONTHLY_PROCESS_OOS]
    root.mkdir(parents=True)
    duplicate_path = root / "duplicate.json"
    duplicate_path.write_text('{"schema_version":"protocol_v3_report_v1","schema_version":"protocol_v3_report_v1"}\n', encoding="utf-8")
    with pytest.raises(ProtocolV3ReportError, match="duplicate JSON key"):
        read_protocol_v3_report(duplicate_path, tmp_path)
    nan_path = root / "nan.json"
    nan_text = report.canonical_json.replace('"process_oos_net_usdc":1095.0', '"process_oos_net_usdc":NaN')
    nan_path.write_text(nan_text + "\n", encoding="utf-8")
    with pytest.raises(ProtocolV3ReportError, match="non-finite JSON constant"):
        read_protocol_v3_report(nan_path, tmp_path)
    pretty = _report(MONTHLY_PROCESS_OOS, report_id="pretty")
    pretty_path = root / "pretty.json"
    pretty_path.write_text(json.dumps(pretty.to_dict(), indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ProtocolV3ReportError, match="bytes are not canonical"):
        read_protocol_v3_report(pretty_path, tmp_path)


def test_registration_content_tampering_blocks_reload(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(reporting, "_utc_now", lambda: datetime(2026, 7, 1, tzinfo=UTC))
    registration = build_forward_window_registration(
        registration_id="tamper_registration",
        registered_at_utc="2026-07-01T00:00:00Z",
        start_inclusive_utc="2026-08-01T00:00:00Z",
        end_exclusive_utc="2026-09-01T00:00:00Z",
        pipeline_generation=PIPELINE_GENERATION,
        run_fingerprint=RUN_FINGERPRINT,
    )
    path = write_forward_window_registration(registration, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["end_exclusive_utc"] = "2026-10-01T00:00:00Z"
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(ProtocolV3ReportError, match="next UTC month boundary|digest mismatch"):
        read_forward_window_registration(path, tmp_path)


@pytest.mark.parametrize("kind", REPORT_KINDS)
def test_every_protocol_v3_report_is_rejected_by_legacy_final_and_adoption_paths(kind: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if kind == FORWARD_SHADOW_MONTH:
        _, report, path = _persisted_forward(monkeypatch, tmp_path)
    else:
        report = _report(kind, report_id=f"legacy_reject_{kind}")
        path = _write_at_clock(monkeypatch, report, tmp_path, datetime(2026, 7, 16, 10, tzinfo=UTC))
    with pytest.raises(ShadowAdoptionError):
        validate_final_evaluation_report(report.to_dict())
    with pytest.raises(ShadowAdoptionError):
        adopt_for_shadow(path, 100, tmp_path / "legacy_shadow_state")
    assert not (tmp_path / "legacy_shadow_state").exists()
