"""Update legacy Shadow test fixtures for the explicit budget-evidence schema."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_all(relative_path: str, old: str, new: str, expected_count: int = 1) -> None:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0 and new in text:
        print(f"already patched {relative_path}")
        return
    if count != expected_count:
        raise RuntimeError(
            f"expected {expected_count} source fragments in {relative_path}, found {count}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"patched {relative_path}")


def assessment_block(indent: str = "        ") -> str:
    return (
        f'{indent}"assessment": {{\n'
        f'{indent}    "color": "green",\n'
        f'{indent}    "color_scope": "canonical_100_usdc_final_evaluation",\n'
        f'{indent}    "shadow_eligible": True,\n'
        f'{indent}    "target_reached": True,\n'
        f'{indent}    "target_evidence_budget_usdc": 100,\n'
        f'{indent}    "deployment_budget_usdc": budget,\n'
        f'{indent}    "deployment_target_usdc_per_day": (\n'
        f'{indent}        policy.target_guidance.desired_net_usdc_per_day\n'
        f'{indent}    ),\n'
        f'{indent}    "deployment_target_status": (\n'
        f'{indent}        "verified" if budget == 100 else "unverified_scaling"\n'
        f'{indent}    ),\n'
        f'{indent}    "deployment_target_reached": budget == 100,\n'
        f'{indent}    "live_eligible": False,\n'
        f'{indent}    "reason_codes": (\n'
        f'{indent}        ["all_quality_gates_passed"]\n'
        f'{indent}        if budget == 100\n'
        f'{indent}        else [\n'
        f'{indent}            "all_quality_gates_passed",\n'
        f'{indent}            "deployment_budget_scaling_unverified",\n'
        f'{indent}        ]\n'
        f'{indent}    ),\n'
        f'{indent}}},\n'
    )


def main() -> None:
    old = '''        "assessment": {\n            "color": "green",\n            "shadow_eligible": True,\n            "target_reached": True,\n            "live_eligible": False,\n            "reason_codes": ["all_quality_gates_passed"],\n        },\n'''
    new = assessment_block()
    replace_all("tests/unit/test_shadow_engine.py", old, new)
    replace_all("tests/unit/test_shadow_runtime.py", old, new)


if __name__ == "__main__":
    main()
