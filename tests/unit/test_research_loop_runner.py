"""Tests for multi-cycle offline Research Protocol v2."""

import json

import pytest

import ethusdc_bot.backtest.research_loop_runner as loop_module
from ethusdc_bot.backtest.metrics import BacktestMetrics
from ethusdc_bot.backtest.quality_gates import evaluate_quality_gates
from ethusdc_bot.backtest.research_loop_runner import LoopConfig, run_research_loop
from ethusdc_bot.backtest.research_protocol import safety_status
from ethusdc_bot.backtest.simulator import StrategyCandidate


def _signature(params=None):
    normalized = dict(params or {})
    normalized.setdefault("symbol", "ETHUSDC")
    return json.dumps(
        {"family": "breakout_volatility_filter", "params": normalized},
        sort_keys=True,
        separators=(",", ":"),
    )


def _cycle(candidate_id: str, validation: float, safety=None):
    selected_id = f"{candidate_id}_a"
    signature = _signature()
    gate = evaluate_quality_gates({}, stage="selection").to_dict()
    gate["candidate_id"] = selected_id
    gate["candidate_signature"] = signature
    return {
        "cycle_id": 1,
        "generated_candidates": 2,
        "tested_candidates": 2,
        "walk_forward_candidates": 1,
        "finalists": 1,
        "candidate_stage_ids": {
            "generated": [f"{candidate_id}_a", f"{candidate_id}_b"],
            "tested": [f"{candidate_id}_a", f"{candidate_id}_b"],
            "walk_forward": [f"{candidate_id}_a"],
            "finalists": [f"{candidate_id}_a"],
        },
        "generated_candidate_inventory": [
            {
                "candidate_id": f"{candidate_id}_a",
                "family": "breakout_volatility_filter",
                "params": {},
                "candidate_signature": signature,
                "tested": True,
                "not_tested_reason": None,
            },
            {
                "candidate_id": f"{candidate_id}_b",
                "family": "breakout_volatility_filter",
                "params": {"lookback": 1},
                "candidate_signature": _signature({"lookback": 1}),
                "tested": True,
                "not_tested_reason": None,
            },
        ],
        "resource_budget": {
            "generated_cap": 4,
            "tested_cap": 2,
            "walk_forward_cap": 1,
            "finalists_cap": 1,
            "walk_forward_folds": 6,
            "rolling_origin_cap": 3,
            "selection_candidate_days_cap": 4015,
            "selection_candle_evaluations_cap": 5_781_600,
            "stress_evidence_candidate_days_cap": 1460,
            "parameter_evidence_candidate_days_cap": 5256,
            "selection_total_candidate_days_cap": 10731,
            "selection_total_candle_evaluations_cap": 15_452_640,
            "max_numeric_parameters_per_finalist": 18,
        },
        "selected_candidate": {
            "candidate_id": selected_id,
            "family": "breakout_volatility_filter",
            "params": {},
            "candidate_signature": signature,
        },
        "selected_candidate_score": {
            "candidate_id": selected_id,
            "candidate_signature": signature,
            "ranking_rule": "quality_gate_then_wfv_aggregate_pf_drawdown_then_fold_tiebreakers",
            "quality_gate_passed": False,
            "wfv_net_usdc_per_day": validation,
            "wfv_profit_factor": 1.2,
            "wfv_max_drawdown_usdc": 1.0,
            "worst_fold_net_usdc_per_day": validation,
            "positive_fold_count": 1,
            "validation_net_usdc_per_day": validation,
            "wfv_cost_load": 1.0,
        },
        "best_training_candidate": {"candidate_id": candidate_id},
        "best_validation_candidate": {"candidate_id": candidate_id, "net_usdc_per_day": validation},
        "best_validation_metrics": BacktestMetrics(validation, validation, 10, 0.5, 1, 1.2, validation / 10, 1, 1, 1, 1),
        "candidate_leaderboard_summary": [],
        "walk_forward_summaries": [],
        "family_aggregate_summary": [],
        "exit_reason_summary": {},
        "wfv_summary": {"ranking_uses_blindtest": False},
        "rolling_origin_summary": {"uses_final_audit": False, "origin_count": 0},
        "quality_gate": gate,
        "quality_gate_evidence": {},
        "finalist_summaries": [
            {
                "candidate_id": selected_id,
                "quality_gate_evidence": {},
                "quality_gate": gate,
            }
        ],
        "next_search_space_adjustment": "continue",
        "safety": safety or safety_status(),
    }


