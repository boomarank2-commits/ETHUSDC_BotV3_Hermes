"""Fail-closed producer tests for the one-shot sealed holdout runner."""

from __future__ import annotations

from datetime import UTC, date, datetime
import json
from pathlib import Path
from statistics import median, pstdev
from types import SimpleNamespace

import pytest

import ethusdc_bot.backtest.sealed_holdout_runner as runner_module
from ethusdc_bot.backtest.data_loader import Candle
from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.quality_gates import evaluate_quality_gates
from ethusdc_bot.backtest.research_protocol import (
    CANDIDATE_STAGE_BUDGETS,
    build_research_protocol,
    safety_status,
)
from ethusdc_bot.backtest.sealed_holdout_runner import (
    SealedHoldoutAlreadyClaimedError,
    SealedHoldoutError,
    run_sealed_holdout,
)
from ethusdc_bot.shadow.adoption import (
    FINAL_REPORT_KEYS,
    assess_final_report,
    validate_final_evaluation_report,
)
from ethusdc_bot.shadow.schema import canonical_signature_payload


HOLDOUT_START = date(2029, 1, 1)
HOLDOUT_END = date(2029, 12, 31)


class _ExactCandleWindow:
    """Low-memory sequence representing all 525,600 sealed minute candles."""

    def __init__(self, *, offset_ms: int = 0):
        self.start_ms = int(
            datetime.combine(HOLDOUT_START, datetime.min.time(), tzinfo=UTC).timestamp()
            * 1000
        ) + offset_ms
        self.count = 365 * 1_440

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        if index < 0:
            index += self.count
        if index < 0 or index >= self.count:
            raise IndexError(index)
        return self._candle(index)

    def __iter__(self):
        for index in range(self.count):
            yield self._candle(index)

    def _candle(self, index: int) -> Candle:
        price = 2_000.0 + index / 1_000_000
        return Candle(
            open_time=self.start_ms + index * 60_000,
            open=price,
            high=price + 1.0,
            low=price - 1.0,
            close=price + 0.25,
            volume=1.0,
        )


