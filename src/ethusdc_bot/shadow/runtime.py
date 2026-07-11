"""Durable, order-free Shadow runtime over closed public ETHUSDC candles.

``events.jsonl`` is the source of truth.  The mutable ``state.json`` file is a
strict, atomically replaced projection that may be repaired by the explicit
``ShadowRuntime.open`` operation only when it exactly matches an earlier event
prefix.  This makes the event-fsync/snapshot-replace crash window recoverable
without accepting an arbitrary or modified snapshot.

The runtime deliberately composes only the immutable adoption receipt, the
pure Shadow reducer, the append-only store, and the public kline poller.  It has
no account, credential, balance, exchange-order, paper-order, or test-order
integration.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Iterator

from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS
from ethusdc_bot.backtest.portfolio_simulator import PortfolioTrade
from ethusdc_bot.shadow.engine import (
    ShadowReplayResult,
    ShadowReplayState,
    initialize_shadow_replay,
    replay_closed_candles,
    start_shadow_replay,
    stop_shadow_replay,
)
from ethusdc_bot.shadow.public_feed import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    PublicKlineContinuityError,
    PublicKlineNetworkError,
    PublicKlineValidationError,
    run_public_kline_poller,
)
from ethusdc_bot.shadow.schema import shadow_safety_status, validate_shadow_state
from ethusdc_bot.shadow.store import (
    ShadowIntegrityError,
    append_event_at_expected_head,
    canonical_json_bytes,
    iter_verified_events,
    load_deployment,
    load_shadow_state,
    utc_now,
    verify_event_log,
    write_state_atomic,
)
from ethusdc_bot.shadow.timeline import first_shadow_candle_open_time_ms


DEPLOYMENT_FILE = "deployment.json"
STATE_FILE = "state.json"
EVENTS_FILE = "events.jsonl"
WRITER_LOCK_FILE = ".writer.lock"
FULL_CHAIN_VERIFY_INTERVAL = 1_440

_CANDLE_KEYS = {"open_time_ms", "open", "high", "low", "close", "volume"}
_ADOPTION_EVENT_KEYS = {
    "deployment_id",
    "final_evaluation_id",
    "source_report_sha256",
    "candidate_id",
    "candidate_signature",
    "assessment_color",
    "deployment_budget_usdc",
    "lot_notional_usdc",
    "orders_enabled",
    "trading_api_enabled",
    "api_keys_used",
}


class ShadowRuntimeError(RuntimeError):
    """Base class for durable Shadow runtime failures."""


class ShadowRuntimeIntegrityError(ShadowRuntimeError):
    """Raised when deployment, report, events, or snapshot do not agree."""


class ShadowRuntimeStateError(ShadowRuntimeError):
    """Raised when a lifecycle operation is unsafe in the current phase."""


@dataclass(frozen=True)
class ShadowProcessResult:
    """Summary of one durable closed-candle reduction request."""

    processed_candles: int
    ignored_idempotent_candles: int
    events_appended: int
    trades_emitted: tuple[PortfolioTrade, ...]
    phase: str
    state_digest: str


@dataclass(frozen=True)
class _RebuiltRuntime:
    replay_state: ShadowReplayState
    current_snapshot: dict[str, Any]
    claimed_prefix_snapshot: dict[str, Any] | None
    event_count: int


class ShadowRuntime:
    """Single-writer durable runtime for an adopted Shadow deployment."""

    def __init__(
        self,
        *,
        deployment_dir: Path,
        deployment: dict[str, Any],
        replay_state: ShadowReplayState,
        state: dict[str, Any],
        recovered_snapshot: bool,
    ) -> None:
        self.deployment_dir = deployment_dir
        self.deployment_path = deployment_dir / DEPLOYMENT_FILE
        self.state_path = deployment_dir / STATE_FILE
        self.events_path = deployment_dir / EVENTS_FILE
        self.deployment = deepcopy(deployment)
        self._replay_state = replay_state
        self._state = deepcopy(state)
        self.recovered_snapshot = recovered_snapshot
        self._deployment_digest = sha256(canonical_json_bytes(deployment)).hexdigest()

    @classmethod
    def open(cls, deployment_dir: str | Path) -> "ShadowRuntime":
        """Open, fully replay, and if provably safe repair one deployment.

        A stale snapshot is repaired only when it is byte-semantically equal to
        the deterministic projection of a strict earlier event prefix.  A
        malformed snapshot, a same-height mismatch, or any invalid event fails
        closed instead of being overwritten.
        """

        root = Path(deployment_dir)
        deployment_path = root / DEPLOYMENT_FILE
        state_path = root / STATE_FILE
        events_path = root / EVENTS_FILE
        try:
            deployment = load_deployment(deployment_path)
            _verify_bound_source_report(deployment)
            loaded_state = load_shadow_state(state_path)
            rebuilt = _rebuild_from_events(
                deployment,
                iter_verified_events(events_path),
                claimed_prefix_event_count=loaded_state["event_count"],
            )
        except (OSError, ValueError, ShadowIntegrityError) as exc:
            raise ShadowRuntimeIntegrityError(str(exc)) from exc

        current = rebuilt.current_snapshot
        recovered = False
        if not _json_equal(loaded_state, current):
            event_count = loaded_state.get("event_count")
            if (
                type(event_count) is not int
                or event_count < 1
                or event_count > rebuilt.event_count
            ):
                raise ShadowRuntimeIntegrityError(
                    "Shadow snapshot event_count is not a valid event prefix"
                )
            expected_prefix = rebuilt.claimed_prefix_snapshot
            if (
                event_count == rebuilt.event_count
                or expected_prefix is None
                or not _json_equal(loaded_state, expected_prefix)
            ):
                raise ShadowRuntimeIntegrityError(
                    "Shadow snapshot does not match its claimed event prefix"
                )
            try:
                write_state_atomic(state_path, current)
            except (OSError, ValueError) as exc:
                raise ShadowRuntimeIntegrityError(
                    f"could not repair stale Shadow snapshot: {exc}"
                ) from exc
            recovered = True

        return cls(
            deployment_dir=root,
            deployment=deployment,
            replay_state=rebuilt.replay_state,
            state=current,
            recovered_snapshot=recovered,
        )

    @property
    def state(self) -> dict[str, Any]:
        """Return an isolated copy of the strict persisted projection."""

        return deepcopy(self._state)

    @property
    def replay_state(self) -> ShadowReplayState:
        """Expose the immutable pure reducer state for audit and comparison."""

        return self._replay_state

    @property
    def state_digest(self) -> str:
        return _state_digest(self._replay_state)

    def start(self) -> dict[str, Any]:
        """Persistently start candle consumption without enabling order paths."""

        if self._replay_state.phase == "running":
            return self.state
        if self._replay_state.phase not in {"adopted_stopped", "stopped"}:
            raise ShadowRuntimeStateError(
                f"cannot start Shadow runtime from phase {self._replay_state.phase!r}"
            )
        prior_phase = self._replay_state.phase
        next_state = start_shadow_replay(self.deployment, self._replay_state)
        payload = self._lifecycle_payload(
            prior_phase=prior_phase,
            resulting_phase=next_state.phase,
            resulting_state_digest=_state_digest(next_state),
        )
        self._commit_event("shadow_started", payload, next_state)
        return self.state

    def stop(self) -> dict[str, Any]:
        """Stop consumption without liquidating or changing an open lot."""

        if self._replay_state.phase in {"adopted_stopped", "stopped"}:
            return self.state
        if self._replay_state.phase in {"paused", "error"}:
            # Preserve the visible failure and its evidence.  Restart is not a
            # recovery mechanism for a data-integrity pause.
            return self.state
        prior_phase = self._replay_state.phase
        next_state = stop_shadow_replay(self._replay_state)
        payload = self._lifecycle_payload(
            prior_phase=prior_phase,
            resulting_phase=next_state.phase,
            resulting_state_digest=_state_digest(next_state),
        )
        self._commit_event("shadow_stopped", payload, next_state)
        return self.state

    def process_closed_candles(
        self, candles: Sequence[Candle]
    ) -> ShadowProcessResult:
        """Durably reduce closed candles one event-fsync at a time.

        An exact already-reduced candle is ignored.  A conflict, reversal,
        missing minute, off-grid time, or malformed OHLCV emits one durable
        ``shadow_paused`` event and performs no hypothetical fill for that
        candle.
        """

        if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
            raise TypeError("candles must be a sequence of Candle values")
        if self._replay_state.phase != "running":
            raise ShadowRuntimeStateError(
                f"cannot process candles while phase is {self._replay_state.phase!r}"
            )

        processed = 0
        ignored = 0
        appended = 0
        emitted: list[PortfolioTrade] = []
        for candle in candles:
            if not isinstance(candle, Candle):
                raise TypeError("candles must contain only Candle values")
            reduction = replay_closed_candles(
                self.deployment, self._replay_state, [candle]
            )
            if reduction.ignored_idempotent_candles == 1:
                ignored += 1
                continue
            if reduction.processed_candles == 1:
                payload = self._candle_payload(candle, reduction)
                self._commit_event("candle_reduced", payload, reduction.state)
                processed += 1
                appended += 1
                emitted.extend(reduction.trades_emitted)
                continue
            if reduction.state.phase == "paused":
                payload = self._pause_payload(candle, reduction)
                self._commit_event("shadow_paused", payload, reduction.state)
                appended += 1
                break
            raise ShadowRuntimeIntegrityError(
                "pure Shadow reducer returned an unexplained no-op"
            )

        return ShadowProcessResult(
            processed_candles=processed,
            ignored_idempotent_candles=ignored,
            events_appended=appended,
            trades_emitted=tuple(emitted),
            phase=self._replay_state.phase,
            state_digest=_state_digest(self._replay_state),
        )

    def run_poller(
        self,
        stop_event: object,
        *,
        start_time_ms: int | None = None,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        **public_poller_dependencies: Any,
    ) -> None:
        """Synchronously run the injected public feed until controlled stop.

        Only :func:`run_public_kline_poller` is called.  Its documented public
        dependency injection points (for example ``fetcher`` and ``clock``)
        may be supplied for deterministic tests.  A normal poller return stops
        the Shadow lifecycle while retaining every open hypothetical lot.
        """

        if self._replay_state.phase not in {"adopted_stopped", "stopped", "running"}:
            raise ShadowRuntimeStateError(
                f"cannot run Shadow poller from phase {self._replay_state.phase!r}"
            )
        expected_start = (
            self._replay_state.last_processed_candle_open_time_ms
            + EXPECTED_STEP_MS
            if self._replay_state.last_processed_candle_open_time_ms is not None
            else _first_post_adoption_minute(self.deployment["created_at_utc"])
        )
        if start_time_ms is None:
            cursor = expected_start
        else:
            if type(start_time_ms) is not int or start_time_ms < 0:
                raise ShadowRuntimeStateError(
                    "start_time_ms must be a non-negative integer"
                )
            if start_time_ms != expected_start:
                raise ShadowRuntimeStateError(
                    "start_time_ms must match the exact forward-only Shadow cursor"
                )
            cursor = start_time_ms

        # Cursor validation must be side-effect free.  Persist the running
        # lifecycle only after every caller-supplied value is accepted.
        self.start()

        def persist_batch(batch: list[Candle]) -> None:
            result = self.process_closed_candles(batch)
            if result.phase != "running":
                raise ShadowRuntimeStateError(
                    "public Shadow consumption paused on invalid candle continuity"
                )

        try:
            run_public_kline_poller(
                cursor,
                stop_event,  # type: ignore[arg-type]
                persist_batch,
                poll_interval_seconds,
                **public_poller_dependencies,
            )
        except PublicKlineContinuityError:
            if self._replay_state.phase == "running":
                self._record_feed_transition(
                    "shadow_feed_continuity_paused",
                    resulting_phase="paused",
                    reason="public_feed_continuity_error",
                )
            raise
        except PublicKlineValidationError:
            if self._replay_state.phase == "running":
                self._record_feed_transition(
                    "shadow_feed_validation_paused",
                    resulting_phase="paused",
                    reason="public_feed_validation_error",
                )
            raise
        except PublicKlineNetworkError:
            if self._replay_state.phase == "running":
                self._record_feed_transition(
                    "shadow_feed_interrupted",
                    resulting_phase="stopped",
                    reason="public_feed_network_error",
                )
            raise
        except Exception:
            if self._replay_state.phase == "running":
                self._record_feed_transition(
                    "shadow_feed_error",
                    resulting_phase="error",
                    reason="public_feed_poller_error",
                )
            raise
        else:
            if self._replay_state.phase == "running":
                self.stop()

    def _record_feed_transition(
        self,
        event_type: str,
        *,
        resulting_phase: str,
        reason: str,
    ) -> None:
        prior_phase = self._replay_state.phase
        if prior_phase != "running":
            return
        next_state = replace(
            self._replay_state,
            phase=resulting_phase,
            paused_reason=reason,
        )
        payload = _feed_transition_payload(
            self.deployment,
            self._deployment_digest,
            prior_phase=prior_phase,
            resulting_phase=resulting_phase,
            reason=reason,
            resulting_state_digest=_state_digest(next_state),
        )
        self._commit_event(event_type, payload, next_state)

    def _event_context(self) -> dict[str, Any]:
        return {
            "deployment_id": self.deployment["deployment_id"],
            "deployment_digest": self._deployment_digest,
            "source_report_sha256": self.deployment["source_report"]["sha256"],
            "candidate_signature": deepcopy(
                self.deployment["candidate"]["candidate_signature"]
            ),
            "public_data_only": True,
            "hypothetical": True,
            "orders_enabled": False,
            "trading_api_enabled": False,
            "api_keys_used": False,
        }

    def _lifecycle_payload(
        self,
        *,
        prior_phase: str,
        resulting_phase: str,
        resulting_state_digest: str,
    ) -> dict[str, Any]:
        return {
            "context": self._event_context(),
            "prior_phase": prior_phase,
            "resulting_phase": resulting_phase,
            "resulting_state_digest": resulting_state_digest,
        }

    def _candle_payload(
        self, candle: Candle, reduction: ShadowReplayResult
    ) -> dict[str, Any]:
        return {
            "context": self._event_context(),
            "candle": _candle_to_payload(candle),
            "step_events": _step_events_payload(reduction),
            "trades": [asdict(trade) for trade in reduction.trades_emitted],
            "resulting_state_digest": _state_digest(reduction.state),
        }

    def _pause_payload(
        self, candle: Candle, reduction: ShadowReplayResult
    ) -> dict[str, Any]:
        reason = reduction.state.paused_reason
        if not isinstance(reason, str) or not reason:
            raise ShadowRuntimeIntegrityError("paused reducer state has no reason")
        return {
            "context": self._event_context(),
            "attempted_candle": _candle_to_payload(candle),
            "reason": reason,
            "step_events": _step_events_payload(reduction),
            "trades": [asdict(trade) for trade in reduction.trades_emitted],
            "resulting_state_digest": _state_digest(reduction.state),
        }

    def _commit_event(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        replay_state: ShadowReplayState,
    ) -> None:
        timestamp = utc_now()
        with _exclusive_writer_lock(self.deployment_dir / WRITER_LOCK_FILE):
            self._assert_current_writer_projection(event_type)
            try:
                record = append_event_at_expected_head(
                    self.events_path,
                    event_type,
                    payload,
                    expected_sequence=self._state["event_count"] + 1,
                    expected_previous_hash=self._state["last_event_hash"],
                    timestamp_utc=timestamp,
                )
            except (OSError, ValueError) as exc:
                raise ShadowRuntimeIntegrityError(
                    f"could not durably append Shadow event: {exc}"
                ) from exc

            # The fsynced event is now authoritative even if the atomic
            # snapshot replacement below fails.  Keep memory aligned so the
            # next explicit open can prove and repair the earlier snapshot.
            self._replay_state = replay_state
            next_snapshot = _snapshot_from_replay(
                self.deployment,
                replay_state,
                event_count=record["sequence"],
                last_event_hash=record["event_hash"],
                updated_at_utc=record["timestamp_utc"],
            )
            self._state = next_snapshot
            try:
                write_state_atomic(self.state_path, next_snapshot)
            except (OSError, ValueError) as exc:
                raise ShadowRuntimeIntegrityError(
                    f"Shadow event is durable but snapshot update failed: {exc}"
                ) from exc

    def _assert_current_writer_projection(self, event_type: str) -> None:
        """Reject stale instances and periodically re-audit the full chain."""

        try:
            persisted = load_shadow_state(self.state_path)
        except (OSError, ValueError, ShadowIntegrityError) as exc:
            raise ShadowRuntimeIntegrityError(
                f"could not verify current Shadow snapshot before append: {exc}"
            ) from exc
        if not _json_equal(persisted, self._state):
            raise ShadowRuntimeStateError(
                "Shadow writer snapshot changed; reopen before mutating"
            )
        next_sequence = self._state["event_count"] + 1
        full_verify = (
            event_type != "candle_reduced"
            or next_sequence % FULL_CHAIN_VERIFY_INTERVAL == 0
        )
        if not full_verify:
            return
        try:
            head = verify_event_log(self.events_path)
        except (OSError, ValueError, ShadowIntegrityError) as exc:
            raise ShadowRuntimeIntegrityError(
                f"Shadow event-chain audit failed before append: {exc}"
            ) from exc
        if (
            head["event_count"] != self._state["event_count"]
            or head["last_event_hash"] != self._state["last_event_hash"]
        ):
            raise ShadowRuntimeStateError(
                "Shadow event head changed; reopen before mutating"
            )


def _rebuild_from_events(
    deployment: Mapping[str, Any],
    records: Iterable[dict[str, Any]],
    *,
    claimed_prefix_event_count: int,
) -> _RebuiltRuntime:
    iterator = iter(records)
    genesis = next(iterator, None)
    if genesis is None:
        raise ShadowRuntimeIntegrityError("Shadow event log has no adoption event")
    _verify_adoption_event(deployment, genesis)
    initial_snapshot = _initial_snapshot(deployment, genesis)
    try:
        replay_state = initialize_shadow_replay(deployment, initial_snapshot)
    except ValueError as exc:
        raise ShadowRuntimeIntegrityError(str(exc)) from exc
    current_snapshot = initial_snapshot
    claimed_prefix_snapshot = (
        initial_snapshot if claimed_prefix_event_count == 1 else None
    )
    event_count = 1
    deployment_digest = sha256(canonical_json_bytes(deployment)).hexdigest()

    for record in iterator:
        event_type = record["event_type"]
        payload = record["payload"]
        if event_type == "shadow_started":
            prior = replay_state.phase
            try:
                next_state = start_shadow_replay(deployment, replay_state)
            except ValueError as exc:
                raise ShadowRuntimeIntegrityError(str(exc)) from exc
            expected = _lifecycle_payload(
                deployment,
                deployment_digest,
                prior_phase=prior,
                resulting_phase=next_state.phase,
                resulting_state_digest=_state_digest(next_state),
            )
        elif event_type == "shadow_stopped":
            if replay_state.phase != "running":
                raise ShadowRuntimeIntegrityError(
                    "shadow_stopped event is invalid outside running phase"
                )
            prior = replay_state.phase
            next_state = stop_shadow_replay(replay_state)
            expected = _lifecycle_payload(
                deployment,
                deployment_digest,
                prior_phase=prior,
                resulting_phase=next_state.phase,
                resulting_state_digest=_state_digest(next_state),
            )
        elif event_type in {"candle_reduced", "shadow_paused"}:
            if replay_state.phase != "running":
                raise ShadowRuntimeIntegrityError(
                    f"{event_type} event is invalid outside running phase"
                )
            candle_key = "candle" if event_type == "candle_reduced" else "attempted_candle"
            if candle_key not in payload:
                raise ShadowRuntimeIntegrityError(
                    f"{event_type} event has no {candle_key}"
                )
            candle = _candle_from_payload(payload[candle_key])
            try:
                reduction = replay_closed_candles(deployment, replay_state, [candle])
            except ValueError as exc:
                raise ShadowRuntimeIntegrityError(str(exc)) from exc
            next_state = reduction.state
            if event_type == "candle_reduced":
                if reduction.processed_candles != 1 or next_state.phase != "running":
                    raise ShadowRuntimeIntegrityError(
                        "candle_reduced event does not deterministically reduce one candle"
                    )
                expected = _reduced_payload(
                    deployment, deployment_digest, candle, reduction
                )
            else:
                if reduction.processed_candles != 0 or next_state.phase != "paused":
                    raise ShadowRuntimeIntegrityError(
                        "shadow_paused event is not reproduced by its attempted candle"
                    )
                expected = _paused_payload(
                    deployment, deployment_digest, candle, reduction
                )
        elif event_type in _FEED_TRANSITIONS:
            if replay_state.phase != "running":
                raise ShadowRuntimeIntegrityError(
                    f"{event_type} event is invalid outside running phase"
                )
            resulting_phase, reason = _FEED_TRANSITIONS[event_type]
            next_state = replace(
                replay_state,
                phase=resulting_phase,
                paused_reason=reason,
            )
            expected = _feed_transition_payload(
                deployment,
                deployment_digest,
                prior_phase="running",
                resulting_phase=resulting_phase,
                reason=reason,
                resulting_state_digest=_state_digest(next_state),
            )
        else:
            raise ShadowRuntimeIntegrityError(
                f"unsupported Shadow runtime event type: {event_type!r}"
            )

        if not _json_equal(payload, expected):
            raise ShadowRuntimeIntegrityError(
                f"Shadow event {record['sequence']} payload disagrees with deterministic replay"
            )
        replay_state = next_state
        event_count = record["sequence"]
        current_snapshot = _snapshot_from_replay(
            deployment,
            replay_state,
            event_count=event_count,
            last_event_hash=record["event_hash"],
            updated_at_utc=record["timestamp_utc"],
        )
        if event_count == claimed_prefix_event_count:
            claimed_prefix_snapshot = current_snapshot
    return _RebuiltRuntime(
        replay_state,
        current_snapshot,
        claimed_prefix_snapshot,
        event_count,
    )


def _verify_bound_source_report(deployment: Mapping[str, Any]) -> None:
    source = deployment["source_report"]
    path = Path(source["path"])
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ShadowRuntimeIntegrityError(
            f"could not read deployment-bound final report: {exc}"
        ) from exc
    digest = sha256(raw).hexdigest()
    if digest != source["sha256"]:
        raise ShadowRuntimeIntegrityError(
            "deployment-bound final report SHA-256 does not match"
        )
    try:
        report = json.loads(raw, parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ShadowRuntimeIntegrityError(
            "deployment-bound final report is not strict JSON"
        ) from exc
    if not isinstance(report, dict):
        raise ShadowRuntimeIntegrityError(
            "deployment-bound final report must be an object"
        )
    bindings = {
        "schema_version": 1,
        "report_type": "final_evaluation",
        "final_evaluation_id": source["final_evaluation_id"],
        "source_research_run_id": source["source_research_run_id"],
        "git_commit": source["git_commit"],
        "candidate": deployment["candidate"],
    }
    for key, expected in bindings.items():
        if key not in report or not _json_equal(report[key], expected):
            raise ShadowRuntimeIntegrityError(
                f"deployment-bound final report disagrees on {key}"
            )


def _verify_adoption_event(
    deployment: Mapping[str, Any], record: Mapping[str, Any]
) -> None:
    if record.get("event_type") != "deployment_adopted":
        raise ShadowRuntimeIntegrityError(
            "first Shadow event must be deployment_adopted"
        )
    if record.get("timestamp_utc") != deployment["created_at_utc"]:
        raise ShadowRuntimeIntegrityError(
            "adoption event timestamp does not match deployment creation"
        )
    payload = record.get("payload")
    if not isinstance(payload, Mapping) or set(payload) != _ADOPTION_EVENT_KEYS:
        raise ShadowRuntimeIntegrityError("adoption event payload schema is invalid")
    expected = {
        "deployment_id": deployment["deployment_id"],
        "final_evaluation_id": deployment["source_report"]["final_evaluation_id"],
        "source_report_sha256": deployment["source_report"]["sha256"],
        "candidate_id": deployment["candidate"]["candidate_id"],
        "candidate_signature": deployment["candidate"]["candidate_signature"],
        "assessment_color": deployment["assessment"]["color"],
        "deployment_budget_usdc": deployment["portfolio_policy"]["policy"][
            "deployment_budget_usdc"
        ],
        "lot_notional_usdc": 100,
        "orders_enabled": False,
        "trading_api_enabled": False,
        "api_keys_used": False,
    }
    if not _json_equal(payload, expected):
        raise ShadowRuntimeIntegrityError(
            "adoption event does not bind the deployment receipt"
        )


def _initial_snapshot(
    deployment: Mapping[str, Any], genesis: Mapping[str, Any]
) -> dict[str, Any]:
    policy = deployment["portfolio_policy"]["policy"]
    state = {
        "schema_version": 1,
        "deployment_id": deployment["deployment_id"],
        "phase": "adopted_stopped",
        "created_at_utc": deployment["created_at_utc"],
        "updated_at_utc": genesis["timestamp_utc"],
        "deployment_budget_usdc": policy["deployment_budget_usdc"],
        "lot_notional_usdc": 100.0,
        "max_open_lots": policy["max_concurrent_lots"],
        "last_processed_candle_open_time_ms": None,
        "open_lots": [],
        "realized_net_usdc": 0.0,
        "unrealized_net_usdc": 0.0,
        "event_count": 1,
        "last_event_hash": genesis["event_hash"],
        "error": None,
        "safety": deepcopy(deployment["safety"]),
    }
    validate_shadow_state(state)
    return state


def _snapshot_from_replay(
    deployment: Mapping[str, Any],
    replay_state: ShadowReplayState,
    *,
    event_count: int,
    last_event_hash: str,
    updated_at_utc: str,
) -> dict[str, Any]:
    engine = replay_state.engine_state
    candles = engine.candles
    open_lots: list[dict[str, Any]] = []
    for lot in engine.open_lots:
        held_closes = [
            float(candle.close) for candle in candles[lot.entry_index :]
        ]
        best_close = max(held_closes) if held_closes else float(lot.entry_price)
        open_lots.append(
            {
                "lot_id": lot.lot_id,
                "signal_time_ms": lot.signal_time_ms,
                "entry_time_ms": lot.entry_time_ms,
                "entry_mid_price": float(lot.entry_mid_price),
                "entry_price": float(lot.entry_price),
                "quantity": float(lot.quantity),
                "notional_usdc": float(lot.entry_notional_usdc),
                "best_close": best_close,
            }
        )
    realized = float(engine.realized_net_usdc)
    liquidation_equity = (
        float(engine.equity_curve[-1].equity_usdc)
        if engine.equity_curve
        else realized
    )
    policy = deployment["portfolio_policy"]["policy"]
    error = replay_state.paused_reason
    state = {
        "schema_version": 1,
        "deployment_id": deployment["deployment_id"],
        "phase": replay_state.phase,
        "created_at_utc": deployment["created_at_utc"],
        "updated_at_utc": updated_at_utc,
        "deployment_budget_usdc": policy["deployment_budget_usdc"],
        "lot_notional_usdc": 100.0,
        "max_open_lots": policy["max_concurrent_lots"],
        "last_processed_candle_open_time_ms": (
            candles[-1].open_time if candles else None
        ),
        "open_lots": open_lots,
        "realized_net_usdc": realized,
        "unrealized_net_usdc": round(liquidation_equity - realized, 10),
        "event_count": event_count,
        "last_event_hash": last_event_hash,
        "error": error,
        "safety": deepcopy(deployment["safety"]),
    }
    validate_shadow_state(state)
    return state


def _state_digest(state: ShadowReplayState) -> str:
    engine = state.engine_state
    payload = {
        "schema_version": 1,
        "deployment_id": state.deployment_id,
        "phase": state.phase,
        "paused_reason": state.paused_reason,
        "strategy": asdict(state.strategy),
        "portfolio_policy": state.policy.to_dict(),
        # The append-only event chain already binds every historical candle.
        # Keep this per-event reducer digest bounded while committing all
        # forward-relevant state and cumulative counters.
        "engine_state": {
            "candle_count": len(engine.candles),
            "last_candle": asdict(engine.candles[-1]) if engine.candles else None,
            "open_lots": [asdict(lot) for lot in engine.open_lots],
            "pending_entry": (
                asdict(engine.pending_entry)
                if engine.pending_entry is not None
                else None
            ),
            "cooldown_until_index": engine.cooldown_until_index,
            "realized_net_usdc": engine.realized_net_usdc,
            "trade_count": len(engine.trades),
            "last_trade": asdict(engine.trades[-1]) if engine.trades else None,
            "capacity_rejection_count": len(engine.capacity_rejections),
            "last_capacity_rejection": (
                asdict(engine.capacity_rejections[-1])
                if engine.capacity_rejections
                else None
            ),
            "equity_point_count": len(engine.equity_curve),
            "last_equity_point": (
                asdict(engine.equity_curve[-1]) if engine.equity_curve else None
            ),
            "next_lot_sequence": engine.next_lot_sequence,
            "max_concurrent_lots": engine.max_concurrent_lots,
            "max_open_entry_exposure_usdc": engine.max_open_entry_exposure_usdc,
            "max_reserved_notional_usdc": engine.max_reserved_notional_usdc,
        },
        "next_event_sequence": state.next_event_sequence,
        "hypothetical": True,
        "orders_enabled": False,
        "trading_api_enabled": False,
    }
    return sha256(canonical_json_bytes(payload)).hexdigest()


@contextmanager
def _exclusive_writer_lock(path: Path) -> Iterator[None]:
    """Hold a cross-process byte lock for one append/snapshot transaction."""

    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    locked = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise ShadowRuntimeStateError(
                "another Shadow writer currently owns this deployment"
            ) from exc
        yield
    finally:
        if locked:
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def _event_context(
    deployment: Mapping[str, Any], deployment_digest: str
) -> dict[str, Any]:
    return {
        "deployment_id": deployment["deployment_id"],
        "deployment_digest": deployment_digest,
        "source_report_sha256": deployment["source_report"]["sha256"],
        "candidate_signature": deepcopy(
            deployment["candidate"]["candidate_signature"]
        ),
        "public_data_only": True,
        "hypothetical": True,
        "orders_enabled": False,
        "trading_api_enabled": False,
        "api_keys_used": False,
    }


def _lifecycle_payload(
    deployment: Mapping[str, Any],
    deployment_digest: str,
    *,
    prior_phase: str,
    resulting_phase: str,
    resulting_state_digest: str,
) -> dict[str, Any]:
    return {
        "context": _event_context(deployment, deployment_digest),
        "prior_phase": prior_phase,
        "resulting_phase": resulting_phase,
        "resulting_state_digest": resulting_state_digest,
    }


_FEED_TRANSITIONS = {
    "shadow_feed_continuity_paused": ("paused", "public_feed_continuity_error"),
    "shadow_feed_validation_paused": ("paused", "public_feed_validation_error"),
    "shadow_feed_interrupted": ("stopped", "public_feed_network_error"),
    "shadow_feed_error": ("error", "public_feed_poller_error"),
}


def _feed_transition_payload(
    deployment: Mapping[str, Any],
    deployment_digest: str,
    *,
    prior_phase: str,
    resulting_phase: str,
    reason: str,
    resulting_state_digest: str,
) -> dict[str, Any]:
    return {
        "context": _event_context(deployment, deployment_digest),
        "prior_phase": prior_phase,
        "resulting_phase": resulting_phase,
        "reason": reason,
        "resulting_state_digest": resulting_state_digest,
    }


def _reduced_payload(
    deployment: Mapping[str, Any],
    deployment_digest: str,
    candle: Candle,
    reduction: ShadowReplayResult,
) -> dict[str, Any]:
    return {
        "context": _event_context(deployment, deployment_digest),
        "candle": _candle_to_payload(candle),
        "step_events": _step_events_payload(reduction),
        "trades": [asdict(trade) for trade in reduction.trades_emitted],
        "resulting_state_digest": _state_digest(reduction.state),
    }


def _paused_payload(
    deployment: Mapping[str, Any],
    deployment_digest: str,
    candle: Candle,
    reduction: ShadowReplayResult,
) -> dict[str, Any]:
    return {
        "context": _event_context(deployment, deployment_digest),
        "attempted_candle": _candle_to_payload(candle),
        "reason": reduction.state.paused_reason,
        "step_events": _step_events_payload(reduction),
        "trades": [asdict(trade) for trade in reduction.trades_emitted],
        "resulting_state_digest": _state_digest(reduction.state),
    }


def _step_events_payload(reduction: ShadowReplayResult) -> list[dict[str, Any]]:
    return [asdict(event) for event in reduction.events]


def _candle_to_payload(candle: Candle) -> dict[str, Any]:
    payload = {
        "open_time_ms": candle.open_time,
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }
    # Reject non-finite floats before the append-only store is touched.
    canonical_json_bytes(payload)
    return payload


def _candle_from_payload(value: object) -> Candle:
    if not isinstance(value, Mapping) or set(value) != _CANDLE_KEYS:
        raise ShadowRuntimeIntegrityError("persisted candle payload schema is invalid")
    try:
        return Candle(
            open_time=value["open_time_ms"],  # type: ignore[arg-type]
            open=value["open"],  # type: ignore[arg-type]
            high=value["high"],  # type: ignore[arg-type]
            low=value["low"],  # type: ignore[arg-type]
            close=value["close"],  # type: ignore[arg-type]
            volume=value["volume"],  # type: ignore[arg-type]
        )
    except (TypeError, ValueError) as exc:
        raise ShadowRuntimeIntegrityError("persisted candle payload is invalid") from exc


def _json_equal(left: object, right: object) -> bool:
    try:
        return canonical_json_bytes(left) == canonical_json_bytes(right)
    except ValueError:
        return False


def _first_post_adoption_minute(value: object) -> int:
    try:
        return first_shadow_candle_open_time_ms(value)
    except ValueError as exc:
        raise ShadowRuntimeStateError(
            "deployment creation timestamp is invalid"
        ) from exc


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


__all__ = [
    "EVENTS_FILE",
    "DEPLOYMENT_FILE",
    "STATE_FILE",
    "ShadowProcessResult",
    "ShadowRuntime",
    "ShadowRuntimeError",
    "ShadowRuntimeIntegrityError",
    "ShadowRuntimeStateError",
]
