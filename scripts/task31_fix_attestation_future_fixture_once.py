from pathlib import Path

path = Path("tests/unit/test_protocol_v3_pipeline_final_attestation.py")
text = path.read_text(encoding="utf-8")
old = '''    original_builder = task23.boundaries.build_monthly_process_boundary_plan
    monkeypatch.setattr(
        task23.boundaries,
        "build_monthly_process_boundary_plan",
        lambda *_args, **_kwargs: future_plan,
    )
    base, plan, requests = task23.state.__wrapped__(tmp_path, monkeypatch)
    monkeypatch.setattr(
        task23.boundaries,
        "build_monthly_process_boundary_plan",
        original_builder,
    )
'''
new = '''    original_task23_builder = task23.boundaries.build_monthly_process_boundary_plan
    original_task13_builder = task23.support.build_monthly_process_boundary_plan
    monkeypatch.setattr(
        task23.boundaries,
        "build_monthly_process_boundary_plan",
        lambda *_args, **_kwargs: future_plan,
    )
    monkeypatch.setattr(
        task23.support,
        "build_monthly_process_boundary_plan",
        lambda *_args, **_kwargs: future_plan,
    )
    base, plan, requests = task23.state.__wrapped__(tmp_path, monkeypatch)
    monkeypatch.setattr(
        task23.boundaries,
        "build_monthly_process_boundary_plan",
        original_task23_builder,
    )
    monkeypatch.setattr(
        task23.support,
        "build_monthly_process_boundary_plan",
        original_task13_builder,
    )
'''
if text.count(old) != 1:
    raise SystemExit("future boundary fixture replacement mismatch")
path.write_text(text.replace(old, new), encoding="utf-8")
