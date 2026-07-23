from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3 import boundaries, inner_folds, inner_selection
from ethusdc_bot.protocol_v3 import production_inner_cycle as cycle_executor
from ethusdc_bot.protocol_v3 import production_inner_cycle_api
from ethusdc_bot.protocol_v3 import production_origin_selection
from ethusdc_bot.protocol_v3 import production_origin_selection_api
from ethusdc_bot.protocol_v3.candidate_matrix import (
    build_candidate_daily_matrix,
)
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy
from ethusdc_bot.protocol_v3.run_identity import build_run_fingerprint
from ethusdc_bot.protocol_v3.trial_ledger import (
    import_canonical_historical_lower_bound,
    read_trial_ledger,
    record_cache_reuse,
)
from protocol_v3_quality_support import complete_quality_evidence
from scripts.run_protocol_v3_production_inner_cycle import (
    _required_context_days,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40
HORIZON = HorizonPolicy(10_080, 10_080, 2)
_TASK13_SUPPORT_PATH = Path(__file__).with_name(
    "protocol_v3_task13_support.py"
)
_TASK13_SPEC = importlib.util.spec_from_file_location(
    "protocol_v3_production_cycle_task13_support",
    _TASK13_SUPPORT_PATH,
)
assert _TASK13_SPEC is not None and _TASK13_SPEC.loader is not None
task13_support = importlib.util.module_from_spec(_TASK13_SPEC)
_TASK13_SPEC.loader.exec_module(task13_support)


@pytest.fixture
def state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    production_identity,
):
    identity_state = production_identity
    origin = boundaries.build_monthly_process_boundary_plan(
        "2026-07-08"
    ).origins[0]
    plan = inner_folds.build_inner_fold_plan_for_origin(
        origin, HORIZON, repo_root=REPO_ROOT
    )
    ledger_root = tmp_path / "ledger"
    import_canonical_historical_lower_bound(ledger_root, REPO_ROOT)
    candle = Candle(0, 100.0, 101.0, 99.0, 100.0, 1.0)
    context = AlignedMarketCandles((candle,), (candle,), (candle,))

    def fake_evaluate(*, candidate, fold_plan, **kwargs):
        token = int(
            hashlib.sha256(candidate.family.encode()).hexdigest()[:8], 16
        )
        daily_value = ((token % 17) - 8) / 100.0
        folds = []
        for fold in fold_plan.folds:
            rows = [
                {
                    "day": (
                        fold.validation_start_inclusive_utc.date()
                        + timedelta(days=index)
                    ).isoformat(),
                    "net_usdc": daily_value,
                }
                for index in range(60)
            ]
            folds.append(
                {
                    "fold_index": fold.fold_index,
                    "fold_id": fold.fold_id,
                    "daily_net_mtm_usdc": rows,
                }
            )
        aggregate = {
            "validation_days": 360,
            "trade_count": 36,
            "net_profit_usdc": daily_value * 360,
            "net_usdc_per_day": daily_value,
            "fees_usdc": 1.0,
            "slippage_usdc": 0.5,
            "positive_fold_count": 6 if daily_value > 0 else 0,
        }
        return SimpleNamespace(
            candidate_matrix_folds=folds,
            evaluation_sha256=hashlib.sha256(
                repr((candidate.family, candidate.params)).encode()
            ).hexdigest(),
            to_dict=lambda: {"aggregate": aggregate},
        )

    monkeypatch.setattr(
        cycle_executor, "evaluate_candidate_on_inner_folds", fake_evaluate
    )
    monkeypatch.setattr(
        cycle_executor,
        "build_production_finalist_quality_evidence",
        lambda **kwargs: complete_quality_evidence(),
    )
    monkeypatch.setattr(
        cycle_executor,
        "validate_production_finalist_quality_evidence",
        lambda value: value,
    )

    def fake_batch(*, pbo_evidence, cycle_index, trial_ledger):
        pbo_payload = pbo_evidence.to_dict()
        cycle = pbo_payload["matrix_identity"]["matrix"]["cycles"][0]
        digest = hashlib.sha256(
            f"batch:{cycle_index}:{pbo_evidence.evidence_sha256}".encode()
        ).hexdigest()
        payload = {
            "pbo_identity": pbo_evidence.identity_payload,
            "cycle_index": cycle_index,
            "profiles": [
                {
                    "profile_id": row["profile_id"],
                    "candidate_id": row["candidate_id"],
                    "result": {
                        "state": "INSUFFICIENT_EVIDENCE",
                        "reason": "fixture_fast_batch",
                        "development_dsr": None,
                        "passed_minimum_dsr": False,
                    },
                    "profile_evidence_sha256": hashlib.sha256(
                        row["profile_id"].encode()
                    ).hexdigest(),
                }
                for row in cycle["profiles"]
            ],
            "shared_statistics": {
                "state": "INSUFFICIENT_EVIDENCE",
                "reason": "fixture_fast_batch",
            },
            "evidence_sha256": digest,
        }
        return SimpleNamespace(
            pbo=pbo_evidence,
            cycle_index=cycle_index,
            to_dict=lambda: payload,
        )

    def fake_validate_batch(value):
        if hasattr(value, "to_dict"):
            return value
        return SimpleNamespace(to_dict=lambda: dict(value))

    def fake_batch_support(batch, *, trial_ledger):
        return inner_selection.build_pbo_development_support(
            batch.pbo,
            cycle_index=batch.cycle_index,
        )

    monkeypatch.setattr(
        cycle_executor,
        "calculate_dsr_batch_evidence",
        fake_batch,
    )
    monkeypatch.setattr(
        cycle_executor,
        "validate_dsr_batch_evidence",
        fake_validate_batch,
    )
    monkeypatch.setattr(
        cycle_executor,
        "build_dsr_batch_development_support",
        fake_batch_support,
    )

    return {
        "plan": plan,
        "ledger_root": ledger_root,
        "context": context,
        "manifest": identity_state["manifest"],
        "fingerprint": identity_state["fingerprint"],
        "snapshot": identity_state["snapshot"],
        "exchange": identity_state["exchange"],
        "generation": identity_state["generation"],
        "binding": identity_state["binding"],
        "selection_decision": identity_state["selection_decision"],
    }


