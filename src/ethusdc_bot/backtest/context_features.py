"""Pure trailing-only BTCUSDC/ETHBTC veto features for ETHUSDC signals.

This module can only confirm or reject an already-existing ETHUSDC base signal.
It cannot create a signal, place an order, access an account, or read files.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any, Final, Mapping, Sequence

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle, DataLoadError


CONTEXT_POLICY_VERSION: Final = "context_veto_v1"
CONTEXT_DECISION_VERSION: Final = 1


class ContextPolicyError(ValueError):
    """Raised when context policy parameters are unsafe or invalid."""


@dataclass(frozen=True)
class ContextVetoPolicy:
    """Immutable trailing-only thresholds for context confirmation."""

    btc_trend_lookback: int = 240
    btc_min_trend_bps: float = -25.0
    btc_volatility_lookback: int = 120
    btc_max_volatility_bps: float = 80.0
    ethbtc_trend_lookback: int = 240
    ethbtc_min_trend_bps: float = -15.0

    def __post_init__(self) -> None:
        for name in (
            "btc_trend_lookback",
            "btc_volatility_lookback",
            "ethbtc_trend_lookback",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 2:
                raise ContextPolicyError(f"{name} must be an integer of at least 2")
        for name in (
            "btc_min_trend_bps",
            "btc_max_volatility_bps",
            "ethbtc_min_trend_bps",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ContextPolicyError(f"{name} must be a finite number")
            if not isfinite(float(value)):
                raise ContextPolicyError(f"{name} must be a finite number")
        if self.btc_max_volatility_bps <= 0:
            raise ContextPolicyError("btc_max_volatility_bps must be positive")

        object.__setattr__(self, "btc_min_trend_bps", float(self.btc_min_trend_bps))
        object.__setattr__(
            self,
            "btc_max_volatility_bps",
            float(self.btc_max_volatility_bps),
        )
        object.__setattr__(
            self,
            "ethbtc_min_trend_bps",
            float(self.ethbtc_min_trend_bps),
        )

    @classmethod
    def from_candidate_params(cls, params: Mapping[str, Any]) -> "ContextVetoPolicy":
        """Build policy from namespaced candidate fields only."""

        return cls(
            btc_trend_lookback=_integer_param(
                params, "context_btc_trend_lookback", cls.btc_trend_lookback
            ),
            btc_min_trend_bps=_number_param(
                params, "context_btc_min_trend_bps", cls.btc_min_trend_bps
            ),
            btc_volatility_lookback=_integer_param(
                params,
                "context_btc_volatility_lookback",
                cls.btc_volatility_lookback,
            ),
            btc_max_volatility_bps=_number_param(
                params,
                "context_btc_max_volatility_bps",
                cls.btc_max_volatility_bps,
            ),
            ethbtc_trend_lookback=_integer_param(
                params,
                "context_ethbtc_trend_lookback",
                cls.ethbtc_trend_lookback,
            ),
            ethbtc_min_trend_bps=_number_param(
                params,
                "context_ethbtc_min_trend_bps",
                cls.ethbtc_min_trend_bps,
            ),
        )

    @property
    def warmup_candles(self) -> int:
        return max(
            self.btc_trend_lookback,
            self.btc_volatility_lookback,
            self.ethbtc_trend_lookback,
        )

    def to_dict(self) -> dict[str, Any]:
        return {"policy_version": CONTEXT_POLICY_VERSION, **asdict(self)}


@dataclass(frozen=True)
class ContextDecision:
    """Transparent decision for one already-existing ETHUSDC base signal."""

    allowed: bool
    reason: str
    index: int
    open_time: int
    policy_version: str
    btc_trend_bps: float | None
    btc_volatility_bps: float | None
    ethbtc_trend_bps: float | None
    uses_entry_time_trailing_data_only: bool = True
    may_create_signal: bool = False
    may_submit_order: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_context_against_trade_candles(
    trade_candles: Sequence[Candle], context: AlignedMarketCandles
) -> None:
    """Require exact ETHUSDC timestamp identity with the context bundle."""

    if not isinstance(context, AlignedMarketCandles):
        raise DataLoadError("market_context must be AlignedMarketCandles")
    if len(trade_candles) != context.candle_count:
        raise DataLoadError(
            "ETHUSDC simulation candles and market context must have equal length"
        )
    expected = tuple(candle.open_time for candle in trade_candles)
    if expected != context.open_times:
        raise DataLoadError(
            "ETHUSDC simulation candles and market context timestamps differ"
        )


def evaluate_context_veto(
    context: AlignedMarketCandles,
    index: int,
    policy: ContextVetoPolicy,
) -> ContextDecision:
    """Evaluate trailing context for a base signal at one closed-candle index."""

    if not isinstance(context, AlignedMarketCandles):
        raise DataLoadError("context must be AlignedMarketCandles")
    if not isinstance(policy, ContextVetoPolicy):
        raise ContextPolicyError("policy must be ContextVetoPolicy")
    if type(index) is not int or index < 0 or index >= context.candle_count:
        raise IndexError("context index is outside the aligned candle range")

    open_time = context.ethusdc[index].open_time
    if index < policy.warmup_candles:
        return ContextDecision(
            allowed=False,
            reason="context_warmup",
            index=index,
            open_time=open_time,
            policy_version=CONTEXT_POLICY_VERSION,
            btc_trend_bps=None,
            btc_volatility_bps=None,
            ethbtc_trend_bps=None,
        )

    btc_trend = _trend_bps(context.btcusdc, index, policy.btc_trend_lookback)
    btc_volatility = _volatility_bps(
        context.btcusdc,
        index,
        policy.btc_volatility_lookback,
    )
    ethbtc_trend = _trend_bps(
        context.ethbtc,
        index,
        policy.ethbtc_trend_lookback,
    )

    if btc_trend < policy.btc_min_trend_bps:
        reason = "context_veto_btc_trend"
    elif btc_volatility > policy.btc_max_volatility_bps:
        reason = "context_veto_btc_volatility"
    elif ethbtc_trend < policy.ethbtc_min_trend_bps:
        reason = "context_veto_ethbtc_relative_strength"
    else:
        reason = "context_allowed"

    return ContextDecision(
        allowed=reason == "context_allowed",
        reason=reason,
        index=index,
        open_time=open_time,
        policy_version=CONTEXT_POLICY_VERSION,
        btc_trend_bps=round(btc_trend, 10),
        btc_volatility_bps=round(btc_volatility, 10),
        ethbtc_trend_bps=round(ethbtc_trend, 10),
    )


def _trend_bps(candles: Sequence[Candle], index: int, lookback: int) -> float:
    reference = float(candles[index - lookback].close)
    current = float(candles[index].close)
    return ((current / reference) - 1.0) * 10_000 if reference else 0.0


def _volatility_bps(
    candles: Sequence[Candle], index: int, lookback: int
) -> float:
    start = index - lookback + 1
    moves: list[float] = []
    for cursor in range(start, index + 1):
        previous = float(candles[cursor - 1].close)
        current = float(candles[cursor].close)
        if previous:
            moves.append(abs(current / previous - 1.0) * 10_000)
    return sum(moves) / len(moves) if moves else 0.0


def _integer_param(params: Mapping[str, Any], key: str, default: int) -> int:
    value = params.get(key, default)
    if type(value) is not int:
        raise ContextPolicyError(f"{key} must be an integer")
    return value


def _number_param(
    params: Mapping[str, Any], key: str, default: float
) -> float:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContextPolicyError(f"{key} must be a finite number")
    return float(value)


__all__ = [
    "CONTEXT_DECISION_VERSION",
    "CONTEXT_POLICY_VERSION",
    "ContextDecision",
    "ContextPolicyError",
    "ContextVetoPolicy",
    "evaluate_context_veto",
    "validate_context_against_trade_candles",
]
