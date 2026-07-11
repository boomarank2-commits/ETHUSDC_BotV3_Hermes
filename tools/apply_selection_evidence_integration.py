"""Integrate selection evidence producers into WFV and Research Protocol v2.

Every replacement is exact and fails if the source shape changed. The script is
one-shot tooling and is removed after the generated commit passes CI.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_exact(relative_path: str, old: str, new: str, *, count: int = 1) -> None:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found == 0 and new in text:
        print(f"already patched {relative_path}")
        return
    if found != count:
        raise RuntimeError(
            f"expected {count} source fragments in {relative_path}, found {found}"
        )
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print(f"patched {relative_path}")


def patch_selection_evidence() -> None:
    path = "src/ethusdc_bot/backtest/selection_evidence.py"
    replace_exact(
        path,
        '''    training_volatility = [\n        _trailing_state(training_candles, index, lookback_minutes)[1]\n        for index in range(1, len(training_candles))\n    ]\n    finite_training_volatility = [value for value in training_volatility if isfinite(value)]\n    volatility_threshold = median(finite_training_volatility) if finite_training_volatility else 0.0\n    times = [candle.open_time for candle in evaluation_candles]\n    rows: dict[str, list[float]] = {label: [] for label in REGIME_LABELS}\n    for trade in trades:\n        index = bisect_left(times, int(trade.entry_time))\n        trend, volatility = _trailing_state(evaluation_candles, index, lookback_minutes)\n''',
        '''    volatility_threshold = _training_volatility_threshold(\n        training_candles, lookback_minutes\n    )\n    evaluation_times = [candle.open_time for candle in evaluation_candles]\n    trailing_context = [\n        *training_candles[-lookback_minutes:],\n        *evaluation_candles,\n    ]\n    context_offset = min(lookback_minutes, len(training_candles))\n    rows: dict[str, list[float]] = {label: [] for label in REGIME_LABELS}\n    for trade in trades:\n        evaluation_index = bisect_left(evaluation_times, int(trade.entry_time))\n        trend, volatility = _trailing_state(\n            trailing_context, context_offset + evaluation_index, lookback_minutes\n        )\n''',
    )
    replace_exact(
        path,
        '''        positive = sum(value for value in values if value > 0)\n        regime_rows.append(\n            {\n                "regime": label,\n                "trade_count": len(values),\n                "net_profit_usdc": _round(sum(values)),\n                "profit_factor": _round(_finite_profit_factor(values)),\n                "positive_pnl_share": _round(positive / total_positive) if total_positive > 0 else 0.0,\n            }\n        )\n''',
        '''        positive = sum(value for value in values if value > 0)\n        negative = abs(sum(value for value in values if value < 0))\n        regime_rows.append(\n            {\n                "regime": label,\n                "trade_count": len(values),\n                "net_profit_usdc": _round(sum(values)),\n                "gross_profit_usdc": _round(positive),\n                "gross_loss_usdc": _round(negative),\n                "profit_factor": _round(_finite_profit_factor(values)),\n                "positive_pnl_share": _round(positive / total_positive) if total_positive > 0 else 0.0,\n            }\n        )\n''',
    )
    replace_exact(
        path,
        '''def run_parameter_stability(\n    candles: list[Candle],\n    candidate: StrategyCandidate,\n    *,\n    days: int,\n    gate: QualityGateV1 = QUALITY_GATE_V1,\n) -> dict[str, Any]:\n    """Evaluate all deterministic numeric neighbours on the same selection data."""\n\n    baseline = simulate_strategy(candles, candidate, days=days)\n''',
        '''def run_parameter_stability(\n    candles: list[Candle],\n    candidate: StrategyCandidate,\n    *,\n    days: int,\n    gate: QualityGateV1 = QUALITY_GATE_V1,\n    baseline_result: SimulationResult | None = None,\n    max_numeric_parameters: int = 12,\n) -> dict[str, Any]:\n    """Evaluate bounded deterministic numeric neighbours on selection data."""\n\n    if max_numeric_parameters <= 0:\n        raise ValueError("max_numeric_parameters must be positive")\n    baseline = baseline_result or simulate_strategy(candles, candidate, days=days)\n''',
    )
    replace_exact(
        path,
        '''    evaluations: list[NeighborEvaluation] = []\n    for parameter, direction, value, neighbor in neighbor_specs:\n''',
        '''    if numeric_count > max_numeric_parameters:\n        return {\n            "all_numeric_parameters_perturbed": False,\n            "numeric_parameter_count": numeric_count,\n            "neighbor_count": 0,\n            "perturbation_fraction": gate.parameter_perturbation_fraction,\n            "session_hour_step": gate.parameter_session_hour_step,\n            "passing_neighbor_fraction": 0.0,\n            "median_net_retention": 0.0,\n            "worst_neighbor_net_usdc_per_day": 0.0,\n            "baseline_net_usdc_per_day": baseline.net_usdc_per_day,\n            "neighbors": [],\n            "resource_limit_numeric_parameters": max_numeric_parameters,\n            "blocked_reason": "numeric_parameter_count_exceeds_resource_limit",\n            "uses_audit_or_holdout": False,\n        }\n    evaluations: list[NeighborEvaluation] = []\n    for parameter, direction, value, neighbor in neighbor_specs:\n''',
    )
    replace_exact(
        path,
        '''def _trailing_state(\n    candles: Sequence[Candle],\n''',
        '''def _training_volatility_threshold(\n    candles: Sequence[Candle], lookback: int\n) -> float:\n    if len(candles) < 2:\n        return 0.0\n    moves: list[float] = []\n    for index in range(1, len(candles)):\n        previous = float(candles[index - 1].close)\n        current = float(candles[index].close)\n        moves.append(abs(current / previous - 1) * 10_000 if previous else 0.0)\n    rolling_values: list[float] = []\n    rolling_sum = 0.0\n    for index, move in enumerate(moves):\n        rolling_sum += move\n        if index >= lookback:\n            rolling_sum -= moves[index - lookback]\n        width = min(index + 1, lookback)\n        rolling_values.append(rolling_sum / width)\n    finite_values = [value for value in rolling_values if isfinite(value)]\n    return median(finite_values) if finite_values else 0.0\n\n\ndef _trailing_state(\n    candles: Sequence[Candle],\n''',
    )


def patch_walk_forward() -> None:
    path = "src/ethusdc_bot/backtest/walk_forward.py"
    replace_exact(
        path,
        '''from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy\n''',
        '''from ethusdc_bot.backtest.simulator import StrategyCandidate, simulate_strategy\nfrom ethusdc_bot.backtest.walk_forward_evidence import (\n    FoldSelectionObservation,\n    build_walk_forward_selection_evidence,\n)\n''',
    )
    replace_exact(
        path,
        '''    max_candles_per_fold: int | None = None,\n    expected_candles_per_day: int | None = None,\n) -> dict[str, Any]:\n''',
        '''    max_candles_per_fold: int | None = None,\n    expected_candles_per_day: int | None = None,\n    fee_rate: float = 0.001,\n    slippage_bps: float = 5.0,\n    include_selection_evidence: bool = True,\n) -> dict[str, Any]:\n''',
        count=1,
    )
    replace_exact(
        path,
        '''    folds = build_walk_forward_folds(\n        training,\n''',
        '''    if fee_rate < 0 or slippage_bps < 0:\n        raise ValueError("fee_rate and slippage_bps must be non-negative")\n    folds = build_walk_forward_folds(\n        training,\n''',
        count=1,
    )
    replace_exact(
        path,
        '''    fold_equity_curves: list[tuple[EquityPoint, ...]] = []\n    simulated_days = 0\n''',
        '''    fold_equity_curves: list[tuple[EquityPoint, ...]] = []\n    selection_observations: list[FoldSelectionObservation] = []\n    simulated_days = 0\n''',
    )
    replace_exact(
        path,
        '''            blindtest_days=blindtest_days,\n        )\n        fold_metrics = result.metrics.to_dict()\n''',
        '''            blindtest_days=blindtest_days,\n            fee_rate=fee_rate,\n            slippage_bps=slippage_bps,\n        )\n        selection_observations.append(\n            FoldSelectionObservation(\n                fold_id=fold.fold_id,\n                training_candles=tuple(fold.train_window),\n                validation_candles=tuple(validation_window),\n                result=result,\n            )\n        )\n        fold_metrics = result.metrics.to_dict()\n''',
        count=1,
    )
    replace_exact(
        path,
        '''    return summarize_walk_forward(\n        fold_rows,\n        aggregate_metrics=aggregate,\n        aggregate_max_underwater_days=max_underwater_calendar_days(chained_equity),\n    )\n''',
        '''    summary = summarize_walk_forward(\n        fold_rows,\n        aggregate_metrics=aggregate,\n        aggregate_max_underwater_days=max_underwater_calendar_days(chained_equity),\n    )\n    if include_selection_evidence:\n        summary["selection_evidence"] = build_walk_forward_selection_evidence(\n            selection_observations,\n            chained_equity=chained_equity,\n        )\n    else:\n        summary["selection_evidence"] = {\n            "not_computed_reason": "stress_profile_reuses_baseline_selection_evidence",\n            "uses_audit_or_holdout": False,\n        }\n    summary["fee_bps_per_side"] = fee_rate * 10_000\n    summary["slippage_bps_per_side"] = slippage_bps\n    return summary\n''',
    )


def patch_research_loop() -> None:
    path = "src/ethusdc_bot/backtest/research_loop_runner.py"
    replace_exact(
        path,
        '''from ethusdc_bot.backtest.search_space import (\n''',
        '''from ethusdc_bot.backtest.selection_evidence import run_parameter_stability\nfrom ethusdc_bot.backtest.search_space import (\n''',
    )
    replace_exact(
        path,
        '''from ethusdc_bot.backtest.walk_forward import (\n    evaluate_rolling_origins,\n''',
        '''from ethusdc_bot.backtest.walk_forward import (\n    evaluate_rolling_origins,\n    evaluate_walk_forward,\n''',
    )
    replace_exact(
        path,
        '''    rank_with_walk_forward,\n)\n''',
        '''    rank_with_walk_forward,\n)\nfrom ethusdc_bot.backtest.walk_forward_evidence import (\n    build_walk_forward_stress_evidence,\n)\n''',
        count=1,
    )
    replace_exact(
        path,
        '''MAX_SELECTION_CANDIDATE_DAYS_PER_CYCLE = (\n    (\n        CANDIDATE_STAGE_BUDGETS["tested_candidates"]\n        + CANDIDATE_STAGE_BUDGETS["walk_forward_candidates"]\n        + CANDIDATE_STAGE_BUDGETS["finalists"]\n    )\n    * TRAINING_DAYS\n    + CANDIDATE_STAGE_BUDGETS["finalists"] * 3 * BLINDTEST_DAYS\n)\n''',
        '''MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS = 12\nPARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER = 2\nSTRESS_PROFILES_BEYOND_BASELINE = 2\nINTERNAL_VALIDATION_DAYS = TRAINING_DAYS // 5\nMAX_SELECTION_CANDIDATE_DAYS_PER_CYCLE = (\n    (\n        CANDIDATE_STAGE_BUDGETS["tested_candidates"]\n        + CANDIDATE_STAGE_BUDGETS["walk_forward_candidates"]\n        + CANDIDATE_STAGE_BUDGETS["finalists"]\n    )\n    * TRAINING_DAYS\n    + CANDIDATE_STAGE_BUDGETS["finalists"] * 3 * BLINDTEST_DAYS\n)\nMAX_SELECTION_EVIDENCE_CANDIDATE_DAYS_PER_CYCLE = (\n    CANDIDATE_STAGE_BUDGETS["finalists"]\n    * (\n        STRESS_PROFILES_BEYOND_BASELINE * TRAINING_DAYS\n        + PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER\n        * MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS\n        * INTERNAL_VALIDATION_DAYS\n    )\n)\n''',
    )
    replace_exact(
        path,
        '''            record["rolling_origin_summary"] = evaluate_rolling_origins(\n                list(plan.historical_origins),\n                record["candidate"],\n                origin_limit=config.rolling_origin_limit,\n            )\n            evidence = _quality_evidence(record, full_training_result)\n''',
        '''            record["rolling_origin_summary"] = evaluate_rolling_origins(\n                list(plan.historical_origins),\n                record["candidate"],\n                origin_limit=config.rolling_origin_limit,\n            )\n            joint_stress_wfv = evaluate_walk_forward(\n                split.training,\n                record["candidate"],\n                fold_count=config.walk_forward_fold_count,\n                training_days=split.training_days,\n                blindtest_days=split.blindtest_days,\n                expected_candles_per_day=1440,\n                fee_rate=QUALITY_GATE_V1.joint_stress_fee_bps_per_side / 10_000,\n                slippage_bps=QUALITY_GATE_V1.joint_stress_slippage_bps_per_side,\n                include_selection_evidence=False,\n            )\n            slippage_stress_wfv = evaluate_walk_forward(\n                split.training,\n                record["candidate"],\n                fold_count=config.walk_forward_fold_count,\n                training_days=split.training_days,\n                blindtest_days=split.blindtest_days,\n                expected_candles_per_day=1440,\n                fee_rate=QUALITY_GATE_V1.slippage_stress_fee_bps_per_side / 10_000,\n                slippage_bps=QUALITY_GATE_V1.slippage_stress_slippage_bps_per_side,\n                include_selection_evidence=False,\n            )\n            baseline_selection = record["walk_forward_summary"].get(\n                "selection_evidence", {}\n            )\n            record["selection_evidence"] = {\n                "rolling": baseline_selection.get("rolling", {}),\n                "temporal": baseline_selection.get("temporal", {}),\n                "regime": baseline_selection.get("regime", {}),\n                "stress": build_walk_forward_stress_evidence(\n                    record["walk_forward_summary"],\n                    joint_stress_wfv,\n                    slippage_stress_wfv,\n                    baseline_fee_bps=QUALITY_GATE_V1.baseline_fee_bps_per_side,\n                    baseline_slippage_bps=(\n                        QUALITY_GATE_V1.baseline_slippage_bps_per_side\n                    ),\n                    joint_fee_bps=QUALITY_GATE_V1.joint_stress_fee_bps_per_side,\n                    joint_slippage_bps=(\n                        QUALITY_GATE_V1.joint_stress_slippage_bps_per_side\n                    ),\n                    slippage_fee_bps=(\n                        QUALITY_GATE_V1.slippage_stress_fee_bps_per_side\n                    ),\n                    slippage_stress_bps=(\n                        QUALITY_GATE_V1.slippage_stress_slippage_bps_per_side\n                    ),\n                ),\n                "parameter_stability": run_parameter_stability(\n                    validation,\n                    record["candidate"],\n                    days=validation_days,\n                    gate=QUALITY_GATE_V1,\n                    baseline_result=record["validation_result"],\n                    max_numeric_parameters=(\n                        MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS\n                    ),\n                ),\n                "provenance": {\n                    "selection_data_only": True,\n                    "uses_audit_or_holdout": False,\n                    "rolling_temporal_regime_source": (\n                        "chronological_walk_forward_validation_folds"\n                    ),\n                    "parameter_source": "internal_validation_only",\n                    "stress_source": "same_walk_forward_folds_fixed_cost_profiles",\n                },\n            }\n            evidence = _quality_evidence(record, full_training_result)\n''',
    )
    replace_exact(
        path,
        '''    validation = record["validation_metrics"].to_dict()\n''',
        '''    selection_evidence = record.get("selection_evidence", {})\n    validation = record["validation_metrics"].to_dict()\n''',
        count=1,
    )
    replace_exact(
        path,
        '''        # Formal rolling-origin evidence requires a time-local pipeline refit.\n        # Fixed-candidate historical replays are reported but never promoted\n        # into the quality-gate evidence mapping.\n        "rolling": {},\n    }\n''',
        '''        "rolling": dict(selection_evidence.get("rolling", {})),\n        "stress": dict(selection_evidence.get("stress", {})),\n        "parameter_stability": dict(\n            selection_evidence.get("parameter_stability", {})\n        ),\n        "temporal": dict(selection_evidence.get("temporal", {})),\n        "regime": dict(selection_evidence.get("regime", {})),\n        "selection_evidence_provenance": dict(\n            selection_evidence.get("provenance", {})\n        ),\n    }\n''',
    )
    replace_exact(
        path,
        '''def _resource_budget(config: LoopConfig) -> dict[str, int]:\n    candidate_days = _selection_candidate_day_cap(config)\n    return {\n''',
        '''def _resource_budget(config: LoopConfig) -> dict[str, int]:\n    candidate_days = _selection_candidate_day_cap(config)\n    stress_days = (\n        config.finalists_per_cycle\n        * STRESS_PROFILES_BEYOND_BASELINE\n        * TRAINING_DAYS\n    )\n    parameter_days = (\n        config.finalists_per_cycle\n        * PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER\n        * MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS\n        * INTERNAL_VALIDATION_DAYS\n    )\n    total_days = candidate_days + stress_days + parameter_days\n    return {\n''',
    )
    replace_exact(
        path,
        '''        "selection_candidate_days_cap": candidate_days,\n        "selection_candle_evaluations_cap": candidate_days * 1440,\n    }\n''',
        '''        "selection_candidate_days_cap": candidate_days,\n        "selection_candle_evaluations_cap": candidate_days * 1440,\n        "stress_evidence_candidate_days_cap": stress_days,\n        "parameter_evidence_candidate_days_cap": parameter_days,\n        "selection_total_candidate_days_cap": total_days,\n        "selection_total_candle_evaluations_cap": total_days * 1440,\n        "max_numeric_parameters_per_finalist": (\n            MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS\n        ),\n    }\n''',
    )
    replace_exact(
        path,
        '''            "selection_candidate_days_cap": _selection_candidate_day_cap(config) * config.max_cycles,\n            "selection_candle_evaluations_cap": (\n                _selection_candidate_day_cap(config) * config.max_cycles * 1440\n            ),\n''',
        '''            "selection_candidate_days_cap": (\n                _selection_candidate_day_cap(config) * config.max_cycles\n            ),\n            "selection_candle_evaluations_cap": (\n                _selection_candidate_day_cap(config) * config.max_cycles * 1440\n            ),\n            "selection_total_candidate_days_cap": (\n                _resource_budget(config)["selection_total_candidate_days_cap"]\n                * config.max_cycles\n            ),\n            "selection_total_candle_evaluations_cap": (\n                _resource_budget(config)[\n                    "selection_total_candle_evaluations_cap"\n                ]\n                * config.max_cycles\n            ),\n''',
    )


def patch_tests() -> None:
    path = "tests/unit/test_research_loop_runner.py"
    replace_exact(
        path,
        '''            "selection_candidate_days_cap": 4015,\n            "selection_candle_evaluations_cap": 5_781_600,\n''',
        '''            "selection_candidate_days_cap": 4015,\n            "selection_candle_evaluations_cap": 5_781_600,\n            "stress_evidence_candidate_days_cap": 1460,\n            "parameter_evidence_candidate_days_cap": 3504,\n            "selection_total_candidate_days_cap": 8979,\n            "selection_total_candle_evaluations_cap": 12_929_760,\n            "max_numeric_parameters_per_finalist": 12,\n''',
    )

    path = "tests/integration/test_research_loop_protocol_v2_smoke.py"
    replace_exact(
        path,
        '''import ethusdc_bot.backtest.research_loop_runner as loop_module\nimport ethusdc_bot.backtest.walk_forward as walk_forward_module\n''',
        '''import ethusdc_bot.backtest.research_loop_runner as loop_module\nimport ethusdc_bot.backtest.selection_evidence as selection_evidence_module\nimport ethusdc_bot.backtest.walk_forward as walk_forward_module\n''',
    )
    replace_exact(
        path,
        '''    monkeypatch.setattr(loop_module, "simulate_strategy", simulate_spy)\n    monkeypatch.setattr(walk_forward_module, "simulate_strategy", simulate_spy)\n''',
        '''    monkeypatch.setattr(loop_module, "simulate_strategy", simulate_spy)\n    monkeypatch.setattr(walk_forward_module, "simulate_strategy", simulate_spy)\n    monkeypatch.setattr(selection_evidence_module, "simulate_strategy", simulate_spy)\n''',
        count=2,
    )
    replace_exact(
        path,
        '''    assert gate["passed"] is False\n    assert "rolling.max_underwater_days" in gate["missing_evidence"]\n    assert "stress.baseline.fee_bps_per_side" in gate["missing_evidence"]\n''',
        '''    assert gate["passed"] is False\n    assert evidence["rolling"]["drawdown_method"] == "mark_to_market"\n    assert evidence["stress"]["baseline"]["fee_bps_per_side"] == 10.0\n    assert evidence["stress"]["joint"]["fee_bps_per_side"] == 15.0\n    assert evidence["parameter_stability"]["uses_audit_or_holdout"] is False\n    assert evidence["temporal"]["months_observed"] >= 1\n    assert evidence["regime"]["threshold_source"] == "training_only"\n    assert "rolling.max_underwater_days" not in gate["missing_evidence"]\n    assert "stress.baseline.fee_bps_per_side" not in gate["missing_evidence"]\n''',
    )


def main() -> None:
    patch_selection_evidence()
    patch_walk_forward()
    patch_research_loop()
    patch_tests()


if __name__ == "__main__":
    main()
