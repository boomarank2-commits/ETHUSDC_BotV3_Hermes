"""Align independent gate CV derivation and honest no-trade fixture expectations."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_exact(relative_path: str, old: str, new: str) -> None:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    if old in text:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"patched {relative_path}")
        return
    if new in text:
        print(f"already patched {relative_path}")
        return
    raise RuntimeError(f"expected source fragment not found in {relative_path}")


def main() -> None:
    replace_exact(
        "src/ethusdc_bot/backtest/quality_gates.py",
        '''        mean_net = sum(net_values) / len(net_values) if net_values else 0.0\n        derived_cv = pstdev(net_values) / abs(mean_net) if len(net_values) > 1 and mean_net else None\n''',
        '''        mean_net = sum(net_values) / len(net_values) if net_values else 0.0\n        if len(net_values) > 1:\n            dispersion = pstdev(net_values)\n            if mean_net:\n                derived_cv = dispersion / abs(mean_net)\n            elif dispersion == 0:\n                derived_cv = 0.0\n            else:\n                derived_cv = None\n        else:\n            derived_cv = None\n''',
    )
    replace_exact(
        "tests/integration/test_research_loop_protocol_v2_smoke.py",
        '''    assert gate["status"] in {"fail_gate", "fail_invalid_evidence"}\n    assert gate["missing_evidence"] == []\n    assert gate["invalid_evidence"] == [], gate["invalid_evidence"]\n    assert gate["stage_readiness"]["research_evidence_complete"] is True\n''',
        '''    assert gate["status"] == "fail_invalid_evidence"\n    assert gate["missing_evidence"] == []\n    # The six-day monotonic fixture intentionally produces no closed wins or\n    # losses. Profit factor is therefore undefined and must remain fail-closed.\n    # This is different from missing producer evidence, which must stay empty.\n    assert gate["invalid_evidence"] == [\n        "wfv.aggregate.profit_factor",\n        "wfv.folds[0].metrics.gross_profit_usdc",\n        "wfv.folds[1].metrics.gross_profit_usdc",\n    ]\n    assert gate["stage_readiness"]["research_evidence_complete"] is False\n''',
    )


if __name__ == "__main__":
    main()
