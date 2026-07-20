"""Task-29 order-free research-challenger controller and forward ledger.

The controller consumes a validated Task-28 decision, exact three-market closed
bars and the existing order-free portfolio reducer.  It has no exchange client,
account reader, order adapter, paper, testtrade, live or adoption entry point.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from ethusdc_bot.backtest.context_features import ContextDecision
from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS
from ethusdc_bot.backtest.equity import EquityPoint
from ethusdc_bot.backtest.portfolio_simulator import (
    CapacityRejection,
    PendingPortfolioEntry,
    PortfolioEngineState,
    PortfolioLot,
    PortfolioStepEvent,
    PortfolioTrade,
    advance_portfolio_engine,
    new_portfolio_engine_state,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.portfolio import PortfolioPolicy
from ethusdc_bot.protocol_v3.context_parity import (
    ContextParityBinding,
    evaluate_closed_bar_context,
    validate_context_parity_binding,
)
from ethusdc_bot.protocol_v3.current_refit import (
    CASH,
    CurrentRefitDecision,
    validate_current_refit_decision,
)

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_research_challenger_contract.json"
)
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_research_challenger_contract_v1"
CONTRACT_VERSION: Final = "protocol_v3_order_free_research_challenger_shadow_v1"
STATE_SCHEMA_VERSION: Final = "protocol_v3_research_challenger_state_v1"
LEDGER_SCHEMA_VERSION: Final = "protocol_v3_research_challenger_forward_ledger_v1"
ZERO_HASH: Final = "0" * 64
_SAFETY: Final = {
    "api_keys": "forbidden",
    "private_endpoints": "forbidden",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "live": "locked",
    "trading_api": "forbidden",
    "adopt_for_shadow": "forbidden",
}
_CANONICAL_CONTRACT: Final = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": CONTRACT_VERSION,
    "controller_policy": {
        "task28_typed_provenance_required": True,
        "manual_start_only": True,
        "ethusdc_only": True,
        "btcusdc_and_ethbtc_context_only": True,
        "exact_closed_three_market_bar_required": True,
        "one_open_lot_maximum": True,
        "refresh_and_replay_must_be_idempotent": True,
        "end_of_feed_may_not_liquidate": True,
    },
    "forward_ledger_policy": {
        "append_only_hash_chain": True,
        "explicit_no_trade_records": True,
        "bar_content_hashes_required": True,
        "context_decision_required": True,
        "virtual_fills_fees_slippage_positions_and_mtm": True,
        "raw_orders_forbidden": True,
    },
    "validity_policy": {
        "entries_before_valid_from_forbidden": True,
        "entries_at_or_after_valid_until_forbidden": True,
        "pending_entry_discarded_on_exit_only_transition": True,
        "open_position_may_exit_after_entry_window": True,
    },
    "evidence_policy": {
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "statistically_supported": False,
        "canonical_adoption_eligible": False,
        "protocol_v3_final_status": False,
    },
    "safety": _SAFETY,
}


class ResearchChallengerError(ValueError):
    """Raised when order-free forward replay is incomplete or contradictory."""


@dataclass(frozen=True)
class ResearchChallengerState:
    canonical_json: str
    state_sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        value["state_sha256"] = self.state_sha256
        return value


@dataclass(frozen=True)
class ResearchChallengerAdvance:
    state: ResearchChallengerState
    new_records: tuple[dict[str, Any], ...]


def load_research_challenger_contract(repo_root: str | Path) -> dict[str, Any]:
    path = Path(repo_root).resolve(strict=True) / CONTRACT_PATH
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchChallengerError(
            "research-challenger contract is missing or invalid"
        ) from exc
    if value != _CANONICAL_CONTRACT:
        raise ResearchChallengerError(
            "research-challenger contract is not canonical"
        )
    return value


def start_research_challenger(
    task28_decision: CurrentRefitDecision,
    *,
    started_at_utc: datetime,
) -> ResearchChallengerState:
    """Create an empty manual research state without activating another mode."""

    if not isinstance(task28_decision, CurrentRefitDecision):
        raise ResearchChallengerError(
            "typed validated Task-28 provenance is required"
        )
    task28 = validate_current_refit_decision(task28_decision).to_dict()
    _validate_task28_scope(task28)
    started = _utc(started_at_utc, "started_at_utc")
    bundle = task28["frozen_candidate_bundle"]
    valid_from = _parse_utc(bundle["validity"]["valid_from_utc"], "valid_from")
    valid_until = _parse_utc(bundle["validity"]["valid_until_utc"], "valid_until")
    if started < valid_from:
        raise ResearchChallengerError(
            "research challenger may not start before Task-28 valid_from"
        )
    if started >= valid_until:
        raise ResearchChallengerError(
            "historical or expired Task-28 challenger may not start"
        )
    strategy = _strategy_from_task28(task28)
    basis = {
        "schema_version": STATE_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "task28_decision": task28,
        "task28_report_sha256": task28["report_sha256"],
        "bundle_sha256": bundle["bundle_sha256"],
        "pipeline_generation_id": task28["identity_manifest"][
            "current_pipeline_generation_id"
        ],
        "run_fingerprint_sha256": task28["identity_manifest"][
            "current_run_fingerprint_sha256"
        ],
        "code_commit": task28["identity_manifest"]["current_code_commit"],
        "start_snapshot_sha256": task28["identity_manifest"][
            "current_data_snapshot_sha256"
        ],
        "exchange_info_snapshot_sha256": task28["identity_manifest"][
            "current_exchange_info_snapshot_sha256"
        ],
        "cost_source_sha256": task28["identity_manifest"][
            "current_cost_source_sha256"
        ],
        "strategy": _strategy_payload(strategy),
        "portfolio_policy": PortfolioPolicy(100).to_dict(),
        "started_at_utc": _utc_text(started),
        "valid_from_utc": _utc_text(valid_from),
        "valid_until_utc": _utc_text(valid_until),
        "mode": "CASH" if strategy is None else "RESEARCH_CHALLENGER",
        "engine_state": _engine_state_payload(new_portfolio_engine_state()),
        "forward_ledger": {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "records": [],
            "record_count": 0,
            "head_sha256": ZERO_HASH,
        },
        "last_processed_open_time_ms": None,
        "last_context_identity_sha256": None,
        "freshness": "NOT_FRESH",
        "diagnostic_only": True,
        "statistically_supported": False,
        "canonical_adoption_eligible": False,
        "protocol_v3_final_status": False,
        "orders_allowed": False,
        "paper_allowed": False,
        "testtrade_allowed": False,
        "live_allowed": False,
        "trading_api_allowed": False,
        "safety": _SAFETY,
    }
    return validate_research_challenger_state(
        ResearchChallengerState(_canonical(basis), _digest(basis))
    )


def advance_research_challenger(
    state: ResearchChallengerState,
    binding: ContextParityBinding,
    *,
    observed_at_utc: datetime,
) -> ResearchChallengerAdvance:
    """Append every newly closed aligned minute exactly once and without orders."""

    validated = validate_research_challenger_state(state)
    root = validated.to_dict()
    validate_context_parity_binding(binding)
    observed = _utc(observed_at_utc, "observed_at_utc")
    expected_observed = datetime.fromtimestamp(
        (binding.common_watermark_open_time_ms + EXPECTED_STEP_MS - 1) / 1000,
        tz=UTC,
    )
    if observed != expected_observed:
        raise ResearchChallengerError(
            "forward binding must end at the exact currently closed watermark"
        )
    _validate_existing_prefix(root, binding)
    strategy = _restore_strategy(root["strategy"])
    engine = _restore_engine_state(root["engine_state"])
    records = list(root["forward_ledger"]["records"])
    previous_head = root["forward_ledger"]["head_sha256"]
    valid_from_ms = int(_parse_utc(root["valid_from_utc"], "valid_from").timestamp() * 1000)
    valid_until_ms = int(_parse_utc(root["valid_until_utc"], "valid_until").timestamp() * 1000)
    last = root["last_processed_open_time_ms"]
    new_rows: list[dict[str, Any]] = []

    for index, candle in enumerate(binding.context.ethusdc):
        if candle.open_time < valid_from_ms:
            continue
        if last is not None and candle.open_time <= last:
            continue
        if last is not None and candle.open_time != last + EXPECTED_STEP_MS:
            raise ResearchChallengerError(
                "research-challenger forward minutes must be contiguous"
            )
        decision_time_ms = candle.open_time + EXPECTED_STEP_MS - 1
        context_decision = evaluate_closed_bar_context(
            binding, index, decision_time_ms=decision_time_ms
        )
        entry_window = candle.open_time < valid_until_ms
        if not entry_window and engine.pending_entry is not None:
            engine = replace(engine, pending_entry=None)
        mode = (
            "CASH"
            if strategy is None
            else "ACTIVE"
            if entry_window
            else "EXIT_ONLY"
        )
        events: tuple[PortfolioStepEvent, ...] = ()
        if strategy is not None:
            before = engine
            engine, events = advance_portfolio_engine(
                engine,
                candle,
                strategy,
                PortfolioPolicy(100),
                end_of_data=False,
            )
            entry_allowed = entry_window and context_decision.allowed
            if not entry_allowed and any(
                event.event_type == "entry_scheduled" for event in events
            ):
                engine = replace(
                    engine,
                    pending_entry=before.pending_entry,
                    max_reserved_notional_usdc=before.max_reserved_notional_usdc,
                )
                events = tuple(
                    event for event in events if event.event_type != "entry_scheduled"
                )
        entry_allowed = strategy is not None and entry_window and context_decision.allowed
        record_basis = {
            "sequence": len(records) + 1,
            "open_time_ms": candle.open_time,
            "decision_time_ms": decision_time_ms,
            "previous_record_sha256": previous_head,
            "context_identity_sha256": binding.context_identity_sha256,
            "market_bar_sha256": {
                "ETHUSDC": _candle_digest(binding.context.ethusdc[index]),
                "BTCUSDC": _candle_digest(binding.context.btcusdc[index]),
                "ETHBTC": _candle_digest(binding.context.ethbtc[index]),
            },
            "context_decision": context_decision.to_dict(),
            "mode": mode,
            "entry_allowed": entry_allowed,
            "events": [_event_payload(event) for event in events],
            "closing_equity_usdc": (
                engine.equity_curve[-1].equity_usdc if engine.equity_curve else 0.0
            ),
            "realized_net_usdc": engine.realized_net_usdc,
            "open_lot_count": len(engine.open_lots),
            "pending_entry": engine.pending_entry is not None,
            "orders_created": 0,
            "private_api_calls": 0,
        }
        record = {**record_basis, "record_sha256": _digest(record_basis)}
        previous_head = record["record_sha256"]
        records.append(record)
        new_rows.append(record)
        last = candle.open_time

    ledger = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "records": records,
        "record_count": len(records),
        "head_sha256": previous_head,
    }
    basis = {
        key: value
        for key, value in root.items()
        if key != "state_sha256"
    }
    basis.update(
        {
            "engine_state": _engine_state_payload(engine),
            "forward_ledger": ledger,
            "last_processed_open_time_ms": last,
            "last_context_identity_sha256": binding.context_identity_sha256,
        }
    )
    next_state = validate_research_challenger_state(
        ResearchChallengerState(_canonical(basis), _digest(basis))
    )
    return ResearchChallengerAdvance(next_state, tuple(new_rows))


def validate_research_challenger_state(
    value: ResearchChallengerState | Mapping[str, Any],
) -> ResearchChallengerState:
    root = (
        value.to_dict()
        if isinstance(value, ResearchChallengerState)
        else dict(_mapping(value, "research_challenger_state"))
    )
    required = {
        "schema_version", "protocol_version", "contract_version",
        "task28_decision", "task28_report_sha256", "bundle_sha256",
        "pipeline_generation_id", "run_fingerprint_sha256", "code_commit",
        "start_snapshot_sha256", "exchange_info_snapshot_sha256",
        "cost_source_sha256", "strategy", "portfolio_policy", "started_at_utc",
        "valid_from_utc", "valid_until_utc", "mode", "engine_state",
        "forward_ledger", "last_processed_open_time_ms",
        "last_context_identity_sha256", "freshness", "diagnostic_only",
        "statistically_supported", "canonical_adoption_eligible",
        "protocol_v3_final_status", "orders_allowed", "paper_allowed",
        "testtrade_allowed", "live_allowed", "trading_api_allowed", "safety",
        "state_sha256",
    }
    if (
        set(root) != required
        or root["schema_version"] != STATE_SCHEMA_VERSION
        or root["protocol_version"] != PROTOCOL_VERSION
        or root["contract_version"] != CONTRACT_VERSION
    ):
        raise ResearchChallengerError("research-challenger state fields are invalid")
    task28_raw = dict(_mapping(root["task28_decision"], "task28_decision"))
    task28_sha = task28_raw.pop("report_sha256", None)
    task28 = validate_current_refit_decision(
        CurrentRefitDecision(_canonical(task28_raw), _sha(task28_sha, "task28_sha"))
    ).to_dict()
    _validate_task28_scope(task28)
    if (
        root["task28_report_sha256"] != task28["report_sha256"]
        or root["bundle_sha256"] != task28["frozen_candidate_bundle"]["bundle_sha256"]
        or root["pipeline_generation_id"] != task28["identity_manifest"]["current_pipeline_generation_id"]
        or root["run_fingerprint_sha256"] != task28["identity_manifest"]["current_run_fingerprint_sha256"]
        or root["code_commit"] != task28["identity_manifest"]["current_code_commit"]
        or root["start_snapshot_sha256"] != task28["identity_manifest"]["current_data_snapshot_sha256"]
        or root["exchange_info_snapshot_sha256"] != task28["identity_manifest"]["current_exchange_info_snapshot_sha256"]
        or root["cost_source_sha256"] != task28["identity_manifest"]["current_cost_source_sha256"]
    ):
        raise ResearchChallengerError("Task-28 provenance binding mismatch")
    strategy = _restore_strategy(root["strategy"])
    expected_strategy = _strategy_from_task28(task28)
    if _strategy_payload(strategy) != _strategy_payload(expected_strategy):
        raise ResearchChallengerError("research strategy differs from Task-28 bundle")
    policy = root["portfolio_policy"]
    if policy != PortfolioPolicy(100).to_dict() or policy["max_concurrent_lots"] != 1:
        raise ResearchChallengerError("research challenger must remain one fixed lot")
    started = _parse_utc(root["started_at_utc"], "started_at_utc")
    valid_from = _parse_utc(root["valid_from_utc"], "valid_from_utc")
    valid_until = _parse_utc(root["valid_until_utc"], "valid_until_utc")
    if not valid_from <= started < valid_until:
        raise ResearchChallengerError("research start lies outside Task-28 validity")
    bundle_validity = task28["frozen_candidate_bundle"]["validity"]
    if (
        root["valid_from_utc"] != bundle_validity["valid_from_utc"]
        or root["valid_until_utc"] != bundle_validity["valid_until_utc"]
    ):
        raise ResearchChallengerError("research validity differs from Task-28 bundle")
    expected_mode = "CASH" if strategy is None else "RESEARCH_CHALLENGER"
    if root["mode"] != expected_mode:
        raise ResearchChallengerError("research challenger mode is invalid")
    engine = _restore_engine_state(root["engine_state"])
    if len(engine.open_lots) > 1 or engine.reserved_lots > 1:
        raise ResearchChallengerError("research challenger exceeded one open lot")
    ledger = dict(_mapping(root["forward_ledger"], "forward_ledger"))
    _validate_ledger(ledger, engine, root["last_processed_open_time_ms"])
    if (
        root["freshness"] != "NOT_FRESH"
        or root["diagnostic_only"] is not True
        or root["statistically_supported"] is not False
        or root["canonical_adoption_eligible"] is not False
        or root["protocol_v3_final_status"] is not False
        or root["orders_allowed"] is not False
        or root["paper_allowed"] is not False
        or root["testtrade_allowed"] is not False
        or root["live_allowed"] is not False
        or root["trading_api_allowed"] is not False
        or root["safety"] != _SAFETY
    ):
        raise ResearchChallengerError("research-challenger safety lock failed")
    observed = _sha(root["state_sha256"], "state_sha256")
    basis = dict(root)
    basis.pop("state_sha256")
    if observed != _digest(basis):
        raise ResearchChallengerError("research-challenger state digest mismatch")
    return ResearchChallengerState(_canonical(basis), observed)


def _validate_task28_scope(task28: Mapping[str, Any]) -> None:
    if (
        task28.get("freshness") != "NOT_FRESH"
        or task28.get("diagnostic_only") is not True
        or task28.get("canonical_adoption_eligible") is not False
        or task28.get("manual_research_shadow_start_required") is not True
        or task28.get("manual_research_shadow_start_allowed") is not False
        or task28.get("sealed_final_holdout_used") is not False
        or task28.get("bot_start_allowed") is not False
    ):
        raise ResearchChallengerError("Task-28 scope is not research-only")


def _strategy_from_task28(task28: Mapping[str, Any]) -> StrategyCandidate | None:
    choice = task28["champion_challenger_cash_decision"]["choice"]
    bundle = task28["frozen_candidate_bundle"]
    if choice == CASH or bundle["research_simulation_routable"] is not True:
        return None
    candidate = bundle["specialist_bundle"]["base_candidate"]
    if not isinstance(candidate, Mapping):
        raise ResearchChallengerError("routable Task-28 bundle lacks a candidate")
    params = dict(candidate["params"])
    params.setdefault("symbol", "ETHUSDC")
    params.setdefault("side", "LONG")
    return StrategyCandidate(str(candidate["family"]), params)


def _validate_existing_prefix(root: Mapping[str, Any], binding: ContextParityBinding) -> None:
    records = root["forward_ledger"]["records"]
    if not records:
        return
    by_time = {
        candle.open_time: index
        for index, candle in enumerate(binding.context.ethusdc)
    }
    for record in records:
        index = by_time.get(record["open_time_ms"])
        if index is None:
            raise ResearchChallengerError(
                "forward binding does not contain the committed prefix"
            )
        expected = {
            "ETHUSDC": _candle_digest(binding.context.ethusdc[index]),
            "BTCUSDC": _candle_digest(binding.context.btcusdc[index]),
            "ETHBTC": _candle_digest(binding.context.ethbtc[index]),
        }
        if record["market_bar_sha256"] != expected:
            raise ResearchChallengerError(
                "forward market history changed after commitment"
            )


def _validate_ledger(
    ledger: Mapping[str, Any],
    engine: PortfolioEngineState,
    last_processed: Any,
) -> None:
    if set(ledger) != {"schema_version", "records", "record_count", "head_sha256"}:
        raise ResearchChallengerError("forward-ledger fields are invalid")
    if ledger["schema_version"] != LEDGER_SCHEMA_VERSION:
        raise ResearchChallengerError("forward-ledger schema is invalid")
    records = ledger["records"]
    if not isinstance(records, list) or ledger["record_count"] != len(records):
        raise ResearchChallengerError("forward-ledger count is invalid")
    previous = ZERO_HASH
    previous_time: int | None = None
    for sequence, raw in enumerate(records, start=1):
        record = dict(_mapping(raw, "forward_record"))
        observed = _sha(record.pop("record_sha256", None), "record_sha256")
        if record.get("sequence") != sequence or record.get("previous_record_sha256") != previous:
            raise ResearchChallengerError("forward-ledger chain is invalid")
        open_time = record.get("open_time_ms")
        if type(open_time) is not int or open_time % EXPECTED_STEP_MS:
            raise ResearchChallengerError("forward-ledger timestamp is invalid")
        if previous_time is not None and open_time != previous_time + EXPECTED_STEP_MS:
            raise ResearchChallengerError("forward-ledger has a gap or duplicate")
        if record.get("orders_created") != 0 or record.get("private_api_calls") != 0:
            raise ResearchChallengerError("forward-ledger contains forbidden side effects")
        if record.get("open_lot_count") not in (0, 1):
            raise ResearchChallengerError("forward-ledger open lot count is invalid")
        if observed != _digest(record):
            raise ResearchChallengerError("forward-ledger record digest mismatch")
        previous = observed
        previous_time = open_time
    if ledger["head_sha256"] != previous:
        raise ResearchChallengerError("forward-ledger head mismatch")
    expected_last = records[-1]["open_time_ms"] if records else None
    if last_processed != expected_last:
        raise ResearchChallengerError("last processed timestamp differs from ledger")
    if len(engine.candles) != len(records) and engine.candles:
        raise ResearchChallengerError("engine history and forward ledger differ")


def _engine_state_payload(state: PortfolioEngineState) -> dict[str, Any]:
    return {
        "candles": [asdict(item) for item in state.candles],
        "open_lots": [asdict(item) for item in state.open_lots],
        "pending_entry": None if state.pending_entry is None else asdict(state.pending_entry),
        "cooldown_until_index": state.cooldown_until_index,
        "realized_net_usdc": state.realized_net_usdc,
        "trades": [asdict(item) for item in state.trades],
        "capacity_rejections": [asdict(item) for item in state.capacity_rejections],
        "equity_curve": [asdict(item) for item in state.equity_curve],
        "next_lot_sequence": state.next_lot_sequence,
        "max_concurrent_lots": state.max_concurrent_lots,
        "max_open_entry_exposure_usdc": state.max_open_entry_exposure_usdc,
        "max_reserved_notional_usdc": state.max_reserved_notional_usdc,
    }


def _restore_engine_state(value: Any) -> PortfolioEngineState:
    root = dict(_mapping(value, "engine_state"))
    required = {
        "candles", "open_lots", "pending_entry", "cooldown_until_index",
        "realized_net_usdc", "trades", "capacity_rejections", "equity_curve",
        "next_lot_sequence", "max_concurrent_lots",
        "max_open_entry_exposure_usdc", "max_reserved_notional_usdc",
    }
    if set(root) != required:
        raise ResearchChallengerError("engine-state fields are invalid")
    try:
        state = PortfolioEngineState(
            candles=tuple(Candle(**item) for item in root["candles"]),
            open_lots=tuple(PortfolioLot(**item) for item in root["open_lots"]),
            pending_entry=(
                None
                if root["pending_entry"] is None
                else PendingPortfolioEntry(**root["pending_entry"])
            ),
            cooldown_until_index=root["cooldown_until_index"],
            realized_net_usdc=root["realized_net_usdc"],
            trades=tuple(PortfolioTrade(**item) for item in root["trades"]),
            capacity_rejections=tuple(
                CapacityRejection(**item) for item in root["capacity_rejections"]
            ),
            equity_curve=tuple(EquityPoint(**item) for item in root["equity_curve"]),
            next_lot_sequence=root["next_lot_sequence"],
            max_concurrent_lots=root["max_concurrent_lots"],
            max_open_entry_exposure_usdc=root["max_open_entry_exposure_usdc"],
            max_reserved_notional_usdc=root["max_reserved_notional_usdc"],
        )
    except (TypeError, ValueError) as exc:
        raise ResearchChallengerError("engine-state payload is invalid") from exc
    if len(state.open_lots) > 1 or state.reserved_lots > 1:
        raise ResearchChallengerError("engine state exceeds one lot")
    return state


def _event_payload(event: PortfolioStepEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "candle_open_time_ms": event.candle_open_time_ms,
        "lot_id": event.lot_id,
        "trade": None if event.trade is None else asdict(event.trade),
        "rejection": None if event.rejection is None else asdict(event.rejection),
    }


def _strategy_payload(strategy: StrategyCandidate | None) -> dict[str, Any] | None:
    if strategy is None:
        return None
    return {"family": strategy.family, "params": dict(strategy.params)}


def _restore_strategy(value: Any) -> StrategyCandidate | None:
    if value is None:
        return None
    root = dict(_mapping(value, "strategy"))
    if set(root) != {"family", "params"} or not isinstance(root["params"], Mapping):
        raise ResearchChallengerError("strategy payload is invalid")
    strategy = StrategyCandidate(str(root["family"]), dict(root["params"]))
    if strategy.params.get("symbol") != "ETHUSDC" or strategy.params.get("side") != "LONG":
        raise ResearchChallengerError("research challenger is ETHUSDC LONG-only")
    return strategy


def _candle_digest(candle: Candle) -> str:
    return _digest(asdict(candle))


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchChallengerError(f"{name} must be an object")
    return value


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ResearchChallengerError(f"{name} must be UTC")
    return value.astimezone(UTC)


def _parse_utc(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ResearchChallengerError(f"{name} must be canonical UTC text")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ResearchChallengerError(f"{name} must be canonical UTC text") from exc
    if _utc_text(parsed) != value:
        raise ResearchChallengerError(f"{name} must be canonical UTC text")
    return parsed


def _utc_text(value: datetime) -> str:
    return _utc(value, "timestamp").isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ResearchChallengerError(f"{name} must be lowercase sha256")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


__all__ = [
    "CONTRACT_PATH", "CONTRACT_SCHEMA_VERSION", "CONTRACT_VERSION",
    "LEDGER_SCHEMA_VERSION", "STATE_SCHEMA_VERSION",
    "ResearchChallengerAdvance", "ResearchChallengerError",
    "ResearchChallengerState", "advance_research_challenger",
    "load_research_challenger_contract", "start_research_challenger",
    "validate_research_challenger_state",
]
