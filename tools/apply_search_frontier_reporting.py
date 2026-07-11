"""Integrate Search Frontier v2 metadata into research-cycle reports."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_exact(relative_path: str, old: str, new: str) -> None:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    if old in text:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"patched {relative_path}")
        return
    if new in text:
        print(f"already patched {relative_path}")
        return
    raise RuntimeError(f"expected source fragment not found in {relative_path}")


def main() -> None:
    replace_exact(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        '''    generate_search_space,\n    next_search_space_state,\n    select_candidates_for_testing,\n''',
        '''    generate_search_space,\n    next_search_space_state,\n    search_frontier_summary,\n    select_candidates_for_testing,\n''',
    )
    replace_exact(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        '''        generated = generate_search_space(state, max_candidates=config.max_candidates_per_cycle)\n        generated_rows = [\n''',
        '''        generated = generate_search_space(state, max_candidates=config.max_candidates_per_cycle)\n        frontier_summary = search_frontier_summary(\n            generated,\n            state,\n            requested_cap=config.max_candidates_per_cycle,\n        )\n        generated_rows = [\n''',
    )
    replace_exact(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        '''        # Context candidates remain generated for transparent inventory, but are\n        # ineligible until BTCUSDC/ETHBTC data are actually wired into signals.\n        supported_rows = [row for row in generated_rows if row["candidate"].family != "context_filter"]\n''',
        '''        # Search Frontier v2 contains only simulator-backed ETHUSDC families.\n        # Context candidates return only after aligned BTCUSDC/ETHBTC data is\n        # actually consumed by the signal engine.\n        supported_rows = list(generated_rows)\n''',
    )
    replace_exact(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        '''            reason = "context_data_not_integrated" if row["candidate"].family == "context_filter" else "tested_stage_budget"\n            not_tested.append({"candidate_id": row["candidate_id"], "reason": reason})\n''',
        '''            not_tested.append(\n                {"candidate_id": row["candidate_id"], "reason": "tested_stage_budget"}\n            )\n''',
    )
    replace_exact(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        '''            "generated_candidate_inventory": generated_inventory,\n            "resource_budget": _resource_budget(config),\n''',
        '''            "generated_candidate_inventory": generated_inventory,\n            "search_frontier": frontier_summary,\n            "resource_budget": _resource_budget(config),\n''',
    )

    replace_exact(
        "tests/integration/test_research_loop_protocol_v2_smoke.py",
        '''    assert cycle["generated_candidates"] == len(cycle["candidate_stage_ids"]["generated"])\n    assert cycle["tested_candidates"] == len(cycle["candidate_stage_ids"]["tested"])\n''',
        '''    assert cycle["generated_candidates"] == len(cycle["candidate_stage_ids"]["generated"])\n    assert cycle["search_frontier"]["generator_version"] == "ethusdc_frontier_v2"\n    assert cycle["search_frontier"]["generated_count"] == cycle["generated_candidates"]\n    assert cycle["search_frontier"]["context_candidates_enabled"] is False\n    assert cycle["search_frontier"]["uses_audit_or_holdout"] is False\n    assert cycle["tested_candidates"] == len(cycle["candidate_stage_ids"]["tested"])\n''',
    )
    replace_exact(
        "tests/integration/test_research_loop_protocol_v2_smoke.py",
        '''    assert cycle["resource_budget"]["generated_cap"] == 40\n    assert cycle["resource_budget"]["tested_cap"] == 12\n''',
        '''    assert cycle["resource_budget"]["generated_cap"] == 40\n    assert cycle["search_frontier"]["requested_cap"] == 40\n    assert cycle["search_frontier"]["generated_count"] == 40\n    assert sum(cycle["search_frontier"]["family_counts"].values()) == 40\n    assert cycle["search_frontier"]["context_disabled_reason"] == (\n        "real_context_market_data_not_integrated"\n    )\n    assert cycle["resource_budget"]["tested_cap"] == 12\n''',
    )


if __name__ == "__main__":
    main()
