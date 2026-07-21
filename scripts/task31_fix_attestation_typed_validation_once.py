from pathlib import Path

path = Path("src/ethusdc_bot/protocol_v3/pipeline_final_attestation.py")
text = path.read_text(encoding="utf-8")
old_build = '''    digest = _digest(basis)
    return validate_pipeline_final_attestation(
        {
            **basis,
            "attestation_id": f"protocol_v3_pipeline_final_attestation_sha256:{digest}",
            "attestation_sha256": digest,
        }
    )
'''
new_build = '''    digest = _digest(basis)
    attestation_id = f"protocol_v3_pipeline_final_attestation_sha256:{digest}"
    candidate = PipelineFinalAttestation(
        _canonical(
            {
                **basis,
                "attestation_id": attestation_id,
                "attestation_sha256": digest,
            }
        ),
        digest,
        attestation_id,
    )
    return validate_pipeline_final_attestation(candidate)
'''
if text.count(old_build) != 1:
    raise SystemExit("attestation builder typed-validation replacement mismatch")
text = text.replace(old_build, new_build)
old_read = '''    value, raw = _read(guarded)
    attestation = validate_pipeline_final_attestation(value)
'''
new_read = '''    value, raw = _read(guarded)
    candidate = PipelineFinalAttestation(
        _canonical(value),
        str(value.get("attestation_sha256", "")),
        str(value.get("attestation_id", "")),
    )
    attestation = validate_pipeline_final_attestation(candidate)
'''
if text.count(old_read) != 1:
    raise SystemExit("attestation reader typed-validation replacement mismatch")
path.write_text(text.replace(old_read, new_read), encoding="utf-8")
