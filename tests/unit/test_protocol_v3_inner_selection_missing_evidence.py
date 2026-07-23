from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import importlib.util
from pathlib import Path

import pytest

from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3 import inner_selection as selection
from ethusdc_bot.protocol_v3 import inner_selection_api  # noqa: F401

_SUPPORT_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_task15_missing_evidence_support",
    _SUPPORT_PATH,
)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_incomplete_candidate_evidence_returns_typed_no_trade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    state = support.build_state(tmp_path, monkeypatch)
    evidence = selection.build_candidate_selection_evidence(
        StrategyCandidate("fixture", {"lookback": 10}),
        {"protocol": {"gate_frozen_before_evaluation": True}},
        state["training_window"],
    )
    candidate_id = evidence.canonical_candidate_id
    development = selection.build_synthetic_complete_development_support(
        tested_candidate_ids=[candidate_id],
        dsr_by_candidate={candidate_id: 0.99},
        matrix_evidence_sha256=_sha("matrix"),
        pbo_evidence_sha256=_sha("pbo"),
        dsr_evidence_sha256=_sha("dsr"),
        development_pbo=0.05,
    )
    config = selection.build_frozen_selection_config(
        pre_run_manifest=state["manifest"],
        run_fingerprint=state["fingerprint"],
        fold_identity=state["inner_fold_plan"].identity_payload,
        origin_index=1,
        cycle_index=1,
        generated_candidate_ids=[candidate_id],
        tested_candidate_ids=[candidate_id],
        walk_forward_candidate_ids=[candidate_id],
        finalist_candidate_ids=[candidate_id],
        candidate_evidence=[evidence],
        development_support=development,
    )
    decision = selection.select_candidate(state["training_window"], config)
    assert decision.outcome == selection.NO_TRADE
    assert decision.to_dict()["selected_candidate"] is None
    assert any(
        blocker.startswith(f"QUALITY_GATE_NOT_PASSED:{candidate_id}:")
        for blocker in decision.to_dict()["blockers"]
    )
    assert selection.validate_selection_decision(decision.to_dict()) == decision
