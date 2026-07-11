from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor missing in {path}: {old[:120]!r}")
    updated = text.replace(old, new, count)
    target.write_text(updated, encoding="utf-8")


# 1. Context wrapper must not collide with nested base strategies' own base_family.
replace(
    "src/ethusdc_bot/backtest/simulator.py",
    '''    base_family = str(strategy.params.get("base_family", "momentum"))
    if base_family == "context_filter":
        return False, "context_recursive_base_forbidden"
    base_params = {
        key: value
        for key, value in strategy.params.items()
        if key != "base_family" and not key.startswith("context_")
    }
''',
    '''    base_family = str(
        strategy.params.get(
            "context_base_family",
            strategy.params.get("base_family", "momentum"),
        )
    )
    if base_family == "context_filter":
        return False, "context_recursive_base_forbidden"
    base_params = {
        key: value
        for key, value in strategy.params.items()
        if key != "context_base_family" and not key.startswith("context_")
    }
''',
)

# 2. Search frontier can optionally add deterministic context wrappers while preserving old default.
replace(
    "src/ethusdc_bot/backtest/search_space.py",
    "from ethusdc_bot.backtest.simulator import StrategyCandidate\n",
    '''from ethusdc_bot.backtest.context_research import (
    context_policy_for_profile,
    wrap_candidate_with_context,
)
from ethusdc_bot.backtest.simulator import StrategyCandidate
''',
)
replace(
    "src/ethusdc_bot/backtest/search_space.py",
    '''CONTEXT_CANDIDATES_ENABLED: Final = False
CONTEXT_DISABLED_REASON: Final = "real_context_market_data_not_integrated"
''',
    '''CONTEXT_CANDIDATES_ENABLED: Final = False
CONTEXT_DISABLED_REASON: Final = "context_research_must_be_explicitly_enabled"
CONTEXT_SEARCH_FAMILY: Final = "context_filter"
''',
)
replace(
    "src/ethusdc_bot/backtest/search_space.py",
    '''def generate_search_space(
    state: SearchSpaceState, *, max_candidates: int = 40
) -> list[StrategyCandidate]:
''',
    '''def generate_search_space(
    state: SearchSpaceState,
    *,
    max_candidates: int = 40,
    context_enabled: bool = False,
) -> list[StrategyCandidate]:
''',
)
replace(
    "src/ethusdc_bot/backtest/search_space.py",
    '''    candidates = _frontier_candidates(pressure, opening_bias)
''',
    '''    if not isinstance(context_enabled, bool):
        raise TypeError("context_enabled must be bool")
    candidates = _frontier_candidates(
        pressure,
        opening_bias,
        context_enabled=context_enabled,
    )
''',
)
replace(
    "src/ethusdc_bot/backtest/search_space.py",
    '''def search_frontier_summary(
    candidates: list[StrategyCandidate],
    state: SearchSpaceState,
    *,
    requested_cap: int,
) -> dict[str, Any]:
''',
    '''def search_frontier_summary(
    candidates: list[StrategyCandidate],
    state: SearchSpaceState,
    *,
    requested_cap: int,
    context_enabled: bool = False,
) -> dict[str, Any]:
''',
)
replace(
    "src/ethusdc_bot/backtest/search_space.py",
    '''    counts = Counter(candidate.family for candidate in candidates)
    return {
''',
    '''    if not isinstance(context_enabled, bool):
        raise TypeError("context_enabled must be bool")
    counts = Counter(candidate.family for candidate in candidates)
    active_families = (
        (*ACTIVE_SEARCH_FAMILIES, CONTEXT_SEARCH_FAMILY)
        if context_enabled
        else ACTIVE_SEARCH_FAMILIES
    )
    return {
''',
)
replace(
    "src/ethusdc_bot/backtest/search_space.py",
    '''        "active_families": list(ACTIVE_SEARCH_FAMILIES),
        "family_counts": {
            family: counts.get(family, 0) for family in ACTIVE_SEARCH_FAMILIES
        },
''',
    '''        "active_families": list(active_families),
        "family_counts": {
            family: counts.get(family, 0) for family in active_families
        },
''',
)
replace(
    "src/ethusdc_bot/backtest/search_space.py",
    '''        "context_candidates_enabled": CONTEXT_CANDIDATES_ENABLED,
        "context_disabled_reason": CONTEXT_DISABLED_REASON,
''',
    '''        "context_candidates_enabled": context_enabled,
        "context_disabled_reason": None if context_enabled else CONTEXT_DISABLED_REASON,
''',
)
replace(
    "src/ethusdc_bot/backtest/search_space.py",
    '''def _frontier_candidates(
    pressure: int, opening_bias: int
) -> list[StrategyCandidate]:
    candidates: list[StrategyCandidate] = []
    for profile in range(_PROFILE_COUNT):
        candidates.extend(
            (
                _breakout_candidate(profile, pressure, opening_bias),
                _cooldown_candidate(profile, pressure, opening_bias),
                _momentum_candidate(profile, pressure, opening_bias),
                _pullback_candidate(profile, pressure, opening_bias),
                _mean_reversion_candidate(profile, pressure, opening_bias),
                _session_candidate(profile, pressure, opening_bias),
            )
        )
    return candidates
''',
    '''def _frontier_candidates(
    pressure: int,
    opening_bias: int,
    *,
    context_enabled: bool = False,
) -> list[StrategyCandidate]:
    candidates: list[StrategyCandidate] = []
    for profile in range(_PROFILE_COUNT):
        base_candidates = (
            _breakout_candidate(profile, pressure, opening_bias),
            _cooldown_candidate(profile, pressure, opening_bias),
            _momentum_candidate(profile, pressure, opening_bias),
            _pullback_candidate(profile, pressure, opening_bias),
            _mean_reversion_candidate(profile, pressure, opening_bias),
            _session_candidate(profile, pressure, opening_bias),
        )
        if context_enabled:
            base_for_context = base_candidates[profile % len(base_candidates)]
            candidates.append(
                wrap_candidate_with_context(
                    base_for_context,
                    context_policy_for_profile(profile),
                )
            )
        candidates.extend(base_candidates)
    return candidates
''',
)

