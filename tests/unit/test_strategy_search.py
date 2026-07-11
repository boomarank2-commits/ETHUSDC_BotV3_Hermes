"""Guards for the deprecated strategy-search and holdout helpers."""

from __future__ import annotations

import pytest

from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.backtest.strategy_search import (
    TARGET_USDC_PER_DAY,
    evaluate_blindtest_once,
    run_strategy_search,
)


def test_legacy_strategy_search_is_disabled_before_any_evaluation():
    with pytest.raises(RuntimeError, match="disabled by Research Protocol v2"):
        run_strategy_search([], [])


def test_direct_blindtest_evaluation_is_disabled():
    candidate = StrategyCandidate("breakout", {"symbol": "ETHUSDC"})

    with pytest.raises(RuntimeError, match="sealed-holdout workflow is not implemented"):
        evaluate_blindtest_once(candidate, [], days=365)


def test_target_constant_remains_a_reporting_contract_only():
    assert TARGET_USDC_PER_DAY == 3.0
