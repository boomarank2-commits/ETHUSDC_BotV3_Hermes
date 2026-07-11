"""Public-data-only hypothetical execution support.

The shadow package contains no exchange account integration, credentials, or
order submission capability.
"""

from ethusdc_bot.shadow.adoption import (
    AdoptionAssessment,
    ShadowAdoptionError,
    adopt_for_shadow,
    assess_final_report,
)

__all__ = [
    "AdoptionAssessment",
    "ShadowAdoptionError",
    "adopt_for_shadow",
    "assess_final_report",
]
