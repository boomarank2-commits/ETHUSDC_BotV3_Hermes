"""Protocol-v3 hindsight solvers bound to exact process data and execution rules.

The solvers are deliberately post-hoc and diagnostic-only. They may inspect future
prices inside the already completed historical process, but their paths and results
cannot feed candidate selection, the monthly quality gate, adoption, or any trading
mode.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import struct
from typing import Any, Final

from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS
from ethusdc_bot.protocol_v3.boundaries import (
    MonthlyProcessBoundaryPlan,
    validate_monthly_process_boundary_plan,
)
from ethusdc_bot.protocol_v3.execution_parity import (
    EXECUTION_PARITY_CONTRACT_VERSION,
    MarketExecutionRules,
    build_market_execution_rules,
    prepare_market_entry,
    prepare_market_exit,
)
from ethusdc_bot.protocol_v3.intrabar_execution import (
    BASELINE_COST_PROFILE,
    INTRABAR_EXECUTION_CONTRACT_VERSION,
    _buy_fill,
    _sell_fill,
)
from ethusdc_bot.protocol_v3.run_identity import (
    FrozenExchangeInfoSnapshot,
    validate_exchange_info_snapshot,
)

PROTOCOL_VERSION: Final = "3.0.0"
SOLVER_SCHEMA_VERSION: Final = "protocol_v3_hindsight_solver_evidence_v1"
SOLVER_CONTRACT_VERSION: Final = "protocol_v3_causally_bound_hindsight_solvers_v1"
ALL_CANDLE_SOLVER: Final = "all_candle_one_trade_close_hindsight"
CANDIDATE_MATCHED_SOLVER: Final = "candidate_matched_volume_filtered_hindsight"
PROCESS_DAYS: Final = 365
MINUTES_PER_DAY: Final = 1440
_PROCESS_MINUTES: Final = PROCESS_DAYS * MINUTES_PER_DAY
_BLOCK_SIZE: Final = 96
_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}


class HindsightSolverError(ValueError):
    """Raised when solver inputs, constraints, or evidence are incomplete."""


@dataclass(frozen=True)
class HindsightOriginPolicy:
    origin_index: int
    start_inclusive_utc: datetime
    end_exclusive_utc: datetime
    valid_from_utc: datetime
    origin_selection_sha256: str
    candidate_bundle_sha256: str
    rotation_state_sha256: str
    max_roundtrips_per_utc_day: int
    max_holding_minutes: int
    entry_allowed: bool

    def __post_init__(self) -> None:
        if type(self.origin_index) is not int or not 1 <= self.origin_index <= 12:
            raise HindsightSolverError("origin_index must be 1..12")
        start = _utc(self.start_inclusive_utc, "start_inclusive_utc")
        end = _utc(self.end_exclusive_utc, "end_exclusive_utc")
        valid_from = _utc(self.valid_from_utc, "valid_from_utc")
        if not start < valid_from < end:
            raise HindsightSolverError("origin validity interval is invalid")
        _sha(self.origin_selection_sha256, "origin_selection_sha256")
        _sha(self.candidate_bundle_sha256, "candidate_bundle_sha256")
        _sha(self.rotation_state_sha256, "rotation_state_sha256")
        if type(self.entry_allowed) is not bool:
            raise HindsightSolverError("entry_allowed must be boolean")
        if (
            type(self.max_roundtrips_per_utc_day) is not int
            or not 0 <= self.max_roundtrips_per_utc_day <= MINUTES_PER_DAY
        ):
            raise HindsightSolverError("max_roundtrips_per_utc_day is invalid")
        if (
            type(self.max_holding_minutes) is not int
            or self.max_holding_minutes < 0
        ):
            raise HindsightSolverError("max_holding_minutes is invalid")
        if self.entry_allowed:
            if (
                self.max_roundtrips_per_utc_day <= 0
                or self.max_holding_minutes <= 0
            ):
                raise HindsightSolverError(
                    "tradeable policy requires positive trade and hold limits"
                )
        elif (
            self.max_roundtrips_per_utc_day != 0
            or self.max_holding_minutes != 0
        ):
            raise HindsightSolverError(
                "NO_TRADE policy must freeze trade and hold limits at zero"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin_index": self.origin_index,
            "start_inclusive_utc": _utc_text(self.start_inclusive_utc),
            "end_exclusive_utc": _utc_text(self.end_exclusive_utc),
            "valid_from_utc": _utc_text(self.valid_from_utc),
            "origin_selection_sha256": self.origin_selection_sha256,
            "candidate_bundle_sha256": self.candidate_bundle_sha256,
            "rotation_state_sha256": self.rotation_state_sha256,
            "max_roundtrips_per_utc_day": self.max_roundtrips_per_utc_day,
            "max_holding_minutes": self.max_holding_minutes,
            "entry_allowed": self.entry_allowed,
        }


@dataclass(frozen=True)
class HindsightSolverEvidence:
    canonical_json: str
    evidence_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["evidence_sha256"] = self.evidence_sha256
        return value


@dataclass(frozen=True)
class _PathNode:
    previous: _PathNode | None
    trade: Mapping[str, Any]
    count: int
    path_sha256: str


@dataclass(frozen=True)
class _State:
    value: Decimal
    path: _PathNode | None


@dataclass(frozen=True)
class _Line:
    slope: Decimal
    intercept: Decimal
    entry_index: int
    expiry_index: int
    entry_day: date
    entry_count: int
    candidate_bundle_sha256: str
    origin_index: int
    entry_time_utc: str
    entry_reference_price: Decimal
    entry_fill_price: Decimal
    executed_quantity: Decimal
    executed_entry_notional: Decimal
    entry_fee: Decimal
    entry_cash_cost: Decimal
    base_path: _PathNode | None

    @property
    def tie_key(self) -> tuple[int, int, str]:
        return (self.entry_index, self.entry_count, _path_sha(self.base_path))

    def evaluate(self, exit_fill: Decimal, fee_rate: Decimal) -> Decimal:
        return self.intercept + self.slope * exit_fill * (
            Decimal("1") - fee_rate
        )


@dataclass
class _HullBlock:
    lines: list[_Line]
    hull: tuple[tuple[_Line, Decimal | None], ...] | None = None

    def seal(self) -> None:
        self.hull = _build_upper_hull(self.lines)

    def best(self, x: Decimal, fee_rate: Decimal) -> _Line | None:
        if not self.lines:
            return None
        if self.hull is None:
            return _best_line(self.lines, x, fee_rate)
        starts = [item[1] for item in self.hull]
        finite = [
            Decimal("-Infinity") if value is None else value for value in starts
        ]
        effective_x = x * (Decimal("1") - fee_rate)
        index = bisect_right(finite, effective_x) - 1
        return self.hull[max(0, index)][0]


class _SlidingLineQueue:
    """FIFO-expiring lines with exact arbitrary-price maximum queries."""

    def __init__(self) -> None:
        self._blocks: deque[_HullBlock] = deque()

    def add(self, line: _Line) -> None:
        if not self._blocks or self._blocks[-1].hull is not None:
            self._blocks.append(_HullBlock([]))
        block = self._blocks[-1]
        block.lines.append(line)
        if len(block.lines) >= _BLOCK_SIZE:
            block.seal()

    def expire_before(self, index: int) -> None:
        while self._blocks:
            block = self._blocks[0]
            cut = 0
            for line in block.lines:
                if line.expiry_index >= index:
                    break
                cut += 1
            if cut:
                del block.lines[:cut]
                block.hull = None
            if block.lines:
                break
            self._blocks.popleft()

    def best(self, x: Decimal, fee_rate: Decimal) -> _Line | None:
        candidates = [block.best(x, fee_rate) for block in self._blocks]
        return _best_line(
            [line for line in candidates if line is not None], x, fee_rate
        )

    def __bool__(self) -> bool:
        return any(block.lines for block in self._blocks)


def solve_all_candle_one_trade_close_hindsight(
    candles: Sequence[Candle],
    *,
    process_start_inclusive: date,
    process_end_exclusive: date,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
) -> HindsightSolverEvidence:
    """Perfect earlier-close/later-close diagnostic, one trade per UTC day."""

    rows, data_sha = _validate_process_candles(
        candles, process_start_inclusive, process_end_exclusive
    )
    rules, exchange_sha = _execution_rules(exchange_info_snapshot)
    daily: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    total = Decimal(0)
    for day_index in range(PROCESS_DAYS):
        start = day_index * MINUTES_PER_DAY
        day_rows = rows[start : start + MINUTES_PER_DAY]
        best_exit: tuple[int, Decimal] | None = None
        best_trade: dict[str, Any] | None = None
        best_value = Decimal(0)
        for local_index in range(MINUTES_PER_DAY - 1, -1, -1):
            candle = day_rows[local_index]
            if candle.volume <= 0:
                continue
            sell = _sell_fill(
                _dec(candle.close),
                BASELINE_COST_PROFILE.slippage_bps_per_side,
                rules,
            )
            if (
                best_exit is None
                or sell > best_exit[1]
                or (sell == best_exit[1] and local_index < best_exit[0])
            ):
                best_exit = (local_index, sell)
            if best_exit is not None and best_exit[0] > local_index:
                candidate = _trade_from_closes(
                    candle,
                    day_rows[best_exit[0]],
                    entry_index=start + local_index,
                    exit_index=start + best_exit[0],
                    bundle_sha256=None,
                    origin_index=None,
                    rules=rules,
                )
                value = _dec(candidate["net_usdc"])
                if value > best_value or (
                    value == best_value
                    and best_trade is not None
                    and _trade_tie(candidate) < _trade_tie(best_trade)
                ):
                    best_value = value
                    best_trade = candidate
        day = process_start_inclusive + timedelta(days=day_index)
        if best_trade is not None and best_value > 0:
            trades.append(best_trade)
            total += best_value
            trade_count = 1
        else:
            best_value = Decimal(0)
            trade_count = 0
        daily.append(
            {
                "day_utc": day.isoformat(),
                "net_usdc": _text(best_value),
                "trade_count": trade_count,
            }
        )
    return _solver_evidence(
        ALL_CANDLE_SOLVER,
        data_sha=data_sha,
        exchange_sha=exchange_sha,
        rules=rules,
        policy_chain=None,
        process_start=process_start_inclusive,
        process_end=process_end_exclusive,
        daily=daily,
        trades=trades,
        total=total,
    )


def solve_candidate_matched_volume_filtered_hindsight(
    candles: Sequence[Candle],
    *,
    boundary_plan: MonthlyProcessBoundaryPlan,
    origin_policies: Sequence[HindsightOriginPolicy],
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
) -> HindsightSolverEvidence:
    """Exact one-lot DP with matched limits and exit-only monthly handoff."""

    validate_monthly_process_boundary_plan(boundary_plan)
    policies = _validate_policies(boundary_plan, origin_policies)
    rows, data_sha = _validate_process_candles(
        candles,
        boundary_plan.process_start_inclusive,
        boundary_plan.process_end_exclusive,
    )
    rules, exchange_sha = _execution_rules(exchange_info_snapshot)
    fee_rate = BASELINE_COST_PROFILE.fee_rate
    policy_by_day: list[HindsightOriginPolicy] = []
    for policy, boundary in zip(policies, boundary_plan.origins, strict=True):
        policy_by_day.extend(
            [policy] * len(tuple(boundary.iter_test_days()))
        )
    if len(policy_by_day) != PROCESS_DAYS:
        raise HindsightSolverError(
            "candidate policy chain does not cover exactly 365 UTC days"
        )

    global_flat = _State(Decimal(0), None)
    carry_queues: dict[tuple[str, int], _SlidingLineQueue] = {}
    pending_carry: list[_Line] = []
    daily_output: list[dict[str, Any]] = []
    prior_total = Decimal(0)

    for day_index in range(PROCESS_DAYS):
        day_start = day_index * MINUTES_PER_DAY
        day_end = day_start + MINUTES_PER_DAY - 1
        policy = policy_by_day[day_index]
        for line in pending_carry:
            key = (
                line.candidate_bundle_sha256,
                line.expiry_index - line.entry_index,
            )
            carry_queues.setdefault(key, _SlidingLineQueue()).add(line)
        pending_carry = []
        same_day = [
            _SlidingLineQueue()
            for _ in range(policy.max_roundtrips_per_utc_day + 1)
        ]
        states = [
            _State(Decimal("-Infinity"), None)
            for _ in range(policy.max_roundtrips_per_utc_day + 1)
        ]
        states[0] = global_flat

        for index in range(day_start, day_end + 1):
            candle = rows[index]
            for queue in carry_queues.values():
                queue.expire_before(index)
            if candle.volume <= 0:
                continue
            exit_fill = _sell_fill(
                _dec(candle.close),
                BASELINE_COST_PROFILE.slippage_bps_per_side,
                rules,
            )
            best_carry = _best_across_queues(
                carry_queues.values(), exit_fill, fee_rate
            )
            if best_carry is not None:
                closed = _close_line(
                    best_carry, candle, index, exit_fill, rules
                )
                states[0] = _better_state(states[0], closed)
            for count in range(1, len(same_day)):
                same_day[count].expire_before(index)
                line = same_day[count].best(exit_fill, fee_rate)
                if line is not None:
                    states[count] = _better_state(
                        states[count],
                        _close_line(line, candle, index, exit_fill, rules),
                    )

            current_time = _time(candle.open_time)
            if policy.entry_allowed and current_time >= policy.valid_from_utc:
                for count in range(policy.max_roundtrips_per_utc_day):
                    state = states[count]
                    if not state.value.is_finite():
                        continue
                    line = _entry_line(
                        state,
                        candle,
                        index,
                        count + 1,
                        policy,
                        rules,
                    )
                    if line.expiry_index <= index:
                        continue
                    same_day[count + 1].add(line)
                    if line.expiry_index > day_end:
                        pending_carry.append(line)

        global_flat = min(
            (state for state in states if state.value.is_finite()),
            key=lambda state: (-state.value, _path_sha(state.path)),
        )
        daily_value = global_flat.value - prior_total
        prior_total = global_flat.value
        previous_trade_count = sum(
            row["trade_count"] for row in daily_output
        )
        daily_output.append(
            {
                "day_utc": (
                    boundary_plan.process_start_inclusive
                    + timedelta(days=day_index)
                ).isoformat(),
                "net_usdc": _text(daily_value),
                "trade_count": _path_count(global_flat.path)
                - previous_trade_count,
            }
        )

    trades = _path_trades(global_flat.path)
    _validate_candidate_trade_path(trades, policies, boundary_plan)
    total = global_flat.value
    by_day: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        by_day.setdefault(trade["exit_time_utc"][:10], []).append(trade)
    daily_output = []
    for day in boundary_plan.iter_process_oos_days():
        day_trades = by_day.get(day.isoformat(), [])
        daily_output.append(
            {
                "day_utc": day.isoformat(),
                "net_usdc": _text(
                    sum(
                        (_dec(row["net_usdc"]) for row in day_trades),
                        Decimal(0),
                    )
                ),
                "trade_count": len(day_trades),
            }
        )
    return _solver_evidence(
        CANDIDATE_MATCHED_SOLVER,
        data_sha=data_sha,
        exchange_sha=exchange_sha,
        rules=rules,
        policy_chain=[policy.to_dict() for policy in policies],
        process_start=boundary_plan.process_start_inclusive,
        process_end=boundary_plan.process_end_exclusive,
        daily=daily_output,
        trades=trades,
        total=total,
    )


def validate_hindsight_solver_evidence(
    value: HindsightSolverEvidence | Mapping[str, Any],
) -> HindsightSolverEvidence:
    root = (
        value.to_dict()
        if isinstance(value, HindsightSolverEvidence)
        else dict(_mapping(value, "solver_evidence"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "solver",
        "input_identity",
        "output",
        "uses_future_prices_for_diagnostic_only",
        "lookahead_safe",
        "diagnostic_only",
        "selection_feedback_allowed",
        "monthly_quality_gate_feedback_allowed",
        "canonical_adoption_eligible",
        "safety",
        "evidence_sha256",
    }
    if set(root) != required:
        raise HindsightSolverError(
            "solver evidence fields are missing or unexpected"
        )
    if (
        root["schema_version"] != SOLVER_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != SOLVER_CONTRACT_VERSION
    ):
        raise HindsightSolverError("solver evidence version is invalid")
    if root["solver"] not in {ALL_CANDLE_SOLVER, CANDIDATE_MATCHED_SOLVER}:
        raise HindsightSolverError("solver name is invalid")
    if (
        root["uses_future_prices_for_diagnostic_only"] is not True
        or root["lookahead_safe"] is not False
    ):
        raise HindsightSolverError(
            "hindsight/lookahead declaration is invalid"
        )
    if (
        root["diagnostic_only"] is not True
        or root["selection_feedback_allowed"] is not False
        or root["monthly_quality_gate_feedback_allowed"] is not False
        or root["canonical_adoption_eligible"] is not False
        or root["safety"] != _SAFETY
    ):
        raise HindsightSolverError(
            "solver safety or feedback locks are invalid"
        )
    identity = dict(_mapping(root["input_identity"], "input_identity"))
    expected_identity_fields = {
        "ethusdc_process_data_sha256",
        "exchange_info_snapshot_sha256",
        "execution_rules_sha256",
        "execution_parity_contract_version",
        "intrabar_execution_contract_version",
        "cost_profile",
        "positive_volume_only",
        "process_start_inclusive",
        "process_end_exclusive",
        "policy_chain",
        "policy_chain_sha256",
    }
    if set(identity) != expected_identity_fields:
        raise HindsightSolverError("solver input identity fields are invalid")
    for key in (
        "ethusdc_process_data_sha256",
        "exchange_info_snapshot_sha256",
        "execution_rules_sha256",
    ):
        _sha(identity[key], key)
    if (
        identity["execution_parity_contract_version"]
        != EXECUTION_PARITY_CONTRACT_VERSION
        or identity["intrabar_execution_contract_version"]
        != INTRABAR_EXECUTION_CONTRACT_VERSION
    ):
        raise HindsightSolverError(
            "solver execution contract identity is invalid"
        )
    if identity["cost_profile"] != {
        "name": BASELINE_COST_PROFILE.name,
        "fee_bps_per_side": _text(
            BASELINE_COST_PROFILE.fee_bps_per_side
        ),
        "slippage_bps_per_side": _text(
            BASELINE_COST_PROFILE.slippage_bps_per_side
        ),
    } or identity["positive_volume_only"] is not True:
        raise HindsightSolverError(
            "solver cost or volume policy was manipulated"
        )
    start = date.fromisoformat(str(identity["process_start_inclusive"]))
    end = date.fromisoformat(str(identity["process_end_exclusive"]))
    if (end - start).days != PROCESS_DAYS:
        raise HindsightSolverError("solver process dates are invalid")
    chain = identity["policy_chain"]
    if root["solver"] == ALL_CANDLE_SOLVER:
        if chain is not None or identity["policy_chain_sha256"] is not None:
            raise HindsightSolverError(
                "all-candle solver may not claim candidate policies"
            )
    else:
        if (
            not isinstance(chain, list)
            or len(chain) != 12
            or identity["policy_chain_sha256"] != _digest(chain)
        ):
            raise HindsightSolverError(
                "candidate policy chain identity is invalid"
            )
        for row in chain:
            HindsightOriginPolicy(
                int(row["origin_index"]),
                _parse_utc(row["start_inclusive_utc"]),
                _parse_utc(row["end_exclusive_utc"]),
                _parse_utc(row["valid_from_utc"]),
                row["origin_selection_sha256"],
                row["candidate_bundle_sha256"],
                row["rotation_state_sha256"],
                int(row["max_roundtrips_per_utc_day"]),
                int(row["max_holding_minutes"]),
                row["entry_allowed"],
            )
    output = dict(_mapping(root["output"], "output"))
    if len(output.get("daily_net_usdc", [])) != PROCESS_DAYS:
        raise HindsightSolverError(
            "solver output must preserve all 365 UTC days"
        )
    if output.get("calendar_days") != PROCESS_DAYS:
        raise HindsightSolverError("solver calendar day count is invalid")
    if _dec(output.get("net_usdc")) != sum(
        (_dec(row["net_usdc"]) for row in output["daily_net_usdc"]),
        Decimal(0),
    ):
        raise HindsightSolverError(
            "solver total differs from daily output"
        )
    if output.get("trade_count") != len(output.get("trades", [])):
        raise HindsightSolverError(
            "solver trade count differs from trade output"
        )
    if output.get("solver_output_sha256") != _digest(
        {
            "daily_net_usdc": output["daily_net_usdc"],
            "trades": output["trades"],
        }
    ):
        raise HindsightSolverError("solver output digest mismatch")
    days = [row.get("day_utc") for row in output["daily_net_usdc"]]
    expected_days = [
        (start + timedelta(days=index)).isoformat()
        for index in range(PROCESS_DAYS)
    ]
    if days != expected_days:
        raise HindsightSolverError(
            "solver daily output has missing, duplicate, or reordered days"
        )
    if root["solver"] == ALL_CANDLE_SOLVER:
        if any(
            int(row.get("trade_count", -1)) not in (0, 1)
            for row in output["daily_net_usdc"]
        ):
            raise HindsightSolverError(
                "all-candle solver exceeded one trade per UTC day"
            )
        seen_days: set[str] = set()
        for trade in output["trades"]:
            entry_day = str(trade["entry_time_utc"])[:10]
            if (
                entry_day != str(trade["exit_time_utc"])[:10]
                or entry_day in seen_days
            ):
                raise HindsightSolverError(
                    "all-candle trade path violates the one-trade UTC-day contract"
                )
            seen_days.add(entry_day)
            if int(trade["exit_index"]) <= int(trade["entry_index"]):
                raise HindsightSolverError(
                    "all-candle exit must follow entry"
                )
    else:
        policies = {int(row["origin_index"]): row for row in chain}
        prior_exit = -1
        entry_counts: dict[tuple[str, str], int] = {}
        for trade in output["trades"]:
            entry = int(trade["entry_index"])
            exit_ = int(trade["exit_index"])
            if entry <= prior_exit or exit_ <= entry:
                raise HindsightSolverError(
                    "candidate solver trades overlap or are unordered"
                )
            prior_exit = exit_
            policy = policies.get(int(trade["origin_index"]))
            if (
                policy is None
                or trade["candidate_bundle_sha256"]
                != policy["candidate_bundle_sha256"]
            ):
                raise HindsightSolverError(
                    "candidate solver trade bundle/origin mismatch"
                )
            if int(trade["holding_minutes"]) > int(
                policy["max_holding_minutes"]
            ):
                raise HindsightSolverError(
                    "candidate solver exceeded matched holding duration"
                )
            entry_time = _parse_utc(str(trade["entry_time_utc"]))
            if not (
                _parse_utc(policy["valid_from_utc"])
                <= entry_time
                < _parse_utc(policy["end_exclusive_utc"])
            ):
                raise HindsightSolverError(
                    "candidate solver entry violates T+24 or origin validity"
                )
            key = (
                policy["candidate_bundle_sha256"],
                entry_time.date().isoformat(),
            )
            entry_counts[key] = entry_counts.get(key, 0) + 1
            if entry_counts[key] > int(
                policy["max_roundtrips_per_utc_day"]
            ):
                raise HindsightSolverError(
                    "candidate solver exceeded matched trade count"
                )
    basis = dict(root)
    observed = _sha(basis.pop("evidence_sha256"), "evidence_sha256")
    if observed != _digest(basis):
        raise HindsightSolverError("solver evidence digest mismatch")
    return HindsightSolverEvidence(_canonical(basis), observed)


def _validate_process_candles(
    candles: Sequence[Candle], start: date, end: date
) -> tuple[tuple[Candle, ...], str]:
    if (
        not isinstance(start, date)
        or isinstance(start, datetime)
        or not isinstance(end, date)
        or isinstance(end, datetime)
    ):
        raise HindsightSolverError("process boundaries must be dates")
    if (end - start).days != PROCESS_DAYS:
        raise HindsightSolverError(
            "hindsight process must contain exactly 365 UTC days"
        )
    if (
        not isinstance(candles, Sequence)
        or isinstance(candles, (str, bytes))
        or len(candles) != _PROCESS_MINUTES
    ):
        raise HindsightSolverError(
            "hindsight process requires exactly 525,600 one-minute candles"
        )
    expected = int(
        datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp()
        * 1000
    )
    hasher = hashlib.sha256()
    positive_by_day = [0] * PROCESS_DAYS
    rows: list[Candle] = []
    for index, candle in enumerate(candles):
        if not isinstance(candle, Candle):
            raise HindsightSolverError(
                "process data must contain Candle values"
            )
        if candle.open_time != expected + index * EXPECTED_STEP_MS:
            raise HindsightSolverError(
                "process candles contain a missing, duplicate, or reordered minute"
            )
        values = (
            candle.open,
            candle.high,
            candle.low,
            candle.close,
            candle.volume,
        )
        if any(not math.isfinite(float(value)) for value in values):
            raise HindsightSolverError(
                "process OHLCV values must be finite"
            )
        if (
            min(candle.open, candle.high, candle.low, candle.close) <= 0
            or candle.high
            < max(candle.open, candle.low, candle.close)
            or candle.low
            > min(candle.open, candle.high, candle.close)
        ):
            raise HindsightSolverError(
                "process candle prices are invalid"
            )
        if candle.volume < 0:
            raise HindsightSolverError(
                "process volume must be non-negative"
            )
        positive_by_day[index // MINUTES_PER_DAY] += int(
            candle.volume > 0
        )
        hasher.update(
            struct.pack(
                ">qddddd",
                candle.open_time,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
            )
        )
        rows.append(candle)
    if any(count == 0 for count in positive_by_day):
        raise HindsightSolverError(
            "every process UTC day requires positive-volume tradable data"
        )
    return tuple(rows), hasher.hexdigest()


def _validate_policies(
    plan: MonthlyProcessBoundaryPlan,
    policies: Sequence[HindsightOriginPolicy],
) -> tuple[HindsightOriginPolicy, ...]:
    if (
        not isinstance(policies, Sequence)
        or isinstance(policies, (str, bytes))
        or len(policies) != 12
    ):
        raise HindsightSolverError(
            "candidate-matched solver requires exactly twelve origin policies"
        )
    result = tuple(policies)
    for policy, origin in zip(result, plan.origins, strict=True):
        if not isinstance(policy, HindsightOriginPolicy):
            raise HindsightSolverError(
                "verified HindsightOriginPolicy required"
            )
        if (
            policy.origin_index != origin.origin_index
            or policy.start_inclusive_utc
            != _midnight(origin.test_start_inclusive)
            or policy.end_exclusive_utc
            != _midnight(origin.test_end_exclusive)
            or policy.valid_from_utc != origin.valid_from
        ):
            raise HindsightSolverError(
                "origin policy boundary or T+24 validity mismatch"
            )
    return result


def _execution_rules(
    snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
) -> tuple[MarketExecutionRules, str]:
    validate_exchange_info_snapshot(snapshot)
    payload = (
        snapshot.to_dict()
        if isinstance(snapshot, FrozenExchangeInfoSnapshot)
        else dict(snapshot)
    )
    rules = build_market_execution_rules(payload)
    return rules, _sha(
        payload.get("snapshot_sha256"),
        "exchange_info_snapshot_sha256",
    )


def _entry_line(
    state: _State,
    candle: Candle,
    index: int,
    entry_count: int,
    policy: HindsightOriginPolicy,
    rules: MarketExecutionRules,
) -> _Line:
    reference = _dec(candle.close)
    fill = _buy_fill(
        reference,
        BASELINE_COST_PROFILE.slippage_bps_per_side,
        rules,
    )
    entry = prepare_market_entry(
        fill, BASELINE_COST_PROFILE.fee_rate, rules
    )
    expiry = min(
        index + policy.max_holding_minutes,
        _PROCESS_MINUTES - 1,
    )
    return _Line(
        slope=entry.executed_quantity,
        intercept=state.value - entry.entry_cash_cost_including_fee,
        entry_index=index,
        expiry_index=expiry,
        entry_day=_time(candle.open_time).date(),
        entry_count=entry_count,
        candidate_bundle_sha256=policy.candidate_bundle_sha256,
        origin_index=policy.origin_index,
        entry_time_utc=_utc_text(_time(candle.open_time)),
        entry_reference_price=reference,
        entry_fill_price=fill,
        executed_quantity=entry.executed_quantity,
        executed_entry_notional=entry.executed_entry_notional,
        entry_fee=entry.entry_fee,
        entry_cash_cost=entry.entry_cash_cost_including_fee,
        base_path=state.path,
    )


def _close_line(
    line: _Line,
    candle: Candle,
    index: int,
    exit_fill: Decimal,
    rules: MarketExecutionRules,
) -> _State:
    if index <= line.entry_index:
        raise HindsightSolverError(
            "hindsight exit must be strictly later than entry"
        )
    if index > line.expiry_index:
        raise HindsightSolverError(
            "hindsight trade exceeds matched holding duration"
        )
    exit_value = prepare_market_exit(
        exit_fill,
        line.executed_quantity,
        BASELINE_COST_PROFILE.fee_rate,
        rules,
    )
    net = exit_value.exit_proceeds_after_fee - line.entry_cash_cost
    trade = {
        "entry_time_utc": line.entry_time_utc,
        "exit_time_utc": _utc_text(_time(candle.open_time)),
        "entry_index": line.entry_index,
        "exit_index": index,
        "holding_minutes": index - line.entry_index,
        "origin_index": line.origin_index,
        "candidate_bundle_sha256": line.candidate_bundle_sha256,
        "entry_reference_price": _text(line.entry_reference_price),
        "entry_fill_price": _text(line.entry_fill_price),
        "exit_reference_price": _text(_dec(candle.close)),
        "exit_fill_price": _text(exit_fill),
        "executed_quantity": _text(line.executed_quantity),
        "executed_entry_notional_usdc": _text(
            line.executed_entry_notional
        ),
        "entry_fee_usdc": _text(line.entry_fee),
        "exit_fee_usdc": _text(exit_value.exit_fee),
        "net_usdc": _text(net),
        "terminal_liquidation": False,
    }
    value = line.intercept + line.slope * exit_fill * (
        Decimal("1") - BASELINE_COST_PROFILE.fee_rate
    )
    return _State(value, _append_path(line.base_path, trade))


def _trade_from_closes(
    entry_candle: Candle,
    exit_candle: Candle,
    *,
    entry_index: int,
    exit_index: int,
    bundle_sha256: str | None,
    origin_index: int | None,
    rules: MarketExecutionRules,
) -> dict[str, Any]:
    entry_reference = _dec(entry_candle.close)
    exit_reference = _dec(exit_candle.close)
    entry_fill = _buy_fill(
        entry_reference,
        BASELINE_COST_PROFILE.slippage_bps_per_side,
        rules,
    )
    sell_fill = _sell_fill(
        exit_reference,
        BASELINE_COST_PROFILE.slippage_bps_per_side,
        rules,
    )
    entry = prepare_market_entry(
        entry_fill, BASELINE_COST_PROFILE.fee_rate, rules
    )
    exit_value = prepare_market_exit(
        sell_fill,
        entry.executed_quantity,
        BASELINE_COST_PROFILE.fee_rate,
        rules,
    )
    net = exit_value.exit_proceeds_after_fee - entry.entry_cash_cost_including_fee
    return {
        "entry_time_utc": _utc_text(_time(entry_candle.open_time)),
        "exit_time_utc": _utc_text(_time(exit_candle.open_time)),
        "entry_index": entry_index,
        "exit_index": exit_index,
        "holding_minutes": exit_index - entry_index,
        "origin_index": origin_index,
        "candidate_bundle_sha256": bundle_sha256,
        "entry_reference_price": _text(entry_reference),
        "entry_fill_price": _text(entry_fill),
        "exit_reference_price": _text(exit_reference),
        "exit_fill_price": _text(sell_fill),
        "executed_quantity": _text(entry.executed_quantity),
        "executed_entry_notional_usdc": _text(
            entry.executed_entry_notional
        ),
        "entry_fee_usdc": _text(entry.entry_fee),
        "exit_fee_usdc": _text(exit_value.exit_fee),
        "net_usdc": _text(net),
        "terminal_liquidation": False,
    }


def _solver_evidence(
    name: str,
    *,
    data_sha: str,
    exchange_sha: str,
    rules: MarketExecutionRules,
    policy_chain: list[dict[str, Any]] | None,
    process_start: date,
    process_end: date,
    daily: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    total: Decimal,
) -> HindsightSolverEvidence:
    input_identity = {
        "ethusdc_process_data_sha256": _sha(
            data_sha, "ethusdc_process_data_sha256"
        ),
        "exchange_info_snapshot_sha256": exchange_sha,
        "execution_rules_sha256": rules.rules_sha256,
        "execution_parity_contract_version": (
            EXECUTION_PARITY_CONTRACT_VERSION
        ),
        "intrabar_execution_contract_version": (
            INTRABAR_EXECUTION_CONTRACT_VERSION
        ),
        "cost_profile": {
            "name": BASELINE_COST_PROFILE.name,
            "fee_bps_per_side": _text(
                BASELINE_COST_PROFILE.fee_bps_per_side
            ),
            "slippage_bps_per_side": _text(
                BASELINE_COST_PROFILE.slippage_bps_per_side
            ),
        },
        "positive_volume_only": True,
        "process_start_inclusive": process_start.isoformat(),
        "process_end_exclusive": process_end.isoformat(),
        "policy_chain": policy_chain,
        "policy_chain_sha256": (
            _digest(policy_chain) if policy_chain is not None else None
        ),
    }
    output = {
        "calendar_days": PROCESS_DAYS,
        "daily_net_usdc": daily,
        "trades": trades,
        "trade_count": len(trades),
        "net_usdc": _text(total),
        "usdc_per_calendar_day": _text(total / Decimal(PROCESS_DAYS)),
        "solver_output_sha256": _digest(
            {"daily_net_usdc": daily, "trades": trades}
        ),
    }
    basis = {
        "schema_version": SOLVER_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": SOLVER_CONTRACT_VERSION,
        "solver": name,
        "input_identity": input_identity,
        "output": output,
        "uses_future_prices_for_diagnostic_only": True,
        "lookahead_safe": False,
        "diagnostic_only": True,
        "selection_feedback_allowed": False,
        "monthly_quality_gate_feedback_allowed": False,
        "canonical_adoption_eligible": False,
        "safety": _SAFETY,
    }
    return validate_hindsight_solver_evidence(
        HindsightSolverEvidence(_canonical(basis), _digest(basis))
    )


def _build_upper_hull(
    lines: Sequence[_Line],
) -> tuple[tuple[_Line, Decimal | None], ...]:
    best_by_slope: dict[Decimal, _Line] = {}
    for line in lines:
        current = best_by_slope.get(line.slope)
        if (
            current is None
            or line.intercept > current.intercept
            or (
                line.intercept == current.intercept
                and line.tie_key < current.tie_key
            )
        ):
            best_by_slope[line.slope] = line
    hull: list[tuple[_Line, Decimal | None]] = []
    for line in sorted(
        best_by_slope.values(),
        key=lambda item: (item.slope, item.tie_key),
    ):
        start: Decimal | None = None
        while hull:
            previous, previous_start = hull[-1]
            start = (previous.intercept - line.intercept) / (
                line.slope - previous.slope
            )
            if previous_start is None or start > previous_start:
                break
            hull.pop()
        if not hull:
            start = None
        hull.append((line, start))
    return tuple(hull)


def _best_line(
    lines: Sequence[_Line], x: Decimal, fee_rate: Decimal
) -> _Line | None:
    best: _Line | None = None
    best_value = Decimal("-Infinity")
    for line in lines:
        value = line.evaluate(x, fee_rate)
        if value > best_value or (
            value == best_value
            and best is not None
            and line.tie_key < best.tie_key
        ):
            best = line
            best_value = value
    return best


def _best_across_queues(
    queues: Any, x: Decimal, fee_rate: Decimal
) -> _Line | None:
    candidates = []
    for queue in queues:
        line = queue.best(x, fee_rate)
        if line is not None:
            candidates.append(line)
    return _best_line(candidates, x, fee_rate)


def _better_state(current: _State, candidate: _State) -> _State:
    return candidate if _state_better(candidate, current) else current


def _state_better(left: _State, right: _State) -> bool:
    return left.value > right.value or (
        left.value == right.value
        and _path_sha(left.path) < _path_sha(right.path)
    )


def _append_path(
    previous: _PathNode | None, trade: Mapping[str, Any]
) -> _PathNode:
    count = _path_count(previous) + 1
    digest = hashlib.sha256(
        f"{_path_sha(previous)}:{_digest(trade)}".encode()
    ).hexdigest()
    return _PathNode(previous, dict(trade), count, digest)


def _path_count(path: _PathNode | None) -> int:
    return 0 if path is None else path.count


def _path_sha(path: _PathNode | None) -> str:
    return "0" * 64 if path is None else path.path_sha256


def _path_trades(path: _PathNode | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    while path is not None:
        rows.append(dict(path.trade))
        path = path.previous
    rows.reverse()
    return rows


def _validate_candidate_trade_path(
    trades: Sequence[Mapping[str, Any]],
    policies: Sequence[HindsightOriginPolicy],
    plan: MonthlyProcessBoundaryPlan,
) -> None:
    prior_exit = -1
    counts: dict[tuple[str, str], int] = {}
    policy_by_origin = {row.origin_index: row for row in policies}
    for raw in trades:
        trade = dict(raw)
        entry = int(trade["entry_index"])
        exit_ = int(trade["exit_index"])
        if entry <= prior_exit or exit_ <= entry:
            raise HindsightSolverError(
                "candidate hindsight trades overlap or are unordered"
            )
        prior_exit = exit_
        origin = policy_by_origin[int(trade["origin_index"])]
        if (
            trade["candidate_bundle_sha256"]
            != origin.candidate_bundle_sha256
        ):
            raise HindsightSolverError(
                "candidate hindsight trade bundle mismatch"
            )
        if int(trade["holding_minutes"]) > origin.max_holding_minutes:
            raise HindsightSolverError(
                "candidate hindsight holding duration exceeded"
            )
        day = str(trade["entry_time_utc"])[:10]
        key = (origin.candidate_bundle_sha256, day)
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > origin.max_roundtrips_per_utc_day:
            raise HindsightSolverError(
                "candidate hindsight trade limit exceeded"
            )
        at = _parse_utc(str(trade["entry_time_utc"]))
        if (
            not origin.entry_allowed
            or not origin.valid_from_utc <= at < origin.end_exclusive_utc
        ):
            raise HindsightSolverError(
                "candidate hindsight entry violates T+24 or origin validity"
            )
    if trades and str(trades[-1]["exit_time_utc"]) > _utc_text(
        _midnight(plan.process_end_exclusive)
    ):
        raise HindsightSolverError(
            "candidate hindsight exits after process end"
        )


def _trade_tie(trade: Mapping[str, Any]) -> tuple[int, int]:
    return int(trade["entry_index"]), int(trade["exit_index"])


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise HindsightSolverError(f"{name} must be an object")
    return value


def _dec(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise HindsightSolverError("numeric value is invalid") from exc
    if not result.is_finite():
        raise HindsightSolverError("numeric value must be finite")
    return result


def _text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _sha(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise HindsightSolverError(
            f"{name} must be lowercase sha256"
        )
    return value


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _time(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


def _midnight(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)


def _utc(value: datetime, name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise HindsightSolverError(f"{name} must be UTC")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise HindsightSolverError(
            "timestamp must be canonical UTC text"
        )
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise HindsightSolverError("timestamp is invalid") from exc
    return _utc(parsed, "timestamp")


__all__ = [
    "ALL_CANDLE_SOLVER",
    "CANDIDATE_MATCHED_SOLVER",
    "HindsightOriginPolicy",
    "HindsightSolverError",
    "HindsightSolverEvidence",
    "PROCESS_DAYS",
    "SOLVER_CONTRACT_VERSION",
    "SOLVER_SCHEMA_VERSION",
    "solve_all_candle_one_trade_close_hindsight",
    "solve_candidate_matched_volume_filtered_hindsight",
    "validate_hindsight_solver_evidence",
]
