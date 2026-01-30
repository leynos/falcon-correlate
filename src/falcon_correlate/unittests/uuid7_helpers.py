"""Shared helpers for UUIDv7 tests."""

from __future__ import annotations

import uuid

UUID_HEX_LENGTH = 32
UUID_VERSION = 7


def assert_uuid7_hex(value: str) -> None:
    """Assert that a value is a UUIDv7 hex string."""
    if not isinstance(value, str):
        msg = "expected UUIDv7 value to be a string"
        raise TypeError(msg)
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

    try:
        parsed = uuid.UUID(hex=value)
    except ValueError as exc:
        msg = "expected value to parse as a UUID"
        raise AssertionError(msg) from exc

    if parsed.version != UUID_VERSION:
        msg = "expected UUIDv7 version bits"
        raise AssertionError(msg)
    if parsed.variant != uuid.RFC_4122:
        msg = "expected RFC 4122 variant bits"
        raise AssertionError(msg)
