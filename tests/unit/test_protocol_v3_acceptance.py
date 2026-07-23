"""Task-32 acceptance contract, parity, and fail-closed receipt tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import acceptance
from ethusdc_bot.protocol_v3 import acceptance_api

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parity() -> dict[str, str]:
    contract = acceptance.load_acceptance_contract(REPO_ROOT)
    return {
        key: (
            "a" * 40
            if key == "code_commit"
            else "protocol_v3_pipeline_sha256:" + "b" * 64
            if key == "pipeline_generation_id"
            else "protocol_v3_run_sha256:" + "c" * 64
            if key == "run_fingerprint"
            else f"{index + 1:064x}"
        )
        for index, key in enumerate(contract["required_parity_identities"])
    }


def _snapshot(mode: str, *, parity: dict[str, str] | None = None):
    payload = {
        "schema_version": acceptance.SNAPSHOT_SCHEMA_VERSION,
        "protocol_version": acceptance.PROTOCOL_VERSION,
        "contract_version": acceptance.CONTRACT_VERSION,
        "mode": mode,
        "fixture_only": True,
        "fixture_repository_sha256": "d" * 64,
        "parity_identities": parity or _parity(),
        "checkpoint_sha256": "e" * 64,
        "origin_count": 12,
        "process_oos_days": 365,
        "freshness": "FIXTURE_ONLY",
        "diagnostic_only": True,
        "real_final_evidence": False,
        "task33_research_run": False,
        "safety": acceptance._SAFETY,
    }
    return acceptance.validate_acceptance_path_snapshot(payload)


def test_contract_api_and_pipeline_binding_are_exact() -> None:
    contract = acceptance.load_acceptance_contract(REPO_ROOT)
    assert contract["contract_version"] == acceptance.CONTRACT_VERSION
    assert contract["execution_modes"] == list(acceptance.EXECUTION_MODES)
    assert contract["fixture_isolation"]["real_final_evidence"] is False
    assert acceptance_api.__all__ == acceptance.__all__
    pipeline = json.loads(
        (REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text()
    )
    assert acceptance.CONTRACT_VERSION in pipeline["component_contracts"]["quality_gates"]
    for path in (
        "configs/protocol_v3_acceptance_contract.json",
        "src/ethusdc_bot/protocol_v3/acceptance.py",
        "src/ethusdc_bot/protocol_v3/acceptance_api.py",
    ):
        assert path in pipeline["source_bindings"]["quality_gates"]


def test_four_bit_identical_paths_create_fixture_only_acceptance() -> None:
    parity = _parity()
    snapshots = [_snapshot(mode, parity=parity) for mode in acceptance.EXECUTION_MODES]
    ui = {"screen": "protocol_v3", "refresh_count_is_state": False}
    receipt = acceptance.build_task32_acceptance_receipt(
        snapshots,
        observed_fault_matrix=acceptance._FAULT_MATRIX,
        ui_state_before=ui,
        ui_state_after=deepcopy(ui),
    )
    payload = acceptance.validate_task32_acceptance_receipt(receipt).to_dict()
    assert payload["status"] == "DONE_100_FIXTURE_ACCEPTANCE"
    assert payload["origin_count"] == 12
    assert payload["process_oos_days"] == 365
    assert payload["freshness"] == "FIXTURE_ONLY"
    assert payload["real_final_evidence"] is False
    assert payload["canonical_adoption_eligible"] is False
    assert payload["bot_start_allowed"] is False
    assert payload["task33_research_run"] is False


def test_changed_path_identity_and_reordered_modes_fail_closed() -> None:
    parity = _parity()
    changed = dict(parity)
    changed["cost_contract_sha256"] = "f" * 64
    rows = [_snapshot(mode, parity=parity) for mode in acceptance.EXECUTION_MODES]
    rows[-1] = _snapshot(acceptance.EXECUTION_MODES[-1], parity=changed)
    with pytest.raises(acceptance.ProtocolV3AcceptanceError, match="bit-identical"):
        acceptance.build_task32_acceptance_receipt(
            rows,
            observed_fault_matrix=acceptance._FAULT_MATRIX,
            ui_state_before={},
            ui_state_after={},
        )
    with pytest.raises(acceptance.ProtocolV3AcceptanceError, match="missing or reordered"):
        acceptance.build_task32_acceptance_receipt(
            list(reversed([_snapshot(mode) for mode in acceptance.EXECUTION_MODES])),
            observed_fault_matrix=acceptance._FAULT_MATRIX,
            ui_state_before={},
            ui_state_after={},
        )


def test_incomplete_fault_matrix_or_ui_mutation_fails_closed() -> None:
    rows = [_snapshot(mode) for mode in acceptance.EXECUTION_MODES]
    faults = deepcopy(acceptance._FAULT_MATRIX)
    faults["identity_mutation"] = faults["identity_mutation"][:-1]
    with pytest.raises(acceptance.ProtocolV3AcceptanceError, match="fault matrix"):
        acceptance.build_task32_acceptance_receipt(
            rows,
            observed_fault_matrix=faults,
            ui_state_before={},
            ui_state_after={},
        )
    with pytest.raises(acceptance.ProtocolV3AcceptanceError, match="mutated"):
        acceptance.build_task32_acceptance_receipt(
            rows,
            observed_fault_matrix=acceptance._FAULT_MATRIX,
            ui_state_before={"state": "before"},
            ui_state_after={"state": "after"},
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fixture_only", False),
        ("freshness", "FRESH_SEALED_FINAL"),
        ("diagnostic_only", False),
        ("real_final_evidence", True),
        ("task33_research_run", True),
    ],
)
def test_rehashed_fixture_safety_claims_are_rejected(field: str, value: object) -> None:
    payload = _snapshot("FIRST_RUN").to_dict()
    payload[field] = value
    with pytest.raises(acceptance.ProtocolV3AcceptanceError, match="fixture safety"):
        acceptance.validate_acceptance_path_snapshot(payload)


def test_contract_mutation_and_nonfinite_ui_fail_closed() -> None:
    contract = acceptance.load_acceptance_contract(REPO_ROOT)
    changed = deepcopy(contract)
    changed["fixture_isolation"]["real_final_evidence"] = True
    with pytest.raises(acceptance.ProtocolV3AcceptanceError, match="not canonical"):
        acceptance.validate_acceptance_contract(changed)
    rows = [_snapshot(mode) for mode in acceptance.EXECUTION_MODES]
    with pytest.raises(acceptance.ProtocolV3AcceptanceError, match="non-finite"):
        acceptance.build_task32_acceptance_receipt(
            rows,
            observed_fault_matrix=acceptance._FAULT_MATRIX,
            ui_state_before={"bad": float("nan")},
            ui_state_after={"bad": float("nan")},
        )


def test_rehashed_fault_digest_cannot_validate() -> None:
    rows = [_snapshot(mode) for mode in acceptance.EXECUTION_MODES]
    receipt = acceptance.build_task32_acceptance_receipt(
        rows,
        observed_fault_matrix=acceptance._FAULT_MATRIX,
        ui_state_before={},
        ui_state_after={},
    )
    forged = receipt.to_dict()
    forged["fault_matrix_sha256"] = "0" * 64
    with pytest.raises(acceptance.ProtocolV3AcceptanceError, match="fault matrix digest"):
        acceptance.validate_task32_acceptance_receipt(forged)
