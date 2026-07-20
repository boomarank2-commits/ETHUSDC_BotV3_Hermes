"""Task-29 order-free research-challenger controller and forward ledger.

The controller consumes a validated Task-28 decision, exact three-market closed
bars, and the existing Task-8 execution core through its incremental adapter. It
has no exchange client, account reader, order adapter, paper, testtrade, live, or
adoption entry point.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any, Final

from ethusdc_bot.backtest.context_features import ContextVetoPolicy
from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS
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
from ethusdc_bot.protocol_v3.intrabar_runtime import (
    IntrabarRuntimeEvent,
    IntrabarRuntimeState,
    advance_intrabar_runtime,
    intrabar_runtime_state_payload,
    new_intrabar_runtime_state,
    restore_intrabar_runtime_state,
)
from ethusdc_bot.protocol_v3.pipeline import (
    PipelineGeneration,
    validate_pipeline_generation,
)
from ethusdc_bot.protocol_v3.run_identity import (
    FrozenExchangeInfoSnapshot,
    validate_exchange_info_snapshot,
)
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy

PROTOCOL_VERSION: Final = "3.0.0"
CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_research_challenger_contract.json"
)
CONTRACT_SCHEMA_VERSION: Final = "protocol_v3_research_challenger_contract_v2"
CONTRACT_VERSION: Final = "protocol_v3_order_free_research_challenger_shadow_v2"
STATE_SCHEMA_VERSION: Final = "protocol_v3_research_challenger_state_v2"
LEDGER_SCHEMA_VERSION: Final = "protocol_v3_research_challenger_forward_ledger_v2"
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
        "current_pipeline_generation_required": True,
        "manual_start_only": True,
        "manual_start_is_first_forward_minute": True,
        "ethusdc_only": True,
        "btcusdc_and_ethbtc_context_only": True,
        "exact_closed_three_market_bar_required": True,
        "frozen_context_policy_required": True,
        "public_exchange_info_snapshot_required_for_active_candidate": True,
        "frozen_horizon_policy_required": True,
        "one_open_lot_maximum": True,
        "refresh_and_replay_must_be_idempotent": True,
        "end_of_feed_may_not_liquidate": True,
    },
    "warmup_policy": {
        "trailing_feature_reads_only": True,
        "signals_forbidden": True,
        "fills_forbidden": True,
        "pnl_forbidden": True,
        "ledger_records_forbidden": True,
        "minimum_minutes_from_strategy_and_context_lookbacks": True,
    },
    "forward_ledger_policy": {
        "append_only_hash_chain": True,
        "pipeline_namespace_bound": True,
        "new_pipeline_generation_requires_empty_ledger": True,
        "explicit_no_trade_records": True,
        "bar_content_hashes_required": True,
        "context_decision_required": True,
        "virtual_fills_fees_slippage_positions_and_mtm": True,
        "raw_orders_forbidden": True,
    },
    "validity_policy": {
        "entries_before_valid_from_forbidden": True,
        "entries_before_manual_activation_forbidden": True,
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
    current_pipeline_generation: PipelineGeneration,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any] | None = None,
) -> ResearchChallengerState:
    """Create an empty manual research state without activating another mode."""

    if not isinstance(task28_decision, CurrentRefitDecision):
        raise ResearchChallengerError(
            "typed validated Task-28 provenance is required"
        )
    task28 = validate_current_refit_decision(task28_decision).to_dict()
    _validate_task28_scope(task28)
    generation = _validate_current_generation(task28, current_pipeline_generation)
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
    horizon = _horizon_from_task28(task28)
    context_policy = _context_policy_from_task28(task28, required=strategy is not None)
    exchange_payload = _exchange_payload(
        exchange_info_snapshot,
        expected_sha=task28["identity_manifest"][
            "current_exchange_info_snapshot_sha256"
        ],
        required=strategy is not None,
    )
    activation_open_time_ms = _ceil_minute_ms(started)
    warmup_minutes = _required_warmup_minutes(strategy, context_policy)
    warmup_start_open_time_ms = activation_open_time_ms - (
        warmup_minutes * EXPECTED_STEP_MS
    )
    run_fingerprint = _run_fingerprint(task28)
    basis = {
        "schema_version": STATE_SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": CONTRACT_VERSION,
        "task28_decision": task28,
        "task28_report_sha256": task28["report_sha256"],
        "bundle_sha256": bundle["bundle_sha256"],
        "pipeline_generation_id": generation.generation_id,
        "forward_ledger_namespace": generation.forward_ledger_namespace,
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
        "exchange_info_snapshot": exchange_payload,
        "horizon_policy": _horizon_payload(horizon),
        "context_policy": None if context_policy is None else context_policy.to_dict(),
        "strategy": _strategy_payload(strategy),
        "portfolio_policy": PortfolioPolicy(100).to_dict(),
        "started_at_utc": _utc_text(started),
        "activation_open_time_ms": activation_open_time_ms,
        "warmup_start_open_time_ms": warmup_start_open_time_ms,
        "warmup_minutes": warmup_minutes,
        "valid_from_utc": _utc_text(valid_from),
        "valid_until_utc": _utc_text(valid_until),
        "mode": "CASH" if strategy is None else "RESEARCH_CHALLENGER",
        "engine_state": intrabar_runtime_state_payload(
            new_intrabar_runtime_state()
        ),
        "forward_ledger": {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "namespace": generation.forward_ledger_namespace,
            "records": [],
            "record_count": 0,
            "head_sha256": ZERO_HASH,
        },
        "last_engine_open_time_ms": None,
        "last_processed_open_time_ms": None,
        "last_context_identity_sha256": None,
        "run_fingerprint_pipeline_namespace": run_fingerprint["pipeline"][
            "forward_ledger_namespace"
        ],
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


def assert_research_challenger_pipeline(
    state: ResearchChallengerState,
    current_pipeline_generation: PipelineGeneration,
) -> None:
    """Block resume across a changed family/feature/controller generation."""

    root = validate_research_challenger_state(state).to_dict()
    validate_pipeline_generation(current_pipeline_generation)
    generation = current_pipeline_generation
    if (
        root["pipeline_generation_id"] != generation.generation_id
        or root["forward_ledger_namespace"] != generation.forward_ledger_namespace
    ):
        raise ResearchChallengerError(
            "new pipeline generation requires a new empty research-challenger ledger"
        )


def advance_research_challenger(
    state: ResearchChallengerState,
    binding: ContextParityBinding,
    *,
    observed_at_utc: datetime,
    current_pipeline_generation: PipelineGeneration,
) -> ResearchChallengerAdvance:
    """Append every newly closed aligned minute exactly once and without orders."""

    validated = validate_research_challenger_state(state)
    assert_research_challenger_pipeline(validated, current_pipeline_generation)
    root = validated.to_dict()
    validate_context_parity_binding(binding)
    _validate_binding_policy(root, binding)
    observed = _utc(observed_at_utc, "observed_at_utc")
    expected_observed = datetime.fromtimestamp(
        (binding.common_watermark_open_time_ms + EXPECTED_STEP_MS - 1) / 1000,
        tz=UTC,
    )
    if observed != expected_observed:
        raise ResearchChallengerError(
            "forward binding must end at the exact currently closed watermark"
        )
    _validate_existing_history(root, binding)
    strategy = _restore_strategy(root["strategy"])
    engine = restore_intrabar_runtime_state(root["engine_state"])
    exchange = root["exchange_info_snapshot"]
    horizon = _restore_horizon(root["horizon_policy"])
    records = list(root["forward_ledger"]["records"])
    previous_head = root["forward_ledger"]["head_sha256"]
    activation_ms = root["activation_open_time_ms"]
    warmup_start_ms = root["warmup_start_open_time_ms"]
    valid_from_ms = int(
        _parse_utc(root["valid_from_utc"], "valid_from").timestamp() * 1000
    )
    valid_until_ms = int(
        _parse_utc(root["valid_until_utc"], "valid_until").timestamp() * 1000
    )
    last_engine = root["last_engine_open_time_ms"]
    last_forward = root["last_processed_open_time_ms"]
    new_rows: list[dict[str, Any]] = []

    if strategy is not None and last_engine is None:
        if binding.context.ethusdc[0].open_time > warmup_start_ms:
            raise ResearchChallengerError(
                "initial forward binding is missing the required causal warmup"
            )

    for index, candle in enumerate(binding.context.ethusdc):
        minimum = warmup_start_ms if strategy is not None else activation_ms
        if candle.open_time < minimum:
            continue
        if last_engine is not None and strategy is not None and candle.open_time <= last_engine:
            continue
        if strategy is None and last_forward is not None and candle.open_time <= last_forward:
            continue
        expected_previous = last_engine if strategy is not None else last_forward
        if expected_previous is not None and candle.open_time != expected_previous + EXPECTED_STEP_MS:
            raise ResearchChallengerError(
                "research-challenger minutes must be contiguous"
            )
        decision_time_ms = candle.open_time + EXPECTED_STEP_MS - 1
        context_decision = evaluate_closed_bar_context(
            binding, index, decision_time_ms=decision_time_ms
        )
        is_forward = candle.open_time >= activation_ms
        entry_window = (
            strategy is not None
            and is_forward
            and candle.open_time >= valid_from_ms
            and candle.open_time < valid_until_ms
        )
        events: tuple[IntrabarRuntimeEvent, ...] = ()
        if strategy is not None:
            if exchange is None:
                raise ResearchChallengerError(
                    "active research challenger lost its exchange-info snapshot"
                )
            engine, events = advance_intrabar_runtime(
                engine,
                candle,
                strategy,
                exchange_info_snapshot=exchange,
                horizon_policy=horizon,
                context_decision=context_decision,
                entry_allowed=entry_window,
            )
            last_engine = candle.open_time
        if not is_forward:
            if events:
                raise ResearchChallengerError(
                    "warmup produced a signal, fill, exit, or other runtime event"
                )
            if engine.position is not None or engine.pending_entry:
                raise ResearchChallengerError(
                    "warmup may not create positions or pending entries"
                )
            if engine.realized_net_usdc != 0:
                raise ResearchChallengerError("warmup may not create PnL")
            continue

        mode = (
            "CASH"
            if strategy is None
            else "ACTIVE"
            if entry_window
            else "EXIT_ONLY"
        )
        entry_allowed = (
            strategy is not None and entry_window and context_decision.allowed
        )
        record_basis = {
            "sequence": len(records) + 1,
            "open_time_ms": candle.open_time,
            "decision_time_ms": decision_time_ms,
            "previous_record_sha256": previous_head,
            "pipeline_generation_id": root["pipeline_generation_id"],
            "forward_ledger_namespace": root["forward_ledger_namespace"],
            "context_identity_sha256": binding.context_identity_sha256,
            "market_bar_sha256": {
                "ETHUSDC": _candle_digest(binding.context.ethusdc[index]),
                "BTCUSDC": _candle_digest(binding.context.btcusdc[index]),
                "ETHBTC": _candle_digest(binding.context.ethbtc[index]),
            },
            "context_decision": context_decision.to_dict(),
            "mode": mode,
            "entry_window_open": entry_window,
            "entry_allowed": entry_allowed,
            "events": [_event_payload(event) for event in events],
            "closing_equity_usdc": (
                engine.closing_equity_usdc if strategy is not None else 0.0
            ),
            "realized_net_usdc": (
                float(engine.realized_net_usdc) if strategy is not None else 0.0
            ),
            "open_lot_count": engine.open_lot_count if strategy is not None else 0,
            "pending_entry": engine.pending_entry if strategy is not None else False,
            "orders_created": 0,
            "private_api_calls": 0,
        }
        record = {**record_basis, "record_sha256": _digest(record_basis)}
        previous_head = record["record_sha256"]
        records.append(record)
        new_rows.append(record)
        last_forward = candle.open_time

    ledger = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "namespace": root["forward_ledger_namespace"],
        "records": records,
        "record_count": len(records),
        "head_sha256": previous_head,
    }
    basis = {key: value for key, value in root.items() if key != "state_sha256"}
    basis.update(
        {
            "engine_state": intrabar_runtime_state_payload(engine),
            "forward_ledger": ledger,
            "last_engine_open_time_ms": last_engine,
            "last_processed_open_time_ms": last_forward,
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
        "pipeline_generation_id", "forward_ledger_namespace",
        "run_fingerprint_sha256", "code_commit", "start_snapshot_sha256",
        "exchange_info_snapshot_sha256", "cost_source_sha256",
        "exchange_info_snapshot", "horizon_policy", "context_policy",
        "strategy", "portfolio_policy", "started_at_utc",
        "activation_open_time_ms", "warmup_start_open_time_ms", "warmup_minutes",
        "valid_from_utc", "valid_until_utc", "mode", "engine_state",
        "forward_ledger", "last_engine_open_time_ms",
        "last_processed_open_time_ms", "last_context_identity_sha256",
        "run_fingerprint_pipeline_namespace", "freshness", "diagnostic_only",
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
    manifest = task28["identity_manifest"]
    run = _run_fingerprint(task28)
    if (
        root["task28_report_sha256"] != task28["report_sha256"]
        or root["bundle_sha256"] != task28["frozen_candidate_bundle"]["bundle_sha256"]
        or root["pipeline_generation_id"] != manifest["current_pipeline_generation_id"]
        or root["run_fingerprint_sha256"] != manifest["current_run_fingerprint_sha256"]
        or root["code_commit"] != manifest["current_code_commit"]
        or root["start_snapshot_sha256"] != manifest["current_data_snapshot_sha256"]
        or root["exchange_info_snapshot_sha256"] != manifest["current_exchange_info_snapshot_sha256"]
        or root["cost_source_sha256"] != manifest["current_cost_source_sha256"]
        or root["forward_ledger_namespace"] != run["pipeline"]["forward_ledger_namespace"]
        or root["run_fingerprint_pipeline_namespace"] != root["forward_ledger_namespace"]
    ):
        raise ResearchChallengerError("Task-28 provenance binding mismatch")
    strategy = _restore_strategy(root["strategy"])
    expected_strategy = _strategy_from_task28(task28)
    if _strategy_payload(strategy) != _strategy_payload(expected_strategy):
        raise ResearchChallengerError("research strategy differs from Task-28 bundle")
    policy = root["portfolio_policy"]
    if policy != PortfolioPolicy(100).to_dict() or policy["max_concurrent_lots"] != 1:
        raise ResearchChallengerError("research challenger must remain one fixed lot")
    horizon = _restore_horizon(root["horizon_policy"])
    if _horizon_payload(horizon) != _horizon_payload(_horizon_from_task28(task28)):
        raise ResearchChallengerError("research horizon differs from Task-28")
    expected_context = _context_policy_from_task28(task28, required=strategy is not None)
    expected_context_payload = None if expected_context is None else expected_context.to_dict()
    if root["context_policy"] != expected_context_payload:
        raise ResearchChallengerError("research context policy differs from Task-28")
    _exchange_payload(
        root["exchange_info_snapshot"],
        expected_sha=root["exchange_info_snapshot_sha256"],
        required=strategy is not None,
    )
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
    activation = _ceil_minute_ms(started)
    warmup = _required_warmup_minutes(strategy, expected_context)
    if (
        root["activation_open_time_ms"] != activation
        or root["warmup_minutes"] != warmup
        or root["warmup_start_open_time_ms"] != activation - warmup * EXPECTED_STEP_MS
    ):
        raise ResearchChallengerError("research manual-start or warmup boundary is invalid")
    expected_mode = "CASH" if strategy is None else "RESEARCH_CHALLENGER"
    if root["mode"] != expected_mode:
        raise ResearchChallengerError("research challenger mode is invalid")
    engine = restore_intrabar_runtime_state(root["engine_state"])
    if engine.open_lot_count > 1 or (engine.open_lot_count + int(engine.pending_entry)) > 1:
        raise ResearchChallengerError("research challenger exceeded one open lot")
    _validate_engine_boundaries(root, engine, strategy)
    ledger = dict(_mapping(root["forward_ledger"], "forward_ledger"))
    _validate_ledger(ledger, root, engine, strategy)
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


def _validate_current_generation(
    task28: Mapping[str, Any], generation: PipelineGeneration
) -> PipelineGeneration:
    validate_pipeline_generation(generation)
    current = generation
    expected = task28["identity_manifest"]["current_pipeline_generation_id"]
    run = _run_fingerprint(task28)
    if (
        current.generation_id != expected
        or current.forward_ledger_namespace
        != run["pipeline"]["forward_ledger_namespace"]
    ):
        raise ResearchChallengerError(
            "Task-28 decision belongs to another pipeline generation"
        )
    return current


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


def _run_fingerprint(task28: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(
        task28["current_origin"]["selection_decision"]["frozen_pipeline_config"][
            "run_fingerprint"
        ],
        "Task-28 run_fingerprint",
    )


def _horizon_from_task28(task28: Mapping[str, Any]) -> HorizonPolicy:
    fold = _mapping(
        task28["current_origin"]["selection_decision"]["frozen_pipeline_config"][
            "fold_identity"
        ],
        "Task-28 fold_identity",
    )
    plan = _mapping(fold.get("plan"), "Task-28 fold plan")
    payload = _mapping(plan.get("horizon_policy"), "Task-28 horizon policy")
    try:
        return HorizonPolicy(
            max_label_horizon_minutes=int(payload["max_label_horizon_minutes"]),
            max_holding_period_minutes=int(payload["max_holding_period_minutes"]),
            pending_entry_latency_minutes=int(payload["pending_entry_latency_minutes"]),
            execution_bar_minutes=int(payload["execution_bar_minutes"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchChallengerError("Task-28 horizon policy is invalid") from exc


def _horizon_payload(policy: HorizonPolicy) -> dict[str, Any]:
    return {**policy.basis(), "policy_sha256": policy.policy_sha256}


def _restore_horizon(value: Any) -> HorizonPolicy:
    root = dict(_mapping(value, "horizon_policy"))
    if set(root) != {
        "contract_version", "max_label_horizon_minutes",
        "max_holding_period_minutes", "pending_entry_latency_minutes",
        "execution_bar_minutes", "policy_sha256",
    }:
        raise ResearchChallengerError("horizon-policy fields are invalid")
    try:
        policy = HorizonPolicy(
            max_label_horizon_minutes=root["max_label_horizon_minutes"],
            max_holding_period_minutes=root["max_holding_period_minutes"],
            pending_entry_latency_minutes=root["pending_entry_latency_minutes"],
            execution_bar_minutes=root["execution_bar_minutes"],
        )
    except (TypeError, ValueError) as exc:
        raise ResearchChallengerError("horizon policy is invalid") from exc
    if _horizon_payload(policy) != root:
        raise ResearchChallengerError("horizon policy is not canonical")
    return policy


def _context_policy_from_task28(
    task28: Mapping[str, Any], *, required: bool
) -> ContextVetoPolicy | None:
    context = task28["frozen_candidate_bundle"].get("context_policy")
    if not isinstance(context, Mapping):
        if required:
            raise ResearchChallengerError("Task-28 context policy is missing")
        return None
    payload = context.get("policy")
    if not isinstance(payload, Mapping):
        if required:
            raise ResearchChallengerError("Task-28 context policy payload is missing")
        return None
    values = dict(payload)
    values.pop("policy_version", None)
    try:
        policy = ContextVetoPolicy(**values)
    except (TypeError, ValueError) as exc:
        raise ResearchChallengerError("Task-28 context policy is invalid") from exc
    if policy.to_dict() != dict(payload):
        raise ResearchChallengerError("Task-28 context policy is not canonical")
    return policy


def _exchange_payload(
    value: FrozenExchangeInfoSnapshot | Mapping[str, Any] | None,
    *,
    expected_sha: str,
    required: bool,
) -> dict[str, Any] | None:
    if value is None:
        if required:
            raise ResearchChallengerError(
                "active challenger requires its public Exchange-Info snapshot"
            )
        return None
    validate_exchange_info_snapshot(value)
    payload = value.to_dict() if isinstance(value, FrozenExchangeInfoSnapshot) else dict(value)
    if payload.get("snapshot_sha256") != expected_sha:
        raise ResearchChallengerError(
            "Exchange-Info snapshot differs from Task-28 provenance"
        )
    return payload


def _required_warmup_minutes(
    strategy: StrategyCandidate | None,
    context_policy: ContextVetoPolicy | None,
) -> int:
    if strategy is None:
        return 0
    params = strategy.params
    lookbacks = [
        int(params.get("lookback", 5) or 5),
        int(params.get("trend_lookback", params.get("lookback", 5)) or 5),
        int(params.get("volatility_lookback", params.get("lookback", 5)) or 5),
    ]
    if context_policy is not None:
        lookbacks.append(context_policy.warmup_candles)
    if any(value < 1 for value in lookbacks):
        raise ResearchChallengerError("strategy warmup lookbacks must be positive")
    return max(lookbacks)


def _validate_binding_policy(
    root: Mapping[str, Any], binding: ContextParityBinding
) -> None:
    expected = root.get("context_policy")
    if expected is not None and binding.policy.to_dict() != expected:
        raise ResearchChallengerError(
            "forward context policy differs from the frozen Task-28 policy"
        )


def _validate_existing_history(
    root: Mapping[str, Any], binding: ContextParityBinding
) -> None:
    by_time = {
        candle.open_time: index
        for index, candle in enumerate(binding.context.ethusdc)
    }
    engine = restore_intrabar_runtime_state(root["engine_state"])
    for candle in engine.candles:
        index = by_time.get(candle.open_time)
        if index is None:
            raise ResearchChallengerError(
                "forward binding does not contain the committed engine history"
            )
        expected = _candle_digest(binding.context.ethusdc[index])
        if _candle_digest(candle) != expected:
            raise ResearchChallengerError(
                "ETHUSDC engine history changed after commitment"
            )
    for record in root["forward_ledger"]["records"]:
        index = by_time.get(record["open_time_ms"])
        if index is None:
            raise ResearchChallengerError(
                "forward binding does not contain the committed ledger prefix"
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


def _validate_engine_boundaries(
    root: Mapping[str, Any],
    engine: IntrabarRuntimeState,
    strategy: StrategyCandidate | None,
) -> None:
    last_engine = root["last_engine_open_time_ms"]
    if strategy is None:
        if engine.candles or last_engine is not None:
            raise ResearchChallengerError("CASH mode may not contain engine history")
        return
    expected_last = engine.candles[-1].open_time if engine.candles else None
    if last_engine != expected_last:
        raise ResearchChallengerError("last engine timestamp differs from engine state")
    if engine.candles:
        if engine.candles[0].open_time != root["warmup_start_open_time_ms"]:
            raise ResearchChallengerError("engine history does not start at warmup")
        if expected_last is not None and expected_last < root["activation_open_time_ms"]:
            if engine.position is not None or engine.pending_entry or engine.realized_net_usdc != 0:
                raise ResearchChallengerError("warmup engine state contains trading effects")


def _validate_ledger(
    ledger: Mapping[str, Any],
    root: Mapping[str, Any],
    engine: IntrabarRuntimeState,
    strategy: StrategyCandidate | None,
) -> None:
    if set(ledger) != {
        "schema_version", "namespace", "records", "record_count", "head_sha256"
    }:
        raise ResearchChallengerError("forward-ledger fields are invalid")
    if (
        ledger["schema_version"] != LEDGER_SCHEMA_VERSION
        or ledger["namespace"] != root["forward_ledger_namespace"]
    ):
        raise ResearchChallengerError("forward-ledger identity is invalid")
    records = ledger["records"]
    if not isinstance(records, list) or ledger["record_count"] != len(records):
        raise ResearchChallengerError("forward-ledger count is invalid")
    previous = ZERO_HASH
    previous_time: int | None = None
    valid_from_ms = int(_parse_utc(root["valid_from_utc"], "valid_from").timestamp() * 1000)
    valid_until_ms = int(_parse_utc(root["valid_until_utc"], "valid_until").timestamp() * 1000)
    for sequence, raw in enumerate(records, start=1):
        record = dict(_mapping(raw, "forward_record"))
        observed = _sha(record.pop("record_sha256", None), "record_sha256")
        if record.get("sequence") != sequence or record.get("previous_record_sha256") != previous:
            raise ResearchChallengerError("forward-ledger chain is invalid")
        open_time = record.get("open_time_ms")
        if type(open_time) is not int or open_time % EXPECTED_STEP_MS:
            raise ResearchChallengerError("forward-ledger timestamp is invalid")
        if open_time < root["activation_open_time_ms"]:
            raise ResearchChallengerError("forward ledger predates manual activation")
        if previous_time is not None and open_time != previous_time + EXPECTED_STEP_MS:
            raise ResearchChallengerError("forward-ledger has a gap or duplicate")
        if (
            record.get("pipeline_generation_id") != root["pipeline_generation_id"]
            or record.get("forward_ledger_namespace") != root["forward_ledger_namespace"]
        ):
            raise ResearchChallengerError("forward record pipeline identity is invalid")
        if record.get("orders_created") != 0 or record.get("private_api_calls") != 0:
            raise ResearchChallengerError("forward-ledger contains forbidden side effects")
        if record.get("open_lot_count") not in (0, 1):
            raise ResearchChallengerError("forward-ledger open lot count is invalid")
        expected_window = strategy is not None and valid_from_ms <= open_time < valid_until_ms
        if record.get("entry_window_open") is not expected_window:
            raise ResearchChallengerError("forward record entry-window flag is invalid")
        context = _mapping(record.get("context_decision"), "context_decision")
        expected_allowed = expected_window and context.get("allowed") is True
        if record.get("entry_allowed") is not expected_allowed:
            raise ResearchChallengerError("forward record entry permission is invalid")
        if observed != _digest(record):
            raise ResearchChallengerError("forward-ledger record digest mismatch")
        previous = observed
        previous_time = open_time
    if ledger["head_sha256"] != previous:
        raise ResearchChallengerError("forward-ledger head mismatch")
    expected_last = records[-1]["open_time_ms"] if records else None
    if root["last_processed_open_time_ms"] != expected_last:
        raise ResearchChallengerError("last processed timestamp differs from ledger")
    if records and records[0]["open_time_ms"] != root["activation_open_time_ms"]:
        raise ResearchChallengerError("forward ledger did not begin at manual activation")
    if strategy is not None and records:
        last = records[-1]
        if last["closing_equity_usdc"] != engine.closing_equity_usdc:
            raise ResearchChallengerError("ledger and engine equity differ")
        if last["realized_net_usdc"] != float(engine.realized_net_usdc):
            raise ResearchChallengerError("ledger and engine realized PnL differ")
        if last["open_lot_count"] != engine.open_lot_count:
            raise ResearchChallengerError("ledger and engine position count differ")
        if last["pending_entry"] is not engine.pending_entry:
            raise ResearchChallengerError("ledger and engine pending state differ")


def _event_payload(event: IntrabarRuntimeEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "candle_open_time_ms": event.candle_open_time_ms,
        "trade": None if event.trade is None else asdict(event.trade),
        "reason": event.reason,
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


def _ceil_minute_ms(value: datetime) -> int:
    raw = int(_utc(value, "started_at_utc").timestamp() * 1000)
    return ((raw + EXPECTED_STEP_MS - 1) // EXPECTED_STEP_MS) * EXPECTED_STEP_MS


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
    "assert_research_challenger_pipeline", "load_research_challenger_contract",
    "start_research_challenger", "validate_research_challenger_state",
]
