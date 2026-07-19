"""Task-25 daily outer MTM ledger and non-overlapping time aggregations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Final

from .boundaries import (
    MonthlyProcessBoundaryPlan,
    validate_monthly_process_boundary_plan,
)
from .outer_origins import OuterOriginProcess, validate_outer_origin_process
from .runtime_state import (
    OuterRotationState,
    restore_outer_rotation_state,
    validate_outer_rotation_state,
)

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path("configs/protocol_v3_outer_mtm_ledger_contract.json")
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_outer_mtm_ledger_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_daily_mtm_and_separate_time_aggregations_v1"
LEDGER_SCHEMA_VERSION: Final = "protocol_v3_outer_daily_mtm_ledger_v1"
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "ledger_policy": {
        "outer_origins": 12,
        "process_oos_days": 365,
        "complete_contiguous_utc_day_grid_required": True,
        "explicit_zero_days_required": True,
        "daily_net_is_closing_equity_delta": True,
        "process_ends_flat": True,
        "process_mtm_total_must_equal_closed_trade_net_total": True,
    },
    "attribution_policy": {
        "deployment_intervals_follow_frozen_boundaries": True,
        "calendar_months_follow_utc_days": True,
        "calendar_quarters_follow_utc_days": True,
        "closed_trades_follow_utc_exit_time": True,
        "fees_and_slippage_follow_actual_execution_day": True,
        "mtm_and_closed_trade_pnl_are_never_added_together": True,
    },
    "output_policy": {
        "deployment_intervals": 12,
        "all_touched_calendar_months_required": True,
        "all_touched_calendar_quarters_required": True,
        "content_hash_required": True,
        "monthly_quality_gate_deferred_to_task": 26,
    },
    "safety": _SAFETY,
}


class OuterMtmLedgerError(ValueError):
    """Raised when daily or time-attribution evidence is incomplete."""


@dataclass(frozen=True)
class OriginLedgerInput:
    origin_index: int
    origin_selection_sha256: str
    candidate_bundle_sha256: str
    rotation_state: OuterRotationState
    opening_equity_usdc: Any
    ending_open_position_bundle_sha256: str | None
    daily_mtm: Sequence[Mapping[str, Any]]
    closed_trades: Sequence[Mapping[str, Any]] = ()
    friction_events: Sequence[Mapping[str, Any]] = ()


@dataclass(frozen=True)
class OuterMtmLedger:
    canonical_json: str
    ledger_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["ledger_sha256"] = self.ledger_sha256
        return value


def load_outer_mtm_ledger_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OuterMtmLedgerError(
            "outer MTM ledger contract is missing or invalid"
        ) from exc
    if value != _CANONICAL_CONTRACT:
        raise OuterMtmLedgerError("outer MTM ledger contract is not canonical")
    return value


def build_outer_mtm_ledger(
    boundary_plan: MonthlyProcessBoundaryPlan,
    outer_process: OuterOriginProcess,
    origin_ledgers: Sequence[OriginLedgerInput],
) -> OuterMtmLedger:
    validate_monthly_process_boundary_plan(boundary_plan)
    process = validate_outer_origin_process(outer_process, boundary_plan=boundary_plan)
    if (
        not isinstance(origin_ledgers, Sequence)
        or isinstance(origin_ledgers, (str, bytes))
        or len(origin_ledgers) != 12
    ):
        raise OuterMtmLedgerError(
            "outer MTM ledger requires exactly twelve origin ledgers"
        )
    process_rows = process.to_dict()["origins"]
    origins: list[dict[str, Any]] = []
    expected_open = Decimal("0")
    for value, boundary, selected in zip(
        origin_ledgers, boundary_plan.origins, process_rows, strict=True
    ):
        normalized = _normalize_origin(value, boundary, selected, expected_open)
        origins.append(normalized)
        expected_open = _decimal(
            normalized["daily_mtm"][-1]["closing_equity_usdc"],
            "closing_equity_usdc",
        )
    for current, following in zip(origins, origins[1:], strict=False):
        following_position = following["rotation_state"]["open_position"]
        carried_bundle = (
            following_position["candidate_bundle_sha256"]
            if following_position is not None
            else None
        )
        if current["ending_open_position_bundle_sha256"] != carried_bundle:
            raise OuterMtmLedgerError(
                "ending position does not match the next origin rotation carry"
            )
    if origins[-1]["ending_open_position_bundle_sha256"] is not None:
        raise OuterMtmLedgerError("outer MTM process must end flat")
    daily = [row for origin in origins for row in origin["daily_mtm"]]
    expected_days = [day.isoformat() for day in boundary_plan.iter_process_oos_days()]
    if [row["day_utc"] for row in daily] != expected_days:
        raise OuterMtmLedgerError(
            "chained daily MTM grid is incomplete, duplicated, or reordered"
        )
    trades = [row for origin in origins for row in origin["closed_trades"]]
    events = [row for origin in origins for row in origin["friction_events"]]
    _unique_ordered(trades, "exit_time_utc", "trade_id", "closed trades")
    _unique_ordered(events, "execution_time_utc", "event_id", "friction events")
    _validate_trade_friction(trades, events)
    total_mtm = _sum(row["net_mtm_usdc"] for row in daily)
    total_closed = _sum(row["net_usdc"] for row in trades)
    if total_mtm != total_closed:
        raise OuterMtmLedgerError(
            "process MTM total differs from closed-trade net total"
        )
    if daily[-1]["closing_equity_usdc"] != _decimal_text(total_mtm):
        raise OuterMtmLedgerError("process final equity differs from process MTM total")
    basis = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "outer_process_sha256": process.process_sha256,
        "process_start_inclusive": boundary_plan.process_start_inclusive.isoformat(),
        "process_end_exclusive": boundary_plan.process_end_exclusive.isoformat(),
        "origin_ledgers": origins,
        "daily_mtm": daily,
        "closed_trades": trades,
        "friction_events": events,
        "deployment_intervals": [_deployment(row) for row in origins],
        "calendar_months": _calendar(daily, trades, "month"),
        "calendar_quarters": _calendar(daily, trades, "quarter"),
        "totals": {
            "calendar_days": 365,
            "net_mtm_usdc": _decimal_text(total_mtm),
            "closed_trade_net_usdc_diagnostic": _decimal_text(total_closed),
            "trade_count": len(trades),
            "fees_usdc": _decimal_text(_sum(row["fees_usdc"] for row in trades)),
            "slippage_usdc": _decimal_text(
                _sum(row["slippage_usdc"] for row in trades)
            ),
            "pnl_combination_policy": "mtm_primary_closed_trade_diagnostic_never_added",
        },
        "safety": _SAFETY,
    }
    return validate_outer_mtm_ledger(
        OuterMtmLedger(_canonical(basis), _digest(basis)),
        boundary_plan=boundary_plan,
        outer_process=process,
    )


def validate_outer_mtm_ledger(
    value: OuterMtmLedger | Mapping[str, Any],
    *,
    boundary_plan: MonthlyProcessBoundaryPlan,
    outer_process: OuterOriginProcess,
) -> OuterMtmLedger:
    root = (
        value.to_dict()
        if isinstance(value, OuterMtmLedger)
        else dict(_mapping(value, "outer_mtm_ledger"))
    )
    required = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "outer_process_sha256",
        "process_start_inclusive",
        "process_end_exclusive",
        "origin_ledgers",
        "daily_mtm",
        "closed_trades",
        "friction_events",
        "deployment_intervals",
        "calendar_months",
        "calendar_quarters",
        "totals",
        "safety",
        "ledger_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != LEDGER_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
    ):
        raise OuterMtmLedgerError("outer MTM ledger fields or versions are invalid")
    rebuilt = (
        build_outer_mtm_ledger(
            boundary_plan,
            outer_process,
            [
                OriginLedgerInput(
                    row["origin_index"],
                    row["origin_selection_sha256"],
                    row["candidate_bundle_sha256"],
                    restore_outer_rotation_state(row["rotation_state"]),
                    row["opening_equity_usdc"],
                    row["ending_open_position_bundle_sha256"],
                    row["daily_mtm"],
                    row["closed_trades"],
                    row["friction_events"],
                )
                for row in root["origin_ledgers"]
            ],
        )
        if not isinstance(value, OuterMtmLedger)
        else None
    )
    if rebuilt is not None and rebuilt.to_dict() != root:
        raise OuterMtmLedgerError("outer MTM ledger content is not canonical")
    if (
        root["outer_process_sha256"]
        != validate_outer_origin_process(
            outer_process, boundary_plan=boundary_plan
        ).process_sha256
    ):
        raise OuterMtmLedgerError("outer MTM ledger process identity mismatch")
    observed = _sha(root["ledger_sha256"], "ledger_sha256")
    basis = dict(root)
    basis.pop("ledger_sha256")
    if observed != _digest(basis):
        raise OuterMtmLedgerError("outer MTM ledger digest mismatch")
    return OuterMtmLedger(_canonical(basis), observed)


def _normalize_origin(
    value: OriginLedgerInput,
    boundary: Any,
    selected: Mapping[str, Any],
    expected_opening_equity: Decimal,
) -> dict[str, Any]:
    if (
        not isinstance(value, OriginLedgerInput)
        or value.origin_index != boundary.origin_index
    ):
        raise OuterMtmLedgerError("origin ledger order or index mismatch")
    if (
        _sha(value.origin_selection_sha256, "origin_selection_sha256")
        != selected["origin_sha256"]
    ):
        raise OuterMtmLedgerError("origin ledger selection identity mismatch")
    bundle = selected["frozen_candidate_bundle"]["bundle_sha256"]
    if _sha(value.candidate_bundle_sha256, "candidate_bundle_sha256") != bundle:
        raise OuterMtmLedgerError("origin ledger candidate bundle mismatch")
    validate_outer_rotation_state(value.rotation_state, origin=boundary)
    if value.rotation_state.new_candidate_bundle_sha256 != bundle:
        raise OuterMtmLedgerError("origin rotation state candidate bundle mismatch")
    opening = _decimal(value.opening_equity_usdc, "opening_equity_usdc")
    if opening != expected_opening_equity:
        raise OuterMtmLedgerError(
            "origin opening equity does not chain from prior origin"
        )
    ending_bundle = value.ending_open_position_bundle_sha256
    if ending_bundle is not None:
        _sha(ending_bundle, "ending_open_position_bundle_sha256")
    expected = [day.isoformat() for day in boundary.iter_test_days()]
    daily: list[dict[str, str]] = []
    prior = opening
    for index, raw in enumerate(value.daily_mtm):
        row = dict(_mapping(raw, f"origin.daily_mtm[{index}]"))
        if set(row) != {"day_utc", "net_mtm_usdc", "closing_equity_usdc"}:
            raise OuterMtmLedgerError("daily MTM row fields are invalid")
        net = _decimal(row["net_mtm_usdc"], "net_mtm_usdc")
        close = _decimal(row["closing_equity_usdc"], "closing_equity_usdc")
        if close != prior + net:
            raise OuterMtmLedgerError("daily net MTM is not the closing-equity delta")
        prior = close
        daily.append(
            {
                "day_utc": _day(row["day_utc"]),
                "net_mtm_usdc": _decimal_text(net),
                "closing_equity_usdc": _decimal_text(close),
            }
        )
    if [row["day_utc"] for row in daily] != expected:
        raise OuterMtmLedgerError(
            "origin daily MTM must contain every UTC day exactly once"
        )
    trades = [
        _trade(row, boundary, value.rotation_state) for row in value.closed_trades
    ]
    events = [_friction(row, boundary) for row in value.friction_events]
    return {
        "origin_index": value.origin_index,
        "origin_selection_sha256": value.origin_selection_sha256,
        "candidate_bundle_sha256": bundle,
        "rotation_state": value.rotation_state.basis(),
        "rotation_state_sha256": value.rotation_state.state_sha256,
        "opening_equity_usdc": _decimal_text(opening),
        "ending_open_position_bundle_sha256": ending_bundle,
        "start_inclusive": boundary.test_start_inclusive.isoformat(),
        "end_exclusive": boundary.test_end_exclusive.isoformat(),
        "daily_mtm": daily,
        "closed_trades": trades,
        "friction_events": events,
    }


def _trade(
    raw: Mapping[str, Any],
    boundary: Any,
    rotation: OuterRotationState,
) -> dict[str, Any]:
    row = dict(_mapping(raw, "closed_trade"))
    required = {
        "trade_id",
        "candidate_bundle_sha256",
        "entry_time_utc",
        "exit_time_utc",
        "gross_usdc",
        "fees_usdc",
        "slippage_usdc",
        "net_usdc",
        "terminal_liquidation",
    }
    if (
        set(row) != required
        or not isinstance(row["trade_id"], str)
        or not row["trade_id"]
        or type(row["terminal_liquidation"]) is not bool
    ):
        raise OuterMtmLedgerError("closed trade fields are invalid")
    entry, exit_at = _utc(row["entry_time_utc"]), _utc(row["exit_time_utc"])
    if (
        exit_at < entry
        or not boundary.test_start_inclusive
        <= exit_at.date()
        < boundary.test_end_exclusive
    ):
        raise OuterMtmLedgerError(
            "closed trade must be attributed to its UTC exit origin"
        )
    candidate = _sha(row["candidate_bundle_sha256"], "candidate_bundle_sha256")
    if entry.date() < boundary.test_start_inclusive:
        if (
            rotation.open_position is None
            or candidate != rotation.open_position.candidate_bundle_sha256
        ):
            raise OuterMtmLedgerError(
                "cross-origin trade must match the carried exit-only position"
            )
    elif candidate != rotation.new_candidate_bundle_sha256:
        raise OuterMtmLedgerError("new-origin trade candidate bundle mismatch")
    if row["terminal_liquidation"] and (
        boundary.origin_index != 12
        or exit_at.date() != boundary.test_end_exclusive - timedelta(days=1)
    ):
        raise OuterMtmLedgerError(
            "terminal liquidation is permitted only on the final process day"
        )
    gross, fees, slip, net = (
        _decimal(row[key], key)
        for key in ("gross_usdc", "fees_usdc", "slippage_usdc", "net_usdc")
    )
    if fees < 0 or slip < 0 or net != gross - fees - slip:
        raise OuterMtmLedgerError("closed trade net/friction arithmetic is invalid")
    return {
        "trade_id": row["trade_id"],
        "candidate_bundle_sha256": candidate,
        "entry_time_utc": _utc_text(entry),
        "exit_time_utc": _utc_text(exit_at),
        "gross_usdc": _decimal_text(gross),
        "fees_usdc": _decimal_text(fees),
        "slippage_usdc": _decimal_text(slip),
        "net_usdc": _decimal_text(net),
        "terminal_liquidation": row["terminal_liquidation"],
    }


def _friction(raw: Mapping[str, Any], boundary: Any) -> dict[str, str]:
    row = dict(_mapping(raw, "friction_event"))
    required = {"event_id", "trade_id", "execution_time_utc", "kind", "amount_usdc"}
    if (
        set(row) != required
        or not all(
            isinstance(row[key], str) and row[key] for key in ("event_id", "trade_id")
        )
        or row["kind"] not in {"fee", "slippage"}
    ):
        raise OuterMtmLedgerError("friction event fields are invalid")
    at = _utc(row["execution_time_utc"])
    amount = _decimal(row["amount_usdc"], "amount_usdc")
    if (
        amount < 0
        or not boundary.test_start_inclusive <= at.date() < boundary.test_end_exclusive
    ):
        raise OuterMtmLedgerError("friction event must use its actual execution day")
    return {
        "event_id": row["event_id"],
        "trade_id": row["trade_id"],
        "execution_time_utc": _utc_text(at),
        "kind": row["kind"],
        "amount_usdc": _decimal_text(amount),
    }


def _validate_trade_friction(
    trades: list[dict[str, Any]], events: list[dict[str, str]]
) -> None:
    by_trade: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"fee": Decimal("0"), "slippage": Decimal("0")}
    )
    ids = {row["trade_id"] for row in trades}
    if len(ids) != len(trades):
        raise OuterMtmLedgerError("trade IDs must be unique")
    for event in events:
        if event["trade_id"] not in ids:
            raise OuterMtmLedgerError("friction event references unknown trade")
        by_trade[event["trade_id"]][event["kind"]] += _decimal(
            event["amount_usdc"], "amount_usdc"
        )
    for trade in trades:
        totals = by_trade[trade["trade_id"]]
        if totals["fee"] != _decimal(trade["fees_usdc"], "fees_usdc") or totals[
            "slippage"
        ] != _decimal(trade["slippage_usdc"], "slippage_usdc"):
            raise OuterMtmLedgerError(
                "trade friction totals differ from execution-day events"
            )


def _deployment(origin: Mapping[str, Any]) -> dict[str, Any]:
    net = _sum(row["net_mtm_usdc"] for row in origin["daily_mtm"])
    return {
        "origin_index": origin["origin_index"],
        "start_inclusive": origin["start_inclusive"],
        "end_exclusive": origin["end_exclusive"],
        "calendar_days": len(origin["daily_mtm"]),
        "net_mtm_usdc": _decimal_text(net),
        "exit_trade_count": len(origin["closed_trades"]),
        "positive": net > 0,
        "active": len(origin["closed_trades"]) > 0,
    }


def _calendar(
    daily: list[dict[str, str]], trades: list[dict[str, Any]], unit: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    exits: dict[str, int] = defaultdict(int)

    def key(day: str) -> str:
        return (
            day[:7] if unit == "month" else f"{day[:4]}-Q{(int(day[5:7]) - 1) // 3 + 1}"
        )

    for row in daily:
        grouped[key(row["day_utc"])].append(row)
    for trade in trades:
        exits[key(trade["exit_time_utc"][:10])] += 1
    return [
        {
            "period": period,
            "calendar_days": len(rows),
            "net_mtm_usdc": _decimal_text(_sum(row["net_mtm_usdc"] for row in rows)),
            "exit_trade_count": exits[period],
            "positive": _sum(row["net_mtm_usdc"] for row in rows) > 0,
            "active": exits[period] > 0,
        }
        for period, rows in sorted(grouped.items())
    ]


def _unique_ordered(
    rows: list[dict[str, Any]], time_key: str, id_key: str, label: str
) -> None:
    keys = [(row[time_key], row[id_key]) for row in rows]
    if keys != sorted(keys) or len({row[id_key] for row in rows}) != len(rows):
        raise OuterMtmLedgerError(f"{label} must be uniquely ordered")


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise OuterMtmLedgerError(f"{label} must be an object")
    return value


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise OuterMtmLedgerError(f"{label} must be finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise OuterMtmLedgerError(f"{label} must be finite decimal") from exc
    if not result.is_finite():
        raise OuterMtmLedgerError(f"{label} must be finite decimal")
    return result


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _sum(values: Any) -> Decimal:
    return sum((_decimal(value, "amount") for value in values), Decimal("0"))


def _day(value: Any) -> str:
    if not isinstance(value, str):
        raise OuterMtmLedgerError("day_utc must be ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise OuterMtmLedgerError("day_utc must be ISO date") from exc
    if parsed.isoformat() != value:
        raise OuterMtmLedgerError("day_utc is not canonical")
    return value


def _utc(value: Any) -> datetime:
    if not isinstance(value, str):
        raise OuterMtmLedgerError("timestamp must be UTC text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OuterMtmLedgerError("timestamp is invalid") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != datetime.min.replace(tzinfo=UTC).utcoffset()
    ):
        raise OuterMtmLedgerError("timestamp must be UTC")
    return parsed.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
        raise OuterMtmLedgerError(f"{label} must be sha256")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


__all__ = [
    "CONTRACT_PATH",
    "CONTRACT_SCHEMA_VERSION",
    "CONTRACT_VERSION",
    "LEDGER_SCHEMA_VERSION",
    "OriginLedgerInput",
    "OuterMtmLedger",
    "OuterMtmLedgerError",
    "build_outer_mtm_ledger",
    "load_outer_mtm_ledger_contract",
    "validate_outer_mtm_ledger",
]
