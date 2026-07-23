"""Regression tests for the stable Task-11 Protocol v3 report facade."""

from __future__ import annotations

import pytest

from ethusdc_bot.protocol_v3 import reporting
from ethusdc_bot.protocol_v3 import reporting_api


def test_public_reporting_api_exports_exact_validated_task11_surface() -> None:
    assert reporting_api.__all__ == reporting.__all__
    for name in reporting.__all__:
        assert getattr(reporting_api, name) is getattr(reporting, name)


def test_public_reporting_api_does_not_accept_unvalidated_report_objects() -> None:
    with pytest.raises(reporting_api.ProtocolV3ReportError, match="validated ProtocolV3Report"):
        reporting_api.write_protocol_v3_report(  # type: ignore[arg-type]
            {"artifact_kind": reporting_api.PROTOCOL_V3_RESEARCH},
            ".",
        )
