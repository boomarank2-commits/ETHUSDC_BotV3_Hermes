from pathlib import Path

path = Path("src/ethusdc_bot/protocol_v3/pipeline_final.py")
text = path.read_text(encoding="utf-8")
replacements = [
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
