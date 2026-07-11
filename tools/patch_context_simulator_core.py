from pathlib import Path

path = Path(__file__).resolve().parents[1] / "src/ethusdc_bot/backtest/simulator.py"
text = path.read_text(encoding="utf-8")
replacements = [
    (
        "from ethusdc_bot.backtest.data_loader import Candle, EXPECTED_STEP_MS, SYMBOL\n",
        "from ethusdc_bot.backtest.context_features import ContextVetoPolicy, evaluate_context_veto, validate_context_against_trade_candles\nfrom ethusdc_bot.backtest.data_loader import AlignedMarketCandles, Candle, EXPECTED_STEP_MS, SYMBOL\n",
    ),
    (
        "    training_days: int = 0,\n    blindtest_days: int = 0,\n) -> SimulationResult:\n",
        "    training_days: int = 0,\n    blindtest_days: int = 0,\n    market_context: AlignedMarketCandles | None = None,\n) -> SimulationResult:\n",
    ),
    (
        "    trades: list[Trade] = []\n",
        "    context_policy: ContextVetoPolicy | None = None\n    if strategy.family == \"context_filter\":\n        context_policy = ContextVetoPolicy.from_candidate_params(strategy.params)\n        if market_context is not None:\n            validate_context_against_trade_candles(candles, market_context)\n    trades: list[Trade] = []\n",
    ),
]
for old, new in replacements:
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError("expected simulator fragment not found")
path.write_text(text, encoding="utf-8")
