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
progress = progress_path.read_text(encoding="utf-8")n