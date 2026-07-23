"""Task-29 compact checkpoint and deterministic replay regressions."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import pytest

import ethusdc_bot.protocol_v3.reporting as reporting_module

from ethusdc_bot.protocol_v3 import research_challenger
from ethusdc_bot.protocol_v3 import research_challenger_checkpoint as checkpointing
from ethusdc_bot.protocol_v3 import research_challenger_checkpoint_api
from ethusdc_bot.protocol_v3.pipeline import BudgetUsage

_TASK29_PATH = Path(__file__).with_name("test_protocol_v3_research_challenger.py")
_SPEC29 = importlib.util.spec_from_file_location(
    "protocol_v3_task29_checkpoint_support", _TASK29_PATH
)
assert _SPEC29 is not None and _SPEC29.loader is not None
task29 = importlib.util.module_from_spec(_SPEC29)
_SPEC29.loader.exec_module(task29)

_TASK13_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC13 = importlib.util.spec_from_file_location(
    "protocol_v3_task29_transaction_support", _TASK13_PATH
)
assert _SPEC13 is not None and _SPEC13.loader is not None
task13 = importlib.util.module_from_spec(_SPEC13)
_SPEC13.loader.exec_module(task13)


def _cash_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    report = task29.task28.state.__wrapped__(tmp_path / "task28", monkeypatch)[-1]
    started = datetime(2026, 7, 9, tzinfo=UTC)
    generation = task29._generation()
    state = research_challenger.start_research_challenger(
        report,
        started_at_utc=started,
        current_pipeline_generation=generation,
    )
    binding = task29._binding(int(started.timestamp() * 1000), count=3)
    monkeypatch.setattr(
        research_challenger, "validate_context_parity_binding", lambda value: None
    )
    monkeypatch.setattr(
        research_challenger, "evaluate_closed_bar_context", task29._allow_context
    )
    observed = datetime.fromtimestamp(
        (binding.common_watermark_open_time_ms + 59_999) / 1000,
        tz=UTC,
    )
    return research_challenger.advance_research_challenger(
        state,
        binding,
        observed_at_utc=observed,
        current_pipeline_generation=generation,
    ).state


def _receipt_for_task13_identity(identity):
    payload = identity.to_dict()
    run = payload["run_fingerprint"]
    slots = {row["name"]: row for row in payload["identity_slots"]}
    basis = {
        "schema_version": checkpointing.RECEIPT_SCHEMA_VERSION,
        "contract_version": checkpointing.RECEIPT_CONTRACT_VERSION,
        "research_state_sha256": "1" * 64,
        "task28_report_sha256": "2" * 64,
        "task28_bundle_sha256": "3" * 64,
        "selection_decision_sha256": slots["candidate_identity"]["payload"][
            "decision_sha256"
        ],
        "run_fingerprint_sha256": run["fingerprint_sha256"],
        "pipeline_generation_id": run["pipeline"]["generation_id"],
        "forward_ledger_namespace": run["pipeline"][
            "forward_ledger_namespace"
        ],
        "forward_ledger_head_sha256": checkpointing.ZERO_HASH,
        "forward_ledger_record_count": 0,
        "started_at_utc": "2026-07-09T00:00:00Z",
        "activation_open_time_ms": 1_752_019_200_000,
        "warmup_start_open_time_ms": 1_752_019_200_000,
        "last_engine_open_time_ms": None,
        "last_processed_open_time_ms": None,
        "mode": "CASH",
        "safety": checkpointing._SAFETY,
    }
    return checkpointing.validate_research_challenger_checkpoint_receipt(
        {**basis, "receipt_sha256": checkpointing._digest(basis)}
    )


def test_state_receipt_roundtrip_and_replay_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = _cash_state(tmp_path, monkeypatch)
    receipt = checkpointing.build_research_challenger_checkpoint_receipt(state)

    assert receipt.to_dict()["forward_ledger_record_count"] == 3
    assert receipt.to_dict()["forward_ledger_head_sha256"] == state.to_dict()[
        "forward_ledger"
    ]["head_sha256"]
    assert (
        checkpointing.verify_replayed_research_challenger_checkpoint(
            receipt,
            state,
        )
        == state
    )

    changed = deepcopy(receipt.to_dict())
    changed["forward_ledger_record_count"] += 1
    basis = dict(changed)
    basis.pop("receipt_sha256")
    changed["receipt_sha256"] = checkpointing._digest(basis)
    changed_receipt = checkpointing.validate_research_challenger_checkpoint_receipt(
        changed
    )
    with pytest.raises(
        research_challenger.ResearchChallengerError,
        match="replayed public-data state differs",
    ):
        checkpointing.verify_replayed_research_challenger_checkpoint(
            changed_receipt,
            state,
        )


def test_task13_atomically_stores_and_resumes_only_the_compact_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    built = task13.build_state(tmp_path, monkeypatch)
    receipt = _receipt_for_task13_identity(built["identity"])

    committed = checkpointing.commit_research_challenger_checkpoint(
        receipt,
        identity=built["identity"],
        pre_run_manifest=built["manifest"],
        seed_state=built["seed"],
        budget_usage=BudgetUsage(),
        stop_state=built["stop"],
        repository_root=built["repo"],
        trial_ledger_root=built["ledger_root"],
        owner_id="task29-checkpoint-test",
    )
    resumed = checkpointing.read_research_challenger_checkpoint(
        current_identity=built["identity"],
        current_pre_run_manifest=built["manifest"],
        repository_root=built["repo"],
    )

    assert resumed is not None
    assert resumed.receipt == receipt
    assert resumed.checkpoint == committed.checkpoint
    result_payload = resumed.checkpoint.to_dict()["result"]["payload"]
    assert set(result_payload) == {"task29_checkpoint_receipt"}
    receipt_payload = result_payload["task29_checkpoint_receipt"]
    assert receipt_payload["safety"]["raw_market_data_stored"] is False
    assert "candles" not in receipt_payload
    assert "ohlcv" not in receipt_payload
    assert "raw_market_data" not in receipt_payload


def test_checkpoint_identity_mismatch_is_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    built = task13.build_state(tmp_path, monkeypatch)
    receipt = _receipt_for_task13_identity(built["identity"])
    changed = deepcopy(receipt.to_dict())
    changed["pipeline_generation_id"] = "protocol_v3_generation_sha256:" + "a" * 64
    basis = dict(changed)
    basis.pop("receipt_sha256")
    changed["receipt_sha256"] = checkpointing._digest(basis)
    wrong = checkpointing.validate_research_challenger_checkpoint_receipt(changed)

    with pytest.raises(
        research_challenger.ResearchChallengerError,
        match="another pipeline generation",
    ):
        checkpointing.commit_research_challenger_checkpoint(
            wrong,
            identity=built["identity"],
            pre_run_manifest=built["manifest"],
            seed_state=built["seed"],
            budget_usage=BudgetUsage(),
            stop_state=built["stop"],
            repository_root=built["repo"],
            trial_ledger_root=built["ledger_root"],
            owner_id="task29-wrong-generation",
        )


def test_task29_checkpoint_api_is_exact() -> None:
    assert checkpointing.__all__ == research_challenger_checkpoint_api.__all__
