"""Transitive Task-27 binding for both historical hindsight solvers.

The binding is downstream of Tasks 22-26. It revalidates the exact outer
process, MTM ledger, raw-data and exchange snapshots, run fingerprints,
pipeline generation, candidate bundles, and rotation states before either
hindsight solver may run. Persisted bindings are accepted only after exact
source replay; caller-provided benchmark values are never trusted.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Final

from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.protocol_v3.boundaries import (
    MonthlyProcessBoundaryPlan,
    validate_monthly_process_boundary_plan,
)
from ethusdc_bot.protocol_v3.data_snapshot import (
    FrozenDataSnapshot,
    compute_utc_day_content_sha256,
    validate_frozen_data_snapshot,
)
from ethusdc_bot.protocol_v3.execution_parity import build_market_execution_rules
from ethusdc_bot.protocol_v3.hindsight_solvers import (
    HindsightOriginPolicy,
    solve_all_candle_one_trade_close_hindsight,
    solve_candidate_matched_volume_filtered_hindsight,
    validate_hindsight_solver_evidence,
)
from ethusdc_bot.protocol_v3.outer_mtm_ledger import (
    OuterMtmLedger,
    validate_outer_mtm_ledger,
)
from ethusdc_bot.protocol_v3.outer_origins import (
    OuterOriginProcess,
    validate_outer_origin_process,
)
from ethusdc_bot.protocol_v3.pipeline import (
    build_pipeline_generation,
    validate_pipeline_generation,
)
from ethusdc_bot.protocol_v3.run_identity import (
    FrozenExchangeInfoSnapshot,
    validate_exchange_info_snapshot,
    validate_run_fingerprint,
)

PROTOCOL_VERSION: Final = "3.0.0"
BINDING_SCHEMA_VERSION: Final = "protocol_v3_bound_hindsight_benchmarks_v1"
BINDING_CONTRACT_VERSION: Final = (
    "protocol_v3_transitively_bound_hindsight_benchmarks_v1"
)
_MANIFEST_SCHEMA_VERSION: Final = "protocol_v3_hindsight_binding_manifest_v1"
_SOURCE_PATHS: Final = (
    "configs/protocol_v3_historical_diagnostics_contract.json",
    "configs/protocol_v3_pipeline_contract.json",
    "src/ethusdc_bot/protocol_v3/hindsight_solvers.py",
    "src/ethusdc_bot/protocol_v3/hindsight_binding.py",
    "src/ethusdc_bot/protocol_v3/historical_diagnostics.py",
)
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class HindsightBindingError(ValueError):
    """Raised when a Task-27 dependency is incomplete or inconsistent."""


@dataclass(frozen=True)
class BoundHindsightBenchmarks:
    canonical_json: str
    binding_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["binding_sha256"] = self.binding_sha256
        return value


def build_bound_hindsight_benchmarks(
    *,
    repo_root: str | Path,
    boundary_plan: MonthlyProcessBoundaryPlan,
    outer_process: OuterOriginProcess,
    baseline_ledger: OuterMtmLedger,
    data_snapshot: FrozenDataSnapshot | Mapping[str, Any],
    ethusdc_process_candles: Sequence[Candle],
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
) -> BoundHindsightBenchmarks:
    """Revalidate all upstream evidence and execute both solver implementations."""

    root = Path(repo_root).resolve(strict=True)
    validate_monthly_process_boundary_plan(boundary_plan)
    process = validate_outer_origin_process(
        outer_process, boundary_plan=boundary_plan
    )
    ledger = validate_outer_mtm_ledger(
        baseline_ledger,
        boundary_plan=boundary_plan,
        outer_process=process,
    )
    validate_frozen_data_snapshot(data_snapshot, repo_root=root)
    validate_exchange_info_snapshot(exchange_info_snapshot, repo_root=root)
    snapshot_payload, snapshot_sha = _snapshot(data_snapshot)
    exchange_payload, exchange_sha = _exchange(exchange_info_snapshot)
    process_payload = process.to_dict()
    ledger_payload = ledger.to_dict()

    snapshot_binding = _bind_process_candles_to_snapshot(
        boundary_plan,
        snapshot_payload,
        snapshot_sha,
        ethusdc_process_candles,
    )
    provenance = _bind_upstream_process(
        root,
        boundary_plan,
        process_payload,
        ledger_payload,
        snapshot_sha,
        exchange_sha,
    )
    policies = _derive_origin_policies(
        boundary_plan, process_payload, ledger_payload
    )
    policy_rows = [policy.to_dict() for policy in policies]
    if _digest(policy_rows) != provenance["candidate_policy_chain_sha256"]:
        raise HindsightBindingError(
            "derived candidate policy chain differs from upstream evidence"
        )

    all_candle = solve_all_candle_one_trade_close_hindsight(
        ethusdc_process_candles,
        process_start_inclusive=boundary_plan.process_start_inclusive,
        process_end_exclusive=boundary_plan.process_end_exclusive,
        exchange_info_snapshot=exchange_payload,
    )
    candidate = solve_candidate_matched_volume_filtered_hindsight(
        ethusdc_process_candles,
        boundary_plan=boundary_plan,
        origin_policies=policies,
        exchange_info_snapshot=exchange_payload,
    )
    all_payload = validate_hindsight_solver_evidence(all_candle).to_dict()
    candidate_payload = validate_hindsight_solver_evidence(candidate).to_dict()
    for payload in (all_payload, candidate_payload):
        identity = payload["input_identity"]
        if (
            identity["ethusdc_process_data_sha256"]
            != snapshot_binding["ethusdc_process_data_sha256"]
            or identity["exchange_info_snapshot_sha256"] != exchange_sha
        ):
            raise HindsightBindingError(
                "solver data or exchange identity differs from bound source evidence"
            )
    if candidate_payload["input_identity"]["policy_chain"] != policy_rows:
        raise HindsightBindingError(
            "candidate solver policy chain differs from Task-22/23/24 evidence"
        )

    source_binding = _source_binding(root)
    rules = build_market_execution_rules(exchange_payload)
    manifest = {
        "schema_version": _MANIFEST_SCHEMA_VERSION,
        **snapshot_binding,
        **provenance,
        "execution_rules_sha256": rules.rules_sha256,
        "exchange_info_snapshot_sha256": exchange_sha,
        "solver_source_binding": source_binding,
        "solver_source_binding_sha256": _digest(source_binding),
        "all_candle_solver_evidence_sha256": all_payload["evidence_sha256"],
        "candidate_matched_solver_evidence_sha256": candidate_payload[
            "evidence_sha256"
        ],
    }
    basis = {
        "schema_version": BINDING_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": BINDING_CONTRACT_VERSION,
        "binding_manifest": manifest,
        "binding_manifest_sha256": _digest(manifest),
        "all_candle_solver_evidence": all_payload,
        "candidate_matched_solver_evidence": candidate_payload,
        "candidate_max_roundtrips_per_utc_day": max(
            policy.max_roundtrips_per_utc_day for policy in policies
        ),
        "candidate_policy_chain": policy_rows,
        "candidate_policy_chain_sha256": _digest(policy_rows),
        "future_prices_used_for_diagnostic_only": True,
        "selection_feedback_allowed": False,
        "monthly_quality_gate_feedback_allowed": False,
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "canonical_adoption_eligible": False,
        "safety": _SAFETY,
    }
    return validate_bound_hindsight_benchmarks(
        BoundHindsightBenchmarks(_canonical(basis), _digest(basis))
    )


def validate_bound_hindsight_benchmarks(
    value: BoundHindsightBenchmarks | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    boundary_plan: MonthlyProcessBoundaryPlan | None = None,
    outer_process: OuterOriginProcess | None = None,
    baseline_ledger: OuterMtmLedger | None = None,
    data_snapshot: FrozenDataSnapshot | Mapping[str, Any] | None = None,
    ethusdc_process_candles: Sequence[Candle] | None = None,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any] | None = None,
) -> BoundHindsightBenchmarks:
    """Validate a fresh typed result or replay every source for persisted data."""

    root = (
        value.to_dict()
        if isinstance(value, BoundHindsightBenchmarks)
        else dict(_mapping(value, "bound_hindsight_benchmarks"))
    )
    if not isinstance(value, BoundHindsightBenchmarks):
        dependencies = (
            repo_root,
            boundary_plan,
            outer_process,
            baseline_ledger,
            data_snapshot,
            ethusdc_process_candles,
            exchange_info_snapshot,
        )
        if any(item is None for item in dependencies):
            raise HindsightBindingError(
                "persisted hindsight binding requires every source dependency"
            )
        expected = build_bound_hindsight_benchmarks(
            repo_root=repo_root,
            boundary_plan=boundary_plan,
            outer_process=outer_process,
            baseline_ledger=baseline_ledger,
            data_snapshot=data_snapshot,
            ethusdc_process_candles=ethusdc_process_candles,
            exchange_info_snapshot=exchange_info_snapshot,
        ).to_dict()
        if root != expected:
            raise HindsightBindingError(
                "persisted hindsight binding differs from exact source replay"
            )

    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "binding_manifest",
        "binding_manifest_sha256",
        "all_candle_solver_evidence",
        "candidate_matched_solver_evidence",
        "candidate_max_roundtrips_per_utc_day",
        "candidate_policy_chain",
        "candidate_policy_chain_sha256",
        "future_prices_used_for_diagnostic_only",
        "selection_feedback_allowed",
        "monthly_quality_gate_feedback_allowed",
        "freshness",
        "diagnostic_only",
        "canonical_adoption_eligible",
        "safety",
        "binding_sha256",
    }
    if set(root) != required:
        raise HindsightBindingError(
            "bound hindsight benchmark fields are missing or unexpected"
        )
    if (
        root["schema_version"] != BINDING_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != BINDING_CONTRACT_VERSION
    ):
        raise HindsightBindingError("bound hindsight benchmark version is invalid")
    manifest = dict(_mapping(root["binding_manifest"], "binding_manifest"))
    if (
        manifest.get("schema_version") != _MANIFEST_SCHEMA_VERSION
        or root["binding_manifest_sha256"] != _digest(manifest)
    ):
        raise HindsightBindingError("hindsight binding manifest digest mismatch")

    all_solver = validate_hindsight_solver_evidence(
        root["all_candle_solver_evidence"]
    ).to_dict()
    candidate_solver = validate_hindsight_solver_evidence(
        root["candidate_matched_solver_evidence"]
    ).to_dict()
    if (
        manifest.get("all_candle_solver_evidence_sha256")
        != all_solver["evidence_sha256"]
        or manifest.get("candidate_matched_solver_evidence_sha256")
        != candidate_solver["evidence_sha256"]
    ):
        raise HindsightBindingError("solver output is not bound to the manifest")
    for solver_payload in (all_solver, candidate_solver):
        identity = solver_payload["input_identity"]
        if (
            identity["ethusdc_process_data_sha256"]
            != manifest.get("ethusdc_process_data_sha256")
            or identity["exchange_info_snapshot_sha256"]
            != manifest.get("exchange_info_snapshot_sha256")
            or identity["execution_rules_sha256"]
            != manifest.get("execution_rules_sha256")
        ):
            raise HindsightBindingError(
                "solver input identity differs from the binding manifest"
            )

    policies = root["candidate_policy_chain"]
    if (
        not isinstance(policies, list)
        or len(policies) != 12
        or root["candidate_policy_chain_sha256"] != _digest(policies)
        or manifest.get("candidate_policy_chain_sha256") != _digest(policies)
        or candidate_solver["input_identity"]["policy_chain"] != policies
        or candidate_solver["input_identity"]["policy_chain_sha256"]
        != _digest(policies)
    ):
        raise HindsightBindingError("candidate policy chain binding is invalid")
    normalized = [_policy_from_dict(row).to_dict() for row in policies]
    if normalized != policies:
        raise HindsightBindingError("candidate policy chain is not canonical")
    _validate_manifest_chains(manifest, policies)

    maximum = max(row["max_roundtrips_per_utc_day"] for row in policies)
    if root["candidate_max_roundtrips_per_utc_day"] != maximum:
        raise HindsightBindingError("candidate maximum trade count is inconsistent")
    if (
        root["future_prices_used_for_diagnostic_only"] is not True
        or root["selection_feedback_allowed"] is not False
        or root["monthly_quality_gate_feedback_allowed"] is not False
        or root["freshness"] != "NOT_FRESH"
        or root["diagnostic_only"] is not True
        or root["canonical_adoption_eligible"] is not False
        or root["safety"] != _SAFETY
    ):
        raise HindsightBindingError("hindsight binding safety or feedback locks failed")

    source_binding = manifest.get("solver_source_binding")
    if (
        not isinstance(source_binding, dict)
        or manifest.get("solver_source_binding_sha256") != _digest(source_binding)
        or set(source_binding) != set(_SOURCE_PATHS)
        or any(not _is_sha(item) for item in source_binding.values())
    ):
        raise HindsightBindingError("solver source-code binding is invalid")
    for key in (
        "data_snapshot_sha256",
        "ethusdc_snapshot_market_content_sha256",
        "ethusdc_process_data_sha256",
        "ethusdc_process_day_index_sha256",
        "outer_process_sha256",
        "outer_ledger_sha256",
        "origin_chain_sha256",
        "candidate_bundle_chain_sha256",
        "rotation_state_chain_sha256",
        "origin_run_fingerprint_chain_sha256",
        "candidate_policy_chain_sha256",
        "current_pipeline_generation_basis_sha256",
        "current_pipeline_contract_sha256",
        "execution_rules_sha256",
        "exchange_info_snapshot_sha256",
        "solver_source_binding_sha256",
        "all_candle_solver_evidence_sha256",
        "candidate_matched_solver_evidence_sha256",
    ):
        if not _is_sha(manifest.get(key)):
            raise HindsightBindingError(
                f"hindsight binding identity is invalid: {key}"
            )
    if (
        not isinstance(manifest.get("code_commit"), str)
        or len(manifest["code_commit"]) != 40
        or any(char not in "0123456789abcdef" for char in manifest["code_commit"])
        or manifest.get("pipeline_generation_id")
        != "protocol_v3_pipeline_sha256:"
        + manifest["current_pipeline_generation_basis_sha256"]
    ):
        raise HindsightBindingError("code or pipeline generation identity is invalid")

    observed = _sha(root["binding_sha256"], "binding_sha256")
    basis = dict(root)
    basis.pop("binding_sha256")
    if observed != _digest(basis):
        raise HindsightBindingError("bound hindsight benchmark digest mismatch")
    return BoundHindsightBenchmarks(_canonical(basis), observed)


def _validate_manifest_chains(
    manifest: Mapping[str, Any], policies: Sequence[Mapping[str, Any]]
) -> None:
    day_index = manifest.get("ethusdc_process_day_index")
    if (
        not isinstance(day_index, list)
        or len(day_index) != 365
        or manifest.get("ethusdc_process_day_index_sha256") != _digest(day_index)
    ):
        raise HindsightBindingError("ETHUSDC process day-index binding is invalid")
    expected_start = date.fromisoformat(
        policies[0]["start_inclusive_utc"][:10]
    )
    expected_days = [
        (expected_start + timedelta(days=index)).isoformat()
        for index in range(365)
    ]
    if [row.get("day") for row in day_index] != expected_days or any(
        not _is_sha(row.get("content_sha256")) for row in day_index
    ):
        raise HindsightBindingError(
            "ETHUSDC process day index has missing, duplicate, or invalid days"
        )

    origin_hashes = manifest.get("origin_hashes")
    bundles = manifest.get("candidate_bundle_chain")
    rotations = manifest.get("rotation_state_chain")
    fingerprints = manifest.get("origin_run_fingerprint_sha256")
    if not all(
        isinstance(rows, list) and len(rows) == 12
        for rows in (origin_hashes, bundles, rotations, fingerprints)
    ):
        raise HindsightBindingError("upstream binding chains require twelve origins")
    if (
        manifest.get("origin_chain_sha256") != _digest(origin_hashes)
        or manifest.get("candidate_bundle_chain_sha256") != _digest(bundles)
        or manifest.get("rotation_state_chain_sha256") != _digest(rotations)
        or manifest.get("origin_run_fingerprint_chain_sha256")
        != _digest(fingerprints)
        or any(not _is_sha(item) for item in origin_hashes)
        or any(not _is_sha(item) for item in fingerprints)
    ):
        raise HindsightBindingError("upstream origin chain digest is invalid")

    for index, (policy, origin_hash, bundle, rotation) in enumerate(
        zip(policies, origin_hashes, bundles, rotations, strict=True), start=1
    ):
        if (
            policy["origin_index"] != index
            or origin_hash != policy["origin_selection_sha256"]
            or not isinstance(bundle, Mapping)
            or bundle.get("origin_index") != index
            or bundle.get("bundle_sha256")
            != policy["candidate_bundle_sha256"]
            or not isinstance(rotation, Mapping)
            or rotation.get("origin_index") != index
            or rotation.get("rotation_state_sha256")
            != policy["rotation_state_sha256"]
            or rotation.get("new_candidate_bundle_sha256")
            != policy["candidate_bundle_sha256"]
        ):
            raise HindsightBindingError(
                "Task-22 bundle, Task-23 origin, and Task-24 rotation chain mismatch"
            )
        validity = bundle.get("validity")
        if not isinstance(validity, Mapping) or (
            validity.get("valid_from_utc") != policy["valid_from_utc"]
            or validity.get("valid_until_utc") != policy["end_exclusive_utc"]
        ):
            raise HindsightBindingError(
                "candidate bundle validity differs from solver policy"
            )
        for key in (
            "bundle_sha256",
            "router_decision_sha256",
            "rotation_state_sha256",
            "new_candidate_bundle_sha256",
        ):
            source = bundle if key in bundle else rotation
            if not _is_sha(source.get(key)):
                raise HindsightBindingError(
                    f"upstream chain hash is invalid: {key}"
                )
        if rotation.get("open_position") is not None:
            if (
                rotation.get("entry_enabled_at_utc") is not None
                or rotation.get("flat_time_utc") is not None
            ):
                raise HindsightBindingError(
                    "exit-only handoff cannot be flat or entry-enabled"
                )
        elif rotation.get("flat_time_utc") is None:
            raise HindsightBindingError(
                "flat rotation requires an explicit flat_time_utc"
            )


def _bind_process_candles_to_snapshot(
    plan: MonthlyProcessBoundaryPlan,
    snapshot: Mapping[str, Any],
    snapshot_sha: str,
    candles: Sequence[Candle],
) -> dict[str, Any]:
    boundary = dict(_mapping(snapshot.get("boundary"), "snapshot.boundary"))
    if boundary.get("process_end_exclusive") != plan.process_end_exclusive.isoformat():
        raise HindsightBindingError(
            "snapshot process end differs from the monthly boundary plan"
        )
    markets = snapshot.get("market_data")
    if not isinstance(markets, list):
        raise HindsightBindingError("snapshot market_data is invalid")
    eth = next(
        (dict(row) for row in markets if row.get("symbol") == "ETHUSDC"),
        None,
    )
    if eth is None:
        raise HindsightBindingError("snapshot lacks ETHUSDC market evidence")
    index = {
        row["day"]: row["content_sha256"]
        for row in eth["utc_day_content_sha256"]
    }
    if len(candles) != 365 * 1440:
        raise HindsightBindingError(
            "process candle input must contain exactly 365 complete UTC days"
        )
    process_index = []
    binary = hashlib.sha256()
    for offset, day in enumerate(plan.iter_process_oos_days()):
        rows = candles[offset * 1440 : (offset + 1) * 1440]
        digest = compute_utc_day_content_sha256("ETHUSDC", day, rows)
        if index.get(day.isoformat()) != digest:
            raise HindsightBindingError(
                f"ETHUSDC process day differs from the frozen raw snapshot: {day}"
            )
        process_index.append({"day": day.isoformat(), "content_sha256": digest})
        for candle in rows:
            binary.update(_binary_candle(candle))
    return {
        "data_snapshot_sha256": snapshot_sha,
        "ethusdc_snapshot_market_content_sha256": eth["market_content_sha256"],
        "ethusdc_process_data_sha256": binary.hexdigest(),
        "ethusdc_process_day_index": process_index,
        "ethusdc_process_day_index_sha256": _digest(process_index),
    }


def _bind_upstream_process(
    repo_root: Path,
    plan: MonthlyProcessBoundaryPlan,
    process: Mapping[str, Any],
    ledger: Mapping[str, Any],
    snapshot_sha: str,
    exchange_sha: str,
) -> dict[str, Any]:
    origins = process["origins"]
    ledgers = ledger["origin_ledgers"]
    if len(origins) != 12 or len(ledgers) != 12:
        raise HindsightBindingError("upstream process must contain twelve origins")
    current_pipeline = build_pipeline_generation(repo_root)
    validate_pipeline_generation(current_pipeline)
    current_basis = current_pipeline.basis()
    origin_hashes = []
    bundle_rows = []
    rotation_rows = []
    fingerprints = []
    commits = set()
    generations = set()
    for origin, origin_ledger, boundary in zip(
        origins, ledgers, plan.origins, strict=True
    ):
        run = origin["selection_decision"]["frozen_pipeline_config"][
            "run_fingerprint"
        ]
        validate_run_fingerprint(run, repo_root=repo_root)
        if run["raw_data"]["snapshot_sha256"] != snapshot_sha:
            raise HindsightBindingError(
                "origin run fingerprint uses another raw-data snapshot"
            )
        if run["exchange_info"]["snapshot_sha256"] != exchange_sha:
            raise HindsightBindingError(
                "origin run fingerprint uses another exchange-info snapshot"
            )
        if origin["pipeline_generation_id"] != run["pipeline"]["generation_id"]:
            raise HindsightBindingError(
                "origin pipeline generation differs from its run fingerprint"
            )
        if origin["code_commit"] != run["code"]["git_commit"]:
            raise HindsightBindingError(
                "origin code commit differs from its run fingerprint"
            )
        if run["pipeline"]["generation_id"] != current_pipeline.generation_id:
            raise HindsightBindingError(
                "historical process was not generated by the current bound pipeline"
            )
        bundle = origin["frozen_candidate_bundle"]
        if bundle["cost_model"] != run["cost_model"]:
            raise HindsightBindingError(
                "frozen candidate bundle cost model differs from the run fingerprint"
            )
        rotation = origin_ledger["rotation_state"]
        if (
            origin_ledger["origin_selection_sha256"] != origin["origin_sha256"]
            or origin_ledger["candidate_bundle_sha256"] != bundle["bundle_sha256"]
            or rotation["new_candidate_bundle_sha256"] != bundle["bundle_sha256"]
        ):
            raise HindsightBindingError(
                "Task-23 origin, Task-22 bundle, and Task-24 rotation do not chain"
            )
        origin_hashes.append(origin["origin_sha256"])
        bundle_rows.append(
            {
                "origin_index": boundary.origin_index,
                "bundle_sha256": bundle["bundle_sha256"],
                "predecessor_bundle_sha256": bundle[
                    "predecessor_bundle_sha256"
                ],
                "router_decision_sha256": bundle["router_decision"][
                    "decision_sha256"
                ],
                "cost_model": bundle["cost_model"],
                "validity": bundle["validity"],
            }
        )
        rotation_rows.append(
            {
                "origin_index": boundary.origin_index,
                "rotation_state_sha256": origin_ledger[
                    "rotation_state_sha256"
                ],
                "new_candidate_bundle_sha256": rotation[
                    "new_candidate_bundle_sha256"
                ],
                "open_position": rotation["open_position"],
                "entry_enabled_at_utc": rotation["entry_enabled_at_utc"],
                "flat_time_utc": rotation["flat_time_utc"],
                "retiring_configuration_mode": rotation[
                    "retiring_configuration_mode"
                ],
                "new_configuration_mode": rotation["new_configuration_mode"],
                "monthly_boundary_liquidation": rotation[
                    "monthly_boundary_liquidation"
                ],
            }
        )
        fingerprints.append(run["fingerprint_sha256"])
        commits.add(origin["code_commit"])
        generations.add(origin["pipeline_generation_id"])
    if len(commits) != 1 or len(generations) != 1:
        raise HindsightBindingError(
            "all origins must share one code commit and pipeline generation"
        )
    policies = _derive_origin_policies(plan, process, ledger)
    policy_rows = [policy.to_dict() for policy in policies]
    return {
        "outer_process_sha256": process["process_sha256"],
        "outer_ledger_sha256": ledger["ledger_sha256"],
        "origin_hashes": origin_hashes,
        "origin_chain_sha256": _digest(origin_hashes),
        "candidate_bundle_chain": bundle_rows,
        "candidate_bundle_chain_sha256": _digest(bundle_rows),
        "rotation_state_chain": rotation_rows,
        "rotation_state_chain_sha256": _digest(rotation_rows),
        "origin_run_fingerprint_sha256": fingerprints,
        "origin_run_fingerprint_chain_sha256": _digest(fingerprints),
        "code_commit": next(iter(commits)),
        "pipeline_generation_id": next(iter(generations)),
        "current_pipeline_generation_basis_sha256": (
            current_pipeline.generation_id.rsplit(":", 1)[1]
        ),
        "current_pipeline_contract_sha256": current_basis["contract_sha256"],
        "current_pipeline_component_source_sha256": current_basis[
            "component_source_sha256"
        ],
        "current_pipeline_component_contracts": current_basis[
            "component_contracts"
        ],
        "candidate_policy_chain_sha256": _digest(policy_rows),
    }


def _derive_origin_policies(
    plan: MonthlyProcessBoundaryPlan,
    process: Mapping[str, Any],
    ledger: Mapping[str, Any],
) -> tuple[HindsightOriginPolicy, ...]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for trade in ledger["closed_trades"]:
        bundle = _sha(
            trade["candidate_bundle_sha256"],
            "trade.candidate_bundle_sha256",
        )
        entry_day = _parse_utc(trade["entry_time_utc"]).date().isoformat()
        counts[(bundle, entry_day)] += 1
    maximum_by_bundle: dict[str, int] = defaultdict(int)
    for (bundle, _), count in counts.items():
        maximum_by_bundle[bundle] = max(maximum_by_bundle[bundle], count)

    policies = []
    for origin, origin_ledger, boundary in zip(
        process["origins"], ledger["origin_ledgers"], plan.origins, strict=True
    ):
        bundle = origin["frozen_candidate_bundle"]
        bundle_sha = bundle["bundle_sha256"]
        routable = (
            bundle["router_decision"]["outcome"] != "NO_TRADE"
            and bundle["research_simulation_routable"] is True
        )
        observed_maximum = maximum_by_bundle[bundle_sha]
        if not routable and observed_maximum:
            raise HindsightBindingError(
                "NO_TRADE or non-routable bundle has observed baseline trades"
            )
        scalar = bundle["scalar_parameters"]
        if routable:
            if not isinstance(scalar, Mapping):
                raise HindsightBindingError(
                    "routable candidate bundle lacks frozen scalar parameters"
                )
            max_hold = scalar.get("max_hold_minutes")
            if (
                isinstance(max_hold, bool)
                or not isinstance(max_hold, int)
                or max_hold <= 0
            ):
                raise HindsightBindingError(
                    "routable candidate lacks a positive frozen max_hold_minutes"
                )
        else:
            max_hold = 0
        entry_allowed = bool(routable and observed_maximum > 0)
        policies.append(
            HindsightOriginPolicy(
                origin_index=boundary.origin_index,
                start_inclusive_utc=_midnight(boundary.test_start_inclusive),
                end_exclusive_utc=_midnight(boundary.test_end_exclusive),
                valid_from_utc=boundary.valid_from,
                origin_selection_sha256=origin["origin_sha256"],
                candidate_bundle_sha256=bundle_sha,
                rotation_state_sha256=origin_ledger[
                    "rotation_state_sha256"
                ],
                max_roundtrips_per_utc_day=(
                    observed_maximum if entry_allowed else 0
                ),
                max_holding_minutes=(max_hold if entry_allowed else 0),
                entry_allowed=entry_allowed,
            )
        )
    return tuple(policies)


def _source_binding(repo_root: Path) -> dict[str, str]:
    result = {}
    for relative in _SOURCE_PATHS:
        path = repo_root / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise HindsightBindingError(
                f"bound solver source is missing: {relative}"
            ) from exc
        result[relative] = hashlib.sha256(data).hexdigest()
    return result


def _policy_from_dict(row: Mapping[str, Any]) -> HindsightOriginPolicy:
    value = dict(_mapping(row, "origin_policy"))
    required = {
        "origin_index",
        "start_inclusive_utc",
        "end_exclusive_utc",
        "valid_from_utc",
        "origin_selection_sha256",
        "candidate_bundle_sha256",
        "rotation_state_sha256",
        "max_roundtrips_per_utc_day",
        "max_holding_minutes",
        "entry_allowed",
    }
    if set(value) != required:
        raise HindsightBindingError("origin policy fields are invalid")
    return HindsightOriginPolicy(
        origin_index=value["origin_index"],
        start_inclusive_utc=_parse_utc(value["start_inclusive_utc"]),
        end_exclusive_utc=_parse_utc(value["end_exclusive_utc"]),
        valid_from_utc=_parse_utc(value["valid_from_utc"]),
        origin_selection_sha256=value["origin_selection_sha256"],
        candidate_bundle_sha256=value["candidate_bundle_sha256"],
        rotation_state_sha256=value["rotation_state_sha256"],
        max_roundtrips_per_utc_day=value["max_roundtrips_per_utc_day"],
        max_holding_minutes=value["max_holding_minutes"],
        entry_allowed=value["entry_allowed"],
    )


def _snapshot(
    value: FrozenDataSnapshot | Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    if isinstance(value, FrozenDataSnapshot):
        return value.payload(), value.snapshot_sha256
    root = dict(_mapping(value, "data_snapshot"))
    digest = _sha(root.pop("snapshot_sha256", None), "data_snapshot_sha256")
    return root, digest


def _exchange(
    value: FrozenExchangeInfoSnapshot | Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    root = (
        value.to_dict()
        if isinstance(value, FrozenExchangeInfoSnapshot)
        else dict(_mapping(value, "exchange_info_snapshot"))
    )
    return root, _sha(
        root["snapshot_sha256"], "exchange_info_snapshot_sha256"
    )


def _binary_candle(candle: Candle) -> bytes:
    return struct.pack(
        ">qddddd",
        candle.open_time,
        candle.open,
        candle.high,
        candle.low,
        candle.close,
        candle.volume,
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HindsightBindingError(f"{name} must be an object")
    return value


def _midnight(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise HindsightBindingError("timestamp must be canonical UTC text")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise HindsightBindingError("timestamp is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise HindsightBindingError("timestamp must be UTC")
    return parsed.astimezone(UTC)


def _sha(value: Any, name: str) -> str:
    if not _is_sha(value):
        raise HindsightBindingError(f"{name} must be lowercase sha256")
    return value


def _is_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


__all__ = [
    "BINDING_CONTRACT_VERSION",
    "BINDING_SCHEMA_VERSION",
    "BoundHindsightBenchmarks",
    "HindsightBindingError",
    "build_bound_hindsight_benchmarks",
    "validate_bound_hindsight_benchmarks",
]
