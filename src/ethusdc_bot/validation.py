"""Small strict schema validation helpers for Phase 1 templates.

This module intentionally uses only the Python standard library and contains no
trading, backtest, exchange, or runtime side effects.
"""

from collections.abc import Mapping, Sequence
from typing import Any


class SchemaValidationError(ValueError):
    """Raised when a Phase 1 template violates its strict schema."""


def require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaValidationError(f"{path} must be a mapping")
    return value


def require_exact_keys(data: Mapping[str, Any], expected_keys: set[str], path: str) -> None:
    actual_keys = set(data.keys())
    missing = expected_keys - actual_keys
    extra = actual_keys - expected_keys
    if missing:
        raise SchemaValidationError(f"{path} missing required keys: {sorted(missing)}")
    if extra:
        raise SchemaValidationError(f"{path} contains unknown keys: {sorted(extra)}")


def require_literal(data: Mapping[str, Any], key: str, expected: Any, path: str) -> None:
    if key not in data:
        raise SchemaValidationError(f"{path}.{key} is required")
    value = data[key]
    if value != expected or type(value) is not type(expected):
        raise SchemaValidationError(f"{path}.{key} must be {expected!r}")


def require_false(data: Mapping[str, Any], key: str, path: str) -> None:
    if key not in data:
        raise SchemaValidationError(f"{path}.{key} is required")
    if data[key] is not False:
        raise SchemaValidationError(f"{path}.{key} must be false")


def require_none(data: Mapping[str, Any], key: str, path: str) -> None:
    if key not in data:
        raise SchemaValidationError(f"{path}.{key} is required")
    if data[key] is not None:
        raise SchemaValidationError(f"{path}.{key} must be null")


def require_non_empty_string(data: Mapping[str, Any], key: str, path: str) -> None:
    if key not in data:
        raise SchemaValidationError(f"{path}.{key} is required")
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise SchemaValidationError(f"{path}.{key} must be a non-empty string")


def require_empty_list(data: Mapping[str, Any], key: str, path: str) -> None:
    if key not in data:
        raise SchemaValidationError(f"{path}.{key} is required")
    value = data[key]
    if not isinstance(value, list) or value:
        raise SchemaValidationError(f"{path}.{key} must be an empty list")


def require_exact_string_list(
    data: Mapping[str, Any], key: str, expected: list[str], path: str
) -> None:
    if key not in data:
        raise SchemaValidationError(f"{path}.{key} is required")
    value = data[key]
    if not isinstance(value, list):
        raise SchemaValidationError(f"{path}.{key} must be a list")
    if value != expected or any(type(item) is not str for item in value):
        raise SchemaValidationError(f"{path}.{key} must be {expected!r}")
