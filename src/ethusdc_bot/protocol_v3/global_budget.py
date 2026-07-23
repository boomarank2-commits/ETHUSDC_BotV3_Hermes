"""Combined Protocol v3 search-budget envelope.

The task-3 ``SearchBudgetPolicy`` deliberately models the twelve historical
monthly origins.  The blueprint additionally permits exactly one current
730-day refit with the same bounded inner loop.  This module combines both
parts without changing the already stable monthly-origin boundary contract.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any

from .boundaries import OUTER_ORIGINS
from .pipeline import PipelineContractError, SearchBudgetPolicy

CURRENT_REFIT_RUNS = 1
SELECTION_RUNS_TOTAL = OUTER_ORIGINS + CURRENT_REFIT_RUNS
MAX_CYCLES_PER_SELECTION_RUN = 8
GENERATED_PER_CYCLE = 40
TESTED_PER_CYCLE = 12
WALK_FORWARD_PER_CYCLE = 3
FINALISTS_PER_CYCLE = 2
MAX_TOTAL_CYCLES = 104
MAX_TOTAL_GENERATED = 4160
MAX_TOTAL_TESTED = 1248
MAX_TOTAL_WALK_FORWARD = 312
MAX_TOTAL_FINALISTS = 208
_REFIT_ID_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class GlobalSearchBudgetEnvelope:
    outer_origins: int = OUTER_ORIGINS
    current_refit_runs: int = CURRENT_REFIT_RUNS
    max_cycles_per_selection_run: int = MAX_CYCLES_PER_SELECTION_RUN
    generated_per_cycle: int = GENERATED_PER_CYCLE
    tested_per_cycle: int = TESTED_PER_CYCLE
    walk_forward_per_cycle: int = WALK_FORWARD_PER_CYCLE
    finalists_per_cycle: int = FINALISTS_PER_CYCLE
    max_total_cycles: int = MAX_TOTAL_CYCLES
    max_total_generated: int = MAX_TOTAL_GENERATED
    max_total_tested: int = MAX_TOTAL_TESTED
    max_total_walk_forward: int = MAX_TOTAL_WALK_FORWARD
    max_total_finalists: int = MAX_TOTAL_FINALISTS

    @property
    def selection_run_count(self) -> int:
        return self.outer_origins + self.current_refit_runs

    def to_dict(self) -> dict[str, int]:
        return {
            "outer_origins": self.outer_origins,
            "current_refit_runs": self.current_refit_runs,
            "max_cycles_per_selection_run": self.max_cycles_per_selection_run,
            "generated_per_cycle": self.generated_per_cycle,
            "tested_per_cycle": self.tested_per_cycle,
            "walk_forward_per_cycle": self.walk_forward_per_cycle,
            "finalists_per_cycle": self.finalists_per_cycle,
            "max_total_cycles": self.max_total_cycles,
            "max_total_generated": self.max_total_generated,
            "max_total_tested": self.max_total_tested,
            "max_total_walk_forward": self.max_total_walk_forward,
            "max_total_finalists": self.max_total_finalists,
        }

    def validate(self) -> None:
        expected = GlobalSearchBudgetEnvelope()
        if self.to_dict() != expected.to_dict():
            raise PipelineContractError(
                "global Protocol v3 budget must remain 12 origins plus one current refit with 8/40/12/3/2"
            )
        if self.selection_run_count != 13:
            raise PipelineContractError("Protocol v3 requires exactly thirteen bounded selection runs")
        if self.max_total_cycles != self.selection_run_count * self.max_cycles_per_selection_run:
            raise PipelineContractError("global cycle maximum is inconsistent")
        expected_totals = {
            "max_total_generated": self.max_total_cycles * self.generated_per_cycle,
            "max_total_tested": self.max_total_cycles * self.tested_per_cycle,
            "max_total_walk_forward": self.max_total_cycles * self.walk_forward_per_cycle,
            "max_total_finalists": self.max_total_cycles * self.finalists_per_cycle,
        }
        for field_name, expected_value in expected_totals.items():
            if getattr(self, field_name) != expected_value:
                raise PipelineContractError(f"{field_name} is inconsistent")
        process = SearchBudgetPolicy.canonical()
        process.validate()
        if (
            process.outer_origins != self.outer_origins
            or process.max_cycles_per_origin != self.max_cycles_per_selection_run
            or process.generated_per_cycle != self.generated_per_cycle
            or process.tested_per_cycle != self.tested_per_cycle
            or process.walk_forward_per_cycle != self.walk_forward_per_cycle
            or process.finalists_per_cycle != self.finalists_per_cycle
        ):
            raise PipelineContractError("global budget conflicts with the task-3 monthly-process budget")


@dataclass(frozen=True)
class GlobalBudgetUsage:
    cycles_by_origin: tuple[int, ...] = (0,) * OUTER_ORIGINS
    current_refit_cycles: int = 0
    current_refit_manifest_sha256: str | None = None
    current_refit_completed: bool = False
    reserved_generated: int = 0
    reserved_tested: int = 0
    reserved_walk_forward: int = 0
    reserved_finalists: int = 0

    @property
    def total_cycles(self) -> int:
        return sum(self.cycles_by_origin) + self.current_refit_cycles

    def reserve_origin_cycle(self, origin_index: int) -> "GlobalBudgetUsage":
        envelope = GlobalSearchBudgetEnvelope()
        envelope.validate()
        validate_global_budget_usage(self, envelope)
        _validate_index(origin_index, 1, envelope.outer_origins, "origin_index")
        offset = origin_index - 1
        if self.cycles_by_origin[offset] >= envelope.max_cycles_per_selection_run:
            raise PipelineContractError(f"origin {origin_index} exceeds the eight-cycle cap")
        cycles = list(self.cycles_by_origin)
        cycles[offset] += 1
        updated = _reserve(replace(self, cycles_by_origin=tuple(cycles)), envelope)
        validate_global_budget_usage(updated, envelope)
        return updated

    def start_current_refit(
        self,
        refit_manifest_sha256: str,
    ) -> "GlobalBudgetUsage":
        """Freeze the sole current-refit identity before reserving any cycle."""

        envelope = GlobalSearchBudgetEnvelope()
        envelope.validate()
        validate_global_budget_usage(self, envelope)
        normalized = _validate_refit_identity(refit_manifest_sha256)
        if self.current_refit_manifest_sha256 is None:
            updated = replace(self, current_refit_manifest_sha256=normalized)
            validate_global_budget_usage(updated, envelope)
            return updated
        if self.current_refit_manifest_sha256 != normalized:
            raise PipelineContractError("a second current refit is forbidden")
        if self.current_refit_completed:
            raise PipelineContractError("the sole current refit is already completed")
        return self

    def reserve_current_refit_cycle(
        self,
        refit_manifest_sha256: str,
    ) -> "GlobalBudgetUsage":
        envelope = GlobalSearchBudgetEnvelope()
        envelope.validate()
        validate_global_budget_usage(self, envelope)
        normalized = _validate_refit_identity(refit_manifest_sha256)
        if self.current_refit_manifest_sha256 is None:
            raise PipelineContractError("current refit must be started before reserving cycles")
        if self.current_refit_manifest_sha256 != normalized:
            raise PipelineContractError("a second current refit is forbidden")
        if self.current_refit_completed:
            raise PipelineContractError("current refit is already completed")
        if self.current_refit_cycles >= envelope.max_cycles_per_selection_run:
            raise PipelineContractError("current refit exceeds the eight-cycle cap")
        updated = _reserve(
            replace(self, current_refit_cycles=self.current_refit_cycles + 1),
            envelope,
        )
        validate_global_budget_usage(updated, envelope)
        return updated

    def complete_current_refit(
        self,
        refit_manifest_sha256: str,
    ) -> "GlobalBudgetUsage":
        envelope = GlobalSearchBudgetEnvelope()
        envelope.validate()
        validate_global_budget_usage(self, envelope)
        normalized = _validate_refit_identity(refit_manifest_sha256)
        if self.current_refit_manifest_sha256 is None:
            raise PipelineContractError("current refit must be started before completion")
        if self.current_refit_manifest_sha256 != normalized:
            raise PipelineContractError("a second current refit is forbidden")
        if self.current_refit_completed:
            raise PipelineContractError("current refit is already completed")
        updated = replace(self, current_refit_completed=True)
        validate_global_budget_usage(updated, envelope)
        return updated


def validate_global_budget_usage(
    usage: GlobalBudgetUsage,
    envelope: GlobalSearchBudgetEnvelope | None = None,
) -> None:
    active = envelope or GlobalSearchBudgetEnvelope()
    active.validate()
    if len(usage.cycles_by_origin) != active.outer_origins:
        raise PipelineContractError("global budget usage requires twelve origin counters")
    counters = (*usage.cycles_by_origin, usage.current_refit_cycles)
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > active.max_cycles_per_selection_run
        for value in counters
    ):
        raise PipelineContractError("selection-run cycle usage is invalid or above cap")
    if not isinstance(usage.current_refit_completed, bool):
        raise PipelineContractError("current refit completion state must be boolean")
    if usage.current_refit_manifest_sha256 is None:
        if usage.current_refit_cycles != 0 or usage.current_refit_completed:
            raise PipelineContractError(
                "current refit cycles or completion require a frozen refit identity"
            )
    else:
        _validate_refit_identity(usage.current_refit_manifest_sha256)
    if usage.total_cycles > active.max_total_cycles:
        raise PipelineContractError("global Protocol v3 cycle budget exceeded")
    expected = {
        "reserved_generated": usage.total_cycles * active.generated_per_cycle,
        "reserved_tested": usage.total_cycles * active.tested_per_cycle,
        "reserved_walk_forward": usage.total_cycles * active.walk_forward_per_cycle,
        "reserved_finalists": usage.total_cycles * active.finalists_per_cycle,
    }
    maxima = {
        "reserved_generated": active.max_total_generated,
        "reserved_tested": active.max_total_tested,
        "reserved_walk_forward": active.max_total_walk_forward,
        "reserved_finalists": active.max_total_finalists,
    }
    for field_name, expected_value in expected.items():
        actual = getattr(usage, field_name)
        if isinstance(actual, bool) or not isinstance(actual, int) or actual != expected_value:
            raise PipelineContractError(f"{field_name} does not match reserved cycles")
        if actual > maxima[field_name]:
            raise PipelineContractError(f"{field_name} exceeds its global maximum")


def _reserve(
    usage_with_incremented_cycle: GlobalBudgetUsage,
    envelope: GlobalSearchBudgetEnvelope,
) -> GlobalBudgetUsage:
    return replace(
        usage_with_incremented_cycle,
        reserved_generated=(
            usage_with_incremented_cycle.reserved_generated + envelope.generated_per_cycle
        ),
        reserved_tested=(
            usage_with_incremented_cycle.reserved_tested + envelope.tested_per_cycle
        ),
        reserved_walk_forward=(
            usage_with_incremented_cycle.reserved_walk_forward + envelope.walk_forward_per_cycle
        ),
        reserved_finalists=(
            usage_with_incremented_cycle.reserved_finalists + envelope.finalists_per_cycle
        ),
    )


def _validate_index(value: Any, minimum: int, maximum: int, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise PipelineContractError(
            f"{field_name} must be an integer from {minimum} through {maximum}"
        )


def _validate_refit_identity(value: Any) -> str:
    if not isinstance(value, str) or not _REFIT_ID_RE.fullmatch(value):
        raise PipelineContractError(
            "current refit identity must be a lowercase 64-character manifest SHA-256"
        )
    return value


__all__ = [
    "CURRENT_REFIT_RUNS",
    "FINALISTS_PER_CYCLE",
    "GENERATED_PER_CYCLE",
    "MAX_CYCLES_PER_SELECTION_RUN",
    "MAX_TOTAL_CYCLES",
    "MAX_TOTAL_FINALISTS",
    "MAX_TOTAL_GENERATED",
    "MAX_TOTAL_TESTED",
    "MAX_TOTAL_WALK_FORWARD",
    "SELECTION_RUNS_TOTAL",
    "TESTED_PER_CYCLE",
    "WALK_FORWARD_PER_CYCLE",
    "GlobalBudgetUsage",
    "GlobalSearchBudgetEnvelope",
    "validate_global_budget_usage",
]