# 3. Walk-forward and rolling-origin functions receive exact aligned context slices.
replace(
    "src/ethusdc_bot/backtest/walk_forward.py",
    "from ethusdc_bot.backtest.data_loader import Candle\n",
    '''from ethusdc_bot.backtest.context_research import context_for_candidate
from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle
''',
)
replace(
    "src/ethusdc_bot/backtest/walk_forward.py",
    '''    include_selection_evidence: bool = True,
) -> dict[str, Any]:
''',
    '''    include_selection_evidence: bool = True,
    market_context: AlignedMarketCandles | None = None,
) -> dict[str, Any]:
''',
)
replace(
    "src/ethusdc_bot/backtest/walk_forward.py",
    '''            slippage_bps=slippage_bps,
        )
''',
    '''            slippage_bps=slippage_bps,
            market_context=context_for_candidate(
                market_context,
                validation_window,
                candidate,
            ),
        )
''',
)
replace(
    "src/ethusdc_bot/backtest/walk_forward.py",
    '''    expected_candles_per_day: int | None = None,
) -> list[dict[str, Any]]:
''',
    '''    expected_candles_per_day: int | None = None,
    market_context: AlignedMarketCandles | None = None,
) -> list[dict[str, Any]]:
''',
)
replace(
    "src/ethusdc_bot/backtest/walk_forward.py",
    '''            expected_candles_per_day=expected_candles_per_day,
        )
''',
    '''            expected_candles_per_day=expected_candles_per_day,
            market_context=market_context,
        )
''',
)
replace(
    "src/ethusdc_bot/backtest/walk_forward.py",
    '''    *,
    origin_limit: int | None = None,
) -> dict[str, Any]:
''',
    '''    *,
    origin_limit: int | None = None,
    market_context: AlignedMarketCandles | None = None,
) -> dict[str, Any]:
''',
)
replace(
    "src/ethusdc_bot/backtest/walk_forward.py",
    '''            blindtest_days=origin.blindtest_days,
        )
''',
    '''            blindtest_days=origin.blindtest_days,
            market_context=context_for_candidate(
                market_context,
                origin.blindtest,
                candidate,
            ),
        )
''',
)