def _passing_selection_evidence() -> dict[str, object]:
    fold_net_values = [0.50 + index * 0.02 for index in range(6)]
    folds = []
    for net_per_day in fold_net_values:
        net_profit = net_per_day * 91
        gross_loss = net_profit / 0.30
        gross_profit = gross_loss + net_profit
        folds.append(
            {
                "days": 91,
                "equity_curve_usdc": [0.0, net_profit + 12.0, net_profit],
                "metrics": {
                    "trade_count": 34,
                    "net_profit_usdc": net_profit,
                    "net_usdc_per_day": net_per_day,
                    "profit_factor": 1.30,
                    "gross_profit_usdc": gross_profit,
                    "gross_loss_usdc": gross_loss,
                    "max_drawdown_usdc": 12.0,
                    "drawdown_method": "mark_to_market",
                },
            }
        )
    fold_mean = sum(fold_net_values) / len(fold_net_values)
    return {
        "protocol": {
            "gate_version": "quality_gate_v1",
            "gate_frozen_before_evaluation": True,
            "selection_uses_audit": False,
        },
        "validation": {
            "trade_count": 60,
            "net_usdc_per_day": 0.60,
            "profit_factor": 1.25,
            "max_drawdown_usdc": 9.0,
            "drawdown_method": "mark_to_market",
        },
        "wfv": {
            "fold_count": 6,
            "folds": folds,
            "aggregate": {
                "trade_count": 204,
                "net_profit_usdc": sum(fold["metrics"]["net_profit_usdc"] for fold in folds),
                "net_usdc_per_day": sum(fold["metrics"]["net_profit_usdc"] for fold in folds)
                / sum(fold["days"] for fold in folds),
                "profit_factor": 1.30,
                "max_drawdown_usdc": 12.0,
                "drawdown_method": "mark_to_market",
                "positive_fold_count": 6,
                "folds_pf_at_least_1_05": 6,
                "worst_fold_profit_factor": 1.30,
                "median_fold_net_usdc_per_day": median(fold_net_values),
                "worst_fold_net_usdc_per_day": 0.50,
                "fold_net_coefficient_of_variation": pstdev(fold_net_values) / abs(fold_mean),
                "full_training_net_usdc_per_day": 0.80,
            },
        },
        "rolling": {
            "max_drawdown_usdc": 12.0,
            "drawdown_method": "mark_to_market",
            "max_underwater_days": 40,
            "top1_positive_pnl_share": 0.08,
            "top5_positive_pnl_share": 0.30,
            "net_without_top5_usdc": 10.0,
            "profit_factor_without_top5": 1.10,
        },
        "stress": {
            "baseline": {
                "fee_bps_per_side": 10.0,
                "slippage_bps_per_side": 5.0,
                "net_usdc_per_day": 3.20,
            },
            "joint": {
                "fee_bps_per_side": 15.0,
                "slippage_bps_per_side": 10.0,
                "net_usdc_per_day": 1.80,
                "profit_factor": 1.15,
                "max_drawdown_usdc": 18.0,
                "drawdown_method": "mark_to_market",
            },
            "slippage": {
                "fee_bps_per_side": 10.0,
                "slippage_bps_per_side": 15.0,
                "net_usdc_per_day": 1.20,
                "profit_factor": 1.08,
            },
            "friction_share_of_positive_pre_cost_pnl": 0.35,
        },
        "parameter_stability": {
            "all_numeric_parameters_perturbed": True,
            "numeric_parameter_count": 8,
            "neighbor_count": 16,
            "perturbation_fraction": 0.10,
            "session_hour_step": 1,
            "passing_neighbor_fraction": 0.85,
            "median_net_retention": 0.80,
            "worst_neighbor_net_usdc_per_day": 0.05,
        },
        "temporal": {
            "months_observed": 12,
            "positive_months": 10,
            "active_months": 12,
            "max_no_trade_gap_days": 20,
            "quarters_observed": 4,
            "positive_quarters": 4,
            "min_quarter_trade_count": 25,
            "worst_month_net_usdc": -2.0,
        },
        "regime": {
            "definition": "trend_sign_x_training_median_volatility",
            "threshold_source": "training_only",
            "assignment_uses_entry_time_trailing_data_only": True,
            "regime_count": 4,
            "min_trades_per_regime": 22,
            "positive_regime_count": 3,
            "regimes_pf_at_least_1_05": 3,
            "worst_regime_profit_factor": 0.95,
            "worst_regime_net_usdc": -3.0,
            "max_positive_pnl_share": 0.50,
        },
    }


def _source_signature(family: str, params: dict[str, object]) -> str:
    normalized = dict(params)
    normalized.setdefault("symbol", "ETHUSDC")
    return json.dumps(
        {"family": family, "params": normalized},
        sort_keys=True,
        separators=(",", ":"),
    )


