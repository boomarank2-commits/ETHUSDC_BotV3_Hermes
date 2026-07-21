from pathlib import Path
import json

pipeline_final_path = Path("src/ethusdc_bot/protocol_v3/pipeline_final.py")
text = pipeline_final_path.read_text(encoding="utf-8")
old_import = '''from ethusdc_bot.protocol_v3.reporting import (
    FORWARD_REGISTRATION_ROOT,
    read_forward_window_registration,
)
'''
new_import = '''from ethusdc_bot.protocol_v3.pipeline import build_pipeline_generation
from ethusdc_bot.protocol_v3.reporting import (
    FORWARD_REGISTRATION_ROOT,
    read_forward_window_registration,
)
from ethusdc_bot.protocol_v3.run_identity import (
    RunFingerprint,
    RunIdentityError,
    validate_run_fingerprint,
)
'''
if text.count(old_import) != 1:
    raise SystemExit("pipeline-final import replacement mismatch")
text = text.replace(old_import, new_import)
identity_anchor = '''_IDENTITY_FIELDS: Final = (
    "bootstrap_contract_sha256",
    "boundary_plan_sha256",
    "code_commit",
    "context_contract_sha256",
    "cost_contract_sha256",
    "data_contract_sha256",
    "exchange_info_contract_sha256",
    "execution_contract_sha256",
    "feature_contract_sha256",
    "pipeline_contract_sha256",
    "pipeline_generation_id",
    "quality_gate_contract_sha256",
    "report_contract_sha256",
    "run_fingerprint",
    "search_budget_sha256",
    "seed_policy_sha256",
    "simulator_contract_sha256",
    "stop_policy_sha256",
    "trial_ledger_head_sha256",
)
'''
identity_groups = identity_anchor + '''_IDENTITY_SOURCE_GROUPS: Final = {
    "bootstrap": (
        "configs/protocol_v3_historical_diagnostics_contract.json",
    ),
    "context": (
        "configs/protocol_v3_context_parity_contract.json",
        "configs/protocol_v3_data_snapshot_contract.json",
    ),
    "cost": (
        "configs/protocol_v3_execution_parity_contract.json",
        "configs/protocol_v3_intrabar_execution_contract.json",
    ),
    "data": (
        "configs/protocol_v3_data_snapshot_contract.json",
    ),
    "exchange_info": (
        "configs/protocol_v3_run_identity_contract.json",
    ),
    "execution": (
        "configs/protocol_v3_execution_parity_contract.json",
        "configs/protocol_v3_intrabar_execution_contract.json",
        "configs/protocol_v3_runtime_state_contract.json",
    ),
    "feature": (
        "configs/protocol_v3_data_snapshot_contract.json",
        "configs/protocol_v3_feature_store_contract.json",
        "configs/protocol_v3_opportunity_regime_contract.json",
    ),
    "quality_gate": (
        "configs/protocol_v3_historical_diagnostics_contract.json",
        "configs/protocol_v3_monthly_quality_gate_contract.json",
        "configs/protocol_v3_pipeline_final_contract.json",
        "configs/protocol_v3_pipeline_final_progress_contract.json",
        "configs/protocol_v3_report_contract.json",
        "configs/protocol_v3_transaction_contract.json",
    ),
    "report": (
        "configs/protocol_v3_report_contract.json",
    ),
    "simulator": (
        "configs/protocol_v3_context_parity_contract.json",
        "configs/protocol_v3_execution_parity_contract.json",
        "configs/protocol_v3_intrabar_execution_contract.json",
        "configs/protocol_v3_runtime_state_contract.json",
    ),
}
'''
if text.count(identity_anchor) != 1:
    raise SystemExit("identity source group insertion mismatch")