def _config(tmp_path, **overrides):
    values = {
        "raw_root": "C:/TradingBot/data/ETHUSDC_BotV3_Hermes",
        "reports_root": tmp_path,
        "max_cycles": 3,
        "max_candidates_per_cycle": 4,
        "tested_candidates_per_cycle": 2,
        "walk_forward_candidates_per_cycle": 1,
        "finalists_per_cycle": 1,
        "min_cycles": 3,
        "required_days": None,
    }
    values.update(overrides)
    return LoopConfig(**values)


def test_research_loop_runner_executes_multiple_cycles(tmp_path):
    calls = []

    def cycle_runner(cycle_index, state):
        calls.append(cycle_index)
        return _cycle(f"candidate_{cycle_index}", validation=-1.0 + cycle_index * 0.1)

    result = run_research_loop(_config(tmp_path), cycle_runner=cycle_runner)

    assert calls == [1, 2, 3]
    assert result.cycles_executed == 3
    assert result.stop_reason == "max_cycles_reached"
    assert result.report_paths.json_path.exists()


def test_research_loop_resumes_from_atomic_cycle_state(tmp_path):
    calls = []

    def interrupted_runner(cycle_index, state):
        calls.append(cycle_index)
        if cycle_index == 1:
            return _cycle("resume_1", validation=-0.9)
        raise RuntimeError("simulated reboot")

    config = _config(tmp_path, run_id="research_loop_resume_test")
    with pytest.raises(RuntimeError, match="simulated reboot"):
        run_research_loop(config, cycle_runner=interrupted_runner)
    resume_path = tmp_path / "research_loop_resume_test.resume.json"
    assert resume_path.is_file()
    assert (tmp_path / "research_loop_resume_test.cycle-01.json").is_file()

    def resumed_runner(cycle_index, state):
        calls.append(cycle_index)
        return _cycle(f"resume_{cycle_index}", validation=-0.8 + cycle_index * 0.1)

    result = run_research_loop(config, cycle_runner=resumed_runner)
    assert calls == [1, 2, 2, 3]
    assert result.cycles_executed == 3
    report = json.loads(result.report_paths.json_path.read_text(encoding="utf-8"))
    assert [cycle["cycle_id"] for cycle in report["cycles"]] == [1, 2, 3]
    assert report["resume_supported"] is True


def test_research_loop_never_claims_target_without_separate_frozen_holdout(tmp_path):
    result = run_research_loop(
        _config(tmp_path),
        cycle_runner=lambda cycle_index, state: _cycle(f"candidate_{cycle_index}", validation=9.0),
    )

    assert result.cycles_executed == 3
    assert result.stop_reason == "max_cycles_reached"
    assert result.target_reached is False


def test_research_loop_rejects_any_cycle_audit_payload(tmp_path):
    def poisoned_cycle(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=-1.0)
        cycle["blindtest_audit"] = {"net_usdc_per_day": 9999.0}
        return cycle

    with pytest.raises(ValueError, match="audit|blindtest|holdout"):
        run_research_loop(_config(tmp_path), cycle_runner=poisoned_cycle)


def test_research_loop_rejects_nested_audit_metrics(tmp_path):
    def poisoned_cycle(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=-1.0)
        cycle["candidate_leaderboard_summary"] = [{"blindtest_metrics": {"net_usdc_per_day": 9999.0}}]
        return cycle

    with pytest.raises(ValueError, match="audit|blindtest|holdout"):
        run_research_loop(_config(tmp_path), cycle_runner=poisoned_cycle)


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "blindtest_result",
        "audit_metrics",
        "holdout_performance",
        "blindtest_data",
        "holdout_evaluation",
        "blindtest_outcome",
        "audit_stats",
    ],
)
def test_research_loop_rejects_variant_audit_result_keys(tmp_path, forbidden_key):
    def poisoned_cycle(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=-1.0)
        cycle["diagnostic"] = {forbidden_key: {"net_usdc_per_day": 9999.0}}
        return cycle

    with pytest.raises(ValueError, match="audit|blindtest|holdout"):
        run_research_loop(_config(tmp_path), cycle_runner=poisoned_cycle)


def test_research_loop_rejects_inconsistent_candidate_stage_counts(tmp_path):
    def invalid_cycle(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=-1.0)
        cycle["finalists"] = 2
        return cycle

    with pytest.raises(ValueError, match="candidate stage"):
        run_research_loop(_config(tmp_path), cycle_runner=invalid_cycle)