def _research_report(raw_root: Path) -> dict[str, object]:
    loop_id = "research_loop_20260711T070000Z"
    family = "momentum_trend_filter"
    params = {
        "symbol": "ETHUSDC",
        "side": "LONG",
        "lookback": 60,
        "threshold_bps": 20,
    }
    signature = _source_signature(family, params)
    candidate = {
        "candidate_id": "momentum_final_001",
        "family": family,
        "params": params,
        "candidate_signature": signature,
    }
    evidence = _passing_selection_evidence()
    gate = evaluate_quality_gates(evidence, stage="selection").to_dict()
    assert gate["passed"] is True
    gate["candidate_id"] = candidate["candidate_id"]
    gate["candidate_signature"] = signature
    holdout = {
        "start": HOLDOUT_START.isoformat(),
        "end": HOLDOUT_END.isoformat(),
        "days": 365,
        "status": "sealed_unopened",
        "consumed_audit_window": False,
        "evaluated": False,
    }
    window_plan = {
        "latest_complete_utc_day": HOLDOUT_END.isoformat(),
        "available_complete_days": 1_095,
        "training_window": {
            "start": "2027-01-02",
            "end": "2028-12-31",
            "days": 730,
        },
        "final_holdout_window": holdout,
        "historical_origin_count": 3,
        "skipped_historical_origin_count": 0,
        "skipped_historical_origins": [],
        "historical_origins": [],
    }
    cycle = {
        "cycle_id": 1,
        "candidate_stage_ids": {
            "generated": [candidate["candidate_id"]],
            "tested": [candidate["candidate_id"]],
            "walk_forward": [candidate["candidate_id"]],
            "finalists": [candidate["candidate_id"]],
        },
        "selected_candidate": candidate,
        "selected_candidate_score": {
            "candidate_id": candidate["candidate_id"],
            "candidate_signature": signature,
            "ranking_rule": "quality_gate_then_wfv_aggregate_pf_drawdown_then_fold_tiebreakers",
            "quality_gate_passed": True,
            "wfv_net_usdc_per_day": 0.60,
            "wfv_profit_factor": 1.30,
            "wfv_max_drawdown_usdc": 12.0,
            "worst_fold_net_usdc_per_day": 0.50,
            "positive_fold_count": 6,
            "validation_net_usdc_per_day": 0.60,
            "wfv_cost_load": 25.0,
        },
        "quality_gate_evidence": evidence,
        "quality_gate": gate,
        "finalist_summaries": [
            {
                "candidate_id": candidate["candidate_id"],
                "family": family,
                "walk_forward_summary": {},
                "historical_replay_summary": {},
                "quality_gate_evidence": evidence,
                "quality_gate": gate,
            }
        ],
        "window_plan": window_plan,
        "safety": safety_status(),
    }
    protocol = build_research_protocol(
        raw_root=raw_root,
        git_commit="c2b65c8",
        run_id=loop_id,
        data_window=window_plan,
        parameter_space={"source": "generated_candidate_inventory", "cycles": []},
        candidate_stage_budgets=dict(CANDIDATE_STAGE_BUDGETS),
    )
    report = {
        "schema_version": 2,
        "loop_run_id": loop_id,
        "timestamp": "2026-07-11T07:00:00Z",
        "git_commit": "c2b65c8",
        "raw_root": str(raw_root),
        "execution_profile": "production_protocol",
        "fixture_data_only": False,
        "max_cycles": 8,
        "cycles_executed": 1,
        "stop_reason": "selection_stagnation_3_cycles",
        "target_reached": False,
        "target_status": "not_evaluated_no_sealed_holdout_run",
        "target_usdc_per_day": 3.0,
        "best_candidate": candidate,
        "best_validation_result": {},
        "frozen_candidate": candidate,
        "freeze_status": "frozen_for_separate_sealed_holdout",
        "candidate_stage_totals": {
            "generated": 40,
            "tested": 12,
            "walk_forward": 3,
            "finalists": 2,
        },
        "resource_budget": {},
        "loop_resource_budget": {},
        "cycles": [cycle],
        "window_plan": window_plan,
        "audit_policy": {
            "consumed_audit_window": False,
            "evaluated_in_research_loop": False,
            "affects_selection": False,
            "allowed_uses": ["historical_reference", "defect_analysis"],
            "freeze_eligible": True,
            "freeze_blocker": None,
        },
        "quality_gate_version": "quality_gate_v1",
        "research_protocol": protocol,
        "all_report_paths": {},
        "safety": safety_status(),
        "safety_status": "ok",
        "result_text": "Final holdout not evaluated.",
    }
    return report


def _write_source(path: Path, report: dict[str, object]) -> Path:
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _simulation(*, net_per_day=3.20, profit_factor=1.30):
    metrics = BacktestMetrics(
        net_profit_usdc=net_per_day * 365,
        net_usdc_per_day=net_per_day,
        trade_count=140,
        winrate=0.60,
        max_drawdown_usdc=12.0,
        profit_factor=profit_factor,
        average_trade_usdc=0.25,
        fees_usdc=28.0,
        slippage_usdc=14.0,
        training_days=0,
        blindtest_days=365,
    )
    return SimpleNamespace(metrics=metrics, drawdown_method="mark_to_market")