# 4. Parameter and cost stability reuse the identical context window.
replace(
    "src/ethusdc_bot/backtest/selection_evidence.py",
    "from ethusdc_bot.backtest.data_loader import Candle\n",
    "from ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle\n",
)
replace(
    "src/ethusdc_bot/backtest/selection_evidence.py",
    '''    "base_family",
    "context_symbol",
''',
    '''    "base_family",
    "context_base_family",
    "context_symbol",
''',
)
replace(
    "src/ethusdc_bot/backtest/selection_evidence.py",
    '''    days: int,
    gate: QualityGateV1 = QUALITY_GATE_V1,
) -> dict[str, Any]:
''',
    '''    days: int,
    gate: QualityGateV1 = QUALITY_GATE_V1,
    market_context: AlignedMarketCandles | None = None,
) -> dict[str, Any]:
''',
    count=1,
)
replace(
    "src/ethusdc_bot/backtest/selection_evidence.py",
    '''            slippage_bps=slippage_bps,
        )
''',
    '''            slippage_bps=slippage_bps,
            market_context=market_context,
        )
''',
    count=1,
)
replace(
    "src/ethusdc_bot/backtest/selection_evidence.py",
    '''    baseline_result: SimulationResult | None = None,
    max_numeric_parameters: int = 12,
) -> dict[str, Any]:
''',
    '''    baseline_result: SimulationResult | None = None,
    max_numeric_parameters: int = 18,
    market_context: AlignedMarketCandles | None = None,
) -> dict[str, Any]:
''',
)
replace(
    "src/ethusdc_bot/backtest/selection_evidence.py",
    "    baseline = baseline_result or simulate_strategy(candles, candidate, days=days)\n",
    '''    baseline = baseline_result or simulate_strategy(
        candles,
        candidate,
        days=days,
        market_context=market_context,
    )
''',
)
replace(
    "src/ethusdc_bot/backtest/selection_evidence.py",
    "                result=simulate_strategy(candles, neighbor, days=days),\n",
    '''                result=simulate_strategy(
                    candles,
                    neighbor,
                    days=days,
                    market_context=market_context,
                ),
''',
)

# 5. Runner loads all aligned markets only when explicitly enabled and threads context everywhere.
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    "from ethusdc_bot.backtest.data_loader import DEFAULT_RAW_ROOT, Candle, load_ethusdc_1m_candles\n",
    '''from ethusdc_bot.backtest.context_research import (
    context_for_candidate,
    context_research_provenance,
    slice_aligned_context,
)
from ethusdc_bot.backtest.data_loader import (
    DEFAULT_RAW_ROOT,
    AlignedMarketCandles,
    Candle,
    load_aligned_market_candles,
    load_ethusdc_1m_candles,
)
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    "MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS = 12\n",
    "MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS = 18\n",
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''    stagnation_cycles: int = 3
    required_days: int | None = REQUIRED_DAYS
''',
    '''    stagnation_cycles: int = 3
    required_days: int | None = REQUIRED_DAYS
    enable_context: bool = False
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''    def __post_init__(self) -> None:
        integer_controls = (
''',
    '''    def __post_init__(self) -> None:
        if not isinstance(self.enable_context, bool):
            raise ValueError("enable_context must be bool")
        integer_controls = (
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''    candles = load_ethusdc_1m_candles(raw_root)
    plan = _build_window_plan(candles, config)
''',
    '''    market_context: AlignedMarketCandles | None
    if config.enable_context:
        market_context = load_aligned_market_candles(raw_root)
        candles = list(market_context.ethusdc)
    else:
        market_context = None
        candles = load_ethusdc_1m_candles(raw_root)
    plan = _build_window_plan(candles, config)
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''    subtrain_days = _calendar_day_count(subtrain)
    validation_days = _calendar_day_count(validation)
''',
    '''    subtrain_days = _calendar_day_count(subtrain)
    validation_days = _calendar_day_count(validation)
    training_context = (
        slice_aligned_context(market_context, split.training)
        if market_context is not None
        else None
    )
    subtrain_context = (
        slice_aligned_context(market_context, subtrain)
        if market_context is not None
        else None
    )
    validation_context = (
        slice_aligned_context(market_context, validation)
        if market_context is not None
        else None
    )
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    "        generated = generate_search_space(state, max_candidates=config.max_candidates_per_cycle)\n",
    '''        generated = generate_search_space(
            state,
            max_candidates=config.max_candidates_per_cycle,
            context_enabled=config.enable_context,
        )
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''            requested_cap=config.max_candidates_per_cycle,
        )
