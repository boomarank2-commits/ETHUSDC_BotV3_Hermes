"""Preserve Windows path semantics before native Path.resolve()."""

from pathlib import Path


root = Path(__file__).resolve().parents[1]
path = root / "src/ethusdc_bot/backtest/data_loader.py"
text = path.read_text(encoding="utf-8")
old = '''def _validate_raw_root(path: Path) -> Path:\n    candidate = path.resolve()\n    repository_root = Path.cwd().resolve()\n    if is_path_within(candidate, repository_root):\n        raise DataLoadError("Backtest loader refuses repository-local raw data paths")\n    return candidate\n'''
new = '''def _validate_raw_root(path: Path) -> Path:\n    repository_root = Path.cwd().resolve()\n    # Compare the original path first so an absolute Windows path keeps Windows\n    # semantics when validation runs on Linux CI. Native resolution happens\n    # only after the repository-containment decision.\n    if is_path_within(path, repository_root):\n        raise DataLoadError("Backtest loader refuses repository-local raw data paths")\n    return path.resolve()\n'''
if old in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
elif new not in text:
    raise RuntimeError("expected _validate_raw_root fragment not found")
