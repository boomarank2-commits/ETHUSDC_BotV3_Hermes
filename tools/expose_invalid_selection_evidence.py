"""Expose the exact invalid selection-evidence paths in the smoke failure."""

from pathlib import Path


path = Path(__file__).resolve().parents[1] / "tests/integration/test_research_loop_protocol_v2_smoke.py"
text = path.read_text(encoding="utf-8")
old = '''    assert gate["status"] == "fail_gate", gate["missing_evidence"]\n    assert gate["missing_evidence"] == []\n    assert gate["invalid_evidence"] == []\n'''
new = '''    assert gate["status"] in {"fail_gate", "fail_invalid_evidence"}\n    assert gate["missing_evidence"] == []\n    assert gate["invalid_evidence"] == [], gate["invalid_evidence"]\n'''
if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
elif new not in text:
    raise RuntimeError("expected diagnostic assertion fragment not found")
