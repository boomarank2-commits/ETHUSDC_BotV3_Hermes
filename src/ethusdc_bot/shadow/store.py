"""Atomic JSON persistence and tamper-evident append-only Shadow events."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterator

from ethusdc_bot.shadow.schema import (
    validate_shadow_deployment,
    validate_shadow_state,
)


EVENT_KEYS = {
    "schema_version",
    "sequence",
    "timestamp_utc",
    "event_type",
    "payload",
    "previous_hash",
    "event_hash",
}
GENESIS_HASH = "0" * 64


class ShadowIntegrityError(ValueError):
    """Raised when persisted Shadow data is malformed or has been changed."""


def utc_now() -> str:
    """Return a canonical UTC timestamp for persisted records."""

    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize JSON deterministically and reject NaN/Infinity."""

    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ShadowIntegrityError(f"value is not strict JSON: {exc}") from exc
    return encoded.encode("utf-8")


def write_deployment_atomic(path: str | Path, deployment: Mapping[str, Any]) -> Path:
    """Validate and atomically write one immutable deployment receipt."""

    validate_shadow_deployment(deployment)
    target = Path(path)
    if target.exists():
        raise FileExistsError(f"Shadow deployment receipt already exists: {target}")
    _write_json_atomic(target, deployment, overwrite=False)
    return target


def write_state_atomic(path: str | Path, state: Mapping[str, Any]) -> Path:
    """Validate and atomically replace the mutable Shadow snapshot."""

    validate_shadow_state(state)
    target = Path(path)
    _write_json_atomic(target, state, overwrite=True)
    return target


def load_deployment(path: str | Path) -> dict[str, Any]:
    return _load_validated_json(Path(path), validate_shadow_deployment)


def load_shadow_state(path: str | Path) -> dict[str, Any]:
    return _load_validated_json(Path(path), validate_shadow_state)


