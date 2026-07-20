"""Task-29 contract, public-surface, and safety-lock regressions."""
from __future__ import annotations

from pathlib import Path

from ethusdc_bot.protocol_v3 import research_challenger
from ethusdc_bot.protocol_v3 import research_challenger_api

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_task29_contract_and_public_api_are_exact() -> None:
    contract = research_challenger.load_research_challenger_contract(REPO_ROOT)

    assert contract["controller_policy"] == {
        "task28_typed_provenance_required": True,
        "manual_start_only": True,
        "ethusdc_only": True,
        "btcusdc_and_ethbtc_context_only": True,
        "exact_closed_three_market_bar_required": True,
        "one_open_lot_maximum": True,
        "refresh_and_replay_must_be_idempotent": True,
        "end_of_feed_may_not_liquidate": True,
    }
    assert contract["evidence_policy"] == {
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "statistically_supported": False,
        "canonical_adoption_eligible": False,
        "protocol_v3_final_status": False,
    }
    assert research_challenger_api.__all__ == research_challenger.__all__


def test_task29_surface_has_no_order_or_private_runtime_dependency() -> None:
    source = (REPO_ROOT / "src/ethusdc_bot/protocol_v3/research_challenger.py").read_text(
        encoding="utf-8"
    )
    forbidden_imports = (
        "ethusdc_bot.live",
        "ethusdc_bot.paper",
        "ethusdc_bot.shadow.adoption",
        "binance_client",
        "order_adapter",
        "account_reader",
    )

    assert all(item not in source for item in forbidden_imports)
    contract = research_challenger.load_research_challenger_contract(REPO_ROOT)
    assert contract["safety"] == {
        "api_keys": "forbidden",
        "private_endpoints": "forbidden",
        "orders": "locked",
        "paper": "locked",
        "testtrade": "locked",
        "live": "locked",
        "trading_api": "forbidden",
        "adopt_for_shadow": "forbidden",
    }
