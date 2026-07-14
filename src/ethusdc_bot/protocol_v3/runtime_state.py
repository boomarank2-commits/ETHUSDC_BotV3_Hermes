"""Protocol v3 warmup, purge, fold-end, and outer rotation state.

This module is a pure state/boundary layer.  It reuses Task-8 sell-fill timing
and Task-7 quantity/notional/fee validation.  It does not select candidates,
fit models, create orders, access private endpoints, or persist resume data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Final, Mapping, Sequence

from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS
from ethusdc_bot.protocol_v3.boundaries import MonthlyOriginBoundary
from ethusdc_bot.protocol_v3.execution_parity import (
    EXECUTION_PARITY_CONTRACT_VERSION,
    MarketExecutionRules,
    prepare_market_exit,
)
from ethusdc_bot.protocol_v3.intrabar_execution import (
    INTRABAR_EXECUTION_CONTRACT_VERSION,
    ExecutionCostProfile,
    _sell_fill,
    _validate_cost_profile,
)


RUNTIME_STATE_CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_runtime_state_contract.json"
)
RUNTIME_STATE_CONTRACT_SCHEMA: Final = "protocol_v3_runtime_state_contract_v1"
RUNTIME_STATE_CONTRACT_VERSION: Final = "warmup_purge_fold_outer_state_v1"
RUNTIME_STATE_SCHEMA: Final = "protocol_v3_outer_rotation_state_v1"
SOURCE_BAR_MINUTES: Final = 1
_BUNDLE_SHA_RE = re.compile(r"^[0-9a-f]{64}$")

_CANONICAL_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: dict[str, Any] = {
    "schema_version": RUNTIME_STATE_CONTRACT_SCHEMA,
    "protocol_version": "3.0.0",
    "contract_version": RUNTIME_STATE_CONTRACT_VERSION,
    "timebase": {
        "timezone": "UTC",
        "source_bar_minutes": 1,
        "interval_semantics": "half_open_except_boundary_touch_purges",
    },
    "warmup_policy": {
        "feature_reads_allowed": True,
        "signals_forbidden": True,
        "labels_forbidden": True,
        "pnl_forbidden": True,
        "scaler_fit_forbidden": True,
        "quantile_fit_forbidden": True,
        "regime_fit_forbidden": True,
    },
    "purge_policy": {
        "formula": "max(max_label_horizon_minutes,max_holding_period_minutes+pending_entry_latency_minutes)+execution_bar_minutes",
        "execution_bar_minutes": 1,
        "boundary_touch_purges": True,
        "training_event_may_not_reach_validation_or_test_start": True,
        "horizon_extension_creates_new_pipeline_generation": True,
    },
    "inner_fold_policy": {
        "starts_flat": True,
        "pending_entry_at_start": "forbidden",
        "cooldown_at_start": "forbidden",
        "inherited_runtime_model_state": "forbidden",
        "inherited_scaler_state": "forbidden",
        "open_position_at_start": "forbidden",
        "pending_entry_at_end": "cancel",
        "open_position_at_end": "conservative_terminal_liquidation",
        "terminal_reference": "last_positive_volume_bar_close",
        "uses_task8_sell_fill": True,
        "uses_task7_exact_quantity_and_fees": True,
    },
    "outer_rotation_policy": {
        "first_origin_starts_flat": True,
        "carry_open_position_only": True,
        "max_open_positions": 1,
        "carry_pending_entry": False,
        "carry_cooldown": False,
        "carry_scaler_state": False,
        "carry_runtime_model_state": False,
        "retiring_configuration_mode": "exit_only",
        "new_configuration_waits_for": ["valid_from", "flat_time"],
        "entry_enabled_at_formula": "max(valid_from,flat_time)",
        "monthly_boundary_liquidation": False,
        "process_end_liquidation": True,
        "expired_waiting_configuration": "NO_TRADE",
    },
    "required_open_position_fields": [
        "candidate_bundle_sha256",
        "quantity",
        "entry_price",
        "accrued_entry_fees",
        "stop_price",
        "target_price",
        "trailing_state",
        "high_watermark",
        "time_stop_deadline_ms",
        "execution_rules_sha256",
        "cost_profile",
    ],
    "state_identity": {
        "canonical_json": True,
        "sha256": True,
        "timestamps_forbidden_from_identity": False,
        "runtime_state_must_be_semantically_revalidated": True,
    },
    "task_dependencies": {
        "boundary_contract": "protocol_v3_monthly_boundary_v1",
        "execution_contract": INTRABAR_EXECUTION_CONTRACT_VERSION,
        "execution_parity_contract": EXECUTION_PARITY_CONTRACT_VERSION,
    },
    "deferred_scope": {
        "exact_6x60_fold_planner_task": 14,
        "context_parity_task": 10,
        "content_addressed_resume_task": 13,
        "outer_origin_orchestration_task": 23,
        "rotation_persistence_task": 24,
    },
    "safety": _CANONICAL_SAFETY,
}


class RuntimeStateError(RuntimeError):
    """Raised when Protocol-v3 temporal state would be ambiguous or optimistic."""


@dataclass(frozen=True)
class HorizonPolicy:
    max_label_horizon_minutes: int
    max_holding_period_minutes: int
    pending_entry_latency_minutes: int
    execution_bar_minutes: int = SOURCE_BAR_MINUTES

    def __post_init__(self) -> None:
        _positive_int(self.max_label_horizon_minutes, "max_label_horizon_minutes")
        _positive_int(self.max_holding_period_minutes, "max_holding_period_minutes")
        _nonnegative_int(
            self.pending_entry_latency_minutes, "pending_entry_latency_minutes"
        )
        if self.execution_bar_minutes != SOURCE_BAR_MINUTES:
            raise RuntimeStateError("Protocol v3 execution_bar_minutes must equal 1")

    @property
    def purge_duration_minutes(self) -> int:
        return max(
            self.max_label_horizon_minutes,
            self.max_holding_period_minutes + self.pending_entry_latency_minutes,
        ) + self.execution_bar_minutes

    def assert_actual_horizons(
        self,
        *,
        label_horizon_minutes: int,
        holding_period_minutes: int,
        pending_entry_latency_minutes: int,
    ) -> None:
        _nonnegative_int(label_horizon_minutes, "label_horizon_minutes")
        _nonnegative_int(holding_period_minutes, "holding_period_minutes")
        _nonnegative_int(
            pending_entry_latency_minutes, "pending_entry_latency_minutes"
        )
        if label_horizon_minutes > self.max_label_horizon_minutes:
            raise RuntimeStateError("label horizon exceeds the frozen purge policy")
        if holding_period_minutes > self.max_holding_period_minutes:
            raise RuntimeStateError("holding period exceeds the frozen purge policy")
        if pending_entry_latency_minutes > self.pending_entry_latency_minutes:
            raise RuntimeStateError(
                "pending-entry latency exceeds the frozen purge policy"
            )


@dataclass(frozen=True)
class InformationInterval:
    event_id: str
    signal_time_ms: int
    information_end_ms: int

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise RuntimeStateError("event_id must be non-empty")
        _nonnegative_int(self.signal_time_ms, "signal_time_ms")
        _nonnegative_int(self.information_end_ms, "information_end_ms")
        if self.information_end_ms < self.signal_time_ms:
            raise RuntimeStateError("information interval ends before its signal")


@dataclass(frozen=True)
class PurgeResult:
    boundary_start_ms: int
    kept: tuple[InformationInterval, ...]
    purged: tuple[InformationInterval, ...]


@dataclass(frozen=True)
class WarmupWindow:
    warmup_start_ms: int
    evaluation_start_ms: int
    evaluation_end_exclusive_ms: int

    def __post_init__(self) -> None:
        _nonnegative_int(self.warmup_start_ms, "warmup_start_ms")
        _nonnegative_int(self.evaluation_start_ms, "evaluation_start_ms")
        _nonnegative_int(
            self.evaluation_end_exclusive_ms, "evaluation_end_exclusive_ms"
        )
        if not (
            self.warmup_start_ms
            < self.evaluation_start_ms
            < self.evaluation_end_exclusive_ms
        ):
            raise RuntimeStateError(
                "warmup/evaluation timestamps must be strictly increasing"
            )

    def assert_use(self, timestamp_ms: int, purpose: str) -> None:
        _nonnegative_int(timestamp_ms, "timestamp_ms")
        allowed_purposes = {
            "feature_read",
            "signal",
            "label",
            "pnl",
            "scaler_fit",
            "quantile_fit",
            "regime_fit",
        }
        if purpose not in allowed_purposes:
            raise RuntimeStateError(f"unsupported warmup purpose: {purpose}")
        if timestamp_ms < self.warmup_start_ms:
            raise RuntimeStateError("timestamp lies before the frozen warmup window")
        if timestamp_ms >= self.evaluation_end_exclusive_ms:
            raise RuntimeStateError("timestamp lies after the evaluation window")
        if timestamp_ms < self.evaluation_start_ms and purpose != "feature_read":
            raise RuntimeStateError(
                f"warmup data may not be used for {purpose}; feature_read only"
            )


@dataclass(frozen=True)
class PendingEntryState:
    candidate_bundle_sha256: str
    signal_time_ms: int

    def __post_init__(self) -> None:
        _sha256(self.candidate_bundle_sha256, "candidate_bundle_sha256")
        _nonnegative_int(self.signal_time_ms, "signal_time_ms")


@dataclass(frozen=True)
class OpenPositionState:
    candidate_bundle_sha256: str
    quantity: str
    entry_price: str
    accrued_entry_fees: str
    stop_price: str
    target_price: str
    trailing_state: str
    trailing_stop_price: str | None
    break_even_active: bool
    high_watermark: str
    time_stop_deadline_ms: int
    execution_rules_sha256: str
    cost_profile: str

    def __post_init__(self) -> None:
        _sha256(self.candidate_bundle_sha256, "candidate_bundle_sha256")
        _sha256(self.execution_rules_sha256, "execution_rules_sha256")
        quantity = _decimal(self.quantity, "quantity")
        entry = _decimal(self.entry_price, "entry_price")
        fees = _decimal(
            self.accrued_entry_fees,
            "accrued_entry_fees",
            allow_zero=True,
        )
        stop = _decimal(self.stop_price, "stop_price")
        target = _decimal(self.target_price, "target_price")
        high = _decimal(self.high_watermark, "high_watermark")
        if quantity <= 0 or entry <= 0 or stop <= 0 or target <= 0 or high <= 0:
            raise RuntimeStateError("open-position prices and quantity must be positive")
        if fees < 0:
            raise RuntimeStateError("accrued entry fees must be non-negative")
        if stop >= target:
            raise RuntimeStateError("open-position stop must remain below target")
        if high < entry:
            raise RuntimeStateError("LONG high watermark cannot be below entry")
        if self.trailing_state not in {"inactive", "armed", "active"}:
            raise RuntimeStateError("trailing_state is not canonical")
        if self.trailing_state == "active":
            if self.trailing_stop_price is None:
                raise RuntimeStateError(
                    "active trailing state requires trailing_stop_price"
                )
            trailing = _decimal(self.trailing_stop_price, "trailing_stop_price")
            if trailing <= 0 or trailing >= target:
                raise RuntimeStateError("trailing stop must be positive and below target")
        elif self.trailing_stop_price is not None:
            raise RuntimeStateError(
                "inactive/armed trailing state cannot carry a trailing stop price"
            )
        if not isinstance(self.break_even_active, bool):
            raise RuntimeStateError("break_even_active must be boolean")
        _nonnegative_int(self.time_stop_deadline_ms, "time_stop_deadline_ms")
        if self.cost_profile not in {
            "baseline",
            "slippage_stress",
            "joint_stress",
        }:
            raise RuntimeStateError("open-position cost_profile is not canonical")

    @property
    def quantity_decimal(self) -> Decimal:
        return _decimal(self.quantity, "quantity")


@dataclass(frozen=True)
class RuntimeCarryState:
    candidate_bundle_sha256: str | None = None
    open_position: OpenPositionState | None = None
    pending_entry: PendingEntryState | None = None
    cooldown_until_ms: int | None = None
    scaler_state_sha256: str | None = None
    runtime_model_state_sha256: str | None = None

    def __post_init__(self) -> None:
        if self.candidate_bundle_sha256 is not None:
            _sha256(self.candidate_bundle_sha256, "candidate_bundle_sha256")
        if self.cooldown_until_ms is not None:
            _nonnegative_int(self.cooldown_until_ms, "cooldown_until_ms")
        for label, value in (
            ("scaler_state_sha256", self.scaler_state_sha256),
            ("runtime_model_state_sha256", self.runtime_model_state_sha256),
        ):
            if value is not None:
                _sha256(value, label)


@dataclass(frozen=True)
class FoldRuntimeState:
    fold_id: str
    open_position: OpenPositionState | None = None
    pending_entry: PendingEntryState | None = None
    cooldown_until_ms: int | None = None
    scaler_state_sha256: str | None = None
    runtime_model_state_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.fold_id.strip():
            raise RuntimeStateError("fold_id must be non-empty")
        if self.cooldown_until_ms is not None:
            _nonnegative_int(self.cooldown_until_ms, "cooldown_until_ms")
        for label, value in (
            ("scaler_state_sha256", self.scaler_state_sha256),
            ("runtime_model_state_sha256", self.runtime_model_state_sha256),
        ):
            if value is not None:
                _sha256(value, label)


@dataclass(frozen=True)
class TerminalLiquidation:
    reason: str
    execution_time_ms: int
    reference_price: str
    fill_price: str
    quantity: str
    executed_exit_notional: str
    exit_fee: str
    exit_proceeds_after_fee: str
    terminal_liquidation: bool = True


@dataclass(frozen=True)
class FoldFinalization:
    fold_id: str
    pending_entry_cancelled: bool
    liquidation: TerminalLiquidation | None
    final_state: FoldRuntimeState


@dataclass(frozen=True)
class OuterRotationState:
    schema_version: str
    contract_version: str
    origin_index: int
    retiring_candidate_bundle_sha256: str | None
    open_position: OpenPositionState | None
    new_candidate_bundle_sha256: str
    anchor_utc: datetime
    valid_from_utc: datetime
    valid_until_utc: datetime
    flat_time_utc: datetime | None
    entry_enabled_at_utc: datetime | None
    retiring_configuration_mode: str
    new_configuration_mode: str
    discarded_pending_entry: bool
    discarded_cooldown: bool
    discarded_scaler_state: bool
    discarded_runtime_model_state: bool
    monthly_boundary_liquidation: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != RUNTIME_STATE_SCHEMA:
            raise RuntimeStateError("outer rotation state schema is not canonical")
        if self.contract_version != RUNTIME_STATE_CONTRACT_VERSION:
            raise RuntimeStateError("outer rotation state contract is not canonical")
        _positive_int(self.origin_index, "origin_index")
        _sha256(self.new_candidate_bundle_sha256, "new_candidate_bundle_sha256")
        if self.retiring_candidate_bundle_sha256 is not None:
            _sha256(
                self.retiring_candidate_bundle_sha256,
                "retiring_candidate_bundle_sha256",
            )
        anchor = _utc(self.anchor_utc, "anchor_utc")
        valid_from = _utc(self.valid_from_utc, "valid_from_utc")
        valid_until = _utc(self.valid_until_utc, "valid_until_utc")
        if not anchor < valid_from < valid_until:
            raise RuntimeStateError(
                "outer rotation anchor/validity timestamps are inconsistent"
            )
        if self.flat_time_utc is not None:
            flat = _utc(self.flat_time_utc, "flat_time_utc")
            if flat < anchor or flat > valid_until:
                raise RuntimeStateError("flat_time lies outside the rotation interval")
        if self.entry_enabled_at_utc is not None:
            enabled = _utc(self.entry_enabled_at_utc, "entry_enabled_at_utc")
            if enabled < valid_from or enabled >= valid_until:
                raise RuntimeStateError("entry_enabled_at lies outside valid deployment")
            if self.open_position is not None:
                raise RuntimeStateError(
                    "new entries cannot be enabled while a retiring position is open"
                )
        if self.open_position is None:
            if self.retiring_candidate_bundle_sha256 is not None:
                raise RuntimeStateError(
                    "flat rotation cannot retain a retiring candidate bundle"
                )
            if self.retiring_configuration_mode != "retired":
                raise RuntimeStateError("flat rotation must mark old configuration retired")
        else:
            if (
                self.retiring_candidate_bundle_sha256
                != self.open_position.candidate_bundle_sha256
            ):
                raise RuntimeStateError(
                    "retiring bundle must equal the carried position bundle"
                )
            if self.retiring_configuration_mode != "exit_only":
                raise RuntimeStateError(
                    "carried old configuration must be exit_only"
                )
        if self.new_configuration_mode not in {
            "waiting_for_valid_from",
            "waiting_for_flat_and_valid_from",
            "entry_enabled",
            "NO_TRADE_EXPIRED",
        }:
            raise RuntimeStateError("new configuration mode is not canonical")
        if self.monthly_boundary_liquidation is not False:
            raise RuntimeStateError("monthly boundaries may not liquidate positions")

    def basis(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_version": self.contract_version,
            "origin_index": self.origin_index,
            "retiring_candidate_bundle_sha256": self.retiring_candidate_bundle_sha256,
            "open_position": (
                _normalize_json(asdict(self.open_position))
                if self.open_position is not None
                else None
            ),
            "new_candidate_bundle_sha256": self.new_candidate_bundle_sha256,
            "anchor_utc": _iso(self.anchor_utc),
            "valid_from_utc": _iso(self.valid_from_utc),
            "valid_until_utc": _iso(self.valid_until_utc),
            "flat_time_utc": (
                _iso(self.flat_time_utc) if self.flat_time_utc is not None else None
            ),
            "entry_enabled_at_utc": (
                _iso(self.entry_enabled_at_utc)
                if self.entry_enabled_at_utc is not None
                else None
            ),
            "retiring_configuration_mode": self.retiring_configuration_mode,
            "new_configuration_mode": self.new_configuration_mode,
            "discarded_pending_entry": self.discarded_pending_entry,
            "discarded_cooldown": self.discarded_cooldown,
            "discarded_scaler_state": self.discarded_scaler_state,
            "discarded_runtime_model_state": self.discarded_runtime_model_state,
            "monthly_boundary_liquidation": self.monthly_boundary_liquidation,
        }

    @property
    def state_sha256(self) -> str:
        return _sha256_json(self.basis())

    def entry_allowed_at(self, at_utc: datetime) -> bool:
        at = _utc(at_utc, "at_utc")
        return bool(
            self.open_position is None
            and self.entry_enabled_at_utc is not None
            and self.entry_enabled_at_utc <= at < self.valid_until_utc
        )

    def mode_at(self, at_utc: datetime) -> str:
        at = _utc(at_utc, "at_utc")
        if at >= self.valid_until_utc:
            return "NO_TRADE_EXPIRED"
        if self.open_position is not None:
            return "retiring_exit_only_new_waiting"
        if self.entry_allowed_at(at):
            return "new_entry_enabled"
        return "new_waiting_for_valid_from"


def load_runtime_state_contract(
    repo_root: str | Path | None = None,
    *,
    contract_path: str | Path | None = None,
) -> dict[str, Any]:
    root = (
        Path(repo_root).resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[3]
    )
    path = (
        Path(contract_path)
        if contract_path is not None
        else root / RUNTIME_STATE_CONTRACT_PATH
    )
    if not path.is_absolute():
        path = root / path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeStateError(
            f"runtime state contract is missing or invalid: {path}"
        ) from exc
    validate_runtime_state_contract(value)
    return value


def validate_runtime_state_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize_json(value) != _CANONICAL_CONTRACT:
        raise RuntimeStateError("Protocol v3 runtime state contract is not canonical")


def build_information_interval(
    event_id: str,
    *,
    signal_time_ms: int,
    label_horizon_minutes: int,
    holding_period_minutes: int,
    pending_entry_latency_minutes: int,
    policy: HorizonPolicy,
) -> InformationInterval:
    policy.assert_actual_horizons(
        label_horizon_minutes=label_horizon_minutes,
        holding_period_minutes=holding_period_minutes,
        pending_entry_latency_minutes=pending_entry_latency_minutes,
    )
    actual_duration = max(
        label_horizon_minutes,
        holding_period_minutes + pending_entry_latency_minutes,
    ) + policy.execution_bar_minutes
    return InformationInterval(
        event_id=event_id,
        signal_time_ms=signal_time_ms,
        information_end_ms=signal_time_ms + actual_duration * 60_000,
    )


def purge_training_events(
    events: Sequence[InformationInterval],
    *,
    boundary_start_ms: int,
) -> PurgeResult:
    _nonnegative_int(boundary_start_ms, "boundary_start_ms")
    kept: list[InformationInterval] = []
    purged: list[InformationInterval] = []
    seen: set[str] = set()
    for event in sorted(events, key=lambda row: (row.signal_time_ms, row.event_id)):
        if event.event_id in seen:
            raise RuntimeStateError("duplicate information interval event_id")
        seen.add(event.event_id)
        if event.signal_time_ms >= boundary_start_ms:
            raise RuntimeStateError(
                "training event signal must be strictly before the validation/test boundary"
            )
        if event.information_end_ms >= boundary_start_ms:
            purged.append(event)
        else:
            kept.append(event)
    return PurgeResult(
        boundary_start_ms=boundary_start_ms,
        kept=tuple(kept),
        purged=tuple(purged),
    )


def begin_inner_fold(fold_id: str) -> FoldRuntimeState:
    state = FoldRuntimeState(fold_id=fold_id)
    assert_inner_fold_starts_flat(state)
    return state


def assert_inner_fold_starts_flat(state: FoldRuntimeState) -> None:
    if not isinstance(state, FoldRuntimeState):
        raise TypeError("state must be FoldRuntimeState")
    if any(
        value is not None
        for value in (
            state.open_position,
            state.pending_entry,
            state.cooldown_until_ms,
            state.scaler_state_sha256,
            state.runtime_model_state_sha256,
        )
    ):
        raise RuntimeStateError(
            "inner fold must start flat without pending, cooldown, scaler, or runtime model state"
        )


def finalize_inner_fold(
    state: FoldRuntimeState,
    *,
    terminal_bar: Candle | None,
    rules: MarketExecutionRules,
    cost_profile: ExecutionCostProfile,
) -> FoldFinalization:
    if not isinstance(state, FoldRuntimeState):
        raise TypeError("state must be FoldRuntimeState")
    liquidation = None
    if state.open_position is not None:
        if terminal_bar is None:
            raise RuntimeStateError(
                "open fold position requires an explicit terminal tradable bar"
            )
        liquidation = _terminal_liquidation(
            state.open_position,
            terminal_bar,
            rules,
            cost_profile,
            reason="fold_end",
        )
    final_state = FoldRuntimeState(fold_id=state.fold_id)
    return FoldFinalization(
        fold_id=state.fold_id,
        pending_entry_cancelled=state.pending_entry is not None,
        liquidation=liquidation,
        final_state=final_state,
    )


def build_outer_rotation_state(
    origin: MonthlyOriginBoundary,
    *,
    new_candidate_bundle_sha256: str,
    previous_runtime: RuntimeCarryState | None = None,
) -> OuterRotationState:
    if not isinstance(origin, MonthlyOriginBoundary):
        raise TypeError("origin must be MonthlyOriginBoundary")
    _sha256(new_candidate_bundle_sha256, "new_candidate_bundle_sha256")
    previous = previous_runtime or RuntimeCarryState()
    if origin.origin_index == 1 and any(
        value is not None
        for value in (
            previous.candidate_bundle_sha256,
            previous.open_position,
            previous.pending_entry,
            previous.cooldown_until_ms,
            previous.scaler_state_sha256,
            previous.runtime_model_state_sha256,
        )
    ):
        raise RuntimeStateError("the first outer origin must start completely flat")

    anchor = datetime.combine(origin.test_start_inclusive, datetime.min.time(), UTC)
    position = previous.open_position
    if position is None:
        flat_time = anchor
        entry_enabled = origin.resolve_entry_enabled_at(flat_time)
        retiring_hash = None
        retiring_mode = "retired"
        new_mode = (
            "waiting_for_valid_from"
            if entry_enabled is not None
            else "NO_TRADE_EXPIRED"
        )
    else:
        flat_time = None
        entry_enabled = None
        retiring_hash = position.candidate_bundle_sha256
        retiring_mode = "exit_only"
        new_mode = "waiting_for_flat_and_valid_from"

    state = OuterRotationState(
        schema_version=RUNTIME_STATE_SCHEMA,
        contract_version=RUNTIME_STATE_CONTRACT_VERSION,
        origin_index=origin.origin_index,
        retiring_candidate_bundle_sha256=retiring_hash,
        open_position=position,
        new_candidate_bundle_sha256=new_candidate_bundle_sha256,
        anchor_utc=anchor,
        valid_from_utc=origin.valid_from,
        valid_until_utc=origin.valid_until,
        flat_time_utc=flat_time,
        entry_enabled_at_utc=entry_enabled,
        retiring_configuration_mode=retiring_mode,
        new_configuration_mode=new_mode,
        discarded_pending_entry=previous.pending_entry is not None,
        discarded_cooldown=previous.cooldown_until_ms is not None,
        discarded_scaler_state=previous.scaler_state_sha256 is not None,
        discarded_runtime_model_state=(
            previous.runtime_model_state_sha256 is not None
        ),
    )
    validate_outer_rotation_state(state, origin=origin)
    return state


def close_retiring_position(
    state: OuterRotationState,
    *,
    exit_time_utc: datetime,
) -> OuterRotationState:
    validate_outer_rotation_state(state)
    if state.open_position is None:
        raise RuntimeStateError("rotation state has no retiring position to close")
    exit_time = _utc(exit_time_utc, "exit_time_utc")
    if exit_time < state.anchor_utc or exit_time > state.valid_until_utc:
        raise RuntimeStateError("retiring position exit lies outside the origin")
    enabled = max(state.valid_from_utc, exit_time)
    if enabled >= state.valid_until_utc:
        enabled = None
        new_mode = "NO_TRADE_EXPIRED"
    elif exit_time < state.valid_from_utc:
        new_mode = "waiting_for_valid_from"
    else:
        new_mode = "entry_enabled"
    closed = replace(
        state,
        retiring_candidate_bundle_sha256=None,
        open_position=None,
        flat_time_utc=exit_time,
        entry_enabled_at_utc=enabled,
        retiring_configuration_mode="retired",
        new_configuration_mode=new_mode,
    )
    validate_outer_rotation_state(closed)
    return closed


def carry_state_for_next_origin(state: OuterRotationState) -> RuntimeCarryState:
    validate_outer_rotation_state(state)
    return RuntimeCarryState(
        candidate_bundle_sha256=(
            state.open_position.candidate_bundle_sha256
            if state.open_position is not None
            else state.new_candidate_bundle_sha256
        ),
        open_position=state.open_position,
        pending_entry=None,
        cooldown_until_ms=None,
        scaler_state_sha256=None,
        runtime_model_state_sha256=None,
    )


def finalize_outer_process(
    state: OuterRotationState,
    *,
    terminal_bar: Candle | None,
    rules: MarketExecutionRules,
    cost_profile: ExecutionCostProfile,
) -> TerminalLiquidation | None:
    validate_outer_rotation_state(state)
    if state.open_position is None:
        return None
    if terminal_bar is None:
        raise RuntimeStateError(
            "open process-end position requires an explicit terminal tradable bar"
        )
    expected_close_ms = int(state.valid_until_utc.timestamp() * 1000)
    observed_close_ms = terminal_bar.open_time + EXPECTED_STEP_MS
    if observed_close_ms != expected_close_ms:
        raise RuntimeStateError(
            "process-end terminal bar must end exactly at valid_until"
        )
    return _terminal_liquidation(
        state.open_position,
        terminal_bar,
        rules,
        cost_profile,
        reason="process_end",
    )


def validate_outer_rotation_state(
    state: OuterRotationState,
    *,
    origin: MonthlyOriginBoundary | None = None,
) -> None:
    if not isinstance(state, OuterRotationState):
        raise TypeError("state must be OuterRotationState")
    # Reconstructing runs dataclass semantic checks even after unsafe replacement.
    OuterRotationState(**asdict(state))
    if origin is not None:
        if state.origin_index != origin.origin_index:
            raise RuntimeStateError("rotation origin index does not match boundary")
        expected_anchor = datetime.combine(
            origin.test_start_inclusive, datetime.min.time(), UTC
        )
        if (
            state.anchor_utc != expected_anchor
            or state.valid_from_utc != origin.valid_from
            or state.valid_until_utc != origin.valid_until
        ):
            raise RuntimeStateError("rotation timestamps do not match boundary")


def _terminal_liquidation(
    position: OpenPositionState,
    terminal_bar: Candle,
    rules: MarketExecutionRules,
    cost_profile: ExecutionCostProfile,
    *,
    reason: str,
) -> TerminalLiquidation:
    if not isinstance(terminal_bar, Candle):
        raise TypeError("terminal_bar must be Candle")
    if terminal_bar.volume <= 0:
        raise RuntimeStateError("terminal liquidation requires positive volume")
    if position.execution_rules_sha256 != rules.rules_sha256:
        raise RuntimeStateError(
            "open position execution rules do not match terminal rules"
        )
    profile = _validate_cost_profile(cost_profile)
    if position.cost_profile != profile.name:
        raise RuntimeStateError(
            "open position cost profile does not match terminal cost profile"
        )
    reference = _decimal(terminal_bar.close, "terminal_bar.close")
    try:
        fill = _sell_fill(reference, profile.slippage_bps_per_side, rules)
        execution = prepare_market_exit(
            fill,
            position.quantity_decimal,
            profile.fee_rate,
            rules,
        )
    except Exception as exc:
        if isinstance(exc, RuntimeStateError):
            raise
        raise RuntimeStateError("terminal liquidation failed closed") from exc
    return TerminalLiquidation(
        reason=reason,
        execution_time_ms=terminal_bar.open_time + EXPECTED_STEP_MS - 1,
        reference_price=_canonical_decimal(reference),
        fill_price=_canonical_decimal(fill),
        quantity=_canonical_decimal(execution.executed_quantity),
        executed_exit_notional=_canonical_decimal(
            execution.executed_exit_notional
        ),
        exit_fee=_canonical_decimal(execution.exit_fee),
        exit_proceeds_after_fee=_canonical_decimal(
            execution.exit_proceeds_after_fee
        ),
    )


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeStateError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeStateError(f"{label} must be a non-negative integer")
    return value


def _decimal(
    value: Any,
    label: str,
    *,
    allow_zero: bool = False,
) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int, float)):
        raise RuntimeStateError(f"{label} must be a finite decimal")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeStateError(f"{label} is not a valid decimal") from exc
    if not parsed.is_finite():
        raise RuntimeStateError(f"{label} must be finite")
    if parsed < 0 or (parsed == 0 and not allow_zero):
        requirement = "non-negative" if allow_zero else "positive"
        raise RuntimeStateError(f"{label} must be {requirement}")
    return parsed


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _BUNDLE_SHA_RE.fullmatch(value) is None:
        raise RuntimeStateError(f"{label} must be a lowercase 64-character sha256")
    return value


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeStateError(f"{label} must be a timezone-aware UTC datetime")
    normalized = value.astimezone(UTC)
    if value.utcoffset() != normalized.utcoffset():
        raise RuntimeStateError(f"{label} must be expressed in UTC")
    return normalized


def _iso(value: datetime) -> str:
    return _utc(value, "datetime").isoformat().replace("+00:00", "Z")


def _sha256_json(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _normalize_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_json(value: Any) -> Any:
    return json.loads(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    )


__all__ = [
    "RUNTIME_STATE_CONTRACT_PATH",
    "RUNTIME_STATE_CONTRACT_SCHEMA",
    "RUNTIME_STATE_CONTRACT_VERSION",
    "RUNTIME_STATE_SCHEMA",
    "FoldFinalization",
    "FoldRuntimeState",
    "HorizonPolicy",
    "InformationInterval",
    "OpenPositionState",
    "OuterRotationState",
    "PendingEntryState",
    "PurgeResult",
    "RuntimeCarryState",
    "RuntimeStateError",
    "TerminalLiquidation",
    "WarmupWindow",
    "assert_inner_fold_starts_flat",
    "begin_inner_fold",
    "build_information_interval",
    "build_outer_rotation_state",
    "carry_state_for_next_origin",
    "close_retiring_position",
    "finalize_inner_fold",
    "finalize_outer_process",
    "load_runtime_state_contract",
    "purge_training_events",
    "validate_outer_rotation_state",
    "validate_runtime_state_contract",
]
