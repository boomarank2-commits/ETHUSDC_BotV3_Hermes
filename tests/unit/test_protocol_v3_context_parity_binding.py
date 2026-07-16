"""Task-10 public-surface, pipeline, and fingerprint-binding regressions."""

from __future__ import annotations

import json
from pathlib import Path

import ethusdc_bot.protocol_v3 as protocol_v3
from ethusdc_bot.protocol_v3 import run_identity
from ethusdc_bot.protocol_v3.pipeline import (
    PIPELINE_CONTRACT_PATH,
    build_pipeline_generation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_task10_context_parity_is_public_and_pipeline_bound() -> None:
    assert (
        protocol_v3.CONTEXT_PARITY_CONTRACT_VERSION
        == "three_market_closed_bar_context_parity_v2"
    )
    assert callable(protocol_v3.build_context_parity_binding)
    assert callable(protocol_v3.evaluate_closed_bar_context)
    assert callable(protocol_v3.simulate_protocol_v3_context_path)

    basis = build_pipeline_generation(REPO_ROOT).basis()
    assert (
        basis["component_contracts"]["context_policy"]
        == "three_market_closed_bar_context_parity_v2"
    )
    assert (
        basis["component_contracts"]["simulator"]
        == "next_tradable_price_pessimistic_intrabar_with_fold_outer_state_and_context_parity_v2"
    )
    assert len(basis["component_source_sha256"]["context_policy"]) == 64
    assert len(basis["component_source_sha256"]["simulator"]) == 64

    contract = json.loads(
        (REPO_ROOT / PIPELINE_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    for component in ("context_policy", "simulator"):
        assert (
            "configs/protocol_v3_context_parity_contract.json"
            in contract["source_bindings"][component]
        )
        assert (
            "src/ethusdc_bot/protocol_v3/context_parity.py"
            in contract["source_bindings"][component]
        )


def test_context_component_is_an_explicit_run_fingerprint_identity() -> None:
    assert run_identity._COMPONENT_MAP["context"] == "context_policy"
    contract = run_identity.load_run_identity_contract(REPO_ROOT)
    required = contract["run_fingerprint_policy"]["required_identity_keys"]
    assert "raw_data" in required
    assert "context" in required
    assert contract["run_fingerprint_policy"]["resume_requires_exact_fingerprint"] is True
    assert contract["run_fingerprint_policy"]["cache_hit_requires_exact_fingerprint"] is True