text = text.replace(identity_anchor, identity_groups)
function_anchor = '''def build_pipeline_final_registration(
'''
functions = '''def build_pipeline_final_identity_manifest(
    *,
    repository_root: str | Path,
    boundary_plan: MonthlyProcessBoundaryPlan,
    run_fingerprint: RunFingerprint | Mapping[str, Any],
) -> dict[str, str]:
    """Recompute every frozen Task-31 identity from typed runtime evidence."""

    repo = _repo(repository_root)
    validate_monthly_process_boundary_plan(boundary_plan)
    run = _validated_run_fingerprint_payload(run_fingerprint, repo)
    generation = build_pipeline_generation(repo)
    pipeline = dict(_mapping(run["pipeline"], "run_fingerprint.pipeline"))
    if (
        pipeline.get("generation_id") != generation.generation_id
        or pipeline.get("contract_sha256") != generation.contract_sha256
    ):
        raise PipelineFinalError(
            "run fingerprint differs from the current pipeline generation"
        )
    pipeline_contract_path = repo / "configs/protocol_v3_pipeline_contract.json"
    try:
        pipeline_contract = _strict_load(
            pipeline_contract_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PipelineFinalError(
            "pipeline contract is missing during final identity derivation"
        ) from exc
    for key in ("budget_policy", "seed_policy", "stop_policy"):
        _mapping(pipeline_contract.get(key), f"pipeline_contract.{key}")
    trial = dict(
        _mapping(run["trial_ledger_head"], "run_fingerprint.trial_ledger_head")
    )
    code = dict(_mapping(run["code"], "run_fingerprint.code"))
    manifest = {
        "bootstrap_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["bootstrap"]
        ),
        "boundary_plan_sha256": pipeline_final_boundary_plan_sha256(boundary_plan),
        "code_commit": code["git_commit"],
        "context_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["context"]
        ),
        "cost_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["cost"]
        ),
        "data_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["data"]
        ),
        "exchange_info_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["exchange_info"]
        ),
        "execution_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["execution"]
        ),
        "feature_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["feature"]
        ),
        "pipeline_contract_sha256": generation.contract_sha256,
        "pipeline_generation_id": generation.generation_id,
        "quality_gate_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["quality_gate"]
        ),
        "report_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["report"]
        ),
        "run_fingerprint": "protocol_v3_run_sha256:" + run["fingerprint_sha256"],
        "search_budget_sha256": _digest(pipeline_contract["budget_policy"]),
        "seed_policy_sha256": _digest(pipeline_contract["seed_policy"]),
        "simulator_contract_sha256": _source_group_sha256(
            repo, _IDENTITY_SOURCE_GROUPS["simulator"]
        ),
        "stop_policy_sha256": _digest(pipeline_contract["stop_policy"]),
        "trial_ledger_head_sha256": trial["head_sha256"],
    }
    return _identity_manifest(manifest)


def validate_pipeline_final_identity_manifest_against_repository(
    value: Mapping[str, Any],
    *,
    repository_root: str | Path,
    boundary_plan: MonthlyProcessBoundaryPlan,
    run_fingerprint: RunFingerprint | Mapping[str, Any],
) -> dict[str, str]:
    observed = _identity_manifest(value)
    expected = build_pipeline_final_identity_manifest(
        repository_root=repository_root,
        boundary_plan=boundary_plan,
        run_fingerprint=run_fingerprint,
    )
    if observed != expected:
        raise PipelineFinalError(
            "frozen pipeline-final identity manifest differs from repository truth"
        )
    return observed


def _validated_run_fingerprint_payload(
    value: RunFingerprint | Mapping[str, Any],
    repository_root: Path,
) -> dict[str, Any]:
    if isinstance(value, RunFingerprint):
        payload = value.to_dict()
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        raise PipelineFinalError("validated run fingerprint is required")
    try:
        validate_run_fingerprint(payload, repo_root=repository_root)
    except RunIdentityError as exc:
        raise PipelineFinalError(
            "run fingerprint failed repository revalidation"
        ) from exc
    return payload


def _source_group_sha256(repo: Path, relative_paths: Sequence[str]) -> str:
    rows: list[dict[str, str]] = []
    for relative_text in relative_paths:
        relative = PurePosixPath(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise PipelineFinalError("final identity source path is unsafe")
        path = repo.joinpath(*relative.parts)
        _no_symlinks(repo, path)
        if not path.exists() or not path.is_file() or path.is_symlink():
            raise PipelineFinalError(
                f"final identity source is missing or unsafe: {relative_text}"
            )
        rows.append(
            {
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return _digest(rows)


'''
if text.count(function_anchor) != 1:
    raise SystemExit("identity function insertion anchor mismatch")
text = text.replace(function_anchor, functions + function_anchor)
old_all = '''    "build_pipeline_final_registration",
    "claim_pipeline_final_evaluation",
'''
new_all = '''    "build_pipeline_final_identity_manifest",
    "build_pipeline_final_registration",
    "claim_pipeline_final_evaluation",
'''
if text.count(old_all) != 1:
    raise SystemExit("identity builder export replacement mismatch")
text = text.replace(old_all, new_all)
old_validate_export = '''    "validate_pipeline_final_contract",
    "validate_pipeline_final_registration",
'''
new_validate_export = '''    "validate_pipeline_final_contract",
    "validate_pipeline_final_identity_manifest_against_repository",
    "validate_pipeline_final_registration",
'''
if text.count(old_validate_export) != 1:
    raise SystemExit("identity validator export replacement mismatch")
