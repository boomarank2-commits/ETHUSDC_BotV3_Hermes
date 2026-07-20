from pathlib import Path

outer_path = Path("src/ethusdc_bot/protocol_v3/outer_origins.py")
outer = outer_path.read_text(encoding="utf-8")
anchor = '''def validate_outer_origin_process(
    value: OuterOriginProcess | Mapping[str, Any],
    *,
    boundary_plan: MonthlyProcessBoundaryPlan,
) -> OuterOriginProcess:
'''
insert = '''def validate_outer_origin_selection(
    value: OuterOriginSelection | Mapping[str, Any],
    *,
    origin: MonthlyOriginBoundary,
) -> OuterOriginSelection:
    """Validate one canonical origin envelope with the full Task-23 rules."""

    if not isinstance(origin, MonthlyOriginBoundary):
        raise OuterOriginError("verified MonthlyOriginBoundary required")
    root = value.to_dict() if isinstance(value, OuterOriginSelection) else value
    normalized = _validate_origin_envelope(root, origin)
    observed = normalized["origin_sha256"]
    basis = dict(normalized)
    basis.pop("origin_sha256")
    return OuterOriginSelection(_canonical(basis), observed)


'''
if outer.count(anchor) != 1:
    raise SystemExit("outer-origin validator insertion anchor mismatch")
outer = outer.replace(anchor, insert + anchor)
old_all = '''    "run_outer_origin",
    "validate_outer_origin_process",
]'''
new_all = '''    "run_outer_origin",
    "validate_outer_origin_process",
    "validate_outer_origin_selection",
]'''
if outer.count(old_all) != 1:
    raise SystemExit("outer-origin __all__ replacement mismatch")
outer_path.write_text(outer.replace(old_all, new_all), encoding="utf-8")

progress_path = Path("src/ethusdc_bot/protocol_v3/pipeline_final_progress.py")
progress = progress_path.read_text(encoding="utf-8")
old_import = '''from ethusdc_bot.protocol_v3.outer_origins import OuterOriginSelection
from ethusdc_bot.protocol_v3.pipeline_final import (
'''
new_import = '''from ethusdc_bot.protocol_v3.outer_origins import (
    OuterOriginError,
    OuterOriginSelection,
    validate_outer_origin_selection,
)
from ethusdc_bot.protocol_v3.pipeline_final import (
'''
if progress.count(old_import) != 1:
    raise SystemExit("progress outer-origin import replacement mismatch")
progress = progress.replace(old_import, new_import)
old_pipeline_import = '''    PipelineFinalRegistration,
    validate_pipeline_final_claim,
    validate_pipeline_final_registration,
)
'''
new_pipeline_import = '''    PipelineFinalRegistration,
    pipeline_final_boundary_plan,
    validate_pipeline_final_claim,
    validate_pipeline_final_registration,
)
'''
if progress.count(old_pipeline_import) != 1:
    raise SystemExit("progress pipeline-final import replacement mismatch")
progress = progress.replace(old_pipeline_import, new_pipeline_import)
start = progress.index("def _validate_origin_selection(")
end = progress.index("\ndef _origin_identities(", start)
replacement = '''def _validate_origin_selection(
    selection: OuterOriginSelection,
    *,
    registration: PipelineFinalRegistration,
    expected_origin_index: int,
) -> str:
    if not isinstance(selection, OuterOriginSelection):
        raise PipelineFinalProgressError(
            "typed OuterOriginSelection required"
        )
    registration_payload = registration.to_dict()
    plan = pipeline_final_boundary_plan(
        start_inclusive_utc=registration_payload["start_inclusive_utc"],
        end_exclusive_utc=registration_payload["end_exclusive_utc"],
    )
    if type(expected_origin_index) is not int or not 1 <= expected_origin_index <= 12:
        raise PipelineFinalProgressError("expected origin index is invalid")
    try:
        validated = validate_outer_origin_selection(
            selection,
            origin=plan.origins[expected_origin_index - 1],
        )
    except OuterOriginError as exc:
        raise PipelineFinalProgressError(
            "outer origin selection failed the full Task-23 validation"
        ) from exc
    root = validated.to_dict()
    manifest = registration_payload["frozen_identity_manifest"]
    if (
        root["pipeline_generation_id"] != manifest["pipeline_generation_id"]
        or root["code_commit"] != manifest["code_commit"]
        or root["outer_results_visible_during_fit"] is not False
    ):
        raise PipelineFinalProgressError(
            "outer origin selection changed pipeline, code, or visibility"
        )
    if selection.origin_sha256 != validated.origin_sha256:
        raise PipelineFinalProgressError(
            "outer origin selection typed digest mismatch"
        )
    return validated.origin_sha256

'''
progress = progress[:start] + replacement + progress[end + 1 :]
progress_path.write_text(progress, encoding="utf-8")


test_path = Path("tests/unit/test_protocol_v3_pipeline_final_progress.py")
test = test_path.read_text(encoding="utf-8")
old = '''    first = _append(progress, selections[0], 1, state=state)
    earlier_than_first = f"{plan.origins[0].test_end_exclusive.isoformat()}T00:00:00Z"
    with pytest.raises(PipelineFinalProgressError, match="monotonic"):
        _append(first, selections[1], 2, state=state, completed=earlier_than_first)
'''
new = '''    delayed_first_dt = datetime.combine(
        plan.origins[1].test_end_exclusive,
        datetime.min.time(),
        tzinfo=UTC,
    ) + timedelta(days=1)
    first = _append(
        progress,
        selections[0],
        1,
        state=state,
        completed=_fmt(delayed_first_dt),
    )
    earlier_than_first = f"{plan.origins[1].test_end_exclusive.isoformat()}T00:00:00Z"
    with pytest.raises(PipelineFinalProgressError, match="monotonic"):
        _append(first, selections[1], 2, state=state, completed=earlier_than_first)
'''
if test.count(old) != 1:
    raise SystemExit("progress monotonicity test replacement mismatch")
test_path.write_text(test.replace(old, new), encoding="utf-8")
