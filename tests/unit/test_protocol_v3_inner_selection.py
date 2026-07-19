from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ethusdc_bot.backtest.quality_gates import QUALITY_GATE_V1
from ethusdc_bot.backtest.simulator import StrategyCandidate
from ethusdc_bot.protocol_v3 import inner_selection as selection
from ethusdc_bot.protocol_v3 import inner_selection_api
from ethusdc_bot.protocol_v3 import transactional_cache as tx

REPO_ROOT = Path(__file__).resolve().parents[2]
_SUPPORT_PATH = Path(__file__).with_name("protocol_v3_task13_support.py")
_SPEC = importlib.util.spec_from_file_location("protocol_v3_task15_support", _SUPPORT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
support = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(support)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _quality_evidence(fold_nets: list[float], *, joint_net: float = 0.2) -> dict:
    folds = []
    total_gross_profit = 0.0
    total_gross_loss = 0.0
    for value in fold_nets:
        net_profit = value * 60
        gross_loss = 10.0
        gross_profit = gross_loss + net_profit
        total_gross_profit += gross_profit
        total_gross_loss += gross_loss
        folds.append(
            {
                "days": 60,
                "metrics": {
                    "trade_count": 30,
                    "net_profit_usdc": net_profit,
                    "net_usdc_per_day": value,
                    "profit_factor": gross_profit / gross_loss,
                    "gross_profit_usdc": gross_profit,
                    "gross_loss_usdc": gross_loss,
                    "max_drawdown_usdc": 0.0,
                    "drawdown_method": "mark_to_market",
                },
                "equity_curve_usdc": [0.0, net_profit],
            }
        )
    mean = sum(fold_nets) / 6
    variance = sum((value - mean) ** 2 for value in fold_nets) / 6
    ordered = sorted(fold_nets)
    median = (ordered[2] + ordered[3]) / 2
    return {
        "protocol": {
            "gate_version": QUALITY_GATE_V1.version,
            "gate_frozen_before_evaluation": True,
            "selection_uses_audit": False,
        },
        "validation": {
            "trade_count": 60,
            "net_usdc_per_day": max(0.2, mean),
            "profit_factor": 1.5,
            "drawdown_method": "mark_to_market",
            "max_drawdown_usdc": 5.0,
        },
        "wfv": {
            "fold_count": 6,
            "folds": folds,
            "aggregate": {
                "trade_count": 180,
                "net_profit_usdc": sum(value * 60 for value in fold_nets),
                "net_usdc_per_day": mean,
                "profit_factor": total_gross_profit / total_gross_loss,
                "drawdown_method": "mark_to_market",
                "max_drawdown_usdc": 0.0,
                "positive_fold_count": sum(1 for value in fold_nets if value > 0),
                "folds_pf_at_least_1_05": 6,
                "worst_fold_profit_factor": min(row["metrics"]["profit_factor"] for row in folds),
                "median_fold_net_usdc_per_day": median,
                "worst_fold_net_usdc_per_day": min(fold_nets),
                "fold_net_coefficient_of_variation": variance**0.5 / abs(mean),
                "full_training_net_usdc_per_day": mean / 0.8,
            },
        },
        "rolling": {
            "drawdown_method": "mark_to_market",
            "max_drawdown_usdc": 5.0,
            "max_underwater_days": 10,
            "top1_positive_pnl_share": 0.05,
            "top5_positive_pnl_share": 0.20,
            "net_without_top5_usdc": 10.0,
            "profit_factor_without_top5": 1.2,
        },
        "stress": {
            "baseline": {
                "fee_bps_per_side": 10.0,
                "slippage_bps_per_side": 5.0,
                "net_usdc_per_day": mean,
            },
            "joint": {
                "fee_bps_per_side": 15.0,
                "slippage_bps_per_side": 10.0,
                "net_usdc_per_day": joint_net,
                "profit_factor": 1.2,
                "drawdown_method": "mark_to_market",
                "max_drawdown_usdc": 6.0,
            },
            "slippage": {
                "fee_bps_per_side": 10.0,
                "slippage_bps_per_side": 15.0,
                "net_usdc_per_day": max(0.1, joint_net),
                "profit_factor": 1.1,
            },
            "friction_share_of_positive_pre_cost_pnl": 0.2,
        },
        "parameter_stability": {
            "all_numeric_parameters_perturbed": True,
            "numeric_parameter_count": 1,
            "neighbor_count": 2,
            "perturbation_fraction": 0.10,
            "session_hour_step": 1,
            "passing_neighbor_fraction": 1.0,
            "median_net_retention": 0.9,
            "worst_neighbor_net_usdc_per_day": 0.0,
        },
        "temporal": {
            "months_observed": 12,
            "positive_months": 10,
            "active_months": 12,
            "max_no_trade_gap_days": 10,
            "quarters_observed": 4,
            "positive_quarters": 4,
            "min_quarter_trade_count": 20,
            "worst_month_net_usdc": 0.0,
        },
        "regime": {
            "definition": QUALITY_GATE_V1.regime_definition,
            "threshold_source": QUALITY_GATE_V1.regime_threshold_source,
            "assignment_uses_entry_time_trailing_data_only": True,
            "regime_count": 4,
            "min_trades_per_regime": 20,
            "positive_regime_count": 4,
            "regimes_pf_at_least_1_05": 4,
            "worst_regime_profit_factor": 1.0,
            "worst_regime_net_usdc": 0.0,
            "max_positive_pnl_share": 0.4,
        },
    }


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import ethusdc_bot.protocol_v3.reporting as reporting_module

    monkeypatch.setattr(
        reporting_module,
        "_utc_now",
        lambda: datetime(2026, 7, 16, tzinfo=UTC),
    )
    return support.build_state(tmp_path, monkeypatch)


def _candidate_rows(state, candidates_and_nets):
    return [
        selection.build_candidate_selection_evidence(
            candidate,
            _quality_evidence(nets, joint_net=joint),
            state["training_window"],
        )
        for candidate, nets, joint in candidates_and_nets
    ]


def _synthetic_config(state, rows, *, pbo=0.05, dsr=0.99):
    ids = [row.canonical_candidate_id for row in rows]
    development = selection.build_synthetic_complete_development_support(
        tested_candidate_ids=ids,
        dsr_by_candidate={candidate_id: dsr for candidate_id in ids},
        matrix_evidence_sha256=_sha("matrix"),
        pbo_evidence_sha256=_sha("pbo"),
        dsr_evidence_sha256=_sha("dsr"),
        development_pbo=pbo,
    )
    return selection.build_frozen_selection_config(
        pre_run_manifest=state["manifest"],
        run_fingerprint=state["fingerprint"],
        fold_identity=state["inner_fold_plan"].identity_payload,
        origin_index=1,
        cycle_index=1,
        generated_candidate_ids=list(reversed(ids)),
        tested_candidate_ids=ids,
        walk_forward_candidate_ids=list(reversed(ids)),
        finalist_candidate_ids=ids,
        candidate_evidence=list(reversed(rows)),
        development_support=development,
    )


def test_contract_api_pipeline_and_transaction_binding(state) -> None:
    contract = selection.load_inner_selection_contract(REPO_ROOT)
    assert contract["contract_version"] == selection.INNER_SELECTION_CONTRACT_VERSION
    assert inner_selection_api.__all__ == selection.__all__
    pipeline = json.loads(
        (REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text()
    )
    assert selection.INNER_SELECTION_CONTRACT_VERSION in pipeline["component_contracts"]["ranking"]
    for path in (
        "configs/protocol_v3_inner_selection_contract.json",
        "src/ethusdc_bot/protocol_v3/inner_selection.py",
        "src/ethusdc_bot/protocol_v3/inner_selection_api.py",
    ):
        assert path in pipeline["source_bindings"]["ranking"]
    transaction = tx.load_transaction_contract(REPO_ROOT)
    assert transaction["identity_policy"]["bound_candidate_selection_required"] is True
    candidate_slot = {
        row["name"]: row for row in state["identity"].to_dict()["identity_slots"]
    }[tx.CANDIDATE_SLOT]
    assert candidate_slot["state"] == tx.BOUND
    assert candidate_slot["payload"] == state["selection_decision"].candidate_identity_payload


def test_production_missing_tasks_16_to_18_is_typed_no_trade(state) -> None:
    decision = state["selection_decision"]
    assert decision.outcome == selection.NO_TRADE
    assert decision.fixture_only is False
    assert decision.to_dict()["selected_candidate"] is None
    assert decision.to_dict()["blockers"] == [
        "NO_FINALISTS",
        "TASK16_MATRIX_INSUFFICIENT_EVIDENCE",
        "TASK17_PBO_INSUFFICIENT_EVIDENCE",
        "TASK18_DSR_INSUFFICIENT_EVIDENCE",
    ]
    assert selection.validate_selection_decision(decision.to_dict()) == decision


def test_lexicographic_worst_fold_precedes_better_aggregate(state) -> None:
    rows = _candidate_rows(
        state,
        [
            (StrategyCandidate("fixture_family", {"lookback": 10}), [0.25] * 6, 0.15),
            (StrategyCandidate("fixture_family", {"lookback": 20}), [0.20, 0.50, 0.50, 0.50, 0.50, 0.50], 0.40),
        ],
    )
    decision = selection.select_candidate(
        state["training_window"], _synthetic_config(state, rows)
    )
    assert decision.outcome == selection.CANDIDATE
    assert decision.fixture_only is True
    assert decision.to_dict()["selected_candidate"]["canonical_candidate_id"] == rows[0].canonical_candidate_id


def test_free_parameter_count_then_candidate_id_break_ties(state) -> None:
    rows = _candidate_rows(
        state,
        [
            (StrategyCandidate("fixture_family", {"lookback": 10}), [0.25] * 6, 0.20),
            (StrategyCandidate("fixture_family", {"lookback": 10, "threshold": 2}), [0.25] * 6, 0.20),
        ],
    )
    decision = selection.select_candidate(
        state["training_window"], _synthetic_config(state, rows)
    )
    assert decision.to_dict()["selected_candidate"]["canonical_candidate_id"] == rows[0].canonical_candidate_id

    equal_rows = _candidate_rows(
        state,
        [
            (StrategyCandidate("fixture_a", {"lookback": 10}), [0.25] * 6, 0.20),
            (StrategyCandidate("fixture_b", {"lookback": 10}), [0.25] * 6, 0.20),
        ],
    )
    equal_decision = selection.select_candidate(
        state["training_window"], _synthetic_config(state, equal_rows)
    )
    assert equal_decision.to_dict()["selected_candidate"]["canonical_candidate_id"] == min(
        row.canonical_candidate_id for row in equal_rows
    )


def test_permuted_and_serialized_inputs_are_identical(state) -> None:
    rows = _candidate_rows(
        state,
        [
            (StrategyCandidate("fixture_a", {"lookback": 10}), [0.25] * 6, 0.20),
            (StrategyCandidate("fixture_b", {"lookback": 11}), [0.24] * 6, 0.21),
        ],
    )
    first = selection.select_candidate(
        state["training_window"], _synthetic_config(state, rows)
    )
    second = selection.select_candidate(
        json.loads(json.dumps(state["training_window"].to_dict())),
        json.loads(json.dumps(_synthetic_config(state, list(reversed(rows))).to_dict())),
    )
    assert first == second
    assert selection.validate_selection_decision(json.loads(json.dumps(first.to_dict()))) == first


def test_claimed_gate_pass_cannot_bypass_real_gate(state) -> None:
    bad = _quality_evidence([0.25] * 6)
    bad["validation"]["trade_count"] = 1
    bad["claimed_gate_passed"] = True
    row = selection.build_candidate_selection_evidence(
        StrategyCandidate("fixture_family", {"lookback": 10}),
        bad,
        state["training_window"],
    )
    decision = selection.select_candidate(
        state["training_window"], _synthetic_config(state, [row])
    )
    assert decision.outcome == selection.NO_TRADE
    assert any(
        "QUALITY_GATE_NOT_PASSED" in blocker
        for blocker in decision.to_dict()["blockers"]
    )


def test_target_outer_future_and_malformed_identity_fail_closed(state) -> None:
    spy = selection.SelectionTimestampSpy(state["training_window"])
    start_ms = int(state["training_window"].start_utc.timestamp() * 1000)
    end_ms = int(state["training_window"].end_utc.timestamp() * 1000)
    spy.observe_warmup_feature_read(start_ms - 1)
    spy.observe_training_read(end_ms - 1)
    with pytest.raises(selection.InnerSelectionError, match="outside"):
        spy.observe_training_read(end_ms)
    with pytest.raises(selection.InnerSelectionError, match="outer result"):
        spy.observe_outer_result(end_ms)

    evidence = _quality_evidence([0.25] * 6)
    evidence["target_usdc_per_day"] = 3.0
    with pytest.raises(selection.InnerSelectionError, match="forbidden"):
        selection.build_candidate_selection_evidence(
            StrategyCandidate("fixture", {"lookback": 10}),
            evidence,
            state["training_window"],
        )

    raw = deepcopy(state["selection_config"].to_dict())
    raw["run_fingerprint"]["context"]["runtime_binding"]["context_identity_sha256"] = "0" * 64
    with pytest.raises(Exception):
        selection.select_candidate(state["training_window"], raw)


def test_transaction_rejects_legacy_pending_and_fixture_candidate(state) -> None:
    legacy = tx.build_not_applicable_identity_slot(
        tx.CANDIDATE_SLOT,
        tx.CANDIDATE_PENDING_SCHEMA,
        "task15_not_implemented",
    )
    common = {
        "run_fingerprint": state["fingerprint"],
        "context_binding": state["binding"],
        "horizon_policy": support.HORIZON,
        "work_unit_id": "origin_01_cycle_01",
        "fold_identity": tx.build_bound_identity_slot(
            tx.FOLD_SLOT,
            tx.FOLD_IDENTITY_SCHEMA,
            state["inner_fold_plan"].identity_payload,
        ),
        "rotation_state_identity": tx.build_genesis_identity_slot(
            tx.ROTATION_SLOT,
            tx.ROTATION_GENESIS_SCHEMA,
            "no_rotation_state",
        ),
        "sealed_store_heads": tx.build_sealed_store_heads_slot(
            [state["index_path"]], state["repo"]
        ),
        "repository_root": state["repo"],
    }
    with pytest.raises(tx.ProtocolV3TransactionError, match="must be BOUND"):
        tx.build_transaction_identity(candidate_identity=legacy, **common)

    row = _candidate_rows(
        state,
        [(StrategyCandidate("fixture", {"lookback": 10}), [0.25] * 6, 0.20)],
    )[0]
    fixture_decision = selection.select_candidate(
        state["training_window"], _synthetic_config(state, [row])
    )
    with pytest.raises(tx.ProtocolV3TransactionError, match="synthetic"):
        tx.build_transaction_identity(
            candidate_identity=tx.build_bound_identity_slot(
                tx.CANDIDATE_SLOT,
                tx.CANDIDATE_SELECTION_IDENTITY_SCHEMA,
                fixture_decision.candidate_identity_payload,
            ),
            **common,
        )


def test_task15_core_modules_are_import_order_independent() -> None:
    assert selection._selection_basis.__module__ == selection.__name__
    assert inner_selection_api.select_candidate is selection.select_candidate

    code = (
        "from pathlib import Path;"
        "import ethusdc_bot.protocol_v3.transactional_cache_model as model;"
        f"contract=model.load_transaction_contract(Path(r'{REPO_ROOT}'));"
        "print(model.TRANSACTION_CONTRACT_VERSION);"
        "print(contract['contract_version'])"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-c", code],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    observed = result.stdout.strip().splitlines()
    assert observed == [
        tx.TRANSACTION_CONTRACT_VERSION,
        tx.TRANSACTION_CONTRACT_VERSION,
    ]
