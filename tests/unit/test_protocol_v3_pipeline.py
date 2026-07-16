"""Protocol v3 task-3 tests for identity, seeds, budgets, and stop rules."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import pytest

from ethusdc_bot.protocol_v3.boundaries import build_monthly_process_boundary_plan
from ethusdc_bot.protocol_v3.pipeline import (
    PIPELINE_CONTRACT_PATH,
    BudgetUsage,
    PipelineContractError,
    PipelineGeneration,
    PreRunManifest,
    SearchBudgetPolicy,
    build_pipeline_generation,
    build_pre_run_manifest,
    derive_seed,
    origin_cycle_seed,
    stagnation_stop_reason,
    validate_actual_cycle_counts,
    validate_budget_usage,
    validate_pipeline_contract,
    validate_pipeline_generation,
    validate_pre_run_manifest,
)
from ethusdc_bot.contracts.protocol_v3 import MANIFEST_PATH, REQUIRED_DOCUMENTS

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40


def _copy_pipeline_sources(tmp_path: Path) -> Path:
    contract_source = REPO_ROOT / PIPELINE_CONTRACT_PATH
    contract = json.loads(contract_source.read_text(encoding="utf-8"))
    target_contract = tmp_path / PIPELINE_CONTRACT_PATH
    target_contract.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(contract_source, target_contract)
    for paths in contract["source_bindings"].values():
        for relative in paths:
            source = REPO_ROOT / relative
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(source, target)
    for relative in (MANIFEST_PATH, *REQUIRED_DOCUMENTS):
        source = REPO_ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(source, target)
    return tmp_path


def _manifest() -> tuple[PipelineGeneration, PreRunManifest]:
    generation = build_pipeline_generation(REPO_ROOT)
    plan = build_monthly_process_boundary_plan("2026-07-08")
    return generation, build_pre_run_manifest(generation, plan, code_commit=COMMIT)


def _all_object_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_all_object_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_all_object_keys(item))
    return keys


def test_task2_boundary_contract_remains_valid_before_task3_identity() -> None:
    plan = build_monthly_process_boundary_plan("2026-07-08")
    assert len(plan.origins) == 12
    assert len(plan.iter_process_oos_days()) == 365
    assert all(origin.training_day_count == 730 for origin in plan.origins)


def test_pipeline_generation_is_deterministic_and_binds_all_components() -> None:
    first = build_pipeline_generation(REPO_ROOT)
    second = build_pipeline_generation(REPO_ROOT)

    assert first == second
    assert first.generation_id.startswith("protocol_v3_pipeline_sha256:")
    assert len(first.generation_id.rsplit(":", 1)[1]) == 64
    basis = first.basis()
    expected_components = {
        "boundary_rules",
        "candidate_families",
        "context_policy",
        "cost_model",
        "feature_contract",
        "quality_gates",
        "ranking",
        "search_space",
        "simulator",
    }
    assert set(basis["component_contracts"]) == expected_components
    assert set(basis["component_source_sha256"]) == expected_components
    assert basis["budget_policy"] == SearchBudgetPolicy.canonical().to_dict()
    assert basis["target_policy"]["target_is_search_loss"] is False
    assert basis["target_policy"]["target_hit_may_stop_search"] is False
    assert set(basis["governing_contract_source_sha256"]) == {
        relative.as_posix() for relative in (MANIFEST_PATH, *REQUIRED_DOCUMENTS)
    }


def test_bound_source_change_creates_new_generation_and_only_new_forward_namespace(
    tmp_path: Path,
) -> None:
    root = _copy_pipeline_sources(tmp_path)
    first = build_pipeline_generation(root)
    feature_path = root / "src/ethusdc_bot/backtest/features.py"
    feature_path.write_bytes(feature_path.read_bytes() + b"\n# changed\n")
    second = build_pipeline_generation(root)

    assert second.generation_id != first.generation_id
    assert second.forward_ledger_namespace != first.forward_ledger_namespace
    assert (
        second.permanent_trial_counter_namespace
        == first.permanent_trial_counter_namespace
        == "protocol_v3_permanent_trial_counter_v1"
    )


def test_missing_bound_source_blocks_generation_fail_closed(tmp_path: Path) -> None:
    root = _copy_pipeline_sources(tmp_path)
    (root / "src/ethusdc_bot/backtest/features.py").unlink()
    with pytest.raises(PipelineContractError, match="missing or unreadable"):
        build_pipeline_generation(root)


def test_missing_or_contradictory_governing_contract_blocks_generation(
    tmp_path: Path,
) -> None:
    root = _copy_pipeline_sources(tmp_path)
    (root / MANIFEST_PATH).unlink()
    with pytest.raises(PipelineContractError, match="repository contract is invalid"):
        build_pipeline_generation(root)

    root = _copy_pipeline_sources(tmp_path)
    agents_path = root / "AGENTS.md"
    agents_path.write_text(
        agents_path.read_text(encoding="utf-8").replace(
            "Protocol-v3-Vertragsgeneration: `3.0.0`",
            "Protocol-v3-Vertragsgeneration: `2.0.0`",
        ),
        encoding="utf-8",
    )
    with pytest.raises(PipelineContractError, match="version marker"):
        build_pipeline_generation(root)


def test_governing_contract_change_creates_a_new_pipeline_generation(
    tmp_path: Path,
) -> None:
    root = _copy_pipeline_sources(tmp_path)
    first = build_pipeline_generation(root)
    project_contract = root / "PROJECT_CONTRACT.md"
    project_contract.write_bytes(project_contract.read_bytes() + b"\n<!-- clarified -->\n")
    second = build_pipeline_generation(root)

    assert second.generation_id != first.generation_id
    assert second.forward_ledger_namespace != first.forward_ledger_namespace


def test_pipeline_contract_rejects_budget_stop_target_and_ledger_relaxation() -> None:
    contract = json.loads(
        (REPO_ROOT / PIPELINE_CONTRACT_PATH).read_text(encoding="utf-8")
    )

    changed = json.loads(json.dumps(contract))
    changed["budget_policy"]["generated_per_cycle"] = 41
    with pytest.raises(PipelineContractError, match="budget policy"):
        validate_pipeline_contract(changed)

    changed = json.loads(json.dumps(contract))
    changed["stop_policy"]["may_expand_budget"] = True
    with pytest.raises(PipelineContractError, match="stop policy"):
        validate_pipeline_contract(changed)

    changed = json.loads(json.dumps(contract))
    changed["target_policy"]["target_hit_may_stop_search"] = True
    with pytest.raises(PipelineContractError, match="target policy"):
        validate_pipeline_contract(changed)

    changed = json.loads(json.dumps(contract))
    changed["ledger_policy"]["new_generation_resets_permanent_trial_counter"] = True
    with pytest.raises(PipelineContractError, match="ledger reset"):
        validate_pipeline_contract(changed)


def test_pipeline_contract_rejects_path_escape_and_missing_component() -> None:
    contract = json.loads(
        (REPO_ROOT / PIPELINE_CONTRACT_PATH).read_text(encoding="utf-8")
    )
    escaped = json.loads(json.dumps(contract))
    escaped["source_bindings"]["feature_contract"] = ["../features.py"]
    with pytest.raises(PipelineContractError, match="inside the repository"):
        validate_pipeline_contract(escaped)

    missing = json.loads(json.dumps(contract))
    del missing["component_contracts"]["ranking"]
    with pytest.raises(PipelineContractError, match="every required"):
        validate_pipeline_contract(missing)


def test_budget_policy_contains_exact_per_cycle_and_global_maxima() -> None:
    policy = SearchBudgetPolicy.canonical()
    policy.validate()
    assert policy.outer_origins == 12
    assert policy.max_cycles_per_origin == 8
    assert (
        policy.generated_per_cycle,
        policy.tested_per_cycle,
        policy.walk_forward_per_cycle,
        policy.finalists_per_cycle,
    ) == (40, 12, 3, 2)
    assert (
        policy.max_total_cycles,
        policy.max_total_generated,
        policy.max_total_tested,
        policy.max_total_walk_forward,
        policy.max_total_finalists,
    ) == (96, 3840, 1152, 288, 192)


def test_budget_reservations_cannot_exceed_per_origin_or_global_caps() -> None:
    policy = SearchBudgetPolicy.canonical()
    usage = BudgetUsage()
    for origin_index in range(1, 13):
        for _ in range(8):
            usage = usage.reserve_next_cycle(origin_index, policy)

    validate_budget_usage(usage, policy)
    assert usage.total_cycles == 96
    assert usage.reserved_generated == 3840
    assert usage.reserved_tested == 1152
    assert usage.reserved_walk_forward == 288
    assert usage.reserved_finalists == 192
    with pytest.raises(PipelineContractError, match="8-cycle cap"):
        usage.reserve_next_cycle(1, policy)


def test_budget_usage_rejects_forged_or_noncanonical_reservations() -> None:
    policy = SearchBudgetPolicy.canonical()
    usage = BudgetUsage().reserve_next_cycle(1, policy)
    with pytest.raises(PipelineContractError, match="does not match"):
        validate_budget_usage(replace(usage, reserved_generated=39), policy)
    with pytest.raises(PipelineContractError, match="twelve origin"):
        validate_budget_usage(replace(usage, cycles_by_origin=(1,)), policy)
    with pytest.raises(PipelineContractError, match="canonical"):
        replace(policy, max_cycles_per_origin=9).validate()


def test_actual_cycle_counts_are_nested_and_never_above_40_12_3_2() -> None:
    validate_actual_cycle_counts(generated=40, tested=12, walk_forward=3, finalists=2)
    validate_actual_cycle_counts(generated=10, tested=5, walk_forward=2, finalists=1)
    with pytest.raises(PipelineContractError, match="40/12/3/2"):
        validate_actual_cycle_counts(generated=41, tested=12, walk_forward=3, finalists=2)
    with pytest.raises(PipelineContractError, match="nested"):
        validate_actual_cycle_counts(generated=10, tested=11, walk_forward=3, finalists=2)
    with pytest.raises(PipelineContractError, match="non-negative"):
        validate_actual_cycle_counts(generated=10, tested=5, walk_forward=2, finalists=-1)


def test_stagnation_can_only_shorten_and_never_expand_budget() -> None:
    policy = SearchBudgetPolicy.canonical()
    usage = BudgetUsage()
    for _ in range(3):
        usage = usage.reserve_next_cycle(1, policy)
    before = usage

    assert stagnation_stop_reason(
        completed_cycles=2,
        consecutive_non_improving_cycles=2,
        policy=policy,
    ) is None
    assert stagnation_stop_reason(
        completed_cycles=3,
        consecutive_non_improving_cycles=3,
        policy=policy,
    ) == "selection_stagnation_3_cycles"
    assert usage == before
    assert policy.max_cycles_per_origin == 8


def test_stagnation_rejects_impossible_counters() -> None:
    with pytest.raises(PipelineContractError, match="completed_cycles"):
        stagnation_stop_reason(completed_cycles=9, consecutive_non_improving_cycles=3)
    with pytest.raises(PipelineContractError, match="consecutive_non_improving"):
        stagnation_stop_reason(completed_cycles=2, consecutive_non_improving_cycles=3)


def test_pre_run_manifest_is_timestamp_free_deterministic_and_self_validating() -> None:
    generation, manifest = _manifest()
    same = build_pre_run_manifest(
        generation,
        build_monthly_process_boundary_plan("2026-07-08"),
        code_commit=COMMIT,
    )

    assert manifest == same
    forbidden = {"timestamp", "created_at", "generated_at", "started_at", "wall_clock_time"}
    assert _all_object_keys(manifest.payload()).isdisjoint(forbidden)
    validate_pre_run_manifest(manifest)
    assert len(manifest.manifest_sha256) == 64


def test_pre_run_manifest_rejects_invalid_commit_and_digest_tampering() -> None:
    generation = build_pipeline_generation(REPO_ROOT)
    plan = build_monthly_process_boundary_plan("2026-07-08")
    with pytest.raises(PipelineContractError, match="40-character"):
        build_pre_run_manifest(generation, plan, code_commit="short")

    manifest = build_pre_run_manifest(generation, plan, code_commit=COMMIT).to_dict()
    manifest["code_commit"] = "b" * 40
    with pytest.raises(PipelineContractError, match="digest mismatch"):
        validate_pre_run_manifest(manifest)


def test_pre_run_manifest_rejects_recomputed_time_or_boundary_tampering() -> None:
    _, frozen = _manifest()
    timed = frozen.payload()
    timed["timestamp"] = "2026-07-14T00:00:00Z"
    timed["manifest_sha256"] = hashlib.sha256(
        json.dumps(timed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(PipelineContractError, match="fields|wall-clock"):
        validate_pre_run_manifest(timed)

    tampered = frozen.to_dict()
    tampered["boundary_plan"]["boundary_dates"][1] = "2025-08-09"
    tampered["boundary_plan_sha256"] = hashlib.sha256(
        json.dumps(
            tampered["boundary_plan"], sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    raw = dict(tampered)
    raw.pop("manifest_sha256")
    tampered["manifest_sha256"] = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(PipelineContractError, match="canonical task-2 plan"):
        validate_pre_run_manifest(tampered)


def test_seeds_are_stable_scoped_and_unsigned_64_bit() -> None:
    _, manifest = _manifest()
    first = origin_cycle_seed(manifest, origin_index=1, cycle_index=1)
    repeated = origin_cycle_seed(manifest, origin_index=1, cycle_index=1)
    next_cycle = origin_cycle_seed(manifest, origin_index=1, cycle_index=2)
    next_origin = origin_cycle_seed(manifest, origin_index=2, cycle_index=1)
    stage_seed = origin_cycle_seed(
        manifest,
        origin_index=1,
        cycle_index=1,
        stage="candidate_generation",
    )

    assert first == repeated
    assert len({first, next_cycle, next_origin, stage_seed}) == 4
    assert all(0 <= seed < 2**64 for seed in (first, next_cycle, next_origin, stage_seed))
    assert derive_seed(manifest, "origin/01/cycle/01/inner_search") == first


def test_seed_scope_and_indexes_are_fail_closed() -> None:
    _, manifest = _manifest()
    with pytest.raises(PipelineContractError, match="origin_index"):
        origin_cycle_seed(manifest, origin_index=13, cycle_index=1)
    with pytest.raises(PipelineContractError, match="cycle_index"):
        origin_cycle_seed(manifest, origin_index=1, cycle_index=9)
    with pytest.raises(PipelineContractError, match="namespace"):
        derive_seed(manifest, "Invalid Namespace")


def test_pipeline_generation_identity_and_namespaces_detect_tampering() -> None:
    generation = build_pipeline_generation(REPO_ROOT)
    with pytest.raises(PipelineContractError, match="generation id"):
        validate_pipeline_generation(
            replace(generation, generation_id="protocol_v3_pipeline_sha256:" + "0" * 64)
        )
    with pytest.raises(PipelineContractError, match="forward ledger"):
        validate_pipeline_generation(
            replace(generation, forward_ledger_namespace="shared-forward-ledger")
        )
    with pytest.raises(PipelineContractError, match="permanent trial"):
        validate_pipeline_generation(
            replace(generation, permanent_trial_counter_namespace="per-generation-trials")
        )