def test_exact_once_load_range_identity_and_green_final_schema(tmp_path, monkeypatch):
    raw_root = tmp_path / "external_raw"
    source_report = _research_report(raw_root)
    source_path = _write_source(tmp_path / "research.json", source_report)
    reports_root = tmp_path / "reports"
    candle_window = _ExactCandleWindow()
    loader_calls = []
    simulation_calls = []

    def loader(root, **kwargs):
        claims = list((reports_root / "sealed_holdout_registry").glob("*.json"))
        assert len(claims) == 1
        assert json.loads(claims[0].read_text(encoding="utf-8"))["status"] == "claimed"
        loader_calls.append((root, kwargs))
        return candle_window

    def simulator(candles, candidate, **kwargs):
        simulation_calls.append((candles, candidate, kwargs))
        return _simulation()

    monkeypatch.setattr(runner_module, "load_ethusdc_1m_candles", loader)
    monkeypatch.setattr(runner_module, "simulate_strategy", simulator)

    result = run_sealed_holdout(source_path, raw_root, reports_root)

    assert loader_calls == [
        (raw_root, {"start_day": HOLDOUT_START, "end_day": HOLDOUT_END})
    ]
    assert len(simulation_calls) == 1
    candles, candidate, kwargs = simulation_calls[0]
    assert candles is candle_window
    assert candidate.family == "momentum_trend_filter"
    assert candidate.params["symbol"] == "ETHUSDC"
    assert candidate.params["side"] == "LONG"
    assert kwargs == {
        "days": 365,
        "trade_usdc": 100.0,
        "fee_rate": 0.001,
        "slippage_bps": 5.0,
        "training_days": 0,
        "blindtest_days": 365,
    }
    final_report = json.loads(result.final_report_path.read_text(encoding="utf-8"))
    assert set(final_report) == FINAL_REPORT_KEYS
    assert final_report["candidate"]["candidate_signature"] == canonical_signature_payload(
        "momentum_trend_filter", final_report["candidate"]["params"]
    )
    assert final_report["quality_gate_evidence"]["final"] == {
        "sealed_holdout_evaluations": 1,
        "trade_count": 140,
        "net_usdc_per_day": 3.2,
        "profit_factor": 1.3,
        "average_trade_usdc": 0.25,
        "max_drawdown_usdc": 12.0,
        "drawdown_method": "mark_to_market",
    }
    copied_selection = dict(final_report["quality_gate_evidence"])
    copied_selection.pop("final")
    assert copied_selection == source_report["cycles"][0]["quality_gate_evidence"]
    validate_final_evaluation_report(final_report)
    assert assess_final_report(result.final_report_path).color == "green"
    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert registry["status"] == "completed"
    assert registry["source_report_sha256"] == result.source_report_sha256
    assert registry["claim_identity_sha256"] == result.claim_identity_sha256

    with pytest.raises(SealedHoldoutAlreadyClaimedError):
        run_sealed_holdout(source_path, raw_root, reports_root)
    assert len(loader_calls) == 1
    assert len(simulation_calls) == 1


def test_semantic_claim_blocks_reformatted_equivalent_source_before_load(tmp_path, monkeypatch):
    raw_root = tmp_path / "raw"
    source_report = _research_report(raw_root)
    source = _write_source(tmp_path / "source.json", source_report)
    reports_root = tmp_path / "reports"
    loads = []
    simulations = []

    monkeypatch.setattr(
        runner_module,
        "load_ethusdc_1m_candles",
        lambda *args, **kwargs: loads.append((args, kwargs)) or [],
    )
    monkeypatch.setattr(runner_module, "_validate_exact_candle_window", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runner_module,
        "simulate_strategy",
        lambda *args, **kwargs: simulations.append((args, kwargs)) or _simulation(),
    )

    first = run_sealed_holdout(source, raw_root, reports_root)
    first_source_sha = first.source_report_sha256
    source.write_text(
        json.dumps(source_report, separators=(",", ":"), sort_keys=False),
        encoding="utf-8",
    )
    assert runner_module.sha256(source.read_bytes()).hexdigest() != first_source_sha

    with pytest.raises(SealedHoldoutAlreadyClaimedError):
        run_sealed_holdout(source, raw_root, reports_root)

    assert len(loads) == 1
    assert len(simulations) == 1
    registry_files = list((reports_root / "sealed_holdout_registry").glob("*.json"))
    assert registry_files == [first.registry_path]


