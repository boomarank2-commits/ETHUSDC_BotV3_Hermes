"""Contract tests for the versioned Protocol v3 adoption."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from ethusdc_bot.contracts.protocol_v3 import (
    CANONICAL_DOCUMENT,
    MANIFEST_PATH,
    ContractValidationError,
    load_protocol_v3_contract,
    validate_protocol_v3_contract,
    validate_repository_contracts,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DOCUMENTS = (
    Path("AGENTS.md"),
    Path("PROJECT_CONTRACT.md"),
    Path("docs/31_PORTFOLIO_SHADOW_PRODUCT_CONTRACT.md"),
    CANONICAL_DOCUMENT,
)


def _canonical_payload() -> dict:
    return json.loads((REPO_ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))


def _copy_contract_fixture(tmp_path: Path) -> Path:
    for relative in (*REQUIRED_DOCUMENTS, MANIFEST_PATH):
        source = REPO_ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return tmp_path


def test_repository_contract_is_versioned_and_consistent() -> None:
    payload = validate_repository_contracts(REPO_ROOT)

    assert payload["protocol_version"] == "3.0.0"
    assert payload["contract_generation"] == "monthly_refit_pipeline_v3"
    assert payload["consumed_audit"]["freshness"] == "NOT_FRESH"
    assert payload["consumed_audit"]["raw_market_observations_may_enter_later_causal_training"] is True
    assert payload["consumed_audit"]["prior_pnl_may_enter_later_training"] is False
    assert payload["evidence_classes"]["research_challenger_shadow"]["canonical_adoption_eligible"] is False
    assert payload["legacy_separation"]["single_candidate_final_path_may_emit_protocol_v3_final"] is False


def test_loader_rejects_missing_manifest(tmp_path: Path) -> None:
    with pytest.raises(ContractValidationError, match="manifest missing"):
        load_protocol_v3_contract(tmp_path / "missing.json")


def test_validator_rejects_missing_or_wrong_protocol_version() -> None:
    payload = _canonical_payload()
    payload.pop("protocol_version")
    with pytest.raises(ContractValidationError, match="protocol_version"):
        validate_protocol_v3_contract(payload)

    payload = _canonical_payload()
    payload["protocol_version"] = "2.0.0"
    with pytest.raises(ContractValidationError, match="protocol_version"):
        validate_protocol_v3_contract(payload)


def test_validator_rejects_consumed_audit_freshness_or_result_feedback() -> None:
    payload = _canonical_payload()
    payload["consumed_audit"]["freshness"] = "FRESH"
    with pytest.raises(ContractValidationError, match="consumed_audit.freshness"):
        validate_protocol_v3_contract(payload)

    payload = _canonical_payload()
    payload["consumed_audit"]["prior_rankings_may_enter_later_training"] = True
    with pytest.raises(
        ContractValidationError,
        match="consumed_audit.prior_rankings_may_enter_later_training",
    ):
        validate_protocol_v3_contract(payload)


def test_validator_rejects_tradable_or_adoptable_research_challenger() -> None:
    for key in (
        "orders",
        "trading_api",
        "canonical_adoption_eligible",
        "paper_testtrade_live_eligible",
    ):
        payload = _canonical_payload()
        payload["evidence_classes"]["research_challenger_shadow"][key] = True
        with pytest.raises(ContractValidationError, match=key):
            validate_protocol_v3_contract(payload)


def test_validator_rejects_legacy_protocol_v3_final_claim() -> None:
    payload = _canonical_payload()
    payload["legacy_separation"]["single_candidate_final_path_may_emit_protocol_v3_final"] = True
    with pytest.raises(
        ContractValidationError,
        match="single_candidate_final_path_may_emit_protocol_v3_final",
    ):
        validate_protocol_v3_contract(payload)


def test_repository_validator_rejects_missing_document_version_marker(tmp_path: Path) -> None:
    root = _copy_contract_fixture(tmp_path)
    project_contract = root / "PROJECT_CONTRACT.md"
    project_contract.write_text(
        project_contract.read_text(encoding="utf-8").replace(
            "Protocol-v3-Vertragsgeneration: `3.0.0`",
            "Protocol v3 ohne Version",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractValidationError, match="version marker missing"):
        validate_repository_contracts(root)


def test_repository_validator_rejects_missing_manifest_reference(tmp_path: Path) -> None:
    root = _copy_contract_fixture(tmp_path)
    agents = root / "AGENTS.md"
    agents.write_text(
        agents.read_text(encoding="utf-8").replace(
            "configs/protocol_v3_contract.json",
            "fehlendes-manifest.json",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractValidationError, match="manifest reference missing"):
        validate_repository_contracts(root)


def test_validator_does_not_mutate_input() -> None:
    payload = _canonical_payload()
    original = deepcopy(payload)

    validate_protocol_v3_contract(payload)

    assert payload == original
