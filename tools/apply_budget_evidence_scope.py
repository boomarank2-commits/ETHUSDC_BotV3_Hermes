"""Bind Shadow deployment target claims to their actual evidence budget.

The sealed final evaluation is canonical for the 100-USDC profile.  Selecting a
larger manual Shadow deployment budget is allowed, but must not inherit a claim
that the proportional 6/15/30-USDC target was independently demonstrated.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_exact(relative_path: str, old: str, new: str) -> bool:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    if old in text:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"patched {relative_path}")
        return True
    if new in text:
        print(f"already patched {relative_path}")
        return False
    raise RuntimeError(f"expected source fragment not found in {relative_path}")


def main() -> None:
    changed = False

    changed |= replace_exact(
        "src/ethusdc_bot/shadow/adoption.py",
        'SAFE_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_.-]+")\n',
        'SAFE_IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_.-]+")\n'
        'TARGET_EVIDENCE_BUDGET_USDC = 100\n'
        'TARGET_COLOR_SCOPE = "canonical_100_usdc_final_evaluation"\n',
    )
    changed |= replace_exact(
        "src/ethusdc_bot/shadow/adoption.py",
        '''    candidate = json.loads(json.dumps(report["candidate"], allow_nan=False))\n    deployment = {\n''',
        '''    candidate = json.loads(json.dumps(report["candidate"], allow_nan=False))\n    if deployment_budget_usdc == TARGET_EVIDENCE_BUDGET_USDC:\n        deployment_target_status = (\n            "verified" if assessment.target_reached else "below_target"\n        )\n    else:\n        deployment_target_status = "unverified_scaling"\n    deployment_reason_codes = list(assessment.reason_codes)\n    if deployment_target_status == "unverified_scaling":\n        deployment_reason_codes.append("deployment_budget_scaling_unverified")\n\n    deployment = {\n''',
    )
    changed |= replace_exact(
        "src/ethusdc_bot/shadow/adoption.py",
        '''        "assessment": {\n            "color": assessment.color,\n            "shadow_eligible": True,\n            "target_reached": assessment.target_reached,\n            "live_eligible": False,\n            "reason_codes": list(assessment.reason_codes),\n        },\n''',
        '''        "assessment": {\n            "color": assessment.color,\n            "color_scope": TARGET_COLOR_SCOPE,\n            "shadow_eligible": True,\n            "target_reached": assessment.target_reached,\n            "target_evidence_budget_usdc": TARGET_EVIDENCE_BUDGET_USDC,\n            "deployment_budget_usdc": deployment_budget_usdc,\n            "deployment_target_usdc_per_day": (\n                portfolio_policy.target_guidance.desired_net_usdc_per_day\n            ),\n            "deployment_target_status": deployment_target_status,\n            "deployment_target_reached": deployment_target_status == "verified",\n            "live_eligible": False,\n            "reason_codes": deployment_reason_codes,\n        },\n''',
    )

    changed |= replace_exact(
        "src/ethusdc_bot/shadow/schema.py",
        '''ASSESSMENT_KEYS = {\n    "color",\n    "shadow_eligible",\n    "target_reached",\n    "live_eligible",\n    "reason_codes",\n}\n''',
        '''ASSESSMENT_KEYS = {\n    "color",\n    "color_scope",\n    "shadow_eligible",\n    "target_reached",\n    "target_evidence_budget_usdc",\n    "deployment_budget_usdc",\n    "deployment_target_usdc_per_day",\n    "deployment_target_status",\n    "deployment_target_reached",\n    "live_eligible",\n    "reason_codes",\n}\n''',
    )
    changed |= replace_exact(
        "src/ethusdc_bot/shadow/schema.py",
        '''    assessment = _mapping(root["assessment"], "shadow_deployment.assessment")\n    _exact_keys(assessment, ASSESSMENT_KEYS, "shadow_deployment.assessment")\n    color = assessment.get("color")\n    if color not in {"green", "yellow"}:\n        raise ShadowSchemaError("shadow_deployment.assessment.color must be green or yellow")\n    _literal(assessment, "shadow_eligible", True, "shadow_deployment.assessment")\n    _literal(assessment, "live_eligible", False, "shadow_deployment.assessment")\n    _literal(assessment, "target_reached", color == "green", "shadow_deployment.assessment")\n    reasons = assessment.get("reason_codes")\n    if not isinstance(reasons, list) or not reasons or any(not isinstance(item, str) or not item for item in reasons):\n        raise ShadowSchemaError("shadow_deployment.assessment.reason_codes must be a non-empty string list")\n''',
        '''    assessment = _mapping(root["assessment"], "shadow_deployment.assessment")\n    _exact_keys(assessment, ASSESSMENT_KEYS, "shadow_deployment.assessment")\n    color = assessment.get("color")\n    if color not in {"green", "yellow"}:\n        raise ShadowSchemaError("shadow_deployment.assessment.color must be green or yellow")\n    _literal(\n        assessment,\n        "color_scope",\n        "canonical_100_usdc_final_evaluation",\n        "shadow_deployment.assessment",\n    )\n    _literal(assessment, "shadow_eligible", True, "shadow_deployment.assessment")\n    _literal(assessment, "live_eligible", False, "shadow_deployment.assessment")\n    _literal(assessment, "target_reached", color == "green", "shadow_deployment.assessment")\n    _literal(\n        assessment,\n        "target_evidence_budget_usdc",\n        100,\n        "shadow_deployment.assessment",\n    )\n    _literal(\n        assessment,\n        "deployment_budget_usdc",\n        policy.deployment_budget_usdc,\n        "shadow_deployment.assessment",\n    )\n    _literal(\n        assessment,\n        "deployment_target_usdc_per_day",\n        policy.target_guidance.desired_net_usdc_per_day,\n        "shadow_deployment.assessment",\n    )\n    if policy.deployment_budget_usdc == 100:\n        expected_target_status = "verified" if color == "green" else "below_target"\n    else:\n        expected_target_status = "unverified_scaling"\n    _literal(\n        assessment,\n        "deployment_target_status",\n        expected_target_status,\n        "shadow_deployment.assessment",\n    )\n    _literal(\n        assessment,\n        "deployment_target_reached",\n        expected_target_status == "verified",\n        "shadow_deployment.assessment",\n    )\n    reasons = assessment.get("reason_codes")\n    if not isinstance(reasons, list) or not reasons or any(not isinstance(item, str) or not item for item in reasons):\n        raise ShadowSchemaError("shadow_deployment.assessment.reason_codes must be a non-empty string list")\n    if (\n        expected_target_status == "unverified_scaling"\n        and "deployment_budget_scaling_unverified" not in reasons\n    ):\n        raise ShadowSchemaError(\n            "shadow_deployment.assessment must disclose unverified budget scaling"\n        )\n''',
    )

    changed |= replace_exact(
        "tests/unit/test_shadow_schema.py",
        '''        "assessment": {\n            "color": "green",\n            "shadow_eligible": True,\n            "target_reached": True,\n            "live_eligible": False,\n            "reason_codes": ["all_quality_gates_passed"],\n        },\n''',
        '''        "assessment": {\n            "color": "green",\n            "color_scope": "canonical_100_usdc_final_evaluation",\n            "shadow_eligible": True,\n            "target_reached": True,\n            "target_evidence_budget_usdc": 100,\n            "deployment_budget_usdc": 500,\n            "deployment_target_usdc_per_day": 15.0,\n            "deployment_target_status": "unverified_scaling",\n            "deployment_target_reached": False,\n            "live_eligible": False,\n            "reason_codes": [\n                "all_quality_gates_passed",\n                "deployment_budget_scaling_unverified",\n            ],\n        },\n''',
    )
    changed |= replace_exact(
        "tests/unit/test_shadow_adoption.py",
        '''    assert deployment["assessment"]["live_eligible"] is False\n    assert state["phase"] == "adopted_stopped"\n''',
        '''    assert deployment["assessment"]["live_eligible"] is False\n    assert deployment["assessment"]["color_scope"] == (\n        "canonical_100_usdc_final_evaluation"\n    )\n    assert deployment["assessment"]["target_evidence_budget_usdc"] == 100\n    assert deployment["assessment"]["deployment_budget_usdc"] == budget\n    assert deployment["assessment"]["deployment_target_usdc_per_day"] == {\n        100: 3.0,\n        200: 6.0,\n        500: 15.0,\n        1000: 30.0,\n    }[budget]\n    if budget == 100:\n        assert deployment["assessment"]["deployment_target_status"] == "verified"\n        assert deployment["assessment"]["deployment_target_reached"] is True\n    else:\n        assert deployment["assessment"]["deployment_target_status"] == (\n            "unverified_scaling"\n        )\n        assert deployment["assessment"]["deployment_target_reached"] is False\n        assert "deployment_budget_scaling_unverified" in deployment["assessment"][\n            "reason_codes"\n        ]\n    assert state["phase"] == "adopted_stopped"\n''',
    )
    changed |= replace_exact(
        "tests/unit/test_shadow_adoption.py",
        '''    assert result.deployment["assessment"]["live_eligible"] is False\n    assert result.deployment["safety"]["live"] == "locked"\n''',
        '''    assert result.deployment["assessment"]["live_eligible"] is False\n    assert result.deployment["assessment"]["deployment_target_status"] == (\n        "below_target"\n    )\n    assert result.deployment["assessment"]["deployment_target_reached"] is False\n    assert result.deployment["safety"]["live"] == "locked"\n''',
    )

    changed |= replace_exact(
        "src/ethusdc_bot/ui/dashboard_state.py",
        '''            "api_keys_used": False,\n        }\n    deployment_dir = deployments[-1]\n''',
        '''            "api_keys_used": False,\n            "source_assessment_color": "none",\n            "target_evidence_budget_usdc": 100,\n            "deployment_target_usdc_per_day": None,\n            "deployment_target_status": "not_available",\n            "deployment_target_reached": False,\n        }\n    deployment_dir = deployments[-1]\n''',
    )
    changed |= replace_exact(
        "src/ethusdc_bot/ui/dashboard_state.py",
        '''            "api_keys_used": False,\n        }\n    return {\n        "status": "valid",\n''',
        '''            "api_keys_used": False,\n            "source_assessment_color": "none",\n            "target_evidence_budget_usdc": 100,\n            "deployment_target_usdc_per_day": None,\n            "deployment_target_status": "integrity_error",\n            "deployment_target_reached": False,\n        }\n    return {\n        "status": "valid",\n''',
    )
    changed |= replace_exact(
        "src/ethusdc_bot/ui/dashboard_state.py",
        '''        "api_keys_used": False,\n    }\n\n\ndef collect_inventory_status''',
        '''        "api_keys_used": False,\n        "source_assessment_color": deployment["assessment"]["color"],\n        "target_evidence_budget_usdc": deployment["assessment"][\n            "target_evidence_budget_usdc"\n        ],\n        "deployment_target_usdc_per_day": deployment["assessment"][\n            "deployment_target_usdc_per_day"\n        ],\n        "deployment_target_status": deployment["assessment"][\n            "deployment_target_status"\n        ],\n        "deployment_target_reached": deployment["assessment"][\n            "deployment_target_reached"\n        ],\n    }\n\n\ndef collect_inventory_status''',
    )

    print("budget evidence scope changed files" if changed else "budget evidence scope already applied")


if __name__ == "__main__":
    main()