def test_selected_candidate_identity_must_match_its_generated_inventory_row(tmp_path):
    def invalid_cycle(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=-1.0)
        cycle["selected_candidate"]["params"] = {"lookback": 999}
        cycle["selected_candidate"]["candidate_signature"] = _signature({"lookback": 999})
        cycle["selected_candidate_score"]["candidate_signature"] = _signature({"lookback": 999})
        return cycle

    with pytest.raises(ValueError, match="generated inventory"):
        run_research_loop(_config(tmp_path), cycle_runner=invalid_cycle)


def test_research_loop_stops_on_stagnation_after_three_non_improving_cycles(tmp_path):
    values = {1: 1.0, 2: 0.9, 3: 0.8, 4: 0.7}

    def cycle_runner(cycle_index, state):
        return _cycle(f"candidate_{cycle_index}", validation=values[cycle_index])

    result = run_research_loop(
        _config(tmp_path, max_cycles=8, stagnation_cycles=3),
        cycle_runner=cycle_runner,
    )

    assert result.cycles_executed == 4
    assert result.stop_reason == "selection_stagnation_3_cycles"


def test_loop_report_schema_v2_contains_honest_stages_and_consumed_audit_policy(tmp_path):
    result = run_research_loop(
        _config(tmp_path),
        cycle_runner=lambda cycle_index, state: _cycle(f"candidate_{cycle_index}", validation=-0.1),
    )

    data = json.loads(result.report_paths.json_path.read_text(encoding="utf-8"))

    assert data["schema_version"] == 2
    assert data["candidate_stage_totals"] == {
        "generated": 6,
        "tested": 6,
        "walk_forward": 3,
        "finalists": 3,
    }
    assert data["audit_policy"]["consumed_audit_window"] is True
    assert data["audit_policy"]["evaluated_in_research_loop"] is False
    assert data["audit_policy"]["affects_selection"] is False
    assert data["target_reached"] is False
    assert "best_blindtest_audit_result" not in data
    text = result.report_paths.txt_path.read_text(encoding="utf-8")
    assert "Holdout evaluated: False" in text
    assert "Live/Paper/Testtrade locked" in text


def test_loop_report_serializes_nonfinite_diagnostics_as_strict_json(tmp_path):
    def nonfinite_cycle(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=-0.1)
        cycle["diagnostic"] = {"profit_factor": float("inf")}
        return cycle

    result = run_research_loop(_config(tmp_path), cycle_runner=nonfinite_cycle)
    raw = result.report_paths.json_path.read_text(encoding="utf-8")

    assert "Infinity" not in raw
    assert json.loads(raw)["cycles"][0]["diagnostic"]["profit_factor"] == "inf"


def test_loop_report_recursively_serializes_nonfinite_metric_objects_as_strict_json(tmp_path):
    def nonfinite_cycle(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=-0.1)
        cycle["best_validation_metrics"] = BacktestMetrics(
            -0.1, -0.1, 1, 1.0, 0.0, float("inf"), -0.1, 0.1, 0.1, 1, 1
        )
        return cycle

    result = run_research_loop(_config(tmp_path), cycle_runner=nonfinite_cycle)
    raw = result.report_paths.json_path.read_text(encoding="utf-8")

    assert "Infinity" not in raw
    assert json.loads(raw)["cycles"][0]["best_validation_metrics"]["profit_factor"] == "inf"


def test_loop_stops_on_safety_violation(tmp_path):
    unsafe = {**safety_status(), "live": "unlocked"}
    config = _config(tmp_path, max_cycles=8, run_id="research_loop_unsafe")

    result = run_research_loop(
        config,
        cycle_runner=lambda cycle_index, state: _cycle(f"candidate_{cycle_index}", validation=-0.1, safety=unsafe),
    )

    assert result.stop_reason == "safety_violation"
    assert result.cycles_executed == 0
    assert not (tmp_path / "research_loop_unsafe.cycle-01.json").exists()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.pop("short_margin_futures_leverage"),
        lambda value: value.update(candidate_adoptable=True),
    ],
)
def test_loop_safety_requires_the_complete_canonical_contract(tmp_path, mutate):
    unsafe = safety_status()
    mutate(unsafe)

    result = run_research_loop(
        _config(tmp_path, max_cycles=8),
        cycle_runner=lambda cycle_index, state: _cycle(
            f"candidate_{cycle_index}", validation=-0.1, safety=unsafe
        ),
    )

    assert result.stop_reason == "safety_violation"
    assert result.cycles_executed == 0


def test_config_rejects_stage_caps_above_the_protocol_hard_caps(tmp_path):
    with pytest.raises(ValueError, match="hard cap"):
        _config(tmp_path, max_candidates_per_cycle=41)


