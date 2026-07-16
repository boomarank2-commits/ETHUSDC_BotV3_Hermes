"""Stable public Protocol v3 compact-artifact API for Task 12."""

from __future__ import annotations

from pathlib import Path

from ethusdc_bot.path_safety import is_path_within

from . import artifact_store as _artifact_store

# Re-export the complete validated Task-12 surface from the implementation module.
for _exported_name in _artifact_store.__all__:
    globals()[_exported_name] = getattr(_artifact_store, _exported_name)

_core_read_compact_artifact_bundle = _artifact_store.read_compact_artifact_bundle


def read_compact_artifact_bundle(
    index_path: str | Path,
    repository_root: str | Path,
):
    """Reject outside or symlinked index paths before opening any index bytes."""

    repo_candidate = Path(repository_root)
    if (
        not repo_candidate.exists()
        or not repo_candidate.is_dir()
        or repo_candidate.is_symlink()
    ):
        raise ProtocolV3ArtifactStoreError(
            "repository_root must be an existing real directory"
        )
    repo = repo_candidate.resolve()
    expected_root = repo / INDEX_ROOT
    if (
        not expected_root.exists()
        or not expected_root.is_dir()
        or expected_root.is_symlink()
    ):
        raise ProtocolV3ArtifactStoreError(
            "artifact index root is missing or unsafe"
        )
    expected_root = expected_root.resolve()
    if not is_path_within(expected_root, repo):
        raise ProtocolV3ArtifactStoreError(
            "artifact index root escapes repository_root"
        )

    candidate = Path(index_path)
    if not candidate.is_absolute():
        candidate = repo / candidate
    try:
        relative = candidate.relative_to(repo)
    except ValueError as exc:
        raise ProtocolV3ArtifactStoreError(
            "artifact index path is outside its canonical root"
        ) from exc

    current = repo
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ProtocolV3ArtifactStoreError(
                "symlinked artifact index paths are forbidden"
            )

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ProtocolV3ArtifactStoreError(
            "artifact index path is missing or unreadable"
        ) from exc
    if not is_path_within(resolved, expected_root):
        raise ProtocolV3ArtifactStoreError(
            "artifact index path is outside its canonical root"
        )
    return _core_read_compact_artifact_bundle(resolved, repo)


# Direct imports of the implementation module must receive the same corrected
# public reader after this stable facade has been imported.
_artifact_store.read_compact_artifact_bundle = read_compact_artifact_bundle

globals()["read_compact_artifact_bundle"] = read_compact_artifact_bundle
__all__ = _artifact_store.__all__
