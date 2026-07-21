from pathlib import Path

path = Path("tests/unit/test_protocol_v3_pipeline_final_attestation.py")
text = path.read_text(encoding="utf-8")
old = '''            bound_hindsight_benchmarks=state["bound"],
            completed_at_utc=state["completed_at"],
'''
new = '''            bound_hindsight_benchmarks=state["bound"],
            source_repository_root=REPO_ROOT,
            completed_at_utc=state["completed_at"],
'''
if text.count(old) != 1:
    raise SystemExit("identity fixture repository argument replacement mismatch")
path.write_text(text.replace(old, new), encoding="utf-8")