''',
    '''            requested_cap=config.max_candidates_per_cycle,
            context_enabled=config.enable_context,
        )
''',
    count=1,
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''                blindtest_days=split.blindtest_days,
            )
            validation_result = simulate_strategy(
''',
    '''                blindtest_days=split.blindtest_days,
                market_context=context_for_candidate(
                    subtrain_context,
                    subtrain,
                    candidate,
                ),
            )
            validation_result = simulate_strategy(
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''                blindtest_days=split.blindtest_days,
            )
            records.append(
''',
    '''                blindtest_days=split.blindtest_days,
                market_context=context_for_candidate(
                    validation_context,
                    validation,
                    candidate,
                ),
            )
            records.append(
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''            expected_candles_per_day=1440,
        )
''',
    '''            expected_candles_per_day=1440,
            market_context=training_context,
        )
''',
    count=1,
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''                blindtest_days=split.blindtest_days,
            )
            record["full_training_result"] = full_training_result
''',
    '''                blindtest_days=split.blindtest_days,
                market_context=context_for_candidate(
                    training_context,
                    split.training,
                    record["candidate"],
                ),
            )
            record["full_training_result"] = full_training_result
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''                origin_limit=config.rolling_origin_limit,
            )
''',
    '''                origin_limit=config.rolling_origin_limit,
                market_context=market_context,
            )
''',
)
# Both stress WFV calls receive the same training context.
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''                include_selection_evidence=False,
            )
''',
    '''                include_selection_evidence=False,
                market_context=training_context,
            )
''',
    count=2,
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''                    max_numeric_parameters=(
                        MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS
                    ),
                ),
''',
    '''                    max_numeric_parameters=(
                        MAX_PARAMETER_STABILITY_NUMERIC_PARAMETERS
                    ),
                    market_context=context_for_candidate(
                        validation_context,
                        validation,
                        record["candidate"],
                    ),
                ),
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''            "search_frontier": frontier_summary,
            "resource_budget": _resource_budget(config),
''',
    '''            "search_frontier": frontier_summary,
            "context_research": (
                context_research_provenance(market_context, generated)
                if market_context is not None
                else {
                    "enabled": False,
                    "reason": "context_research_not_enabled",
                    "uses_audit_or_holdout": False,
                    "target_used_as_parameter": False,
                }
            ),
            "resource_budget": _resource_budget(config),
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''    parser.add_argument("--fixture-smoke", action="store_true")
''',
    '''    parser.add_argument("--fixture-smoke", action="store_true")
    parser.add_argument("--enable-context", action="store_true")
''',
)
replace(
    "src/ethusdc_bot/backtest/research_loop_runner.py",
    '''        required_days=None if args.fixture_smoke else REQUIRED_DAYS,
    )
''',
    '''        required_days=None if args.fixture_smoke else REQUIRED_DAYS,
        enable_context=args.enable_context,
    )
''',
)

# 6. Launcher explicitly requests the integrated context path.
replace(
    "tools/run_production_research.ps1",
    '''    "--rolling-origin-limit", "3"
)
''',
    '''    "--rolling-origin-limit", "3",
    "--enable-context"
)
''',
)

# 7. Existing resource fixture reflects the explicit 18-parameter cap.
replace(
    "tests/unit/test_research_loop_runner.py",
    '            "parameter_evidence_candidate_days_cap": 3504,\n',
    '            "parameter_evidence_candidate_days_cap": 5256,\n',
)
replace(
    "tests/unit/test_research_loop_runner.py",
    '            "selection_total_candidate_days_cap": 8979,\n',
    '            "selection_total_candidate_days_cap": 10731,\n',
)
replace(
    "tests/unit/test_research_loop_runner.py",
    '            "selection_total_candle_evaluations_cap": 12_929_760,\n',
    '            "selection_total_candle_evaluations_cap": 15_452_640,\n',
)
replace(
    "tests/unit/test_research_loop_runner.py",
    '            "max_numeric_parameters_per_finalist": 12,\n',
    '            "max_numeric_parameters_per_finalist": 18,\n',
)

print("context research integration patch applied")
