"""Protocol v3 three-market closed-bar context parity.

This module reuses the existing trailing-only context veto and the Task-8
execution engine.  It adds one fail-closed binding shared by research, replay,
final-evaluator, and research-challenger calls.  BTCUSDC and ETHBTC remain
context-only and can neither create a signal nor trigger a trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any, Final, Mapping, Sequence

from ethusdc_bot.backtest.context_features import (
    CONTEXT_POLICY_VERSION,
    ContextDecision,
    ContextVetoPolicy,
    evaluate_context_veto,
    validate_context_against_trade_candles,
)
from ethusdc_bot.backtest.context_research import wrap_candidate_with_context
from ethusdc_bot.backtest.data_loader import (
    EXPECTED_STEP_MS,
    AlignedMarketCandles,
    Candle,
    DataLoadError,
)
from ethusdc_bot.backtest.portfolio_simulator import PortfolioSimulationResult
from ethusdc_bot.backtest.simulator import SimulationResult, StrategyCandidate
from ethusdc_bot.portfolio import PortfolioPolicy
from ethusdc_bot.protocol_v3.data_snapshot import (
    DataSnapshotError,
    FrozenDataSnapshot,
    compute_utc_day_content_sha256,
    validate_frozen_data_snapshot,
)
from ethusdc_bot.protocol_v3.intrabar_execution import (
    BASELINE_COST_PROFILE,
    ExecutionCostProfile,
    simulate_protocol_v3_intrabar_portfolio_strategy,
    simulate_protocol_v3_intrabar_strategy,
)
from ethusdc_bot.protocol_v3.run_identity import FrozenExchangeInfoSnapshot
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy


CONTEXT_PARITY_CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_context_parity_contract.json"
)
CONTEXT_PARITY_CONTRACT_SCHEMA: Final = (
    "protocol_v3_context_parity_contract_v2"
)
CONTEXT_PARITY_CONTRACT_VERSION: Final = (
    "three_market_closed_bar_context_parity_v2"
)
CONTEXT_PATHS: Final = (
    "research",
    "replay",
    "final_evaluator",
    "research_challenger",
)
TRADE_SYMBOL: Final = "ETHUSDC"
CONTEXT_SYMBOLS: Final = ("BTCUSDC", "ETHBTC")
MARKETS: Final = (TRADE_SYMBOL, *CONTEXT_SYMBOLS)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_DAY_MS = 86_400_000

_CANONICAL_SAFETY = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: dict[str, Any] = {
    "schema_version": CONTEXT_PARITY_CONTRACT_SCHEMA,
    "protocol_version": "3.0.0",
    "contract_version": CONTEXT_PARITY_CONTRACT_VERSION,
    "markets": [
        {
            "symbol": "ETHUSDC",
            "role": "trade_market",
            "may_create_signal": True,
            "may_trigger_trade": True,
        },
        {
            "symbol": "BTCUSDC",
            "role": "context_only",
            "may_create_signal": False,
            "may_trigger_trade": False,
        },
        {
            "symbol": "ETHBTC",
            "role": "context_only",
            "may_create_signal": False,
            "may_trigger_trade": False,
        },
    ],
    "paths": list(CONTEXT_PATHS),
    "parity_policy": {
        "all_paths_use_same_context_engine": True,
        "context_may_only_confirm_or_veto_existing_ethusdc_signal": True,
        "context_may_never_create_signal": True,
        "context_may_never_submit_order": True,
        "candidate_policy_must_be_identical_across_paths": True,
    },
    "time_policy": {
        "timezone": "UTC",
        "source_interval": "1m",
        "source_bar_ms": EXPECTED_STEP_MS,
        "decision_time": "closed_signal_bar_end",
        "required_markets_per_decision": 3,
        "exact_open_time_identity_required": True,
        "nearest_neighbor_forbidden": True,
        "forward_fill_forbidden": True,
        "interpolation_forbidden": True,
        "missing_context": "block",
        "misaligned_context": "block",
        "stale_context": "block",
        "future_context": "block",
    },
    "watermark_policy": {
        "source": "validated_protocol_v3_three_market_data_snapshot",
        "rule": "latest_common_closed_1m_bar_not_after_snapshot_common_complete_day",
        "window_must_lie_inside_snapshot_raw_interval": True,
        "all_three_market_content_digests_required": True,
        "common_grid_digest_required": True,
        "complete_utc_day_windows_required": True,
        "window_day_content_must_match_snapshot_index": True,
    },
    "identity_policy": {
        "data_snapshot_sha256_required": True,
        "context_contract_sha256_required": True,
        "policy_payload_sha256_required": True,
        "window_market_content_sha256_required": True,
        "context_identity_sha256_required": True,
        "pipeline_and_run_fingerprint_binding_required": True,
        "cache_or_resume_reuse_requires_exact_identity": True,
    },
    "deferred_scope": {
        "report_schemas_task": 11,
        "cache_store_task": 13,
        "feature_store_task": 19,
        "router_task": 22,
        "challenger_controller_task": 29,
        "final_evaluator_task": 31,
    },
    "safety": _CANONICAL_SAFETY,
}


class ContextParityError(RuntimeError):
    """Raised when three-market context would be missing, stale, or divergent."""


@dataclass(frozen=True)
class ContextParityBinding:
    context: AlignedMarketCandles
    policy: ContextVetoPolicy
    data_snapshot: FrozenDataSnapshot
    data_snapshot_sha256: str
    data_snapshot_common_grid_sha256: str
    snapshot_market_content_sha256: tuple[tuple[str, str], ...]
    window_market_content_sha256: tuple[tuple[str, str], ...]
    first_open_time_ms: int
    common_watermark_open_time_ms: int
    candle_count: int
    context_identity_sha256: str
    contract_version: str = CONTEXT_PARITY_CONTRACT_VERSION
    policy_version: str = CONTEXT_POLICY_VERSION

    @property
    def cache_key(self) -> str:
        return f"protocol_v3_context_sha256:{self.context_identity_sha256}"

    @property
    def resume_key(self) -> str:
        return self.cache_key

    def identity_payload(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "policy_version": self.policy_version,
            "policy": self.policy.to_dict(),
            "data_snapshot_sha256": self.data_snapshot_sha256,
            "data_snapshot_common_grid_sha256": self.data_snapshot_common_grid_sha256,
            "snapshot_market_content_sha256": dict(
                self.snapshot_market_content_sha256
            ),
            "window_market_content_sha256": dict(
                self.window_market_content_sha256
            ),
            "first_open_time_ms": self.first_open_time_ms,
            "common_watermark_open_time_ms": self.common_watermark_open_time_ms,
            "candle_count": self.candle_count,
        }


def load_context_parity_contract(
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
        else root / CONTEXT_PARITY_CONTRACT_PATH
    )
    if not path.is_absolute():
        path = root / path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContextParityError(
            f"context parity contract is missing or invalid: {path}"
        ) from exc
    validate_context_parity_contract(value)
    return value


def validate_context_parity_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize_json(value) != _CANONICAL_CONTRACT:
        raise ContextParityError("Protocol v3 context parity contract is not canonical")


def build_context_parity_binding(
    context: AlignedMarketCandles,
    policy: ContextVetoPolicy,
    data_snapshot: FrozenDataSnapshot | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> ContextParityBinding:
    """Bind one exact three-market window to a validated Task-5 snapshot."""

    load_context_parity_contract(repo_root)
    if not isinstance(context, AlignedMarketCandles):
        raise ContextParityError("context must be AlignedMarketCandles")
    if not isinstance(policy, ContextVetoPolicy):
        raise ContextParityError("policy must be ContextVetoPolicy")
    if context.candle_count <= 0:
        raise ContextParityError("three-market context window must be non-empty")
    _validate_aligned_context(context)

    frozen_snapshot = _coerce_frozen_data_snapshot(data_snapshot)
    try:
        validate_frozen_data_snapshot(frozen_snapshot, repo_root=repo_root)
    except Exception as exc:
        raise ContextParityError(f"validated Task-5 snapshot required: {exc}") from exc
    snapshot_payload, snapshot_sha = _snapshot_parts(frozen_snapshot)
    raw_interval = _require_mapping(snapshot_payload.get("raw_interval"), "raw_interval")
    raw_start_ms = _utc_ms(raw_interval.get("start_inclusive"), "raw start")
    raw_end_ms = _utc_ms(raw_interval.get("end_exclusive"), "raw end")
    first = context.ethusdc[0].open_time
    last = context.ethusdc[-1].open_time
    if first < raw_start_ms or last + EXPECTED_STEP_MS > raw_end_ms:
        raise ContextParityError("context window lies outside the frozen raw interval")

    availability = _require_mapping(snapshot_payload.get("availability"), "availability")
    latest_day = str(availability.get("latest_common_complete_day", ""))
    latest_day_end_ms = _utc_ms(f"{latest_day}T00:00:00Z", "common day") + 86_400_000
    if last + EXPECTED_STEP_MS > latest_day_end_ms:
        raise ContextParityError("context watermark exceeds the snapshot common complete day")

    common_grid, snapshot_market_digests = _snapshot_content_identity(
        snapshot_payload
    )

    window_digests = tuple(
        (symbol, _candles_sha256(candles))
        for symbol, candles in _market_series(context)
    )
    _validate_snapshot_window_provenance(context, snapshot_payload)
    identity = {
        "contract_version": CONTEXT_PARITY_CONTRACT_VERSION,
        "policy_version": CONTEXT_POLICY_VERSION,
        "policy": policy.to_dict(),
        "data_snapshot_sha256": snapshot_sha,
        "data_snapshot_common_grid_sha256": common_grid,
        "snapshot_market_content_sha256": dict(snapshot_market_digests),
        "window_market_content_sha256": dict(window_digests),
        "first_open_time_ms": first,
        "common_watermark_open_time_ms": last,
        "candle_count": context.candle_count,
    }
    identity_sha = _sha256_json(identity)
    return ContextParityBinding(
        context=context,
        policy=policy,
        data_snapshot=frozen_snapshot,
        data_snapshot_sha256=snapshot_sha,
        data_snapshot_common_grid_sha256=common_grid,
        snapshot_market_content_sha256=snapshot_market_digests,
        window_market_content_sha256=window_digests,
        first_open_time_ms=first,
        common_watermark_open_time_ms=last,
        candle_count=context.candle_count,
        context_identity_sha256=identity_sha,
    )


def validate_context_parity_binding(binding: ContextParityBinding) -> None:
    if not isinstance(binding, ContextParityBinding):
        raise ContextParityError("binding must be ContextParityBinding")
    if binding.contract_version != CONTEXT_PARITY_CONTRACT_VERSION:
        raise ContextParityError("binding context contract version is invalid")
    if binding.policy_version != CONTEXT_POLICY_VERSION:
        raise ContextParityError("binding context policy version is invalid")
    if not isinstance(binding.policy, ContextVetoPolicy):
        raise ContextParityError("binding policy must be ContextVetoPolicy")
    try:
        validate_frozen_data_snapshot(binding.data_snapshot)
    except Exception as exc:
        raise ContextParityError(
            f"binding Task-5 snapshot is invalid: {exc}"
        ) from exc
    snapshot_payload, snapshot_sha = _snapshot_parts(binding.data_snapshot)
    if binding.data_snapshot_sha256 != snapshot_sha:
        raise ContextParityError("binding snapshot digest does not match its snapshot")
    _validate_aligned_context(binding.context)
    if binding.candle_count != binding.context.candle_count:
        raise ContextParityError("binding candle count is invalid")
    if binding.first_open_time_ms != binding.context.ethusdc[0].open_time:
        raise ContextParityError("binding first timestamp is invalid")
    if binding.common_watermark_open_time_ms != binding.context.ethusdc[-1].open_time:
        raise ContextParityError("binding watermark is invalid")
    if not _HEX64_RE.fullmatch(binding.data_snapshot_sha256):
        raise ContextParityError("binding snapshot digest is invalid")
    if not _HEX64_RE.fullmatch(binding.data_snapshot_common_grid_sha256):
        raise ContextParityError("binding grid digest is invalid")
    snapshot_grid, snapshot_market_digests = _snapshot_content_identity(
        snapshot_payload
    )
    if binding.data_snapshot_common_grid_sha256 != snapshot_grid:
        raise ContextParityError("binding grid digest does not match its snapshot")
    if binding.snapshot_market_content_sha256 != snapshot_market_digests:
        raise ContextParityError(
            "binding market content digests do not match its snapshot"
        )
    _validate_snapshot_window_provenance(binding.context, snapshot_payload)
    expected_window = tuple(
        (symbol, _candles_sha256(candles))
        for symbol, candles in _market_series(binding.context)
    )
    if expected_window != binding.window_market_content_sha256:
        raise ContextParityError("binding window content digest mismatch")
    expected_identity = _sha256_json(binding.identity_payload())
    if binding.context_identity_sha256 != expected_identity:
        raise ContextParityError("binding context identity digest mismatch")
    if binding.cache_key != binding.resume_key:
        raise ContextParityError("context cache and resume keys must be identical")


def evaluate_closed_bar_context(
    binding: ContextParityBinding,
    index: int,
    *,
    decision_time_ms: int,
) -> ContextDecision:
    """Evaluate exactly one common fully closed 1m bar, never stale or future data."""

    validate_context_parity_binding(binding)
    return _evaluate_closed_bar_context_validated(
        binding,
        index,
        decision_time_ms=decision_time_ms,
    )


def _evaluate_closed_bar_context_validated(
    binding: ContextParityBinding,
    index: int,
    *,
    decision_time_ms: int,
) -> ContextDecision:
    if type(index) is not int or not 0 <= index < binding.candle_count:
        raise ContextParityError("context index is outside the bound window")
    expected_open = binding.context.ethusdc[index].open_time
    expected_decision_time = expected_open + EXPECTED_STEP_MS - 1
    if decision_time_ms < expected_decision_time:
        raise ContextParityError("future or unclosed context is forbidden")
    if decision_time_ms > expected_decision_time:
        raise ContextParityError("stale context is forbidden")
    for symbol, candles in _market_series(binding.context):
        if candles[index].open_time != expected_open:
            raise ContextParityError(f"{symbol} context is misaligned")
    return evaluate_context_veto(binding.context, index, binding.policy)


def simulate_protocol_v3_context_path(
    path: str,
    binding: ContextParityBinding,
    candles: list[Candle],
    strategy: StrategyCandidate,
    *,
    days: int,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    horizon_policy: HorizonPolicy,
    cost_profile: ExecutionCostProfile = BASELINE_COST_PROFILE,
    training_days: int = 0,
    blindtest_days: int = 0,
) -> SimulationResult:
    """Run all Protocol-v3 evaluation paths through one context and fill engine."""

    _validate_path(path)
    validate_context_parity_binding(binding)
    _validate_trade_window(candles, binding)
    wrapped = _context_candidate(strategy, binding.policy)
    return simulate_protocol_v3_intrabar_strategy(
        candles,
        wrapped,
        days=days,
        exchange_info_snapshot=exchange_info_snapshot,
        horizon_policy=horizon_policy,
        cost_profile=cost_profile,
        training_days=training_days,
        blindtest_days=blindtest_days,
        market_context=binding.context,
        closed_context_decision_provider=lambda index, decision_time_ms: (
            _evaluate_closed_bar_context_validated(
                binding,
                index,
                decision_time_ms=decision_time_ms,
            )
        ),
    )


def simulate_protocol_v3_context_portfolio_path(
    path: str,
    binding: ContextParityBinding,
    candles: list[Candle],
    strategy: StrategyCandidate,
    *,
    days: int,
    policy: PortfolioPolicy,
    exchange_info_snapshot: FrozenExchangeInfoSnapshot | Mapping[str, Any],
    horizon_policy: HorizonPolicy,
    cost_profile: ExecutionCostProfile = BASELINE_COST_PROFILE,
    training_days: int = 0,
    blindtest_days: int = 0,
) -> PortfolioSimulationResult:
    """Expose the same bound context engine through the order-free portfolio path."""

    _validate_path(path)
    validate_context_parity_binding(binding)
    _validate_trade_window(candles, binding)
    wrapped = _context_candidate(strategy, binding.policy)
    return simulate_protocol_v3_intrabar_portfolio_strategy(
        candles,
        wrapped,
        days=days,
        policy=policy,
        exchange_info_snapshot=exchange_info_snapshot,
        horizon_policy=horizon_policy,
        cost_profile=cost_profile,
        training_days=training_days,
        blindtest_days=blindtest_days,
        market_context=binding.context,
        closed_context_decision_provider=lambda index, decision_time_ms: (
            _evaluate_closed_bar_context_validated(
                binding,
                index,
                decision_time_ms=decision_time_ms,
            )
        ),
    )


def assert_context_identity_compatible(
    current: ContextParityBinding,
    persisted: ContextParityBinding,
) -> None:
    validate_context_parity_binding(current)
    validate_context_parity_binding(persisted)
    if current.context_identity_sha256 != persisted.context_identity_sha256:
        raise ContextParityError("context identity mismatch blocks cache/resume reuse")


def _context_candidate(
    strategy: StrategyCandidate,
    policy: ContextVetoPolicy,
) -> StrategyCandidate:
    if not isinstance(strategy, StrategyCandidate):
        raise TypeError("strategy must be StrategyCandidate")
    if str(strategy.params.get("symbol", TRADE_SYMBOL)) != TRADE_SYMBOL:
        raise ContextParityError("only ETHUSDC may enter the context parity engine")
    if strategy.family == "context_filter":
        observed = ContextVetoPolicy.from_candidate_params(strategy.params)
        if observed != policy:
            raise ContextParityError("candidate context policy differs from bound policy")
        return strategy
    return wrap_candidate_with_context(strategy, policy)


def _validate_trade_window(
    candles: Sequence[Candle], binding: ContextParityBinding
) -> None:
    if not candles:
        raise ContextParityError("context simulation requires non-empty ETHUSDC candles")
    try:
        validate_context_against_trade_candles(candles, binding.context)
    except DataLoadError as exc:
        raise ContextParityError(str(exc)) from exc
    for index, candle in enumerate(candles):
        evaluate_time = candle.open_time + EXPECTED_STEP_MS - 1
        expected = binding.context.ethusdc[index].open_time + EXPECTED_STEP_MS - 1
        if evaluate_time != expected:
            raise ContextParityError("trade and context closed-bar times differ")


def _validate_aligned_context(context: AlignedMarketCandles) -> None:
    try:
        validate_context_against_trade_candles(context.ethusdc, context)
    except DataLoadError as exc:
        raise ContextParityError(str(exc)) from exc
    for symbol, candles in _market_series(context):
        previous: int | None = None
        for candle in candles:
            if not isinstance(candle, Candle):
                raise ContextParityError(f"{symbol} context contains a non-candle value")
            if candle.open_time < 0 or candle.open_time % EXPECTED_STEP_MS:
                raise ContextParityError(f"{symbol} context is not on the UTC 1m grid")
            if previous is not None and candle.open_time - previous != EXPECTED_STEP_MS:
                raise ContextParityError(f"{symbol} context contains a stale or missing minute")
            values = (candle.open, candle.high, candle.low, candle.close, candle.volume)
            if any(not isfinite(float(value)) for value in values):
                raise ContextParityError(f"{symbol} context contains non-finite values")
            if min(candle.open, candle.high, candle.low, candle.close) <= 0:
                raise ContextParityError(f"{symbol} context prices must be positive")
            if candle.volume < 0:
                raise ContextParityError(f"{symbol} context volume must be non-negative")
            if candle.high < max(candle.open, candle.low, candle.close):
                raise ContextParityError(f"{symbol} context high is inconsistent")
            if candle.low > min(candle.open, candle.high, candle.close):
                raise ContextParityError(f"{symbol} context low is inconsistent")
            previous = candle.open_time


def _market_series(
    context: AlignedMarketCandles,
) -> tuple[tuple[str, tuple[Candle, ...]], ...]:
    return (
        ("ETHUSDC", context.ethusdc),
        ("BTCUSDC", context.btcusdc),
        ("ETHBTC", context.ethbtc),
    )


def _candles_sha256(candles: Sequence[Candle]) -> str:
    rows = [
        [
            candle.open_time,
            str(candle.open),
            str(candle.high),
            str(candle.low),
            str(candle.close),
            str(candle.volume),
        ]
        for candle in candles
    ]
    return _sha256_json(rows)


def _coerce_frozen_data_snapshot(
    snapshot: FrozenDataSnapshot | Mapping[str, Any],
) -> FrozenDataSnapshot:
    if isinstance(snapshot, FrozenDataSnapshot):
        return snapshot
    if not isinstance(snapshot, Mapping):
        raise ContextParityError("data snapshot must be a frozen snapshot object")
    raw = dict(snapshot)
    digest = raw.pop("snapshot_sha256", None)
    if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
        raise ContextParityError("data snapshot digest is missing or invalid")
    return FrozenDataSnapshot(_canonical_json(raw), digest)


def _snapshot_content_identity(
    snapshot_payload: Mapping[str, Any],
) -> tuple[str, tuple[tuple[str, str], ...]]:
    common_grid = snapshot_payload.get("common_minute_grid_sha256")
    if not isinstance(common_grid, str) or not _HEX64_RE.fullmatch(common_grid):
        raise ContextParityError("snapshot common grid digest is invalid")
    market_rows = snapshot_payload.get("market_data")
    if not isinstance(market_rows, list) or len(market_rows) != len(MARKETS):
        raise ContextParityError("snapshot market_data must contain three rows")
    market_digests: list[tuple[str, str]] = []
    for expected_symbol, row in zip(MARKETS, market_rows, strict=True):
        market = _require_mapping(row, f"market_data.{expected_symbol}")
        if market.get("symbol") != expected_symbol:
            raise ContextParityError("snapshot market ordering is invalid")
        digest = market.get("market_content_sha256")
        if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
            raise ContextParityError(
                f"snapshot market content digest is invalid for {expected_symbol}"
            )
        market_digests.append((expected_symbol, digest))
    return common_grid, tuple(market_digests)


def _validate_snapshot_window_provenance(
    context: AlignedMarketCandles,
    snapshot_payload: Mapping[str, Any],
) -> None:
    """Prove each exact full UTC context day against Task-5's v2 day index."""

    first = context.ethusdc[0].open_time
    end_exclusive = context.ethusdc[-1].open_time + EXPECTED_STEP_MS
    if first % _DAY_MS != 0 or end_exclusive % _DAY_MS != 0:
        raise ContextParityError(
            "context provenance requires complete midnight-to-midnight UTC days"
        )
    if context.candle_count % 1440 != 0:
        raise ContextParityError(
            "context provenance requires exactly 1,440 candles per UTC day"
        )
    day_count = context.candle_count // 1440
    first_day = datetime.fromtimestamp(first / 1000, tz=UTC).date()
    market_rows = snapshot_payload.get("market_data")
    if not isinstance(market_rows, list) or len(market_rows) != len(MARKETS):
        raise ContextParityError("snapshot market_data must contain three rows")

    for (symbol, candles), raw_market in zip(
        _market_series(context), market_rows, strict=True
    ):
        market = _require_mapping(raw_market, f"market_data.{symbol}")
        if market.get("symbol") != symbol:
            raise ContextParityError("snapshot market ordering is invalid")
        raw_index = market.get("utc_day_content_sha256")
        if not isinstance(raw_index, list):
            raise ContextParityError(
                f"Task-5 UTC-day content index is missing for {symbol}"
            )
        expected_by_day: dict[str, str] = {}
        for item in raw_index:
            row = _require_mapping(item, f"{symbol}.utc_day_content_sha256[]")
            day_text = row.get("day")
            digest = row.get("content_sha256")
            if (
                not isinstance(day_text, str)
                or not isinstance(digest, str)
                or not _HEX64_RE.fullmatch(digest)
            ):
                raise ContextParityError(
                    f"Task-5 UTC-day content index is invalid for {symbol}"
                )
            expected_by_day[day_text] = digest

        for day_offset in range(day_count):
            day = first_day + timedelta(days=day_offset)
            start = day_offset * 1440
            daily_candles = candles[start : start + 1440]
            try:
                observed = compute_utc_day_content_sha256(
                    symbol,
                    day,
                    daily_candles,
                )
            except DataSnapshotError as exc:
                raise ContextParityError(
                    f"context provenance is invalid for {symbol} {day.isoformat()}: {exc}"
                ) from exc
            if expected_by_day.get(day.isoformat()) != observed:
                raise ContextParityError(
                    f"context content is not proven by the Task-5 snapshot for "
                    f"{symbol} {day.isoformat()}"
                )


