"""Regression tests for the one supported Windows dashboard entry point."""

from __future__ import annotations

from pathlib import Path


def _launcher_text() -> str:
    repository_root = Path(__file__).resolve().parents[2]
    return (repository_root / "START_DASHBOARD.bat").read_text(encoding="utf-8")


def test_start_dashboard_pins_its_own_source_tree_and_python_version() -> None:
    text = _launcher_text()

    assert 'cd /d "%~dp0"' in text
    assert 'set "PYTHONPATH=%~dp0src"' in text
    assert "py -3.12 -m ethusdc_bot.ui.dashboard" in text
    assert "python -m ethusdc_bot.ui.dashboard" not in text


def test_start_dashboard_rejects_detached_head_before_ui_launch() -> None:
    text = _launcher_text()

    assert "git branch --show-current" in text
    assert "if not defined HERMES_GIT_BRANCH" in text
    assert "detached HEAD" in text


def test_start_dashboard_uses_the_external_canonical_data_root() -> None:
    text = _launcher_text()

    assert (
        'set "HERMES_DATA_ROOT=C:\\TradingBot\\data\\ETHUSDC_BotV3_Hermes"'
        in text
    )
    assert "Data/report root: %HERMES_DATA_ROOT%" in text
