from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = "real_context_market_data_not_integrated"
NEW = "context_research_must_be_explicitly_enabled"

for relative in (
    "tests/integration/test_research_loop_protocol_v2_smoke.py",
    "tests/unit/test_search_frontier_v2.py",
):
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if OLD not in text:
        raise SystemExit(f"expected legacy context reason not found in {relative}")
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")

print("context disabled-reason expectations updated")
