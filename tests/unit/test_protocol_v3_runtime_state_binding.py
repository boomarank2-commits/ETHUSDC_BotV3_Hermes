"""Task-9 public-surface and pipeline identity regression tests."""

from __future__ import annotations

import json
from pathlib import Path

import ethusdc_bot.protocol_v3 as protocol_v3
from ethusdc_bot.protocol_v3.pipeline import (
    PIPELINE_CONTRACT_PATH,
    build_pipeline_generation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_task9_runtime_state_is_public_and_pipeline_bound() -> None:
    assert protocol_v3.RUNTIME_STATE_CONTRACT_VERSION == "warmup_purge_fold_outer_state_v1"
    assert callable(protocol_v3.build_outer_rotation_state)
    assert callable(protocol_v3.finalize_inner_fold)
    assert callable(protocol_v3.purge_training_events)

    basis = build_pipeline_generation(REPO_ROOT).basis()
    assert (
        basis["component_contracts"]["boundary_rules"]
        == "protocol_v3_monthly_boundary_and_runtime_state_v1"
    )
    assert (
        basis["component_contracts"]["simulator"]
        == "next_tradable_price_pessimistic_intrabar_with_fold_outer_state_v1"
    )
    assert len(basis["component_source_sha256"]["boundary_rules"]) == 64
    assert len(basis["component_source_sha256"]["simulator"]) == 64

    contract = json.loads(
        (REPO_ROOT / PIPELINE_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    for component in ("boundary_rules", "simulator"):
        assert (
            "configs/protocol_v3_runtime_state_contract.json"
            in contract["source_bindings"][component]
        )
        assert (
            "src/ethusdc_bot/protocol_v3/runtime_state.py"
            in contract["source_bindings"][component]
        )


def test_task8_intrabar_contract_remains_separate_and_bound() -> None:
    assert (
        protocol_v3.INTRABAR_EXECUTION_CONTRACT_VERSION
        == "next_tradable_price_pessimistic_intrabar_v1"
    )
    contract = json.loads(
        (REPO_ROOT / PIPELINE_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    assert (
        "configs/protocol_v3_intrabar_execution_contract.json"
        in contract["source_bindings"]["simulator"]
    )
    assert (
        "src/ethusdc_bot/protocol_v3/intrabar_execution.py"
        in contract["source_bindings"]["simulator"]
    )
