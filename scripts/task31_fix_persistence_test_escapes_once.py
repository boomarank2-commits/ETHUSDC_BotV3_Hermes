from pathlib import Path

path = Path("scripts/task31_harden_final_persistence_once.py")
text = path.read_text(encoding="utf-8")
replacements = [
    (
        r'''    malformed = report.canonical_json[:-1] + ',"report_id":"duplicate"}\n' ''',
        r'''    malformed = report.canonical_json[:-1] + ',"report_id":"duplicate"}\\n' ''',
    ),
    (
        r'''    orphan.write_text("{}\n", encoding="utf-8")''',
        r'''    orphan.write_text("{}\\n", encoding="utf-8")''',
    ),
    (
        r'''    path.write_text(raw[:-1] + ',"registration_id":"duplicate"}\n', encoding="utf-8")''',
        r'''    path.write_text(raw[:-1] + ',"registration_id":"duplicate"}\\n', encoding="utf-8")''',
    ),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"persistence test escape replacement mismatch: {old!r}")
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
