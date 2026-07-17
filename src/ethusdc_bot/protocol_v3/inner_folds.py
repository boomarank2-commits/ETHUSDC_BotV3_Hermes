"""Exact Protocol v3 inner 6x60-day fold planning for Task 14.

The planner is pure calendar and leakage-boundary logic. It reuses the Task-2
730-day development boundary and Task-9 HorizonPolicy/purge primitives. It does
not select candidates, evaluate PnL, orchestrate outer origins, or trade.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from ethusdc_bot.protocol_v3.boundaries import (
    TRAINING_DAYS_PER_ORIGIN,
    MonthlyOriginBoundary,
)
from ethusdc_bot.protocol_v3.runtime_state import (
    HorizonPolicy,
    InformationInterval,
    PurgeResult,
    RuntimeStateError,
    purge_training_events,
)

INNER_FOLD_CONTRACT_PATH: Final = Path(
    "configs/protocol_v3_inner_fold_contract.json"
)
INNER_FOLD_CONTRACT_SCHEMA: Final = "protocol_v3_inner_fold_contract_v1"
INNER_FOLD_CONTRACT_VERSION: Final = (
    "protocol_v3_exact_inner_6x60_day_folds_v1"
)
INNER_FOLD_PLAN_SCHEMA: Final = "protocol_v3_inner_fold_plan_v1"
INNER_FOLD_IDENTITY_SCHEMA: Final = "protocol_v3_inner_fold_identity_v1"
PROTOCOL_VERSION: Final = "3.0.0"
FOLD_COUNT: Final = 6
VALIDATION_DAYS_PER_FOLD: Final = 60
VALIDATION_UNION_DAYS: Final = 360
FIRST_FIT_DAYS_BEFORE_PURGE: Final = 370
FIT_GROWTH_DAYS_PER_FOLD: Final = 60

_SAFETY: Final = {
    "api_keys": "forbidden",
    "live": "locked",
    "orders": "locked",
    "paper": "locked",
    "testtrade": "locked",
    "trading_api": "forbidden",
}
_CANONICAL_CONTRACT: dict[str, Any] = {
    "schema_version": INNER_FOLD_CONTRACT_SCHEMA,
    "protocol_version": PROTOCOL_VERSION,
    "contract_version": INNER_FOLD_CONTRACT_VERSION,
    "plan_schema_version": INNER_FOLD_PLAN_SCHEMA,
    "identity_schema_version": INNER_FOLD_IDENTITY_SCHEMA,
    "calendar_policy": {
        "timezone": "UTC",
        "development_days": 730,
        "validation_fold_count": 6,
        "validation_days_per_fold": 60,
        "validation_union_days": 360,
        "first_fit_days_before_purge": 370,
        "fit_growth_days_per_fold": 60,
        "half_open_intervals": True,
        "validation_folds_strictly_chronological": True,
        "validation_folds_non_overlapping": True,
        "validation_union_is_last_360_development_days": True,
    },
    "formula_policy": {
        "fold_index_range": "0..5",
        "validation_start": "training_end-(6-k)*60d",
        "validation_end": "training_end-(5-k)*60d",
        "fit_start": "training_start",
        "fit_end": "validation_start-purge_duration",
    },
    "purge_policy": {
        "source": "Task-9 HorizonPolicy and purge_training_events",
        "formula": (
            "max(max_label_horizon_minutes,max_holding_period_minutes+"
            "pending_entry_latency_minutes)+execution_bar_minutes"
        ),
        "boundary_touch_purges": True,
        "signals_at_or_after_validation_start_forbidden": True,
        "fixed_maximum_purge_cutoff_required": True,
    },
    "leakage_policy": {
        "fit_access_must_be_before_fit_end": True,
        "validation_access_must_be_inside_fold": True,
        "feature_source_must_not_follow_decision": True,
        "warmup_before_training_start_feature_read_only": True,
        "validation_information_must_end_before_fold_end": True,
        "training_information_must_end_before_validation_start": True,
        "timestamp_spies_fail_closed": True,
    },
    "fold_runtime_policy": {
        "starts_flat": True,
        "pending_entry_at_start": "forbidden",
        "cooldown_at_start": "forbidden",
        "scaler_state_at_start": "forbidden",
        "runtime_model_state_at_start": "forbidden",
        "fold_end_uses_task9_finalization": True,
    },
    "deferred_scope": {
        "candidate_selector_task": 15,
        "candidate_daily_matrix_task": 16,
        "pbo_task": 17,
        "outer_orchestration_task": 23,
    },
    "safety": _SAFETY,
}


class InnerFoldPlanError(ValueError):
    """Raised when an inner fold boundary or timestamp would leak."""


@dataclass(frozen=True)
class InnerFoldBoundary:
    fold_index: int
    fold_id: str
    fit_start_inclusive_utc: datetime
    fit_end_exclusive_utc: datetime
    validation_start_inclusive_utc: datetime
    validation_end_exclusive_utc: datetime
    purge_duration_minutes: int

    @property
    def fit_start_ms(self) -> int:
        return _timestamp_ms(self.fit_start_inclusive_utc)

    @property
    def fit_end_ms(self) -> int:
        return _timestamp_ms(self.fit_end_exclusive_utc)

    @property
    def validation_start_ms(self) -> int:
        return _timestamp_ms(self.validation_start_inclusive_utc)

    @property
    def validation_end_ms(self) -> int:
        return _timestamp_ms(self.validation_end_exclusive_utc)

    @property
    def pre_purge_fit_days(self) -> int:
        return (
            self.validation_start_inclusive_utc
            - self.fit_start_inclusive_utc
        ).days

    @property
    def validation_days(self) -> int:
        return (
            self.validation_end_exclusive_utc
            - self.validation_start_inclusive_utc
        ).days

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_index": self.fold_index,
            "fold_id": self.fold_id,
            "fit_start_inclusive_utc": _utc_text(
                self.fit_start_inclusive_utc
            ),
            "fit_end_exclusive_utc": _utc_text(
                self.fit_end_exclusive_utc
            ),
            "validation_start_inclusive_utc": _utc_text(
                self.validation_start_inclusive_utc
            ),
            "validation_end_exclusive_utc": _utc_text(
                self.validation_end_exclusive_utc
            ),
            "purge_duration_minutes": self.purge_duration_minutes,
            "pre_purge_fit_days": self.pre_purge_fit_days,
            "validation_days": self.validation_days,
        }


@dataclass(frozen=True)
class InnerFoldPlan:
    canonical_json: str
    plan_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)

    @property
    def plan_id(self) -> str:
        return f"protocol_v3_inner_fold_plan_sha256:{self.plan_sha256}"

    @property
    def folds(self) -> tuple[InnerFoldBoundary, ...]:
        return tuple(_fold_from_mapping(row) for row in self.to_dict()["folds"])

    @property
    def training_start_inclusive_utc(self) -> datetime:
        return _parse_utc(
            self.to_dict()["training_start_inclusive_utc"],
            "training_start_inclusive_utc",
        )

    @property
    def training_end_exclusive_utc(self) -> datetime:
        return _parse_utc(
            self.to_dict()["training_end_exclusive_utc"],
            "training_end_exclusive_utc",
        )

    @property
    def identity_payload(self) -> dict[str, Any]:
        return {
            "identity_schema_version": INNER_FOLD_IDENTITY_SCHEMA,
            "plan": self.to_dict(),
            "plan_sha256": self.plan_sha256,
            "plan_id": self.plan_id,
        }


class FoldTimestampSpy:
    """Fail-closed timestamp access guard used by fold consumers and tests."""

    _FIT_PURPOSES = {
        "fit_feature",
        "fit_label",
        "scaler_fit",
        "quantile_fit",
        "regime_fit",
        "feature_selection_fit",
    }
    _VALIDATION_PURPOSES = {
        "validation_signal",
        "validation_label",
        "validation_pnl",
        "validation_execution",
    }

    def __init__(self, fold: InnerFoldBoundary) -> None:
        self.fold = _validate_fold_boundary(fold)
        self._observations: list[dict[str, Any]] = []

    def observe(self, purpose: str, timestamp_ms: int) -> None:
        _nonnegative_int(timestamp_ms, "timestamp_ms")
        if purpose in self._FIT_PURPOSES:
            if not self.fold.fit_start_ms <= timestamp_ms < self.fold.fit_end_ms:
                raise InnerFoldPlanError(
                    f"{purpose} lies outside the fold fit interval"
                )
        elif purpose in self._VALIDATION_PURPOSES:
            if not (
                self.fold.validation_start_ms
                <= timestamp_ms
                < self.fold.validation_end_ms
            ):
                raise InnerFoldPlanError(
                    f"{purpose} lies outside the validation interval"
                )
        elif purpose == "warmup_feature_read":
            if timestamp_ms >= self.fold.fit_start_ms:
                raise InnerFoldPlanError(
                    "warmup_feature_read must be before fit_start"
                )
        else:
            raise InnerFoldPlanError(f"unsupported timestamp purpose: {purpose}")
        self._observations.append(
            {"purpose": purpose, "timestamp_ms": timestamp_ms}
        )

    def observe_feature_read(
        self,
        *,
        decision_time_ms: int,
        source_time_ms: int,
        decision_phase: str,
    ) -> None:
        _nonnegative_int(decision_time_ms, "decision_time_ms")
        _nonnegative_int(source_time_ms, "source_time_ms")
        if source_time_ms > decision_time_ms:
            raise InnerFoldPlanError(
                "feature source timestamp follows its decision timestamp"
            )
        purpose = (
            "fit_feature"
            if decision_phase == "fit"
            else "validation_signal"
            if decision_phase == "validation"
            else None
        )
        if purpose is None:
            raise InnerFoldPlanError(
                "decision_phase must be fit or validation"
            )
        self.observe(purpose, decision_time_ms)
        self._observations.append(
            {
                "purpose": "feature_source",
                "timestamp_ms": source_time_ms,
                "decision_time_ms": decision_time_ms,
                "decision_phase": decision_phase,
            }
        )

    def observe_validation_information_interval(
        self,
        interval: InformationInterval,
    ) -> None:
        if not isinstance(interval, InformationInterval):
            raise TypeError("interval must be InformationInterval")
        if not (
            self.fold.validation_start_ms
            <= interval.signal_time_ms
            < self.fold.validation_end_ms
        ):
            raise InnerFoldPlanError(
                "validation information signal lies outside the fold"
            )
        if interval.information_end_ms >= self.fold.validation_end_ms:
            raise InnerFoldPlanError(
                "validation information reaches or crosses fold end"
            )
        self._observations.append(
            {
                "purpose": "validation_information_interval",
                "event_id": interval.event_id,
                "signal_time_ms": interval.signal_time_ms,
                "information_end_ms": interval.information_end_ms,
            }
        )

    @property
    def observations(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(row) for row in self._observations)


def load_inner_fold_contract(
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
        else root / INNER_FOLD_CONTRACT_PATH
    )
    if not path.is_absolute():
        path = root / path
    try:
        value = _strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InnerFoldPlanError(
            f"inner fold contract is missing or invalid: {path}"
        ) from exc
    validate_inner_fold_contract(value)
    return value


def validate_inner_fold_contract(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or _normalize(value) != _CANONICAL_CONTRACT:
        raise InnerFoldPlanError(
            "Protocol v3 inner fold contract is not canonical"
        )


def build_inner_fold_plan(
    training_start_inclusive: date | datetime | str,
    training_end_exclusive: date | datetime | str,
    horizon_policy: HorizonPolicy,
    *,
    repo_root: str | Path | None = None,
) -> InnerFoldPlan:
    load_inner_fold_contract(repo_root)
    if not isinstance(horizon_policy, HorizonPolicy):
        raise InnerFoldPlanError(
            "horizon_policy must be a validated Task-9 HorizonPolicy"
        )
    start = _utc_midnight(
        training_start_inclusive,
        "training_start_inclusive",
    )
    end = _utc_midnight(training_end_exclusive, "training_end_exclusive")
    if end - start != timedelta(days=TRAINING_DAYS_PER_ORIGIN):
        raise InnerFoldPlanError(
            "inner fold development window must contain exactly 730 UTC days"
        )
    purge_minutes = horizon_policy.purge_duration_minutes
    folds: list[InnerFoldBoundary] = []
    for zero_index in range(FOLD_COUNT):
        validation_start = end - timedelta(
            days=(FOLD_COUNT - zero_index) * VALIDATION_DAYS_PER_FOLD
        )
        validation_end = end - timedelta(
            days=(FOLD_COUNT - 1 - zero_index)
            * VALIDATION_DAYS_PER_FOLD
        )
        folds.append(
            InnerFoldBoundary(
                fold_index=zero_index + 1,
                fold_id=f"inner_fold_{zero_index + 1:02d}",
                fit_start_inclusive_utc=start,
                fit_end_exclusive_utc=(
                    validation_start - timedelta(minutes=purge_minutes)
                ),
                validation_start_inclusive_utc=validation_start,
                validation_end_exclusive_utc=validation_end,
                purge_duration_minutes=purge_minutes,
            )
        )
    basis = {
        "schema_version": INNER_FOLD_PLAN_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "contract_version": INNER_FOLD_CONTRACT_VERSION,
        "training_start_inclusive_utc": _utc_text(start),
        "training_end_exclusive_utc": _utc_text(end),
        "development_days": TRAINING_DAYS_PER_ORIGIN,
        "validation_union_days": VALIDATION_UNION_DAYS,
        "horizon_policy": {
            **horizon_policy.basis(),
            "policy_sha256": horizon_policy.policy_sha256,
            "purge_duration_minutes": purge_minutes,
        },
        "folds": [fold.to_dict() for fold in folds],
        "safety": _SAFETY,
    }
    canonical = _canonical(basis)
    plan = InnerFoldPlan(
        canonical,
        hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )
    validate_inner_fold_plan(plan, repo_root=repo_root)
    return plan


def build_inner_fold_plan_for_origin(
    origin: MonthlyOriginBoundary,
    horizon_policy: HorizonPolicy,
    *,
    repo_root: str | Path | None = None,
) -> InnerFoldPlan:
    if not isinstance(origin, MonthlyOriginBoundary):
        raise TypeError("origin must be MonthlyOriginBoundary")
    if origin.training_day_count != TRAINING_DAYS_PER_ORIGIN:
        raise InnerFoldPlanError(
            "origin does not contain the canonical 730-day development window"
        )
    if origin.training_end_exclusive != origin.test_start_inclusive:
        raise InnerFoldPlanError(
            "origin development must end exactly at outer test start"
        )
    return build_inner_fold_plan(
        origin.training_start_inclusive,
        origin.training_end_exclusive,
        horizon_policy,
        repo_root=repo_root,
    )


def validate_inner_fold_plan(
    value: InnerFoldPlan | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> InnerFoldPlan:
    load_inner_fold_contract(repo_root)
    if isinstance(value, InnerFoldPlan):
        root = value.to_dict()
        observed_digest = value.plan_sha256
        observed_canonical = value.canonical_json
    elif isinstance(value, Mapping):
        raw = dict(value)
        observed_digest = raw.pop("plan_sha256", None)
        root = raw
        observed_canonical = _canonical(root)
    else:
        raise InnerFoldPlanError("inner fold plan must be an object")
    expected_keys = {
        "schema_version",
        "protocol_version",
        "contract_version",
        "training_start_inclusive_utc",
        "training_end_exclusive_utc",
        "development_days",
        "validation_union_days",
        "horizon_policy",
        "folds",
        "safety",
    }
    _exact_keys(root, expected_keys, "inner_fold_plan")
    _literal(root, "schema_version", INNER_FOLD_PLAN_SCHEMA)
    _literal(root, "protocol_version", PROTOCOL_VERSION)
    _literal(root, "contract_version", INNER_FOLD_CONTRACT_VERSION)
    start = _parse_utc(
        root["training_start_inclusive_utc"],
        "training_start_inclusive_utc",
    )
    end = _parse_utc(
        root["training_end_exclusive_utc"],
        "training_end_exclusive_utc",
    )
    if start.time() != datetime.min.time() or end.time() != datetime.min.time():
        raise InnerFoldPlanError(
            "development boundaries must be UTC midnight"
        )
    if end - start != timedelta(days=TRAINING_DAYS_PER_ORIGIN):
        raise InnerFoldPlanError(
            "inner fold plan development span is not 730 days"
        )
    if root["development_days"] != TRAINING_DAYS_PER_ORIGIN:
        raise InnerFoldPlanError("development_days is not canonical")
    if root["validation_union_days"] != VALIDATION_UNION_DAYS:
        raise InnerFoldPlanError("validation_union_days is not canonical")
    horizon = _validate_horizon_payload(root["horizon_policy"])
    folds_raw = root["folds"]
    if not isinstance(folds_raw, list) or len(folds_raw) != FOLD_COUNT:
        raise InnerFoldPlanError("inner fold plan must contain exactly six folds")
    folds = tuple(_fold_from_mapping(row) for row in folds_raw)
    purge_minutes = horizon.purge_duration_minutes
    for zero_index, fold in enumerate(folds):
        _validate_fold_boundary(fold)
        expected_validation_start = end - timedelta(
            days=(FOLD_COUNT - zero_index) * VALIDATION_DAYS_PER_FOLD
        )
        expected_validation_end = end - timedelta(
            days=(FOLD_COUNT - 1 - zero_index)
            * VALIDATION_DAYS_PER_FOLD
        )
        expected_pre_purge_days = (
            FIRST_FIT_DAYS_BEFORE_PURGE
            + zero_index * FIT_GROWTH_DAYS_PER_FOLD
        )
        if fold.fold_index != zero_index + 1:
            raise InnerFoldPlanError("fold indexes must be consecutive 1..6")
        if fold.fold_id != f"inner_fold_{zero_index + 1:02d}":
            raise InnerFoldPlanError("fold id is not canonical")
        if fold.fit_start_inclusive_utc != start:
            raise InnerFoldPlanError("fold fit_start differs from training_start")
        if fold.validation_start_inclusive_utc != expected_validation_start:
            raise InnerFoldPlanError("fold validation_start formula mismatch")
        if fold.validation_end_exclusive_utc != expected_validation_end:
            raise InnerFoldPlanError("fold validation_end formula mismatch")
        if fold.validation_days != VALIDATION_DAYS_PER_FOLD:
            raise InnerFoldPlanError("validation fold is not exactly 60 days")
        if fold.pre_purge_fit_days != expected_pre_purge_days:
            raise InnerFoldPlanError("expanding fit day count is not canonical")
        if fold.purge_duration_minutes != purge_minutes:
            raise InnerFoldPlanError("fold purge duration differs from policy")
        if fold.fit_end_exclusive_utc != (
            fold.validation_start_inclusive_utc
            - timedelta(minutes=purge_minutes)
        ):
            raise InnerFoldPlanError("fold fit_end purge formula mismatch")
        if fold.fit_end_exclusive_utc <= fold.fit_start_inclusive_utc:
            raise InnerFoldPlanError("purge removes the complete fit window")
        if zero_index and (
            folds[zero_index - 1].validation_end_exclusive_utc
            != fold.validation_start_inclusive_utc
        ):
            raise InnerFoldPlanError(
                "validation folds contain a gap or overlap"
            )
    if folds[0].validation_start_inclusive_utc != end - timedelta(
        days=VALIDATION_UNION_DAYS
    ):
        raise InnerFoldPlanError(
            "validation union is not the last 360 development days"
        )
    if folds[-1].validation_end_exclusive_utc != end:
        raise InnerFoldPlanError("last validation fold does not end at training_end")
    if root["safety"] != _SAFETY:
        raise InnerFoldPlanError("inner fold safety locks are invalid")
    _finite_json(root, "inner_fold_plan")
    canonical = _canonical(root)
    expected_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if observed_canonical != canonical:
        raise InnerFoldPlanError("inner fold plan is not canonical")
    if observed_digest != expected_digest:
        raise InnerFoldPlanError("inner fold plan digest mismatch")
    return InnerFoldPlan(canonical, expected_digest)


def validate_inner_fold_identity_payload(
    value: Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = dict(_mapping(value, "inner_fold_identity"))
    _exact_keys(
        root,
        {"identity_schema_version", "plan", "plan_sha256", "plan_id"},
        "inner_fold_identity",
    )
    _literal(
        root,
        "identity_schema_version",
        INNER_FOLD_IDENTITY_SCHEMA,
    )
    raw_plan = dict(_mapping(root["plan"], "inner_fold_identity.plan"))
    plan = validate_inner_fold_plan(
        {**raw_plan, "plan_sha256": root["plan_sha256"]},
        repo_root=repo_root,
    )
    if root["plan_id"] != plan.plan_id:
        raise InnerFoldPlanError("inner fold identity plan_id mismatch")
    normalized = plan.identity_payload
    if root != normalized:
        raise InnerFoldPlanError("inner fold identity payload is not canonical")
    return normalized


def purge_fold_training_events(
    plan: InnerFoldPlan | Mapping[str, Any],
    fold_index: int,
    events: Sequence[InformationInterval],
    *,
    repo_root: str | Path | None = None,
) -> PurgeResult:
    validated = validate_inner_fold_plan(plan, repo_root=repo_root)
    fold = _fold_at(validated, fold_index)
    try:
        task9 = purge_training_events(
            events,
            boundary_start_ms=fold.validation_start_ms,
        )
    except RuntimeStateError as exc:
        raise InnerFoldPlanError(str(exc)) from exc
    kept: list[InformationInterval] = []
    purged = list(task9.purged)
    for event in task9.kept:
        if event.signal_time_ms >= fold.fit_end_ms:
            purged.append(event)
        else:
            kept.append(event)
    kept.sort(key=lambda row: (row.signal_time_ms, row.event_id))
    purged.sort(key=lambda row: (row.signal_time_ms, row.event_id))
    if any(
        event.signal_time_ms >= fold.fit_end_ms
        or event.information_end_ms >= fold.validation_start_ms
        for event in kept
    ):
        raise InnerFoldPlanError("purge retained a boundary-leaking event")
    return PurgeResult(
        boundary_start_ms=fold.validation_start_ms,
        kept=tuple(kept),
        purged=tuple(purged),
    )


def _fold_at(plan: InnerFoldPlan, fold_index: int) -> InnerFoldBoundary:
    _positive_int(fold_index, "fold_index")
    if fold_index > FOLD_COUNT:
        raise InnerFoldPlanError("fold_index must be in 1..6")
    return plan.folds[fold_index - 1]


def _validate_horizon_payload(value: Any) -> HorizonPolicy:
    root = dict(_mapping(value, "horizon_policy"))
    _exact_keys(
        root,
        {
            "contract_version",
            "max_label_horizon_minutes",
            "max_holding_period_minutes",
            "pending_entry_latency_minutes",
            "execution_bar_minutes",
            "policy_sha256",
            "purge_duration_minutes",
        },
        "horizon_policy",
    )
    try:
        policy = HorizonPolicy(
            root["max_label_horizon_minutes"],
            root["max_holding_period_minutes"],
            root["pending_entry_latency_minutes"],
            root["execution_bar_minutes"],
        )
    except (TypeError, RuntimeStateError) as exc:
        raise InnerFoldPlanError("horizon policy is invalid") from exc
    expected = {
        **policy.basis(),
        "policy_sha256": policy.policy_sha256,
        "purge_duration_minutes": policy.purge_duration_minutes,
    }
    if root != expected:
        raise InnerFoldPlanError("horizon policy payload is not canonical")
    return policy


def _fold_from_mapping(value: Any) -> InnerFoldBoundary:
    root = dict(_mapping(value, "fold"))
    _exact_keys(
        root,
        {
            "fold_index",
            "fold_id",
            "fit_start_inclusive_utc",
            "fit_end_exclusive_utc",
            "validation_start_inclusive_utc",
            "validation_end_exclusive_utc",
            "purge_duration_minutes",
            "pre_purge_fit_days",
            "validation_days",
        },
        "fold",
    )
    fold = InnerFoldBoundary(
        fold_index=_positive_int(root["fold_index"], "fold.fold_index"),
        fold_id=_required_text(root["fold_id"], "fold.fold_id"),
        fit_start_inclusive_utc=_parse_utc(
            root["fit_start_inclusive_utc"],
            "fold.fit_start_inclusive_utc",
        ),
        fit_end_exclusive_utc=_parse_utc(
            root["fit_end_exclusive_utc"],
            "fold.fit_end_exclusive_utc",
        ),
        validation_start_inclusive_utc=_parse_utc(
            root["validation_start_inclusive_utc"],
            "fold.validation_start_inclusive_utc",
        ),
        validation_end_exclusive_utc=_parse_utc(
            root["validation_end_exclusive_utc"],
            "fold.validation_end_exclusive_utc",
        ),
        purge_duration_minutes=_positive_int(
            root["purge_duration_minutes"],
            "fold.purge_duration_minutes",
        ),
    )
    if root["pre_purge_fit_days"] != fold.pre_purge_fit_days:
        raise InnerFoldPlanError("fold pre_purge_fit_days is inconsistent")
    if root["validation_days"] != fold.validation_days:
        raise InnerFoldPlanError("fold validation_days is inconsistent")
    return _validate_fold_boundary(fold)


def _validate_fold_boundary(fold: InnerFoldBoundary) -> InnerFoldBoundary:
    if not isinstance(fold, InnerFoldBoundary):
        raise TypeError("fold must be InnerFoldBoundary")
    _positive_int(fold.fold_index, "fold.fold_index")
    _required_text(fold.fold_id, "fold.fold_id")
    _positive_int(fold.purge_duration_minutes, "fold.purge_duration_minutes")
    for name, value in (
        ("fit_start", fold.fit_start_inclusive_utc),
        ("fit_end", fold.fit_end_exclusive_utc),
        ("validation_start", fold.validation_start_inclusive_utc),
        ("validation_end", fold.validation_end_exclusive_utc),
    ):
        _require_utc(value, name)
    if not (
        fold.fit_start_inclusive_utc
        < fold.fit_end_exclusive_utc
        < fold.validation_start_inclusive_utc
        < fold.validation_end_exclusive_utc
    ):
        raise InnerFoldPlanError("fold timestamps are not strictly ordered")
    return fold


def _utc_midnight(value: date | datetime | str, path: str) -> datetime:
    if isinstance(value, datetime):
        parsed = _require_utc(value, path)
        if parsed.time() != datetime.min.time():
            raise InnerFoldPlanError(f"{path} must be UTC midnight")
        return parsed
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str):
        text = value.strip()
        try:
            if "T" in text:
                parsed = _parse_utc(text, path)
                if parsed.time() != datetime.min.time():
                    raise InnerFoldPlanError(f"{path} must be UTC midnight")
                return parsed
            day = date.fromisoformat(text)
        except ValueError as exc:
            raise InnerFoldPlanError(f"{path} is invalid") from exc
        return datetime(day.year, day.month, day.day, tzinfo=UTC)
    raise InnerFoldPlanError(f"{path} must be a date, UTC datetime, or ISO text")


def _parse_utc(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InnerFoldPlanError(f"{path} must be UTC and end in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InnerFoldPlanError(f"{path} is invalid") from exc
    return _require_utc(parsed, path)


def _require_utc(value: datetime, path: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InnerFoldPlanError(f"{path} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise InnerFoldPlanError(f"{path} must be UTC")
    return value.astimezone(UTC)


def _utc_text(value: datetime) -> str:
    return _require_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _timestamp_ms(value: datetime) -> int:
    return int(_require_utc(value, "timestamp").timestamp() * 1000)


def _strict_json_loads(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise InnerFoldPlanError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject(value: str) -> None:
        raise InnerFoldPlanError(f"non-finite JSON constant: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject)


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise InnerFoldPlanError(f"value is not strict JSON: {exc}") from exc


def _normalize(value: Any) -> Any:
    return json.loads(_canonical(value))


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InnerFoldPlanError(f"{path} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(value)
    extra = set(value) - expected
    if missing or extra:
        raise InnerFoldPlanError(
            f"{path} keys invalid; missing={sorted(missing)} extra={sorted(extra)}"
        )


def _literal(value: Mapping[str, Any], key: str, expected: Any) -> None:
    observed = value.get(key)
    if observed != expected or type(observed) is not type(expected):
        raise InnerFoldPlanError(f"{key} must equal {expected!r}")


def _required_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InnerFoldPlanError(f"{path} must be a non-empty string")
    return value.strip()


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InnerFoldPlanError(f"{path} must be a positive integer")
    return value


def _nonnegative_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InnerFoldPlanError(f"{path} must be a non-negative integer")
    return value


def _finite_json(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise InnerFoldPlanError(f"{path} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise InnerFoldPlanError(f"{path} contains a non-string key")
            _finite_json(item, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _finite_json(item, f"{path}[{index}]")
        return
    raise InnerFoldPlanError(f"{path} contains a non-JSON value")


__all__ = [
    "FIRST_FIT_DAYS_BEFORE_PURGE",
    "FIT_GROWTH_DAYS_PER_FOLD",
    "FOLD_COUNT",
    "INNER_FOLD_CONTRACT_PATH",
    "INNER_FOLD_CONTRACT_SCHEMA",
    "INNER_FOLD_CONTRACT_VERSION",
    "INNER_FOLD_IDENTITY_SCHEMA",
    "INNER_FOLD_PLAN_SCHEMA",
    "VALIDATION_DAYS_PER_FOLD",
    "VALIDATION_UNION_DAYS",
    "FoldTimestampSpy",
    "InnerFoldBoundary",
    "InnerFoldPlan",
    "InnerFoldPlanError",
    "build_inner_fold_plan",
    "build_inner_fold_plan_for_origin",
    "load_inner_fold_contract",
    "purge_fold_training_events",
    "validate_inner_fold_contract",
    "validate_inner_fold_identity_payload",
    "validate_inner_fold_plan",
]
