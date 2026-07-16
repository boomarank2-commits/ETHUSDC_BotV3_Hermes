"""Adversarial Task-12 path-ordering regression tests."""

from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import artifact_store_api as store


def test_public_reader_rejects_outside_path_before_json_open(tmp_path: Path) -> None:
    (tmp_path / store.INDEX_ROOT).mkdir(parents=True)
    outside = tmp_path.parent / "outside_task12_index.json"
    outside.write_text("not-json", encoding="utf-8")

    with pytest.raises(
        store.ProtocolV3ArtifactStoreError,
        match="outside its canonical root",
    ):
        store.read_compact_artifact_bundle(outside, tmp_path)


def test_public_reader_rejects_symlink_before_json_open(tmp_path: Path) -> None:
    index_root = tmp_path / store.INDEX_ROOT
    index_root.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text("not-json", encoding="utf-8")
    linked = index_root / "linked.json"
    try:
        linked.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(
        store.ProtocolV3ArtifactStoreError,
        match="symlinked artifact index paths are forbidden",
    ):
        store.read_compact_artifact_bundle(linked, tmp_path)
