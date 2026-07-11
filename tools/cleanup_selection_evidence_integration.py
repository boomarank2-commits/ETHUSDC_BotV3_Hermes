"""Remove duplicate fragments caused by a repeated one-shot integration run."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def collapse(relative_path: str, fragment: str) -> None:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    doubled = fragment + fragment
    if doubled in text:
        path.write_text(text.replace(doubled, fragment), encoding="utf-8")
        print(f"collapsed duplicate in {relative_path}")
        return
    if fragment in text:
        print(f"already clean {relative_path}")
        return
    raise RuntimeError(f"expected fragment missing in {relative_path}")


def remove_second_block(relative_path: str, block: str) -> None:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    first = text.find(block)
    if first < 0:
        raise RuntimeError(f"expected block missing in {relative_path}")
    second = text.find(block, first + len(block))
    if second < 0:
        print(f"already single block in {relative_path}")
        return
    if text.find(block, second + len(block)) >= 0:
        raise RuntimeError(f"more than two duplicate blocks in {relative_path}")
    path.write_text(text[:second] + text[second + len(block):], encoding="utf-8")
    print(f"removed second block in {relative_path}")


def main() -> None:
    collapse(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        "from ethusdc_bot.backtest.selection_evidence import run_parameter_stability\n",
    )
    collapse(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        "    evaluate_walk_forward,\n",
    )
    collapse(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        "from ethusdc_bot.backtest.walk_forward_evidence import (\n"
        "    build_walk_forward_stress_evidence,\n"
        ")\n",
    )
    collapse(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        "MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS = 12\n"
        "PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER = 2\n"
        "STRESS_PROFILES_BEYOND_BASELINE = 2\n"
        "INTERNAL_VALIDATION_DAYS = TRAINING_DAYS // 5\n",
    )
    collapse(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        "    selection_evidence = record.get(\"selection_evidence\", {})\n",
    )
    remove_second_block(
        "src/ethusdc_bot/backtest/research_loop_runner.py",
        "MAX_SELECTION_EVIDENCE_CANDIDATE_DAYS_PER_CYCLE = (\n"
        "    CANDIDATE_STAGE_BUDGETS[\"finalists\"]\n"
        "    * (\n"
        "        STRESS_PROFILES_BEYOND_BASELINE * TRAINING_DAYS\n"
        "        + PARAMETER_NEIGHBORS_PER_NUMERIC_PARAMETER\n"
        "        * MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS\n"
        "        * INTERNAL_VALIDATION_DAYS\n"
        "    )\n"
        ")\n",
    )

    collapse(
        "src/ethusdc_bot/backtest/walk_forward.py",
        "from ethusdc_bot.backtest.walk_forward_evidence import (\n"
        "    FoldSelectionObservation,\n"
        "    build_walk_forward_selection_evidence,\n"
        ")\n",
    )
    collapse(
        "src/ethusdc_bot/backtest/walk_forward.py",
        "    if fee_rate < 0 or slippage_bps < 0:\n"
        "        raise ValueError(\"fee_rate and slippage_bps must be non-negative\")\n",
    )

    collapse(
        "src/ethusdc_bot/backtest/selection_evidence.py",
        "    if numeric_count > max_numeric_parameters:\n"
        "        return {\n"
        "            \"all_numeric_parameters_perturbed\": False,\n"
        "            \"numeric_parameter_count\": numeric_count,\n"
        "            \"neighbor_count\": 0,\n"
        "            \"perturbation_fraction\": gate.parameter_perturbation_fraction,\n"
        "            \"session_hour_step\": gate.parameter_session_hour_step,\n"
        "            \"passing_neighbor_fraction\": 0.0,\n"
        "            \"median_net_retention\": 0.0,\n"
        "            \"worst_neighbor_net_usdc_per_day\": 0.0,\n"
        "            \"baseline_net_usdc_per_day\": baseline.net_usdc_per_day,\n"
        "            \"neighbors\": [],\n"
        "            \"resource_limit_numeric_parameters\": max_numeric_parameters,\n"
        "            \"blocked_reason\": \"numeric_parameter_count_exceeds_resource_limit\",\n"
        "            \"uses_audit_or_holdout\": False,\n"
        "        }\n",
    )
    remove_second_block(
        "src/ethusdc_bot/backtest/selection_evidence.py",
        "def _training_volatility_threshold(\n"
        "    candles: Sequence[Candle], lookback: int\n"
        ") -> float:\n"
        "    if len(candles) < 2:\n"
        "        return 0.0\n"
        "    moves: list[float] = []\n"
        "    for index in range(1, len(candles)):\n"
        "        previous = float(candles[index - 1].close)\n"
        "        current = float(candles[index].close)\n"
        "        moves.append(abs(current / previous - 1) * 10_000 if previous else 0.0)\n"
        "    rolling_values: list[float] = []\n"
        "    rolling_sum = 0.0\n"
        "    for index, move in enumerate(moves):\n"
        "        rolling_sum += move\n"
        "        if index >= lookback:\n"
        "            rolling_sum -= moves[index - lookback]\n"
        "        width = min(index + 1, lookback)\n"
        "        rolling_values.append(rolling_sum / width)\n"
        "    finite_values = [value for value in rolling_values if isfinite(value)]\n"
        "    return median(finite_values) if finite_values else 0.0\n\n\n",
    )

    collapse(
        "tests/integration/test_research_loop_protocol_v2_smoke.py",
        "    monkeypatch.setattr(selection_evidence_module, \"simulate_strategy\", simulate_spy)\n",
    )
    collapse(
        "tests/unit/test_research_loop_runner.py",
        "            \"stress_evidence_candidate_days_cap\": 1460,\n"
        "            \"parameter_evidence_candidate_days_cap\": 3504,\n"
        "            \"selection_total_candidate_days_cap\": 8979,\n"
        "            \"selection_total_candle_evaluations_cap\": 12_929_760,\n"
        "            \"max_numeric_parameters_per_finalist\": 12,\n",
    )


if __name__ == "__main__":
    main()
