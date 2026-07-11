"""Integration guard for the disabled legacy backtest runner."""

from __future__ import annotations

import pytest

from ethusdc_bot.backtest.runner import run_backtest


def test_legacy_backtest_runner_is_disabled_before_loading_or_writing_data(tmp_path):
    raw_root = tmp_path / "raw_root"
    report_root = tmp_path / "reports"

    with pytest.raises(RuntimeError, match="disabled by Research Protocol v2"):
        run_backtest(raw_root=raw_root, reports_root=report_root, required_days=None)

    assert not raw_root.exists()
    assert not report_root.exists()