text = text.replace(old_validate_export, new_validate_export)
pipeline_final_path.write_text(text, encoding="utf-8")

attestation_path = Path("src/ethusdc_bot/protocol_v3/pipeline_final_attestation.py")
attestation = attestation_path.read_text(encoding="utf-8")
old_import = '''    pipeline_final_boundary_plan,
    pipeline_final_boundary_plan_sha256,
    validate_pipeline_final_claim,
'''
new_import = '''    pipeline_final_boundary_plan,
    pipeline_final_boundary_plan_sha256,
    validate_pipeline_final_claim,
    validate_pipeline_final_identity_manifest_against_repository,
'''
if attestation.count(old_import) != 1:
    raise SystemExit("attestation identity import replacement mismatch")
attestation = attestation.replace(old_import, new_import)
old_signature = '''    bound_hindsight_benchmarks: BoundHindsightBenchmarks,
    completed_at_utc: str,
) -> PipelineFinalAttestation:
'''
new_signature = '''    bound_hindsight_benchmarks: BoundHindsightBenchmarks,
    source_repository_root: str | Path,
    completed_at_utc: str,
) -> PipelineFinalAttestation:
'''
if attestation.count(old_signature) != 1:
    raise SystemExit("attestation repository signature replacement mismatch")
attestation = attestation.replace(old_signature, new_signature)
checkpoint_anchor = '''    checkpoint_payload = checkpoint.checkpoint.to_dict()
    result = _mapping(checkpoint_payload.get("result"), "checkpoint.result")
'''
checkpoint_insert = '''    checkpoint_payload = checkpoint.checkpoint.to_dict()
    checkpoint_identity = _mapping(
        checkpoint_payload.get("identity"), "checkpoint.identity"
    )
    checkpoint_run = _mapping(
        checkpoint_identity.get("run_fingerprint"),
        "checkpoint.identity.run_fingerprint",
    )
    try:
        validate_pipeline_final_identity_manifest_against_repository(
            reg_payload["frozen_identity_manifest"],
            repository_root=source_repository_root,
            boundary_plan=plan,
            run_fingerprint=checkpoint_run,
        )
    except PipelineFinalError as exc:
        raise PipelineFinalAttestationError(
            "pipeline-final frozen identity failed repository revalidation"
        ) from exc
    result = _mapping(checkpoint_payload.get("result"), "checkpoint.result")
'''
if attestation.count(checkpoint_anchor) != 1:
    raise SystemExit("attestation checkpoint identity insertion mismatch")
attestation = attestation.replace(checkpoint_anchor, checkpoint_insert)
old_validator_signature = '''    bound_hindsight_benchmarks: BoundHindsightBenchmarks | None = None,
) -> PipelineFinalAttestation:
'''
new_validator_signature = '''    bound_hindsight_benchmarks: BoundHindsightBenchmarks | None = None,
    source_repository_root: str | Path | None = None,
) -> PipelineFinalAttestation:
'''
if attestation.count(old_validator_signature) != 1:
    raise SystemExit("attestation validator repository signature mismatch")
attestation = attestation.replace(old_validator_signature, new_validator_signature)
old_dependencies = '''            bound_hindsight_benchmarks,
        )
'''
new_dependencies = '''            bound_hindsight_benchmarks,
            source_repository_root,
        )
'''
if attestation.count(old_dependencies) != 1:
    raise SystemExit("attestation dependency tuple replacement mismatch")
attestation = attestation.replace(old_dependencies, new_dependencies)
old_rebuild_call = '''            bound_hindsight_benchmarks=bound_hindsight_benchmarks,
            completed_at_utc=root.get("completed_at_utc"),
'''
new_rebuild_call = '''            bound_hindsight_benchmarks=bound_hindsight_benchmarks,
            source_repository_root=source_repository_root,
            completed_at_utc=root.get("completed_at_utc"),
'''
if attestation.count(old_rebuild_call) != 1:
    raise SystemExit("attestation rebuild repository argument mismatch")
attestation = attestation.replace(old_rebuild_call, new_rebuild_call)
attestation_path.write_text(attestation, encoding="utf-8")

attestation_test_path = Path("tests/unit/test_protocol_v3_pipeline_final_attestation.py")
test = attestation_test_path.read_text(encoding="utf-8")
import_anchor = '''from ethusdc_bot.protocol_v3 import monthly_quality_gate

'''
if test.count(import_anchor) != 1:
    raise SystemExit("attestation test repo root anchor mismatch")
