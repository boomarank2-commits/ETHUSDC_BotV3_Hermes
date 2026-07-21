from pathlib import Path
import json

pipeline_final_path = Path("src/ethusdc_bot/protocol_v3/pipeline_final.py")
text = pipeline_final_path.read_text(encoding="utf-8")
replacements = [
    (
        'CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_pipeline_final_contract_v1"\n',
        'CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_pipeline_final_contract_v2"\n',
    ),
    (
        'CONTRACT_VERSION: Final = "protocol_v3_preregistered_single_open_pipeline_final_v1"\n',
        'CONTRACT_VERSION: Final = (\n    "protocol_v3_preregistered_transitively_attested_exactly_once_"\n    "pipeline_final_v2"\n)\n',
    ),
    (
        '''    "registration_schema_version": REGISTRATION_SCHEMA_VERSION,
    "claim_schema_version": CLAIM_SCHEMA_VERSION,
    "roots": {
        "registration_root": REGISTRATION_ROOT,
        "claim_root": CLAIM_ROOT,
    },
''',
        '''    "registration_schema_version": REGISTRATION_SCHEMA_VERSION,
    "claim_schema_version": CLAIM_SCHEMA_VERSION,
    "progress_schema_version": "protocol_v3_pipeline_final_progress_v1",
    "checkpoint_receipt_schema_version": (
        "protocol_v3_pipeline_final_checkpoint_receipt_v1"
    ),
    "attestation_schema_version": "protocol_v3_pipeline_final_attestation_v1",
    "final_report_schema_version": "protocol_v3_report_v1",
    "open_receipt_schema_version": (
        "protocol_v3_pipeline_final_open_receipt_v1"
    ),
    "roots": {
        "registration_root": REGISTRATION_ROOT,
        "claim_root": CLAIM_ROOT,
        "attestation_root": (
            "reports/protocol_v3/pipeline_final/attestations"
        ),
        "final_report_root": "reports/protocol_v3/pipeline_final",
        "open_receipt_root": (
            "reports/protocol_v3/pipeline_final_open_receipts"
        ),
    },
''',
    ),
    (
        '''        "task31_attestation_required_before_open": True,
        "open_exactly_once_after_complete": True,
    },
''',
        '''        "task31_attestation_required_before_open": True,
        "attestation_transitively_revalidates_tasks_23_25_26_27": True,
        "final_report_contract_version": (
            "protocol_v3_exactly_once_pipeline_final_report_open_v1"
        ),
        "open_exactly_once_after_complete": True,
        "report_written_before_open_receipt": True,
        "exact_report_without_receipt_is_crash_recoverable": True,
        "second_open_after_receipt_forbidden": True,
        "result_feedback_to_pipeline_forbidden": True,
    },
''',
    ),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"pipeline-final contract source replacement mismatch: {old[:90]!r}")
    text = text.replace(old, new)
pipeline_final_path.write_text(text, encoding="utf-8")

config_path = Path("configs/protocol_v3_pipeline_final_contract.json")
config = json.loads(config_path.read_text(encoding="utf-8"))
config["schema_version"] = "protocol_v3_pipeline_final_contract_v2"
config["contract_version"] = (
    "protocol_v3_preregistered_transitively_attested_exactly_once_pipeline_final_v2"
)
config["progress_schema_version"] = "protocol_v3_pipeline_final_progress_v1"
config["checkpoint_receipt_schema_version"] = (
    "protocol_v3_pipeline_final_checkpoint_receipt_v1"
)
config["attestation_schema_version"] = "protocol_v3_pipeline_final_attestation_v1"
config["final_report_schema_version"] = "protocol_v3_report_v1"
config["open_receipt_schema_version"] = (
    "protocol_v3_pipeline_final_open_receipt_v1"
)
config["roots"] = {
    "registration_root": "reports/protocol_v3/evidence_windows/pipeline_final",
    "claim_root": "reports/protocol_v3/pipeline_final_claims",
    "attestation_root": "reports/protocol_v3/pipeline_final/attestations",
    "final_report_root": "reports/protocol_v3/pipeline_final",
    "open_receipt_root": "reports/protocol_v3/pipeline_final_open_receipts",
}
config["sealing_policy"].update(
    {
        "attestation_transitively_revalidates_tasks_23_25_26_27": True,
        "final_report_contract_version": (
            "protocol_v3_exactly_once_pipeline_final_report_open_v1"
        ),
        "report_written_before_open_receipt": True,
        "exact_report_without_receipt_is_crash_recoverable": True,
        "second_open_after_receipt_forbidden": True,
        "result_feedback_to_pipeline_forbidden": True,
    }
)
config_path.write_text(json.dumps(config, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

contract_test_path = Path("tests/unit/test_protocol_v3_pipeline_final.py")
test = contract_test_path.read_text(encoding="utf-8")
old_version = '''    assert contract["contract_version"] == (
        "protocol_v3_preregistered_single_open_pipeline_final_v1"
    )
'''
new_version = '''    assert contract["contract_version"] == (
        "protocol_v3_preregistered_transitively_attested_exactly_once_"
        "pipeline_final_v2"
    )
'''
if test.count(old_version) != 1:
    raise SystemExit("pipeline-final contract test version replacement mismatch")
test = test.replace(old_version, new_version)
assertion_anchor = '''    assert contract["sealing_policy"]["intermediate_outer_pnl_visible"] is False
'''
extra = assertion_anchor + '''    assert contract["roots"]["attestation_root"] == (
        "reports/protocol_v3/pipeline_final/attestations"
    )
    assert contract["roots"]["final_report_root"] == (
        "reports/protocol_v3/pipeline_final"
    )
    assert contract["roots"]["open_receipt_root"] == (
        "reports/protocol_v3/pipeline_final_open_receipts"
    )
    assert contract["sealing_policy"][
        "attestation_transitively_revalidates_tasks_23_25_26_27"
    ] is True
    assert contract["sealing_policy"]["second_open_after_receipt_forbidden"] is True
'''
if test.count(assertion_anchor) != 1:
    raise SystemExit("pipeline-final contract test assertion anchor mismatch")
test = test.replace(assertion_anchor, extra)
contract_test_path.write_text(test, encoding="utf-8")

pipeline_contract_path = Path("configs/protocol_v3_pipeline_contract.json")
pipeline = json.loads(pipeline_contract_path.read_text(encoding="utf-8"))
versions = pipeline["component_contracts"]["quality_gates"]
for old in (
    "protocol_v3_preregistered_single_open_pipeline_final_v1",
):
    if old in versions:
        versions.remove(old)
for version in (
    "protocol_v3_preregistered_transitively_attested_exactly_once_pipeline_final_v2",
    "protocol_v3_exactly_once_pipeline_final_report_open_v1",
):
    if version not in versions:
        versions.append(version)
sources = pipeline["source_bindings"]["quality_gates"]
for source in (
    "src/ethusdc_bot/protocol_v3/pipeline_final_report.py",
    "src/ethusdc_bot/protocol_v3/pipeline_final_report_api.py",
):
    if source not in sources:
        sources.append(source)
pipeline_contract_path.write_text(
    json.dumps(pipeline, indent=2, ensure_ascii=True) + "\n",
    encoding="utf-8",
)