def _snapshot_parts(
    snapshot: FrozenDataSnapshot | Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    if isinstance(snapshot, FrozenDataSnapshot):
        return snapshot.payload(), snapshot.snapshot_sha256
    raw = dict(snapshot)
    digest = raw.pop("snapshot_sha256", None)
    if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
        raise ContextParityError("data snapshot digest is missing or invalid")
    return raw, digest


def _validate_path(path: str) -> None:
    if path not in CONTEXT_PATHS:
        raise ContextParityError(
            f"context path must be one of {CONTEXT_PATHS}; received {path!r}"
        )


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContextParityError(f"{label} must be an object")
    return value


def _utc_ms(value: Any, label: str) -> int:
    if not isinstance(value, str) or not value:
        raise ContextParityError(f"{label} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContextParityError(f"{label} is not a valid UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ContextParityError(f"{label} must be UTC")
    return int(parsed.timestamp() * 1000)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _normalize_json(value: Any) -> Any:
    return json.loads(_canonical_json(value))


__all__ = [
    "CONTEXT_PARITY_CONTRACT_PATH",
    "CONTEXT_PARITY_CONTRACT_SCHEMA",
    "CONTEXT_PARITY_CONTRACT_VERSION",
    "CONTEXT_PATHS",
    "ContextParityBinding",
    "ContextParityError",
    "assert_context_identity_compatible",
    "build_context_parity_binding",
    "evaluate_closed_bar_context",
    "load_context_parity_contract",
    "simulate_protocol_v3_context_path",
    "simulate_protocol_v3_context_portfolio_path",
    "validate_context_parity_binding",
    "validate_context_parity_contract",
]