def test_config_rejects_candidate_day_budget_above_the_protocol_hard_cap(tmp_path):
    with pytest.raises(ValueError, match="candidate-day hard cap"):
        _config(tmp_path, rolling_origin_limit=40)


def test_config_rejects_more_than_eight_research_cycles(tmp_path):
    with pytest.raises(ValueError, match="hard cap of 8"):
        _config(tmp_path, max_cycles=9)


def test_config_accepts_only_production_or_explicit_fixture_window_policy(tmp_path):
    with pytest.raises(ValueError, match="1095.*fixture"):
        _config(tmp_path, required_days=30)


def test_production_config_requires_exact_six_folds_and_canonical_origins(tmp_path):
    with pytest.raises(ValueError, match="exactly six"):
        LoopConfig(reports_root=tmp_path, walk_forward_fold_count=5)
    with pytest.raises(ValueError, match="three 365-day"):
        LoopConfig(reports_root=tmp_path, rolling_origin_limit=0)


def test_config_accepts_only_an_iso_data_end_day(tmp_path):
    config = LoopConfig(reports_root=tmp_path, data_end_day="2026-07-07")

    assert config.data_end_day == "2026-07-07"
    with pytest.raises(ValueError, match="ISO date"):
        LoopConfig(reports_root=tmp_path, data_end_day="07.07.2026")


def test_context_cycle_proof_binds_the_first_cycle_runtime_contract(tmp_path):
    context_ids = [f"context_{index}" for index in range(6)]
    base_ids = [f"base_{index}" for index in range(34)]
    cycle = {
        "cycle_id": 1,
        "generated_candidates": 40,
        "tested_candidates": 12,
        "walk_forward_candidates": 3,
        "finalists": 2,
        "context_research": {
            "enabled": True,
            "uses_audit_or_holdout": False,
        },
        "selection_source": "subtrain_validation_walk_forward_only",
        "candidate_stage_ids": {"tested": context_ids[:2] + base_ids[:10]},
        "generated_candidate_inventory": [
            {"candidate_id": candidate_id, "family": "context_filter"}
            for candidate_id in context_ids
        ]
        + [
            {"candidate_id": candidate_id, "family": "breakout_volatility_filter"}
            for candidate_id in base_ids
        ],
        "wfv_summary": {"fold_count": 6, "ranking_uses_blindtest": False},
        "rolling_origin_summary": {"uses_final_audit": False},
        "resource_budget": {"rolling_origin_cap": 3},
        "window_plan": {"final_holdout_window": {"evaluated": False}},
        "safety": safety_status(),
    }
    config = LoopConfig(
        reports_root=tmp_path,
        enable_context=True,
        data_end_day="2026-07-07",
    )

    proof = loop_module._context_cycle_proof(cycle, config)

    assert "context_research.enabled=true" in proof
    assert "context_generated=6 context_tested=2" in proof
    assert "walk_forward_folds=6 rolling_origin_limit=3" in proof
    assert "audit_evaluated=false final_holdout_evaluated=false" in proof

    cycle["context_research"]["uses_audit_or_holdout"] = True
    with pytest.raises(RuntimeError, match="audit-free selection"):
        loop_module._context_cycle_proof(cycle, config)


def test_custom_cycle_runner_cannot_create_a_production_report(tmp_path):
    with pytest.raises(ValueError, match="fixture/test-only"):
        run_research_loop(
            LoopConfig(reports_root=tmp_path, max_cycles=1, min_cycles=1),
            cycle_runner=lambda cycle_index, state: _cycle("forged", validation=99.0),
        )


def test_best_candidate_uses_the_selected_finalist_score_not_an_unrelated_validation_leader(tmp_path):
    def cycle_runner(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=float(cycle_index))
        cycle["best_validation_candidate"]["net_usdc_per_day"] = 100.0 if cycle_index == 1 else -100.0
        return cycle

    result = run_research_loop(
        _config(tmp_path, max_cycles=2, min_cycles=2),
        cycle_runner=cycle_runner,
    )

    assert result.best_candidate["candidate_id"] == "candidate_2_a"


