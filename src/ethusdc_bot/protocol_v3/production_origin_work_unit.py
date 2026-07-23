"""Restartable real-data execution for one Protocol-v3 monthly origin."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import uuid
from typing import Any, Final

from ethusdc_bot.backtest.context_features import ContextVetoPolicy
from ethusdc_bot.backtest.data_loader import AlignedMarketCandles

from . import transactional_cache as tx
from .boundaries import MonthlyProcessBoundaryPlan
from .context_parity import build_context_parity_binding
from .inner_folds import InnerFoldPlan, validate_inner_fold_plan
from .inner_selection import CANDIDATE_SELECTION_IDENTITY_SCHEMA
from .pipeline import (
    BudgetUsage,
    build_pipeline_generation,
    build_pre_run_manifest,
)
from .production_inner_cycle import (
    ProductionInnerCycleResult,
    execute_production_inner_cycle,
    validate_production_inner_cycle_result,
    write_production_inner_cycle_result,
)
from .production_origin_selection import (
    ProductionOriginSelectionResult,
    build_production_cycle_selection_decision,
    build_production_origin_selection,
    restore_archived_cycle_decision,
    validate_production_origin_selection,
    write_production_origin_selection,
)
from .run_identity import build_run_fingerprint
from .runtime_state import HorizonPolicy
from .trial_ledger import read_trial_ledger

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_production_origin_work_unit_contract.json"
)
CONTRACT_SCHEMA_VERSION: Final = (
    "protocol_v3_production_origin_work_unit_contract_v1"
)
CONTRACT_VERSION: Final = "protocol_v3_restartable_origin_work_unit_v1"
INTENT_SCHEMA_VERSION: Final = "protocol_v3_origin_work_unit_intent_v1"
WORK_ROOT: Final = Path("reports/protocol_v3/origin_work_units")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_CYCLES: Final = tuple(range(1, 9))
_SAFETY: Final = {
    "api_keys": "forbidden",
    "canonical_adoption": "locked",
    "live": "locked",
    "orders": "locked",
    "outer_results": "forbidden",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "cycle_policy": {
        "required_cycles": 8,
        "generated_per_cycle": 40,
        "tested_per_cycle": 12,
        "walk_forward_per_cycle": 3,
        "finalists_per_cycle": 2,
        "cycle_result_write_is_create_only": True,
        "later_cycle_requires_prior_committed_checkpoint": True,
    },
    "identity_policy": {
        "current_pre_run_manifest_required": True,
        "current_run_fingerprint_at_decision_required": True,
        "real_task15_decision_required": True,
        "context_parity_binding_required": True,
        "exact_fold_identity_required": True,
        "exact_ledger_head_required": True,
        "transaction_intent_write_is_create_only": True,
    },
    "resume_policy": {
        "committed_checkpoint_is_only_resume_truth": True,
        "cycle_artifact_revalidated_before_resume": True,
        "uncommitted_cycle_artifact_may_be_recovered_only_at_its_exact_ledger_head": True,
        "stale_or_unknown_lock_recovery_is_never_automatic": True,
        "duplicate_cycle_or_ledger_append_forbidden": True,
    },
    "origin_policy": {
        "all_eight_cycle_results_required": True,
        "full_cross_cycle_origin_selection_required": True,
        "origin_selection_uses_current_post_cycle_ledger_head": True,
        "origin_selection_write_is_create_only": True,
        "execution_may_remediate_sole_outer_adapter_blocker": True,
        "terminal_stop_reason": "max_cycles_reached",
    },
    "safety": _SAFETY,
}


class ProductionOriginWorkUnitError(ValueError):
    """Raised when a production origin cannot execute or resume exactly."""


@dataclass(frozen=True)
class ProductionOriginWorkUnitResult:
    origin_index: int
    cycle_result_paths: tuple[Path, ...]
    origin_selection_path: Path
    origin_selection: ProductionOriginSelectionResult
    resumed_cycle_count: int


CycleExecutor = Callable[..., ProductionInnerCycleResult]


def load_production_origin_work_unit_contract(
    repo_root: str | Path,
) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        payload = _strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProductionOriginWorkUnitError(
            "production origin work-unit contract is unreadable"
        ) from exc
    if payload != _CANONICAL_CONTRACT:
        raise ProductionOriginWorkUnitError(
            "production origin work-unit contract is not canonical"
        )
    return payload


def execute_production_origin_work_unit(
    *,
    repo_root: str | Path,
    context: AlignedMarketCandles,
    fold_plan: InnerFoldPlan | Mapping[str, Any],
    boundary_plan: MonthlyProcessBoundaryPlan,
    data_snapshot: Mapping[str, Any],
    exchange_info_snapshot: Mapping[str, Any],
    horizon_policy: HorizonPolicy,
    trial_ledger_root: str | Path,
    initial_trial_ledger_status: Mapping[str, Any],
    origin_index: int,
    code_commit: str,
    cycle_executor: CycleExecutor = execute_production_inner_cycle,
) -> ProductionOriginWorkUnitResult:
    """Execute or resume cycles 1..8, then commit full origin selection."""

    repo = Path(repo_root).resolve(strict=True)
    load_production_origin_work_unit_contract(repo)
    if not isinstance(context, AlignedMarketCandles):
        raise ProductionOriginWorkUnitError(
            "real aligned three-market context is required"
        )
    if not isinstance(boundary_plan, MonthlyProcessBoundaryPlan):
        raise ProductionOriginWorkUnitError(
            "validated monthly boundary plan is required"
        )
    if not isinstance(horizon_policy, HorizonPolicy):
        raise ProductionOriginWorkUnitError(
            "validated horizon policy is required"
        )
    plan = validate_inner_fold_plan(fold_plan)
    origin = _positive(origin_index, "origin_index")
    if (
        origin > len(boundary_plan.origins)
        or plan.origin_index != origin
    ):
        raise ProductionOriginWorkUnitError(
            "origin index differs from boundary or fold plan"
        )
    commit = str(code_commit).strip().lower()
    if not _COMMIT.fullmatch(commit):
        raise ProductionOriginWorkUnitError(
            "code_commit must be a full lowercase git SHA"
        )
    pipeline = build_pipeline_generation(repo)
    manifest = build_pre_run_manifest(
        pipeline, boundary_plan, code_commit=commit
    )
    binding = build_context_parity_binding(
        context,
        ContextVetoPolicy(),
        data_snapshot,
        repo_root=repo,
    )
    ledger_root = Path(trial_ledger_root).resolve(strict=True)
    root = _origin_root(repo, pipeline.generation_id, origin)
    root.mkdir(parents=True, exist_ok=True)
    _validate_initial_ledger_binding(
        repo=repo,
        root=root,
        ledger_root=ledger_root,
        initial_status=initial_trial_ledger_status,
    )

    results: list[ProductionInnerCycleResult] = []
    paths: list[Path] = []
    resumed = 0
    for cycle in _CYCLES:
        artifact_path = root / f"cycle-{cycle:02d}.json"
        intent_path = root / f"cycle-{cycle:02d}.intent.json"
        if intent_path.exists():
            result = _resume_cycle(
                repo=repo,
                intent_path=intent_path,
                artifact_path=artifact_path,
                manifest=manifest,
                ledger_root=ledger_root,
                origin_index=origin,
                cycle_index=cycle,
                fold_plan=plan,
                code_commit=commit,
            )
            resumed += 1
        else:
            if artifact_path.exists():
                result = _read_cycle_result(artifact_path)
                ledger = read_trial_ledger(ledger_root)
                if (
                    result.to_dict()["trial_ledger_head_sha256"]
                    != ledger.status.head_sha256
                ):
                    raise ProductionOriginWorkUnitError(
                        "uncommitted cycle artifact is not at the current "
                        "ledger head"
                    )
            else:
                result = cycle_executor(
                    repo_root=repo,
                    context=context,
                    fold_plan=plan,
                    exchange_info_snapshot=exchange_info_snapshot,
                    horizon_policy=horizon_policy,
                    trial_ledger_root=ledger_root,
                    origin_index=origin,
                    cycle_index=cycle,
                    code_commit=commit,
                )
                write_production_inner_cycle_result(result, artifact_path)
            _validate_cycle_binding(
                result,
                origin_index=origin,
                cycle_index=cycle,
                fold_plan=plan,
                pipeline_generation_id=pipeline.generation_id,
                code_commit=commit,
            )
            ledger = read_trial_ledger(ledger_root)
            fingerprint = build_run_fingerprint(
                data_snapshot=data_snapshot,
                exchange_info_snapshot=exchange_info_snapshot,
                pipeline_generation=pipeline,
                context_binding=binding,
                code_commit=commit,
                trial_ledger=ledger,
                repo_root=repo,
            )
            decision = build_production_cycle_selection_decision(
                result,
                fold_plan=plan,
                pre_run_manifest=manifest,
                run_fingerprint=fingerprint,
            )
            identity = _transaction_identity(
                repo=repo,
                fingerprint=fingerprint,
                binding=binding,
                horizon_policy=horizon_policy,
                plan=plan,
                decision=decision,
                work_unit_id=f"origin_{origin:02d}_cycle_{cycle:02d}",
            )
            intent = _build_intent(
                identity=identity,
                manifest=manifest,
                artifact_path=artifact_path,
                artifact_sha256=result.result_sha256,
                origin_index=origin,
                cycle_index=cycle,
                kind="cycle",
                repo=repo,
            )
            _write_create_only_atomic(intent_path, intent)
            _commit_intent(
                repo=repo,
                ledger_root=ledger_root,
                identity=identity,
                manifest=manifest,
                result_status="COMPLETED",
                result_payload=_artifact_reference(
                    repo, artifact_path, result.result_sha256
                ),
                origin_index=origin,
                cycle_index=cycle,
                stage="inner_search",
            )
        results.append(result)
        paths.append(artifact_path)

    ledger = read_trial_ledger(ledger_root)
    fingerprint = build_run_fingerprint(
        data_snapshot=data_snapshot,
        exchange_info_snapshot=exchange_info_snapshot,
        pipeline_generation=pipeline,
        context_binding=binding,
        code_commit=commit,
        trial_ledger=ledger,
        repo_root=repo,
    )
    selection_path = root / "origin-selection.json"
    if selection_path.exists():
        selection = _read_origin_selection(selection_path)
    else:
        selection = build_production_origin_selection(
            repo_root=repo,
            fold_plan=plan,
            trial_ledger=ledger,
            cycle_results=results,
            pre_run_manifest=manifest,
            run_fingerprint=fingerprint,
            code_commit=commit,
        )
        write_production_origin_selection(selection, selection_path)
    if (
        selection.to_dict()["trial_ledger_head_sha256"]
        != ledger.status.head_sha256
    ):
        raise ProductionOriginWorkUnitError(
            "origin selection differs from current permanent ledger head"
        )
    _commit_final_selection(
        repo=repo,
        ledger_root=ledger_root,
        manifest=manifest,
        fingerprint=fingerprint,
        binding=binding,
        horizon_policy=horizon_policy,
        plan=plan,
        selection=selection,
        selection_path=selection_path,
        origin_index=origin,
    )
    return ProductionOriginWorkUnitResult(
        origin_index=origin,
        cycle_result_paths=tuple(paths),
        origin_selection_path=selection_path,
        origin_selection=selection,
        resumed_cycle_count=resumed,
    )


def _commit_final_selection(
    *,
    repo: Path,
    ledger_root: Path,
    manifest: Any,
    fingerprint: Any,
    binding: Any,
    horizon_policy: HorizonPolicy,
    plan: InnerFoldPlan,
    selection: ProductionOriginSelectionResult,
    selection_path: Path,
    origin_index: int,
) -> None:
    payload = selection.to_dict()
    selected_cycle = payload["selected_cycle_index"] or 1
    archive = payload["cycle_decision_archives"][selected_cycle - 1]
    decision = restore_archived_cycle_decision(
        archive, expected_cycle=selected_cycle
    )
    identity = _transaction_identity(
        repo=repo,
        fingerprint=fingerprint,
        binding=binding,
        horizon_policy=horizon_policy,
        plan=plan,
        decision=decision,
        work_unit_id=f"origin_{origin_index:02d}_final_selection",
    )
    intent_path = selection_path.with_name("origin-selection.intent.json")
    intent = _build_intent(
        identity=identity,
        manifest=manifest,
        artifact_path=selection_path,
        artifact_sha256=selection.result_sha256,
        origin_index=origin_index,
        cycle_index=8,
        kind="origin_selection",
        repo=repo,
    )
    if intent_path.exists():
        observed = _read_intent(intent_path, repo)
        if observed != intent:
            raise ProductionOriginWorkUnitError(
                "persisted final-selection intent differs from current result"
            )
        checkpoint = tx.resume_last_committed_checkpoint(
            current_identity=identity,
            current_pre_run_manifest=manifest,
            repository_root=repo,
        )
        if checkpoint is None:
            _commit_intent(
                repo=repo,
                ledger_root=ledger_root,
                identity=identity,
                manifest=manifest,
                result_status=(
                    "NO_TRADE"
                    if payload["outcome"] == "NO_TRADE"
                    else "COMPLETED"
                ),
                result_payload=_artifact_reference(
                    repo, selection_path, selection.result_sha256
                ),
                origin_index=origin_index,
                cycle_index=8,
                stage="origin_selection",
            )
        else:
            expected = _artifact_reference(
                repo, selection_path, selection.result_sha256
            )
            checkpoint_payload = checkpoint.to_dict()["result"]
            expected_status = (
                "NO_TRADE"
                if payload["outcome"] == "NO_TRADE"
                else "COMPLETED"
            )
            if (
                checkpoint_payload["status"] != expected_status
                or checkpoint_payload["payload"] != expected
            ):
                raise ProductionOriginWorkUnitError(
                    "final checkpoint differs from origin selection"
                )
        return
    _write_create_only_atomic(intent_path, intent)
    _commit_intent(
        repo=repo,
        ledger_root=ledger_root,
        identity=identity,
        manifest=manifest,
        result_status=(
            "NO_TRADE"
            if payload["outcome"] == "NO_TRADE"
            else "COMPLETED"
        ),
        result_payload=_artifact_reference(
            repo, selection_path, selection.result_sha256
        ),
        origin_index=origin_index,
        cycle_index=8,
        stage="origin_selection",
    )


def _resume_cycle(
    *,
    repo: Path,
    intent_path: Path,
    artifact_path: Path,
    manifest: Any,
    ledger_root: Path,
    origin_index: int,
    cycle_index: int,
    fold_plan: InnerFoldPlan,
    code_commit: str,
) -> ProductionInnerCycleResult:
    intent = _read_intent(intent_path, repo)
    if (
        intent["kind"] != "cycle"
        or intent["origin_index"] != origin_index
        or intent["cycle_index"] != cycle_index
    ):
        raise ProductionOriginWorkUnitError(
            "cycle intent identity is inconsistent"
        )
    identity = tx.validate_transaction_identity(
        intent["transaction_identity"], repository_root=repo
    )
    checkpoint = tx.resume_last_committed_checkpoint(
        current_identity=identity,
        current_pre_run_manifest=manifest,
        repository_root=repo,
    )
    if checkpoint is None:
        result = _read_cycle_result(artifact_path)
        reference = _artifact_reference(
            repo, artifact_path, result.result_sha256
        )
        if intent["artifact"] != reference:
            raise ProductionOriginWorkUnitError(
                "uncommitted cycle intent differs from its artifact"
            )
        checkpoint = _commit_intent(
            repo=repo,
            ledger_root=ledger_root,
            identity=identity,
            manifest=manifest,
            result_status="COMPLETED",
            result_payload=reference,
            origin_index=origin_index,
            cycle_index=cycle_index,
            stage="inner_search",
        )
    else:
        result = _read_cycle_result(artifact_path)
    _validate_cycle_binding(
        result,
        origin_index=origin_index,
        cycle_index=cycle_index,
        fold_plan=fold_plan,
        pipeline_generation_id=(
            manifest.payload()["pipeline_generation"]["generation_id"]
        ),
        code_commit=code_commit,
    )
    reference = _artifact_reference(repo, artifact_path, result.result_sha256)
    if (
        intent["artifact"] != reference
        or checkpoint.to_dict()["result"]["payload"] != reference
        or checkpoint.to_dict()["result"]["status"] != "COMPLETED"
    ):
        raise ProductionOriginWorkUnitError(
            "cycle checkpoint does not bind the revalidated artifact"
        )
    return result


def _transaction_identity(
    *,
    repo: Path,
    fingerprint: Any,
    binding: Any,
    horizon_policy: HorizonPolicy,
    plan: InnerFoldPlan,
    decision: Any,
    work_unit_id: str,
) -> Any:
    return tx.build_transaction_identity(
        run_fingerprint=fingerprint,
        context_binding=binding,
        horizon_policy=horizon_policy,
        work_unit_id=work_unit_id,
        candidate_identity=tx.build_bound_identity_slot(
            tx.CANDIDATE_SLOT,
            CANDIDATE_SELECTION_IDENTITY_SCHEMA,
            decision.candidate_identity_payload,
        ),
        fold_identity=tx.build_bound_identity_slot(
            tx.FOLD_SLOT,
            tx.FOLD_IDENTITY_SCHEMA,
            plan.identity_payload,
        ),
        rotation_state_identity=tx.build_genesis_identity_slot(
            tx.ROTATION_SLOT,
            tx.ROTATION_GENESIS_SCHEMA,
            "no_rotation_state",
        ),
        sealed_store_heads=tx.build_sealed_store_heads_slot([], repo),
        repository_root=repo,
    )


def _commit_intent(
    *,
    repo: Path,
    ledger_root: Path,
    identity: Any,
    manifest: Any,
    result_status: str,
    result_payload: Mapping[str, Any],
    origin_index: int,
    cycle_index: int,
    stage: str,
) -> Any:
    lock = tx.acquire_transaction_lock(
        identity.transaction_id,
        repo,
        owner_id=f"{stage}_{os.getpid()}",
    )
    try:
        return tx.commit_checkpoint(
            identity=identity,
            pre_run_manifest=manifest,
            seed_state=tx.build_seed_state(
                manifest,
                origin_index=origin_index,
                cycle_index=cycle_index,
                stage=stage,
            ),
            budget_usage=_budget(origin_index, cycle_index),
            stop_state=tx.build_stop_state(
                completed_cycles=cycle_index,
                consecutive_non_improving_cycles=0,
            ),
            result_status=result_status,
            result_payload=result_payload,
            repository_root=repo,
            trial_ledger_root=ledger_root,
            lock=lock,
        )
    finally:
        current = tx.inspect_transaction_lock(identity.transaction_id, repo)
        if current is not None and current.to_dict()["process_id"] == os.getpid():
            tx.release_transaction_lock(current, repo)


def _budget(origin_index: int, completed_cycles: int) -> BudgetUsage:
    usage = BudgetUsage()
    for _ in range(completed_cycles):
        usage = usage.reserve_next_cycle(origin_index)
    return usage


def _build_intent(
    *,
    identity: Any,
    manifest: Any,
    artifact_path: Path,
    artifact_sha256: str,
    origin_index: int,
    cycle_index: int,
    kind: str,
    repo: Path,
) -> dict[str, Any]:
    basis = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "kind": kind,
        "origin_index": origin_index,
        "cycle_index": cycle_index,
        "transaction_identity": identity.to_dict(),
        "pre_run_manifest_sha256": manifest.manifest_sha256,
        "artifact": _artifact_reference(
            repo, artifact_path, artifact_sha256
        ),
        "safety": _SAFETY,
    }
    return {**basis, "intent_sha256": _digest(basis)}


def _read_intent(path: Path, repo: Path) -> dict[str, Any]:
    try:
        root = _strict_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProductionOriginWorkUnitError(
            "production work-unit intent is unreadable"
        ) from exc
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "kind",
        "origin_index",
        "cycle_index",
        "transaction_identity",
        "pre_run_manifest_sha256",
        "artifact",
        "safety",
        "intent_sha256",
    }
    if set(root) != required or root["safety"] != _SAFETY:
        raise ProductionOriginWorkUnitError(
            "production work-unit intent fields are invalid"
        )
    observed = root.pop("intent_sha256")
    if observed != _digest(root):
        raise ProductionOriginWorkUnitError(
            "production work-unit intent digest mismatch"
        )
    tx.validate_transaction_identity(
        root["transaction_identity"], repository_root=repo
    )
    return {**root, "intent_sha256": observed}


def _validate_cycle_binding(
    result: ProductionInnerCycleResult,
    *,
    origin_index: int,
    cycle_index: int,
    fold_plan: InnerFoldPlan,
    pipeline_generation_id: str,
    code_commit: str,
) -> None:
    payload = validate_production_inner_cycle_result(result).to_dict()
    if (
        payload["origin_index"] != origin_index
        or payload["cycle_index"] != cycle_index
        or payload["fold_plan_sha256"] != fold_plan.plan_sha256
        or payload["pipeline_generation_id"] != pipeline_generation_id
        or payload["code_commit"] != code_commit
    ):
        raise ProductionOriginWorkUnitError(
            "cycle result identity differs from active origin"
        )


def _validate_initial_ledger_binding(
    *,
    repo: Path,
    root: Path,
    ledger_root: Path,
    initial_status: Mapping[str, Any],
) -> None:
    status = dict(initial_status)
    head = status.get("head_sha256")
    event_count = status.get("event_count")
    if (
        not isinstance(head, str)
        or not _SHA.fullmatch(head)
        or isinstance(event_count, bool)
        or not isinstance(event_count, int)
        or event_count < 0
    ):
        raise ProductionOriginWorkUnitError(
            "initial preflight ledger status is invalid"
        )
    first_intent_path = root / "cycle-01.intent.json"
    if first_intent_path.exists():
        intent = _read_intent(first_intent_path, repo)
        decision_head = intent["transaction_identity"][
            "run_fingerprint"
        ]["trial_ledger_head"]
        if (
            decision_head["head_sha256"] != head
            or decision_head["event_count"] != event_count
        ):
            raise ProductionOriginWorkUnitError(
                "cycle-1 resume identity differs from preflight ledger"
            )
        return
    current = read_trial_ledger(ledger_root).status
    if (
        current.head_sha256 != head
        or current.event_count != event_count
    ):
        raise ProductionOriginWorkUnitError(
            "fresh origin run requires the exact preflight ledger head"
        )


def _read_cycle_result(path: Path) -> ProductionInnerCycleResult:
    try:
        return validate_production_inner_cycle_result(
            _strict_loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProductionOriginWorkUnitError(
            "cycle result artifact is invalid"
        ) from exc


def _read_origin_selection(path: Path) -> ProductionOriginSelectionResult:
    try:
        return validate_production_origin_selection(
            _strict_loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ProductionOriginWorkUnitError(
            "origin-selection artifact is invalid"
        ) from exc


def _artifact_reference(
    repo: Path,
    path: Path,
    artifact_sha256: str,
) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(repo)
    except ValueError as exc:
        raise ProductionOriginWorkUnitError(
            "work-unit artifact lies outside repository runtime root"
        ) from exc
    raw = resolved.read_bytes()
    return {
        "relative_path": relative.as_posix(),
        "artifact_sha256": artifact_sha256,
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
    }


def _origin_root(repo: Path, generation_id: str, origin: int) -> Path:
    generation = generation_id.rsplit(":", 1)[1][:16]
    return repo / WORK_ROOT / generation / f"origin-{origin:02d}"


def _write_create_only_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (_canonical(payload) + "\n").encode("utf-8")
    temp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    try:
        with temp.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)
        except FileExistsError as exc:
            raise ProductionOriginWorkUnitError(
                "production work-unit intent is create-only"
            ) from exc
    finally:
        if temp.exists():
            temp.unlink()


def _positive(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProductionOriginWorkUnitError(
            f"{path} must be a positive integer"
        )
    return value


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _strict_loads(text: str) -> dict[str, Any]:
    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ProductionOriginWorkUnitError(
                    f"duplicate JSON key: {key}"
                )
            result[key] = value
        return result

    value = json.loads(
        text,
        object_pairs_hook=hook,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ProductionOriginWorkUnitError(
                f"non-finite JSON constant: {token}"
            )
        ),
    )
    if not isinstance(value, dict):
        raise ProductionOriginWorkUnitError("JSON root must be an object")
    return value


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_VERSION",
    "ProductionOriginWorkUnitError",
    "ProductionOriginWorkUnitResult",
    "execute_production_origin_work_unit",
    "load_production_origin_work_unit_contract",
]
