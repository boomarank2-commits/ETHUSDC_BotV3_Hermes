"""Dashboard start script safety tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_start_dashboard_script_exists():
    assert (ROOT / "START_DASHBOARD.bat").exists()


def test_start_dashboard_script_starts_dashboard_with_its_own_absolute_src_pythonpath():
    text = (ROOT / "START_DASHBOARD.bat").read_text(encoding="utf-8")

    assert 'set "PYTHONPATH=%~dp0src"' in text
    assert "py -3.12 -m ethusdc_bot.ui.dashboard" in text
    assert "PYTHONPATH=src" not in text


def test_start_dashboard_script_has_no_trading_starts():
    text = (ROOT / "START_DASHBOARD.bat").read_text(encoding="utf-8").lower()
    executable_lines = [line for line in text.splitlines() if line.strip() and not line.strip().startswith(("rem", "echo"))]
    executable_text = "\n".join(executable_lines)

    assert "live" not in executable_text
    assert "paper" not in executable_text
    assert "testtrade" not in executable_text
    assert "order" not in executable_text
    assert "api key" not in executable_text
    assert "binance_client" not in executable_text
