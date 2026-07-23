"""Task-12 tests for compact content-addressed Protocol v3 artifacts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

import pytest

from ethusdc_bot.protocol_v3 import artifact_store as store
from ethusdc_bot.protocol_v3 import artifact_store_api
from ethusdc_bot.protocol_v3.reporting_api import (
    PROTOCOL_V3_RESEARCH,
    build_protocol_v3_report,
    write_protocol_v3_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN = "protocol_v3_run_sha256:" + "a" * 64
PIPELINE = "protocol_v3_pipeline_sha256:" + "b" * 64


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parent_report(repo: Path, report_id: str = "research_parent") -> Path:
    report = build_protocol_v3_report(
        artifact_kind=PROTOCOL_V3_RESEARCH,
        report_id=report_id,
        created_at_utc=_now(),
        run_fingerprint=RUN,
        pipeline_generation=PIPELINE,
        window_id="historical_window",
        start_inclusive_utc="2024-01-01T00:00:00Z",
        end_exclusive_utc="2025-01-01T00:00:00Z",
        process_oos_net_usdc=None,
        producer="task12_fixture",
        producer_status="completed_diagnostic",
    )
    return write_protocol_v3_report(report, repo)


def _artifacts() -> dict[str, store.ArtifactPayload]:
    return {
        "trades": store.build_artifact_payload(
            store.TRADES,
            [
                {
                    "trade_id": "trade_001",
                    "entry_time_utc": "2025-01-01T00:01:00Z",
                    "exit_time_utc": "2025-01-01T00:05:00Z",
                    "net_usdc": 1.25,
                    "data": {"exit_reason": "tp", "quantity": 0.031},
                }
            ],
        ),
        "daily": store.build_artifact_payload(
            store.DAILY_MTM,
            [
                {"day_utc": "2025-01-01", "net_mtm_usdc": 1.25},
                {"day_utc": "2025-01-02", "net_mtm_usdc": 0.0},
                {"day_utc": "2025-01-03", "net_mtm_usdc": -0.25},
            ],
            coverage={
                "start_inclusive_utc": "2025-01-01T00:00:00Z",
                "end_exclusive_utc": "2025-01-04T00:00:00Z",
                "calendar_days": 3,
            },
        ),
        "equity": store.build_artifact_payload(
            store.EQUITY_UNDERWATER,
            [
                {"timestamp_utc": "2025-01-01T23:59:59Z", "equity_usdc": 1.25, "underwater_usdc": 0.0},
                {"timestamp_utc": "2025-01-02T23:59:59Z", "equity_usdc": 1.25, "underwater_usdc": 0.0},
                {"timestamp_utc": "2025-01-03T23:59:59Z", "equity_usdc": 1.0, "underwater_usdc": -0.25},
            ],
        ),
        "diagnostics": store.build_artifact_payload(
            store.DIAGNOSTICS,
            [
                {
                    "record_id": "fold_01",
                    "category": "fold_candidate_evidence",
                    "data": {"candidate_id": "candidate_01", "passed": False},
                }
            ],
        ),
    }


def _persist(repo: Path, *, work_unit_id: str = "origin_01_cycle_01", artifacts=None) -> Path:
    return store.persist_compact_artifact_bundle(
        parent_report_path=_parent_report(repo),
        repository_root=repo,
        work_unit_id=work_unit_id,
        work_unit_identity={"origin": 1, "cycle": 1, "phase": "task12_fixture"},
        artifacts=artifacts or _artifacts(),
    )


def _rewrite_index(path: Path, payload: dict) -> None:
    basis = dict(payload)
    basis.pop("index_id", None)
    basis.pop("index_sha256", None)
    digest = hashlib.sha256(store._serialized_bytes(store._canonical_json(basis))).hexdigest()
    payload["index_id"] = f"protocol_v3_artifact_index_sha256:{digest}"
    payload["index_sha256"] = digest
    path.write_bytes(store._serialized_bytes(store._canonical_json(payload)))


def test_contract_and_public_api_are_exact_and_pipeline_bound() -> None:
    contract = store.load_artifact_store_contract(REPO_ROOT)
    assert contract["contract_version"] == store.ARTIFACT_STORE_CONTRACT_VERSION
    assert contract["size_policy"]["representative_references"] == 12 * 8 * 4 == 384
    assert contract["size_policy"]["max_references"] == 768
    assert contract["storage_policy"]["index_embeds_records"] is False
    assert artifact_store_api.__all__ == store.__all__
    for name in store.__all__:
        assert getattr(artifact_store_api, name) is getattr(store, name)

    pipeline = json.loads((REPO_ROOT / "configs/protocol_v3_pipeline_contract.json").read_text())
    assert store.ARTIFACT_STORE_CONTRACT_VERSION in pipeline["component_contracts"]["quality_gates"]
    bindings = pipeline["source_bindings"]["quality_gates"]
    assert "configs/protocol_v3_artifact_store_contract.json" in bindings
    assert "src/ethusdc_bot/protocol_v3/artifact_store.py" in bindings
    assert "src/ethusdc_bot/protocol_v3/artifact_store_api.py" in bindings


def test_roundtrip_reconstructs_all_series_and_sums(tmp_path: Path) -> None:
    index_path = _persist(tmp_path)
    bundle = store.read_compact_artifact_bundle(index_path, tmp_path)

    assert set(bundle.artifacts) == {"trades", "daily", "equity", "diagnostics"}
    daily = bundle.artifacts["daily"].to_dict()["records"]
    assert [row["day_utc"] for row in daily] == ["2025-01-01", "2025-01-02", "2025-01-03"]
    assert daily[1]["net_mtm_usdc"] == 0.0
    assert sum(row["net_mtm_usdc"] for row in daily) == pytest.approx(1.0)
    trades = bundle.artifacts["trades"].to_dict()["records"]
    assert sum(row["net_usdc"] for row in trades) == pytest.approx(1.25)
    index = bundle.index.to_dict()
    assert all("records" not in reference for reference in index["artifacts"])
    assert "records" not in index


def test_zero_day_is_valid_but_missing_day_is_not() -> None:
    zero = store.build_artifact_payload(
        store.DAILY_MTM,
        [
            {"day_utc": "2025-01-01", "net_mtm_usdc": 0.0},
            {"day_utc": "2025-01-02", "net_mtm_usdc": 0.0},
        ],
        coverage={
            "start_inclusive_utc": "2025-01-01T00:00:00Z",
            "end_exclusive_utc": "2025-01-03T00:00:00Z",
            "calendar_days": 2,
        },
    )
    assert zero.logical_cardinality == 2

    with pytest.raises(store.ProtocolV3ArtifactStoreError, match="every covered UTC day"):
        store.build_artifact_payload(
            store.DAILY_MTM,
            [{"day_utc": "2025-01-01", "net_mtm_usdc": 0.0}],
            coverage={
                "start_inclusive_utc": "2025-01-01T00:00:00Z",
                "end_exclusive_utc": "2025-01-03T00:00:00Z",
                "calendar_days": 2,
            },
        )


def test_identical_bytes_deduplicate_but_references_remain_distinct(tmp_path: Path) -> None:
    payload = _artifacts()["diagnostics"]
    index_path = _persist(
        tmp_path,
        artifacts={"diagnostic_a": payload, "diagnostic_b": payload},
    )
    bundle = store.read_compact_artifact_bundle(index_path, tmp_path)
    refs = bundle.index.to_dict()["artifacts"]
    assert refs[0]["sha256"] == refs[1]["sha256"]
    objects = list((tmp_path / store.OBJECT_ROOT).rglob("*.json"))
    assert len(objects) == 1
    assert set(bundle.artifacts) == {"diagnostic_a", "diagnostic_b"}


def test_different_content_never_collides_by_name_or_metadata(tmp_path: Path) -> None:
    first = store.build_artifact_payload(
        store.DIAGNOSTICS,
        [{"record_id": "a", "category": "x", "data": {"value": 1}}],
    )
    second = store.build_artifact_payload(
        store.DIAGNOSTICS,
        [{"record_id": "a", "category": "x", "data": {"value": 2}}],
    )
    assert first.sha256 != second.sha256
    index_path = _persist(tmp_path, artifacts={"first": first, "second": second})
    refs = store.read_compact_artifact_bundle(index_path, tmp_path).index.to_dict()["artifacts"]
    assert refs[0]["relative_path"] != refs[1]["relative_path"]
    assert len(list((tmp_path / store.OBJECT_ROOT).rglob("*.json"))) == 2


@pytest.mark.parametrize("mode", ["missing", "truncated", "tampered"])
def test_missing_truncated_or_tampered_object_blocks(tmp_path: Path, mode: str) -> None:
    index_path = _persist(tmp_path)
    index = store.read_compact_artifact_bundle(index_path, tmp_path).index.to_dict()
    ref = index["artifacts"][0]
    object_path = tmp_path / store.OBJECT_ROOT / ref["relative_path"]
    if mode == "missing":
        object_path.unlink()
    elif mode == "truncated":
        object_path.write_bytes(object_path.read_bytes()[:20])
    else:
        raw = json.loads(object_path.read_text())
        raw["logical_cardinality"] += 1
        object_path.write_text(json.dumps(raw, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(store.ProtocolV3ArtifactStoreError):
        store.read_compact_artifact_bundle(index_path, tmp_path)


def test_swapped_schema_and_wrong_provenance_block_even_with_formal_index_digest(tmp_path: Path) -> None:
    index_path = _persist(tmp_path)
    payload = json.loads(index_path.read_text())
    swapped = deepcopy(payload)
    swapped["artifacts"][0]["artifact_kind"] = store.DIAGNOSTICS
    swapped["artifacts"][0]["artifact_schema"] = store.ARTIFACT_SCHEMAS[store.DIAGNOSTICS]
    swapped["artifacts"][0]["relative_path"] = (
        f"{store.DIAGNOSTICS}/{swapped['artifacts'][0]['sha256'][:2]}/"
        f"{swapped['artifacts'][0]['sha256']}.json"
    )
    _rewrite_index(index_path, swapped)
    with pytest.raises(store.ProtocolV3ArtifactStoreError):
        store.read_compact_artifact_bundle(index_path, tmp_path)

    index_path.unlink()
    original = payload
    original["artifacts"][0]["provenance"]["work_unit_sha256"] = "c" * 64
    _rewrite_index(index_path, original)
    with pytest.raises(store.ProtocolV3ArtifactStoreError, match="provenance"):
        store.read_compact_artifact_bundle(index_path, tmp_path)


def test_existing_corrupt_digest_object_is_never_overwritten(tmp_path: Path) -> None:
    report_path = _parent_report(tmp_path)
    payload = _artifacts()["diagnostics"]
    object_path = (
        tmp_path
        / store.OBJECT_ROOT
        / payload.artifact_kind
        / payload.sha256[:2]
        / f"{payload.sha256}.json"
    )
    object_path.parent.mkdir(parents=True)
    object_path.write_bytes(b"corrupt\n")
    before = object_path.read_bytes()
    with pytest.raises(store.ProtocolV3ArtifactStoreError):
        store.persist_compact_artifact_bundle(
            parent_report_path=report_path,
            repository_root=tmp_path,
            work_unit_id="wu",
            work_unit_identity={"origin": 1},
            artifacts={"diagnostics": payload},
        )
    assert object_path.read_bytes() == before


def test_traversal_symlink_and_raw_candle_payloads_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(store.ProtocolV3ArtifactStoreError, match="raw candle"):
        store.build_artifact_payload(
            store.DIAGNOSTICS,
            [{"record_id": "a", "category": "x", "data": {"candles": []}}],
        )

    report_path = _parent_report(tmp_path)
    with pytest.raises(store.ProtocolV3ArtifactStoreError, match="raw candle"):
        store.persist_compact_artifact_bundle(
            parent_report_path=report_path,
            repository_root=tmp_path,
            work_unit_id="wu_raw",
            work_unit_identity={"raw_candles": []},
            artifacts={"diagnostics": _artifacts()["diagnostics"]},
        )

    index_path = store.persist_compact_artifact_bundle(
        parent_report_path=report_path,
        repository_root=tmp_path,
        work_unit_id="wu_safe",
        work_unit_identity={"origin": 1},
        artifacts={"diagnostics": _artifacts()["diagnostics"]},
    )
    payload = json.loads(index_path.read_text())
    payload["artifacts"][0]["relative_path"] = "../escape.json"
    _rewrite_index(index_path, payload)
    with pytest.raises(store.ProtocolV3ArtifactStoreError, match="inside|root|relative|content address"):
        store.read_compact_artifact_bundle(index_path, tmp_path)

    if hasattr(Path, "symlink_to"):
        clean_repo = tmp_path / "symlink_case"
        clean_repo.mkdir()
        index_path = _persist(clean_repo)
        index = json.loads(index_path.read_text())
        ref = index["artifacts"][0]
        object_path = clean_repo / store.OBJECT_ROOT / ref["relative_path"]
        target = clean_repo / "outside.json"
        target.write_bytes(object_path.read_bytes())
        object_path.unlink()
        try:
            object_path.symlink_to(target)
        except OSError:
            pytest.skip("symlinks are unavailable")
        with pytest.raises(store.ProtocolV3ArtifactStoreError, match="symlink"):
            store.read_compact_artifact_bundle(index_path, clean_repo)


def test_representative_12_origin_index_is_compact_and_row_count_independent(tmp_path: Path) -> None:
    index_path = _persist(tmp_path, artifacts={"diagnostics": _artifacts()["diagnostics"]})
    base = store.read_compact_artifact_bundle(index_path, tmp_path).index.to_dict()
    prototype = base["artifacts"][0]
    refs = []
    for index in range(store.REPRESENTATIVE_REFERENCES):
        ref = deepcopy(prototype)
        ref["reference_id"] = f"origin_cycle_artifact_{index:04d}"
        refs.append(ref)
    representative = store._build_index_payload(
        parent_report=base["parent_report"],
        run_fingerprint=base["run_fingerprint"],
        pipeline_generation=base["pipeline_generation"],
        work_unit=base["work_unit"],
        references=refs,
    )
    validated = store.validate_artifact_index(representative)
    representative_size = len(store._serialized_bytes(validated.canonical_json))
    assert representative_size < store.MAX_INDEX_BYTES
    assert len(validated.to_dict()["artifacts"]) == 12 * 8 * 4

    few_rows = deepcopy(representative)
    many_rows = deepcopy(representative)
    for ref in few_rows["artifacts"]:
        ref["logical_cardinality"] = 1
        ref["byte_size"] = 100
    for ref in many_rows["artifacts"]:
        ref["logical_cardinality"] = 999_999
        ref["byte_size"] = 999_999_999
    few = store._build_index_payload(
        parent_report=few_rows["parent_report"],
        run_fingerprint=few_rows["run_fingerprint"],
        pipeline_generation=few_rows["pipeline_generation"],
        work_unit=few_rows["work_unit"],
        references=few_rows["artifacts"],
    )
    many = store._build_index_payload(
        parent_report=many_rows["parent_report"],
        run_fingerprint=many_rows["run_fingerprint"],
        pipeline_generation=many_rows["pipeline_generation"],
        work_unit=many_rows["work_unit"],
        references=many_rows["artifacts"],
    )
    size_few = len(store._serialized_bytes(store.validate_artifact_index(few).canonical_json))
    size_many = len(store._serialized_bytes(store.validate_artifact_index(many).canonical_json))
    assert abs(size_many - size_few) < store.REPRESENTATIVE_REFERENCES * 20


def test_store_recomputes_digest_size_and_cardinality_instead_of_trusting_caller(tmp_path: Path) -> None:
    report_path = _parent_report(tmp_path)
    valid = _artifacts()["diagnostics"]
    forged = replace(valid, sha256="0" * 64, byte_size=1, logical_cardinality=999)
    index_path = store.persist_compact_artifact_bundle(
        parent_report_path=report_path,
        repository_root=tmp_path,
        work_unit_id="wu_recomputed",
        work_unit_identity={"origin": 1},
        artifacts={"diagnostics": forged},
    )
    reference = store.read_compact_artifact_bundle(index_path, tmp_path).index.to_dict()["artifacts"][0]
    assert reference["sha256"] == valid.sha256
    assert reference["byte_size"] == valid.byte_size
    assert reference["logical_cardinality"] == valid.logical_cardinality


def test_duplicate_keys_nonfinite_values_and_unknown_index_fields_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(store.ProtocolV3ArtifactStoreError, match="finite"):
        store.build_artifact_payload(
            store.DIAGNOSTICS,
            [{"record_id": "a", "category": "x", "data": {"value": float("nan")}}],
        )

    index_path = _persist(tmp_path, artifacts={"diagnostics": _artifacts()["diagnostics"]})
    text = index_path.read_text()
    duplicate = text.replace('"protocol_version":"3.0.0"', '"protocol_version":"3.0.0","protocol_version":"3.0.0"', 1)
    index_path.write_text(duplicate)
    with pytest.raises(store.ProtocolV3ArtifactStoreError, match="duplicate JSON key"):
        store.read_compact_artifact_bundle(index_path, tmp_path)

    index_path.write_text(text)
    payload = json.loads(text)
    payload["unexpected"] = True
    index_path.write_bytes(store._serialized_bytes(store._canonical_json(payload)))
    with pytest.raises(store.ProtocolV3ArtifactStoreError, match="keys are invalid"):
        store.read_compact_artifact_bundle(index_path, tmp_path)


def test_generated_artifact_roots_are_gitignored() -> None:
    ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "reports/protocol_v3/artifacts/" in ignore
    assert "reports/protocol_v3/artifact_indexes/" in ignore
