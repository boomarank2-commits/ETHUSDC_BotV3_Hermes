"""Tests for the pure trailing-only context veto engine."""

from __future__ import annotations

from dataclasses import replace

import pytest

from ethusdc_bot.backtest.context_features import (
    CONTEXT_POLICY_VERSION,
    ContextPolicyError,
    ContextVetoPolicy,
    evaluate_context_veto,
    validate_context_against_trade_candles,
)
from ethusdc_bot.backtest.data_loader import (
    AlignedMarketCandles,
    Candle,
    DataLoadError,
)


def _series(closes: list[float], *, start: int = 1_700_000_000_000) -> tuple[Candle, ...]:
    return tuple(
        Candle(
            open_time=start + index * 60_000,
            open=close,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=1.0,
        )
        for index, close in enumerate(closes)
    )


def _context(
    *,
    eth: list[float] | None = None,
    btc: list[float] | None = None,
    ratio: list[float] | None = None,
) -> AlignedMarketCandles:
    eth_values = eth or [100.0, 100.2, 100.4, 100.6, 100.8, 101.0]
    btc_values = btc or [100.0, 100.1, 100.2, 100.3, 100.4, 100.5]
    ratio_values = ratio or [1.0, 1.001, 1.002, 1.003, 1.004, 1.005]
    return AlignedMarketCandles(
        ethusdc=_series(eth_values),
        btcusdc=_series(btc_values),
        ethbtc=_series(ratio_values),
    )


def _policy(**overrides: object) -> ContextVetoPolicy:
    values: dict[str, object] = {
        "btc_trend_lookback": 3,
        "btc_min_trend_bps": -10.0,
        "btc_volatility_lookback": 3,
        "btc_max_volatility_bps": 100.0,
        "ethbtc_trend_lookback": 3,
        "ethbtc_min_trend_bps": -10.0,
    }
    values.update(overrides)
    return ContextVetoPolicy(**values)  # type: ignore[arg-type]


def test_context_policy_is_namespaced_and_immutable() -> None:
    policy = ContextVetoPolicy.from_candidate_params(
        {
            "context_btc_trend_lookback": 60,
            "context_btc_min_trend_bps": -20,
            "context_btc_volatility_lookback": 30,
            "context_btc_max_volatility_bps": 75,
            "context_ethbtc_trend_lookback": 90,
            "context_ethbtc_min_trend_bps": -5,
            "threshold_bps": 42,
        }
    )

    assert policy.btc_trend_lookback == 60
    assert policy.btc_min_trend_bps == -20.0
    assert policy.btc_volatility_lookback == 30
    assert policy.btc_max_volatility_bps == 75.0
    assert policy.ethbtc_trend_lookback == 90
    assert policy.ethbtc_min_trend_bps == -5.0
    assert policy.warmup_candles == 90
    assert policy.to_dict()["policy_version"] == CONTEXT_POLICY_VERSION
    with pytest.raises(Exception):
        policy.btc_trend_lookback = 2  # type: ignore[misc]


def test_policy_rejects_invalid_or_nonfinite_values() -> None:
    with pytest.raises(ContextPolicyError, match="at least 2"):
        ContextVetoPolicy(btc_trend_lookback=1)
    with pytest.raises(ContextPolicyError, match="positive"):
        ContextVetoPolicy(btc_max_volatility_bps=0)
    with pytest.raises(ContextPolicyError, match="finite"):
        ContextVetoPolicy(ethbtc_min_trend_bps=float("nan"))
    with pytest.raises(ContextPolicyError, match="must be an integer"):
        ContextVetoPolicy.from_candidate_params(
            {"context_btc_trend_lookback": 30.5}
        )


def test_warmup_fails_closed_without_feature_values() -> None:
    decision = evaluate_context_veto(_context(), 2, _policy())

    assert decision.allowed is False
    assert decision.reason == "context_warmup"
    assert decision.btc_trend_bps is None
    assert decision.btc_volatility_bps is None
    assert decision.ethbtc_trend_bps is None
    assert decision.may_create_signal is False
    assert decision.may_submit_order is False


