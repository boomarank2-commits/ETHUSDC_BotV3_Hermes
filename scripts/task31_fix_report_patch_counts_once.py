from pathlib import Path

path = Path("scripts/task31_bind_final_report_registration_once.py")
text = path.read_text(encoding="utf-8")
old = '''for old, new in call_replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"final report call replacement count={count}: {old[:90]!r}")
    text = text.replace(old, new)
'''
new = '''for old, new in call_replacements:
    count = text.count(old)
    if old.startswith("            report_path,"):
        expected = 2
    elif old.startswith("        report_path,"):
        expected = 0
    else:
        expected = 1
    if count != expected:
        raise SystemExit(
            f"final report call replacement count={count} expected={expected}: "
            f"{old[:90]!r}"
        )
    text = text.replace(old, new)
'''
if text.count(old) != 1:
    raise SystemExit("final report patch-count loop replacement mismatch")
path.write_text(text.replace(old, new), encoding="utf-8")
