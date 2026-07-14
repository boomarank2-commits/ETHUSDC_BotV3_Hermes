"""Protocol v3 primitives that are implemented task by task.

Only modules whose numbered implementation task reached ``DONE_100`` may be
imported here as executable Protocol v3 behavior.
"""

from .boundaries import (
    ACTIVATION_DELAY_HOURS,
    DEPLOYMENT_ANCHOR_DAY_UTC,
    OUTER_ORIGINS,
    PROCESS_OOS_DAYS,
    TRAINING_DAYS_PER_ORIGIN,
    BoundaryValidationError,
    LateButtonResolution,
    MonthlyOriginBoundary,
    MonthlyProcessBoundaryPlan,
    build_monthly_process_boundary_plan,
    monthly_anchor,
    resolve_process_end_exclusive,
    resolve_target_anchor_for_button,
    validate_monthly_process_boundary_plan,
)

__all__ = [
    "ACTIVATION_DELAY_HOURS",
    "DEPLOYMENT_ANCHOR_DAY_UTC",
    "OUTER_ORIGINS",
    "PROCESS_OOS_DAYS",
    "TRAINING_DAYS_PER_ORIGIN",
    "BoundaryValidationError",
    "LateButtonResolution",
    "MonthlyOriginBoundary",
    "MonthlyProcessBoundaryPlan",
    "build_monthly_process_boundary_plan",
    "monthly_anchor",
    "resolve_process_end_exclusive",
    "resolve_target_anchor_for_button",
    "validate_monthly_process_boundary_plan",
]