test = test.replace(import_anchor, import_anchor + 'REPO_ROOT = Path(__file__).resolve().parents[2]\n\n')
start = test.index("def _manifest(base, plan) -> dict[str, str]:")
end = test.index("\n\ndef _completion_identities", start)
new_manifest = '''def _manifest(base, plan) -> dict[str, str]:
    return pipeline_final.build_pipeline_final_identity_manifest(
        repository_root=REPO_ROOT,
        boundary_plan=plan,
        run_fingerprint=base["identity"].to_dict()["run_fingerprint"],
    )
'''
test = test[:start] + new_manifest + test[end:]
old_build_call = '''        bound_hindsight_benchmarks=state["bound"],
        completed_at_utc=state["completed_at"],
'''
new_build_call = '''        bound_hindsight_benchmarks=state["bound"],
        source_repository_root=REPO_ROOT,
        completed_at_utc=state["completed_at"],
'''
if test.count(old_build_call) != 1:
    raise SystemExit("attestation test build repository argument mismatch")
test = test.replace(old_build_call, new_build_call)
old_dependencies_return = '''        "bound_hindsight_benchmarks": state["bound"],
    }
'''
new_dependencies_return = '''        "bound_hindsight_benchmarks": state["bound"],
        "source_repository_root": REPO_ROOT,
    }
'''
if test.count(old_dependencies_return) != 1:
    raise SystemExit("attestation test dependency repository argument mismatch")
test = test.replace(old_dependencies_return, new_dependencies_return)
insert_anchor = '''def test_incomplete_or_early_final_evidence_is_blocked(state) -> None:
'''
identity_test = '''def test_frozen_identity_manifest_is_recomputed_from_repository(state) -> None:
    manifest = state["registration"].to_dict()["frozen_identity_manifest"]
    assert (
        pipeline_final.validate_pipeline_final_identity_manifest_against_repository(
            manifest,
            repository_root=REPO_ROOT,
            boundary_plan=state["plan"],
            run_fingerprint=state["base"]["identity"].to_dict()[
                "run_fingerprint"
            ],
        )
        == manifest
    )
    changed = dict(manifest)
    changed["quality_gate_contract_sha256"] = "0" * 64
    with pytest.raises(
        pipeline_final.PipelineFinalError,
        match="differs from repository truth",
    ):
        pipeline_final.validate_pipeline_final_identity_manifest_against_repository(
            changed,
            repository_root=REPO_ROOT,
            boundary_plan=state["plan"],
            run_fingerprint=state["base"]["identity"].to_dict()[
                "run_fingerprint"
            ],
        )


'''
if test.count(insert_anchor) != 1:
    raise SystemExit("identity revalidation test insertion mismatch")
test = test.replace(insert_anchor, identity_test + insert_anchor)
attestation_test_path.write_text(test, encoding="utf-8")

pipeline_contract_path = Path("configs/protocol_v3_pipeline_contract.json")
contract = json.loads(pipeline_contract_path.read_text(encoding="utf-8"))
versions = contract["component_contracts"]["quality_gates"]
for version in (
    "protocol_v3_preregistered_single_open_pipeline_final_v1",
    "protocol_v3_result_blind_twelve_origin_progress_v1",
    "protocol_v3_task13_result_blind_pipeline_final_checkpoint_v1",
    "protocol_v3_transitively_revalidated_pipeline_final_attestation_v1",
):
    if version not in versions:
        versions.append(version)
sources = contract["source_bindings"]["quality_gates"]
for source in (
    "configs/protocol_v3_pipeline_final_contract.json",
    "configs/protocol_v3_pipeline_final_progress_contract.json",
    "src/ethusdc_bot/protocol_v3/pipeline_final.py",
    "src/ethusdc_bot/protocol_v3/pipeline_final_api.py",
    "src/ethusdc_bot/protocol_v3/pipeline_final_progress.py",
    "src/ethusdc_bot/protocol_v3/pipeline_final_progress_api.py",
    "src/ethusdc_bot/protocol_v3/pipeline_final_checkpoint.py",
    "src/ethusdc_bot/protocol_v3/pipeline_final_checkpoint_api.py",
    "src/ethusdc_bot/protocol_v3/pipeline_final_attestation.py",
    "src/ethusdc_bot/protocol_v3/pipeline_final_attestation_api.py",
):
    if source not in sources:
        sources.append(source)
pipeline_contract_path.write_text(
    json.dumps(contract, indent=2, ensure_ascii=True) + "\n",
    encoding="utf-8",
)
