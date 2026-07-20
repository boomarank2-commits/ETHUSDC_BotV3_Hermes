from pathlib import Path

path = Path("src/ethusdc_bot/protocol_v3/pipeline_final.py")
text = path.read_text(encoding="utf-8")
replacements = [
    (
        '''from ethusdc_bot.protocol_v3.boundaries import (
    MonthlyProcessBoundaryPlan,
    build_monthly_process_boundary_plan,
    validate_monthly_process_boundary_plan,
)
''',
        '''from ethusdc_bot.protocol_v3.boundaries import (
    BoundaryValidationError,
    MonthlyProcessBoundaryPlan,
    build_monthly_process_boundary_plan,
    validate_monthly_process_boundary_plan,
)
''',
    ),
    (
        '''    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["registration_sha256"] = self.registration_sha256
        return value
''',
        '''    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)
''',
    ),
    (
        '''    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["claim_sha256"] = self.claim_sha256
        value["claim_id"] = self.claim_id
        return value
''',
        '''    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)
''',
    ),
    (
        '''    plan = build_monthly_process_boundary_plan(end.date())
    validate_monthly_process_boundary_plan(plan)
''',
        '''    try:
        plan = build_monthly_process_boundary_plan(end.date())
        validate_monthly_process_boundary_plan(plan)
    except BoundaryValidationError as exc:
        raise PipelineFinalError(
            "pipeline-final window is not an exact Task-2 boundary plan"
        ) from exc
''',
    ),
    (
        '    return PipelineFinalRegistration(_canonical(basis), observed)\n',
        '    return PipelineFinalRegistration(_canonical(root), observed)\n',
    ),
    (
        '    return PipelineFinalClaim(_canonical(basis), observed, root["claim_id"])\n',
        '    return PipelineFinalClaim(_canonical(root), observed, root["claim_id"])\n',
    ),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"serialization replacement mismatch: {old[:80]!r}")
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")


test_path = Path("tests/unit/test_protocol_v3_pipeline_final.py")
test = test_path.read_text(encoding="utf-8")
old = '    with pytest.raises(PipelineFinalError, match="outside its fixed root"):\n'
new = '    with pytest.raises(PipelineFinalError, match="repository_root"):\n'
if test.count(old) != 1:
    raise SystemExit("wrong-root expectation replacement mismatch")
test_path.write_text(test.replace(old, new), encoding="utf-8")
