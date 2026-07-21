from pathlib import Path

path = Path("src/ethusdc_bot/protocol_v3/pipeline_final_attestation.py")
text = path.read_text(encoding="utf-8")
old = '            or completed["outer_origin_selection_sha256"]\n'
new = '            or completed["origin_selection_sha256"]\n'
if text.count(old) != 1:
    raise SystemExit("attestation origin selection field replacement mismatch")
path.write_text(text.replace(old, new), encoding="utf-8")