def test_btc_downtrend_vetoes_existing_base_signal() -> None:
    decision = evaluate_context_veto(
        _context(btc=[100.0, 99.9, 99.8, 99.7, 99.6, 99.5]),
        5,
        _policy(btc_min_trend_bps=-5.0),
    )

    assert decision.allowed is False
    assert decision.reason == "context_veto_btc_trend"
    assert decision.btc_trend_bps is not None
    assert decision.btc_trend_bps < -5.0


def test_btc_volatility_veto_is_evaluated_after_trend() -> None:
    decision = evaluate_context_veto(
        _context(btc=[100.0, 100.1, 99.0, 101.0, 99.5, 101.5]),
        5,
        _policy(btc_min_trend_bps=-1_000.0, btc_max_volatility_bps=50.0),
    )

    assert decision.allowed is False
    assert decision.reason == "context_veto_btc_volatility"
    assert decision.btc_volatility_bps is not None
    assert decision.btc_volatility_bps > 50.0


def test_ethbtc_relative_weakness_vetoes_after_btc_checks_pass() -> None:
    decision = evaluate_context_veto(
        _context(ratio=[1.0, 0.999, 0.998, 0.997, 0.996, 0.995]),
        5,
        _policy(ethbtc_min_trend_bps=-5.0),
    )

    assert decision.allowed is False
    assert decision.reason == "context_veto_ethbtc_relative_strength"
    assert decision.ethbtc_trend_bps is not None
    assert decision.ethbtc_trend_bps < -5.0


def test_context_allows_when_all_trailing_checks_pass() -> None:
    decision = evaluate_context_veto(_context(), 5, _policy())

    assert decision.allowed is True
    assert decision.reason == "context_allowed"
    assert decision.open_time == _context().ethusdc[5].open_time
    assert decision.uses_entry_time_trailing_data_only is True
    assert decision.may_create_signal is False
    assert decision.may_submit_order is False


def test_future_context_changes_cannot_change_past_decision() -> None:
    original = _context(
        eth=[100.0] * 8,
        btc=[100.0, 100.1, 100.2, 100.3, 100.4, 100.5, 100.6, 100.7],
        ratio=[1.0, 1.001, 1.002, 1.003, 1.004, 1.005, 1.006, 1.007],
    )
    changed_future_btc = list(candle.close for candle in original.btcusdc)
    changed_future_ratio = list(candle.close for candle in original.ethbtc)
    changed_future_btc[6:] = [50.0, 200.0]
    changed_future_ratio[6:] = [0.5, 2.0]
    future_changed = AlignedMarketCandles(
        ethusdc=original.ethusdc,
        btcusdc=_series(changed_future_btc),
        ethbtc=_series(changed_future_ratio),
    )

    first = evaluate_context_veto(original, 5, _policy())
    second = evaluate_context_veto(future_changed, 5, _policy())

    assert first == second


def test_trade_candle_alignment_must_match_context_exactly() -> None:
    context = _context()
    validate_context_against_trade_candles(context.ethusdc, context)

    with pytest.raises(DataLoadError, match="equal length"):
        validate_context_against_trade_candles(context.ethusdc[:-1], context)
    shifted = list(context.ethusdc)
    shifted[2] = replace(shifted[2], open_time=shifted[2].open_time + 60_000)
    with pytest.raises(DataLoadError, match="timestamps differ"):
        validate_context_against_trade_candles(shifted, context)


def test_context_decision_rejects_invalid_index_and_types() -> None:
    context = _context()
    with pytest.raises(IndexError):
        evaluate_context_veto(context, -1, _policy())
    with pytest.raises(IndexError):
        evaluate_context_veto(context, context.candle_count, _policy())
    with pytest.raises(ContextPolicyError, match="policy"):
        evaluate_context_veto(context, 3, object())  # type: ignore[arg-type]