@pytest.fixture(scope="module")
def production_identity(tmp_path_factory: pytest.TempPathFactory):
    monkeypatch = pytest.MonkeyPatch()
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    identity_state = task13_support.build_state(
        tmp_path_factory.mktemp("production-identity"),
        monkeypatch,
    )
    monkeypatch.undo()
    return identity_state


def _run(state):
    return cycle_executor.execute_production_inner_cycle(
        repo_root=REPO_ROOT,
        context=state["context"],
        fold_plan=state["plan"],
        exchange_info_snapshot={},
        horizon_policy=HORIZON,
        trial_ledger_root=state["ledger_root"],
        origin_index=1,
        cycle_index=1,
        code_commit=COMMIT,
    )


def _run_cycle(state, cycle_index: int):
    return cycle_executor.execute_production_inner_cycle(
        repo_root=REPO_ROOT,
        context=state["context"],
        fold_plan=state["plan"],
        exchange_info_snapshot={},
        horizon_policy=HORIZON,
        trial_ledger_root=state["ledger_root"],
        origin_index=1,
        cycle_index=cycle_index,
        code_commit=COMMIT,
    )


def _current_fingerprint(state):
    return build_run_fingerprint(
        data_snapshot=state["snapshot"],
        exchange_info_snapshot=state["exchange"],
        pipeline_generation=state["generation"],
        context_binding=state["binding"],
        code_commit=COMMIT,
        trial_ledger=read_trial_ledger(state["ledger_root"]),
        repo_root=REPO_ROOT,
    )


