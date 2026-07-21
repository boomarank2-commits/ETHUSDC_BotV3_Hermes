from pathlib import Path

checkpoint_path = Path("src/ethusdc_bot/protocol_v3/pipeline_final_checkpoint.py")
checkpoint = checkpoint_path.read_text(encoding="utf-8")
replacements = [
    (
        '''def commit_pipeline_final_checkpoint(
    receipt: PipelineFinalCheckpointReceipt,
    *,
    identity: TransactionIdentity,
''',
        '''def commit_pipeline_final_checkpoint(
    receipt: PipelineFinalCheckpointReceipt,
    *,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
    identity: TransactionIdentity,
''',
    ),
    (
        '''    validated = validate_pipeline_final_checkpoint_receipt(receipt)
    _assert_receipt_identity(validated, identity, repository_root)
''',
        '''    validated = validate_pipeline_final_checkpoint_receipt(receipt)
    _assert_receipt_sources(validated, registration, claim)
    _assert_receipt_identity(validated, identity, repository_root)
''',
    ),
    (
        '''def read_pipeline_final_checkpoint(
    *,
    current_identity: TransactionIdentity,
''',
        '''def read_pipeline_final_checkpoint(
    *,
    current_registration: PipelineFinalRegistration,
    current_claim: PipelineFinalClaim,
    current_identity: TransactionIdentity,
''',
    ),
    (
        '''    receipt = validate_pipeline_final_checkpoint_receipt(
        payload["task31_pipeline_final_checkpoint_receipt"]
    )
    _assert_receipt_identity(receipt, current_identity, repository_root)
''',
        '''    receipt = validate_pipeline_final_checkpoint_receipt(
        payload["task31_pipeline_final_checkpoint_receipt"]
    )
    _assert_receipt_sources(receipt, current_registration, current_claim)
    _assert_receipt_identity(receipt, current_identity, repository_root)
''',
    ),
]
for old, new in replacements:
    if checkpoint.count(old) != 1:
        raise SystemExit(f"checkpoint replacement mismatch: {old[:80]!r}")
    checkpoint = checkpoint.replace(old, new)

identity_anchor = '''def _assert_receipt_identity(
    receipt: PipelineFinalCheckpointReceipt,
    identity: TransactionIdentity,
    repository_root: str | Path,
) -> None:
'''
source_validator = '''def _assert_receipt_sources(
    receipt: PipelineFinalCheckpointReceipt,
    registration: PipelineFinalRegistration,
    claim: PipelineFinalClaim,
) -> None:
    expected = validate_pipeline_final_checkpoint_receipt(receipt).to_dict()
    registration_payload = validate_pipeline_final_registration(registration).to_dict()
    claim_payload = validate_pipeline_final_claim(claim).to_dict()
    if (
        claim_payload["registration_id"] != registration_payload["registration_id"]
        or claim_payload["registration_sha256"]
        != registration.registration_sha256
        or claim_payload["result_opened"] is not False
    ):
        raise PipelineFinalCheckpointError(
            "Task-31 claim belongs to another registration or is already opened"
        )
    manifest = registration_payload["frozen_identity_manifest"]
    source_identity = {
        "registration_id": registration_payload["registration_id"],
        "registration_sha256": registration.registration_sha256,
        "claim_id": claim.claim_id,
        "claim_sha256": claim.claim_sha256,
        "frozen_identity_manifest_sha256": registration_payload[
            "frozen_identity_manifest_sha256"
        ],
        "run_fingerprint": manifest["run_fingerprint"],
        "pipeline_generation_id": manifest["pipeline_generation_id"],
        "code_commit": manifest["code_commit"],
        "trial_ledger_head_sha256": manifest["trial_ledger_head_sha256"],
    }
    if any(expected[key] != value for key, value in source_identity.items()):
        raise PipelineFinalCheckpointError(
            "Task-31 checkpoint receipt uses another registration or claim"
        )


'''
if checkpoint.count(identity_anchor) != 1:
    raise SystemExit("checkpoint source-validator insertion anchor mismatch")
checkpoint = checkpoint.replace(identity_anchor, source_validator + identity_anchor)
checkpoint_path.write_text(checkpoint, encoding="utf-8")

progress_test_path = Path("tests/unit/test_protocol_v3_pipeline_final_progress.py")
progress_test = progress_test_path.read_text(encoding="utf-8")
old_progress = '''    first = _append(progress, selections[0], 1, state=state)
    earlier_than_first = f"{plan.origins[0].test_end_exclusive.isoformat()}T00:00:00Z"
    with pytest.raises(PipelineFinalProgressError, match="monotonic"):
        _append(first, selections[1], 2, state=state, completed=earlier_than_first)
'''
new_progress = '''    delayed_first_dt = datetime.combine(
        plan.origins[1].test_end_exclusive,
        datetime.min.time(),
        tzinfo=UTC,
    ) + timedelta(days=1)
    first = _append(
        progress,
        selections[0],
        1,
        state=state,
        completed=_fmt(delayed_first_dt),
    )
    earlier_than_first = f"{plan.origins[1].test_end_exclusive.isoformat()}T00:00:00Z"
    with pytest.raises(PipelineFinalProgressError, match="monotonic"):
        _append(first, selections[1], 2, state=state, completed=earlier_than_first)
'''
if progress_test.count(old_progress) != 1:
    raise SystemExit("progress monotonic fixture replacement mismatch")
progress_test_path.write_text(
    progress_test.replace(old_progress, new_progress), encoding="utf-8"
)

checkpoint_test_path = Path("tests/unit/test_protocol_v3_pipeline_final_checkpoint.py")
test = checkpoint_test_path.read_text(encoding="utf-8")n
