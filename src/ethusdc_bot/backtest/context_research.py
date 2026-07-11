"""Selection-only adapters for aligned ETHUSDC/BTCUSDC/ETHBTC research.

This module connects already-loaded, exactly aligned public candles to the
existing context-veto simulator path. It has no loader, account, key, network,
order, audit or final-holdout dependency.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Final, Sequence

from ethusdc_bot.backtest.context_features import (
    CONTEXT_POLICY_VERSION,
    ContextVetoPolicy,
)
from ethusdc_bot.backtest.data_loader import (
    EXPECTED_STEP_MS,
    AlignedMarketCandles,
    Candle,
    DataLoadError,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate


CONTEXT_RESEARCH_VERSION: Final = "context_research_v1"
CONTEXT_BASE_FAMILY_KEY: Final = "context_base_family"
_CONTEXT_POLICY_KEYS: Final = {
    "btc_trend_lookback": "context_btc_trend_lookback",
    "btc_min_trend_bps": "context_btc_min_trend_bps",
    "btc_volatility_lookback": "context_btc_volatility_lookback",
    "btc_max_volatility_bps": "context_btc_max_volatility_bps",
    "ethbtc_trend_lookback": "context_ethbtc_trend_lookback",
    "ethbtc_min_trend_bps": "context_ethbtc_min_trend_bps",
}


def slice_aligned_context(
    context: AlignedMarketCandles,
    trade_candles: Sequence[Candle],
) -> AlignedMarketCandles:
    """Return the exact aligned context slice for one ETHUSDC candle window.

    The aligned source and requested trade window must both be contiguous 1m
    sequences. No nearest-neighbour lookup, fill, interpolation or clipping is
    allowed. The arithmetic start index avoids building a million-element
    timestamp dictionary for each WFV/rolling/stress simulation.
    """

    if not isinstance(context, AlignedMarketCandles):
        raise DataLoadError("context must be AlignedMarketCandles")
    if not trade_candles:
        raise DataLoadError("context slice requires a non-empty ETHUSDC window")
    if context.candle_count <= 0:
        raise DataLoadError("aligned context is empty")

    _validate_contiguous_trade_window(trade_candles)
    first = int(trade_candles[0].open_time)
    source_first = int(context.ethusdc[0].open_time)
    offset_ms = first - source_first
    if offset_ms < 0 or offset_ms % EXPECTED_STEP_MS:
        raise DataLoadError("ETHUSDC window does not start on the aligned context timeline")
    start = offset_ms // EXPECTED_STEP_MS
    end = start + len(trade_candles)
    if end > context.candle_count:
        raise DataLoadError("ETHUSDC window exceeds the aligned context timeline")

    ethusdc = context.ethusdc[start:end]
    btcusdc = context.btcusdc[start:end]
    ethbtc = context.ethbtc[start:end]
    requested_times = tuple(int(candle.open_time) for candle in trade_candles)
    if tuple(candle.open_time for candle in ethusdc) != requested_times:
        raise DataLoadError("ETHUSDC window is not an exact aligned context slice")
    if tuple(candle.open_time for candle in btcusdc) != requested_times:
        raise DataLoadError("BTCUSDC context window is not exactly aligned")
    if tuple(candle.open_time for candle in ethbtc) != requested_times:
        raise DataLoadError("ETHBTC context window is not exactly aligned")
    return AlignedMarketCandles(
        ethusdc=tuple(ethusdc),
        btcusdc=tuple(btcusdc),
        ethbtc=tuple(ethbtc),
    )


def context_for_candidate(
    context: AlignedMarketCandles | None,
    trade_candles: Sequence[Candle],
    candidate: StrategyCandidate,
) -> AlignedMarketCandles | None:
    """Slice context only for `context_filter`; other families remain untouched."""

    if candidate.family != "context_filter":
        return None
    if context is None:
        raise DataLoadError("context_filter candidate requires aligned market context")
    return slice_aligned_context(context, trade_candles)


def wrap_candidate_with_context(
    base_candidate: StrategyCandidate,
    policy: ContextVetoPolicy,
) -> StrategyCandidate:
    """Wrap an existing ETHUSDC signal family with a trailing-only context veto.

    The original parameter map is preserved. `context_base_family` is separate
    from a base strategy's own `base_family` parameter, which is required for
    nested existing families such as `cooldown_fee_aware` and `session_filter`.
    """

    if not isinstance(base_candidate, StrategyCandidate):
        raise TypeError("base_candidate must be StrategyCandidate")
    if not isinstance(policy, ContextVetoPolicy):
        raise TypeError("policy must be ContextVetoPolicy")
    if base_candidate.family == "context_filter":
        raise ValueError("context_filter cannot wrap itself")
    symbol = str(base_candidate.params.get("symbol", "ETHUSDC"))
    if symbol != "ETHUSDC":
        raise ValueError("context research may wrap only ETHUSDC candidates")

    params = dict(base_candidate.params)
    params["symbol"] = "ETHUSDC"
    params[CONTEXT_BASE_FAMILY_KEY] = base_candidate.family
    policy_values = asdict(policy)
    for source_key, target_key in _CONTEXT_POLICY_KEYS.items():
        params[target_key] = policy_values[source_key]
    return StrategyCandidate("context_filter", params)


def context_policy_for_profile(profile: int) -> ContextVetoPolicy:
    """Return one fixed ex-ante context policy from a bounded seven-profile grid."""

    if type(profile) is not int or not 0 <= profile < 7:
        raise ValueError("context profile must be an integer from 0 through 6")
    return ContextVetoPolicy(
        btc_trend_lookback=(120, 180, 240, 360, 480, 720, 960)[profile],
        btc_min_trend_bps=(-50, -35, -25, -15, 0, 10, 20)[profile],
        btc_volatility_lookback=(60, 90, 120, 180, 240, 360, 480)[profile],
        btc_max_volatility_bps=(140, 115, 95, 80, 65, 55, 45)[profile],
        ethbtc_trend_lookback=(120, 180, 240, 360, 480, 720, 960)[profile],
        ethbtc_min_trend_bps=(-35, -25, -15, -10, 0, 5, 10)[profile],
    )


def context_research_provenance(
    context: AlignedMarketCandles,
    candidates: Sequence[StrategyCandidate],
) -> dict[str, Any]:
    """Return strict, non-performance provenance for one selection frontier."""

    if not isinstance(context, AlignedMarketCandles) or context.candle_count <= 0:
        raise DataLoadError("context provenance requires non-empty aligned candles")
    context_candidates = [row for row in candidates if row.family == "context_filter"]
    return {
        "integration_version": CONTEXT_RESEARCH_VERSION,
        "policy_version": CONTEXT_POLICY_VERSION,
        "enabled": True,
        "symbols": {
            "trade": "ETHUSDC",
            "context_only": ["BTCUSDC", "ETHBTC"],
        },
        "aligned_candle_count": context.candle_count,
        "first_open_time": context.ethusdc[0].open_time,
        "last_open_time": context.ethusdc[-1].open_time,
        "context_candidate_count": len(context_candidates),
        "context_direct_trigger_allowed": False,
        "context_may_only_confirm_or_veto_base_signal": True,
        "uses_audit_or_holdout": False,
        "target_used_as_parameter": False,
    }


def _validate_contiguous_trade_window(candles: Sequence[Candle]) -> None:
    previous: int | None = None
    for index, candle in enumerate(candles):
        if not isinstance(candle, Candle):
            raise DataLoadError(f"trade_candles[{index}] must be Candle")
        timestamp = int(candle.open_time)
        if previous is not None and timestamp - previous != EXPECTED_STEP_MS:
            raise DataLoadError("ETHUSDC context research window must be contiguous 1m data")
        previous = timestamp


__all__ = [
    "CONTEXT_BASE_FAMILY_KEY",
    "CONTEXT_RESEARCH_VERSION",
    "context_for_candidate",
    "context_policy_for_profile",
    "context_research_provenance",
    "slice_aligned_context",
    "wrap_candidate_with_context",
]
