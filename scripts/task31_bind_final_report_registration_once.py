from pathlib import Path

path = Path("src/ethusdc_bot/protocol_v3/pipeline_final_report.py")
text = path.read_text(encoding="utf-8")
replacements = [
    (
        '''from ethusdc_bot.protocol_v3.pipeline_final import (
    PipelineFinalClaim,
    PipelineFinalRegistration,
)
''',
        '''from ethusdc_bot.protocol_v3.pipeline_final import (
    PipelineFinalClaim,
    PipelineFinalRegistration,
    validate_pipeline_final_registration,
)
''',
    ),
    (
        '''def build_pipeline_final_report(
    attestation: PipelineFinalAttestation,
    *,
    created_at_utc: str,
) -> ProtocolV3Report:
''',
        '''def build_pipeline_final_report(
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
    *,
    created_at_utc: str,
) -> ProtocolV3Report:
''',
    ),
    (
        '''    attested = validate_pipeline_final_attestation(attestation)
    source = attested.to_dict()
''',
        '''    attested = validate_pipeline_final_attestation(attestation)
    registered = validate_pipeline_final_registration(registration)
    source = attested.to_dict()
    registration_payload = registered.to_dict()
    if (
        source["registration_id"] != registration_payload["registration_id"]
        or source["registration_sha256"] != registered.registration_sha256
    ):
        raise PipelineFinalReportError(
            "pipeline-final report registration differs from attestation"
        )
    manifest = dict(
        _mapping(
            registration_payload["frozen_identity_manifest"],
            "registration.frozen_identity_manifest",
        )
    )
''',
    ),
    (
        '''        "run_fingerprint": source["frozen_identity_manifest_sha256"] and source[
            "registration_sha256"
        ],
        "pipeline_generation": "",
''',
        '''        "run_fingerprint": manifest["run_fingerprint"],
        "pipeline_generation": manifest["pipeline_generation_id"],
''',
    ),
    (
        '''    # Run and pipeline identities are not duplicated in the attestation body; they
    # remain frozen in the persisted registration.  The opener injects them only
    # after re-reading that exact registration.
    return _validate_report_structure(basis)
''',
        '''    return _validate_report_structure(basis)
''',
    ),
    (
        '''    report = build_pipeline_final_report(attested, created_at_utc=opened_at_utc)
    report_payload = report.to_dict()
    report_payload["run_fingerprint"] = manifest["run_fingerprint"]
    report_payload["pipeline_generation"] = manifest["pipeline_generation_id"]
    report = _validate_report_structure(report_payload)
''',
        '''    report = build_pipeline_final_report(
        attested,
        registration,
        created_at_utc=opened_at_utc,
    )
''',
    ),
    (
        '''def validate_pipeline_final_report(
    value: ProtocolV3Report | Mapping[str, Any],
    *,
    attestation: PipelineFinalAttestation,
) -> ProtocolV3Report:
''',
        '''def validate_pipeline_final_report(
    value: ProtocolV3Report | Mapping[str, Any],
    *,
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
) -> ProtocolV3Report:
''',
    ),
    (
        '''    expected = build_pipeline_final_report(
        attested,
        created_at_utc=root["created_at_utc"],
    ).to_dict()
    expected["run_fingerprint"] = root["run_fingerprint"]
    expected["pipeline_generation"] = root["pipeline_generation"]
    expected_report = _validate_report_structure(expected)
''',
        '''    expected_report = build_pipeline_final_report(
        attested,
        registration,
        created_at_utc=root["created_at_utc"],
    )
''',
    ),
    (
        '''def read_pipeline_final_report(
    path: str | Path,
    repository_root: str | Path,
    *,
    attestation: PipelineFinalAttestation,
) -> ProtocolV3Report:
''',
        '''def read_pipeline_final_report(
    path: str | Path,
    repository_root: str | Path,
    *,
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
) -> ProtocolV3Report:
''',
    ),
    (
        '''    report = validate_pipeline_final_report(value, attestation=attestation)
''',
        '''    report = validate_pipeline_final_report(
        value,
        attestation=attestation,
        registration=registration,
    )
''',
    ),
    (
        '''def build_pipeline_final_open_receipt(
    attestation: PipelineFinalAttestation,
    report: ProtocolV3Report,
    *,
''',
        '''def build_pipeline_final_open_receipt(
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
    report: ProtocolV3Report,
    *,
''',
    ),
    (
        '''    validated_report = validate_pipeline_final_report(
        report,
        attestation=attested,
    )
''',
        '''    validated_report = validate_pipeline_final_report(
        report,
        attestation=attested,
        registration=registration,
    )
''',
    ),
    (
        '''def validate_pipeline_final_open_receipt(
    value: PipelineFinalOpenReceipt | Mapping[str, Any],
    *,
    attestation: PipelineFinalAttestation,
    report: ProtocolV3Report,
) -> PipelineFinalOpenReceipt:
''',
        '''def validate_pipeline_final_open_receipt(
    value: PipelineFinalOpenReceipt | Mapping[str, Any],
    *,
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
    report: ProtocolV3Report,
) -> PipelineFinalOpenReceipt:
''',
    ),
    (
        '''    validated_report = validate_pipeline_final_report(
        report,
        attestation=attestation,
    )
''',
        '''    validated_report = validate_pipeline_final_report(
        report,
        attestation=attestation,
        registration=registration,
    )
''',
    ),
    (
        '''def read_pipeline_final_open_receipt(
    path: str | Path,
    repository_root: str | Path,
    *,
    attestation: PipelineFinalAttestation,
    report: ProtocolV3Report,
) -> PipelineFinalOpenReceipt:
''',
        '''def read_pipeline_final_open_receipt(
    path: str | Path,
    repository_root: str | Path,
    *,
    attestation: PipelineFinalAttestation,
    registration: PipelineFinalRegistration,
    report: ProtocolV3Report,
) -> PipelineFinalOpenReceipt:
''',
    ),
    (
        '''        value,
        attestation=attestation,
        report=report,
    )
''',
        '''        value,
        attestation=attestation,
        registration=registration,
        report=report,
    )
''',
    ),
]
for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"final report registration replacement count={count}: {old[:90]!r}")
    text = text.replace(old, new)

call_replacements = [
    (
        '''            attestation=attested,
            report=report,
        )
''',
        '''            attestation=attested,
            registration=registration,
            report=report,
        )
''',
    ),
    (
        '''            report_path,
            repo,
            attestation=attested,
        )
''',
        '''            report_path,
            repo,
            attestation=attested,
            registration=registration,
        )
''',
    ),
    (
        '''        report_path,
        repo,
        attestation=attested,
    )
''',
        '''        report_path,
        repo,
        attestation=attested,
        registration=registration,
    )
''',
    ),
    (
        '''    receipt = build_pipeline_final_open_receipt(
        attested,
        report,
''',
        '''    receipt = build_pipeline_final_open_receipt(
        attested,
        registration,
        report,
''',
    ),
    (
        '''        receipt_path,
        repo,
        attestation=attested,
        report=report,
    )
''',
        '''        receipt_path,
        repo,
        attestation=attested,
        registration=registration,
        report=report,
    )
''',
    ),
    (
        '''        PipelineFinalOpenReceipt(_canonical(root), digest, receipt_id),
        attestation=attested,
        report=validated_report,
    )
''',
        '''        PipelineFinalOpenReceipt(_canonical(root), digest, receipt_id),
        attestation=attested,
        registration=registration,
        report=validated_report,
    )
''',
    ),
]
for old, new in call_replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"final report call replacement count={count}: {old[:90]!r}")
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
