"""Cross-platform path containment checks for repository safety rules.

The bot is developed on Windows but is also validated in Linux CI.  Native
``Path.resolve()`` must not reinterpret an absolute Windows path such as
``C:/TradingBot/data`` as a relative POSIX path below the checkout directory.
This module compares Windows and POSIX paths using their own path semantics and
never creates directories or touches market data.
"""

from __future__ import annotations

import ntpath
from pathlib import Path, PureWindowsPath


def is_path_within(path: str | Path, root: str | Path) -> bool:
    """Return whether *path* is equal to or below *root*.

    Windows absolute paths are compared with Windows semantics even when this
    function runs on Linux.  Paths using different absolute path flavours are
    necessarily disjoint.  Native paths fall back to resolved ``Path`` values.
    Resolution errors fail open for containment only, so callers can still
    reject a path for separate existence or policy reasons without falsely
    classifying it as repository-local.
    """

    path_text = _normalized_text(path)
    root_text = _normalized_text(root)

    if path_text == root_text or path_text.startswith(root_text + "/"):
        return True

    path_is_windows = _is_absolute_windows_path(path_text)
    root_is_windows = _is_absolute_windows_path(root_text)
    if path_is_windows or root_is_windows:
        if not (path_is_windows and root_is_windows):
            return False
        try:
            normalized_path = ntpath.normcase(ntpath.normpath(path_text))
            normalized_root = ntpath.normcase(ntpath.normpath(root_text))
            return ntpath.commonpath([normalized_path, normalized_root]) == normalized_root
        except ValueError:
            return False

    try:
        path_resolved = Path(path).resolve()
        root_resolved = Path(root).resolve()
    except (OSError, RuntimeError):
        return False

    try:
        path_resolved.relative_to(root_resolved)
    except ValueError:
        return False
    return True


def _normalized_text(value: str | Path) -> str:
    return str(value).replace("\\", "/").rstrip("/").lower()


def _is_absolute_windows_path(value: str) -> bool:
    parsed = PureWindowsPath(value)
    return bool(parsed.drive and parsed.root)


__all__ = ["is_path_within"]
