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

production_test = ROOT / "tests/integration/test_research_loop_protocol_v2_smoke.py"
text = production_test.read_text(encoding="utf-8")
for old, new in (
    (
        'assert cycle["resource_budget"]["parameter_evidence_candidate_days_cap"] == 7008',
        'assert cycle["resource_budget"]["parameter_evidence_candidate_days_cap"] == 10512',
    ),
    (
        'assert cycle["resource_budget"]["selection_total_candidate_days_cap"] == 24528',
        'assert cycle["resource_budget"]["selection_total_candidate_days_cap"] == 28032',
    ),
):
    if old not in text:
        raise SystemExit(f"expected production resource assertion not found: {old}")
    text = text.replace(old, new)
production_test.write_text(text, encoding="utf-8")

print("context disabled-reason and resource expectations updated")
