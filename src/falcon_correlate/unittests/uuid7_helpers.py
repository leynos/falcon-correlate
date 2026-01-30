"""Helper functions for UUIDv7 validation in tests."""

from __future__ import annotations

import uuid

UUID_HEX_LENGTH = 32
UUID_VERSION = 7


def _validate_type(value: str) -> None:
    """Validate that value is a string."""
    if not isinstance(value, str):
        msg = "expected UUIDv7 value to be a string"
        raise TypeError(msg)


def _validate_format(value: str) -> None:
    """Validate hex string format (length, lowercase, hex validity)."""
    if len(value) != UUID_HEX_LENGTH:
        msg = "expected 32-character UUID hex string"
        raise AssertionError(msg)
    if value != value.lower():
        msg = "expected lowercase hex characters"
        raise AssertionError(msg)
    try:
        int(value, 16)
    except ValueError as exc:
        msg = "expected value to be valid hexadecimal"
        raise AssertionError(msg) from exc


def _parse_uuid(value: str) -> uuid.UUID:
    """Parse hex string as UUID."""
    try:
        return uuid.UUID(hex=value)
    except ValueError as exc:
        msg = "expected value to parse as a UUID"
        raise AssertionError(msg) from exc


def _validate_uuid7_properties(parsed: uuid.UUID) -> None:
    """Validate UUID version and variant bits."""
    if parsed.version != UUID_VERSION:
        msg = "expected UUIDv7 version bits"
        raise AssertionError(msg)
    if parsed.variant != uuid.RFC_4122:
        msg = "expected RFC 4122 variant bits"
        raise AssertionError(msg)


def assert_uuid7_hex(value: str) -> None:
    """Assert that a value is a UUIDv7 hex string."""
    _validate_type(value)
    _validate_format(value)
    parsed = _parse_uuid(value)
    _validate_uuid7_properties(parsed)
