from pathlib import Path

path = Path(__file__).resolve().parents[1] / "src/ethusdc_bot/backtest/simulator.py"
text = path.read_text(encoding="utf-8")

block = '''    context_policy: ContextVetoPolicy | None = None\n    if strategy.family == "context_filter":\n        context_policy = ContextVetoPolicy.from_candidate_params(strategy.params)\n        if market_context is not None:\n            validate_context_against_trade_candles(candles, market_context)\n'''
while block + block in text:
    text = text.replace(block + block, block, 1)

old_entry = '''        if position is None and index >= cooldown_until_index and index < len(candles) - 1 and _signal(candles, index, strategy):\n            pending_entry = True\n'''
new_entry = '''        if position is None and index >= cooldown_until_index and index < len(candles) - 1:\n            entry_allowed, rejection_reason = _entry_decision(\n                candles,\n                index,\n                strategy,\n                market_context=market_context,\n                context_policy=context_policy,\n            )\n            if entry_allowed:\n                pending_entry = True\n            elif rejection_reason is not None:\n                rejections[rejection_reason] += 1\n'''
if old_entry in text:
    text = text.replace(old_entry, new_entry, 1)
elif new_entry not in text:
    raise RuntimeError("entry fragment not found")

marker = '''def _signal(candles: list[Candle], index: int, strategy: StrategyCandidate) -> bool:\n'''
helper = '''def _entry_decision(\n    candles: list[Candle],\n    index: int,\n    strategy: StrategyCandidate,\n    *,\n    market_context: AlignedMarketCandles | None,\n    context_policy: ContextVetoPolicy | None,\n) -> tuple[bool, str | None]:\n    if strategy.family != "context_filter":\n        return _signal(candles, index, strategy), None\n\n    base_family = str(strategy.params.get("base_family", "momentum"))\n    if base_family == "context_filter":\n        return False, "context_recursive_base_forbidden"\n    base_params = {\n        key: value\n        for key, value in strategy.params.items()\n        if key != "base_family" and not key.startswith("context_")\n    }\n    if not _signal(candles, index, StrategyCandidate(base_family, base_params)):\n        return False, None\n    if market_context is None or context_policy is None:\n        return False, "context_data_missing"\n    decision = evaluate_context_veto(market_context, index, context_policy)\n    if decision.allowed:\n        return True, None\n    return False, decision.reason\n\n\n'''
if helper not in text:
    if marker not in text:
        raise RuntimeError("signal marker not found")
    text = text.replace(marker, helper + marker, 1)

old_context = '''    if strategy.family == "context_filter":\n        # Context symbols are filters only. ETHUSDC remains the only tradeable\n        # symbol, and the base ETHUSDC strategy must still generate the signal.\n        if str(strategy.params.get("symbol", SYMBOL)) != SYMBOL:\n            return False\n        return _signal(candles, index, StrategyCandidate(str(strategy.params.get("base_family", "momentum")), dict(strategy.params)))\n'''
new_context = '''    if strategy.family == "context_filter":\n        return False\n'''
if old_context in text:
    text = text.replace(old_context, new_context, 1)
elif new_context not in text:
    raise RuntimeError("context signal fragment not found")

path.write_text(text, encoding="utf-8")
