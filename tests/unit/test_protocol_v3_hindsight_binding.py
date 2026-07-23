"""Focused Task-27 chain-integrity tests for bound hindsight evidence."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest

from ethusdc_bot.protocol_v3 import boundaries, hindsight_binding, hindsight_solvers


def _manifest_and_policies():
    plan = boundaries.build_monthly_process_boundary_plan("2026-07-08")
    policies = []
    origin_hashes = []
    bundles = []
    rotations = []
    fingerprints = []
    for origin in plan.origins:
        index = origin.origin_index
        origin_sha = f"{index:064x}"
        bundle_sha = f"{index + 20:064x}"
        rotation_sha = f"{index + 40:064x}"
        policy = hindsight_solvers.HindsightOriginPolicy(
            origin_index=index,
            start_inclusive_utc=datetime.combine(
                origin.test_start_inclusive, datetime.min.time(), UTC
            ),
            end_exclusive_utc=datetime.combine(
                origin.test_end_exclusive, datetime.min.time(), UTC
            ),
            valid_from_utc=origin.valid_from,
            origin_selection_sha256=origin_sha,
            candidate_bundle_sha256=bundle_sha,
            rotation_state_sha256=rotation_sha,
            max_roundtrips_per_utc_day=0,
            max_holding_minutes=0,
            entry_allowed=False,
        ).to_dict()
        policies.append(policy)
        origin_hashes.append(origin_sha)
        bundles.append(
            {
                "origin_index": index,
                "bundle_sha256": bundle_sha,
                "predecessor_bundle_sha256": None,
                "router_decision_sha256": f"{index + 60:064x}",
                "cost_model": {"contract_version": "baseline"},
                "validity": {
                    "as_of_utc": (
                        origin.valid_from.replace(hour=0) .isoformat(timespec="seconds")
                        .replace("+00:00", "Z")
                    ),
                    "valid_from_utc": policy["valid_from_utc"],
                    "valid_until_utc": policy["end_exclusive_utc"],
                },
            }
        )
        rotations.append(
            {
                "origin_index": index,
                "rotation_state_sha256": rotation_sha,
                "new_candidate_bundle_sha256": bundle_sha,
                "open_position": None,
                "entry_enabled_at_utc": policy["valid_from_utc"],
                "flat_time_utc": policy["start_inclusive_utc"],
                "retiring_configuration_mode": "retired",
                "new_configuration_mode": "waiting_for_valid_from",
                "monthly_boundary_liquidation": False,
            }
        )
        fingerprints.append(f"{index + 80:064x}")
    day_index = [
        {"day": day.isoformat(), "content_sha256": "a" * 64}
        for day in plan.iter_process_oos_days()
    ]
    manifest = {
        "ethusdc_process_day_index": day_index,
        "ethusdc_process_day_index_sha256": hindsight_binding._digest(day_index),
        "origin_hashes": origin_hashes,
        "origin_chain_sha256": hindsight_binding._digest(origin_hashes),
        "candidate_bundle_chain": bundles,
        "candidate_bundle_chain_sha256": hindsight_binding._digest(bundles),
        "rotation_state_chain": rotations,
        "rotation_state_chain_sha256": hindsight_binding._digest(rotations),
        "origin_run_fingerprint_sha256": fingerprints,
        "origin_run_fingerprint_chain_sha256": hindsight_binding._digest(
            fingerprints
        ),
    }
    return manifest, policies


def test_manifest_chains_accept_exact_bundle_origin_rotation_and_day_grid() -> None:
    manifest, policies = _manifest_and_policies()
    hindsight_binding._validate_manifest_chains(manifest, policies)


def test_rehashed_bundle_or_exit_only_handoff_manipulation_fails_closed() -> None:
    manifest, policies = _manifest_and_policies()
    bundle = deepcopy(manifest)
    bundle["candidate_bundle_chain"][0]["bundle_sha256"] = "f" * 64
    bundle["candidate_bundle_chain_sha256"] = hindsight_binding._digest(
        bundle["candidate_bundle_chain"]
    )
    with pytest.raises(hindsight_binding.HindsightBindingError, match="Task-22"):
        hindsight_binding._validate_manifest_chains(bundle, policies)

    handoff = deepcopy(manifest)
    handoff["rotation_state_chain"][0]["open_position"] = {
        "candidate_bundle_sha256": policies[0]["candidate_bundle_sha256"]
    }
    handoff["rotation_state_chain_sha256"] = hindsight_binding._digest(
        handoff["rotation_state_chain"]
    )
    with pytest.raises(hindsight_binding.HindsightBindingError, match="exit-only"):
        hindsight_binding._validate_manifest_chains(handoff, policies)


def test_rehashed_missing_or_duplicate_process_day_fails_closed() -> None:
    manifest, policies = _manifest_and_policies()
    changed = deepcopy(manifest)
    changed["ethusdc_process_day_index"][1]["day"] = changed[
        "ethusdc_process_day_index"
    ][0]["day"]
    changed["ethusdc_process_day_index_sha256"] = hindsight_binding._digest(
        changed["ethusdc_process_day_index"]
    )
    with pytest.raises(hindsight_binding.HindsightBindingError, match="missing"):
        hindsight_binding._validate_manifest_chains(changed, policies)