def append_event(
    path: str | Path,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    """Append an event after validating the complete existing hash chain."""

    if not isinstance(event_type, str) or not event_type.strip():
        raise ShadowIntegrityError("event_type must be a non-empty string")
    if not isinstance(payload, Mapping):
        raise ShadowIntegrityError("payload must be a mapping")
    # Validate serializability before touching the filesystem.
    payload_copy = json.loads(canonical_json_bytes(dict(payload)).decode("utf-8"))
    event_path = Path(path)
    existing = read_event_log(event_path)
    previous_hash = existing[-1]["event_hash"] if existing else GENESIS_HASH
    record_without_hash = {
        "schema_version": 1,
        "sequence": len(existing) + 1,
        "timestamp_utc": timestamp_utc or utc_now(),
        "event_type": event_type,
        "payload": payload_copy,
        "previous_hash": previous_hash,
    }
    _validate_timestamp(record_without_hash["timestamp_utc"], "event.timestamp_utc")
    record = {
        **record_without_hash,
        "event_hash": sha256(canonical_json_bytes(record_without_hash)).hexdigest(),
    }
    _validate_event(record, expected_sequence=len(existing) + 1, expected_previous_hash=previous_hash)
    event_path.parent.mkdir(parents=True, exist_ok=True)
    line = canonical_json_bytes(record) + b"\n"
    try:
        with event_path.open("ab") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ShadowIntegrityError(f"could not append Shadow event: {exc}") from exc
    return record


def append_event_at_expected_head(
    path: str | Path,
    event_type: str,
    payload: Mapping[str, Any],
    *,
    expected_sequence: int,
    expected_previous_hash: str,
    timestamp_utc: str | None = None,
) -> dict[str, Any]:
    """Append in O(last-record) time after an already verified open.

    The caller must serialize writers.  This function verifies the physical
    tail against the caller's exact expected sequence/hash before appending,
    so a stale runtime cannot silently extend a newer log.  Full-chain
    verification remains the responsibility of ``read_event_log`` and is
    performed by the runtime on open and at periodic audit boundaries.
    """

    if type(expected_sequence) is not int or expected_sequence < 1:
        raise ShadowIntegrityError("expected_sequence must be an integer >= 1")
    _validate_sha256(expected_previous_hash, "expected_previous_hash")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ShadowIntegrityError("event_type must be a non-empty string")
    if not isinstance(payload, Mapping):
        raise ShadowIntegrityError("payload must be a mapping")
    payload_copy = json.loads(canonical_json_bytes(dict(payload)).decode("utf-8"))
    event_path = Path(path)
    tail = _read_last_event(event_path)
    actual_sequence = tail["sequence"] if tail is not None else 0
    actual_hash = tail["event_hash"] if tail is not None else GENESIS_HASH
    if actual_sequence != expected_sequence - 1 or actual_hash != expected_previous_hash:
        raise ShadowIntegrityError(
            "Shadow event log head changed; writer must reopen before appending"
        )

    record_without_hash = {
        "schema_version": 1,
        "sequence": expected_sequence,
        "timestamp_utc": timestamp_utc or utc_now(),
        "event_type": event_type,
        "payload": payload_copy,
        "previous_hash": expected_previous_hash,
    }
    _validate_timestamp(record_without_hash["timestamp_utc"], "event.timestamp_utc")
    record = {
        **record_without_hash,
        "event_hash": sha256(canonical_json_bytes(record_without_hash)).hexdigest(),
    }
    _validate_event(
        record,
        expected_sequence=expected_sequence,
        expected_previous_hash=expected_previous_hash,
    )
    event_path.parent.mkdir(parents=True, exist_ok=True)
    line = canonical_json_bytes(record) + b"\n"
    try:
        with event_path.open("ab") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ShadowIntegrityError(f"could not append Shadow event: {exc}") from exc
    return record


def read_event_log(path: str | Path) -> list[dict[str, Any]]:
    """Read and verify every sequence number and hash-chain link."""

    return list(iter_verified_events(path))


def iter_verified_events(path: str | Path) -> Iterator[dict[str, Any]]:
    """Stream a complete verified hash chain without loading the file at once."""

    event_path = Path(path)
    if not event_path.exists():
        return
    previous_hash = GENESIS_HASH
    line_number = 0
    try:
        with event_path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.endswith(b"\n"):
                    raise ShadowIntegrityError(
                        "Shadow event log ends with a partial record"
                    )
                line = raw_line[:-1]
                if not line:
                    raise ShadowIntegrityError(
                        f"Shadow event log contains blank line {line_number}"
                    )
                try:
                    value = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ShadowIntegrityError(
                        f"Shadow event log line {line_number} is invalid JSON"
                    ) from exc
                if not isinstance(value, dict):
                    raise ShadowIntegrityError(
                        f"Shadow event log line {line_number} must be an object"
                    )
                _validate_event(
                    value,
                    expected_sequence=line_number,
                    expected_previous_hash=previous_hash,
                )
                previous_hash = value["event_hash"]
                yield value
    except OSError as exc:
        raise ShadowIntegrityError(f"could not read Shadow event log: {exc}") from exc


def verify_event_log(path: str | Path) -> dict[str, Any]:
    event_count = 0
    last_event_hash = GENESIS_HASH
    for record in iter_verified_events(path):
        event_count = record["sequence"]
        last_event_hash = record["event_hash"]
    return {
        "valid": True,
        "event_count": event_count,
        "last_event_hash": last_event_hash,
    }


def read_event_tail(path: str | Path) -> dict[str, Any]:
    """Return a self-verified O(last-record) cursor for read-only status UIs."""

    tail = _read_last_event(Path(path))
    return {
        "valid": True,
        "event_count": tail["sequence"] if tail is not None else 0,
        "last_event_hash": tail["event_hash"] if tail is not None else GENESIS_HASH,
    }


def _read_last_event(path: Path) -> dict[str, Any] | None:
    """Read and self-verify only the final complete JSONL record."""

    if not path.exists():
        return None
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            if size == 0:
                return None
            handle.seek(-1, os.SEEK_END)
            if handle.read(1) != b"\n":
                raise ShadowIntegrityError(
                    "Shadow event log ends with a partial record"
                )
            position = size - 2
            suffix = b""
            while position >= 0:
                chunk_size = min(65_536, position + 1)
                chunk_start = position - chunk_size + 1
                handle.seek(chunk_start)
                chunk = handle.read(chunk_size)
                newline = chunk.rfind(b"\n")
                if newline >= 0:
                    line = chunk[newline + 1 :] + suffix
                    break
                suffix = chunk + suffix
                position = chunk_start - 1
            else:
                line = suffix
    except OSError as exc:
        raise ShadowIntegrityError(f"could not read Shadow event log tail: {exc}") from exc
    if not line:
        raise ShadowIntegrityError("Shadow event log contains an empty final record")
    try:
        value = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowIntegrityError("Shadow event log final line is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ShadowIntegrityError("Shadow event log final line must be an object")
    sequence = value.get("sequence")
    if type(sequence) is not int or sequence < 1:
        raise ShadowIntegrityError("Shadow event log final sequence is invalid")
    previous_hash = value.get("previous_hash")
    _validate_sha256(previous_hash, "event.previous_hash")
    _validate_event(
        value,
        expected_sequence=sequence,
        expected_previous_hash=previous_hash,
    )
    return value


def _validate_event(
    event: Mapping[str, Any], *, expected_sequence: int, expected_previous_hash: str
) -> None:
    missing = EVENT_KEYS - set(event)
    extra = set(event) - EVENT_KEYS
    if missing or extra:
        raise ShadowIntegrityError(
            f"Shadow event keys are invalid; missing={sorted(missing)} extra={sorted(extra)}"
        )
    if event.get("schema_version") != 1 or type(event.get("schema_version")) is not int:
        raise ShadowIntegrityError("Shadow event schema_version must be 1")
    if event.get("sequence") != expected_sequence or type(event.get("sequence")) is not int:
        raise ShadowIntegrityError("Shadow event sequence is not contiguous")
    _validate_timestamp(event.get("timestamp_utc"), "event.timestamp_utc")
    if not isinstance(event.get("event_type"), str) or not event["event_type"].strip():
        raise ShadowIntegrityError("Shadow event event_type must be a non-empty string")
    if not isinstance(event.get("payload"), dict):
        raise ShadowIntegrityError("Shadow event payload must be an object")
    canonical_json_bytes(event["payload"])
    if event.get("previous_hash") != expected_previous_hash:
        raise ShadowIntegrityError("Shadow event previous_hash breaks the hash chain")
    _validate_sha256(event.get("previous_hash"), "event.previous_hash")
    event_hash = event.get("event_hash")
    if not isinstance(event_hash, str) or len(event_hash) != 64:
        raise ShadowIntegrityError("Shadow event event_hash is invalid")
    without_hash = {key: event[key] for key in EVENT_KEYS if key != "event_hash"}
    expected_hash = sha256(canonical_json_bytes(without_hash)).hexdigest()
    if event_hash != expected_hash:
        raise ShadowIntegrityError("Shadow event hash verification failed")


def _validate_sha256(value: object, path: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ShadowIntegrityError(f"{path} must be a lowercase SHA-256 hex digest")


def _load_validated_json(
    path: Path, validator: Callable[[Mapping[str, Any]], None]
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ShadowIntegrityError(f"could not load strict JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ShadowIntegrityError(f"{path} must contain a JSON object")
    try:
        validator(value)
    except ValueError as exc:
        raise ShadowIntegrityError(f"{path} failed schema validation: {exc}") from exc
    return value


def _write_json_atomic(path: Path, value: Mapping[str, Any], *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if not overwrite and path.exists():
            raise FileExistsError(f"refusing to overwrite immutable file: {path}")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_timestamp(value: object, path: str) -> None:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ShadowIntegrityError(f"{path} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ShadowIntegrityError(f"{path} is invalid") from exc
    if parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ShadowIntegrityError(f"{path} must be UTC")
