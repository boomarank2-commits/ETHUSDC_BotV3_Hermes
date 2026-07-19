"""Adversarial Task-12 path-ordering regression tests."""

from pathlib import Path
import os
import subprocess
import sys

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


def test_core_reader_rejects_outside_path_before_json_open_in_fresh_process(
    tmp_path: Path,
) -> None:
    (tmp_path / store.INDEX_ROOT).mkdir(parents=True)
    outside = tmp_path.parent / "outside_task12_core_index.json"
    outside.write_text("not-json", encoding="utf-8")
    code = (
        "from ethusdc_bot.protocol_v3 import artifact_store as s;"
        "from pathlib import Path;"
        f"repo=Path(r'{tmp_path}'); outside=Path(r'{outside}');"
        "\ntry:\n s.read_compact_artifact_bundle(outside, repo)\n"
        "except Exception as exc:\n print(type(exc).__name__ + ':' + str(exc))\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            text=True,
            capture_output=True,
            check=True,
            env=env,
        )
    finally:
        outside.unlink(missing_ok=True)
    assert "outside its canonical root" in result.stdout
    assert "unreadable or invalid" not in result.stdout
