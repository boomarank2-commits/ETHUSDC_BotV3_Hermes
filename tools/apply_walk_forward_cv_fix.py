"""Apply the zero-mean Walk-Forward coefficient-of-variation correction."""

from __future__ import annotations

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
        "src/ethusdc_bot/backtest/walk_forward.py",
        '''    mean = sum(values) / len(values) if values else 0.0\n    coefficient_of_variation = pstdev(values) / abs(mean) if len(values) > 1 and mean else None\n''',
        '''    mean = sum(values) / len(values) if values else 0.0\n    if len(values) > 1:\n        dispersion = pstdev(values)\n        if mean:\n            coefficient_of_variation = dispersion / abs(mean)\n        elif dispersion == 0:\n            coefficient_of_variation = 0.0\n        else:\n            coefficient_of_variation = None\n    else:\n        coefficient_of_variation = None\n''',
    )


if __name__ == "__main__":
    main()