def test_cli_loads_complete_730_day_development_context(state) -> None:
    start, end = _required_context_days(state["plan"])
    assert start == state["plan"].training_start_inclusive_utc.date()
    assert end == (
        state["plan"].training_end_exclusive_utc.date()
        - timedelta(days=1)
    )
    assert (end - start).days + 1 == 730


def test_public_api_and_real_cycle_evidence_chain(state) -> None:
    assert production_inner_cycle_api.__all__ == cycle_executor.__all__
    result = _run(state)
    payload = result.to_dict()
    assert payload["generated_candidate_count"] == 40
    assert payload["tested_candidate_count"] == 12
    assert len(payload["candidate_summaries"]) == 12
    assert len(payload["matrix"]["day_grid"]) == 360
    assert payload["pbo"]["state"] == "COMPLETE"
    assert len(payload["dsr_batch"]["profiles"]) == 12
    assert payload["development_support"]["matrix"]["state"] == "COMPLETE"
    assert payload["development_support"]["pbo"]["state"] == "COMPLETE"
    assert payload["safety"]["orders"] == "locked"
    assert cycle_executor.validate_production_inner_cycle_result(result) == result


def test_cycle_resume_uses_immutable_trials_without_reevaluation(
    state, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _run(state)
    monkeypatch.setattr(
        cycle_executor,
        "evaluate_candidate_on_inner_folds",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("resume must not reevaluate")
        ),
    )
    resumed = _run(state)
    assert all(
        row["resumed_from_permanent_trial"]
        for row in resumed.to_dict()["candidate_summaries"]
    )
    assert (
        resumed.to_dict()["matrix"]["content_sha256"]
        == first.to_dict()["matrix"]["content_sha256"]
    )


def test_cross_cycle_identical_attempts_are_cache_reuse(
    state, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _run_cycle(state, 1)
    monkeypatch.setattr(
        cycle_executor,
        "generate_search_space",
        lambda state, **kwargs: [
            StrategyCandidate(
                row["family"], row["parameters"]
            )
            for row in first.to_dict()["candidate_summaries"]
        ]
        + [
            StrategyCandidate(
                "breakout_volatility_filter",
                {"symbol": "ETHUSDC", "lookback": 10_000 + index},
            )
            for index in range(28)
        ],
    )
    monkeypatch.setattr(
        cycle_executor,
        "select_candidates_for_testing",
        lambda candidates, limit, **kwargs: candidates[:12],
    )
    monkeypatch.setattr(
        cycle_executor,
        "evaluate_candidate_on_inner_folds",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("cache reuse must not reevaluate")
        ),
    )
    reused = _run_cycle(state, 2)
    assert all(
        row["cache_reuse"]
        for row in reused.to_dict()["candidate_summaries"]
    )
    assert all(
        row["cache_reuse"]
        for row in reused.to_dict()["matrix"]["cycles"][0]["profiles"]
    )


def test_result_write_is_create_only(state, tmp_path: Path) -> None:
    result = _run(state)
    target = tmp_path / "cycle.json"
    assert cycle_executor.write_production_inner_cycle_result(
        result, target
    ) == target
    with pytest.raises(
        cycle_executor.ProductionInnerCycleError, match="create-only"
    ):
        cycle_executor.write_production_inner_cycle_result(result, target)


def test_recomputed_task15_decision_binds_real_cycle_quality_and_support(
    state,
) -> None:
    result = _run_cycle(state, 1).to_dict()
    decision = production_origin_selection._build_cycle_decision(
        result,
        plan=state["plan"],
        origin_index=1,
        support=result["development_support"],
        pre_run_manifest=state["manifest"],
        run_fingerprint=state["fingerprint"],
    )
    payload = decision.to_dict()
    assert payload["fixture_only"] is False
    assert payload["outcome"] == production_origin_selection.NO_TRADE
    assert payload["frozen_pipeline_config"][
        "candidate_evidence"
    ] == result["finalist_candidate_evidence"]
    assert payload["frozen_pipeline_config"][
        "development_support"
    ] == result["development_support"]


