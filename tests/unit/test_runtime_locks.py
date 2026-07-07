"""Safety template tests for Phase 1 runtime locks."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_default_locks_template_keeps_live_locked():
    locks_path = ROOT / "runtime" / "default_locks.example.json"
    locks = json.loads(locks_path.read_text(encoding="utf-8"))

    assert locks["template"] is True
    assert locks["locks"]["live_trading"]["enabled"] is False
    assert locks["locks"]["paper_trading"]["enabled"] is False
    assert locks["locks"]["testtrade"]["enabled"] is False
    assert locks["locks"]["shorts_margin_futures_leverage"]["enabled"] is False


def test_default_runtime_state_template_is_not_current_truth():
    state_path = ROOT / "runtime" / "default_runtime_state.example.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))

    assert state["template"] is True
    assert state["live_status"] == "locked"
    assert state["paper_status"] == "locked"
    assert state["testtrade_status"] == "locked"
