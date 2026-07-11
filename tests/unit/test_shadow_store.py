"""Tamper-evident and atomic persistence tests for Shadow mode."""

from __future__ import annotations

import json

import pytest

from ethusdc_bot.shadow.store import (
    GENESIS_HASH,
    ShadowIntegrityError,
    append_event,
    append_event_at_expected_head,
    canonical_json_bytes,
    iter_verified_events,
    read_event_tail,
    read_event_log,
    verify_event_log,
)


def test_append_only_event_log_uses_contiguous_sequence_and_hash_chain(tmp_path):
    path = tmp_path / "events.jsonl"

    first = append_event(
        path,
        "deployment_adopted",
        {"deployment_id": "shadow_1", "orders_enabled": False},
        timestamp_utc="2026-07-11T08:00:00Z",
    )
    second = append_event(
        path,
        "shadow_started",
        {"public_data_only": True},
        timestamp_utc="2026-07-11T08:01:00Z",
    )

    records = read_event_log(path)
    assert [record["sequence"] for record in records] == [1, 2]
    assert first["previous_hash"] == GENESIS_HASH
    assert second["previous_hash"] == first["event_hash"]
    assert verify_event_log(path) == {
        "valid": True,
        "event_count": 2,
        "last_event_hash": second["event_hash"],
    }


def test_event_log_fails_closed_after_payload_tampering(tmp_path):
    path = tmp_path / "events.jsonl"
    append_event(path, "deployment_adopted", {"budget": 100})
    record = json.loads(path.read_text(encoding="utf-8"))
    record["payload"]["budget"] = 1000
    path.write_bytes(canonical_json_bytes(record) + b"\n")

    with pytest.raises(ShadowIntegrityError, match="hash verification failed"):
        read_event_log(path)
    with pytest.raises(ShadowIntegrityError):
        append_event(path, "shadow_started", {})


def test_event_log_rejects_partial_record_instead_of_ignoring_it(tmp_path):
    path = tmp_path / "events.jsonl"
    append_event(path, "deployment_adopted", {"budget": 100})
    with path.open("ab") as handle:
        handle.write(b'{"schema_version":1')

    with pytest.raises(ShadowIntegrityError, match="partial record"):
        read_event_log(path)


def test_event_payload_rejects_non_finite_json_before_writing(tmp_path):
    path = tmp_path / "events.jsonl"

    with pytest.raises(ShadowIntegrityError, match="strict JSON"):
        append_event(path, "bad", {"net": float("nan")})

    assert not path.exists()


def test_empty_or_missing_event_log_has_verified_genesis_state(tmp_path):
    path = tmp_path / "missing.jsonl"

    assert read_event_log(path) == []
    assert verify_event_log(path) == {
        "valid": True,
        "event_count": 0,
        "last_event_hash": GENESIS_HASH,
    }


def test_expected_head_append_rejects_stale_writer_without_touching_log(tmp_path):
    path = tmp_path / "events.jsonl"
    first = append_event(path, "deployment_adopted", {"budget": 100})
    second = append_event_at_expected_head(
        path,
        "shadow_started",
        {"public_data_only": True},
        expected_sequence=2,
        expected_previous_hash=first["event_hash"],
    )
    before = path.read_bytes()

    with pytest.raises(ShadowIntegrityError, match="head changed"):
        append_event_at_expected_head(
            path,
            "stale_writer",
            {},
            expected_sequence=2,
            expected_previous_hash=first["event_hash"],
        )

    assert path.read_bytes() == before
    assert read_event_log(path)[-1] == second


def test_expected_head_append_rejects_partial_tail(tmp_path):
    path = tmp_path / "events.jsonl"
    first = append_event(path, "deployment_adopted", {"budget": 100})
    with path.open("ab") as handle:
        handle.write(b"partial")

    with pytest.raises(ShadowIntegrityError, match="partial record"):
        append_event_at_expected_head(
            path,
            "shadow_started",
            {},
            expected_sequence=2,
            expected_previous_hash=first["event_hash"],
        )


def test_streaming_verifier_and_tail_cursor_match_full_read(tmp_path):
    path = tmp_path / "events.jsonl"
    first = append_event(path, "deployment_adopted", {"budget": 100})
    second = append_event(path, "shadow_started", {"public_data_only": True})

    assert list(iter_verified_events(path)) == [first, second]
    assert read_event_tail(path) == {
        "valid": True,
        "event_count": 2,
        "last_event_hash": second["event_hash"],
    }