def test_forged_unbound_passed_gate_is_rejected_before_freeze(tmp_path):
    def cycle_runner(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=1.0)
        cycle["quality_gate"] = {
            "schema_version": 1,
            "gate_version": "quality_gate_v1",
            "stage": "selection",
            "status": "pass",
            "passed": True,
            "missing_evidence": [],
            "invalid_evidence": [],
            "stage_readiness": {
                "research_evidence_complete": True,
                "sealed_holdout_ready": True,
                "candidate_adoption_ready": False,
                "live_ready": False,
            },
            "safety": {
                "candidate_adoptable": False,
                "live": "locked",
                "paper": "locked",
                "testtrade": "locked",
            },
            "checks": [{"passed": True}],
            "candidate_id": "different_candidate",
            "candidate_signature": "forged",
        }
        cycle["selected_candidate_score"]["quality_gate_passed"] = True
        return cycle

    with pytest.raises(ValueError, match="canonical re-evaluation"):
        run_research_loop(_config(tmp_path), cycle_runner=cycle_runner)


def test_bound_but_structurally_incomplete_passed_gate_is_rejected(tmp_path):
    def cycle_runner(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=1.0)
        selected = cycle["selected_candidate"]
        gate = {
            "schema_version": 1,
            "gate_version": "quality_gate_v1",
            "stage": "selection",
            "status": "pass",
            "passed": True,
            "missing_evidence": [],
            "invalid_evidence": [],
            "stage_readiness": {
                "research_evidence_complete": True,
                "sealed_holdout_ready": True,
                "candidate_adoption_ready": False,
                "live_ready": False,
            },
            "safety": {
                "candidate_adoptable": False,
                "live": "locked",
                "paper": "locked",
                "testtrade": "locked",
            },
            "checks": [{"code": "forged", "phase": "selection", "passed": True, "reason": "passed", "evidence_paths": ["fake"]}],
            "candidate_id": selected["candidate_id"],
            "candidate_signature": selected["candidate_signature"],
        }
        cycle["quality_gate"] = gate
        cycle["selected_candidate_score"]["quality_gate_passed"] = True
        cycle["finalist_summaries"] = [
            {"candidate_id": selected["candidate_id"], "quality_gate": gate}
        ]
        return cycle

    with pytest.raises(ValueError, match="canonical re-evaluation"):
        run_research_loop(_config(tmp_path), cycle_runner=cycle_runner)


def test_flipping_every_canonical_check_to_pass_cannot_forge_a_freeze(tmp_path):
    def cycle_runner(cycle_index, state):
        cycle = _cycle(f"candidate_{cycle_index}", validation=1.0)
        gate = cycle["quality_gate"]
        gate.update(
            {
                "status": "pass",
                "passed": True,
                "missing_evidence": [],
                "invalid_evidence": [],
                "stage_readiness": {
                    "research_evidence_complete": True,
                    "sealed_holdout_ready": True,
                    "candidate_adoption_ready": False,
                    "live_ready": False,
                },
            }
        )
        for check in gate["checks"]:
            check["passed"] = True
            check["reason"] = "passed"
        cycle["selected_candidate_score"]["quality_gate_passed"] = True
        return cycle

    with pytest.raises(ValueError, match="canonical re-evaluation"):
        run_research_loop(_config(tmp_path), cycle_runner=cycle_runner)


def test_context_symbols_cannot_trigger_trades():
    candidate = StrategyCandidate("context_filter", {"context_symbol": "BTCUSDC", "symbol": "ETHUSDC"})

    assert candidate.params["context_symbol"] == "BTCUSDC"
    assert candidate.params["symbol"] == "ETHUSDC"


def test_candidate_freeze_requires_exact_unconsumed_unevaluated_365_day_holdout(monkeypatch):
    monkeypatch.setattr(loop_module, "_quality_gate_freeze_eligible", lambda cycle: True)
    cycle = _cycle("candidate", validation=1.0)
    cycle["window_plan"] = {
        "final_holdout_window": {
            "status": "sealed_unopened",
            "consumed_audit_window": False,
            "evaluated": False,
            "days": 365,
        }
    }

    assert loop_module._select_frozen_candidate([cycle]) == cycle["selected_candidate"]

    for field, invalid in (
        ("status", "consumed"),
        ("consumed_audit_window", True),
        ("evaluated", True),
        ("days", 364),
    ):
        blocked = _cycle("candidate", validation=1.0)
        holdout = dict(cycle["window_plan"]["final_holdout_window"])
        holdout[field] = invalid
        blocked["window_plan"] = {"final_holdout_window": holdout}
        assert loop_module._select_frozen_candidate([blocked]) is None


def test_production_freeze_status_names_holdout_policy_blocker(tmp_path):
    config = LoopConfig(reports_root=tmp_path)
    consumed = {
        "status": "consumed",
        "consumed_audit_window": True,
        "evaluated": False,
        "days": 365,
    }

    assert loop_module._freeze_status(config, None, consumed) == "blocked_by_holdout_policy"
