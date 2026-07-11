"""Tests for the immutable fixed-lot portfolio policy."""

from dataclasses import FrozenInstanceError
import json

import pytest

from ethusdc_bot.portfolio import (
    PORTFOLIO_MODEL_VERSION,
    PortfolioPolicy,
    RESEARCH_PORTFOLIO_V1,
    canonical_portfolio_signature,
)


@pytest.mark.parametrize(
    ("budget", "expected_lots", "soft_drawdown", "acceptable", "desired"),
    [
        (100, 1, 15.0, 3.0, 3.0),
        (200, 2, 30.0, 5.0, 6.0),
        (500, 5, 75.0, 12.0, 15.0),
        (1000, 10, 150.0, 25.0, 30.0),
    ],
)
def test_allowed_budgets_derive_capacity_drawdown_and_guidance(
    budget: int,
    expected_lots: int,
    soft_drawdown: float,
    acceptable: float,
    desired: float,
) -> None:
    policy = PortfolioPolicy(deployment_budget_usdc=budget)

    assert policy.lot_notional_usdc == 100.0
    assert policy.max_concurrent_lots == expected_lots
    assert policy.soft_drawdown_limit_usdc == soft_drawdown
    assert policy.target_guidance.acceptable_net_usdc_per_day == acceptable
    assert policy.target_guidance.desired_net_usdc_per_day == desired


def test_reference_policy_fixes_costs_and_disables_compounding() -> None:
    assert RESEARCH_PORTFOLIO_V1.deployment_budget_usdc == 100
    assert RESEARCH_PORTFOLIO_V1.lot_notional_usdc == 100.0
    assert RESEARCH_PORTFOLIO_V1.compounding_enabled is False
    assert RESEARCH_PORTFOLIO_V1.baseline_fee_bps_per_side == 10.0
    assert RESEARCH_PORTFOLIO_V1.baseline_slippage_bps_per_side == 5.0


def test_policy_is_frozen() -> None:
    policy = PortfolioPolicy()

    with pytest.raises(FrozenInstanceError):
        policy.deployment_budget_usdc = 500  # type: ignore[misc]


@pytest.mark.parametrize(
    "bad_budget",
    [False, True, 0, 99, 101, 300, 250.0, "100", None, float("nan"), float("inf"), -float("inf")],
)
def test_rejects_bool_nonfinite_and_unapproved_budgets(bad_budget: object) -> None:
    with pytest.raises(ValueError, match="deployment_budget_usdc"):
        PortfolioPolicy(deployment_budget_usdc=bad_budget)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_lot",
    [False, True, 99, 101, "100", float("nan"), float("inf")],
)
def test_rejects_any_non_fixed_or_invalid_lot_size(bad_lot: object) -> None:
    with pytest.raises(ValueError, match="lot_notional_usdc"):
        PortfolioPolicy(lot_notional_usdc=bad_lot)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_value", [True, 0, 1, None, "false"])
def test_compounding_must_be_boolean_false(bad_value: object) -> None:
    with pytest.raises(ValueError, match="compounding_enabled"):
        PortfolioPolicy(compounding_enabled=bad_value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("baseline_fee_bps_per_side", 9.99),
        ("baseline_fee_bps_per_side", True),
        ("baseline_fee_bps_per_side", float("nan")),
        ("baseline_slippage_bps_per_side", 4.99),
        ("baseline_slippage_bps_per_side", False),
        ("baseline_slippage_bps_per_side", float("inf")),
        ("soft_drawdown_fraction", 0.16),
        ("soft_drawdown_fraction", True),
        ("soft_drawdown_fraction", float("nan")),
    ],
)
def test_cost_and_soft_drawdown_contract_cannot_be_changed(
    field: str, bad_value: object
) -> None:
    with pytest.raises(ValueError, match=field):
        PortfolioPolicy(**{field: bad_value})  # type: ignore[arg-type]


def test_drawdown_threshold_is_exposed_as_warning_only() -> None:
    policy = PortfolioPolicy(deployment_budget_usdc=100)

    assert policy.has_soft_drawdown_warning(15.0) is False
    assert policy.has_soft_drawdown_warning(16.0) is True
    assert policy.to_dict()["drawdown_limit_kind"] == "soft_warning_only"


@pytest.mark.parametrize("bad_drawdown", [True, -0.01, float("nan"), float("inf")])
def test_drawdown_warning_rejects_invalid_values(bad_drawdown: object) -> None:
    with pytest.raises(ValueError, match="max_drawdown_usdc"):
        PortfolioPolicy().has_soft_drawdown_warning(bad_drawdown)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("budget", "net_usdc_per_day", "expected"),
    [(100, 3.0, 3.0), (200, 5.0, 2.5), (500, 12.5, 2.5), (1000, 25.0, 2.5)],
)
def test_normalizes_daily_net_result_per_100_usdc(
    budget: int, net_usdc_per_day: float, expected: float
) -> None:
    policy = PortfolioPolicy(deployment_budget_usdc=budget)

    assert policy.normalized_net_usdc_per_day_per_100(net_usdc_per_day) == expected


@pytest.mark.parametrize("bad_value", [True, "3", None, float("nan"), float("inf")])
def test_normalization_rejects_nonfinite_and_non_numeric_values(bad_value: object) -> None:
    with pytest.raises(ValueError, match="net_usdc_per_day"):
        PortfolioPolicy().normalized_net_usdc_per_day_per_100(bad_value)  # type: ignore[arg-type]


def test_canonical_signature_is_stable_normalized_json() -> None:
    integer_input = PortfolioPolicy(deployment_budget_usdc=500, lot_notional_usdc=100)
    float_input = PortfolioPolicy(deployment_budget_usdc=500.0, lot_notional_usdc=100.0)

    first = canonical_portfolio_signature(integer_input)
    second = float_input.canonical_signature

    assert first == second
    assert first == canonical_portfolio_signature(integer_input)
    payload = json.loads(first)
    assert payload["model_version"] == PORTFOLIO_MODEL_VERSION
    assert payload["deployment_budget_usdc"] == 500
    assert payload["max_concurrent_lots"] == 5
    assert payload["compounding_enabled"] is False


def test_canonical_signature_changes_with_manual_budget() -> None:
    assert PortfolioPolicy(100).canonical_signature != PortfolioPolicy(200).canonical_signature


def test_signature_rejects_wrong_type() -> None:
    with pytest.raises(TypeError, match="PortfolioPolicy"):
        canonical_portfolio_signature({})  # type: ignore[arg-type]
