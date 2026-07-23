"""Stable public facade for the transitive Protocol-v3 Task-31 attestation."""
from ethusdc_bot.protocol_v3.pipeline_final_attestation import (
    ATTESTATION_CONTRACT_VERSION,
    ATTESTATION_ROOT,
    ATTESTATION_SCHEMA_VERSION,
    PipelineFinalAttestation,
    PipelineFinalAttestationError,
    build_pipeline_final_attestation,
    read_pipeline_final_attestation,
    validate_pipeline_final_attestation,
    write_pipeline_final_attestation,
)

__all__ = [
    "ATTESTATION_CONTRACT_VERSION",
    "ATTESTATION_ROOT",
    "ATTESTATION_SCHEMA_VERSION",
    "PipelineFinalAttestation",
    "PipelineFinalAttestationError",
    "build_pipeline_final_attestation",
    "read_pipeline_final_attestation",
    "validate_pipeline_final_attestation",
    "write_pipeline_final_attestation",
]
