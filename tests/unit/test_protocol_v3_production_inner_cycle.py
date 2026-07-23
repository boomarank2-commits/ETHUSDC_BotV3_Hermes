from __future__ import annotations

from datetime import timedelta
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3 import boundaries, inner_folds
from ethusdc_bot.protocol_v3 import production_inner_cycle as cycle_executor
from ethusdc_bot.protocol_v3 import production_inner_cycle_api
from ethusdc_bot.protocol_v3.runtime_state import HorizonPolicy
from ethusdc_bot.protocol_v3.trial_ledger import (
    import_canonical_historical_lower_bound,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMIT = "a" * 40
HORIZON = HorizonPolicy(10_080, 10_080, 2)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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

    def fake_dsr(*, pbo_evidence, selected_profile_id, trial_ledger):
        pbo = pbo_evidence.to_dict()
        digest = hashlib.sha256(selected_profile_id.encode()).hexdigest()
        return SimpleNamespace(
            to_dict=lambda: {
                "state": "COMPLETE",
                "evidence_sha256": digest,
                "pbo_evidence_sha256": pbo["evidence_sha256"],
                "matrix_sha256": pbo["matrix_identity"]["matrix_sha256"],
            }
        )

    def fake_support(evidence_by_candidate, *, cycle_index, trial_ledger):
        first = next(iter(evidence_by_candidate.values())).to_dict()
        return SimpleNamespace(
            to_dict=lambda: {
                "matrix": {
                    "state": "COMPLETE",
                    "evidence_sha256": first["matrix_sha256"],
                },
                "pbo": {
                    "state": "COMPLETE",
                    "evidence_sha256": first["pbo_evidence_sha256"],
                },
                "dsr": {"state": "COMPLETE"},
            }
        )

    monkeypatch.setattr(cycle_executor, "calculate_dsr", fake_dsr)
    monkeypatch.setattr(
        cycle_executor, "build_dsr_development_support", fake_support
    )
    return {
        "plan": plan,
        "ledger_root": ledger_root,
        "context": context,
    }


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


def test_public_api_and_real_cycle_evidence_chain(state) -> None:
    assert production_inner_cycle_api.__all__ == cycle_executor.__all__
    result = _run(state)
    payload = result.to_dict()
    assert payload["generated_candidate_count"] == 40
    assert payload["tested_candidate_count"] == 12
    assert len(payload["candidate_summaries"]) == 12
    assert len(payload["matrix"]["day_grid"]) == 360
    assert payload["pbo"]["state"] == "COMPLETE"
    assert len(payload["dsr_by_candidate"]) == 12
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
