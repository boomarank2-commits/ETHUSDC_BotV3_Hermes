"""Immutable fixed-lot portfolio contract for ETHUSDC research and shadow use.

The policy separates a manually selected deployment budget from the fixed
100 USDC notional of each logical lot.  It contains no account access, order
creation, compounding, or trading side effects.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from math import isfinite
from types import MappingProxyType
from typing import Any, Final, Mapping


PORTFOLIO_MODEL_VERSION: Final = "fixed_lot_portfolio_v1"
FIXED_LOT_NOTIONAL_USDC: Final = 100.0
ALLOWED_DEPLOYMENT_BUDGETS_USDC: Final = (100, 200, 500, 1000)
BASELINE_FEE_BPS_PER_SIDE: Final = 10.0
BASELINE_SLIPPAGE_BPS_PER_SIDE: Final = 5.0
SOFT_DRAWDOWN_FRACTION: Final = 0.15


@dataclass(frozen=True)
class DailyTargetGuidance:
    """Non-binding daily result guidance for a deployment budget."""

    acceptable_net_usdc_per_day: float
    desired_net_usdc_per_day: float


TARGET_GUIDANCE_BY_BUDGET_USDC: Final[Mapping[int, DailyTargetGuidance]] = (
    MappingProxyType(
        {
            100: DailyTargetGuidance(3.0, 3.0),
            200: DailyTargetGuidance(5.0, 6.0),
            500: DailyTargetGuidance(12.0, 15.0),
            1000: DailyTargetGuidance(25.0, 30.0),
        }
    )
)


@dataclass(frozen=True)
class PortfolioPolicy:
    """Validated execution-capacity policy with a fixed 100 USDC lot size.

    ``deployment_budget_usdc`` limits reserved entry notional.  Realized P&L
    never changes ``lot_notional_usdc`` or the derived concurrent-lot limit.
    The drawdown value is guidance only and is intentionally exposed as a
    warning rather than as a pass/fail gate.
    """

    deployment_budget_usdc: int = 100
    lot_notional_usdc: float = FIXED_LOT_NOTIONAL_USDC
    compounding_enabled: bool = False
    baseline_fee_bps_per_side: float = BASELINE_FEE_BPS_PER_SIDE
    baseline_slippage_bps_per_side: float = BASELINE_SLIPPAGE_BPS_PER_SIDE
    soft_drawdown_fraction: float = SOFT_DRAWDOWN_FRACTION

    def __post_init__(self) -> None:
        budget = _finite_number(
            self.deployment_budget_usdc, "deployment_budget_usdc"
        )
        if not budget.is_integer() or int(budget) not in ALLOWED_DEPLOYMENT_BUDGETS_USDC:
            raise ValueError(
                "deployment_budget_usdc must be exactly one of "
                f"{ALLOWED_DEPLOYMENT_BUDGETS_USDC}"
            )
        _require_fixed_number(
            self.lot_notional_usdc,
            FIXED_LOT_NOTIONAL_USDC,
            "lot_notional_usdc",
        )
        if self.compounding_enabled is not False:
            raise ValueError("compounding_enabled must remain false")
        _require_fixed_number(
            self.baseline_fee_bps_per_side,
            BASELINE_FEE_BPS_PER_SIDE,
            "baseline_fee_bps_per_side",
        )
        _require_fixed_number(
            self.baseline_slippage_bps_per_side,
            BASELINE_SLIPPAGE_BPS_PER_SIDE,
            "baseline_slippage_bps_per_side",
        )
        _require_fixed_number(
            self.soft_drawdown_fraction,
            SOFT_DRAWDOWN_FRACTION,
            "soft_drawdown_fraction",
        )

        # Normalize equivalent int/float inputs so serialization and signatures
        # remain byte-for-byte stable.
        object.__setattr__(self, "deployment_budget_usdc", int(budget))
        object.__setattr__(self, "lot_notional_usdc", FIXED_LOT_NOTIONAL_USDC)
        object.__setattr__(
            self, "baseline_fee_bps_per_side", BASELINE_FEE_BPS_PER_SIDE
        )
        object.__setattr__(
            self,
            "baseline_slippage_bps_per_side",
            BASELINE_SLIPPAGE_BPS_PER_SIDE,
        )
        object.__setattr__(self, "soft_drawdown_fraction", SOFT_DRAWDOWN_FRACTION)

    @property
    def max_concurrent_lots(self) -> int:
        return int(self.deployment_budget_usdc / self.lot_notional_usdc)

    @property
    def soft_drawdown_limit_usdc(self) -> float:
        return round(self.deployment_budget_usdc * self.soft_drawdown_fraction, 10)

    @property
    def target_guidance(self) -> DailyTargetGuidance:
        return TARGET_GUIDANCE_BY_BUDGET_USDC[self.deployment_budget_usdc]

    @property
    def canonical_signature(self) -> str:
        return canonical_portfolio_signature(self)

    def normalized_net_usdc_per_day_per_100(self, net_usdc_per_day: float) -> float:
        """Normalize a finite daily result to each 100 USDC of budget."""

        value = _finite_number(net_usdc_per_day, "net_usdc_per_day")
        return round(value * FIXED_LOT_NOTIONAL_USDC / self.deployment_budget_usdc, 10)

    def has_soft_drawdown_warning(self, max_drawdown_usdc: float) -> bool:
        """Return a warning only; this method never declares gate failure."""

        value = _finite_number(max_drawdown_usdc, "max_drawdown_usdc")
        if value < 0:
            raise ValueError("max_drawdown_usdc must be non-negative")
        return value > self.soft_drawdown_limit_usdc

    def to_dict(self) -> dict[str, Any]:
        guidance = self.target_guidance
        return {
            "model_version": PORTFOLIO_MODEL_VERSION,
            **asdict(self),
            "max_concurrent_lots": self.max_concurrent_lots,
            "soft_drawdown_limit_usdc": self.soft_drawdown_limit_usdc,
            "drawdown_limit_kind": "soft_warning_only",
            "target_guidance": asdict(guidance),
        }


def canonical_portfolio_signature(policy: PortfolioPolicy) -> str:
    """Return stable canonical JSON that binds every portfolio policy value."""

    if not isinstance(policy, PortfolioPolicy):
        raise TypeError("policy must be a PortfolioPolicy")
    return json.dumps(
        policy.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _require_fixed_number(value: object, expected: float, name: str) -> None:
    number = _finite_number(value, name)
    if number != expected:
        raise ValueError(f"{name} must remain exactly {expected}")


RESEARCH_PORTFOLIO_V1: Final = PortfolioPolicy()


__all__ = [
    "ALLOWED_DEPLOYMENT_BUDGETS_USDC",
    "BASELINE_FEE_BPS_PER_SIDE",
    "BASELINE_SLIPPAGE_BPS_PER_SIDE",
    "DailyTargetGuidance",
    "FIXED_LOT_NOTIONAL_USDC",
    "PORTFOLIO_MODEL_VERSION",
    "PortfolioPolicy",
    "RESEARCH_PORTFOLIO_V1",
    "SOFT_DRAWDOWN_FRACTION",
    "TARGET_GUIDANCE_BY_BUDGET_USDC",
    "canonical_portfolio_signature",
]
