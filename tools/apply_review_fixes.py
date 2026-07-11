"""Apply small deterministic PR4 review fixes.

This script exists because the external reviewer can write repository files via
GitHub but cannot clone the repository directly.  Every replacement is exact,
idempotent, and fails loudly if the expected source shape changed.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def replace_exact(relative_path: str, old: str, new: str) -> bool:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    if old in text:
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"patched {relative_path}")
        return True
    if new in text:
        print(f"already patched {relative_path}")
        return False
    raise RuntimeError(f"expected source fragment not found in {relative_path}")


def main() -> None:
    changed = False

    changed |= replace_exact(
        "src/ethusdc_bot/config/schema.py",
        '{"100": 3, "200": 6, "500": 13, "1000": 30}',
        '{"100": 3, "200": 6, "500": 15, "1000": 30}',
    )

    changed |= replace_exact(
        "src/ethusdc_bot/data_pipeline/raw_data_contract.py",
        "from ethusdc_bot.validation import SchemaValidationError\n",
        "from ethusdc_bot.path_safety import is_path_within\n"
        "from ethusdc_bot.validation import SchemaValidationError\n",
    )
    changed |= replace_exact(
        "src/ethusdc_bot/data_pipeline/raw_data_contract.py",
        '''def _is_inside_repository(path: str | Path, repository_root: str | Path) -> bool:\n    repo_text = str(repository_root).replace("\\\\", "/").rstrip("/").lower()\n    path_text = str(path).replace("\\\\", "/").rstrip("/").lower()\n    if path_text == repo_text or path_text.startswith(repo_text + "/"):\n        return True\n\n    try:\n        path_resolved = Path(path).resolve()\n        repo_resolved = Path(repository_root).resolve()\n    except (OSError, RuntimeError):\n        return False\n\n    try:\n        path_resolved.relative_to(repo_resolved)\n    except ValueError:\n        return False\n    return True\n''',
        '''def _is_inside_repository(path: str | Path, repository_root: str | Path) -> bool:\n    return is_path_within(path, repository_root)\n''',
    )

    changed |= replace_exact(
        "src/ethusdc_bot/data_pipeline/catalog_schema.py",
        "from ethusdc_bot.validation import (\n",
        "from ethusdc_bot.path_safety import is_path_within\n"
        "from ethusdc_bot.validation import (\n",
    )
    changed |= replace_exact(
        "src/ethusdc_bot/data_pipeline/catalog_schema.py",
        '''def _reject_repository_path(\n    path_value: str, repository_root: str | Path | None, path_name: str\n) -> None:\n    if repository_root is None:\n        return\n\n    repo_text = str(repository_root).replace("\\\\", "/").rstrip("/").lower()\n    value_text = str(path_value).replace("\\\\", "/").rstrip("/").lower()\n    if value_text == repo_text or value_text.startswith(repo_text + "/"):\n        raise SchemaValidationError(f"{path_name} must be outside the repository")\n\n    try:\n        repo_resolved = Path(repository_root).resolve()\n        value_resolved = Path(path_value).resolve()\n    except (OSError, RuntimeError):\n        return\n\n    try:\n        value_resolved.relative_to(repo_resolved)\n    except ValueError:\n        return\n    raise SchemaValidationError(f"{path_name} must be outside the repository")\n''',
        '''def _reject_repository_path(\n    path_value: str, repository_root: str | Path | None, path_name: str\n) -> None:\n    if repository_root is None:\n        return\n    if is_path_within(path_value, repository_root):\n        raise SchemaValidationError(f"{path_name} must be outside the repository")\n''',
    )

    print("review fixes changed files" if changed else "review fixes already applied")


if __name__ == "__main__":
    main()