def test_task15_decision_archive_validates_from_cold_cache(state) -> None:
    payload = state["selection_decision"].to_dict()
    archive = production_origin_selection._archive_decision(1, payload)
    production_origin_selection._DECISION_BINDING_CACHE.clear()
    binding = production_origin_selection._read_decision_archive(
        archive,
        expected_cycle=1,
    )
    assert binding["decision_id"] == payload["decision_id"]
    assert binding["outcome"] == production_origin_selection.NO_TRADE
    assert binding["cycle_index"] == 1


def test_full_cross_cycle_origin_recomputes_96_profiles_and_task15(
    state,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    base = _run_cycle(state, 1).to_dict()
    base_cycle = base["matrix"]["cycles"][0]
    for cycle_index in range(2, 9):
        for profile in base_cycle["profiles"]:
            record_cache_reuse(
                state["ledger_root"],
                trial_id=profile["trial_id"],
                reuse_scope={
                    "origin_index": 1,
                    "cycle_index": cycle_index,
                },
            )
    ledger = read_trial_ledger(state["ledger_root"])
    current_fingerprint = _current_fingerprint(state)
    rows = []
    for cycle_index in range(1, 9):
        matrix = build_candidate_daily_matrix(
            fold_plan=state["plan"],
            origin_index=1,
            cycles=[
                {
                    "cycle_index": cycle_index,
                    "tested_candidate_ids": base_cycle[
                        "tested_candidate_ids"
                    ],
                    "promoted_candidate_ids": base_cycle[
                        "promoted_candidate_ids"
                    ],
                    "finalist_candidate_ids": base_cycle[
                        "finalist_candidate_ids"
                    ],
                    "profiles": [
                        {
                            "candidate_id": profile["candidate_id"],
                            "trial_id": profile["trial_id"],
                            "cache_reuse": cycle_index > 1,
                            "folds": [
                                {
                                    "fold_index": fold["fold_index"],
                                    "fold_id": fold["fold_id"],
                                    "daily_net_mtm_usdc": fold[
                                        "daily_net_mtm_usdc"
                                    ],
                                }
                                for fold in profile["folds"]
                            ],
                        }
                        for profile in base_cycle["profiles"]
                    ],
                }
            ],
            trial_ledger=ledger,
        )
        rows.append(
            {
                **base,
                "cycle_index": cycle_index,
                "matrix": matrix.to_dict(),
                "result_sha256": hashlib.sha256(
                    f"source:{cycle_index}".encode()
                ).hexdigest(),
            }
        )
    monkeypatch.setattr(
        production_origin_selection,
        "_validated_cycle_rows",
        lambda *args, **kwargs: rows,
    )

    def fake_batch(*, pbo_evidence, cycle_index, trial_ledger):
        cycle = pbo_evidence.to_dict()["matrix_identity"]["matrix"]["cycles"][
            cycle_index - 1
        ]
        return SimpleNamespace(
            pbo=pbo_evidence,
            cycle_index=cycle_index,
            to_dict=lambda: {
                "profiles": [
                    {
                        "profile_id": row["profile_id"],
                        "candidate_id": row["candidate_id"],
                        "result": {
                            "state": "INSUFFICIENT_EVIDENCE",
                            "reason": "fixture_compact",
                            "development_dsr": None,
                            "passed_minimum_dsr": False,
                        },
                        "profile_evidence_sha256": hashlib.sha256(
                            row["profile_id"].encode()
                        ).hexdigest(),
                    }
                    for row in cycle["profiles"]
                ],
                "shared_statistics": {
                    "state": "INSUFFICIENT_EVIDENCE",
                    "reason": "fixture_compact",
                },
            }
        )

    def fake_support(batch, *, trial_ledger):
        return inner_selection.build_pbo_development_support(
            batch.pbo,
            cycle_index=batch.cycle_index,
        )

    real_build_cycle_decision = (
        production_origin_selection._build_cycle_decision
    )

    def fake_decision(row, **kwargs):
        return real_build_cycle_decision(
            row,
            **{
                **kwargs,
                "run_fingerprint": current_fingerprint,
            },
        )

    monkeypatch.setattr(
        production_origin_selection,
        "calculate_dsr_batch_evidence",
        fake_batch,
    )
    monkeypatch.setattr(
        production_origin_selection,
        "build_dsr_batch_development_support",
        fake_support,
    )
    monkeypatch.setattr(
        production_origin_selection,
        "_build_cycle_decision",
        fake_decision,
    )
    result = production_origin_selection.build_production_origin_selection(
        repo_root=REPO_ROOT,
        fold_plan=state["plan"],
        trial_ledger=ledger,
        cycle_results=[],
        pre_run_manifest=state["manifest"],
        run_fingerprint=current_fingerprint,
        code_commit=COMMIT,
    )
    payload = result.to_dict()
    assert production_origin_selection_api.__all__ == (
        production_origin_selection.__all__
    )
    assert payload["matrix"]["profile_count"] == 96
    assert [row["cycle_index"] for row in payload["matrix"]["cycles"]] == list(
        range(1, 9)
    )
    assert len(payload["dsr_summaries"]) == 96
    assert payload["pbo_summary"]["matrix_sha256"] == payload["matrix"][
        "matrix_sha256"
    ]
    assert len(payload["cycle_decision_summaries"]) == 8
    assert len(payload["cycle_decision_archives"]) == 8
    assert len(payload["cycle_decision_bindings"]) == 8
    assert payload["state"] == production_origin_selection.NO_TRADE
    assert payload["outcome"] == production_origin_selection.NO_TRADE
    assert payload["selected_candidate"] is None
    assert payload["target_usdc_per_day_used_for_selection"] is False
    assert production_origin_selection.validate_production_origin_selection(
        result
    ) == result

    tampered = json.loads(json.dumps(payload))
    tampered["cycle_decision_archives"][0]["payload_base64"] = (
        "TAMPERED"
    )
    basis = dict(tampered)
    basis.pop("result_sha256")
    tampered["result_sha256"] = hashlib.sha256(
        json.dumps(
            basis,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    with pytest.raises(
        production_origin_selection.ProductionOriginSelectionError,
        match="full Task-15 decision archive is invalid",
    ):
        production_origin_selection.validate_production_origin_selection(
            tampered
        )

    target = tmp_path / "origin-selection.json"
    assert production_origin_selection.write_production_origin_selection(
        result, target
    ) == target
    with pytest.raises(
        production_origin_selection.ProductionOriginSelectionError,
        match="create-only",
    ):
        production_origin_selection.write_production_origin_selection(
            result, target
        )

def test_cross_cycle_origin_rejects_duplicate_or_missing_cycles(
    state,
) -> None:
    result = _run_cycle(state, 1)
    current_fingerprint = _current_fingerprint(state)
    with pytest.raises(
        production_origin_selection.ProductionOriginSelectionError,
        match="indexes must be exactly 1..8",
    ):
        production_origin_selection.build_production_origin_selection(
            repo_root=REPO_ROOT,
            fold_plan=state["plan"],
            trial_ledger=read_trial_ledger(state["ledger_root"]),
            cycle_results=[result] * 8,
            pre_run_manifest=state["manifest"],
            run_fingerprint=current_fingerprint,
            code_commit=COMMIT,
        )


def test_cross_cycle_origin_rejects_stale_run_fingerprint(state) -> None:
    result = _run_cycle(state, 1)
    with pytest.raises(
        production_origin_selection.ProductionOriginSelectionError,
        match="run fingerprint is stale",
    ):
        production_origin_selection.build_production_origin_selection(
            repo_root=REPO_ROOT,
            fold_plan=state["plan"],
            trial_ledger=read_trial_ledger(state["ledger_root"]),
            cycle_results=[result] * 8,
            pre_run_manifest=state["manifest"],
            run_fingerprint=state["fingerprint"],
            code_commit=COMMIT,
        )