@pytest.mark.parametrize(
    ("net_per_day", "profit_factor", "expected_color"),
    [(2.50, 1.30, "yellow"), (2.50, 1.00, "red")],
)
def test_final_report_is_shadow_assessment_compatible_for_yellow_and_red(
    tmp_path, monkeypatch, net_per_day, profit_factor, expected_color
):
    raw_root = tmp_path / "raw"
    source = _write_source(tmp_path / "source.json", _research_report(raw_root))
    monkeypatch.setattr(runner_module, "load_ethusdc_1m_candles", lambda *args, **kwargs: [])
    monkeypatch.setattr(runner_module, "_validate_exact_candle_window", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runner_module,
        "simulate_strategy",
        lambda *args, **kwargs: _simulation(
            net_per_day=net_per_day, profit_factor=profit_factor
        ),
    )

    result = run_sealed_holdout(source, raw_root, tmp_path / "reports")

    assert assess_final_report(result.final_report_path).color == expected_color


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report.update(fixture_data_only=True),
        lambda report: report.update(freeze_status="blocked_by_quality_gates"),
        lambda report: report["window_plan"]["final_holdout_window"].update(
            consumed_audit_window=True
        ),
        lambda report: report["window_plan"]["final_holdout_window"].update(
            start="2025-08-01", end="2026-07-31"
        ),
        lambda report: report["frozen_candidate"].update(candidate_id="not_selected"),
        lambda report: report["cycles"][0]["quality_gate"].update(passed=False),
    ],
)
def test_invalid_or_unbound_source_blocks_before_candle_load(tmp_path, monkeypatch, mutation):
    raw_root = tmp_path / "raw"
    report = _research_report(raw_root)
    mutation(report)
    source = _write_source(tmp_path / "source.json", report)
    loads = []
    monkeypatch.setattr(
        runner_module,
        "load_ethusdc_1m_candles",
        lambda *args, **kwargs: loads.append((args, kwargs)),
    )

    with pytest.raises(SealedHoldoutError):
        run_sealed_holdout(source, raw_root, tmp_path / "reports")

    assert loads == []


def test_missing_source_blocks_before_candle_load(tmp_path, monkeypatch):
    loads = []
    monkeypatch.setattr(
        runner_module,
        "load_ethusdc_1m_candles",
        lambda *args, **kwargs: loads.append((args, kwargs)),
    )

    with pytest.raises(SealedHoldoutError):
        run_sealed_holdout(
            tmp_path / "missing.json", tmp_path / "raw", tmp_path / "reports"
        )

    assert loads == []


def test_out_of_range_candles_are_rejected_without_simulation(tmp_path, monkeypatch):
    raw_root = tmp_path / "raw"
    source = _write_source(tmp_path / "source.json", _research_report(raw_root))
    simulations = []
    monkeypatch.setattr(
        runner_module,
        "load_ethusdc_1m_candles",
        lambda *args, **kwargs: _ExactCandleWindow(offset_ms=60_000),
    )
    monkeypatch.setattr(
        runner_module,
        "simulate_strategy",
        lambda *args, **kwargs: simulations.append((args, kwargs)),
    )

    with pytest.raises(SealedHoldoutError, match="00:00 UTC"):
        run_sealed_holdout(source, raw_root, tmp_path / "reports")

    assert simulations == []


def test_crash_claim_survives_and_blocks_every_retry_before_load(tmp_path, monkeypatch):
    raw_root = tmp_path / "raw"
    source = _write_source(tmp_path / "source.json", _research_report(raw_root))
    loads = []
    simulations = []

    def loader(*args, **kwargs):
        loads.append((args, kwargs))
        return []

    def crash(*args, **kwargs):
        simulations.append((args, kwargs))
        raise RuntimeError("simulated crash after claim")

    monkeypatch.setattr(runner_module, "load_ethusdc_1m_candles", loader)
    monkeypatch.setattr(runner_module, "_validate_exact_candle_window", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner_module, "simulate_strategy", crash)

    with pytest.raises(RuntimeError, match="simulated crash"):
        run_sealed_holdout(source, raw_root, tmp_path / "reports")
    registry_files = list((tmp_path / "reports" / "sealed_holdout_registry").glob("*.json"))
    assert len(registry_files) == 1
    assert json.loads(registry_files[0].read_text(encoding="utf-8"))["status"] == "claimed"

    with pytest.raises(SealedHoldoutAlreadyClaimedError):
        run_sealed_holdout(source, raw_root, tmp_path / "reports")
    assert len(loads) == 1
    assert len(simulations) == 1
